"""Reproducible checks against the resolved editorial preview inputs and output."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .editorial_overlay import _event_label
from .editorial_revision import resolve_director, validate_resolved_director
from .film_renderer import _write_json
from .scene_cache import file_sha256, inspect_media


PHOTO_ID = "IMG-20150824-01"
PHOTO_SHOT = "GPT2015-21"

_CLOCK_CAPABILITIES = {
    "camera_continuity": "Every camera and trading-row join matched the preceding frame.",
    "market_clock_keys": "Every authored key and frame was checked against frozen OHLC.",
    "market_freeze_with_event_clock": "Checked the resolved freeze periods and event clock.",
    "single_reversible_stage_rail": "Verified the single rail mode, value and fill for each frame.",
    "immutable_historical_date_labels": "Historical event clocks and observation labels retained their source semantics.",
    "independent_event_clock": "The event label remains independent of the real market date.",
    "retrospective_statistic_label": "Month-only historical label matched the June observation rule.",
}
_LAYOUT_CAPABILITIES = {
    "coordinated_orbit_hit": "Actual sampled overlay draws the orbit reflection at the authored hit.",
    "company_context_distinct_from_index_value": "Preserved the released company lines and separate index HUD.",
    "floating_event_anchor": "Sampled event labels and connection marks checked against the frozen anchor.",
    "full_down_gap_geometry": "Checked the three true gap boundaries and their sampled geometry.",
    "statistics_range_bracket": "Checked the drawn statistics bracket separately from the publication time.",
    "true_close_endpoint_link": "Checked true endpoints and sampled connection at stable reading.",
    "true_intraday_wick_anchor": "Checked sampled placement of the real daily wick extremum.",
    "historical_photo_scene": "Validated exact documentary photo bytes and checked its sampled drawing branch.",
}


def _close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-8)


def _record(path: Path | None) -> dict | None:
    return None if path is None else {
        "path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size,
    }


def _manifest_failures(root: Path, release: Path) -> list[str]:
    manifest = json.loads((release / "manifest.json").read_bytes())
    failures = [
        item["path"] for item in manifest["artifacts"]
        if not (candidate := release / item["path"]).is_file()
        or file_sha256(candidate) != item["sha256"]
        or candidate.stat().st_size != item["size_bytes"]
    ]
    inputs = {"data/cyb_daily.csv": "market_sha256",
              "config/production/film_master_v1.json": "frozen_master_sha256"}
    return failures + [
        name for name, field in inputs.items()
        if file_sha256(root / name) != manifest[field]
    ]


def _validated_clock(clock, director: dict) -> dict:
    states, projections = clock.states, clock.projections
    failures = []
    by_id = {cue["shot_id"]: cue for cue in director["cues"]}
    anchors, freezes, joins = [], [], []
    if (clock.fps, len(states), len(projections), len(clock.cues)) != (30, 5010, 5010, 28):
        return {"passed": False, "failures": ["Clock must expose 28 cues and 5010 frames at 30 fps."]}
    market = clock.market
    rails = director["rail"]
    switch = rails["drawdown"]["start_frame"]
    prior = None
    for frame, (state, projection) in enumerate(zip(states, projections, strict=True)):
        cue = clock.cue_at(frame)
        rail = rails["rise" if frame < switch else "drawdown"]
        index = state.current_index
        close = market.close[index]
        value = close / rail["base_close"] - 1
        domain = max(map(abs, rail["display_domain_percent"])) / 100
        progress = min(1.0, max(0.0, (value if frame < switch else -value) / domain))
        if (
            frame != state.frame_number or not _close(state.t, frame / 30)
            or cue != by_id.get(state.shot_id)
            or index != math.floor(state.playhead_index + 1e-9)
            or state.current_date != market.dates[index] or not _close(state.current_close, close)
            or prior is not None and state.playhead_index < prior.playhead_index - 1e-8
            or not all(math.isfinite(float(number)) for number in projection.values())
            or projection["window_span"] <= 0 or not 0 < projection["y_min"] < projection["y_max"]
            or not _close(state.y_min, projection["y_min"]) or not _close(state.y_max, projection["y_max"])
        ):
            failures.append(f"Frame {frame}: market playback or projection is inconsistent.")
        if (
            state.stage_mode != rail["mode"] or state.stage_mode != cue["rail_mode"]
            or state.stage_label != rail["label"] or not _close(state.stage_value, value)
            or not _close(state.stage_progress, progress)
        ):
            failures.append(f"Frame {frame}: active rail differs from the real price-based rail.")
        prior = state

    for cue in director["cues"]:
        name = cue["shot_id"]
        start, stop = cue["start_frame"], cue["end_frame_exclusive"]
        anchor = cue["primary_anchor"]
        hit = anchor["hit_frame"]
        index = market.index_for_date(anchor["date"])
        actual = float(getattr(market, anchor["field"])[index])
        state = states[hit]
        hit_ok = state.current_index == index and _close(actual, anchor["value"])
        keys_ok = all(
            _close(states[start + key["frame_offset"]].playhead_index, market.index_for_date(key["date"]))
            for key in cue["market_clock"]["keyframes"]
        )
        if not hit_ok or not keys_ok:
            failures.append(f"{name}: OHLC anchor or authored market key differs.")
        event_clock = cue["event_clock"]
        anchors.append({
            "shot_id": name, "hit_frame": hit, "market_date": anchor["date"],
            "field": anchor["field"], "value": actual, "event_label": _event_label(event_clock),
            "full_alpha_frame": cue["text_cue"]["full_alpha_from_frame"], "passed": hit_ok and keys_ok,
        })
        if start:
            same_projection = all(_close(value, projections[start - 1][key])
                                  for key, value in projections[start].items())
            same_market_row = states[start - 1].current_index == states[start].current_index
            if not same_projection or not same_market_row:
                failures.append(f"{name}: projection or market row jumps at frame {start}.")
            joins.append({"frame": start, "previous_shot": states[start - 1].shot_id,
                          "next_shot": name, "projection_matches": same_projection,
                          "market_row_matches": same_market_row})
        if cue["camera"]["lock_y_scale_while_text_reading"]:
            first_frame = cue["text_cue"]["in_frame"]
            first = projections[first_frame]
            if any(not (_close(p["y_min"], first["y_min"]) and _close(p["y_max"], first["y_max"]))
                   for p in projections[first_frame:cue["text_cue"]["out_frame_exclusive"]]):
                failures.append(f"{name}: vertical scale moves during the reading window.")
        if event_clock and event_clock.get("market_freeze_after_hit"):
            frozen = all(_close(item.playhead_index, index) and item.current_index == index
                         for item in states[hit:stop])
            freezes.append({"shot_id": name, "from_frame": hit, "end_frame_exclusive": stop,
                            "market_date": anchor["date"], "close": float(state.current_close),
                            "event_clock": event_clock, "passed": frozen})
            if not frozen:
                failures.append(f"{name}: market moves during an authored event freeze.")

    month = by_id["GPT2015-08"]["event_clock"]
    if _event_label(month) != "2015年6月" or month["date"] != "2015-06-18":
        failures.append("The June retrospective caption must be month-only; June 18 is its OHLC observation anchor.")
    by_market_date = {item.current_date.date().isoformat(): item for item in states}
    early, rebound = by_market_date.get("2015-07-07"), by_market_date.get("2015-07-23")
    if early is None or rebound is None or not (early.stage_value < rebound.stage_value < 0
                                                 and early.stage_progress > rebound.stage_progress):
        failures.append("The July rebound did not push the real drawdown rail back.")
    return {
        "passed": not failures, "failures": failures, "frames": len(states), "fps": clock.fps,
        "anchors": anchors, "joined_frames": joins, "joins_checked": len(joins),
        "freeze_intervals": freezes, "rail_switch_frames": [switch],
        "july7": {"value": early.stage_value, "progress": early.stage_progress} if early else None,
        "july23": {"value": rebound.stage_value, "progress": rebound.stage_progress} if rebound else None,
        "final_close": states[-1].current_close, "final_drawdown": states[-1].stage_value,
        "camera_adjustments": clock.camera_adjustments,
    }


def _layout_result(layout: dict | None, clock, photo: dict | None) -> dict:
    if layout is None:
        return {"status": "NOT_EXECUTED", "failures": [], "photo_rendered": False}
    failures = []
    rendered_photo_frames = []
    full_read_frames = {cue["text_cue"]["full_alpha_from_frame"] for cue in clock.cues}
    frames = layout.get("frames", [])
    if not layout.get("passed") or not full_read_frames.issubset({row["frame"] for row in frames}):
        failures.append("Missing or failed target layout samples at the full-reading frames.")
    for row in frames:
        n = row["frame"]
        if not 0 <= n < clock.total_frames:
            failures.append(f"Layout frame {n} lies outside the timeline.")
            continue
        cue, state = clock.cue_at(n), clock.states[n]
        if (
            row["shot_id"] != cue["shot_id"] or row["active_track_count"] != 1
            or row["market_date"] != state.current_date.date().isoformat()
            or not _close(row["market_close"], state.current_close)
            or row["out_of_bounds"] or row["text_overlaps"]
        ):
            failures.append(f"Frame {n}: layout, rail, or rendered market HUD is inconsistent.")
        overlay = row["overlay"]
        text = cue["text_cue"]
        if cue["photo_asset_id"] and photo is None:
            if not overlay.get("missing_photo") or overlay.get("photo_visible") or overlay.get("text_visible"):
                failures.append(f"Frame {n}: missing photo must hold the chart and omit the photo caption.")
            continue
        if overlay.get("photo_visible"):
            if not cue["photo_asset_id"] or photo is None:
                failures.append(f"Frame {n}: documentary photo visible without the validated source.")
            rendered_photo_frames.append(n)
        if n != text["full_alpha_from_frame"]:
            continue
        if not _close(overlay.get("caption_alpha", 0), 1) or not overlay.get("text_visible"):
            failures.append(f"Frame {n}: text does not reach full alpha at its stable-reading start.")
        if overlay.get("event_label") != _event_label(cue["event_clock"]):
            failures.append(f"Frame {n}: rendered event label differs from its fixed historical clock.")
        if cue["photo_asset_id"] and not overlay.get("photo_visible"):
            failures.append(f"Frame {n}: validated documentary photo was not drawn.")
        geometry, link = overlay.get("geometry", {}), cue["link_geometry"]
        for field, diagnostic in (("close_endpoints", "close_endpoints_visible"),
                                  ("intraday_anchor", "wick_visible")):
            if link[field] and not geometry.get(diagnostic):
                failures.append(f"Frame {n}: {field} is not fully in view at stable reading.")
        for field, diagnostic in (("gap", "gap"), ("statistics_range", "statistics_bracket")):
            if link[field] and not (geometry.get(diagnostic) or {}).get("visible"):
                failures.append(f"Frame {n}: {field} did not appear in the rendered overlay.")
        orbit = overlay.get("orbit") or {}
        expected_orbit = cue["earth_orbit"]
        if orbit.get("visible") and (
            orbit.get("node_date") != expected_orbit["node_date"] or orbit.get("hit_frame") != expected_orbit["hit_frame"]
        ):
            failures.append(f"Frame {n}: rendered orbit is bound to the wrong hit.")
    return {"status": "PASSED" if not failures else "FAILED", "frames_sampled": len(frames),
            "failures": failures, "photo_rendered": bool(rendered_photo_frames),
            "photo_frames": rendered_photo_frames}


def validate_run(root: Path, release: Path, revision: Path, resolved_path: Path, out: Path,
                 clock, photo_path: Path | None, video_path: Path | None, *,
                 layout: dict | None = None) -> dict:
    """Write current-run checks. Use only layout samples captured by this invocation."""
    resolved = json.loads(resolved_path.read_bytes())
    photo = _record(photo_path)
    video = _record(video_path)
    input_hashes = {
        "content_manifest": _record(release / "manifest.json"),
        "released_director_timeline": _record(release / "director_timeline.json"),
        "resolved_director_timeline": _record(resolved_path),
        "visual_revision": _record(revision),
        "frozen_market": _record(root / "data/cyb_daily.csv"),
        "formal_master": _record(root / "config/production/film_master_v1.json"),
        "actual_photo": photo, "actual_media": video,
        "relevant_renderer_code": [
            _record(path) for path in sorted((root / "src/chinext_v6").glob("*.py"))
        ] + [_record(root / "tools/render_editorial_preview.py")],
    }
    config = {"failed_checks": _manifest_failures(root, release)}
    try:
        config["immutable_field_validation"] = validate_resolved_director(release, resolved)
        if resolve_director(root, release, revision, photo is not None) != resolved:
            config["failed_checks"].append("Parsed timeline differs from the validated resolution of base and revision.")
        if tuple(resolved["cues"]) != clock.cues:
            config["failed_checks"].append("The inspected renderer clock did not use the parsed cues.")
        if photo:
            manifest = json.loads((release / "photo_manifest.json").read_bytes())
            exact = next(asset for asset in manifest["assets"] if asset["asset_id"] == PHOTO_ID)
            if (photo["sha256"], photo["bytes"]) != (exact["sha256"], exact["bytes"]):
                config["failed_checks"].append("The selected photo does not match the exact documentary input.")
    except (KeyError, ValueError) as error:
        config["failed_checks"].append(str(error))
    config["passed"] = not config["failed_checks"]
    config["input_hashes"] = input_hashes
    _write_json(out / "resolved_config_validation.json", config)

    checks = (_validated_clock(clock, resolved) if config["passed"]
              else {"passed": False, "failures": ["Resolved input check failed."]})
    checks["input_hashes"] = input_hashes
    _write_json(out / "clock_validation.json", checks)
    layout_checks = _layout_result(layout, clock, photo) if config["passed"] else {
        "status": "NOT_EXECUTED", "failures": [], "photo_rendered": False,
    }
    media = (inspect_media(video_path, width=clock.video["width"], height=clock.video["height"],
                           fps=clock.fps, expected_frames=clock.total_frames, full_decode=True)
             if video else None)
    if media and _record(video_path) != video:
        media["passed"] = False
        media["error"] = "Output changed during verification."
    capabilities = dict(_CLOCK_CAPABILITIES) if checks["passed"] else {}
    if layout_checks["status"] == "PASSED":
        capabilities.update(_LAYOUT_CAPABILITIES)
    if not layout_checks["photo_rendered"]:
        capabilities.pop("historical_photo_scene", None)
    required = {name for cue in clock.cues for name in cue["requires_renderer_capabilities"]}
    missing = dict.fromkeys(sorted(required - capabilities.keys()), "Current invocation has no passing verification for this capability.")
    if PHOTO_ID and photo is None:
        missing["historical_photo_scene"] = {
            "asset_id": PHOTO_ID, "shot_id": PHOTO_SHOT, "frame_span": [3630, 3780],
            "reason": "The exact documentary photo is not available in this runtime.",
        }
    failures = config["failed_checks"] + checks["failures"] + layout_checks["failures"]
    if media and not media["passed"]:
        failures.append("Media failed current-run stream, frame, duration or full-decode verification.")
    unexpected_missing = (required - capabilities.keys()) - ({"historical_photo_scene"} if photo is None else set())
    if layout is not None and unexpected_missing:
        failures.append(f"Required renderer capabilities not verified: {', '.join(sorted(unexpected_missing))}")
    report = {
        "passed": not failures,
        "complete_photo_preview_verified": not failures and layout_checks["photo_rendered"] and bool(media and media["passed"]),
        "failures": failures, "capabilities": sorted(capabilities), "implemented_or_reused": capabilities,
        "missing": missing, "input_hashes": input_hashes, "layout": layout_checks, "media": media,
        "user_aesthetic_acceptance": "PENDING",
    }
    _write_json(out / "renderer_capabilities.json", report)
    if failures:
        raise RuntimeError("Editorial verification failed. See the current validation reports.")
    return report
