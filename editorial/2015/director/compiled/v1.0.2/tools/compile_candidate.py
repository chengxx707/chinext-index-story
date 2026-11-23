"""Compile the pinned 2015 director contract and check it without producing media."""

import argparse
from copy import deepcopy
import csv
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from jsonschema import Draft202012Validator
from PIL import ImageFont

from event_audit import EVENT_SOURCES, audit_events
from market_audit import audit_market
from runtime_audit import audit_runtime
from scene_plan import PHASES

EDITORIAL_COMMIT = "fe21de75777f04daab59155c43336c7e2719d0ae"
RUNTIME_COMMIT = "67a8cc6740c521675f71c6c733997e429681c3a2"
FPS = 30
DIRECTOR = Path("editorial/2015/director")
RELEASE = Path("editorial/2015/releases/v1.0.1")
SCHEMA = RELEASE / "director_timeline.schema.json"
MARKET = Path("data/cyb_daily.csv")
FROZEN_PATHS = (MARKET, Path("config/production/film_master_v1.json"), Path("config/event_registry.json"))
CANDIDATE_FILES = ("2015_BEAT_SHEET_V1.0.2.json", "EVENT_CLOCK_REGISTER_V1.0.2.json", "V1.0.2_DIRECTOR_CONTRACT.md")
LAYER = re.compile(r"L[1-6]_")
SEGMENTS = {
    "B01": "flash_forward",
    "B02": "main_before_august",
    "B12": "main_through_november",
}
LEGACY_ROLES = {
    "weekend_announcement", "effective_date", "publisher_timestamp", "historical_observation",
    "public_statement", "retrospective_statistic", "macro_context", "documentary_scene",
    "official_website_timestamp",
}
BINDINGS = {
    "E-JUN-02-01": ("weekend_announcement", "中国人民银行"),
    "E-JUN-02-02": ("weekend_announcement", "人民网／巨潮资讯"),
    "E-JUN-02-03": ("weekend_announcement", "公司公告／同期报道"),
    "E-JUN-02-04": ("weekend_announcement", "中国证监会"),
    "E-AUG-01-01": ("macro_context", "中国人民银行"),
    "E-AUG-01-03": ("publisher_timestamp", "财新网 · 网页刊发"),
    "E-AUG-02-05": ("official_website_timestamp", "中国人民银行网站"),
    "E-APR-01-01": ("effective_date", "中国结算／同期报道"),
    "E-APR-01-04": ("publisher_timestamp", "澎湃新闻引中国结算"),
    "E-IND-01-04": ("historical_observation", "两篇同期报道／留存交易资料"),
    "E-JUN-01-01": ("public_statement", "中国证监会"),
    "E-JUN-01-04": ("retrospective_statistic", "中国证券报 · 8月27日事后回顾"),
}


def read(path: Path):
    return json.loads(path.read_bytes())


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def blob(root: Path, commit: str, path: Path) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path.as_posix()}"], cwd=root)


def load_inputs(root: Path, runtime: Path):
    inputs = {name: blob(root, EDITORIAL_COMMIT, DIRECTOR / name) for name in CANDIDATE_FILES}
    handoff = Path("editorial/2015/HANDOFF_TO_CODEX.md")
    expected = {str(DIRECTOR / name): digest(data) for name, data in inputs.items()}
    expected[str(handoff)] = digest(blob(root, EDITORIAL_COMMIT, handoff))
    for path in (*FROZEN_PATHS, *sorted(p.relative_to(root) for p in (root / RELEASE).rglob("*") if p.is_file())):
        reviewed = blob(root, EDITORIAL_COMMIT, path)
        if (root / path).read_bytes() != reviewed or reviewed != blob(root, RUNTIME_COMMIT, path):
            raise ValueError(f"Protected bytes differ between runtime and editorial inputs: {path}")
        expected[str(path)] = digest(reviewed)
    release_names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", EDITORIAL_COMMIT,
                                            str(RELEASE)], cwd=root, text=True).splitlines()
    if set(release_names) != {path for path in expected if path.startswith(f"{RELEASE}/")}:
        raise ValueError("V1.0.1 files differ from the frozen release tree")
    if (runtime / SCHEMA).read_bytes() != blob(root, RUNTIME_COMMIT, SCHEMA):
        raise ValueError("Legacy schema differs from the pinned implementation")
    runtime_sources = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", RUNTIME_COMMIT,
                                               "src/chinext_v6"], cwd=root, text=True).splitlines()
    runtime_commit = runtime / "implementation_commit.txt"
    if runtime_commit.exists() and runtime_commit.read_text().strip() != RUNTIME_COMMIT:
        raise ValueError("Runtime stamp differs from the pinned implementation")
    for name in runtime_sources:
        path = Path(name)
        expected_bytes = blob(root, RUNTIME_COMMIT, path)
        if (runtime / path).read_bytes() != expected_bytes:
            raise ValueError(f"Legacy implementation differs from pinned bytes: {path}")
        expected[f"runtime/{path}"] = digest(expected_bytes)
    return json.loads(inputs[CANDIDATE_FILES[0]]), json.loads(inputs[CANDIDATE_FILES[1]]), expected


