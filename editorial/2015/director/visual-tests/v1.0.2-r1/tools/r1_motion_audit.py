"""Audit the delivered V1.0.2 baseline and actual representative R1 diagnostics."""

from __future__ import annotations

import argparse
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile


COMMIT = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
GIT_PATH = "editorial/2015/director/visual-tests/v1.0.2"
ARCHIVE = "director-v1.0.2-representative-visual-review.zip"
FPS = 30
BASE_RANGES = {"B01-B02": [0, 540], "B08-B10": [2280, 3600], "B16-B18": [5520, 7200]}
R1_RANGES = {**BASE_RANGES, "B16-B18": [5520, 7320]}
B17_READ_EXTENSIONS = {"01": 12, "02": 12, "03": 24, "ETF": 18, "04": 24, "TURNOVER": 12, "05": 18}
B17_CLOSES = {
    "01": ("2015-09-16", "1926.25", "+7.16%"), "02": ("2015-09-21", "2079.06", "+4.83%"),
    "03": ("2015-09-25", "2020.97", "−4.06%"), "04": ("2015-09-28", "2122.26", "+5.01%"),
    "05": ("2015-09-29", "2098.57", "−1.12%"),
}
T2 = {
    "ETF": ("03", "E-SEP-ETF-01", ("易方达创业板ETF份额", "9/7—9/22", "2015.09.25", "12.37亿份", "18.07亿份", "+46.08%", "据中国证券报援引深交所数据")),
    "TURNOVER": ("04", "E-SEP-TURNOVER-01", ("2015.09.28", "收盘后", "沪深两市成交额", "4,044", "亿元", "中国新闻网、21世纪经济报道")),
}


def _sha(contents: bytes) -> str:
    return sha256(contents).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _git(repo: Path, subpath: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{COMMIT}:{GIT_PATH}/{subpath}"])


def _section(checks: dict, **evidence) -> dict:
    return {"passed": all(checks.values()), "checks": checks, **evidence}


def _identical(data: bytes, expected: dict) -> bool:
    return len(data) == expected["bytes"] and _sha(data) == expected["sha256"]


def _baseline(repo: Path, local: Path) -> tuple[dict, dict]:
    manifest_bytes = _git(repo, "manifest.json")
    manifest = json.loads(manifest_bytes)
    archive_bytes = _git(repo, ARCHIVE)
    checks, errors, counts = {}, [], {}
    listed = manifest["artifacts"]
    tracked_paths = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", f"{COMMIT}:{GIT_PATH}"], text=True,
    ).splitlines()
    for name in sorted(set(tracked_paths) & listed.keys()):
        counts["git_blobs"] = counts.get("git_blobs", 0) + 1
        if not _identical(_git(repo, name), listed[name]):
            errors.append({"source": "git_blob", "path": name})
    with ZipFile(BytesIO(archive_bytes)) as archive:
        checks["zip_contains_exact_commit_manifest_and_listed_artifacts"] = (
            len(archive.namelist()) == len(listed) + 1
            and set(archive.namelist()) == set(listed) | {"manifest.json"}
            and archive.read("manifest.json") == manifest_bytes
        )
        for name, expected in listed.items():
            counts["zip_entries"] = counts.get("zip_entries", 0) + 1
            if not _identical(archive.read(name), expected):
                errors.append({"source": "git_zip", "path": name})
            path = local / name
            if path.is_file():
                counts["local_entries"] = counts.get("local_entries", 0) + 1
                if not _identical(path.read_bytes(), expected):
                    errors.append({"source": "local_baseline", "path": name})
    checks["all_available_artifacts_match_committed_manifest"] = not errors
    candidate_bytes = _git(repo, "candidate.json")
    checks["candidate_matches_published_digest"] = _sha(candidate_bytes) == manifest["candidate_sha256"]
    duration_reports = {name: json.loads(_git(repo, f"{name}/manifest.json")) for name in BASE_RANGES}
    checks["published_clip_frame_ranges_and_duration"] = all(
        report["frame_span"] == BASE_RANGES[name] and report["fps"] == FPS
        and report["target_frames"] == BASE_RANGES[name][1] - BASE_RANGES[name][0]
        and report["duration_seconds"] == report["target_frames"] / FPS
        for name, report in duration_reports.items()
    )
    intake = json.loads(_git(repo, "intake.json"))
    frozen = {}
    for name, expected in intake["input_sha256"].items():
        if not name.startswith(("data/", "config/", "assets/", "editorial/2015/releases/v1.0.1/")):
            continue
        path = repo / name
        actual = _sha(path.read_bytes()) if path.is_file() else None
        frozen[name] = {"sha256": expected, "matches": actual == expected}
    checks["locked_source_data_master_assets_and_v101_match"] = bool(frozen) and all(item["matches"] for item in frozen.values())
    result = _section(checks, commit=COMMIT, archive_sha256=_sha(archive_bytes), counts=counts,
                      artifact_mismatches=errors, frozen_sha256=frozen, frame_ranges=BASE_RANGES)
    return result, json.loads(candidate_bytes)


