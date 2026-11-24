"""Restore the approved phone-only B01–B02 block without re-encoding the selected B01 prefix."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from importlib import import_module
from itertools import chain
import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from PIL import Image

from approved_intro import apply_approved_intro_push


PREFIX_SHA256 = "bd0f8594c50ba5986362ae02e658616c5126616c773d7c2df018cb05145b74ee"
BASELINE_HELPERS = {
    "render_visual.py": "f62ed0de8f4f6ddd5090578402e0791c36d90036b5fe177612df07a83ed49c79",
    "visual_overlay.py": "d9d77bd6f7ac0c9b88bed6d82b1aadfdbbb172bfe9ef546686227e8295214320",
}
PREFIX_END, BLOCK_END = 360, 540
WIDTH, HEIGHT, FPS = 390, 694, 30
_scene = None


def _load(path):
    return json.loads(path.read_bytes())


def _build_scene(project, tools, candidate, legacy, runtime):
    for name, digest in BASELINE_HELPERS.items():
        if sha256((tools / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Unexpected checksum for baseline helper {name}")
    sys.path.insert(0, str(tools.resolve()))
    renderer = import_module("render_visual")
    segments = [dict(segment, timeline=_load(legacy / f"{segment['id']}.json"))
                for segment in _load(legacy / "segments.json")]
    scene = renderer.build_scene(project, _load(candidate), segments, runtime, width=1080)
    apply_approved_intro_push(scene)
    if any(scene.cue_at(frame)["beat_id"] != "B02" for frame in range(PREFIX_END, BLOCK_END)):
        raise ValueError("The continuation must consist exclusively of the approved B02 range")
    return scene


def _phone_frame(frame):
    image, result = _scene.frame(frame)
    if (image.size != (1080, 1920) or result["layout_errors"] or not result["no_future_candles"]
            or result["active_track_count"] != 1):
        raise ValueError(f"Unexpected layout, chart, or rail at continuation frame {frame}")
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).tobytes()


def _continuation(pool=None):
    if pool is None:
        yield from map(_phone_frame, range(PREFIX_END, BLOCK_END))
        return
    for cursor in range(PREFIX_END, BLOCK_END, 24):
        yield from pool.map(_phone_frame, range(cursor, min(cursor + 24, BLOCK_END)), chunksize=2)


def _decoded_hashes(path):
    command = ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(path),
               "-map", "0:v:0", "-an", "-f", "framemd5", "-"]
    decoded = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    return [line.rsplit(",", 1)[-1].strip() for line in decoded.splitlines() if not line.startswith("#")]


def restore(prefix, output, workers):
    from chinext_v6.renderer import encode_frames
    from chinext_v6.scene_cache import inspect_media

    if output.exists() or output.suffix != ".mp4":
        raise ValueError("Choose a new .mp4 destination")
    if sha256(prefix.read_bytes()).hexdigest() != PREFIX_SHA256:
        raise ValueError("The prefix must match the approved 37dfb77 B01-B clip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as directory:
        work = Path(directory)
        tail = work / "tail.mp4"
        if workers == 1:
            count = encode_frames(_continuation(), WIDTH, HEIGHT, FPS, tail, preset="veryfast", crf=20)
        else:
            context = multiprocessing.get_context("fork")
            with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
                frames = _continuation(pool)
                first = next(frames)
                count = encode_frames(chain((first,), frames), WIDTH, HEIGHT, FPS, tail, preset="veryfast", crf=20)
        if count != BLOCK_END - PREFIX_END:
            raise ValueError("The B02 continuation must contain exactly 180 frames")
        (work / "head.mp4").symlink_to(prefix.resolve())
        listing = work / "clips.ffconcat"
        listing.write_text("ffconcat version 1.0\nfile head.mp4\nfile tail.mp4\n", encoding="ascii")
        joined = work / "joined.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-f", "concat", "-safe", "0",
                        "-i", str(listing), "-map", "0:v:0", "-an", "-c:v", "copy", "-movflags",
                        "+faststart", str(joined)], check=True)
        probe = inspect_media(joined, width=WIDTH, height=HEIGHT, fps=FPS, expected_frames=BLOCK_END,
                              full_decode=True)
        if not probe["passed"] or _decoded_hashes(joined) != _decoded_hashes(prefix) + _decoded_hashes(tail):
            raise ValueError("The joined phone block failed frame-preservation checks")
        joined.replace(output)


def main():
    global _scene
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    for name in ("baseline-tools", "runtime", "candidate", "legacy-dir", "prefix", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=4)
    args = parser.parse_args()
    _scene = _build_scene(args.repo_root.resolve(), args.baseline_tools, args.candidate, args.legacy_dir, args.runtime)
    restore(args.prefix, args.output, args.workers)


if __name__ == "__main__":
    main()