def market_keys(days: list[str], frames: int, anchor: str, has_copy: bool,
                motion_fraction: float | None) -> list[dict]:
    # Every trading session has an authored landing frame. The remaining frames
    # are a terminal hold, so weekend, press and closing cues receive real time.
    if len(days) == 1:
        return [{"date": days[0], "frame_offset": 0}, {"date": days[0], "frame_offset": frames - 1}]
    if motion_fraction is None:
        motion_fraction = .84 if not has_copy else (.50 if anchor != days[-1] else .36)
    last_motion = min(frames - 2, max(len(days) - 1, round(frames * motion_fraction)))
    keys = [{"date": day, "frame_offset": round(index * last_motion / (len(days) - 1))}
            for index, day in enumerate(days)]
    return [*keys, {"date": days[-1], "frame_offset": frames - 1}]


def normalized_event(phase: dict, registered: dict, release_events: dict, activation: int,
                     first_day: str, last_day: str):
    event_id = phase.get("event_id")
    if not event_id:
        return None, []
    source_ids = list(EVENT_SOURCES[event_id])
    supplied = registered.get(event_id)
    evidence = release_events.get(event_id)
    if not (supplied or evidence):
        raise ValueError(f"Unknown event provenance: {event_id}")
    base = deepcopy(supplied or {})
    known = (evidence or {}).get("date_roles", {})
    if not isinstance(known, dict):
        known = {}
    role, source_name = BINDINGS.get(event_id, ("historical_observation", "V1.0.1 已审事实"))
    date = phase.get("event_date") or base.get("date") or last_day
    variant = phase.get("event_variant", "")
    if "implementation" in variant:
        role = "effective_date"
        date = "2015-06-28" if event_id == "E-JUN-02-01" else "2015-08-26"
    elif event_id == "E-AUG-01-03":
        role = "publisher_timestamp"
    elif event_id.startswith("E-IMG-"):
        role = "documentary_scene"
        source_name = "中新社发 刘冉阳 摄"
    elif "retrospective" in variant:
        role = "retrospective_statistic"
        date = phase.get("event_date", "2015-06-18")
    elif "report" in variant or "statistic" in variant:
        role = "publisher_timestamp"
    elif variant in LEGACY_ROLES:
        role = variant
    assert role in LEGACY_ROLES
    if date != base.get("date"):
        base.pop("time", None)
    spec = {
        **base, "event_id": event_id, "date": date, "role": role,
        "registered_role": base.get("role") or variant,
        "precision": phase.get("event_precision", "day"), "timezone": "Asia/Shanghai",
        "source_ids": source_ids, "source_short": phase.get("source_short", source_name),
        "activation_frame": activation, "phase_variant": variant or None,
        "persistent_date_label_required": True, "caption_must_not_follow_market_hud": True,
        "market_freeze_after_hit": first_day == last_day,
        "provenance": "V1.0.2 event register" if supplied else "V1.0.1 frozen event review",
    }
    if known:
        spec["frozen_release_date_roles"] = known
    if phase.get("observation_window"):
        spec["observation_window"] = phase["observation_window"]
    if phase.get("event_time"):
        spec["time"] = phase["event_time"]
    if event_id == "E-AUG-01-03":
        spec["presentation_context"] = "retrospective_annotation_alongside_completed_daily_bar"
    if "retrospective" in variant:
        spec.update(precision="month", observation_label="2015年6月",
                    date_is_market_observation_anchor=True)
    return spec, source_ids