def _by_shot(candidate: dict) -> dict:
    return {cue["shot_id"]: cue for cue in candidate["cues"]}


def _window_length(cue: dict) -> int:
    start, stop = cue["camera_story_clock"]["reading_window"]
    return stop - start


def _untimed_event(event):
    return {key: value for key, value in event.items() if key != "activation_frame"} if event else None


def _candidate(base: dict, current: dict) -> dict:
    previous, latest = _by_shot(base), _by_shot(current)
    b01 = latest["V102-B01-01"]
    story = b01["camera_story_clock"]
    unchanged = [cue for cue in previous.values() if cue["beat_id"] not in {"B01", "B17", "B18"}
                 and cue["shot_id"] != "V102-B13-02"]
    b13_before, b13_after = previous["V102-B13-02"], latest["V102-B13-02"]
    checks = {
        "same_48_cues_in_same_order": len(previous) == 48 and list(previous) == list(latest),
        "scoped_timeline_is_244_seconds": current["fps"] == FPS and current["frame_count"] == 7320,
        "unchanged_cues_are_byte_equivalent_as_values": all(cue == latest[cue["shot_id"]] for cue in unchanged),
        "rail_basis_unchanged": current["rail"] == base["rail"],
        "b13_only_changes_context_label": b13_after == {
            **b13_before, "camera_story_clock": {**b13_before["camera_story_clock"], "context_label": "2015.08.21 · 当日回顾"},
        },
        "hook_preserves_real_market_clock_and_original_boundaries": (
            (b01["start_frame"], b01["end_frame_exclusive"]) == (0, 240)
            and b01["market_clock"] == previous["V102-B01-01"]["market_clock"]
            and b01["primary_anchor"] == previous["V102-B01-01"]["primary_anchor"]
            and b01["text_cue"]["lines"] == previous["V102-B01-01"]["text_cue"]["lines"]
        ),
        "hook_camera_and_captions_timed_separately": story["intro_camera"] == {
            "start_frame": 0, "settled_frame": 48, "initial_visible_trading_days": 72,
            "initial_y_domain": [1000, 4800], "easing": "smoothstep",
        } and story["intro_reveal"] == {
            "date_in_frame": 0, "date_full_frame": 6,
            "value_in_frame": 48, "value_full_frame": 54, "source_in_frame": 48,
        },
    }
    authored = {}
    shift = 0
    for old in previous.values():
        if old["beat_id"] not in {"B17", "B18"}:
            continue
        shot = old["shot_id"]
        new = latest[shot]
        extension = B17_READ_EXTENSIONS.get(shot.removeprefix("V102-B17-"), 0)
        old_keys = old["market_clock"]["keyframes"]
        new_keys = new["market_clock"]["keyframes"]
        old_story = old["camera_story_clock"]
        new_story = new["camera_story_clock"]
        anchor = old["primary_anchor"]
        key = {
            "shift_matches_accumulated_prior_holds": new["start_frame"] == old["start_frame"] + shift,
            "only_terminal_hold_added": (new["end_frame_exclusive"] == old["end_frame_exclusive"] + shift + extension
                and new_keys[:-1] == old_keys[:-1]
                and new_keys[-1] == {**old_keys[-1], "frame_offset": old_keys[-1]["frame_offset"] + extension}),
            "facts_links_and_copies_unchanged": (
                new["primary_anchor"] == {**anchor, "hit_frame": anchor["hit_frame"] + shift}
                and _untimed_event(new["event_clock"]) == _untimed_event(old["event_clock"])
                and [_untimed_event(event) for event in new["event_refs"]] == [_untimed_event(event) for event in old["event_refs"]]
                and new["text_cue"]["lines"] == old["text_cue"]["lines"]
                and new["text_cue"]["source_line"] == old["text_cue"]["source_line"]
                and new["link_geometry"] == old["link_geometry"]
            ),
            "full_reading_gets_exact_added_frames": _window_length(new) == _window_length(old) + extension,
            "fade_duration_preserved": (
                "exit_window" not in old_story and "exit_window" not in new_story
                or new_story.get("exit_window") == [frame + shift + extension for frame in old_story["exit_window"]]
            ),
        }
        authored[shot] = _section(key, reading_frames_added=extension, start_shift_frames=shift)
        if old["beat_id"] == "B17":
            shift += extension
    checks["all_tail_cue_preservation_checks"] = all(result["passed"] for result in authored.values())
    checks["total_b17_extension_120_frames"] = shift == 120
    return _section(checks, cue_comparisons=authored)


