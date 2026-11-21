"""Normalize research claims and record the checks that support each decision."""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO
import json
import re

from .ingest import Source, normalize_text

EVENT_TYPES = {"fact", "market_observation", "attributed_view", "hypothesis"}
DATE_PRECISIONS = {"timestamp", "day", "month", "year", "range", "unknown"}
CAUSAL_WORDS = re.compile(r"直接导致|导致|引发|造成|致使|唯一原因")
CAUSAL_HEDGES = re.compile(r"不能|无法|不可|未能|并未|不能据此|不足以|是否|可能|怀疑|待核|候选")


def normalized_date(value: str, precision: str | None = None) -> str:
    text = normalize_text(value)
    if precision is None:
        precision = "timestamp" if re.search(r"\d:\d", text) else "day"
    if precision == "range":
        left, right = re.split(r"/|—|至", text, maxsplit=1)
        start, end = normalized_date(left, "day"), normalized_date(right, "day")
        if start > end:
            raise ValueError("Date range ends before it starts")
        return f"{start}/{end}"
    if precision == "timestamp":
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("Timestamp needs an explicit timezone offset")
        return stamp.isoformat()
    text = text.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").rstrip("-")
    parts = text.split("-")
    count = {"year": 1, "month": 2, "day": 3}.get(precision)
    if count is None or len(parts) != count or not re.fullmatch(r"[0-9]{4}", parts[0]):
        raise ValueError(f"Date does not match declared {precision} precision: {value}")
    year, month, day = map(int, parts + ["1"] * (3 - count))
    return date(year, month, day).isoformat()[: {1: 4, 2: 7, 3: 10}[count]]


def _date_forms(value: str) -> tuple[str, ...]:
    if "/" in value:
        start, end = value.split("/")
        y, m, d = map(int, start.split("-"))
        ey, em, ed = map(int, end.split("-"))
        if (y, m) == (ey, em):
            return (value, f"{m}月{d}–{ed}", f"{m}月{d}—{ed}", f"{m}月{d}-{ed}",
                    f"{m}月{d}日至{em}月{ed}日")
        return (value, f"{m}月{d}日至{em}月{ed}日")
    if "T" in value:
        return (value, value[:19].replace("T", ""))
    parts = value.split("-")
    if len(parts) == 1:
        return (value, value + "年")
    year, month = map(int, parts[:2])
    if len(parts) == 2:
        return (value, f"{year}年{month}月", f"{year}年{month:02d}月")
    day = int(parts[2])
    return (value, f"{year}年{month}月{day}日", f"{year}年{month:02d}月{day:02d}日", f"{month}月{day}日")


def _market_series(source: Source) -> dict[str, dict]:
    if source.metadata["parse_status"] != "PARSED" or not source.text:
        return {}
    rows = {}
    previous = None
    for raw in csv.DictReader(StringIO(source.text)):
        day = normalized_date(raw["date"], "day")
        if previous is not None and day <= previous:
            raise ValueError("Market dates must be unique and increasing")
        prices = {field: Decimal(raw[field]) for field in ("open", "close", "high", "low")}
        if not all(value.is_finite() and value > 0 for value in prices.values()):
            raise ValueError(f"Non-finite or nonpositive OHLC: {day}")
        if not prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]:
            raise ValueError(f"Inconsistent OHLC: {day}")
        rows[day] = {**prices, "previous_date": previous}
        previous = day
    return rows


def market_sources(sources: dict[str, Source]) -> dict[str, dict]:
    results = {}
    for source_id, source in sources.items():
        if source.metadata["type"] == "market_data" and source.metadata["file_type"] == "csv":
            try:
                results[source_id] = _market_series(source)
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                source.metadata.update(parse_status="PARSE_ERROR", parse_notes=str(error))
                results[source_id] = {}
    return results


