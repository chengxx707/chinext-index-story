#!/usr/bin/env python3
"""Render and validate the isolated 2015 editorial candidate against its cue sheet."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chinext_v6.editorial_clock import EditorialClock
from chinext_v6.editorial_overlay import draw_cue
from chinext_v6.film_renderer import _ProjectionDrawer, _black_check, _write_json
from chinext_v6.renderer import encode_frames
from chinext_v6.scene_cache import file_sha256, inspect_media

RELEASE = ROOT / "editorial/2015/releases/v1.0.1"
OUTPUT = ROOT / "output/wf-02-2015-gpt-v1.0.1"
PHOTO_ID = "IMG-20150824-01"
SCENE = None


class EditorialScene:
    def __init__(self, release: Path, width: int, photo_path: Path | None = None):
        self.clock = EditorialClock(ROOT, release, width, photo_available=photo_path is not None)
        self.drawer = _ProjectionDrawer(self.clock, ROOT / "assets")
        self.background = self.drawer.background.copy()
        self.background.alpha_composite(self.drawer.grid)
        self.photo = None
        if photo_path is not None:
            manifest = json.loads((release / "photo_manifest.json").read_bytes())
            asset = next(item for item in manifest["assets"] if item["asset_id"] == PHOTO_ID)
            if file_sha256(photo_path) != asset["sha256"] or photo_path.stat().st_size != asset["bytes"]:
                raise ValueError("Documentary photo does not match the released asset")
            with Image.open(photo_path) as photo:
                if list(photo.size) != asset["size"] or photo.format != "JPEG":
                    raise ValueError("Documentary photo dimensions or format do not match")
                self.photo = photo.convert("RGB")
        self.last_layout = {}

    def frame(self, number: int) -> Image.Image:
        state, cue = self.clock.states[number], self.clock.cue_at(number)
        drawer = self.drawer
        drawer.projection = self.clock.projections[number]
        drawer.text_boxes, drawer.critical_diagnostics, drawer.active_track_count = [], [], 0
        image = self.background.copy()
        drawer._chart(image, state)
        image.alpha_composite(drawer.earth_layer)
        drawer._world(image, state)
        drawer._header(image, state)
        drawer._rail(image, state)
        drawer._footer(image)
        overlay = draw_cue(image, drawer, state, cue, self.photo)
        boxes = drawer.text_boxes
        out_of_bounds = []
        overlaps = []
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box["bbox"]
            if not (0 <= x1 < x2 <= drawer.w and 0 <= y1 < y2 <= drawer.h):
                out_of_bounds.append(box)
            for other in boxes[i+1:]:
                a1, b1, a2, b2 = other["bbox"]
                if min(x2, a2) - max(x1, a1) > 1 and min(y2, b2) - max(y1, b1) > 1:
                    overlaps.append([box["id"], other["id"]])
        self.last_layout = {
            "frame": number, "shot_id": cue["shot_id"], "market_date": state.current_date.date().isoformat(),
            "market_close": state.current_close, "stage_mode": state.stage_mode, "stage_value": state.stage_value,
            "active_track_count": drawer.active_track_count, "width": drawer.w, "height": drawer.h,
            "text_boxes": boxes, "out_of_bounds": out_of_bounds, "text_overlaps": overlaps,
            "projection": drawer.projection, "overlay": overlay,
        }
        return image.convert("RGB")


def _start_worker(release: Path, width: int, photo: Path | None):
    global SCENE
    SCENE = EditorialScene(release, width, photo)


def _render_frame(number: int) -> bytes:
    return SCENE.frame(number).tobytes()


def _frames(scene, release, width, photo, workers):
    count = scene.clock.total_frames
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                             initializer=_start_worker, initargs=(release, width, photo)) as pool:
        for start in range(0, count, 48):
            yield from pool.map(_render_frame, range(start, min(start + 48, count)), chunksize=3)
            if start % 480 == 0:
                print(f"Encoded through frame {min(start + 48, count)}/{count}", flush=True)


def _target_frames(release, out, photo):
    scene = EditorialScene(release, 1080, photo)
    path = out / "keyframes"
    path.mkdir(parents=True, exist_ok=True)
    diagnostics = []
    images = []
    critical = {2, 4, 7, 12, 14, 18, 19, 20, 21, 22, 26}
    for index, cue in enumerate(scene.clock.cues):
        text = cue["text_cue"]
        samples = {text["full_alpha_from_frame"], text["out_frame_exclusive"] - 1}
        if index in critical:
            samples.add(cue["primary_anchor"]["hit_frame"])
        for number in sorted(samples):
            image = scene.frame(number)
            result = dict(scene.last_layout)
            diagnostics.append(result)
            if number == text["full_alpha_from_frame"] or number == cue["primary_anchor"]["hit_frame"]:
                name = f"{cue['shot_id']}-f{number:04d}.png"
                image.save(path / name)
                if number == text["full_alpha_from_frame"]:
                    image.thumbnail((162, 288))
                    images.append((image, f"{cue['shot_id']}  {number / 30:.2f}s"))
    for page, start in enumerate(range(0, len(images), 12), 1):
        items = images[start:start + 12]
        sheet = Image.new("RGB", (4 * 162, ((len(items) + 3)//4)*309), "#0a111a")
        pen = ImageDraw.Draw(sheet)
        for offset, (image, label) in enumerate(items):
            x, y = offset % 4 * 162, offset // 4 * 309
            sheet.paste(image, (x, y))
            pen.text((x + 4, y + 290), label, fill="white")
        sheet.save(out / f"keyframe_contact_{page:02d}.jpg", quality=92)
    failures = [row["frame"] for row in diagnostics if row["out_of_bounds"] or row["text_overlaps"]
                or row["active_track_count"] != 1]
    _write_json(out / "layout_diagnostics.json", {"passed": not failures, "failures": failures,
                 "frame_count": len(diagnostics), "frames": diagnostics})
    if failures:
        raise RuntimeError(f"Target keyframe checks failed at frames {failures}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--photo", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--keyframes", action="store_true")
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    if not (args.keyframes or args.video):
        parser.error("Choose --keyframes and/or --video")
    out, release = args.output.resolve(), args.release.resolve()
    if not out.is_relative_to(ROOT / "output") or out == ROOT / "output":
        parser.error("Output must be under output/")
    if args.keyframes:
        _target_frames(release, out, args.photo)
    if args.video:
        scene = EditorialScene(release, 540, args.photo)
        filename = "preview_2015_v1.0.1.mp4" if scene.photo else "preview_2015_v1.0.1_photo_missing.mp4"
        video = out / filename
        count = encode_frames(_frames(scene, release, 540, args.photo, args.workers),
                              540, 960, scene.clock.fps, video, preset="veryfast", crf=20)
        checks = inspect_media(video, width=540, height=960, fps=scene.clock.fps,
                               expected_frames=scene.clock.total_frames, full_decode=True)
        black = _black_check(video)
        passed = checks["passed"] and black["passed"] and count == 5010
        _write_json(out / "media_validation.json", {
            "passed": passed, "encoded_frames": count, "output": filename,
            "output_sha256": file_sha256(video), "media": checks, "blackdetect": black,
            "photo_asset_id": PHOTO_ID, "photo_rendered": scene.photo is not None,
            "missing_photo_treatment": None if scene.photo else {
                "shot_id": "GPT2015-21", "start_frame": 3630, "end_frame_exclusive": 3780,
                "treatment": "Hold the prior close camera on the Aug 24 chart with HUD and rail; omit photo and caption",
            },
        })
        if not passed:
            raise RuntimeError("Continuous preview failed media validation")
        print(video, flush=True)


if __name__ == "__main__":
    main()