def _rows(result: Path, block: str) -> list[dict]:
    folder = result / block
    records = _read(folder / "diagnostics.json")["frames"]
    start, stop = R1_RANGES[block]
    if [row["frame"] for row in records] != list(range(start, stop)):
        raise ValueError(f"{block}: diagnostics do not cover [{start},{stop}) exactly")
    media = _read(folder / "media_validation.json")
    if media["global_frame_interval"] != [start, stop] or media["sha256"] != _sha((folder / "target.mp4").read_bytes()):
        raise ValueError(f"{block}: diagnostics and encoded target have different range or lineage")
    return records


def _caption(row: dict) -> str:
    return "".join(row["overlay"]["caption_lines"])


def _main_alpha(row: dict, roles: set[str]) -> float:
    return max((entry["alpha"] for entry in row["overlay"]["text_roles"] if entry["role"] in roles), default=0)


def _sample_projection(row: dict) -> dict:
    return {key: row["projection"][key] for key in ("window_start", "window_span", "y_min", "y_max")}


def _b01(result: Path) -> dict:
    rows = _rows(result, "B01-B02")
    hook, settle = rows[:240], 48
    projection = [_sample_projection(row) for row in hook]
    initial, settled = projection[0], projection[settle]
    checks = {
        "holds_real_june3_without_future_candles_or_duplicated_rail": all(
            row["market_date"] == "2015-06-03" and Decimal(str(row["market_close"])) == Decimal("3982.25")
            and row["no_future_candles"] and row["last_eligible_candle_index"] <= row["market_index"]
            and row["active_track_count"] == 1 and row["stage_mode"] == hook[0]["stage_mode"] for row in hook
        ),
        "one_eased_push_to_same_final_projection": (
            (initial["window_span"], initial["y_min"], initial["y_max"]) == (72, 1000, 4800)
            and (settled["window_span"], settled["y_min"], settled["y_max"]) == (50, 1300, 4550)
            and all(a["window_span"] > b["window_span"] for a, b in zip(projection[:settle], projection[1:settle + 1]))
            and all(current == settled for current in projection[settle:])
        ),
        "projection_uses_smoothstep_for_each_component": all(
            abs(value - (initial[key] + (settled[key] - initial[key]) * t * t * (3 - 2 * t))) < 1e-6
            for frame, current in enumerate(projection[:settle + 1]) for t in [frame / settle]
            for key, value in current.items()
        ),
        "opening_price_is_deferred_in_hud_and_caption": all(
            row["hud"]["close_visible"] is False and row["hud"]["close_text"] is None
            and not any(box["id"] in {"current_close", "current_close_label"} for box in row["text_boxes"])
            for row in hook
        ) and all("3,982.25" not in _caption(row) for row in hook[:settle]),
        "actual_value_enters_after_push_and_holds_at_full_opacity": (
            all("3,982.25" in _caption(row) for row in hook[settle:])
            and 0 < _main_alpha(hook[48], {"market_key_point"}) < 1
            and all(_main_alpha(row, {"market_key_point"}) == 1 for row in hook[54:])
        ),
        "same_explicit_f240_return_and_real_restarted_tape": (
            rows[240]["market_date"] == "2015-04-01" and Decimal(str(rows[240]["market_close"])) == Decimal("2404.91")
            and rows[240]["hud"]["close_visible"] is True and rows[-1]["market_date"] == "2015-04-10"
            and max(abs(rows[240]["projection"][key] - settled[key]) for key in settled) > 1
        ),
        "early_chart_and_late_keypoint_have_distinct_focus_phases": (
            all(row["visual_mode"] == "M1_MARKET" for row in hook[:48])
            and all(row["visual_mode"] == "M2_KEY_POINT" for row in hook[48:])
        ),
        "timed_qualifier_source_anchor_and_single_orbit_pulse": (
            all(row["overlay"]["intro_reveal"]["qualifier_visible"] and "阶段最高收盘" in _caption(row) for row in hook)
            and all(not row["overlay"]["intro_reveal"]["source_visible"] and not row["overlay"]["geometry"]
                    and row["overlay"]["orbit"] is None for row in hook[:48])
            and all(row["overlay"]["intro_reveal"]["source_visible"] and row["overlay"]["geometry"]["anchor_visible"]
                    and "项目冻结日线" in _caption(row) for row in hook[48:])
            and [row["frame"] for row in hook if (row["overlay"]["orbit"] or {}).get("pulse")] == list(range(48, 69))
        ),
        "no_frame_layout_errors": all(not row["layout_errors"] for row in rows),
    }
    steps = [a["window_span"] - b["window_span"] for a, b in zip(projection[:settle], projection[1:settle + 1])]
    evidence = {frame: {"projection": projection[frame], "drawn_caption": hook[frame]["overlay"]["caption_lines"],
                        "hero_alpha": _main_alpha(hook[frame], {"market_key_point"}),
                        "camera": hook[frame].get("hook_camera"),
                        "intro_overlay": hook[frame]["overlay"].get("intro_reveal"),
                        "orbit": hook[frame]["overlay"].get("orbit")}
                for frame in (0, 6, 24, 47, 48, 54, 239)}
    return _section(checks, samples=evidence, push_steps={"first": steps[0], "max": max(steps), "last": steps[-1]},
                    stable_value_reading_frames=240 - 54)


