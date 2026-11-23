"""Validate the V1.0.2 event references against their pinned V1.0.1 evidence."""

import csv
import hashlib
import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image


NEW_CITATIONS = {
    "V102-PMI-CX-100842068": "https://pmi.caixin.com/2015-08-21/100842068.html",
    "V102-ETF-CSJ-CNS": "https://www.chinanews.com/stock/2015/09-25/7544425.shtml",
    "V102-ETF-CSJ-PDF": "https://epaper.cs.com.cn/zgzqb/images/2015-09/25/A07/ZQBJD0010925C.pdf",
    "V102-ETF-CNS-0928": "https://www.chinanews.com/stock/2015/09-28/7548055.shtml",
    "V102-TURNOVER-CNS": "https://www.chinanews.com/stock/2015-09-28/7548354.shtml",
    "V102-TURNOVER-21CJ": "https://m.21jingji.com/article/20150928/herald/1e750135def82134d36e9eda0366b679.html",
}

EVENT_SOURCES = {
    "E-APR-01-01": ["APR-01:S02", "APR-01:S03"],
    "E-APR-01-04": ["APR-01:S06", "APR-01:WEB01"],
    "E-IND-01-04": ["IND-01:WEB01", "IND-01:WEB02", "IND-01:S01", "LETV-RAW-DAILY"],
    "E-JUN-01-01": ["JUN-01:S01"],
    "E-JUN-01-04": ["JUN-01:S04"],
    "E-JUN-02-01": ["JUN-02:S01", "JUN-02:S02"],
    "E-JUN-02-02": ["JUN-02:S03", "JUN-02:S04"],
    "E-JUN-02-03": ["JUN-02:S06", "JUN-02:S05"],
    "E-JUN-02-04": ["CSRC-2015-17"],
    "E-AUG-01-01": ["AUG-01:S01", "PBC-2015-Q3-REPORT"],
    "E-AUG-01-03": ["AUG-01:S03", "V102-PMI-CX-100842068"],
    "E-AUG-02-05": ["PBC-2015-0825", "PBC-2015-0825-TEXT"],
    "E-AUG-03-01": ["CNR-2015-0825-FULL"],
    "E-IMG-01-01": ["IMG-01:S01"],
    "E-SEP-ETF-01": ["V102-ETF-CSJ-CNS", "V102-ETF-CSJ-PDF", "V102-ETF-CNS-0928"],
    "E-SEP-TURNOVER-01": ["V102-TURNOVER-CNS", "V102-TURNOVER-21CJ"],
}

CONTEXT_BEATS = {
    "B03": ["E-APR-01-01", "E-APR-01-04"],
    "B04": ["E-IND-01-04"],
    "B07": ["E-JUN-01-01", "E-JUN-01-04"],
    "B13": ["E-IMG-01-01"],
}

# These are the register's factual time roles. Its display slots are separately
# chosen by the compiler and never inferred from the media publication time.
EXPECTED_ROWS = {
    "E-JUN-02-01": ("2015-06-27", "weekend_announcement", "2015-06-26"),
    "E-JUN-02-02": ("2015-07-04", "weekend_commitment", "2015-07-03"),
    "E-JUN-02-03": ("2015-07-04", "weekend_company_announcement", "2015-07-03"),
    "E-JUN-02-04": ("2015-07-05", "weekend_public_announcement", "2015-07-03"),
    "E-AUG-01-01": ("2015-08-11", "policy_mechanism_announcement", "2015-08-11"),
    "E-AUG-01-03": ("2015-08-21", "publisher_webpage_timestamp", None),
    "E-SEP-ETF-01": ("2015-09-07", "etf_share_observation_period", None),
    "E-SEP-TURNOVER-01": ("2015-09-28", "two_exchange_market_turnover", None),
    "E-AUG-02-05": ("2015-08-25", "official_pbc_webpage_timestamp", "2015-08-25"),
}

