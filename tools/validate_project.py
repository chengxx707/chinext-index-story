#!/usr/bin/env python3
"""Validate source facts, actual frame states, layout and an optional silent MP4.

Exit 0 means all *executed required checks* passed, not that an artistic review
has passed. The JSON explicitly lists manual and unexecuted review scopes.
"""
from __future__ import annotations

import argparse
import bisect
import csv
from datetime import date, datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
ALLOWED_GRADES = {"A", "DATA"}


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.scope: dict[str, Any] = {}

    def add(self, name: str, passed: bool, evidence: Any, *, severity: str = "error") -> None:
        self.checks.append({"id": name, "passed": bool(passed), "severity": severity, "evidence": evidence})

    def as_dict(self) -> dict[str, Any]:
        errors = [c for c in self.checks if not c["passed"] and c["severity"] == "error"]
        return {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "passed": not errors,
            "scope": self.scope,
            "summary": {"checks": len(self.checks), "passed": sum(c["passed"] for c in self.checks),
                        "failed": len(errors), "warnings": sum(not c["passed"] and c["severity"] == "warning" for c in self.checks)},
            "checks": self.checks,
            "problems": errors,
            "manual_review": {
                "status": "pending",
                "items": ["手机尺寸阅读速度", "与批准母版的美术质量比较", "实际播放的镜头节奏与极值命中感"],
                "note": "自动检查通过不代表已达到海报质量或已获样片审阅通过。当前阶段为无声画面。",
            },
        }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def production_provenance(root: Path = ROOT) -> dict[str, Any]:
    sources = sorted((root / "src").rglob("*.py")) + [root / "render_v6.py", root / "tools/render_ending.py"]
    digest = hashlib.sha256()
    for path in sorted(p for p in sources if p.is_file()):
        digest.update(f"{path.relative_to(root).as_posix()}:{sha256(path)}\n".encode())
    assets = {path.relative_to(root).as_posix(): sha256(path)
              for path in sorted((root / "assets").rglob("*.png"))}
    return {"source_tree_sha256": digest.hexdigest(), "asset_hashes": assets}


def validate_market_rows(rows: list[dict[str, Any]], report: Report) -> None:
    """Validate the original file order; a loader's sort must not hide bad input."""
    problems: list[dict[str, Any]] = []
    dates: list[date] = []
    for number, row in enumerate(rows, start=2):
        try:
            day = date.fromisoformat(str(row["date"]))
            values = {k: float(row[k]) for k in ("open", "high", "low", "close")}
            if not all(math.isfinite(v) and v > 0 for v in values.values()):
                raise ValueError("OHLC must be finite and positive")
            if not (values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]):
                raise ValueError("OHLC order must satisfy low <= open/close <= high")
            if "pct_chg" in row and not math.isfinite(float(row["pct_chg"])):
                raise ValueError("pct_chg must be finite")
            dates.append(day)
        except (KeyError, TypeError, ValueError) as exc:
            problems.append({"line": number, "error": str(exc)})
    report.add("market.nonempty", bool(rows), {"rows": len(rows)})
    report.add("market.ohlc", not problems, {"invalid_rows": len(problems), "examples": problems[:20]})
    ordered = all(a < b for a, b in zip(dates, dates[1:]))
    report.add("market.unique_chronological_dates", ordered,
               {"rows": len(dates), "duplicates": len(dates) - len(set(dates)),
                "first": str(dates[0]) if dates else None, "last": str(dates[-1]) if dates else None})


def day_string(value: Any) -> str:
    return str(value)[:10]


def first_state_at_or_after(states: list[Any], t: float) -> Any:
    times = [float(s.t) for s in states]
    return states[min(bisect.bisect_left(times, float(t) - 1e-8), len(states) - 1)]


def validate_event_sources(raw_events: list[dict[str, Any]], registry: dict[str, Any], report: Report,
                           *, repository_root: Path = ROOT) -> None:
    """A copied grade flag is insufficient: resolve the actual source record."""
    records = {item["id"]: item for item in registry.get("events", [])}
    issues = []
    checked = []
    for event in raw_events:
        if not event.get("enabled", False) or event.get("release_grade") != "A":
            continue
        source_id = event.get("source_id")
        source = records.get(source_id)
        checked.append(source_id)
        if not source or source.get("release_grade") != "A" or not source.get("enabled", False):
            issues.append({"event": event["id"], "error": "No enabled A-grade source record", "source_id": source_id})
            continue
        evidence = source.get("evidence", {})
        document = evidence.get("document")
        if not document or not (repository_root / document).is_file() or not evidence.get("section"):
            issues.append({"event": event["id"], "error": "Source document/section is not recoverable"})
        if event.get("date_precision", "day") != source.get("date_precision", "day"):
            issues.append({"event": event["id"], "error": "Date precision differs from source record"})
        if source.get("anchor_date") and day_string(event.get("anchor_date", event["date"])) != source["anchor_date"]:
            issues.append({"event": event["id"], "error": "Trading-day anchor differs from source record"})
        source_metric = source.get("metric", {})
        if "metric_value" in event and "value" in source_metric:
            if not math.isclose(float(event["metric_value"]), float(source_metric["value"]), abs_tol=1e-7):
                issues.append({"event": event["id"], "error": "Screen metric differs from source record"})
    report.add("events.enabled_sources_resolve", not issues,
               {"source_ids_checked": checked, "problems": issues,
                "verification_basis": "Recoverable user-supplied research; not a new online verification"})