def _calculate(rows: dict, assertion: dict) -> Decimal | bool:
    day = normalized_date(assertion["date"], "day")
    row = rows[day]
    op = assertion["operation"]
    if op in {"open", "close", "high", "low"}:
        return row[op]
    if op == "interval_return":
        earlier = normalized_date(assertion["previous_date"], "day")
        if earlier >= day:
            raise ValueError("Interval return needs an earlier baseline")
    else:
        earlier = row["previous_date"]
        if assertion.get("previous_date", earlier) != earlier:
            raise ValueError("Daily comparison must use the previous trading date")
    previous = rows[earlier]
    if op == "whole_session_down_gap":
        return row["high"] < previous["low"]
    if op == "whole_session_gap_points":
        return max(Decimal(0), previous["low"] - row["high"])
    if op in {"daily_return", "daily_return_at_most", "interval_return"}:
        percent = ((row["close"] / previous["close"] - 1) * 100).quantize(Decimal(".01"), ROUND_HALF_UP)
        if op == "daily_return_at_most":
            return percent <= Decimal(str(assertion["threshold"]))
        return percent
    raise ValueError(f"Unsupported arithmetic check: {op}")


def _check_market(event: dict, market: dict) -> list[dict]:
    assertions = event.get("market_assertions", [])
    if event.get("market_assertion"):
        assertions = [*assertions, event["market_assertion"]]
    checks = []
    default = [source_id for source_id in event["source_ids"] if source_id in market]
    for assertion in assertions:
        try:
            source_id = assertion.get("source_id", default[0] if len(default) == 1 else None)
            if source_id not in event["source_ids"]:
                raise ValueError("Market comparison must cite the CSV source")
            actual = _calculate(market[source_id], assertion)
            expected = assertion["expected"]
            match = (type(expected) is bool and expected == actual) if type(actual) is bool else (
                type(expected) is not bool and Decimal(str(expected)) == actual
            )
            checks.append({**assertion, "source_id": source_id, "actual": actual if type(actual) is bool else float(actual),
                           "passed": match})
        except (KeyError, AttributeError, TypeError, ValueError, InvalidOperation) as error:
            checks.append({"assertion": assertion, "passed": False, "reason": str(error)})
    return checks


def _check_excerpts(event: dict, sources: dict[str, Source]) -> list[dict]:
    checks = []
    for entry in event.get("evidence", []):
        source_id = entry["source_id"]
        excerpt = entry["excerpt"]
        source = sources.get(source_id)
        text = source.text if source and source.metadata["parse_status"] == "PARSED" else None
        registered = source_id in event["source_ids"] and source is not None
        normalized = normalize_text(excerpt)
        if not normalized or not registered:
            status = "invalid_reference"
        elif not text:
            status = "body_unavailable"
        else:
            status = "matched" if normalized in normalize_text(text) else "not_in_body"
        checks.append({"source_id": source_id, "excerpt": excerpt, "status": status})
    return checks


def _normalize_event(row: dict, provenance: str) -> dict:
    event = {name: row.get(name) for name in (
        "event_id", "event_date", "date_precision", "event_type", "title", "summary", "market_anchor",
        "category", "attribution", "announcement_at", "publication_at", "implementation_date",
    )}
    event["provenance"] = provenance
    event["source_ids"] = list(dict.fromkeys(row["source_ids"]))
    event["key_figures"] = row.get("key_figures", [])
    event["evidence"] = row.get("evidence", [])
    event["market_assertions"] = row.get("market_assertions", [])
    event["market_assertion"] = row.get("market_assertion")
    event["implementation_dates"] = row.get("implementation_dates", [])
    if not all(isinstance(event[key], str) and event[key].strip() for key in ("event_id", "title", "summary")):
        raise ValueError("Research event requires ID, title and summary")
    if event["event_type"] not in EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {event['event_type']}")
    if event["date_precision"] not in DATE_PRECISIONS:
        raise ValueError(f"Unsupported date precision: {event['date_precision']}")
    if event["date_precision"] != "unknown" or event["event_date"] is not None:
        event["event_date"] = normalized_date(event["event_date"], event["date_precision"])
    for field in ("announcement_at", "publication_at", "implementation_date", "market_anchor"):
        if event[field]:
            event[field] = normalized_date(event[field])
    event["implementation_dates"] = [
        {**item, "date": normalized_date(item["date"])} if isinstance(item, dict) else normalized_date(item)
        for item in event["implementation_dates"]
    ]
    if event["event_type"] == "attributed_view" and not event["attribution"]:
        raise ValueError("An attributed opinion needs a named speaker or institution")
    return event


