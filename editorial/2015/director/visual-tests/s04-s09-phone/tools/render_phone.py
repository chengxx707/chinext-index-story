"""Render the approved 20-second S04–S09 phone representative sample."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import chain
import json
import math
import multiprocessing
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

from amber_globe import atmosphere, land_mask

APPROVAL = "9bfc3039efe5a78b9a48bbe3c27844935238060f"
RUNTIME_COMMIT = "b0c339c629b8034427d20a49bdceb6a9fde5bd41"
FPS = 30
FRAME_COUNT = 600
SOURCE_SIZE = (1080, 1920)
PHONE_SIZE = (390, 694)
SOURCE_HASHES = {
    "data/cyb_daily.csv": "d832c794deaabaeda7b3803e5e93da471d6075f5d807b65714b9ab243d477205",
    "assets/earth_cinematic.png": "c3a9ee4a2f66bffd0899f5223d0c394520470da196ec1b80d77adaa7d2571197",
    "assets/earth_body.png": "a619239f32ba3ae6c9b5ee692ca0116a62d736f9f80bb72e8192b8238eecb253",
}
LAND_HASH = "9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9"
scene = None


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def smooth(value: float) -> float:
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def build_scene(runtime: Path, land: Path) -> None:
    global scene
    sys.path.insert(0, str(runtime / "src"))
    from chinext_v6.film_renderer import _ProjectionDrawer
    from chinext_v6.model import MarketData
    from market_clock import build_clock
    from montage_overlay import draw_copy

    market = MarketData(runtime / "data/cyb_daily.csv")
    clock = build_clock(market)
    if len(clock) != FRAME_COUNT:
        raise ValueError("Expected exactly 600 frame states")
    model = SimpleNamespace(
        video=dict(width=SOURCE_SIZE[0], height=SOURCE_SIZE[1]),
        style={}, states=(), events=(), market=market,
        config={"sample": {
            "timeline_start": "2012-08-10", "timeline_end": "2015-10-01",
            "timeline_years": [2013, 2014, 2015],
        }},
    )
    drawer = _ProjectionDrawer(model, runtime / "assets")
    # The approved full dot globe supplies the background. Only the existing
    # date-to-orbit geometry is inherited from the low-horizon renderer.
    drawer.earth_mask = Image.new("L", SOURCE_SIZE)
    world = land_mask(land)
    warm, cool = (atmosphere(kind, SOURCE_SIZE, world) for kind in ("start", "density"))
    for back in (warm, cool):
        back.alpha_composite(drawer.grid)
    scene = drawer, market, clock, draw_copy, warm, cool


def _box_collisions(boxes: list[dict]) -> list[list[str]]:
    collisions = []
    for index, first in enumerate(boxes):
        for second in boxes[:index]:
            x0, y0, x1, y1 = first["bbox"]
            i0, j0, i1, j1 = second["bbox"]
            if min(x1, i1) - max(x0, i0) > 2 and min(y1, j1) - max(y0, j0) > 2:
                collisions.append([first["id"], second["id"]])
    return collisions


def _render(frame: int) -> tuple[bytes, dict]:
    drawer, market, clock, draw_copy, warm, cool = scene
    state, projection = clock[frame]
    drawer.projection = projection
    drawer.text_boxes = []
    drawer.active_track_count = 0
    mix = smooth((state.t - 10.3) / 1.5) * smooth((18.0 - state.t) / 1.15)
    if mix <= 0:
        image = warm.copy()
    elif mix >= 1:
        image = cool.copy()
    else:
        image = Image.blend(warm, cool, mix)
    drawer._chart(image, state)
    drawer._world(image, state)
    cue = draw_copy(image, drawer, state, state.t, None)
    drawer._rail(image, state)
    drawer._footer(image)
    boxes = list(drawer.text_boxes)
    bounds = [box["id"] for box in boxes if not (
        0 <= box["bbox"][0] < box["bbox"][2] <= SOURCE_SIZE[0]
        and 0 <= box["bbox"][1] < box["bbox"][3] <= SOURCE_SIZE[1]
    )]
    active = drawer.active_track_count
    if active != 1:
        raise ValueError(f"Expected exactly one active stage rail at f{frame}; got {active}")
    xp, yp = drawer._coords(state)
    current = state.current_index
    first = max(0, math.floor(projection["window_start"]))
    last = min(current, math.ceil(projection["window_start"] + projection["window_span"]))
    row = {
        "frame": frame, "second": state.t, "market_date": str(state.current_date.date()),
        "market_index": current, "market_close": state.current_close,
        "price_ohlc": {key: float(getattr(market, key)[current]) for key in ("open", "high", "low", "close")},
        "stage_return_percent": 100 * state.stage_value,
        "active_track_count": active,
        "projection": projection,
        "text_boxes_logical": [
            {**item, "bbox": [round(value / drawer.s, 2) for value in item["bbox"]]} for item in boxes
        ],
        "out_of_bounds": bounds, "text_collisions": _box_collisions(boxes),
        "cue": cue, "window_first": first, "window_last": last,
        "current_point_logical_xy": [xp(current), yp(state.current_close)],
        "no_future_candles": last == current,
    }
    return image.convert("RGB").resize(PHONE_SIZE, Image.Resampling.LANCZOS).tobytes(), row


def write_trace(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({
        "approved_stills": APPROVAL, "source_runtime": RUNTIME_COMMIT,
        "fps": FPS, "duration_seconds": FRAME_COUNT / FPS,
        "source_canvas": list(SOURCE_SIZE), "phone_canvas": list(PHONE_SIZE),
        "source_hashes": SOURCE_HASHES, "land_geometry_sha256": LAND_HASH,
        "frames": rows,
    }, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def render(runtime: Path, land: Path, output: Path, workers: int) -> None:
    sys.path.insert(0, str(runtime / "src"))
    from chinext_v6.renderer import encode_frames
    from chinext_v6.scene_cache import inspect_media

    for name, wanted in SOURCE_HASHES.items():
        if digest(runtime / name) != wanted:
            raise ValueError(f"Source hash changed: {name}")
    if digest(land) != LAND_HASH:
        raise ValueError("Natural Earth land geometry hash changed")
    output.mkdir(parents=True, exist_ok=True)
    incomplete = output / "phone-390.building.mp4"
    rows: list[dict] = []

    def pictures(mapped):
        for picture, row in mapped:
            rows.append(row)
            if len(rows) % 120 == 0:
                print(f"{len(rows)}/{FRAME_COUNT} phone frames", flush=True)
            yield picture

    if workers == 1:
        build_scene(runtime, land)
        count = encode_frames(pictures(map(_render, range(FRAME_COUNT))),
                              *PHONE_SIZE, FPS, incomplete, preset="fast", crf=17)
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                 initializer=build_scene, initargs=(runtime, land)) as pool:
            stream = pictures(pool.map(_render, range(FRAME_COUNT), chunksize=4))
            first = next(stream)
            count = encode_frames(chain((first,), stream), *PHONE_SIZE, FPS, incomplete,
                                  preset="fast", crf=17)

    probe = inspect_media(incomplete, width=PHONE_SIZE[0], height=PHONE_SIZE[1], fps=FPS,
                          expected_frames=FRAME_COUNT, full_decode=True)
    write_trace(output / "frames.json", rows)
    failure = [r["frame"] for r in rows if r["out_of_bounds"] or r["text_collisions"]
               or not r["no_future_candles"]]
    if count != FRAME_COUNT or not probe["passed"] or failure:
        raise ValueError(f"Export failed: {count} frames, media={probe['passed']}, layout={failure[:15]}")
    final = output / "phone-390.mp4"
    incomplete.replace(final)
    payload = {"passed": True, "sha256": digest(final), "duration_seconds": 20,
               "width": 390, "height": 694, "frames": count, "fps": FPS,
               "media": final.name, "scope": "S04–S09 standalone representative sample",
               "approval_commit": APPROVAL, "runtime_commit": RUNTIME_COMMIT,
               "drawn_frames_trace_sha256": digest(output / "frames.json"),
               "source_hashes": SOURCE_HASHES, "land_geometry_sha256": LAND_HASH,
               "land_geometry_license": "Natural Earth public domain", "media_probe": probe}
    (output / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Complete: {final}, {count} frames, {payload['sha256']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--land-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", default=3, choices=(1, 2, 3, 4), type=int)
    args = parser.parse_args()
    render(args.runtime_root.resolve(), args.land_file.resolve(), args.output.resolve(), args.workers)


if __name__ == "__main__":
    main()
