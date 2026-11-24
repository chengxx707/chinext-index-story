"""Restore B08–B10 around the signed B08 clip and hold the genuine July 1 close."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image


SIGNED = "aa7ee0aeebf9861ceecbc889ce13898e24063cb5"
BASE = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
VISUAL = "editorial/2015/director/visual-tests"
B08_SOURCE_SHA = "03238d2f642ee8e1cc6ea794e6f2cdeff5a154a858c7b8d9711021066da771d7"
BASE_SOURCE_SHA = "713b9c0ff005f4a52fe6c72d6df5121bc2da5c3820d4cea23220e18b306b0ae1"
WIDTH, HEIGHT, FPS = 390, 694, 30
BYTES_PER_FRAME = WIDTH * HEIGHT * 3 // 2
JULY1 = "2015-07-01"
HELD_SOURCE_FRAME = 2669
HOLD_FRAME_COUNT = 56
FADE_IN, FADE_OUT = 4, 2
HOLD_START_LOCAL = 390
HOLD_END_LOCAL = HOLD_START_LOCAL + HOLD_FRAME_COUNT
ASSEMBLED_FRAMES = 1350
FRAME_PIECES = (
    ("baseline", 0, 270),
    ("signed", 0, 120),
    ("july1", 0, HOLD_FRAME_COUNT),
    ("baseline", 390, 454),
    ("baseline", 480, 1320),
)


def file_sha(path):
    with path.open("rb") as stream:
        digest = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob(root, commit, path):
    return subprocess.check_output(["git", "-C", str(root), "show", f"{commit}:{path}"])


def run_media(*args, capture=False, data=None):
    return subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                           "-y", "-threads", "2", *args], input=data, check=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def import_signed_renderer(repo, work):
    script = work / "render_signed_b08.py"
    script.write_bytes(git_blob(repo, SIGNED, f"{VISUAL}/v1.0.2-selected/tools/render_b08.py"))
    spec = importlib.util.spec_from_file_location("render_signed_b08", script)
    if spec is None or spec.loader is None:
        raise ValueError("Prior, signed B08 renderer is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def july1_data(repo):
    with (repo / "data/cyb_daily.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = csv.DictReader(stream)
        for row in rows:
            if row["date"] == JULY1:
                fields = {key: Decimal(row[key]) for key in ("open", "high", "low", "close")}
                assert fields["close"] == Decimal("2759.41")
                return fields
    raise ValueError("Missing July 1 in frozen OHLC")


def write_reading_hold(repo, work, raw):
    inputs = work / "pinned-scene"
    inputs.mkdir()
    signed = import_signed_renderer(repo, work)
    scene, hashes = signed.load_scene(repo, inputs, None)
    from visual_overlay import Caption

    prices = july1_data(repo)
    copy = f"7月1日 · 收盘 {prices['close']:,.2f}"
    original = scene._overlay
    diagnostics = {}
    contrast = [0.25, 0.43, 0.65, 0.87, *([1.0] * (HOLD_FRAME_COUNT - FADE_IN - FADE_OUT)), 0.65, 0.3]

    def with_reading_frame(opacity):
        def draw(image, drawer, state, cue, frame, t2_state=None):
            original_result = original(image, drawer, state, cue, frame, t2_state=t2_state)
            if original_result["text_visible"]:
                raise ValueError("July 1 reading would cover an existing foreground caption")
            layer = drawer._new()
            start = len(drawer.text_boxes)
            caption = Caption(drawer, layer, opacity)
            caption.text(copy, 69, 173, 32, role="market_close_reading", width=492, bold=True)
            image.alpha_composite(layer)
            return {
                **original_result,
                "caption_boxes": drawer.text_boxes[start:],
                "caption_lines": caption.lines,
                "text_roles": caption.roles,
                "text_visible": True,
            }

        scene._overlay = draw
        pixels, report = scene.frame(HELD_SOURCE_FRAME)
        expected_drawdown = float(prices["close"] / Decimal("3982.25") - 1)
        if (pixels.size != (1080, 1920) or report["layout_errors"] or report["active_track_count"] != 1
                or not report["no_future_candles"] or report["market_date"] != JULY1
                or report["market_close"] != float(prices["close"]) or report["primary_focus"] != "L1_MARKET"
                or abs(report["stage_value"] - expected_drawdown) > 1e-8):
            raise ValueError("July 1 overlay or frozen market state failed verification")
        image = pixels.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        diagnostics[opacity] = report
        return image.tobytes()

    cached = {opacity: with_reading_frame(opacity) for opacity in sorted(set(contrast))}
    run_media("-f", "rawvideo", "-pix_fmt", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
              "-framerate", str(FPS), "-i", "pipe:0", "-pix_fmt", "yuv420p", "-f", "rawvideo", str(raw),
              data=b"".join(cached[value] for value in contrast))
    report = diagnostics[1.0]
    return {
        "date": JULY1,
        "source_frames_with_market_row_end_exclusive": [2666, 2674],
        "repeated_source_state_frame": HELD_SOURCE_FRAME,
        "ohlc": {key: float(value) for key, value in prices.items()},
        "close_copy": copy,
        "market_focus": report["primary_focus"],
        "candle_index": report["last_eligible_candle_index"],
        "drawdown_percent_vs_3982_25": round(100 * report["stage_value"], 2),
        "overlay_text_roles": report["overlay"]["text_roles"],
        "new_clip_local_frames_end_exclusive": [HOLD_START_LOCAL, HOLD_END_LOCAL],
        "new_clip_local_full_alpha_end_exclusive": [HOLD_START_LOCAL + FADE_IN, HOLD_END_LOCAL - FADE_OUT],
        "displaced_in_existing_44s_excerpt": "July 1 had 8 trading-row frames; no dedicated July 1 full reading cue",
        "checks": {"no_foreground_collision": True, "no_future_candles": True, "one_active_rail": True},
        "scene_inputs_sha256": hashes,
    }


def decode(media, raw):
    run_media("-xerror", "-i", str(media), "-map", "0:v:0", "-an", "-pix_fmt", "yuv420p",
              "-f", "rawvideo", str(raw))
    size = raw.stat().st_size
    if size % BYTES_PER_FRAME:
        raise ValueError(f"Partial decoded phone frame in {media.name}")
    return size // BYTES_PER_FRAME


def append_piece(source, target, start, stop):
    amount = (stop - start) * BYTES_PER_FRAME
    with source.open("rb") as read:
        read.seek(start * BYTES_PER_FRAME)
        while amount:
            data = read.read(min(amount, BYTES_PER_FRAME * 16))
            if not data:
                raise ValueError(f"Early EOF in selected piece {source.name}")
            target.write(data)
            amount -= len(data)


def encode(raw, out, encoding):
    run_media("-f", "rawvideo", "-pix_fmt", "yuv420p", "-video_size", f"{WIDTH}x{HEIGHT}",
              "-framerate", str(FPS), "-i", str(raw), "-map", "0:v:0", "-an", "-c:v", "libx264",
              "-threads", "3", "-preset", "veryfast", *encoding, "-movflags", "+faststart",
              "-video_track_timescale", "15360", str(out))


def probe(media):
    response = subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                                        "stream=codec_type,codec_name,profile,pix_fmt,width,height,level,"
                                        "avg_frame_rate,nb_read_frames,duration,time_base:"
                                        "frame=best_effort_timestamp", "-show_frames", "-show_streams",
                                        "-of", "json", str(media)])
    payload = json.loads(response)
    streams = payload["streams"]
    if len(streams) != 1:
        raise ValueError("Review requires one silent video stream")
    stream = streams[0]
    if (stream["codec_type"], stream["codec_name"], stream["pix_fmt"], stream["width"], stream["height"],
            stream["avg_frame_rate"], int(stream["nb_read_frames"]), float(stream["duration"])) != (
            "video", "h264", "yuv420p", WIDTH, HEIGHT, "30/1", ASSEMBLED_FRAMES, ASSEMBLED_FRAMES / FPS):
        raise ValueError(f"Unexpected review format: {stream}")
    if stream["time_base"] != "1/15360" or [
        int(frame["best_effort_timestamp"]) for frame in payload["frames"]
    ] != [frame * 512 for frame in range(ASSEMBLED_FRAMES)]:
        raise ValueError("The reconstructed video has gaps or duplicates in its presentation clock")
    return stream


def similarity(raw, media, start, end):
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-threads", "2", "-i", str(media),
         "-f", "rawvideo", "-pix_fmt", "yuv420p", "-video_size", f"{WIDTH}x{HEIGHT}",
         "-framerate", str(FPS), "-i", str(raw), "-lavfi",
         f"[0:v]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS[a];"
         f"[1:v]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS[b];[a][b]ssim",
         "-f", "null", "-"], check=True, capture_output=True, text=True,
    )
    line = next(line for line in result.stderr.splitlines() if " All:" in line)
    return float(line.split(" All:")[1].split()[0])


def run(repo, out):
    with TemporaryDirectory(prefix="chinext-b08-context-") as temp:
        work = Path(temp)
        source_paths = {
            "baseline": (BASE, f"{VISUAL}/v1.0.2/B08-B10/phone-390.mp4", BASE_SOURCE_SHA, 1320),
            "signed": (SIGNED, f"{VISUAL}/v1.0.2-selected/b08/phone-390.mp4", B08_SOURCE_SHA, 120),
        }
        raw_sources = {}
        for name, (commit, path, expected_sha, expected_frames) in source_paths.items():
            media = work / f"{name}.mp4"
            media.write_bytes(git_blob(repo, commit, path))
            if file_sha(media) != expected_sha:
                raise ValueError(f"Unexpected source asset contents: {name}")
            decoded = work / f"{name}.yuv"
            if decode(media, decoded) != expected_frames:
                raise ValueError(f"Unexpected source frame count: {name}")
            raw_sources[name] = decoded

        raw_sources["july1"] = work / "july1.yuv"
        hold = write_reading_hold(repo, work, raw_sources["july1"])
        local_ranges = []
        local = 0
        assembled = work / "assembled.yuv"
        with assembled.open("wb") as target:
            for label, start, stop in FRAME_PIECES:
                append_piece(raw_sources[label], target, start, stop)
                local_end = local + stop - start
                local_ranges.append({"source": label, "source_clip_frames_end_exclusive": [start, stop],
                                     "review_clip_frames_end_exclusive": [local, local_end]})
                local = local_end
        if local != ASSEMBLED_FRAMES:
            raise ValueError("Unexpected local representative timing")

        exact = work / "lossless-reference.mp4"
        encode(assembled, exact, ["-qp", "0"])
        comparison = work / "roundtrip.yuv"
        if decode(exact, comparison) != ASSEMBLED_FRAMES or file_sha(comparison) != file_sha(assembled):
            raise ValueError("Lossless reconstruction did not preserve the assembled source pixels")
        exact_reference_sha = file_sha(exact)
        comparison.unlink()

        for name, start, stop in (("prefix", 0, 270), ("suffix", 390, ASSEMBLED_FRAMES)):
            part = work / f"{name}.yuv"
            with part.open("wb") as target:
                append_piece(assembled, target, start, stop)
            encode(part, work / f"{name}.mp4", ["-profile:v", "high", "-level:v", "3.0", "-crf", "14"])
            part.unlink()

        concat = work / "cuts.txt"
        concat.write_text("file prefix.mp4\nduration 9.000000\nfile signed.mp4\nduration 4.000000\n"
                          "file suffix.mp4\nduration 32.000000\n", encoding="ascii")
        phone = out / "phone-390.mp4"
        run_media("-f", "concat", "-safe", "1", "-i", str(concat), "-map", "0:v:0", "-an", "-c:v", "copy",
                  "-movflags", "+faststart", "-video_track_timescale", "15360", str(phone))
        phone_probe = probe(phone)
        if phone_probe["profile"] != "High" or phone_probe["level"] != 30:
            raise ValueError("Unexpected review phone codec profile")
        if decode(phone, comparison) != ASSEMBLED_FRAMES:
            raise ValueError("Review phone MP4 did not decode its full duration")

        approval = work / "signed-roundtrip.yuv"
        with approval.open("wb") as target:
            append_piece(comparison, target, 270, 390)
        signed_pixel_sha = file_sha(raw_sources["signed"])
        if file_sha(approval) != signed_pixel_sha:
            raise ValueError("The phone release changed pixels inside the signed B08 excerpt")

        similarities = [
            {**piece, "decoded_yuv_ssim_vs_exact":
                similarity(assembled, phone, *piece["review_clip_frames_end_exclusive"])}
            for piece in local_ranges
        ]
        if any(piece["decoded_yuv_ssim_vs_exact"] < 0.99 for piece in similarities):
            raise ValueError("A phone region falls below the controlled decoded comparison")

    result = {
        "passed": True,
        "chronology_source": BASE,
        "signed_short_source": SIGNED,
        "approved_original_sources_sha256": {label: entry[2] for label, entry in source_paths.items()},
        "signed_entire_120_frame_short_is_stream_copied_and_bit_exact_in_phone_export": True,
        "signed_decoded_120_frames_sha256": signed_pixel_sha,
        "benchmark_lossless_build_sha256": exact_reference_sha,
        "all_reused_baseline_frames_are_bit_exact_in_benchmark_build": True,
        "phone_prefix_and_suffix_are_reencoded": True,
        "decoded_yuv_ssim_vs_benchmark_by_interval": similarities,
        "scope": "B08–B10 review only. Source global frames still use b0d71e8. No new whole-candidate timeline.",
        "source_global_frames_end_exclusive": [2280, 3600],
        "clip_local_duration_seconds": ASSEMBLED_FRAMES / FPS,
        "source_clip_sequence": local_ranges,
        "local_delay_after_B08_in_frames": 30,
        "july1_close_read": hold,
        "july2_and_july3_first_arrival_local_frames": {"2015-07-02": 450, "2015-07-03": 459},
        "july3_close_full_alpha_clip_frames_end_exclusive": [465, 510],
        "b09_and_b10_local_start_frames": {"B09": 510, "B10": 990},
        "media": {"name": phone.name, "sha256": file_sha(phone), "probe": phone_probe,
                  "full_decode_and_regular_presentation_timestamps_passed": True},
    }
    (out / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"encoded_frames": ASSEMBLED_FRAMES, "phone": result["media"]}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo, out = args.repo_root.resolve(), args.out.resolve()
    if not out.is_relative_to(repo / "output") or out == repo / "output":
        parser.error("Use a separate output directory below the repository's output/")
    out.mkdir(parents=True, exist_ok=True)
    run(repo, out)


if __name__ == "__main__":
    main()
