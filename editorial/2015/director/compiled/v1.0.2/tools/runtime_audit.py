"""Audit strict DirectorTimeline projections with the published EditorialClock.

The legacy timelines are validation projections of a richer candidate. The
clock is evaluated without calling the compositor or generating any media.
"""

from __future__ import annotations

from collections import Counter
from hashlib import file_digest
import json
import math
from pathlib import Path
import subprocess
import sys

RELEASE_PATH = Path("editorial/2015/releases/v1.0.1")
SEGMENT_IDS = ("flash_forward", "main_before_august", "main_through_november")
SEGMENT_FRAMES = ((0, 240), (240, 3840), (3840, 7200))


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def _same(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0, abs_tol=1e-8)


def _schema_errors(validator, payload: dict) -> list[dict]:
    return [
        {"field": str(error.json_path), "message": error.message}
        for error in validator.iter_errors(payload)
    ]


def audit_runtime(canonical: dict, segments: list[dict], repo_root: Path, runtime_root: Path) -> dict:
    """Check the exact published schema, then execute the pinned clock in isolation."""
    from jsonschema import Draft202012Validator

    repo_root, runtime_root = repo_root.resolve(), runtime_root.resolve()
    schema_path = runtime_root / RELEASE_PATH / "director_timeline.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    canonical_errors = _schema_errors(validator, canonical)
    legacy_errors = {segment["id"]: _schema_errors(validator, segment["timeline"]) for segment in segments}
    payload = {"canonical": canonical, "segments": segments, "repo_root": str(repo_root),
               "runtime_root": str(runtime_root), "invalid_segments": [name for name, errors in legacy_errors.items() if errors]}
    attempt = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).resolve()), "--worker"],
        input=json.dumps(payload), text=True, capture_output=True, cwd=repo_root, timeout=90,
    )
    if attempt.returncode:
        actual = {"passed": False, "actual_runtime_executed": False,
                  "errors": [f"Pinned EditorialClock process failed: {attempt.stderr.strip()}"]}
    else:
        actual = json.loads(attempt.stdout)
    return {
        "passed": actual["passed"] and not any(legacy_errors.values()),
        "scope": "legacy_schema_and_actual_clock_only",
        "published_schema": {"data": str(schema_path.relative_to(runtime_root)),
                             "draft": "2020-12", "sha256": _sha(schema_path)},
        "canonical_direct_legacy_schema_accepted": not canonical_errors,
        "canonical_direct_schema_errors": canonical_errors,
        "legacy_schema_passed": not any(legacy_errors.values()),
        "legacy_projection_schema_errors": legacy_errors,
        "runtime": actual,
        "renderer_executed": False,
        "renderer_output_validated": False,
    }


def _offset_cue(legacy: dict, start: int) -> dict:
    items = {key: legacy[key] for key in ("shot_id", "market_clock", "rail_mode", "photo_asset_id")}
    for field in ("start_frame", "end_frame_exclusive"):
        items[field] = legacy[field] + start
    items["primary_anchor"] = {**legacy["primary_anchor"], "hit_frame": legacy["primary_anchor"]["hit_frame"] + start}
    items["text_cue"] = {**legacy["text_cue"]}
    for field in ("in_frame", "out_frame_exclusive", "full_alpha_from_frame"):
        items["text_cue"][field] += start
    if legacy["event_clock"] is not None:
        items["event_fields"] = {key: legacy["event_clock"][key] for key in (
            "date", "time", "implementation_date", "implementation_dates",
            "observation_range", "market_freeze_after_hit", "first_release_time",
        ) if key in legacy["event_clock"]}
    return items


