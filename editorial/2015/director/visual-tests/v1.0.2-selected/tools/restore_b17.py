#!/usr/bin/env python3
"""Rebuild the selected B17-B in its complete 56-second phone context."""

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from b17_variant import make_b17_b


BASE = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
SELECT = "37dfb77e102909788cc2f0b4428319f4ae1ecc32"
EDITORIAL = "editorial/2015/director/visual-tests"
INPUTS = {
    "context": (BASE, f"{EDITORIAL}/v1.0.2/B16-B18/phone-390.mp4",
                "6846262ca3f6f6b9f2aa5686d602164f1d98f453567654346544de5765324607"),
    "approved_b17": (SELECT, f"{EDITORIAL}/v1.0.2-ab/B17-B.mp4",
                     "5d131d03a587c94fbaf6c006cfe7490a0679de15ebc554cd2a64a818207becef"),
    "candidate": (BASE, f"{EDITORIAL}/v1.0.2/candidate.json",
                  "c9dfa6638885d55b712f0546f55df695b1f29c66a543c1733255bbd46084e86a"),
}
EXPECTED_CANDIDATE = "746e943a5938bf7a68e1273829ece1843b2364e77840117800157318ad4b36d6"
WIDTH, HEIGHT, FPS = 390, 694, 30
Y_BYTES = WIDTH * HEIGHT
FRAME_BYTES = Y_BYTES * 3 // 2
CUTS = (360, 1020)
FRAME_COUNT = 1680


def _checked_git_blob(repo, reference, path, expected):
    blob = subprocess.check_output(["git", "show", f"{reference}:{path}"], cwd=repo)
    digest = sha256(blob).hexdigest()
    if digest != expected:
        raise ValueError(f"Pinned input mismatch {reference}:{path} ({digest})")
    return blob


def _json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)


def _media_probe(path):
    fields = "stream=codec_name,profile,level,codec_type,width,height,pix_fmt,r_frame_rate,time_base:frame=best_effort_timestamp"
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", fields,
        "-show_frames", "-show_streams", "-of", "json", str(path),
    ]))
    if len(probe["streams"]) != 1:
        raise ValueError("Expected one video stream and no audio")
    stream = probe["streams"][0]
    if (
        (stream["codec_type"], stream["codec_name"], stream["profile"], stream["level"], stream["pix_fmt"])
        != ("video", "h264", "High", 30, "yuv420p")
        or (stream["width"], stream["height"], Fraction(stream["r_frame_rate"])) != (WIDTH, HEIGHT, FPS)
    ):
        raise ValueError(f"Unexpected phone media: {stream}")
    time_base = Fraction(stream["time_base"])
    timestamps = [int(frame["best_effort_timestamp"]) for frame in probe["frames"]]
    if any(pts * time_base != Fraction(index, FPS) for index, pts in enumerate(timestamps)):
        raise ValueError("Phone media lacks a contiguous 30 fps timestamp sequence")
    return {**stream, "decoded_frames": len(timestamps),
            "duration_seconds": len(timestamps) / FPS, "contiguous_pts": True}


def _decoded_frames(path, watched):
    args = ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(path),
            "-map", "0:v:0", "-an", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
    digests, pictures = [], {}
    with tempfile.TemporaryFile() as diagnostics:
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=diagnostics) as process:
            while picture := process.stdout.read(FRAME_BYTES):
                if len(picture) != FRAME_BYTES:
                    raise ValueError(f"Short decoded frame in {path.name}")
                if len(digests) in watched:
                    pictures[len(digests)] = picture[:Y_BYTES]
                digests.append(sha256(picture).digest())
            if process.wait() != 0:
                diagnostics.seek(0)
                raise RuntimeError(diagnostics.read().decode("utf-8", errors="replace"))
    return digests, pictures


def _luma_difference(left, right):
    differences = [abs(a - b) for a, b in zip(left, right, strict=True)]
    return {
        "mean_absolute_8bit": round(sum(differences) / len(differences), 4),
        "fraction_abs_gt_20": round(sum(value > 20 for value in differences) / len(differences), 6),
    }


def _context_cut(work, start, stop, name):
    _run([
        "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", "context.mp4", "-an",
        "-vf", f"trim=start_frame={start}:end_frame={stop},setpts=PTS-STARTPTS,setsar=1",
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "3.0", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "14", "-threads", "2", "-video_track_timescale", "15360",
        "-movflags", "+faststart", name,
    ], cwd=work)


def _check_selected_candidate(baseline):
    rendered = _json_bytes(make_b17_b(json.loads(baseline)))
    if sha256(rendered).hexdigest() != EXPECTED_CANDIDATE:
        raise ValueError("Integration candidate differs from the config used to render the selected B17-B clip")
    return rendered