def _causal_wording(row: dict) -> bool:
    if row.get("causal_claim") is True or row.get("relationship") == "direct_causal":
        return True
    for clause in re.split(r"[，。；;！？!?]", row["title"] + "。" + row["summary"]):
        if CAUSAL_WORDS.search(clause) and not CAUSAL_HEDGES.search(clause):
            return True
    return False


def verify_event(row: dict, provenance: str, sources: dict[str, Source], market: dict,
                 legacy: dict | None = None) -> dict:
    review = row.get("review", {}) if provenance == "local_dossier" else {}
    try:
        event = _normalize_event(row, provenance)
        excerpts = _check_excerpts(event, sources)
        arithmetic = _check_market(event, market)
        matched = [check for check in excerpts if check["status"] == "matched"]
        missing = [name for name in event["source_ids"]
                   if name not in sources or sources[name].metadata["parse_status"] != "PARSED"]
        source_text = " ".join(sources[check["source_id"]].text for check in matched)
        normalized_source = normalize_text(source_text)
        dates = list(dict.fromkeys(value for value in [
            event["event_date"], event["announcement_at"], event["publication_at"],
            event["implementation_date"],
            *(item["date"] if isinstance(item, dict) else item for item in event["implementation_dates"]),
        ] if value))
        date_checks = {value: any(form in normalized_source for form in _date_forms(value)) for value in dates}
        figures = [str(figure["value"]) for figure in event["key_figures"]]
        digits = normalize_text(" ".join(check["excerpt"] for check in matched)).replace(",", "").replace("−", "-")
        computed = {_number(check.get("actual")) for check in arithmetic if check["passed"]}
        figure_checks = {
            figure: _number(figure) in computed
            or re.search(r"(?<![\d.])" + re.escape(normalize_text(figure).replace(",", "").replace("−", "-"))
                         + r"(?![\d.])", digits) is not None
            for figure in figures
        }
        invalid_anchor = event["market_anchor"] and not any(event["market_anchor"] in rows for rows in market.values())
        direct_causal = _causal_wording(row)
        conflicts = review.get("conflict") is True or bool(row.get("contradicts"))
        disproved = any(not check["passed"] and "actual" in check for check in arithmetic)
        if disproved and review.get("refutation") is True:
            status = "REJECTED"
        elif direct_causal or conflicts or invalid_anchor or any(not check["passed"] for check in arithmetic):
            status = "DISPUTED"
        elif any(check["status"] in {"not_in_body", "invalid_reference"} for check in excerpts):
            status = "DISPUTED"
        elif not matched and not arithmetic:
            status = "NEEDS_EXTERNAL_RESEARCH"
        elif not arithmetic and event["event_type"] == "hypothesis":
            status = "NEEDS_EXTERNAL_RESEARCH"
        elif missing or event["event_type"] == "hypothesis" or provenance != "local_dossier":
            status = "PARTIALLY_VERIFIED"
        elif event["event_type"] == "market_observation" and arithmetic and all(figure_checks.values()):
            status = "VERIFIED"
        elif (matched and len(matched) == len(excerpts) and all(figure_checks.values())
              and dates and all(date_checks.values()) and review.get("body_support") is True
              and review.get("date_support") is True and (not figures or review.get("figures_support") is True)):
            status = "VERIFIED"
        else:
            status = "PARTIALLY_VERIFIED"
        event["verification_notes"] = {
            "excerpts": excerpts, "market_assertions": arithmetic, "date_matches": date_checks,
            "figure_matches": figure_checks, "unavailable_source_ids": missing,
            "invalid_market_anchor": bool(invalid_anchor), "direct_causal_claim": direct_causal,
            "conflict": conflicts, "scope_caution": review.get("conflict") if isinstance(review.get("conflict"), str) else None,
            "editor_review": review.get("notes"), "editor_observation": review.get("evidence_status"),
            "editor_body_support": review.get("body_support") is True,
            "editor_date_support": review.get("date_support") is True,
            "editor_figures_support": review.get("figures_support") is True,
        }
    except (AttributeError, KeyError, TypeError, ValueError, InvalidOperation) as error:
        raw_ids = row.get("source_ids")
        event = {
            "event_id": str(row.get("event_id") or "unidentified"),
            "event_date": None, "date_precision": "unknown", "event_type": "hypothesis",
            "title": str(row.get("title") or "格式无效"), "summary": str(row.get("summary") or "无法读取陈述"),
            "key_figures": [], "source_ids": [ref for ref in raw_ids if isinstance(ref, str)] if isinstance(raw_ids, list) else [],
            "evidence": [], "market_anchor": None, "provenance": provenance,
        }
        event["verification_notes"] = {"rejected": str(error)}
        status = "REJECTED"
    authored = provenance == "local_dossier"
    related = row.get("production_event_id", row.get("event_id")) if authored else None
    production_event = (legacy or {}).get(related, {})
    grade = production_event.get("release_grade")
    if grade is None and authored:
        grade = row.get("release_grade", review.get("release_grade"))
    grade = str(grade).upper() if grade is not None else None
    event["grade_provenance"] = {
        "existing_grade": grade, "production_event_id": related if production_event else None,
        "production_enabled": production_event.get("enabled"),
        "origin": "config/event_registry.json" if production_event else ("dossier_metadata" if grade else None),
        "decision": "Historical grade is contextual; verification is computed independently.",
    }
    candidate = status == "VERIFIED" and grade not in {"B", "C"}
    event["evidence_status"] = status
    event["narrative_candidate"] = candidate and row.get("narrative_candidate", True) is not False
    event["display_candidate"] = candidate and row.get("display_candidate", review.get("display_candidate", True)) is not False
    return event