def geometry(phase: dict, event: dict | None, index: dict, dates: list[str], rows: dict):
    shape = {"event_ids": [event["event_id"]] if event else [],
             "event_line_has_arrowhead": False, "event_line_meaning": "同期相邻，保留日期语义",
             "close_endpoints": [], "intraday_anchor": None, "gap": None, "statistics_range": None}
    if period := phase.get("interval"):
        first, last = period
        if last != phase["end_date"]:
            raise ValueError(f"Interval endpoint is not the cue outcome: {last}")
        shape["close_endpoints"] = [{"date": date, "field": "close", "value": float(rows[date]["close"])}
                                    for date in (first, last)]
    if gap_day := phase.get("gap"):
        previous = dates[index[gap_day] - 1]
        old_low = Decimal(rows[previous]["low"])
        new_high = Decimal(rows[gap_day]["high"])
        shape["gap"] = {"current_date": gap_day, "previous_date": previous,
                        "previous_low": float(old_low), "current_high": float(new_high),
                        "price_gap": float(old_low - new_high), "full_down_gap": new_high < old_low}
    if bracket := phase.get("statistics_range"):
        shape["statistics_range"] = bracket
    return shape


def camera_for(beat: str, phase: dict) -> dict:
    mode = phase["mode"]
    span = {"M1_MARKET": 64, "M2_KEY_POINT": 50, "M3_EVENT_TAKEOVER": 64,
            "M4_COMPANY": 52, "M5_DOCUMENTARY": 36, "M6_SETTLEMENT": 104}[mode]
    # At the legal one-session hard boundary the price axis and span must match.
    if beat in {"B11", "B12"} or beat == "B13":
        span = 64
    if phase.get("interval") and beat == "B18":
        span = 130
    return {"scale": "wide" if span >= 64 else ("close" if span < 48 else "medium"),
            "visible_trading_days": span, "target_y_domain": [1300, 4550],
            "transition_seconds": 0.7,
            "continuity": "explicit isolated flash-forward cut" if beat == "B01" else "carry prior scale and tween within section",
            "lock_y_scale_while_text_reading": True, "clip_future_candles": True,
            "photograph_layout": bool(phase.get("asset_id")), "domain_group": "candidate_shared_price_axis"}