def validate_model(model: Any, raw_events: list[dict[str, Any]], report: Report) -> None:
    states = list(model.states)
    expected_count = int(round(float(model.duration) * int(model.fps)))
    report.add("timeline.frame_count", len(states) == expected_count and bool(states),
               {"actual": len(states), "expected": expected_count})
    if not states:
        return
    market = model.market
    config = model.config
    start = config["sample"]["start_date"]
    end = config["sample"]["end_date"]
    report.add("timeline.first_frame", day_string(states[0].current_date) == start,
               {"actual": day_string(states[0].current_date), "expected": start})
    report.add("timeline.last_frame_reaches_end", day_string(states[-1].current_date) == end,
               {"actual": day_string(states[-1].current_date), "expected": end,
                "last_frame_number": states[-1].frame_number, "last_logical_time": float(states[-1].t)})
    state_errors = []
    previous_index = -1
    for state in states:
        idx = int(state.current_index)
        if not 0 <= idx < len(market.close):
            state_errors.append({"frame": state.frame_number, "error": "index out of data range"})
            continue
        if idx < previous_index:
            state_errors.append({"frame": state.frame_number, "error": "date moved backwards"})
        previous_index = idx
        if (day_string(state.current_date) != day_string(market.dates[idx])
                or not math.isclose(float(state.current_close), float(market.close[idx]), abs_tol=1e-7)):
            state_errors.append({"frame": state.frame_number, "error": "HUD date/close is not the same real row",
                                 "date": day_string(state.current_date), "close": float(state.current_close),
                                 "expected_close": float(market.close[idx])})
        if not math.isfinite(float(state.y_min)) or not math.isfinite(float(state.y_max)) or state.y_max <= state.y_min:
            state_errors.append({"frame": state.frame_number, "error": "invalid camera y range"})
    report.add("timeline.real_close_and_date", not state_errors,
               {"frames_checked": len(states), "errors": len(state_errors), "examples": state_errors[:12]})

    loaded_events = {event.id: event for event in model.events}
    leaked = []
    invalid_enabled = []
    for raw in raw_events:
        grade = str(raw.get("release_grade", "A")).upper()
        enabled = raw.get("enabled", True)
        forbidden = not enabled or grade not in ALLOWED_GRADES
        if forbidden and raw["id"] in loaded_events:
            leaked.append(raw["id"])
        if enabled and grade not in ALLOWED_GRADES:
            invalid_enabled.append(raw["id"])
    report.add("events.disabled_and_unverified_do_not_leak", not leaked, {"leaked_event_ids": leaked})
    report.add("events.unverified_not_enabled_in_config", not invalid_enabled, {"invalid_enabled_event_ids": invalid_enabled})
    synchrony = []
    for event in model.events:
        try:
            logical_idx = math.floor(float(model.playhead_index(float(event.hit_t))) + 1e-7)
            frame_state = first_state_at_or_after(states, float(event.hit_t))
            anchor_date = getattr(event, "anchor_date", None)
            anchor_date = event.date if anchor_date is None else anchor_date
            strict_idx = market.index_for_date(anchor_date)
            valid = (day_string(market.dates[strict_idx]) == day_string(anchor_date)
                     and logical_idx == int(event.index) == int(frame_state.current_index)
                     and frame_state.window_start <= event.index <= frame_state.window_end
                     and 0 <= float(event.hit_t) <= model.duration)
            synchrony.append({"id": event.id, "passed": valid, "event_date": day_string(event.date),
                              "logical_index": logical_idx, "event_index": int(event.index),
                              "hit_frame_date": day_string(frame_state.current_date)})
        except (KeyError, IndexError, ValueError) as exc:
            synchrony.append({"id": event.id, "passed": False, "error": str(exc)})
    report.add("events.hit_date_matches_candle_and_frame", all(c["passed"] for c in synchrony), synchrony)

    critical = []
    for point in model.critical_points:
        try:
            idx = market.index_for_date(point.date)
            state = first_state_at_or_after(states, point.hit_t)
            passed = (math.isclose(float(point.price), float(market.close[idx]), abs_tol=0.005)
                      and int(state.current_index) == idx
                      and state.window_start <= idx <= state.window_end
                      and state.y_min <= float(point.price) <= state.y_max
                      and float(point.hold_until) >= float(point.hit_t))
            critical.append({"id": point.id, "passed": passed, "date": day_string(point.date),
                             "price": float(point.price), "actual_close": float(market.close[idx]),
                             "hit_frame_date": day_string(state.current_date)})
        except (KeyError, IndexError, ValueError) as exc:
            critical.append({"id": point.id, "passed": False, "error": str(exc)})
    report.add("critical.price_date_and_visibility", bool(critical) and all(c["passed"] for c in critical), critical)

    locked_shots = []
    for shot in config.get("camera_shots", []):
        if shot.get("y_policy") not in {"lookahead_locked", "critical_anchor"}:
            continue
        settle = float(shot.get("transition_seconds", 0.7))
        held = [s for s in states if s.shot_id == shot["id"] and s.t >= float(shot["start_t"]) + settle]
        y_variation = max((float(s.y_min) for s in held), default=0) - min((float(s.y_min) for s in held), default=0)
        y_variation += max((float(s.y_max) for s in held), default=0) - min((float(s.y_max) for s in held), default=0)
        locked_shots.append({"id": shot["id"], "stable_frames": len(held), "total_y_variation": y_variation,
                             "passed": len(held) > 1 and y_variation <= 1e-7})
    report.add("camera.reading_range_stable_after_entry", bool(locked_shots) and all(s["passed"] for s in locked_shots), locked_shots)

    stage_problems = []
    modes = config.get("stage_rail", {}).get("modes", [])
    mode_map = {mode["id"]: mode for mode in modes}
    for state in states:
        if not isinstance(getattr(state, "stage_mode", None), str) or not state.stage_mode:
            stage_problems.append({"frame": state.frame_number, "error": "missing singular stage mode"})
            continue
        if not math.isfinite(float(state.stage_value)) or not 0 <= float(state.stage_progress) <= 1:
            stage_problems.append({"frame": state.frame_number, "error": "invalid stage value/progress"})
        mode = mode_map.get(state.stage_mode)
        if mode and "anchor_price" in mode:
            expected = float(state.current_close) / float(mode["anchor_price"]) - 1
            if not math.isclose(float(state.stage_value), expected, abs_tol=1e-7):
                stage_problems.append({"frame": state.frame_number, "error": "stage value is not derived from close/anchor"})
    report.add("stage.singular_and_derived_state", not stage_problems,
               {"frames_checked": len(states), "modes_seen": sorted({getattr(s, "stage_mode", "") for s in states}),
                "problems": stage_problems[:12]})
    reversals = []
    inconsistent = []
    for a, b in zip(states, states[1:]):
        if a.stage_mode != b.stage_mode or a.current_index == b.current_index:
            continue
        rising = "rise" in a.stage_mode
        falling = "drawdown" in a.stage_mode
        if rising and b.current_close < a.current_close:
            reversals.append(int(b.frame_number))
            if b.stage_progress > a.stage_progress + 1e-7:
                inconsistent.append(int(b.frame_number))
        if falling and b.current_close > a.current_close:
            reversals.append(int(b.frame_number))
            if b.stage_progress > a.stage_progress + 1e-7:
                inconsistent.append(int(b.frame_number))
    report.add("stage.actual_retracements_reverse_progress", bool(reversals) and not inconsistent,
               {"reversal_frames": len(reversals), "wrong_direction_frames": inconsistent[:12]})