def _number(value) -> str:
    if type(value) is bool:
        return str(value)
    text = normalize_text(str(value)).replace(",", "").replace("−", "-")
    try:
        return str(Decimal(text).normalize())
    except InvalidOperation:
        return text


def group_events(events: list[dict]) -> list[dict]:
    """Collapse identical claims and retain materially conflicting assertions."""
    groups = defaultdict(list)
    for event in events:
        fingerprint = (
            str(event.get("event_date")), str(event.get("date_precision")), str(event.get("event_type")),
            normalize_text(str(event.get("title", ""))).casefold(),
        )
        groups[fingerprint].append(event)
    output = []
    statuses = {"VERIFIED": 4, "PARTIALLY_VERIFIED": 3, "NEEDS_EXTERNAL_RESEARCH": 2, "DISPUTED": 1, "REJECTED": 0}
    for items in groups.values():
        chosen = max(items, key=lambda event: statuses[event["evidence_status"]])
        alternatives = {
            json.dumps([normalize_text(str(item.get("summary"))), item.get("key_figures")], ensure_ascii=False, sort_keys=True)
            for item in items
        }
        if len(alternatives) > 1:
            chosen.update(evidence_status="DISPUTED", narrative_candidate=False, display_candidate=False)
            chosen["verification_notes"]["conflicting_variants"] = [
                {name: item.get(name) for name in ("event_id", "summary", "key_figures", "source_ids", "provenance")}
                for item in items
            ]
        elif len(items) > 1:
            chosen["verification_notes"]["duplicates"] = [
                {name: item.get(name) for name in ("event_id", "source_ids", "provenance", "evidence_status")}
                for item in items if item is not chosen
            ]
            chosen["source_ids"] = list(dict.fromkeys(ref for item in items for ref in item["source_ids"]))
            evidence = {}
            for item in items:
                for record in item["evidence"]:
                    evidence[(record["source_id"], record["excerpt"])] = record
            chosen["evidence"] = list(evidence.values())
            if any(item["grade_provenance"]["existing_grade"] in {"B", "C"} for item in items):
                chosen.update(narrative_candidate=False, display_candidate=False)
        output.append(chosen)
    seen = defaultdict(list)
    for item in output:
        seen[item.get("event_id")].append(item)
    for event_id, items in seen.items():
        if len(items) > 1:
            for index, item in enumerate(items, 1):
                item.update(event_id=f"{event_id}-variant-{index}", evidence_status="DISPUTED",
                            narrative_candidate=False, display_candidate=False)
                item["verification_notes"]["conflicting_event_id"] = event_id
    return sorted(output, key=lambda item: (str(item.get("event_date") or "~"), str(item.get("event_id"))))