def _check_segment(segment: dict, clock, canonical: dict, errors: list[str]) -> dict:
    name, start, end = (segment[key] for key in ("id", "start_frame", "end_frame_exclusive"))
    if clock.total_frames != end - start or clock.fps != 30:
        errors.append(f"{name}: actual frame count or fps differs from the segment contract")

    anchors = 0
    freeze_cues = []
    for cue in clock.cues:
        shot = cue["shot_id"]
        approved = canonical.get(shot)
        rebased = _offset_cue(cue, start)
        expected = {key: approved.get(key) for key in rebased if key != "event_fields"} if approved else None
        if expected is not None and "event_fields" in rebased:
            expected["event_fields"] = {key: (approved.get("event_clock") or {}).get(key)
                                        for key in rebased["event_fields"]}
        if rebased != expected:
            errors.append(f"{name}/{shot}: immutable cue fields differ after rebasing global frames")
        anchor = cue["primary_anchor"]
        hit = clock.states[anchor["hit_frame"]]
        hit_date = hit.current_date.date().isoformat()
        actual = float(getattr(clock.market, anchor["field"])[hit.current_index])
        if hit_date != anchor["date"] or not _same(actual, anchor["value"]):
            errors.append(f"{name}/{shot}: actual primary hit disagrees with its exact OHLC")
        else:
            anchors += 1
        spec = cue["camera"]
        if not spec["clip_future_candles"]:
            errors.append(f"{name}/{shot}: no-future-candles flag was lost")
        text = cue["text_cue"]
        full = text["full_alpha_from_frame"]
        text_end = text["out_frame_exclusive"]
        if not cue["start_frame"] <= text["in_frame"] <= full < text_end <= cue["end_frame_exclusive"]:
            errors.append(f"{name}/{shot}: reading window falls outside the cue")
        elif spec["lock_y_scale_while_text_reading"]:
            reading = clock.projections[full:text_end]
            for field in ("y_min", "y_max"):
                if any(not _same(item[field], reading[0][field]) for item in reading):
                    errors.append(f"{name}/{shot}: {field} changes within stable reading")
        event = cue.get("event_clock") or {}
        if event.get("market_freeze_after_hit"):
            frozen = clock.states[anchor["hit_frame"]:cue["end_frame_exclusive"]]
            if any(state.current_index != hit.current_index or not _same(state.current_close, hit.current_close)
                   for state in frozen):
                errors.append(f"{name}/{shot}: event freeze advanced the real market")
            freeze_cues.append({"shot_id": shot, "event_date": event["date"], "time": event.get("time"),
                                "market_date": hit_date, "close": float(hit.current_close),
                                "start_frame": start + anchor["hit_frame"],
                                "end_frame_exclusive": start + cue["end_frame_exclusive"]})

    last_index = -1
    mismatched = []
    for frame, state in enumerate(clock.states):
        index = state.current_index
        if (state.frame_number != frame or not _same(state.t, frame / 30)
                or clock.cue_at(frame)["shot_id"] != state.shot_id
                or index < last_index or index != math.floor(state.playhead_index + 1e-9)
                or state.current_date != clock.market.dates[index]
                or not _same(state.current_close, clock.market.close[index])):
            mismatched.append(frame + start)
        last_index = index
    if mismatched:
        errors.append(f"{name}: invalid market row, order or clock at global frames {mismatched[:12]}")
    return {"id": name, "start_frame": start, "end_frame_exclusive": end,
            "actual_frames": len(clock.states), "primary_hits_checked": anchors,
            "observed_rail_modes": dict(Counter(state.stage_mode for state in clock.states)),
            "first_market_date": clock.states[0].current_date.date().isoformat(),
            "last_market_date": clock.states[-1].current_date.date().isoformat(),
            "freeze_cues": freeze_cues, "projection_adjustments": clock.camera_adjustments}