def _verify_t2(candidate):
    cues = {row["shot_id"]: row for row in candidate["cues"]}
    records = []
    for shot, event_id, anchor, reading in [
        ("V102-B17-ETF", "E-SEP-ETF-01", "2015-09-25", [6132, 6258]),
        ("V102-B17-TURNOVER", "E-SEP-TURNOVER-01", "2015-09-28", [6354, 6456]),
    ]:
        cue = cues[shot]
        event = cue["event_clock"]
        if (
            event["event_id"] != event_id or cue["primary_anchor"]["date"] != anchor
            or cue["camera_story_clock"]["reading_window"] != reading
        ):
            raise ValueError(f"Approved T2 binding changed: {event_id}")
        records.append({
            "metric_id": event_id, "market_date": anchor, "global_reading_frames": reading,
            "block_reading_frames": [index - 5520 for index in reading],
            "stable_seconds": (reading[1] - reading[0]) / FPS,
            "source_ids": cue["source_ids"], "global_fade_frames": cue["camera_story_clock"]["exit_window"],
        })
    if records[0]["global_fade_frames"][1] > cues["V102-B17-TURNOVER"]["text_cue"]["in_frame"]:
        raise ValueError("Two T2 indicators must have separate display intervals.")
    return records


def restore(repo, out):
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".restore-b17-", dir=out) as folder:
        work = Path(folder)
        for key in ("context", "approved_b17"):
            (work / f"{key}.mp4").write_bytes(_checked_git_blob(repo, *INPUTS[key]))
        candidate_data = _check_selected_candidate(_checked_git_blob(repo, *INPUTS["candidate"]))
        candidate = json.loads(candidate_data)
        blocks = {b["id"]: (b["start_frame"], b["end_frame_exclusive"]) for b in candidate["beat_ranges"]}
        if [blocks[key] for key in ("B16", "B17", "B18")] != [(5520, 5880), (5880, 6540), (6540, 7200)]:
            raise ValueError("Representative block or selected B17 no longer fits the approved scope")
        t2 = _verify_t2(candidate)

        _context_cut(work, 0, CUTS[0], "before.mp4")
        _context_cut(work, CUTS[1], FRAME_COUNT, "after.mp4")
        (work / "cuts.txt").write_text(
            "file before.mp4\nduration 12.000000\n"
            "file approved_b17.mp4\nduration 22.000000\n"
            "file after.mp4\nduration 22.000000\n", encoding="ascii",
        )
        final = work / "B16-B18-selected-390.mp4"
        _run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-f", "concat", "-safe", "1",
              "-i", "cuts.txt", "-map", "0:v:0", "-an", "-c:v", "copy", "-movflags", "+faststart",
              "-video_track_timescale", "15360", final.name], cwd=work)
        media = _media_probe(final)
        if media["decoded_frames"] != FRAME_COUNT:
            raise ValueError(f"Representative block is missing frames: {media}")
        watched = {cut + delta for cut in CUTS for delta in (-1, 0)}
        decoded, joined = _decoded_frames(final, watched)
        selected, selected_pictures = _decoded_frames(work / "approved_b17.mp4", {0, 659})
        _, baseline = _decoded_frames(work / "context.mp4", watched)
        if len(decoded) != FRAME_COUNT or len(selected) != 660 or decoded[CUTS[0]:CUTS[1]] != selected:
            raise ValueError("The restored B17 must be decode-identical to the selected B17-B MP4.")

        seams = []
        for cut, expected_source in ((CUTS[0], selected_pictures[0]), (CUTS[1], selected_pictures[659])):
            selected_side = cut if cut == CUTS[0] else cut - 1
            context_side = cut - 1 if cut == CUTS[0] else cut
            selected_vs_baseline = _luma_difference(expected_source, baseline[selected_side])
            context_reencode = _luma_difference(joined[context_side], baseline[context_side])
            baseline_jump = _luma_difference(baseline[cut - 1], baseline[cut])
            restored_jump = _luma_difference(joined[cut - 1], joined[cut])
            if restored_jump["mean_absolute_8bit"] > baseline_jump["mean_absolute_8bit"] + 1.5:
                raise ValueError(f"Unexpected visual jump at block frame {cut}: {restored_jump}")
            seams.append({
                "block_frame": cut, "global_frame": 5520 + cut, "clip_seconds": cut / FPS,
                "baseline_boundary_difference": baseline_jump, "restored_boundary_difference": restored_jump,
                "selected_boundary_vs_baseline": selected_vs_baseline,
                "context_sample_reencode_difference": context_reencode,
            })

        manifest = {
            "passed": True, "file": final.name, "sha256": sha256(final.read_bytes()).hexdigest(),
            "bytes": final.stat().st_size, "media": media, "global_frame_range": [5520, 7200],
            "selection_commit": SELECT, "input_blobs": {
                key: {"commit": item[0], "path": item[1], "sha256": item[2]}
                for key, item in INPUTS.items()
            },
            "candidate": {"file": "candidate-b17-selected.json", "sha256": EXPECTED_CANDIDATE},
            "construction": "Encode contextual head and tail at CRF 14. Concatenate the three H.264 streams by copy.",
            "approved_b17_decoded_frames_identical": len(selected),
            "verified_t2": t2, "decoded_boundary_pixel_checks": seams,
        }
        final.replace(out / final.name)
        (out / "candidate-b17-selected.json").write_bytes(candidate_data)
        (out / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    manifest = restore(args.repo.resolve(), args.out.resolve())
    print(f"{manifest['file']}: 1680 frames, exact 660-frame B17-B preserved")
    for seam in manifest["decoded_boundary_pixel_checks"]:
        print("Seam", seam["global_frame"], seam["restored_boundary_difference"])


if __name__ == "__main__":
    main()