def compile_cues(beats, registry, release, market):
    dates = list(market)
    index = {date: n for n, date in enumerate(dates)}
    event_records = {item.get("event_id", item.get("metric_id")): item for item in registry["events"]}
    release_events = {item["event_id"]: item for item in read(release / "event_review.json")["events"]}
    photo = {asset["asset_id"]: asset for asset in read(release / "photo_manifest.json")["assets"]}
    base = read(release / "director_timeline.json")
    cue_result, beat_ranges = [], []
    at = 0
    for beat in beats:
        bid = beat["id"]
        phases = PHASES[bid]
        start_beat = at
        assert phases[0]["start_date"] == beat["market_window"][0]
        assert phases[-1]["end_date"] == beat["market_window"][-1]
        assert sum(Decimal(str(phase["seconds"])) for phase in phases) == beat["duration_seconds"]
        first_main_hit = None
        for n, phase in enumerate(phases):
            duration = Decimal(str(phase["seconds"])) * FPS
            assert duration == int(duration) and duration >= 12
            end = at + int(duration)
            day0, day1 = phase["start_date"], phase["end_date"]
            if n:
                assert phase["start_date"] == phases[n - 1]["end_date"]
            anchor = phase.get("anchor", {"date": day1, "field": "close"})
            anchor_day, field = anchor["date"], anchor["field"]
            assert day0 <= anchor_day <= day1 and field in {"low", "high", "close"}
            keys = market_keys(dates[index[day0]:index[day1]+1], int(duration), anchor_day, bool(phase["lines"]),
                               phase.get("motion_fraction"))
            first_key = {day: next(key["frame_offset"] for key in keys if key["date"] == day)
                         for day in {key["date"] for key in keys}}
            hit = at + first_key[anchor_day]
            text_in = hit
            if phase.get("asset_id"):
                text_in = max(hit, at + 18)
            if not phase["lines"]:
                text_in = at
            text_read = min(text_in + 6, end - 1)
            actual = float(market[anchor_day][field])
            focus = phase["focus"]
            assert LAYER.match(focus)
            legacy_ev, source_ids = normalized_event(phase, event_records, release_events, text_in, day0, day1)
            if legacy_ev:
                market_anchor = {"date": anchor_day, "field": field, "value": actual}
                if legacy_ev["phase_variant"] == "rate_cut_implementation":
                    legacy_ev["announcement_market_anchor"] = legacy_ev["market_anchor"]
                    legacy_ev["announcement_date"] = "2015-08-25"
                    legacy_ev["market_anchor"] = market_anchor
                    legacy_ev["effective_policy"] = "benchmark interest-rate cuts"
                legacy_ev["resolved_market_anchor"] = market_anchor
            has_photo = phase.get("asset_id")
            asset_refs = []
            if has_photo:
                info = photo[has_photo]
                asset_refs.append({"asset_id": has_photo, "sha256": info["sha256"], "expected_bytes": info["bytes"],
                                   "dimensions": info["size"], "rights_status": info["rights_status"],
                                   "source_id": info["source_id"], "mode": "contain_keep_watermark"})
            layers = list(phase.get("secondary_layers", (layer for layer in beat["secondary_layers"] if layer != focus)))
            shot_id = f"V102-{bid}-{n+1:02d}"
            cut = "hard_cut_from_flash_forward" if bid == "B02" and n == 0 else (
                "continue_next_real_session" if bid == "B12" and n == 0 else (
                    "isolated_flash_forward" if bid == "B01" and n == 0 else "share_trade_row_and_camera"))
            windows = []
            if text_in > at:
                windows.append({"start_frame": at, "end_frame_exclusive": text_in, "primary_focus": "L1_MARKET",
                                "mode": "M1_MARKET"})
            windows.append({"start_frame": text_in, "end_frame_exclusive": end, "primary_focus": focus, "mode": phase["mode"]})
            linked = geometry(phase, legacy_ev, index, dates, market)
            if field in {"high", "low"}:
                linked["intraday_anchor"] = {"date": anchor_day, "field": field, "value": actual}
            cam = camera_for(bid, phase)
            lines = phase["lines"] or ["创业板指 · 冻结日线"]
            primary_lines = phase.get("primary_lines", [1, 2] if bid == "B09" and len(lines) == 3 else [min(1, len(lines)-1)])
            caption_roles = [{"text": line, "role": "primary" if i in primary_lines else
                              ("date_or_context" if i == 0 else "supporting")} for i, line in enumerate(lines)]
            scene = {
                "shot_id": shot_id, "beat_id": bid, "start_frame": at, "end_frame_exclusive": end,
                "market_clock": {"mode": "monotone_trading_index", "keyframes": keys,
                                 "hud_rule": "last_reached_frozen_daily_close",
                                 "visual_scroll": "interpolate_market_position_only",
                                 "ohlc_reveal": "reveal_frozen_complete_bar_at_session_key_no_intraday_path"},
                "primary_anchor": {"date": anchor_day, "field": field, "value": actual, "hit_frame": hit},
                "event_clock": legacy_ev, "event_refs": [legacy_ev] if legacy_ev else [],
                "text_cue": {"in_frame": text_in, "full_alpha_from_frame": text_read,
                             "out_frame_exclusive": end, "stable_reading_seconds": (end - text_read) / FPS,
                             "lines": lines,
                             "source_line": legacy_ev["source_short"] if legacy_ev else "项目冻结日线"},
                "primary_focus": focus, "secondary_layers": layers, "copy_is_hud_only": not phase["lines"],
                "camera": cam,
                "camera_story_clock": {"clock": "global_integer_frame", "focus_windows": windows,
                                       "easing": "smoothstep", "target": cam,
                                       "reading_window": [text_read, end], "focus_exit_frame": end,
                                       "caption_hierarchy": caption_roles},
                "link_geometry": linked,
                "earth_orbit": {"node_date": legacy_ev["date"] if legacy_ev else anchor_day, "hit_frame": hit,
                                "reflection_pulse_seconds": 0.7, "red_glow": "local_soft_reflection"},
                "rail_mode": base["rail"]["rise" if bid <= "B05" else "drawdown"]["mode"],
                "photo_asset_id": has_photo, "asset_refs": asset_refs, "source_ids": source_ids,
                "requires_renderer_capabilities": ["market_clock_keys", "camera_continuity", "single_reversible_stage_rail",
                                                  *(["independent_event_clock"] if legacy_ev else []),
                                                  *(["historical_photo_scene"] if has_photo else [])],
                "historical_anchor_label": {"date": anchor_day, "value_field": field,
                                            "immutable_during_following_market_motion": True},
                "transition_in": cut, "transition_out": "carry_chart_and_retire_caption",
                "acceptance_checks": ["exact_frozen_ohlc", "one_primary_focus", "no_future_candles",
                                      "one_active_stage_rail", "stable_phone_reading", "review_rendered_occlusion_later"],
            }
            if phase.get("evidence_flag"):
                scene["evidence_flag"] = phase["evidence_flag"]
            main = beat["anchor"]
            if main["date"] in first_key and first_main_hit is None:
                first_main_hit = at + first_key[main["date"]]
            cue_result.append(scene)
            at = end
        beat_ranges.append({"id": bid, "start_frame": start_beat, "end_frame_exclusive": at,
                            "primary_anchor": {**beat["anchor"], "hit_frame": first_main_hit},
                            "secondary_anchors": beat.get("secondary_anchors", []),
                            "market_window": beat["market_window"], "narrative_purpose": beat["narrative_purpose"]})
    cue_result[-1]["transition_out"] = "chapter_handoff_pending_formal_mapping"
    for earlier, later in zip(cue_result, cue_result[1:]):
        if later["transition_in"] in {"hard_cut_from_flash_forward", "continue_next_real_session"}:
            earlier["transition_out"] = later["transition_in"]
    return cue_result, beat_ranges, base


