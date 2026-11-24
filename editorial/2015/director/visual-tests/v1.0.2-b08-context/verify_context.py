"""Verify the B08–B10 phone review export against pinned baseline and sign-off."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from io import BytesIO


BASELINE = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
SIGNED = "aa7ee0aeebf9861ceecbc889ce13898e24063cb5"
VISUALS = "editorial/2015/director/visual-tests"
ROOT = Path("output/director-v1.0.2-b08-context")
START, END, FPS = 2280, 3600, 30
SIGNED_IN, SIGNED_OUT = 2550, 2670
JULY1_IN, JULY1_OUT = 2666, 2674
TARGET_FRAMES = 1350
SIGNED_LOCAL = (SIGNED_IN - START, SIGNED_OUT - START)
STABLE = (394, 444)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, capture_output=True, timeout=120, check=False)


def _git(repo: Path, commit: str, name: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{name}"], timeout=25)


def _check(checks: dict, **evidence) -> dict:
    return {"passed": all(checks.values()), "checks": checks, **evidence}


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _market(repo: Path) -> dict:
    with (repo / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as handle:
        return {row["date"]: {key: Decimal(row[key]) for key in ("open", "high", "low", "close")}
                for row in csv.DictReader(handle)}


def _baseline(repo: Path, market: dict) -> tuple[dict, bytes, bytes, dict]:
    prefix = f"{VISUALS}/v1.0.2"
    signed_prefix = f"{VISUALS}/v1.0.2-selected/b08"
    baseline = _git(repo, BASELINE, f"{prefix}/B08-B10/phone-390.mp4")
    signed_clip = _git(repo, SIGNED, f"{signed_prefix}/phone-390.mp4")
    original_manifest = json.loads(_git(repo, BASELINE, f"{prefix}/B08-B10/manifest.json"))
    signed_manifest = json.loads(_git(repo, SIGNED, f"{signed_prefix}/manifest.json"))
    zipped = _git(repo, BASELINE, f"{prefix}/director-v1.0.2-representative-visual-review.zip")
    with ZipFile(BytesIO(zipped)) as bundle:
        baseline_diagnostic_bytes = bundle.read("B08-B10/diagnostics.json")
    frames = {row["frame"]: row for row in json.loads(baseline_diagnostic_bytes)["frames"]}
    locked = {path: _sha((repo / path).read_bytes()) == _sha(_git(repo, BASELINE, path))
              for path in ("data/cyb_daily.csv", "config/event_registry.json", "config/production/film_master_v1.json",
                           "assets/earth_cinematic.png", "assets/earth_body.png")}
    june30, july1, june3 = (market[day] for day in ("2015-06-30", "2015-07-01", "2015-06-03"))
    return_percent = 100 * (july1["close"] / june30["close"] - 1)
    full_drawdown = 100 * (july1["close"] / june3["close"] - 1)
    july_rows = [row for row in frames.values() if row["market_date"] == "2015-07-01"]
    signed_last = signed_manifest["market_boundaries"][str(SIGNED_OUT - 1)]
    evidence = _check({
        "baseline_and_signed_media_match_commit_manifests": _sha(baseline) == original_manifest["artifacts"]["phone-390.mp4"]["sha256"]
        and _sha(signed_clip) == signed_manifest["media"]["sha256"],
        "frozen_prices_event_register_master_and_assets_match": all(locked.values()),
        "signed_short_includes_first_four_true_july1_frames": signed_manifest["frame_interval_end_exclusive"] == [SIGNED_IN, SIGNED_OUT]
        and signed_last["market_date"] == "2015-07-01" and Decimal(str(signed_last["market_close"])) == july1["close"]
        and SIGNED_OUT - JULY1_IN == 4,
        "baseline_july1_reader_is_only_eight_plain_hud_frames": [row["frame"] for row in july_rows] == list(range(JULY1_IN, JULY1_OUT))
        and all(row["overlay"]["text_visible"] is False and Decimal(str(row["market_close"])) == july1["close"] for row in july_rows),
        "baseline_diagnostics_match_recorded_sha256": _sha(baseline_diagnostic_bytes) == original_manifest["artifacts"]["diagnostics.json"]["sha256"],
    }, frozen_checks=locked, baseline_commit=BASELINE, signed_commit=SIGNED, signed_sha256=_sha(signed_clip),
        baseline_sha256=_sha(baseline), july1={
            "ohlc": {key: str(value) for key, value in july1.items()}, "from_june30_close_pct": str(return_percent),
            "from_june3_close_pct": str(full_drawdown), "original_frames_end_exclusive": [JULY1_IN, JULY1_OUT],
            "original_duration_seconds": len(july_rows) / FPS,
        })
    return evidence, baseline, signed_clip, frames


def _decode_hashes(video: Path) -> list[str]:
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-threads", "2", "-i", str(video),
            "-map", "0:v:0", "-fps_mode", "passthrough", "-pix_fmt", "yuv420p"]
    result = _run(args + ["-f", "framehash", "-hash", "sha256", "-"])
    if result.returncode or result.stderr:
        raise ValueError(result.stderr[-900:])
    return [line.rsplit(",", 1)[1].strip() for line in result.stdout.splitlines() if line and not line.startswith("#")]


def _probe(path: Path, depth: int) -> dict:
    result = _run(["ffprobe", "-v", "error", "-threads", "2", "-show_streams", "-show_frames", "-of", "json", str(path)])
    if result.returncode or result.stderr:
        raise ValueError(result.stderr[-900:])
    raw = json.loads(result.stdout)
    v = raw["streams"][0]
    time_base = Fraction(v["time_base"])
    pts = [Fraction(row["best_effort_timestamp"]) * time_base for row in raw["frames"]]
    decoded = _run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "info", "-xerror", "-threads", "2", "-i", str(path),
                    "-vf", "blackdetect=d=0:pic_th=0.98:pix_th=0.02", "-fps_mode", "passthrough",
                    "-progress", "pipe:1", "-nostats", "-f", "null", "-"])
    counts = re.findall(r"^frame=(\d+)$", decoded.stdout, re.MULTILINE)
    black = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", decoded.stderr)
    return _check({
        "single_h264_video_no_audio": len(raw["streams"]) == 1 and v["codec_type"] == "video" and v["codec_name"] == "h264",
        "phone_390x694_yuv420p": (v["width"], v["height"], v["pix_fmt"]) == (390, 694, "yuv420p"),
        "phone_avc_high_profile_level3": v["profile"] == "High" and v["level"] == 30,
        "exact_cfr_pts_duration": pts == [Fraction(frame, FPS) for frame in range(depth)] and int(v["duration_ts"]) * time_base == Fraction(depth, FPS)
        and Fraction(v["avg_frame_rate"]) == Fraction(v["r_frame_rate"]) == FPS,
        "whole_stream_decodes": decoded.returncode == 0 and bool(counts) and int(counts[-1]) == depth,
        "blackdetect_empty": not black,
    }, frames=len(pts), fps=FPS, duration_seconds=depth / FPS, profile=v.get("profile"), sha256=_sha(path.read_bytes()), black_intervals=black)


def _pixel_section(a: list[str], b: list[str], label: str) -> dict:
    different = [frame for frame, (source, target) in enumerate(zip(a, b)) if source != target]
    return _check({label: len(a) == len(b) and bool(a) and not different},
                  requested_frames=len(a), resulting_frames=len(b), different_relative_frame_indices=different[:10])


def _similarity(source: Path, source_range: tuple[int, int], target: Path, target_range: tuple[int, int],
                crop: str = "", repeat_source: bool = False) -> dict:
    trims = []
    for stream, (start, stop) in enumerate((source_range, target_range)):
        settings = f"trim=start_frame={start}:end_frame={stop}"
        if stream == 0 and repeat_source:
            settings += f",tpad=stop_mode=clone:stop={target_range[1] - target_range[0] - 1}"
        settings += ",settb=1/30,setpts=N"
        if crop:
            settings += f",crop={crop}"
        trims.append(f"[{stream}:v]{settings}[v{stream}]")
    graph = ";".join([*trims, "[v0][v1]ssim=stats_file=-:shortest=1"])
    process = _run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-threads", "2", "-i", str(source), "-threads", "2",
                    "-i", str(target), "-filter_complex_threads", "1", "-filter_complex", graph, "-an", "-f", "null", "-"])
    values = [float(value) for value in re.findall(r"\bAll:([0-9.]+)", process.stdout)]
    expected = target_range[1] - target_range[0]
    average, minimum = (sum(values) / len(values), min(values)) if values else (0, 0)
    return _check({"all_requested_frames_compared": process.returncode == 0 and not process.stderr and len(values) == expected,
                   "same_pictures_up_to_reencoding_tolerance": average > .99 and minimum > .97},
                  source_frames=source_range, sample_frames=target_range, compared_frames=len(values),
                  min_ssim=minimum, mean_ssim=round(average, 6), crop=crop or None,
                  reference_repeated_for_reading=repeat_source, error=process.stderr[-900:] or None)


def _reading(folder: Path, target: Path, baseline_frames: dict, market: dict) -> dict:
    proof = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    read = proof["july1_close_read"]
    start, end = read["new_clip_local_full_alpha_end_exclusive"]
    applied = read["new_clip_local_frames_end_exclusive"]
    roles = read["overlay_text_roles"]
    row = baseline_frames[read["repeated_source_state_frame"]]
    july1, top = market["2015-07-01"], market["2015-06-03"]["close"]
    frozen_cut = [baseline_frames[frame] for frame in range(START + 454, START + 480)]
    expected_pieces = [
        ("baseline", [0, 270], [0, 270]), ("signed", [0, 120], [270, 390]),
        ("july1", [0, 56], [390, 446]), ("baseline", [390, 454], [446, 510]),
        ("baseline", [480, 1320], [510, 1350]),
    ]
    recorded_pieces = [(piece["source"], piece["source_clip_frames_end_exclusive"], piece["review_clip_frames_end_exclusive"])
                       for piece in proof["source_clip_sequence"]]
    return _check({
        "manifest_bound_to_the_review_mp4": proof["passed"] and proof["media"]["sha256"] == _sha(target.read_bytes()),
        "published_original_and_signed_inputs_claimed": proof["chronology_source"] == BASELINE and proof["signed_short_source"] == SIGNED,
        "same_ohlc_chart_close_and_rail": read["date"] == row["market_date"] == "2015-07-01"
        and {key: Decimal(str(value)) for key, value in read["ohlc"].items()} == july1
        and Decimal(str(row["market_close"])) == july1["close"]
        and read["candle_index"] == row["last_eligible_candle_index"]
        and Decimal(str(read["drawdown_percent_vs_3982_25"])) == ((july1["close"] / top - 1) * 100).quantize(Decimal(".01")),
        "one_factual_market_caption_no_policy_copy_or_overlap": read["close_copy"] == "7月1日 · 收盘 2,759.41"
        and read["market_focus"] == "L1_MARKET" and len(roles) == 1 and roles[0]["role"] == "market_close_reading"
        and all(read["checks"].values()),
        "50_full_alpha_frames": applied == [390, 446] and (start, end) == STABLE and roles[0]["alpha"] == 1,
        "precise_source_frame_map_and_b09_b10_entry": recorded_pieces == expected_pieces
        and proof["b09_and_b10_local_start_frames"] == {"B09": 510, "B10": 990}
        and proof["july2_and_july3_first_arrival_local_frames"] == {"2015-07-02": 450, "2015-07-03": 459},
        "only_26_frames_of_steady_7_3_hold_displaced": all(
            item["market_date"] == "2015-07-03" and item["market_close"] == 2605.28
            and item["overlay"]["caption_lines"] == ["7月3日 · 收盘 2,605.28"] for item in frozen_cut
        ) and proof["july3_close_full_alpha_clip_frames_end_exclusive"] == [465, 510],
    }, copy=read["close_copy"], full_read_local_frames_end_exclusive=[start, end], full_read_seconds=(end - start) / FPS,
        phone_nominal_font_px=roles[0]["phone_size_px"], retained_july3_full_read_seconds=1.5,
        retained_drawdown_percent=read["drawdown_percent_vs_3982_25"])


def _implementation(root: Path, baseline_bytes: bytes, signed_bytes: bytes, baseline_frames: dict, market: dict) -> dict:
    folder = root / "implementation"
    target = folder / "phone-390.mp4"
    probe = _probe(target, TARGET_FRAMES)
    with TemporaryDirectory(prefix="pinned-inputs-", dir=root / "qa") as temp:
        old, signed = (Path(temp) / name for name in ("baseline.mp4", "signed.mp4"))
        old.write_bytes(baseline_bytes)
        signed.write_bytes(signed_bytes)
        pixels = _decode_hashes(target)
        signed_pixels = _decode_hashes(signed)
        checks = {"media": probe, "signed_clip": _pixel_section(signed_pixels, pixels[slice(*SIGNED_LOCAL)],
                                                               "all_120_signed_decoded_frames_exact")}
        for name, source_frames, output_frames in (
            ("before_signed_clip", (0, 270), (0, 270)),
            ("july2_and_july3_catchup", (390, 454), (446, 510)),
            ("b09_and_b10_picture_and_timing", (480, 1320), (510, 1350)),
        ):
            checks[name] = _similarity(old, source_frames, target, output_frames)
        checks["july1_chart_hold"] = _similarity(signed, (119, 120), target, STABLE, crop="390:494:0:200", repeat_source=True)
        checks["july1_stable_picture"] = _similarity(target, (STABLE[0], STABLE[0] + 1), target, STABLE, repeat_source=True)
    checks["july1_reading"] = _reading(folder, target, baseline_frames, market)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    market = _market(args.repo)
    baseline, original_bytes, signed_bytes, baseline_frames = _baseline(args.repo, market)
    sections = {"baseline": baseline}
    if not args.baseline_only:
        sections.update(_implementation(args.root, original_bytes, signed_bytes, baseline_frames, market))
    report = _check({key: result["passed"] for key, result in sections.items()}, sections=sections,
                    scope="read-only native decoded-frame, frozen OHLC, and timing checks; separate from 1× viewing")
    out = args.out or args.root / "qa" / ("baseline.json" if args.baseline_only else "technical_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["checks"], ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