def validate_boxes(diagnostics: dict[str, Any], width: int, height: int) -> list[dict[str, Any]]:
    problems = []
    boxes = diagnostics.get("text_boxes", [])
    if not boxes:
        problems.append({"error": "drawing returned no measured text boxes"})
    for item in boxes:
        bbox = item.get("bbox", [])
        if len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox):
            problems.append({"id": item.get("id"), "error": "invalid measured bbox"})
            continue
        left, top, right, bottom = bbox
        if left < -0.5 or top < -0.5 or right > width + 0.5 or bottom > height + 0.5:
            problems.append({"id": item.get("id"), "error": "text outside frame", "bbox": bbox})
        if right <= left or bottom <= top:
            problems.append({"id": item.get("id"), "error": "empty text bounds", "bbox": bbox})
    for i, a in enumerate(boxes):
        if a.get("overlaps_allowed", False) or len(a.get("bbox", [])) != 4:
            continue
        for b in boxes[i + 1:]:
            if b.get("overlaps_allowed", False) or len(b.get("bbox", [])) != 4:
                continue
            al, at, ar, ab = a["bbox"]
            bl, bt, br, bb = b["bbox"]
            if min(ar, br) - max(al, bl) > 1 and min(ab, bb) - max(at, bt) > 1:
                problems.append({"ids": [a.get("id"), b.get("id")], "error": "measured text boxes overlap"})
    for point in diagnostics.get("critical_points", []):
        if not point.get("visible", False):
            problems.append({"id": point.get("id"), "error": "critical anchor outside camera"})
    return problems