def project_legacy(candidate: dict, schema: dict):
    root_fields = schema["properties"]
    cue_fields = root_fields["cues"]["items"]["properties"]
    by_segment = {}
    for cue in candidate["cues"]:
        if cue["beat_id"] in SEGMENTS:
            segment = SEGMENTS[cue["beat_id"]]
        by_segment.setdefault(segment, []).append(cue)

    exports = []
    for segment, original in by_segment.items():
        offset = original[0]["start_frame"]
        stop = original[-1]["end_frame_exclusive"]
        transport = {name: deepcopy(candidate[name]) for name in root_fields if name != "cues"}
        transport.update(package_version="1.0.1", frame_count=stop - offset)
        transport["source_provenance"].update({"candidate_version": "1.0.2", "transport_version": "1.0.1",
                                               "global_start_frame": offset, "segment_id": segment})
        switch = min(stop - offset, max(0, candidate["rail"]["drawdown"]["start_frame"] - offset))
        transport["rail"]["rise"]["switch_after_frame"] = switch - 1
        transport["rail"]["drawdown"]["start_frame"] = switch
        local_cues = []
        for old in original:
            cue = {name: deepcopy(old[name]) for name in cue_fields}
            cue["start_frame"] -= offset
            cue["end_frame_exclusive"] -= offset
            cue["primary_anchor"]["hit_frame"] -= offset
            cue["earth_orbit"]["hit_frame"] -= offset
            if cue["event_clock"]:
                cue["event_clock"]["activation_frame"] -= offset
            for name in ("in_frame", "full_alpha_from_frame", "out_frame_exclusive"):
                cue["text_cue"][name] -= offset
            local_cues.append(cue)
        transport["cues"] = local_cues
        exports.append({"id": segment, "start_frame": offset, "end_frame_exclusive": stop, "timeline": transport})
    return exports


def bind_price_checkpoints(cues: list[dict], ranges: list[dict], price: dict):
    first_reveal = {}
    for cue in cues:
        for key in cue["market_clock"]["keyframes"]:
            first_reveal.setdefault((cue["beat_id"], key["date"]), cue["start_frame"] + key["frame_offset"])
    by_beat = {item["id"]: item for item in ranges}
    for item in price["price_checks"]:
        beat_id = item["id"].split(maxsplit=1)[0]
        if beat_id in by_beat:
            frame = first_reveal[(beat_id, item["date"])]
            by_beat[beat_id].setdefault("verified_price_checkpoints", []).append({
                "id": item["id"], "date": item["date"], "field": item["field"],
                "value": item["actual"], "hit_frame": frame,
            })
    for beat in ranges:
        for anchor in beat["secondary_anchors"]:
            anchor["hit_frame"] = first_reveal[(beat["id"], anchor["date"])]