EXPECTED_BEAT_LINKS = {
    ("B08", "E-JUN-02-01"),
    ("B09", "E-JUN-02-02"),
    ("B09", "E-JUN-02-03"),
    ("B09", "E-JUN-02-04"),
    ("B12", "E-AUG-01-01"),
    ("B13", "E-AUG-01-03"),
    ("B14", "E-AUG-02-05"),
    ("B15", "E-AUG-02-05"),
    ("B17", "E-SEP-ETF-01"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pinned_source(root: Path, source: dict) -> dict:
    record = {key: source.get(key) for key in (
        "url", "published_at", "materialization", "original_path", "archive_member", "sha256"
    )}
    path = root / source["original_path"] if source.get("original_path") else None
    record["local_sha256"] = _sha256(path) if path and path.is_file() else None
    if record["local_sha256"] and source.get("sha256"):
        matched = record["local_sha256"] == source["sha256"]
        record["local_status"] = "BYTES_MATCH" if matched else "HASH_MISMATCH"
    else:
        record["local_status"] = "RELEASE_REVIEW_REFERENCE_ONLY"
    return record


def _photo(root: Path, release: Path, photo_path: Path | None) -> dict:
    manifest_path = release / "photo_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    asset = next(item for item in manifest["assets"] if item["asset_id"] == manifest["selected_asset_id"])
    record = {
        "asset_id": asset["asset_id"], "source_id": asset["source_id"], "approved_caption": asset["caption_safe"],
        "depicted_date": asset["depicted_date"], "published_date": asset["publication_date"],
        "expected_sha256": asset["sha256"], "expected_dimensions": asset["size"], "expected_bytes": asset["bytes"],
        "manifest_sha256": _sha256(manifest_path), "rights_status": asset["rights_status"],
        "public_release_ready": asset["public_release_ready"], "crop_rule": asset["crop_rule"],
        "status": "ORIGINAL_NOT_PRESENT", "media_rendered": False,
    }
    if photo_path is None:
        return record
    path = photo_path if photo_path.is_absolute() else root / photo_path
    if not path.is_file():
        return record
    observed = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    try:
        with Image.open(path) as image:
            observed.update(format=image.format, dimensions=list(image.size))
            image.verify()
    except (OSError, SyntaxError) as exc:
        observed["image_validation_error"] = str(exc)
    expected = {"sha256": asset["sha256"], "bytes": asset["bytes"], "format": "JPEG", "dimensions": asset["size"]}
    record.update(observed=observed, status="EXACT_INPUT_VERIFIED" if observed == expected else "INPUT_MISMATCH")
    return record


def audit_events(beats: list[dict], registry: dict, repo_root: Path, photo_path: Path | None) -> dict:
    """Return separate reproducible structural checks and unresolved editorial decisions."""
    release = repo_root / "editorial/2015/releases/v1.0.1"
    frozen = json.loads((release / "event_review.json").read_bytes())
    reviews = {row["event_id"]: row for row in frozen["events"] + frozen["supplemental_events"]}
    source_registry = json.loads((release / "source_registry.json").read_bytes())
    pinned = {row["source_id"]: row for row in source_registry["sources"]}
    needed = sorted({source_id for source_ids in EVENT_SOURCES.values() for source_id in source_ids})
    citations = {key: {"url": value, "local_status": "CITED_IN_CONTRACT_ORIGINAL_NOT_IMPORTED"}
                 for key, value in NEW_CITATIONS.items()}
    citations.update({key: _pinned_source(repo_root, pinned[key]) for key in needed if key in pinned})
    with (repo_root / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as handle:
        daily = {row["date"]: row for row in csv.DictReader(handle)}
    rows = registry["events"]
    by_id = {row.get("event_id", row.get("metric_id")): row for row in rows}
    structural = {
        "register_schema_and_timezone": registry["schema_version"] == "chinext-event-clock-register/1.0"
            and registry["timezone"] == "Asia/Shanghai",
        "register_ids_unique_and_complete": len(rows) == len(EXPECTED_ROWS) and set(by_id) == set(EXPECTED_ROWS),
        "pinned_source_ids_resolve": all(source_id in citations for source_id in needed),
        "local_source_hashes_match": all(row["local_status"] != "HASH_MISMATCH" for row in citations.values()),
        "pbc_html_and_derived_text_verified": all(citations.get(sid, {}).get("local_status") == "BYTES_MATCH"
                                                 for sid in EVENT_SOURCES["E-AUG-02-05"]),
    }
    beat_clocks = [(beat["id"], event) for beat in beats for event in beat.get("event_clock", [])]
    structural["beat_event_links_resolve"] = len(beat_clocks) == len(EXPECTED_BEAT_LINKS) and {
        (beat_id, event["event_id"]) for beat_id, event in beat_clocks
    } == EXPECTED_BEAT_LINKS
    beat_links = []
    for beat_id, beat_event in beat_clocks:
        event_id = beat_event["event_id"]
        target = by_id.get(event_id, {})
        target_day = target.get("date", target.get("observation_start"))
        target_role = target.get("role", "")
        target_market = target.get("market_anchor")
        if beat_id == "B15" and event_id == "E-AUG-02-05":
            target_day = "2015-08-26"
            target_role = "implementation_date"
            target_market = {"date": target_day, "field": "close", "value": float(daily[target_day]["close"])}
        role = beat_event.get("role", "").lower()
        role_alias = event_id == "E-JUN-02-04" and role == "public_announcement"
        checks = {
            "factual_day_matches_with_distinct_b15_effectiveness": beat_event.get("date") == target_day,
            "factual_role_matches_or_documented_alias": role == target_role or role_alias,
            "market_anchor_matches_register_or_declared_effective_day": (
                "market_anchor" not in beat_event or beat_event["market_anchor"] == target_market
            ),
            "supplementary_time_fields_match": all(beat_event[k] == target.get(k) for k in (
                "time", "timezone", "first_release_time", "implementation_date", "implementation_dates", "observation_end"
            ) if k in beat_event),
        }
        if event_id == "E-SEP-ETF-01":
            checks["publication_day_matches"] = beat_event.get("source_publication_date") == target.get("publication_date")
        beat_links.append({"beat": beat_id, "event_id": event_id, "role_alias_used": role_alias, "checks": checks})
    structural["beat_event_timing_and_market_references_match"] = all(all(row["checks"].values()) for row in beat_links)
    record_checks = {}
    for event_id, (day, role, market_day) in EXPECTED_ROWS.items():
        row = by_id.get(event_id, {})
        market = row.get("market_anchor", {})
        source_ids = EVENT_SOURCES[event_id]
        urls = [citations.get(sid, {}).get("url") for sid in source_ids]
        source_review = reviews.get(event_id)
        supplied_urls = row.get("sources", [])
        temporal = {
            "date_role_and_timezone": row.get("date", row.get("observation_start")) == day
                and date.fromisoformat(day).isoformat() == day and row.get("role") == role
                and row.get("timezone", registry["timezone"]) == "Asia/Shanghai",
            "market_date_and_price": market.get("date") == market_day and (not market_day or (
                market.get("field") == "close" and market_day in daily and (
                    market.get("value") is None and event_id == "E-AUG-01-01"
                    or Decimal(str(market.get("value"))) == Decimal(daily[market_day]["close"])
                )
            )),
            "citation_urls_resolve_to_bound_ids": all(
                urlsplit(url).scheme in {"http", "https"} and urlsplit(url).netloc and url in urls
                for url in supplied_urls
            ),
            "direct_source_ids_match": "source_ids" not in row or row["source_ids"] == source_ids,
            "timed_sources_are_not_first_release": "time" not in row or (
                time.fromisoformat(row["time"]).isoformat() == row["time"]
                and "first_release_time" in row and row["first_release_time"] is None
            ),
        }
        if source_review:
            temporal["frozen_event_date_matches"] = source_review["event_date"] == day
            frozen_ids = {source["source_id"] for source in source_review["source_evidence"]}
            temporal["bound_frozen_sources_match_review"] = all(sid in frozen_ids or sid in NEW_CITATIONS for sid in source_ids)
        if event_id == "E-JUN-02-01":
            temporal["separate_implementation_day"] = row.get("implementation_date") == "2015-06-28"
        if event_id == "E-AUG-01-03":
            temporal["strictly_webpage_evidence"] = row.get("time") == "09:43:10" and "47.1" in row.get("value", "")
        if event_id == "E-SEP-ETF-01":
            temporal["observation_and_publication_separate"] = row.get("observation_end") == "2015-09-22" and row.get("publication_date") == "2015-09-25"
            temporal["reported_share_arithmetic"] = (row.get("start_shares"), row.get("end_shares"), row.get("change_pct")) == (
                "12.37亿份", "18.07亿份", float(((Decimal("18.07") / Decimal("12.37") - 1) * 100).quantize(Decimal("0.01")))
            ) and row.get("first_party_original_imported") is False
        if event_id == "E-SEP-TURNOVER-01":
            temporal["two_market_scope_and_value"] = row.get("value") == "4044亿元" and "沪深两市成交额" in row.get("visual", "")
        if event_id == "E-AUG-02-05":
            temporal["separate_implementation_days"] = row.get("time") == "18:15:34" and row.get("implementation_dates") == [
                {"date": "2015-08-26", "policy": "benchmark interest-rate cuts"},
                {"date": "2015-09-06", "policy": "reserve requirement ratio cuts"},
            ]
        record_checks[event_id] = {
            "checks": temporal, "source_ids": list(source_ids), "original_role": row.get("role"),
            "frozen_review_status": source_review["review_status"] if source_review else None,
            "selected_in_v1_0_1": source_review["selected_in_candidate"] if source_review else None,
            "review_status": "FROZEN_REVIEW_LINKED" if source_review else "T2_CITATION_ONLY",
            "facts_as_registered": row,
        }

    context_events = {}
    for beat_id, event_ids in CONTEXT_BEATS.items():
        context_events[beat_id] = []
        for event_id in event_ids:
            item = reviews[event_id]
            bound = EVENT_SOURCES[event_id]
            original_source_ids = {source["source_id"] for source in item["source_evidence"]}
            context_events[beat_id].append({
                **{key: item.get(key) for key in ("event_id", "event_date", "date_precision", "publication_date",
                                                  "effective_date", "review_status", "approved_claim",
                                                  "screen_safe_copy", "unresolved")},
                "source_ids": bound,
                "frozen_review_sources_resolve": set(bound) <= original_source_ids,
                "historical_scene_date_is_event_date": True if event_id == "E-IMG-01-01" else None,
            })
    structural["context_sources_match_frozen_reviews"] = all(
        event["frozen_review_sources_resolve"] for events in context_events.values() for event in events
    )
    photo = _photo(repo_root, release, photo_path)
    structural["photo_input_if_supplied_matches"] = photo_path is None or photo["status"] == "EXACT_INPUT_VERIFIED"
    structural["documentary_citation_resolves"] = photo["source_id"] in citations
    judgments = [
        {"beat": "B03", "rule": "4/13 is implementation, 4/20–24 is the A-share account observation, 4/28 20:37 is the source publication; 413.03万户 is neither persons nor ChiNext-only."},
        {"beat": "B04", "rule": "LeTV closing market capitalization exceeds 1500亿元 on 5/13; index close 3192.15 is only the coincident OHLC context. No independently licensed historical company asset identified; use contract typography fallback."},
        {"beat": "B07", "rule": "Label June leverage as qualitative沪深 background and 8/27 retrospective publication; 6/18 is the market observation anchor, never the exact fact or publication date."},
        {"beat": "B08", "rule": "6/27 announcement and 6/28 effectiveness share the 6/26 frozen real close. Do not label the archived page timestamp as the first release time."},
        {"beat": "B09", "rule": "7/4 commitments and company announcements plus 7/5 CSRC statement are three distinct calendar events at 7/3 close. The IPO item is newly selected by the contract; it was supported with corrections but not selected in V1.0.1. Beat public_announcement vs register weekend_public_announcement for E-JUN-02-04 is an alias. Keep 将 and distinguish commitment from executed purchases."},
        {"beat": "B12", "rule": "The 8/11 FX mechanism change is same-day macro context. Register leaves market anchor value null; report the frozen close only as separate OHLC and avoid a causal effect."},
        {"beat": "B13", "rule": "Do not use the stale audience_takeaway 'PMI公布晚于当日开盘'. Label '财新网页刊发 09:43:10'; the distinct 09:40:30 page does not establish first release. If replaying 09:43, do not imply that the complete 8/21 OHLC was already available then."},
        {"beat": "B13", "rule": "Photo IMG-20150824-01 depicts the 8/24 scene. The gallery published at 16:39, a separate clock. Preserve proportion, photographer credit and watermark. Exact input availability establishes neither public-use rights nor visual approval."},
        {"beat": "B14–B15", "rule": "8/25 18:15:34 is the PBC page timestamp after close. 8/26 is the interest-rate cut effective day only; 9/6 is the RRR effective day and a Sunday calendar label. The B15 generic title is not literal publication copy. Do not simulate an intraday cross of 2000."},
        {"beat": "B17", "rule": "ETF is optional, observational T2 as the contract explicitly adjudicates. If selected, use attribution to 中国证券报援引深交所数据, 9/7–22 window and no earlier than 9/25 publication. Historical SZSE file not imported; do not turn shares into cash flows or causal attribution."},
        {"beat": "B17", "rule": "4044亿元 (1664+2380) is citation-linked T2 two-exchange turnover only. It is not an OHLC-derived metric or required beat event. Original reports have not been imported or independently read in this run."},
    ]
    return {
        "passed": all(structural.values()) and all(all(row["checks"].values()) for row in record_checks.values()),
        "verification_scope": "Pinned V1.0.1 records plus actual available local bytes; external new citations warrant no new fact verification or visual approval.",
        "structural_checks": structural, "register_entries_checked": len(record_checks), "register_entries": record_checks,
        "beat_links": beat_links, "pinned_v1_0_1_context_events": context_events,
        "sources": citations, "judgment_discrepancies_and_rules": judgments,
        "assets": {
            "photo": photo,
            "historical_letv_visual": "NO_LICENSED_HISTORICAL_VISUAL_IDENTIFIED_IN_PINNED_INPUTS_TEXT_FALLBACK_AUTHORIZED",
            "nasdaq_reference_recording": "ORIGINAL_NOT_ATTACHED_LOCAL_REVIEW_STILLS_AVAILABLE",
            "existing_visual_refs": {str(path.relative_to(repo_root)): _sha256(path) for path in (
                repo_root / "assets/reference/approved_visual_reference.png",
                repo_root / "assets/reference/earth_body_reference.png",
            ) if path.is_file()},
            "optional_szse_share_original": "NOT_IMPORTED",
        },
    }