def validate_layout(model: Any, asset_dir: Path, report: Report) -> None:
    from chinext_v6.drawing import SceneDrawer
    drawer = SceneDrawer(model, asset_dir)
    times = {0.0, float(model.duration), float(model.duration) / 2}
    for event in model.events:
        times.update([max(0., event.hit_t), min(model.duration, event.hit_t + min(0.6, event.post_seconds / 2))])
    for point in model.critical_points:
        times.update([point.hit_t, point.hold_until])
    details = []
    rail_count = []
    for t in sorted(times):
        state = first_state_at_or_after(list(model.states), t)
        diagnostic = drawer.get_layout_diagnostics(state)
        issues = validate_boxes(diagnostic, int(model.video["width"]), int(model.video["height"]))
        details.append({"t": float(state.t), "frame": int(state.frame_number),
                        "measured_text_count": len(diagnostic.get("text_boxes", [])), "problems": issues})
        rail_count.append({"t": float(state.t), "count": diagnostic.get("active_track_count")})
    report.add("layout.measured_text_and_critical_bounds", not any(d["problems"] for d in details), details)
    report.add("layout.only_one_drawn_active_track", all(item["count"] == 1 for item in rail_count), rail_count)


def validate_video_metadata(probe: dict[str, Any], expected: dict[str, Any], report: Report) -> None:
    streams = probe.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    report.add("media.one_video_no_audio", len(videos) == 1 and not audio,
               {"video_streams": len(videos), "audio_streams": len(audio)})
    if len(videos) != 1:
        return
    video = videos[0]
    fps = float(Fraction(video.get("avg_frame_rate", "0/1")))
    duration = float(probe.get("format", {}).get("duration", 0))
    expected_frames = round(float(expected["duration_seconds"]) * int(expected["fps"]))
    count = int(video.get("nb_frames", video.get("nb_read_frames", 0)))
    report.add("media.dimensions_and_fps", video.get("width") == expected["width"]
               and video.get("height") == expected["height"] and abs(fps - expected["fps"]) < 1e-6,
               {"width": video.get("width"), "height": video.get("height"), "fps": fps, "expected": expected})
    report.add("media.frame_count_and_duration", count == expected_frames
               and abs(duration - float(expected["duration_seconds"])) <= 1 / int(expected["fps"]) + 0.001,
               {"frames": count, "expected_frames": expected_frames, "duration": duration,
                "expected_duration": float(expected["duration_seconds"])})