def _joins(clocks: list, errors: list[str]) -> list[dict]:
    hook, main, continuation = clocks
    hook_out = hook.states[-1].current_date.date().isoformat()
    main_in = main.states[0].current_date.date().isoformat()
    main_out = main.states[-1]
    next_in = continuation.states[0]
    market_dates = (main_out.current_date.date().isoformat(), next_in.current_date.date().isoformat())
    old, new = main.projections[-1], continuation.projections[0]
    span_and_domain_equal = all(_same(old[key], new[key]) for key in ("window_span", "y_min", "y_max"))
    origin_advance = new["window_start"] - old["window_start"]
    hook_pass = (hook_out, main_in) == ("2015-06-03", "2015-04-01") and all(
        state.current_date == hook.states[-1].current_date and _same(state.current_close, 3982.25)
        for state in hook.states
    )
    if not hook_pass:
        errors.append("B01→B02 does not preserve the isolated fixed 6/3 hook and explicit 4/1 restart")
    adjoining = (market_dates == ("2015-07-27", "2015-07-28")
                 and next_in.current_index == main_out.current_index + 1)
    continuation_pass = adjoining and span_and_domain_equal and _same(origin_advance, 1)
    if not continuation_pass:
        errors.append("B11→B12 does not continue to the next real trading row under the same camera scale/domain")
    return [
        {"frame": 240, "kind": "explicit_isolated_flash_forward_cut", "out_date": hook_out, "in_date": main_in,
         "passed": hook_pass},
        {"frame": 3840, "kind": "next_trading_row_at_compatible_camera", "out_date": market_dates[0],
         "in_date": market_dates[1], "consecutive_csv_rows": adjoining,
         "camera_span_and_domain_equal": span_and_domain_equal, "window_start_change_in_trading_rows": origin_advance,
         "out_projection": old, "in_projection": new, "passed": continuation_pass},
    ]


def _audit_director_states(clocks: list, canonical: dict, beat_ranges: list[dict],
                           records: list[dict], errors: list[str]) -> dict:
    hook, main, continuation = clocks
    states = (*main.states, *continuation.states)
    dates = list(dict.fromkeys(state.current_index for state in states))
    start = main.market.index_for_date("2015-04-01")
    end = main.market.index_for_date("2015-11-25")
    expected_dates = list(range(start, end + 1))
    if dates != expected_dates:
        unseen = sorted(set(expected_dates) - set(dates))
        errors.append("Actual main sequence omitted or reordered trading rows: " +
                      ", ".join(main.market.dates[i].date().isoformat() for i in unseen))
    beat_dates = {}
    beat_sequence = {}
    for state in states:
        beat = canonical[state.shot_id]["beat_id"]
        day = state.current_date.date().isoformat()
        beat_dates.setdefault(beat, set()).add(day)
        ordered = beat_sequence.setdefault(beat, [])
        if not ordered or ordered[-1] != day:
            ordered.append(day)
    if beat_dates.get("B09") != {"2015-07-03"}:
        errors.append("B09 must hold only the real 7/3 close throughout the weekend event sequence")
    for beat, required_start, required_end in (
        ("B08", "2015-06-19", "2015-07-03"),
        ("B10", "2015-07-03", "2015-07-23"),
        ("B11", "2015-07-23", "2015-07-27"),
        ("B12", "2015-07-28", "2015-08-20"),
        ("B16", "2015-08-26", "2015-09-15"),
        ("B17", "2015-09-15", "2015-09-29"),
        ("B18", "2015-09-29", "2015-11-25"),
    ):
        observed = beat_sequence.get(beat, [])
        left = main.market.index_for_date(required_start)
        right = main.market.index_for_date(required_end)
        expected = [day.date().isoformat() for day in main.market.dates[left:right+1]]
        if observed != expected:
            errors.append(f"{beat}: actual stage did not play every trading row {required_start}→{required_end}")
    freezes = [hold for record in records for hold in record["freeze_cues"]]
    june_hold = {hold["event_date"] for hold in freezes if hold["market_date"] == "2015-06-26"
                 and _same(hold["close"], 2920.70)} == {"2015-06-27", "2015-06-28"}
    august_hold = any(hold["event_date"] == "2015-08-25" and hold["time"] == "18:15:34"
                      and hold["market_date"] == "2015-08-25" and _same(hold["close"], 1990.71)
                      for hold in freezes)
    if not june_hold or not august_hold:
        errors.append("Missing actual freeze for the June announcement/effectiveness or August after-close notice")
    all_states = (*hook.states, *states)
    checked_anchors = 0
    for beat in beat_ranges:
        for checkpoint in beat.get("verified_price_checkpoints", []):
            resolved = all_states[checkpoint["hit_frame"]]
            actual = float(getattr(main.market, checkpoint["field"])[resolved.current_index])
            if (resolved.current_date.date().isoformat() == checkpoint["date"]
                    and _same(actual, float(checkpoint["value"]))
                    and canonical[resolved.shot_id]["beat_id"] == beat["id"]):
                checked_anchors += 1
            else:
                errors.append(f'{checkpoint["id"]}: expected date/field not reached on the compiled hit frame')
    return {"frame_count": len(hook.states) + len(states), "main_unique_trading_days": len(dates),
            "expected_main_trading_days": len(expected_dates), "june_weekend_hold": june_hold,
            "compiled_price_checkpoint_hits": checked_anchors,
            "august_after_close_hold": august_hold,
            "july_weekend_held_entire_beat": beat_dates.get("B09") == {"2015-07-03"},
            "checked_beat_market_sequences": {name: beat_sequence.get(name, [])
                                               for name in ("B08", "B09", "B10", "B11", "B12", "B16", "B17", "B18")}}