def audit_compiled_events(cues: list[dict], source_report: dict) -> dict:
    entries = [(cue, cue["event_clock"]) for cue in cues if cue["event_clock"]]
    by_id = {}
    for cue, event in entries:
        by_id.setdefault(event["event_id"], []).append((cue, event))
    pmi_cue, pmi = by_id["E-AUG-01-03"][0]
    fx_cue, fx = by_id["E-AUG-01-01"][0]
    policy = by_id["E-AUG-02-05"]
    b09 = [(cue, event) for cue, event in entries if cue["beat_id"] == "B09"]
    june = by_id["E-JUN-02-01"]
    checks = {
        "source_ids_and_activation_match": all(
            event["source_ids"] and all(sid in source_report["sources"] for sid in event["source_ids"])
            and event["activation_frame"] == cue["text_cue"]["in_frame"]
            and cue["primary_anchor"]["hit_frame"] <= event["activation_frame"] < cue["end_frame_exclusive"]
            for cue, event in entries
        ),
        "june_weekend_two_dates_one_market_close": [event["date"] for _, event in june] == ["2015-06-27", "2015-06-28"]
            and all(cue["primary_anchor"]["date"] == "2015-06-26" and event["market_freeze_after_hit"] for cue, event in june),
        "july_policy_sequence_stays_on_july3": [event["event_id"] for _, event in b09] ==
            ["E-JUN-02-02", "E-JUN-02-03", "E-JUN-02-04"]
            and all(cue["primary_anchor"]["date"] == "2015-07-03" and event["market_freeze_after_hit"] for cue, event in b09)
            and any("将" in line for line in b09[-1][0]["text_cue"]["lines"]),
        "august_fx_overlay_continues_market_clock": fx["date"] == "2015-08-11"
            and fx_cue["primary_anchor"]["date"] == fx["date"]
            and fx_cue["market_clock"]["keyframes"][-1]["date"] > fx["date"],
        "pmi_page_time_only": pmi["role"] == "publisher_timestamp" and pmi["time"] == "09:43:10"
            and pmi["first_release_time"] is None
            and "财新网页刊发 09:43:10" in pmi_cue["text_cue"]["lines"],
        "august_notice_and_effective_day_remain_distinct": [(item["date"], item.get("time")) for _, item in policy] ==
            [("2015-08-25", "18:15:34"), ("2015-08-26", None)]
            and policy[0][1]["market_freeze_after_hit"]
            and policy[1][1]["market_anchor"] == {"date": "2015-08-26", "field": "close", "value": 1890.04}
            and "8月26日 · 降息实施日" in policy[1][0]["text_cue"]["lines"],
        "optional_t2_layers_are_not_activated": set(by_id).isdisjoint({"E-SEP-ETF-01", "E-SEP-TURNOVER-01"}),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "activations": [{"cue": cue["shot_id"], "event_id": event["event_id"], "date": event["date"],
                             "role": event["role"], "frame": event["activation_frame"],
                             "source_ids": event["source_ids"]} for cue, event in entries]}


def candidate_schema(legacy: dict) -> dict:
    schema = deepcopy(legacy)
    schema["title"] = "ChiNext 2015 V1.0.2 independent director candidate"
    schema["properties"]["package_version"]["const"] = "1.0.2"
    for name, type_name in (("beat_ranges", "array"), ("compatibility", "object")):
        schema["required"].append(name)
        schema["properties"][name] = {"type": type_name}
    cues = schema["properties"]["cues"]["items"]
    for name, type_name in (("beat_id", "string"), ("camera_story_clock", "object"), ("event_refs", "array"),
                            ("primary_focus", "string"), ("secondary_layers", "array"), ("transition_in", "string"),
                            ("transition_out", "string"), ("acceptance_checks", "array"), ("asset_refs", "array"),
                            ("source_ids", "array"), ("copy_is_hud_only", "boolean")):
        cues["required"].append(name)
        cues["properties"][name] = {"type": type_name}
    cues["properties"]["evidence_flag"] = {}
    return schema