def validate_media(video_path: Path, expected: dict[str, Any], inputs: dict[str, Path], report: Report,
                   *, preview: bool = False) -> None:
    report.scope["video"] = {"path": str(video_path.resolve()), "size_bytes": video_path.stat().st_size,
                             "sha256": sha256(video_path)}
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)],
                           capture_output=True, text=True, check=False)
    report.add("media.ffprobe", probe.returncode == 0, {"returncode": probe.returncode, "stderr": probe.stderr[-1500:]})
    if probe.returncode:
        return
    manifest_path = video_path.parent / "render_manifest.json"
    if preview:
        if not manifest_path.exists():
            report.add("media.preview_dimensions_declared", False, "Preview requires a render manifest with explicit width and height")
            return
        manifest = load_json(manifest_path)
        expected = dict(expected, width=int(manifest["width"]), height=int(manifest["height"]))
    validate_video_metadata(json.loads(probe.stdout), expected, report)
    decode = subprocess.run(["ffmpeg", "-hide_banner", "-v", "info", "-xerror", "-i", str(video_path),
                             "-an", "-vf", "scale=160:284,blackdetect=d=0.10:pic_th=0.997:pix_th=0.025",
                             "-f", "null", "-"], capture_output=True, text=True, check=False)
    report.add("media.full_decode", decode.returncode == 0, {"returncode": decode.returncode,
               "stderr_tail": decode.stderr[-1000:] if decode.returncode else "Decoded complete video with -xerror"})
    black = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", decode.stderr)
    report.add("media.no_unintended_black_segment", not black,
               {"threshold": "99.7% of pixels below 2.5% luminance for >=0.10s", "segments": black})
    if not manifest_path.exists():
        report.add("media.render_manifest_provenance", False,
                   "No render_manifest.json; source provenance is unconfirmed and the production media gate is blocked")
    else:
        manifest = load_json(manifest_path)
        # Permit direct hash map or the renderer's {inputs: {name: {sha256}}}.
        saved = manifest.get("input_hashes", manifest.get("inputs", {}))
        observed = {name: sha256(path) for name, path in inputs.items()}
        declared = {name: (saved.get(name, {}).get("sha256") if isinstance(saved.get(name), dict)
                           else saved.get(name, manifest.get(f"{name}_sha256")))
                    for name in inputs}
        report.add("media.render_manifest_provenance", observed == declared,
                   {"manifest": str(manifest_path), "observed": observed, "declared": declared,
                    "run_id": manifest.get("run_id")})
        current_production = production_provenance()
        recorded_production = {key: manifest.get(key) for key in current_production}
        report.add("media.production_sources_and_assets_match", current_production == recorded_production,
                   {"observed_source_tree_sha256": current_production["source_tree_sha256"],
                    "recorded_source_tree_sha256": recorded_production["source_tree_sha256"],
                    "assets_match": current_production["asset_hashes"] == recorded_production["asset_hashes"]})


def validate(config_path: Path, events_path: Path, csv_path: Path, *, layout: bool = False,
             asset_dir: Path | None = None, video_path: Path | None = None, preview: bool = False) -> dict[str, Any]:
    report = Report()
    inputs = {"config": config_path, "events": events_path, "csv": csv_path}
    report.scope = {"inputs": {}, "layout": "requested" if layout else "not_run",
                    "media": "requested" if video_path else "not_run", "media_target": "preview" if preview else "production"}
    for key, path in inputs.items():
        exists = path.is_file()
        report.add(f"input.{key}.exists", exists, str(path.resolve()))
        if exists:
            report.scope["inputs"][key] = {"path": str(path.resolve()), "sha256": sha256(path)}
    if any(not c["passed"] for c in report.checks):
        return report.as_dict()
    try:
        config = load_json(config_path)
        raw_events = load_json(events_path)
        if isinstance(raw_events, dict):
            raw_events = raw_events["events"]
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        validate_market_rows(rows, report)
        registry_path = config_path.parent / "event_registry.json"
        if registry_path.is_file():
            report.scope["event_registry"] = {"path": str(registry_path.resolve()), "sha256": sha256(registry_path)}
            validate_event_sources(raw_events, load_json(registry_path), report)
        else:
            report.add("events.registry_available", False, "No event_registry.json alongside config: enabled event source provenance is unconfirmed", severity="warning")
    except Exception as exc:
        report.add("inputs.parse", False, {"type": type(exc).__name__, "message": str(exc)})
        return report.as_dict()
    try:
        from chinext_v6.model import SceneModel
        model = SceneModel(config_path, events_path, csv_path)
        report.add("model.constructs", True, {"class": type(model).__name__})
        validate_model(model, raw_events, report)
    except Exception as exc:
        report.add("model.constructs_or_validates", False, {"type": type(exc).__name__, "message": str(exc)})
        return report.as_dict()
    if layout:
        try:
            validate_layout(model, asset_dir or ROOT / "assets", report)
        except Exception as exc:
            report.add("layout.executed", False, {"type": type(exc).__name__, "message": str(exc)})
    if video_path:
        try:
            validate_media(video_path, config["video"], inputs, report, preview=preview)
        except Exception as exc:
            report.add("media.executed", False, {"type": type(exc).__name__, "message": str(exc)})
    return report.as_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/v6_sample.json")
    parser.add_argument("--events", type=Path, default=ROOT / "config/events_v6.json")
    parser.add_argument("--csv", type=Path, default=ROOT / "data/cyb_daily.csv")
    parser.add_argument("--assets", type=Path, default=ROOT / "assets")
    parser.add_argument("--output", type=Path, default=ROOT / "output/v6_review/validation.json")
    parser.add_argument("--layout", action="store_true")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--preview", action="store_true", help="Check declared preview dimensions from render manifest; does not validate production dimensions")
    args = parser.parse_args()
    result = validate(args.config, args.events, args.csv, layout=args.layout,
                      asset_dir=args.assets, video_path=args.video, preview=args.preview)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "summary": result["summary"],
                      "manual_review": "pending", "report": str(args.output)}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
