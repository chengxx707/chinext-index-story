#!/usr/bin/env python3
"""Render the independent, silent 15-second ending component review."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.ending import EndingDrawer


def validate_media(path, width, height, fps, count):
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                            "format=duration:stream=codec_type,width,height,r_frame_rate,nb_read_frames", "-of", "json", str(path)],
                           capture_output=True, text=True, check=True)
    metadata = json.loads(probe.stdout)
    streams = metadata["streams"]
    video = [s for s in streams if s["codec_type"] == "video"]
    checks = {
        "one_video_stream": len(video) == 1,
        "silent_no_audio_stream": not any(s["codec_type"] == "audio" for s in streams),
    }
    if video:
        stream = video[0]
        numerator, denominator = map(int, stream["r_frame_rate"].split("/"))
        checks.update({"target_dimensions": (stream["width"], stream["height"]) == (width, height),
                       "frame_rate": numerator / denominator == fps,
                       "frame_count": int(stream["nb_read_frames"]) == count,
                       "duration": abs(float(metadata["format"]["duration"]) - count / fps) <= 1 / fps})
    decode = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-xerror", "-threads", "2", "-i", str(path),
                             "-vf", "blackdetect=d=0.1:pic_th=0.98:pix_th=0.02", "-an", "-f", "null", "-"],
                            capture_output=True, text=True)
    black = re.findall(r"black_start:[^\n]+", decode.stderr)
    checks["full_decode"] = decode.returncode == 0
    checks["no_black_intervals"] = not black
    result = {"passed": all(checks.values()), "checks": checks, "black_intervals": black, "probe": metadata}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--keyframes", action="store_true")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/ending_review")
    args = parser.parse_args()
    if args.width < 360 or args.width % 2 or round(args.width * 16 / 9) % 2:
        parser.error("width must produce even 9:16 video dimensions")
    if not args.video and not args.keyframes:
        args.keyframes = True
    drawer = EndingDrawer(ROOT, args.width)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    diagnostics = []
    times = [.5, 2, 4.5, 6.5, 9.5, 11.5, 14.5]
    if args.keyframes:
        frames = out / "keyframes"
        frames.mkdir(exist_ok=True)
        for t in times:
            drawer.render(t).save(frames / f"ending_{t:04.1f}.png")
            diagnostics.append(drawer.diagnostics(t))
        from PIL import Image, ImageDraw
        sheet = Image.new("RGB", (1080, 2 * 682), (4, 9, 15))
        for i, t in enumerate([.5, 4.5, 6.5, 9.5, 11.5, 14.5]):
            frame = drawer.render(t).resize((360, 640))
            x, y = i % 3 * 360, i // 3 * 682
            sheet.paste(frame, (x, y))
            ImageDraw.Draw(sheet).text((x+12, y+650), f"{t:.1f}s", fill="white")
        sheet.save(out / "review_contact.jpg", quality=94)
        (out / "layout_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2))
        if any(d["out_of_bounds"] for d in diagnostics):
            raise RuntimeError("Ending text has out-of-bounds coordinates")
    if args.video:
        from chinext_v6.renderer import production_provenance
        provenance = production_provenance(ROOT)
        target = out / "chinext_ending_components.mp4"
        partial = out / "chinext_ending_components.partial.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{drawer.width}x{drawer.height}", "-r", str(drawer.fps), "-i", "-", "-an", "-c:v", "libx264",
               "-threads", "2", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial)]
        total = round(drawer.duration * drawer.fps)
        start = time.monotonic()
        with (out / "ffmpeg.log").open("wb") as log:
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
            try:
                for n in range(total):
                    process.stdin.write(drawer.render(n / (total - 1) * drawer.duration).tobytes())
                    if n % 90 == 0:
                        print(f"ending {n}/{total}", flush=True)
                process.stdin.close()
                if process.wait():
                    raise RuntimeError("FFmpeg failed; see ffmpeg.log")
            except BaseException:
                process.kill()
                process.wait()
                raise
        partial.replace(target)
        source_paths = [ROOT / "data/cyb_daily.csv", ROOT / "data/materials/创业板指_成分股_20261110.csv"]
        sources_stable = production_provenance(ROOT) == provenance
        manifest = {"run_id": uuid.uuid4().hex, "video": str(target), "width": drawer.width, "height": drawer.height, "fps": drawer.fps,
                    "duration": drawer.duration, "frame_count": total, "audio": False,
                    **provenance, "sources_stable_during_render": sources_stable,
                    "elapsed_seconds": round(time.monotonic()-start, 2),
                    "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}}
        (out / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        media = validate_media(target, drawer.width, drawer.height, drawer.fps, total)
        media["checks"]["sources_stable_during_render"] = sources_stable
        media["passed"] = all(media["checks"].values())
        (out / "media_checks.json").write_text(json.dumps(media, ensure_ascii=False, indent=2))
        if not media["passed"]:
            raise RuntimeError("Ending media or source stability checks failed; see media_checks.json")
        print(target)


if __name__ == "__main__":
    main()
