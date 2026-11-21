"""Join evidenced dates to contemporaneous market periods without inference."""

from bisect import bisect_left
from calendar import monthrange
from datetime import date, datetime, time
import re
from zoneinfo import ZoneInfo

from .market import Market


CHINA_TIME = ZoneInfo("Asia/Shanghai")


def _local_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(CHINA_TIME) if parsed.tzinfo else parsed.replace(tzinfo=CHINA_TIME)


def date_bounds(value: str | None, precision: str) -> tuple[str, str] | None:
    if not value or precision == "unknown":
        return None
    try:
        if precision in ("timestamp", "day"):
            day = _local_time(value).date() if precision == "timestamp" else date.fromisoformat(value)
            return day.isoformat(), day.isoformat()
        if precision == "range":
            start, end = map(date.fromisoformat, value.split("/"))
            if start <= end:
                return start.isoformat(), end.isoformat()
        if precision == "month":
            year, month = map(int, value.split("-"))
            return date(year, month, 1).isoformat(), date(year, month, monthrange(year, month)[1]).isoformat()
        if precision == "year":
            return date(int(value), 1, 1).isoformat(), date(int(value), 12, 31).isoformat()
    except ValueError:
        raise ValueError(f"Invalid {precision} event date: {value}") from None
    raise ValueError(f"Unsupported or reversed {precision} event date: {value}")


def _anchor_kind(market: Market, anchor: str | None, bounds: tuple[str, str] | None) -> str | None:
    if anchor not in market.by_date or bounds is None:
        return None
    start, end = bounds
    if start == end == anchor:
        return "same_trading_day"
    if start <= anchor <= end:
        return "period_observation"
    index = bisect_left(market.dates, start)
    if start == end and start not in market.by_date and index and market.dates[index - 1] == anchor:
        return "explicit_previous_trading_day"
    return None


def _has_verified_evidence(event: dict, source_registry: dict[str, dict]) -> bool:
    notes = event.get("verification_notes", {})
    source_ids = event.get("source_ids") or []
    if (
        event["evidence_status"] != "VERIFIED" or not source_ids
        or notes.get("direct_causal_claim") or notes.get("conflict")
        or notes.get("invalid_market_anchor") or notes.get("unavailable_source_ids")
    ):
        return False
    for source_id in source_ids:
        source = source_registry.get(source_id, {})
        if source.get("parse_status") != "PARSED" or not re.fullmatch(r"[a-f0-9]{64}", source.get("sha256") or ""):
            return False
    if event.get("event_type") == "market_observation":
        assertions = notes.get("market_assertions", [])
        return bool(assertions) and all(assertion.get("passed") is True for assertion in assertions)
    if event.get("event_type") not in {"fact", "attributed_view"}:
        return False
    excerpts = notes.get("excerpts", [])
    date_matches = notes.get("date_matches", {})
    return bool(
        excerpts and all(item.get("status") == "matched" and item.get("source_id") in source_ids for item in excerpts)
        and date_matches and all(date_matches.values())
        and all(notes.get("figure_matches", {}).values())
        and notes.get("editor_body_support") is True and notes.get("editor_date_support") is True
        and (event.get("event_type") != "attributed_view" or event.get("attribution"))
    )


def map_events(market: Market, periods: list[dict], events: list[dict], source_registry: dict[str, dict]) -> list[dict]:
    result = []
    seen = set()
    for event in events:
        event_id = event["event_id"]
        if event_id in seen:
            raise ValueError(f"Duplicate research event: {event_id}")
        seen.add(event_id)
        try:
            bounds = date_bounds(event.get("event_date"), event.get("date_precision", "unknown"))
        except ValueError:
            if event["evidence_status"] != "REJECTED":
                raise
            bounds = None
        matching = []
        if bounds:
            start, end = bounds
            for period in periods:
                first, last = max(start, period["start_date"]), min(end, period["end_date"])
                if first <= last:
                    matching.append({"period_id": period["period_id"], "start_date": first, "end_date": last})
        published = event.get("announcement_at") or event.get("publication_at")
        same_day_timestamp = _local_time(published) if bounds and published and "T" in published else None
        after_close = bool(same_day_timestamp and same_day_timestamp.date().isoformat() == bounds[0]
                           and bounds[0] in market.by_date and same_day_timestamp.time() > time(15))
        anchor = event.get("market_anchor")
        anchor_kind = _anchor_kind(market, anchor, bounds)
        verified = _has_verified_evidence(event, source_registry)
        grade = event.get("grade_provenance", {}).get("existing_grade")
        eligible = (verified and grade not in {"B", "C"} and event.get("display_candidate") is True and bool(matching) and
                    anchor_kind is not None)
        if not matching:
            strength, reason = "none", "证据日期暂无可定位的试点行情窗口。"
        elif bounds[0] == bounds[1] and anchor_kind is not None:
            strength, reason = "precise_date", "事件日和交易观察日分别保留，日期可精确对齐。"
        else:
            strength, reason = "period_only", "日期精度仅支持同一时期并列。"
        if after_close:
            reason += "公告在当日收盘之后，时间轨保留当日已发生的收盘。"
        result.append({
            "event_id": event_id, "event_type": event.get("event_type"), "title": event.get("title") or event_id,
            "event_date": event.get("event_date"), "date_precision": event.get("date_precision", "unknown"),
            "announcement_at": event.get("announcement_at"), "publication_at": event.get("publication_at"),
            "implementation_date": event.get("implementation_date"),
            "implementation_dates": event.get("implementation_dates", []),
            "after_close": after_close,
            "relevant_market_intervals": matching, "market_anchor": anchor,
            "market_anchor_kind": anchor_kind, "relation": "co_occurrence" if matching else "unmapped",
            "mapping_strength": strength, "mapping_reason": reason, "causal_claim": False,
            "evidence_status": event["evidence_status"], "source_ids": event.get("source_ids", []),
            "on_screen_eligible": eligible, "context_only": not eligible,
            "needs_background_explanation": event.get("event_type") != "market_observation" or after_close,
            "further_research_needed": not verified,
        })
    return result
