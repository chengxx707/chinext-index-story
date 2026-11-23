"""Independently check representative encoded media and frame diagnostics."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from decimal import Decimal
from fractions import Fraction
from hashlib import file_digest
import json
import math
from pathlib import Path
import re
import struct
import subprocess


FPS = 30
TARGET = (1080, 1920)
PHONE = (390, 694)
BLOCKS = {"B01-B02": (0, 540), "B16-B18": (5520, 7320)}
BLACK_FILTER = "blackdetect=d=0:pic_th=0.98:pix_th=0.02"


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def _subprocess(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=180, check=False)


def _media(path: Path, expected_frames: int, spec: tuple[int, int]) -> dict:
    if not path.is_file():
        return {"path": str(path), "passed": False, "error": "Missing encoded media"}
    original_hash = _sha(path)
    found = _subprocess([
        "ffprobe", "-v", "error", "-threads", "2", "-count_frames", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    if found.returncode or found.stderr.strip():
        return {"path": str(path), "passed": False, "error": found.stderr[-1500:]}
    data = json.loads(found.stdout)
    streams = data.get("streams", [])
    video = [track for track in streams if track.get("codec_type") == "video"]
    checks = {"single_video_and_no_other_stream": len(video) == len(streams) == 1}
    metadata = {"stream_types": [track.get("codec_type") for track in streams]}
    if len(video) == 1:
        track = video[0]
        time_base = Fraction(track["time_base"])
        duration = int(track.get("duration_ts", -1)) * time_base
        count = int(track.get("nb_read_frames", -1))
        width, height = track.get("width"), track.get("height")
        expected_duration = Fraction(expected_frames, FPS)
        checks.update({
            "dimensions": (width, height) == spec,
            "rate_and_average_rate": all(Fraction(track[k]) == FPS for k in ("r_frame_rate", "avg_frame_rate")),
            "decoded_probe_frame_count": count == expected_frames,
            "exact_stream_duration": duration == expected_duration,
            "container_duration": abs(Fraction(data["format"]["duration"]) - expected_duration) <= Fraction(1, 1_000_000),
            "no_start_edit_offset": Fraction(track.get("start_time", "0")) == 0,
        })
        metadata.update(width=width, height=height, fps=track["r_frame_rate"], frames=count,
                        duration_seconds=float(duration), codec=track.get("codec_name"), time_base=track["time_base"])
    decoded = _subprocess([
        "ffmpeg", "-nostdin", "-hide_banner", "-v", "info", "-xerror", "-threads", "2", "-i", str(path),
        "-map", "0:v:0", "-an", "-vf", BLACK_FILTER, "-fps_mode", "passthrough", "-nostats",
        "-progress", "pipe:1", "-f", "null", "-",
    ])
    black = [(float(a), float(b), float(t)) for a, b, t in re.findall(
        r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", decoded.stderr,
    )]
    frames = re.findall(r"^frame=(\d+)$", decoded.stdout, re.MULTILINE)
    checks.update({
        "decode_without_error": decoded.returncode == 0 and "progress=end" in decoded.stdout,
        "independent_decode_frame_count": bool(frames) and int(frames[-1]) == expected_frames,
        "no_black_intervals_at_threshold": not black,
        "sha256_unchanged_while_checked": _sha(path) == original_hash,
    })
    return {"passed": all(checks.values()), "path": str(path), "sha256": original_hash, "checks": checks,
            "metadata": metadata, "black_filter": BLACK_FILTER, "black_intervals": black,
            "decode_error": decoded.stderr[-1500:] if decoded.returncode else None}


def _read(path: Path):
    return json.loads(path.read_bytes())


def _market(path: Path) -> tuple[dict[str, dict[str, Decimal]], dict[str, int]]:
    names = ("open", "high", "low", "close")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["date"]: {name: Decimal(row[name]) for name in names} for row in csv.DictReader(handle)}
    return rows, {day: i for i, day in enumerate(rows)}


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _candidate_cues(candidate: dict) -> dict[int, dict]:
    return {frame: cue for cue in candidate["cues"]
            for frame in range(cue["start_frame"], cue["end_frame_exclusive"])}


def _bbox_summary(rows: list[dict]) -> dict:
    """Check observed draw bounds and map text geometry to the encoded phone size."""
    failures, heights = [], {}
    for row in rows:
        for box in row["text_boxes"]:
            x1, y1, x2, y2 = box["bbox"]
            if not (0 <= x1 < x2 <= TARGET[0] and 0 <= y1 < y2 <= TARGET[1]):
                failures.append({"frame": row["frame"], "box": box["id"], "bbox": box["bbox"]})
            role = box.get("role", "unknown")
            size = (y2-y1)*(PHONE[1]/TARGET[1])
            stats = heights.setdefault(role, {"min_px": size, "max_px": size, "boxes": 0})
            stats["min_px"] = min(stats["min_px"], size)
            stats["max_px"] = max(stats["max_px"], size)
            stats["boxes"] += 1
    return {"passed": not failures, "out_of_frame_boxes": failures[:50],
            "roles": {k: {**v, "min_px": round(v["min_px"], 2), "max_px": round(v["max_px"], 2)}
                      for k, v in sorted(heights.items())},
            "scope": "rendered target boxes scaled to phone; reading experience needs playback/visual observation"}


def _window_on_report(dates: list[str], indices: dict[str, int]) -> list[int]:
    return [indices[d] for d in dates if d in indices]


def _flash_range(rows: list[dict]) -> bool:
    return (all(row["market_date"] == "2015-06-03" for row in rows[:240])
            and rows[240]["market_date"] == "2015-04-01" and rows[-1]["market_date"] == "2015-04-10")


def _camera_joins(rows: list[dict]) -> dict:
    joins = []
    properties = ("window_start", "window_span", "y_min", "y_max")
    for index, (a, b) in enumerate(zip(rows, rows[1:]), start=1):
        if a["shot_id"] == b["shot_id"]:
            continue
        before, after = a["projection"], b["projection"]
        delta = {key: round(after[key]-before[key], 10) for key in properties}
        previous = rows[index-2]["projection"] if index > 1 else before
        following = rows[index+1]["projection"] if index < len(rows)-1 else after
        velocity = {key: [round(before[key]-previous[key], 10), round(following[key]-after[key], 10)]
                    for key in properties}
        joins.append({"frame": b["frame"], "from": a["shot_id"], "to": b["shot_id"],
                      "explicit_flash_return": b["frame"] == 240, "camera_delta": delta,
                      "neighbor_frame_deltas": velocity,
                      "passed": b["frame"] == 240 or all(abs(value) < 1e-6 for value in delta.values())})
    return {"passed": all(join["passed"] for join in joins), "joins": joins,
            "continuity_scope": "exact sampled projection seam and finite-difference velocity evidence"}


def _clock_and_rail(rows: list[dict], frame_cues: dict, candidate: dict,
                    market: dict[str, dict[str, Decimal]], indices: dict[str, int]) -> dict:
    failures = []
    dates = []
    drawdown = candidate["rail"]["drawdown"]
    rails = {rail["mode"]: rail for rail in (drawdown, candidate["rail"]["rise"])}
    for row in rows:
        frame, day = row["frame"], row["market_date"]
        cue = frame_cues[frame]
        if day not in market:
            failures.append({"frame": frame, "detail": "market date absent from frozen rows", "date": day})
            continue
        dates.append(day)
        close = market[day]["close"]
        if _decimal(row["market_close"]) != close or row["shot_id"] != cue["shot_id"]:
            failures.append({"frame": frame, "detail": "reported close or shot disagrees with frozen data or cue"})
        if (row["market_index"] != indices[day] or math.floor(row["playhead_index"]+1e-9) != indices[day]
                or row["last_eligible_candle_index"] > indices[day] or row["no_future_candles"] is not True):
            failures.append({"frame": frame, "detail": "market index/future candle validation failed"})
        focus = [item for item in cue["camera_story_clock"]["focus_windows"]
                 if item["start_frame"] <= frame < item["end_frame_exclusive"]]
        if (len(focus) != 1 or row["primary_focus"] != focus[0]["primary_focus"]
                or row["visual_mode"] != focus[0]["mode"]):
            failures.append({"frame": frame, "detail": "visible focus disagrees with exclusive authored frame focus"})
        if row["active_track_count"] != 1 or row["stage_mode"] != cue["rail_mode"]:
            failures.append({"frame": frame, "detail": "active rail is absent, duplicated or uses another mode"})
        else:
            rail = rails[row["stage_mode"]]
            base = market[rail["base_date"]]["close"]
            expected = close / base - 1
            if (row["stage_base_date"] != rail["base_date"] or _decimal(row["stage_base_close"]) != base
                    or abs(_decimal(row["stage_value"])-expected) > Decimal("0.0000001")):
                failures.append({"frame": frame, "detail": "rail value disagrees with the actual close/basis"})
        if frame == cue["primary_anchor"]["hit_frame"]:
            anchor = cue["primary_anchor"]
            if day != anchor["date"] or market[day][anchor["field"]] != _decimal(anchor["value"]):
                failures.append({"frame": frame, "detail": "missed exact date/field/price anchor"})
        event = cue.get("event_clock") or {}
        if event.get("market_freeze_after_hit") and frame >= cue["primary_anchor"]["hit_frame"]:
            if day != cue["primary_anchor"]["date"]:
                failures.append({"frame": frame, "detail": "date advanced under a frozen event overlay"})
    locations = _window_on_report(dates, indices)
    if rows[0]["frame"] == 0:
        if not _flash_range(rows):
            failures.append({"detail": "flash-forward did not freeze, reset at f240 and reach April 10"})
        locations = locations[240:]
    no_skips = all(0 <= b-a <= 1 for a, b in zip(locations, locations[1:]))
    if not no_skips:
        failures.append({"detail": "a chronological trading row was skipped or reversed"})
    return {"passed": not failures, "failures": failures[:50], "failure_count": len(failures),
            "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
            "trading_days_observed": list(dict.fromkeys(dates)), "computed_without_trusting_pct_chg": True}


def _candidate_requirements(candidate: dict) -> dict:
    by_variant = {cue["camera_story_clock"].get("visual_variant"): cue for cue in candidate["cues"]}
    pmi, etf, turnover = (by_variant[name] for name in ("pmi_dual_timeline", "etf", "turnover"))
    event = pmi["event_clock"]
    pmi_ok = (
        pmi["text_cue"]["lines"] == ["09:30｜A股开盘", "09:43:10｜财新网页刊发", "财新8月制造业PMI初值 47.1"]
        and event["first_release_time"] is None and event["intraday_price_alignment"] is False
        and [(item["time"], item["role"]) for item in event["timeline_points"]] ==
        [("09:30", "market_open"), ("09:43:10", "publisher_webpage_timestamp")]
        and [item["date"] for item in event["timeline_points"]] == ["2015-08-21", "2015-08-21"]
        and set(key["date"] for key in pmi["market_clock"]["keyframes"]) == {"2015-08-21"}
        and pmi["primary_anchor"]["field"] == "close"
        and pmi["camera_story_clock"]["market_environment"]["show_minute_level_prices"] is False
    )
    etf_ev, turnover_ev = etf["event_clock"], turnover["event_clock"]
    etf_copy = "".join(etf["text_cue"]["lines"])+etf["text_cue"]["source_line"]
    turnover_copy = "".join(turnover["text_cue"]["lines"])+turnover["text_cue"]["source_line"]
    hook = candidate["cues"][0]
    hook_clock = hook["camera_story_clock"]
    intro = hook_clock["intro_camera"]
    reveal = hook_clock["intro_reveal"]
    ranges = {item["id"]: [item["start_frame"], item["end_frame_exclusive"]] for item in candidate["beat_ranges"]}
    etf_read, turnover_read = (cue["camera_story_clock"]["reading_window"] for cue in (etf, turnover))
    checks = {
        "v102_r1_global_timebase": candidate["fps"] == FPS and candidate["frame_count"] == 7320,
        "bounded_r1_beat_timing": ranges["B01"] == [0, 240] and ranges["B02"] == [240, 540]
        and ranges["B17"] == [5880, 6660] and ranges["B18"] == [6660, 7320],
        "hook_true_date_anchor_and_visual_start": (
            hook["beat_id"] == "B01"
            and hook["primary_anchor"] == {"date": "2015-06-03", "field": "close", "value": 3982.25, "hit_frame": 0}
            and intro == {"start_frame": 0, "settled_frame": 48, "initial_visible_trading_days": 72,
                          "initial_y_domain": [1000, 4800], "easing": "smoothstep"}
            and reveal["date_in_frame"] == 0 and reveal["date_full_frame"] == 6
            and reveal["value_in_frame"] == reveal["source_in_frame"] == 48
            and reveal["value_full_frame"] == 54 and hook["earth_orbit"]["hit_frame"] == 48
        ),
        "pmi_context_marks_same_day_retrospective": pmi["camera_story_clock"]["context_label"] == "2015.08.21 · 当日回顾",
        "exact_pmi_dual_timeline_semantics": pmi_ok,
        "etf_copy_units_period_and_attribution": (
            all(value in etf_copy for value in ("易方达创业板ETF份额", "12.37亿份", "18.07亿份", "+46.08%", "9月25日报道", "据中国证券报援引深交所数据"))
            and etf_ev["observation_range"] == ["2015-09-07", "2015-09-22"]
            and etf_ev["publication_date"] == "2015-09-25" and etf_ev["first_release_time"] is None
            and etf_ev["first_party_original_imported"] is False
            and not any(word in etf_copy for word in ("净申购", "净流入", "资金流入", "推高", "导致"))
        ),
        "whole_day_two_exchange_turnover_attribution": (
            "沪深两市成交额" in turnover_copy and "4,044 亿元" in turnover_copy
            and turnover_ev["presentation_context"] == "full_session_total_after_completed_close"
            and turnover_ev["scope"] == "沪深两市合计成交额" and turnover_ev["first_release_time"] is None
        ),
        "t2_layers_have_separate_time_windows": etf["end_frame_exclusive"] < turnover["start_frame"],
        "t2_stable_reading_extended": etf_read[1] - etf_read[0] > 126
        and turnover_read[1] - turnover_read[0] > 102,
        "no_causal_links": all(cue["link_geometry"]["event_line_has_arrowhead"] is False for cue in (pmi, etf, turnover)),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "cues": {name: {"shot_id": cue["shot_id"], "start_frame": cue["start_frame"],
                            "end_frame_exclusive": cue["end_frame_exclusive"],
                            "reading_window": cue["camera_story_clock"]["reading_window"],
                            "exit_window": cue["camera_story_clock"].get("exit_window"),
                            "stable_reading_seconds": cue["text_cue"]["stable_reading_seconds"]}
                     for name, cue in (("pmi", pmi), ("etf", etf), ("turnover", turnover))}}


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG with an IHDR: {path}")
    return struct.unpack("!II", head[16:24])


def _captions_during_reading(rows: list[dict], frame_cues: dict) -> dict:
    cue_frames = {}
    failures = []
    for row in rows:
        frame = row["frame"]
        cue = frame_cues[frame]
        overlay = row["overlay"]
        if cue.get("copy_is_hud_only"):
            continue
        start, end = cue["camera_story_clock"]["reading_window"]
        entry = cue_frames.setdefault(cue["shot_id"], {"planned": [start, end], "measured": [], "height_px_at_390": []})
        if overlay["caption_alpha"] >= .999 and overlay["text_visible"]:
            entry["measured"].append(frame)
            entry["height_px_at_390"].extend((box["bbox"][3]-box["bbox"][1])*PHONE[1]/TARGET[1]
                                              for box in overlay["caption_boxes"])
        if start <= frame < end and (overlay["caption_alpha"] < .999 or not overlay["text_visible"]):
            failures.append({"frame": frame, "shot_id": cue["shot_id"], "detail": "missing full-opacity caption in authored reading interval"})
    summarized = {}
    for cue_id, entry in cue_frames.items():
        observed = entry["measured"]
        start, end = entry["planned"]
        length = len([frame for frame in observed if start <= frame < end])
        heights = entry["height_px_at_390"]
        summarized[cue_id] = {"planned_global_frames": [start, end], "fully_drawn_frames_in_window": length,
                              "rendered_reading_seconds": round(length/FPS, 3),
                              "planned_reading_seconds": round((end-start)/FPS, 3),
                              "all_full_opacity_frames": len(observed),
                              "min_caption_glyph_bbox_height_at_390px": round(min(heights), 2) if heights else None}
    return {"passed": not failures, "failures": failures[:50], "cue_reading": summarized,
            "scope": "actual caption visibility/full opacity; not subjective reading speed"}


def _has_text(row: dict, required: tuple[str, ...]) -> bool:
    text = "".join(row["overlay"]["caption_lines"])
    return all(item in text for item in required)


def _hook(rows: list[dict]) -> dict:
    flash = rows[:240]
    projections = [row["projection"] for row in flash]
    camera = [row["hook_camera"] for row in flash]
    visual = [row["overlay"]["intro_reveal"] for row in flash]
    endpoints = {"window_span": (72, 50), "y_min": (1000, 1300), "y_max": (4800, 4550)}
    trajectory_ok = True
    for frame, projection in enumerate(projections):
        t = min(frame, 48) / 48
        ease = 3 * t * t - 2 * t * t * t
        if any(abs(projection[key] - (before + (after-before)*ease)) > 1e-7
               for key, (before, after) in endpoints.items()):
            trajectory_ok = False
    x_positions = [record["anchor_logical"][0] for record in camera]
    checks = {
        "actual_same_row_eased_projection": trajectory_ok and all(row["market_date"] == "2015-06-03"
                                                                 and _decimal(row["market_close"]) == Decimal("3982.25")
                                                                 for row in flash),
        "real_candle_stays_on_axis_during_push": max(x_positions) - min(x_positions) <= 1e-7
        and all(row["chart_top_logical"] <= camera[i]["anchor_logical"][1] <= 846
                for i, row in enumerate(flash)),
        "historical_qualifier_before_value": (
            visual[6]["date_alpha"] == 1 and _has_text(flash[6], ("闪前", "2015.06.03", "阶段最高收盘"))
            and all(not phase["value_visible"] and not phase["source_visible"] and not _has_text(flash[i], ("3,982.25",))
                    and not flash[i]["overlay"]["geometry"] for i, phase in enumerate(visual[:48]))
        ),
        "no_competing_numeric_hud_across_hook": all(
            not row["hud"]["close_visible"] and row["hud"]["close_text"] is None
            and not any(box["id"] == "current_close" for box in row["text_boxes"]) for row in flash
        ),
        "one_value_reveal_and_stable_hold": (
            visual[48]["value_visible"] and 0 < visual[48]["value_alpha"] < 1
            and all(phase["value_alpha"] == 1 and phase["source_visible"]
                    and "".join(flash[i]["overlay"]["caption_lines"]).count("3,982.25") == 1
                    for i, phase in enumerate(visual[54:], start=54))
            and all(visual[i]["value_alpha"] <= visual[i+1]["value_alpha"] for i in range(48, 54))
        ),
        "hook_returns_to_ordinary_hud_at_240": rows[240]["market_date"] == "2015-04-01"
        and rows[240]["hud"]["close_visible"] and rows[240]["hud"]["close_text"] == "2,404.91"
        and rows[240]["hook_camera"] is None and rows[240]["overlay"].get("intro_reveal") is None,
    }
    return {
        "passed": all(checks.values()), "checks": checks,
        "sampled_frames": [
            {key: rows[frame][key] for key in ("frame", "market_date", "market_close", "projection", "hook_camera", "hud")}
            | {"reveal": rows[frame]["overlay"]["intro_reveal"]} for frame in (0, 6, 24, 47, 48, 54, 239, 240)
        ],
    }


def _t2(rows: list[dict], candidate: dict) -> dict:
    variant = {cue["camera_story_clock"].get("visual_variant"): cue for cue in candidate["cues"]}
    specs = [
        ("etf", "E-SEP-ETF-01", "2015-09-25", Decimal("2020.97"),
         ("易方达创业板ETF份额", "9/7—9/22", "2015.09.25", "12.37亿份", "18.07亿份", "+46.08%", "据中国证券报援引深交所数据")),
        ("turnover", "E-SEP-TURNOVER-01", "2015-09-28", Decimal("2122.26"),
         ("2015.09.28 · 收盘后", "沪深两市成交额", "4,044", "亿元", "中国新闻网、21世纪经济报道")),
    ]
    by_frame = {row["frame"]: row for row in rows}
    checks = {}
    windows = {}
    for name, metric_id, date, close, required in specs:
        cue = variant[name]
        entered, stop = cue["start_frame"], cue["end_frame_exclusive"]
        first_read, reading_end = cue["camera_story_clock"]["reading_window"]
        exit_start, exit_end = cue["camera_story_clock"]["exit_window"]
        shown = [row for row in rows if (row["overlay"]["market_structure"] or {}).get("metric_id") == metric_id]
        first_visible = shown[0]["frame"] if shown else None
        checks[name+" only displayed after relevant real close"] = (
            bool(shown) and by_frame[entered-1]["market_date"] == date
            and _decimal(by_frame[entered-1]["market_close"]) == close
            and all(row["market_date"] == date and _decimal(row["market_close"]) == close
                    and entered <= row["frame"] < stop for row in shown)
        )
        checks[name+" valid T2 labels every full-read frame"] = all(
            _has_text(by_frame[frame], required)
            and by_frame[frame]["overlay"]["caption_alpha"] >= .999
            and by_frame[frame]["overlay"]["market_structure"]["evidence_tier"] == "T2"
            and by_frame[frame]["primary_focus"] == "L3_MARKET_STRUCTURE"
            for frame in range(first_read, reading_end)
        )
        fade = [by_frame[frame]["overlay"]["caption_alpha"] for frame in range(exit_start, exit_end)]
        checks[name+" complete out-fade before following cue"] = (
            len(fade) >= 4 and fade[0] >= .999 and fade[-1] == 0
            and all(before >= after for before, after in zip(fade, fade[1:]))
            and any(0 < alpha < 1 for alpha in fade)
            and not by_frame[stop-1]["overlay"]["text_visible"]
            and by_frame[stop-1]["overlay"]["market_structure"] is None
        )
        windows[name] = {"first_visible_frame": first_visible,
                         "last_visible_frame": shown[-1]["frame"] if shown else None,
                         "preexisting_market_close_frame": entered - 1,
                         "stable_read_frame_interval": [first_read, reading_end],
                         "stable_reading_seconds": round((reading_end-first_read)/FPS, 3),
                         "exit_frame_interval": [exit_start, exit_end], "exit_alpha_samples": fade}
    checks["market structures do not overlap visually"] = all(
        not (_has_text(row, ("易方达创业板ETF份额",)) and _has_text(row, ("沪深两市成交额",))) for row in rows)
    checks["shows Sep28 market rebound after ETF and before turnover"] = any(
        variant["etf"]["end_frame_exclusive"] <= row["frame"] < variant["turnover"]["start_frame"]
        and row["market_date"] == "2015-09-28" and row["overlay"]["market_structure"] is None
        and _has_text(row, ("+5.01%",)) for row in rows)
    checks["shows Sep29 actual pullback after turnover"] = any(
        row["frame"] >= variant["turnover"]["end_frame_exclusive"] and row["market_date"] == "2015-09-29"
        and row["overlay"]["market_structure"] is None and _has_text(row, ("−1.12%",)) for row in rows)
    checks["metric overlays omit chart-to-event link geometry"] = all(
        not row["overlay"]["geometry"] for row in rows if row["overlay"]["market_structure"])
    return {"passed": all(checks.values()), "checks": checks, "windows": windows}


def _pmi_still(folder: Path, frame_cues: dict, market: dict, indices: dict) -> dict:
    if not (folder / "diagnostics.json").is_file():
        return {"passed": False, "error": "Missing B13 still diagnostics"}
    envelope = _read(folder / "diagnostics.json")
    frames = envelope["frames"]
    checks = []
    details = []
    for row in frames:
        frame = row["frame"]
        path = folder / row["path"]
        overlay = row["overlay"]
        cue = frame_cues[frame]
        full, exit_frame = cue["camera_story_clock"]["reading_window"]
        if not full <= frame < exit_frame:
            continue
        if path.is_file():
            size = _png_size(path)
            decoded = _subprocess(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(path),
                                   "-frames:v", "1", "-f", "null", "-"])
            valid_image = size == TARGET and decoded.returncode == 0
        else:
            size, valid_image = None, False
        checks.append(valid_image and row["beat_id"] == "B13" and row["market_date"] == "2015-08-21"
                      and row["overlay"]["caption_alpha"] == 1 and row["no_future_candles"] is True
                      and _decimal(row["market_close"]) == market["2015-08-21"]["close"]
                      and row["market_index"] == indices["2015-08-21"] and row["chart_alpha"] < 1
                      and overlay["visual_variant"] == "pmi_dual_timeline"
                      and not row["layout_errors"] and not overlay["geometry"]
                      and _has_text(row, ("当日回顾", "09:30", "A股开盘", "09:43:10", "财新网页刊发", "47.1"))
                      and [(entry["time"], entry["role"]) for entry in overlay["timeline_points"]] ==
                      [("09:30", "market_open"), ("09:43:10", "publisher_webpage_timestamp")])
        details.append({"frame": frame, "path": str(path), "sha256": _sha(path) if path.is_file() else None,
                        "size": size, "actual_text": overlay["caption_lines"], "charted_market_date": row["market_date"],
                        "first_release_time": cue["event_clock"]["first_release_time"], "passed": checks[-1]})
    boxes = _bbox_summary(frames)
    return {"passed": len(checks) == 2 and all(checks) and boxes["passed"], "tested_fully_visible_stills": details,
            "diagnostics_sha256": _sha(folder / "diagnostics.json"),
            "phone_bbox_summary": boxes, "video_encoded": False}


def _block(folder: Path, bounds: tuple[int, int], candidate: dict, frame_cues: dict,
           market: dict, indices: dict, target_report: dict) -> dict:
    start, end = bounds
    diagnostic_path = folder / "diagnostics.json"
    if not diagnostic_path.is_file():
        return {"passed": False, "error": "Missing frame diagnostics"}
    envelope = _read(diagnostic_path)
    rows = envelope["frames"]
    if [row["frame"] for row in rows] != list(range(start, end)):
        return {"passed": False, "error": "Diagnostics do not cover the exact authorized frame interval",
                "actual_frames": len(rows), "expected": [start, end]}
    own_report = _read(folder / "media_validation.json")
    structural = {"claim_matches_authorized_range": own_report["global_frame_interval"] == [start, end],
                  "diagnostics_link_to_actual_target_sha": own_report["sha256"] == target_report.get("sha256"),
                  "diagnostics_report_no_layout_errors": envelope["passed"] and all(not row["layout_errors"] for row in rows),
                  "source_rgba_frames_match_target_dimensions": (envelope["width"], envelope["height"]) == TARGET}
    phone_bounds = _bbox_summary(rows)
    protected_box_issues = []
    for row in rows:
        chart_top = row["chart_top_logical"] * TARGET[0] / 720
        for box in row["overlay"]["caption_boxes"]:
            if box["bbox"][3] > chart_top + 1:
                protected_box_issues.append({"frame": row["frame"], "id": box["id"],
                                             "target_bottom": box["bbox"][3], "clipped_chart_top": chart_top})
    structural["caption_band_does_not_cover_chart"] = not protected_box_issues
    main = {"clock_focus_and_rail": _clock_and_rail(rows, frame_cues, candidate, market, indices),
            "camera": _camera_joins(rows), "phone_bbox_summary": phone_bounds,
            "caption_reading": _captions_during_reading(rows, frame_cues)}
    if start == 0:
        main["hook_opening_eased_reveal"] = _hook(rows)
    if start == 5520:
        main["b17_separate_t2_layers"] = _t2(rows, candidate)
        final = any(row["market_date"] == "2015-11-25" and _has_text(row, ("+61.19%", "9月15日"))
                    for row in rows)
        closing = _decimal(rows[-1]["market_close"]) == Decimal("2897.57")
        main["november_settlement"] = {"passed": final and closing, "final_close": rows[-1]["market_close"],
                                        "interval_label_observed": final}
    return {"passed": all(structural.values()) and all(result["passed"] for result in main.values()),
            "diagnostics_sha256": _sha(diagnostic_path), "checks": structural, **main,
            "caption_chart_issues": protected_box_issues[:50]}


def _safe(function, *args) -> dict:
    try:
        return function(*args)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.TimeoutExpired) as error:
        return {"passed": False, "error": f"{type(error).__name__}: {error}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--phone-filename", default="phone-390.mp4")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result_root = args.result.resolve()
    candidate_path = (args.candidate or result_root / "candidate.json").resolve()
    market_path = args.repo_root.resolve() / "data/cyb_daily.csv"
    candidate = _read(candidate_path)
    frame_cues = _candidate_cues(candidate)
    market, indices = _market(market_path)
    media = {block: {} for block in BLOCKS}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = []
        for block, (start, end) in BLOCKS.items():
            for kind, name, size in (("target", "target.mp4", TARGET), ("phone", args.phone_filename, PHONE)):
                jobs.append((block, kind, pool.submit(_safe, _media, result_root / block / name, end-start, size)))
        for block, kind, pending in jobs:
            media[block][kind] = pending.result()
    blocks = {block: _safe(_block, result_root / block, bounds, candidate, frame_cues, market, indices,
                           media[block]["target"]) for block, bounds in BLOCKS.items()}
    pmi = _safe(_pmi_still, result_root / "B13-PMI", frame_cues, market, indices)
    contract = _safe(_candidate_requirements, candidate)
    passed = (contract["passed"] and pmi["passed"] and all(block["passed"] for block in blocks.values())
              and all(item["passed"] for pair in media.values() for item in pair.values()))
    report = {"passed": passed, "scope": "independent ffprobe/full-decode checks and actual R1 compositor diagnostics",
              "authorized_global_ranges": BLOCKS, "candidate_sha256": _sha(candidate_path),
              "frozen_ohlc_sha256": _sha(market_path), "candidate": contract, "media": media, "blocks": blocks,
              "pmi": pmi, "B08-B10_recheck": "outside this R1 render; use pinned previously verified bytes",
              "subjective_mobile_readability_validated_by_this_script": False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "candidate": contract["passed"], "pmi": pmi["passed"],
                      "blocks": {key: value["passed"] for key, value in blocks.items()},
                      "media": {block: {kind: report["passed"] for kind, report in objects.items()}
                                for block, objects in media.items()}}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
