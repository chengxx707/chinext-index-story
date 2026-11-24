"""Check the rendered S04–S09 20-second phone excerpt against frozen data and approved cues."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from itertools import combinations, pairwise
import json
from pathlib import Path
import re
import subprocess


FPS, FRAMES = 30, 600
ROOT = Path("output/director-s04-s09-phone/review")
VISUALS = "editorial/2015/director/visual-tests"
APPROVAL = "9bfc3039efe5a78b9a48bbe3c27844935238060f"
MONTAGE = "a65de025fbc9c9eda06cc1a80f0f463e8ed39507"
BASE = "2012-12-03"
PEAK = "2015-06-03"
PRIMARY_WINDOWS = {
    "low": (0, 46), "huayi": (120, 174), "ipo": (210, 270), "accounts_policy": (330, 387),
    "accounts": (390, 450), "letv": (450, 512), "peak": (540, 600),
}


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, timeout=100, check=False)


def _git(repo: Path, commit: str, name: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{name}"], timeout=30)


def _result(checks: dict, **evidence) -> dict:
    return {"passed": all(checks.values()), "checks": checks, **evidence}


def _media(path: Path) -> dict:
    source_sha = _sha(path.read_bytes())
    found = _run(["ffprobe", "-v", "error", "-threads", "2", "-show_streams", "-show_frames", "-of", "json", str(path)])
    if found.returncode or found.stderr:
        raise ValueError(found.stderr[-800:])
    doc = json.loads(found.stdout)
    tracks = doc["streams"]
    v = tracks[0]
    time_base = Fraction(v["time_base"])
    pts = [int(frame["best_effort_timestamp"]) * time_base for frame in doc["frames"]]
    decoded = _run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "info", "-xerror", "-threads", "2", "-i", str(path),
                    "-map", "0:v:0", "-vf", "blackdetect=d=0:pic_th=0.98:pix_th=0.02", "-fps_mode", "passthrough",
                    "-progress", "pipe:1", "-nostats", "-f", "null", "-"])
    counts = re.findall(r"^frame=(\d+)$", decoded.stdout, re.MULTILINE)
    black = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", decoded.stderr)
    return _result({
        "one_silent_h264_video_track": len(tracks) == 1 and v["codec_type"] == "video" and v["codec_name"] == "h264",
        "exact_390_694_420p": (v["width"], v["height"], v["pix_fmt"]) == (390, 694, "yuv420p"),
        "600_exact_consecutive_30fps_pts": pts == [Fraction(frame, FPS) for frame in range(FRAMES)]
        and Fraction(v["avg_frame_rate"]) == Fraction(v["r_frame_rate"]) == FPS,
        "exact_20_seconds": int(v["duration_ts"]) * time_base == 20,
        "ffmpeg_full_decode_600_frames_no_error": decoded.returncode == 0 and bool(counts) and int(counts[-1]) == FRAMES,
        "no_black_intervals_at_98_percent_threshold": not black,
        "file_unchanged_during_checks": _sha(path.read_bytes()) == source_sha,
    }, sha256=source_sha, decoded_frames=len(pts), black_intervals=black, avc_profile=v.get("profile"))


def _market(repo: Path) -> tuple[list[tuple[str, dict]], dict]:
    with (repo / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as handle:
        candles = [(row["date"], {key: Decimal(row[key]) for key in ("open", "high", "low", "close")})
                   for row in csv.DictReader(handle)]
    return candles, {date: index for index, (date, _) in enumerate(candles)}


def _pinned(repo: Path) -> tuple[dict, list[str]]:
    approval = json.loads(_git(repo, APPROVAL, f"{VISUALS}/s04-s09-reference-r1/stills-check.json"))
    storyboard = _git(repo, MONTAGE, f"{VISUALS}/s04-s09-montage/README.md").decode()
    anchors = [match.replace(".", "-") for match in re.findall(r"^\| 00:\d{2}–00:\d{2} \| (\d{4}\.\d{2}\.\d{2}) \|", storyboard, re.MULTILINE)]
    digests = {name: _sha((repo / name).read_bytes()) == digest for name, digest in approval["source_hashes"].items()}
    release = _git(repo, APPROVAL, "editorial/2015/releases/v1.0.1/period_screen_copy.md").decode()
    register = json.loads(_git(repo, APPROVAL, "editorial/2015/releases/v1.0.1/event_review.json"))
    payload = register.get("events", register.get("event_reviews"))
    event = {row["event_id"]: row for row in payload}
    accounts = event["E-APR-01-04"]
    letv = event["E-IND-01-04"]
    recomputed_letv = Decimal("82.49") * Decimal("1850618138") / Decimal("100000000")
    result = _result({
        "actual_approved_frozen_source_hashes_match": all(digests.values()),
        "20_approved_storyboard_trading_anchors": len(anchors) == 20 and anchors[0] == BASE and anchors[-1] == PEAK,
        "account_source_and_observation_period": all(term in accounts["approved_claim"] for term in
            ("同期报道引中国结算", "4月20—24日", "413.03万户")) and "4月28日20:37" in "".join(accounts["corrections"]),
        "letv_source_dates_and_authorized_basis": letv["event_date"] == "2015-05-13"
        and "收盘总市值超过 1,500 亿元" in letv["screen_safe_copy"] and recomputed_letv > 1500
        and '"source_publication_dates": ["2015-05-17", "2015-05-18"]' in release,
    }, approval_commit=APPROVAL, storyboard_commit=MONTAGE, frozen_sources=digests,
        account_report_after_close="2015-04-28 20:37", letv_recomputed_yi_yuan=str(recomputed_letv.quantize(Decimal(".01"))))
    return result, anchors


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _clock(rows: list[dict], anchors: list[str], candles: list[tuple[str, dict]], indices: dict) -> dict:
    section = set()
    failures = []
    base_close = candles[indices[BASE]][1]["close"]
    last = indices[PEAK]
    widest_index_step = max(b["market_index"] - a["market_index"] for a, b in pairwise(rows))
    for row in rows:
        frame, date, idx = row["frame"], row["market_date"], row["market_index"]
        prices = candles[idx][1]
        errors = []
        if indices.get(date) != idx or {key: _dec(value) for key, value in row["price_ohlc"].items()} != prices or _dec(row["market_close"]) != prices["close"]:
            errors.append("frozen timestamp, OHLC or close")
        if row["active_track_count"] != 1 or abs(_dec(row["stage_return_percent"]) - (prices["close"] / base_close - 1) * 100) > Decimal("0.005001"):
            errors.append("single rail or return basis")
        first, end = row["window_first"], row["window_last"]
        if not 0 <= first <= idx == end <= last or not row["no_future_candles"]:
            errors.append("field uses inclusive first/last chart indices and ends at the HUD date")
        else:
            section.update(range(max(first, indices[BASE]), end + 1))
        projection = row["projection"]
        if projection["y_min"] >= projection["y_max"] or projection["window_span"] <= 0:
            errors.append("invalid projection")
        elif not all(projection["y_min"] <= float(candle["low"]) <= float(candle["high"]) <= projection["y_max"]
                     for _, candle in candles[first:end + 1]):
            errors.append("a real candle or wick falls outside the independent price-domain check")
        if not (0 <= row["current_point_logical_xy"][0] <= 720 and 0 <= row["current_point_logical_xy"][1] <= 1280):
            errors.append("current close plotted outside the canvas")
        if errors:
            failures.append({"frame": frame, "errors": errors})
    checks = {
        "one_record_for_each_of_600_frames": [row["frame"] for row in rows] == list(range(FRAMES)),
        "required_20_anchor_dates_at_second_boundaries": [rows[frame]["market_date"] for frame in range(0, FRAMES, FPS)] == anchors,
        "all_600_market_states_use_real_ohlc_and_no_future_candles": not failures,
        "trading_dates_never_reverse": all(a["market_index"] <= b["market_index"] for a, b in pairwise(rows)),
        "all_605_sessions_covered_by_the_scroll_windows": section == set(range(indices[BASE], last + 1)),
        "endpoint_closes_and_stage_return_agree": _dec(rows[0]["market_close"]) == Decimal("593.66")
        and _dec(rows[-1]["market_close"]) == Decimal("3982.25")
        and _dec(rows[-1]["stage_return_percent"]).quantize(Decimal(".01")) == Decimal("570.80"),
        "final_60_frames_hold_exact_peak_date_price_projection_and_dot": all(
            row["market_date"] == PEAK and row["market_close"] == rows[540]["market_close"]
            and row["projection"] == rows[540]["projection"] and row["current_point_logical_xy"] == rows[540]["current_point_logical_xy"]
            for row in rows[540:]),
    }
    return _result(checks, failures=failures[:20], frozen_sessions_covered=len(section), largest_hud_step_in_sessions=widest_index_step,
                   measured_peak_hold_frames=60, anchor_days=[rows[frame]["market_date"] for frame in range(0, FRAMES, FPS)])


def _layout(rows: list[dict]) -> dict:
    bad = []
    for row in rows:
        boxes = row["text_boxes_logical"]
        for box in boxes:
            left, top, right, bottom = box["bbox"]
            if not 0 <= left < right <= 720 or not 0 <= top < bottom <= 1280:
                bad.append({"frame": row["frame"], "issue": "off_canvas", "box": box["id"]})
        for a, b in combinations(boxes, 2):
            u, v = a["bbox"], b["bbox"]
            if min(u[2], v[2]) - max(u[0], v[0]) > 1 and min(u[3], v[3]) - max(u[1], v[1]) > 1:
                bad.append({"frame": row["frame"], "issue": "text_intersection", "boxes": [a["id"], b["id"]]})
    return _result({"every_tracked_text_box_is_on_canvas_and_disjoint": not bad}, issue_count=len(bad), first_issues=bad[:12])


def _overlay(rows: list[dict]) -> dict:
    primary = {key: [] for key in PRIMARY_WINDOWS}
    overlaps = []
    for row in rows:
        cue = row["cue"]
        if active := cue["primary"]:
            primary[active["id"]].append(row)
            if active["id"] == "ipo" and any(item["id"] == "huayi" for item in cue["secondary"]):
                overlaps.append(row["frame"])
    stats = {
        name: {"first_last_frames": [entries[0]["frame"], entries[-1]["frame"]] if entries else None,
               "full_alpha_frames": sum(row["cue"]["primary"]["opacity"] == 1 for row in entries),
               "copy": entries[0]["cue"]["primary"]["lines"] if entries else None}
        for name, entries in primary.items()
    }
    accounts = primary["accounts"]
    letv = primary["letv"]
    anchor_dates = {"low": (BASE, "593.66"), "peak": (PEAK, "3,982.25")}
    checks = {
        "one_planned_primary_also_matches_each_precise_frame_window": all(
            [row["frame"] for row in primary[name]] == list(range(start, stop))
            and all(row["cue"]["frame"] == row["frame"] and row["cue"]["primary"]["opacity"] > 0 for row in primary[name])
            for name, (start, stop) in PRIMARY_WINDOWS.items()
        ),
        "ipo_primary_and_huayi_past_event_overlap_only_24_frames": overlaps == list(range(210, 234))
        and all(rows[i]["cue"]["primary"]["lines"] == ["2014.01", "IPO 重启"] and any(
            item["id"] == "huayi" and item["visual_role"] == "past_event" and item["opacity"] < 1
            and item["lines"] == ["2013.07", "华谊兄弟并购"] for item in rows[i]["cue"]["secondary"]
        ) for i in overlaps),
        "accounts_only_after_april28_reporting_and_correct_statistical_scope": bool(accounts) and all(
            row["market_date"] >= "2015-04-29" and row["cue"]["primary"]["precision"] == "statistics_week"
            and row["cue"]["primary"]["lines"] == ["2015.04.20—24  ·  统计周", "新增 A 股账户", "413.03 万户"]
            and row["cue"]["primary"]["source"] == "中国结算数据  ·  4/28 盘后报道" for row in accounts
        ),
        "dense_reference_day_keeps_two_past_events_and_real_hud_separate": rows[420]["market_date"] == "2015-05-05"
        and rows[420]["cue"]["market_hud"] == {"date": "2015.05.05", "close": "2,783.44", "label": "当日收盘"}
        and {event["id"] for event in rows[420]["cue"]["secondary"]} == {"accounts_policy", "ipo"},
        "letv_as_of_may13_close_with_two_named_sources_and_after_coverage": bool(letv) and all(
            row["market_date"] >= "2015-05-18" and row["cue"]["primary"]["precision"] == "historical_close"
            and row["cue"]["primary"]["lines"] == ["回看 2015.05.13 收盘", "乐视网总市值", "超过 1,500 亿元"]
            and all(label in row["cue"]["primary"]["source"] for label in ("北京青年报", "大众证券报")) for row in letv
        ),
        "clear_event_layers_in_28_prepeak_frames_and_60_full_alpha_final": all(
            row["cue"]["primary"] is None and row["cue"]["secondary"] == [] for row in rows[512:540]
        ) and all(row["cue"]["primary"]["opacity"] == 1 and row["cue"]["secondary"] == [] for row in primary["peak"]),
        "both_hero_numbers_are_tied_to_actual_visible_close_point": all(
            row["market_date"] == date and row["cue"]["primary"]["lines"][:2] == [date.replace("-", "."), close]
            and all(abs(a - b) < 1e-6 for a, b in zip(row["cue"]["primary"]["price_anchor_logical"], row["current_point_logical_xy"], strict=True))
            for name, (date, close) in anchor_dates.items() for row in primary[name]
        ),
        "all_regular_hud_values_match_the_real_rows": all(
            row["cue"]["market_hud"] == {"date": row["market_date"].replace("-", "."), "close": f"{row['market_close']:,.2f}", "label": "当日收盘"}
            for row in rows[46:540]
        ),
    }
    return _result(checks, primary_events=stats, huayi_and_ipo_overlap_frames=overlaps,
                   clear_prepeak_frames_end_exclusive=[512, 540])


def _lineage(repo: Path, folder: Path, frames: dict) -> dict:
    manifest = json.loads((folder / "manifest.json").read_bytes())
    hashes = json.loads(_git(repo, APPROVAL, f"{VISUALS}/s04-s09-reference-r1/stills-check.json"))
    return _result({
        "actual_phone_file_and_all_frame_records_match_export_manifest": manifest["passed"]
        and manifest["sha256"] == _sha((folder / "phone-390.mp4").read_bytes())
        and manifest["drawn_frames_trace_sha256"] == _sha((folder / "frames.json").read_bytes()),
        "approved_stills_same_sources_and_landgeometry": manifest["approval_commit"] == frames["approved_stills"] == APPROVAL
        and manifest["source_hashes"] == frames["source_hashes"] == hashes["source_hashes"]
        and manifest["land_geometry_sha256"] == frames["land_geometry_sha256"] == hashes["land_geometry"]["sha256"],
        "frame_record_declares_exact_delivery_timebase": frames["fps"] == manifest["fps"] == FPS
        and frames["duration_seconds"] == manifest["duration_seconds"] == 20 and frames["phone_canvas"] == [390, 694],
    }, media_sha256=manifest["sha256"], render_trace_sha256=manifest["drawn_frames_trace_sha256"])


def _safe(use, *params) -> dict:
    try:
        return use(*params)
    except (OSError, KeyError, ValueError, IndexError, TypeError, subprocess.SubprocessError) as error:
        return _result({"completed_independent_check": False}, error=f"{type(error).__name__}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--review", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT.parent / "qa/technical_validation.json")
    parser.add_argument("--pinned-only", action="store_true")
    args = parser.parse_args()
    pinned, anchors = _pinned(args.repo)
    sections = {"pinned_inputs_and_source_ledger": pinned}
    evidence = {}
    if not args.pinned_only:
        data = args.review / "frames.json"
        parsed = json.loads(data.read_bytes())
        rows = parsed["frames"]
        candles, indices = _market(args.repo)
        sections.update({"lineage": _safe(_lineage, args.repo, args.review, parsed),
                         "media": _safe(_media, args.review / "phone-390.mp4"),
                         "clock": _safe(_clock, rows, anchors, candles, indices),
                         "layout": _safe(_layout, rows), "overlay": _safe(_overlay, rows)})
        evidence = {"frame_record_sha256": _sha(data.read_bytes())}
    report = _result({name: value["passed"] for name, value in sections.items()}, sections=sections,
                     scope="independent actual decode and frame-record cross-checks; playback review separate", **evidence)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["checks"], ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