def _b17(result: Path, base: dict, current: dict) -> dict:
    rows = _rows(result, "B16-B18")
    by_frame = {row["frame"]: row for row in rows}
    previous, latest = _by_shot(base), _by_shot(current)
    checks, readings = {}, {}
    for suffix, added in B17_READ_EXTENSIONS.items():
        key = f"V102-B17-{suffix}"
        cue = latest[key]
        first, end = cue["camera_story_clock"]["reading_window"]
        out, stop = cue["camera_story_clock"]["exit_window"]
        visible = [by_frame[frame] for frame in range(first, end)]
        fade = [by_frame[frame]["overlay"]["caption_alpha"] for frame in range(out, stop)]
        t2 = T2.get(suffix)
        if t2:
            prior, metric, terms = t2
            day, close, _ = B17_CLOSES[prior]
            before = by_frame[cue["start_frame"] - 1]
            checks[suffix + "_only_after_completed_real_close"] = (
                before["market_date"] == day and Decimal(str(before["market_close"])) == Decimal(close)
                and all(by_frame[frame]["market_date"] == day and Decimal(str(by_frame[frame]["market_close"])) == Decimal(close)
                        for frame in range(cue["start_frame"], cue["end_frame_exclusive"]))
                and all((row["overlay"]["market_structure"] or {}).get("metric_id") != metric or
                        cue["start_frame"] <= row["frame"] < cue["end_frame_exclusive"] for row in rows)
            )
            checks[suffix + "_actual_t2_provenance_and_no_causal_geometry"] = all(
                (row["overlay"]["market_structure"] or {}).get("metric_id") == metric
                and row["overlay"]["market_structure"].get("evidence_tier") == "T2"
                and row["primary_focus"] == "L3_MARKET_STRUCTURE" and not row["overlay"]["geometry"]
                and not any(word in _caption(row) for word in ("净申购", "净流入", "资金流入", "导致", "推高"))
                for row in visible
            )
        else:
            day, close, move = B17_CLOSES[suffix]
            terms = move, f"{Decimal(close):,.2f}"
        checks[suffix + "_stable_visible_actual_reading"] = (
            len(visible) == _window_length(previous[key]) + added and first < end == out
            and all(row["market_date"] == day and Decimal(str(row["market_close"])) == Decimal(close)
                    and row["overlay"]["text_visible"] and row["overlay"]["caption_alpha"] >= .999
                    and all(term in _caption(row) for term in terms) for row in visible)
        )
        checks[suffix + "_full_six_frame_exit_fade"] = (
            len(fade) == 6 and fade[0] == 1 and fade[-1] == 0 and all(a > b for a, b in zip(fade, fade[1:]))
            and not by_frame[stop - 1]["overlay"]["text_visible"]
        )
        readings[suffix] = {"from_frame": first, "end_frame_exclusive": end, "stable_seconds": round(len(visible) / FPS, 3),
                            "prior_stable_seconds": round(_window_length(previous[key]) / FPS, 3), "fade": fade}
    checks["etf_and_turnover_never_share_a_frame"] = not any(
        "易方达创业板ETF份额" in _caption(row) and "沪深两市成交额" in _caption(row) for row in rows
    )
    checks["etf_then_sep28_rebound_then_turnover_then_sep29_pullback"] = list(readings) == ["01", "02", "03", "ETF", "04", "TURNOVER", "05"] and all(
        first["end_frame_exclusive"] < following["from_frame"] for first, following in zip(
            list(readings.values()), list(readings.values())[1:])
    )
    days = list(dict.fromkeys(row["market_date"] for row in rows if row["beat_id"] == "B17"))
    checks["all_actual_b17_trading_days_present_in_order"] = days == [
        "2015-09-15", "2015-09-16", "2015-09-17", "2015-09-18", "2015-09-21", "2015-09-22",
        "2015-09-23", "2015-09-24", "2015-09-25", "2015-09-28", "2015-09-29",
    ]
    checks["only_one_rail_no_future_or_layout_errors"] = all(
        row["active_track_count"] == 1 and row["no_future_candles"] and not row["layout_errors"] for row in rows
    )
    return _section(checks, readings=readings, b17_trading_days=days)