def audit_focus(candidate: dict, font_path: Path) -> dict:
    rows = []
    # Provisional phone layout/pacing contract, not a composited visual review.
    # 19 px approximates the existing nominal 54 px text at a 390/1080 scale.
    font = ImageFont.truetype(str(font_path), 19)
    for cue in candidate["cues"]:
        report = {"shot_id": cue["shot_id"], "beat_id": cue["beat_id"], "checks": {}}
        windows = cue["camera_story_clock"]["focus_windows"]
        frames = [frame for window in windows for frame in range(window["start_frame"], window["end_frame_exclusive"])]
        expected = list(range(cue["start_frame"], cue["end_frame_exclusive"]))
        lines = cue["text_cue"]["lines"]
        reading = cue["text_cue"]["stable_reading_seconds"]
        chars = sum(.34 if char.isascii() else 1 for line in lines for char in line if not char.isspace())
        min_seconds = 0.45 + chars / 11
        widths = [round(font.getlength(line), 2) for line in lines]
        secondary = [layer for layer in cue["secondary_layers"] if isinstance(layer, dict)]
        checks = report["checks"]
        checks["exactly_one_primary_each_frame"] = frames == expected and all(LAYER.match(w["primary_focus"]) for w in windows)
        checks["no_more_than_three_policy_layers"] = len(secondary) <= 2
        checks["no_causal_arrow"] = cue["link_geometry"]["event_line_has_arrowhead"] is False
        anchors = cue["link_geometry"]
        known_date = cue["primary_anchor"]["date"]
        checks["geometry_endpoints_already_reached_when_activated"] = all(
            item["date"] <= known_date for item in anchors["close_endpoints"]
        ) and (anchors["gap"] is None or anchors["gap"]["current_date"] <= known_date)
        hierarchy = cue["camera_story_clock"]["caption_hierarchy"]
        checks["one_or_two_main_caption_lines"] = [line["text"] for line in hierarchy] == lines and (
            1 <= sum(line["role"] == "primary" for line in hierarchy) <= 2)
        checks["known_text_window"] = reading > 0 and cue["text_cue"]["out_frame_exclusive"] == cue["end_frame_exclusive"]
        checks["phone_width_with_safe_margins"] = max(widths) <= 316
        checks["modeled_reading_budget"] = cue["copy_is_hud_only"] or reading >= min_seconds
        report.update(phone_text_line_px=widths, measured_at_width_px=390, text_font_px=19,
                      stable_frames=cue["end_frame_exclusive"] - cue["text_cue"]["full_alpha_from_frame"],
                      stable_seconds=round(reading, 3), provisional_minimum_seconds=round(min_seconds, 3),
                      event_id=cue["event_clock"]["event_id"] if cue["event_clock"] else None)
        rows.append(report)
    roster = [row for row in rows if not all(row["checks"].values())]
    return {"passed": not roster, "mode": "freetype_width_and_reading_budget_no_compositing",
            "font_sha256": digest(font_path.read_bytes()), "estimator": "0.45 s + 1 s per 11 weighted visible glyphs",
            "checked_cues": len(rows), "failed_cues": [row["shot_id"] for row in roster], "cues": rows,
            "encoded_mobile_readability": "NOT_RUN", "rendered_occlusion": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--photo", type=Path)
    parser.add_argument("--font", type=Path, default=Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"))
    args = parser.parse_args()
    repo, runtime, out = args.repo_root.resolve(), args.runtime_root.resolve(), args.output.resolve()
    if not out.is_relative_to(repo / "output"):
        parser.error("Choose a candidate output directory under output/")
    out.mkdir(parents=True, exist_ok=True)
    sheet, event_register, inputs = load_inputs(repo, runtime)
    with (repo / MARKET).open(encoding="utf-8-sig", newline="") as input_file:
        market = {row["date"]: row for row in csv.DictReader(input_file)}
    old_schema = read(runtime / SCHEMA)
    beats = sheet["beats"]
    price = audit_market(beats, event_register, repo / MARKET)
    events = audit_events(beats, event_register, repo, args.photo.resolve() if args.photo else None)
    write(out / "market_audit.json", price)
    cues, ranges, legacy_release = compile_cues(beats, event_register, repo / RELEASE, market)
    bind_price_checkpoints(cues, ranges, price)
    assert {(cue["beat_id"], anchor["asset_id"]) for cue in cues for anchor in cue["asset_refs"]} == {
        ("B13", "IMG-20150824-01")}
    events["compiled_event_checks"] = audit_compiled_events(cues, events)
    write(out / "event_asset_audit.json", events)
    rules = {**legacy_release["global_rules"], "isolated_flash_forward": True, "frame_clock_including_flash_forward": True}
    rail = deepcopy(legacy_release["rail"])
    switch = next(item["end_frame_exclusive"] for item in ranges if item["id"] == "B05")
    rail["rise"]["switch_after_frame"], rail["drawdown"]["start_frame"] = switch - 1, switch
    candidate = {"schema_version": "gpt-director-1.0", "package_version": "1.0.2",
                 "fps": FPS, "frame_count": ranges[-1]["end_frame_exclusive"],
                 "source_provenance": {"editorial_commit": EDITORIAL_COMMIT, "implementation_commit": RUNTIME_COMMIT,
                                       "input_sha256": inputs},
                 "timebase": "integer_frames_end_exclusive", "rail": rail, "global_rules": rules,
                 "cues": cues, "beat_ranges": ranges,
                 "compatibility": {"status": "candidate_schema_extension_and_legacy_clock_segments",
                                   "legacy_package_version_transport_only": "1.0.1", "standalone_render_supported": False,
                                   "legacy_projection_excludes": ["primary_focus", "secondary_layers", "camera_story_clock",
                                                                   "asset_refs", "acceptance_checks", "transition_in",
                                                                   "transition_out", "beat_ranges"]}}
    compiled_schema = candidate_schema(old_schema)
    schema_errors = [{"path": list(error.absolute_path), "message": error.message}
                     for error in Draft202012Validator(compiled_schema).iter_errors(candidate)]
    segments = project_legacy(candidate, old_schema)
    write(out / "director_candidate.json", candidate)
    write(out / "candidate.schema.json", compiled_schema)
    projection_dir = out / "legacy"
    projection_dir.mkdir(exist_ok=True)
    for segment in segments:
        write(projection_dir / f"{segment['id']}.json", segment["timeline"])
    write(projection_dir / "segments.json",
          [{name: value for name, value in segment.items() if name != "timeline"} for segment in segments])
    phone = audit_focus(candidate, args.font)
    compatibility = audit_runtime(candidate, segments, repo, runtime)
    write(out / "schema_report.json", {"passed": not schema_errors and compatibility["legacy_schema_passed"],
                                       "candidate_schema_errors": schema_errors, "legacy_schema_passed": compatibility["legacy_schema_passed"],
                                       "legacy_schema_sha256": digest((runtime / SCHEMA).read_bytes())})
    write(out / "clock_report.json", compatibility)
    write(out / "visual_structure_report.json", phone)
    checks = {"schema": not schema_errors and compatibility["legacy_schema_passed"], "market": price["passed"],
              "event_and_asset_reference": events["passed"] and events["compiled_event_checks"]["passed"],
              "clock": compatibility["passed"], "visual_structure": phone["passed"]}
    evidence = {"task": "DIRECTOR-V1.0.2-COMPILE-AND-VALIDATE", "checks": checks, "passed": all(checks.values()),
                "editorial_input_commit": EDITORIAL_COMMIT, "runtime_commit": RUNTIME_COMMIT,
                "frames": candidate["frame_count"], "fps": FPS, "beats": len(ranges), "cues": len(cues),
                "rendered": False, "gpt_editorial_decisions_pending": True,
                "representative_blocks": [
                    {"id": "hook_to_april", "beats": ["B01", "B02"]},
                    {"id": "weekend_policy_to_rebound", "beats": ["B08", "B09", "B10"]},
                    {"id": "september_through_repair", "beats": ["B16", "B17", "B18"]},
                ]}
    for block in evidence["representative_blocks"]:
        block["candidate_frame_windows"] = [{k: r[k] for k in ("id", "start_frame", "end_frame_exclusive")}
                                            for r in ranges if r["id"] in block["beats"]]
        block["media"] = "NOT_RUN_AWAITING_VISUAL_TEST_AUTHORIZATION"
    write(out / "execution_summary.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