def _worker(payload: dict) -> dict:
    repo_root, runtime_root = (Path(payload[key]) for key in ("repo_root", "runtime_root"))
    sys.path.insert(0, str(runtime_root / "src"))
    from chinext_v6 import editorial_clock

    actual_module = Path(editorial_clock.__file__).resolve()
    expected_module = runtime_root / "src/chinext_v6/editorial_clock.py"
    if actual_module != expected_module:
        raise RuntimeError(f"Clock import did not come from the pinned runtime: {actual_module}")
    approved = {cue["shot_id"]: cue for cue in payload["canonical"]["cues"]}
    segments = payload["segments"]
    errors = []
    if payload["canonical"]["frame_count"] != 7200 or payload["canonical"]["fps"] != 30:
        errors.append("Canonical V1.0.2 timing must use 7200 frames at 30 fps")
    if [segment["id"] for segment in segments] != list(SEGMENT_IDS) or [
        (segment["start_frame"], segment["end_frame_exclusive"]) for segment in segments
    ] != list(SEGMENT_FRAMES):
        errors.append("Legacy validation segments do not partition the approved 7200-frame plan")
    legacy_ids = [cue["shot_id"] for segment in segments for cue in segment["timeline"].get("cues", [])]
    matching_cues = legacy_ids == [cue["shot_id"] for cue in payload["canonical"]["cues"]]
    if not matching_cues:
        errors.append("Legacy cue list omits, duplicates or reorders canonical cues")
    clocks = []
    records = []
    for segment in segments:
        if segment["id"] in payload["invalid_segments"]:
            errors.append(f"{segment['id']}: did not execute because strict schema validation failed")
            continue
        try:
            clock = editorial_clock.EditorialClock(
                repo_root, runtime_root / RELEASE_PATH, 1080, director=segment["timeline"], photo_available=True,
            )
            records.append(_check_segment(segment, clock, approved, errors))
            clocks.append(clock)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append(f"{segment['id']}: {type(error).__name__}: {error}")
    joins, frame_checks = [], {}
    if len(clocks) == 3 and matching_cues and [segment["id"] for segment in segments] == list(SEGMENT_IDS):
        joins = _joins(clocks, errors)
        frame_checks = _audit_director_states(clocks, approved, payload["canonical"]["beat_ranges"], records, errors)
    return {
        "passed": not errors, "actual_runtime_executed": bool(clocks),
        "module": str(actual_module.relative_to(runtime_root)), "module_sha256": _sha(actual_module),
        "segment_runs": records, "joins": joins, "frame_checks": frame_checks, "errors": errors,
        "photo_clock_option": "photo_available_true_for_timing_only; image not read",
        "future_ohlc_evidence": "per-frame current row is exact floor of real playhead; chart clip flag checked; compositor not evaluated",
    }


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("Import audit_runtime from the V1.0.2 compiler")
    print(json.dumps(_worker(json.load(sys.stdin)), ensure_ascii=False))