def _b08_and_b13(result: Path, repo: Path) -> dict:
    b08 = "B08-B10"
    files = ("target.mp4", "phone-390.mp4", "diagnostics.json")
    expected = json.loads(_git(repo, f"{b08}/manifest.json"))["artifacts"]
    reused = {name: _identical((result / b08 / name).read_bytes(), expected[name]) for name in files}
    stills = _read(result / "B13-PMI/diagnostics.json")["frames"]
    bright = next(row for row in stills if row["frame"] == 4440)
    still = result / "B13-PMI" / bright["path"]
    decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(still), "-frames:v", "1",
                              "-f", "null", "-"], capture_output=True, text=True, check=False)
    checks = {
        "b08_reuses_exact_previous_encoding_and_diagnostics": all(reused.values()),
        "b13_current_still_decodes_without_error": still.is_file() and decoded.returncode == 0 and not decoded.stderr,
        "b13_actual_recapped_date_and_original_pmi_numbers": (
            bright["market_date"] == "2015-08-21" and Decimal(str(bright["market_close"])) == Decimal("2341.95")
            and all(term in _caption(bright) for term in ("2015.08.21 · 当日回顾", "47.1", "财新8月制造业PMI初值"))
            and [(entry["time"], entry["role"]) for entry in bright["overlay"]["timeline_points"]] == [
                ("09:30", "market_open"), ("09:43:10", "publisher_webpage_timestamp"),
            ] and not bright["layout_errors"] and bright["no_future_candles"]
        ),
    }
    return _section(checks, b08_reused_files=reused, b13_frame=bright["frame"], b13_visible_copy=_caption(bright))


def _attempt(check, *args) -> dict:
    try:
        return check(*args)
    except (OSError, KeyError, ValueError, IndexError, StopIteration) as error:
        return {"passed": False, "error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-result", type=Path, default=Path("output/director-v1.0.2-visual-test/result"))
    parser.add_argument("--result", type=Path, default=Path("output/director-v1.0.2-visual-r1/result"))
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--candidate-only", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline, base = _baseline(args.repo_root, args.baseline_result)
    checks = {"baseline": baseline}
    if not args.baseline_only:
        current = _read(args.result / "candidate.json")
        checks["candidate"] = _attempt(_candidate, base, current)
        if not args.candidate_only:
            checks.update(b01=_attempt(_b01, args.result), b17=_attempt(_b17, args.result, base, current),
                          b08_and_b13=_attempt(_b08_and_b13, args.result, args.repo_root))
    report = _section({key: value["passed"] for key, value in checks.items()}, sections=checks,
                      scope="committed baseline integrity, authored timing and rendered-frame diagnostic checks")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["checks"], ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
