"""Render the two revised V1.0.2-R1 blocks and scoped B13 PMI stills."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import importlib
import importlib.util
import json
import math
import multiprocessing
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import ImageDraw

BLOCKS = {"B01-B02": (0, 540), "B16-B18": (5520, 7320)}
SEGMENT_IDS = ("flash_forward", "main_before_august", "main_through_november")
PINNED_COMMIT = "67a8cc6740c521675f71c6c733997e429681c3a2"
RELEASE = Path("editorial/2015/releases/v1.0.1")
WORKER_SCENE = None


def _read(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _runtime(runtime_root: Path):
    runtime_root = runtime_root.resolve()
    source = runtime_root / "src"
    sys.path.insert(0, str(source))
    clock = importlib.import_module("chinext_v6.editorial_clock")
    if Path(clock.__file__).resolve() != source / "chinext_v6/editorial_clock.py":
        raise ValueError("EditorialClock was imported from outside the pinned runtime")
    spec = importlib.util.spec_from_file_location(
        "director_v102_published_preview", runtime_root / "tools/render_editorial_preview.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("Published EditorialProjectionDrawer is unavailable")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    return clock.EditorialClock, preview.EditorialProjectionDrawer


class VisualScene:
    """Composite legacy market-clock states with the exact global visual cue."""

    def __init__(self, repo_root: Path, candidate: dict, clocks: list, segments: list[dict],
                 width: int = 1080, *, drawer_class=None):
        if candidate["fps"] != 30 or candidate["frame_count"] != 7320:
            raise ValueError("Representative visual-test scope is the approved 7320-frame R1 candidate")
        self.candidate = candidate
        self.width = width
        self.height = width * 16 // 9
        if width * 16 != self.height * 9 or self.height % 2:
            raise ValueError("Production canvas requires even 9:16 dimensions")
        if len(clocks) != len(segments) or tuple(segment["id"] for segment in segments) != SEGMENT_IDS:
            raise ValueError("Visual candidate requires the three approved clock segments")
        self.projections = []
        self.states = []
        self.segment_for_frame = []
        for segment, clock in zip(segments, clocks, strict=True):
            start, end = segment["start_frame"], segment["end_frame_exclusive"]
            if start != len(self.states) or end - start != clock.total_frames:
                raise ValueError("Clock segments must partition the global frames")
            self.states.extend(replace(state, frame_number=state.frame_number + start,
                                       t=(state.frame_number + start) / 30) for state in clock.states)
            self.projections.extend(clock.projections)
            self.segment_for_frame.extend([segment["id"]] * clock.total_frames)
        if len(self.states) != candidate["frame_count"] or len(self.projections) != len(self.states):
            raise ValueError("Clock segments do not cover the approved frame count")
        self.cues = tuple(candidate["cues"])
        self.cue_starts = tuple(cue["start_frame"] for cue in self.cues)
        for cue, stop in zip(self.cues, (*self.cue_starts[1:], len(self.states)), strict=True):
            if cue["end_frame_exclusive"] != stop:
                raise ValueError(f"Candidate visual cues are discontinuous: {cue['shot_id']}")
        if self.cue_starts[0] != 0:
            raise ValueError("The first visual cue must start at global frame zero")

        initial_clock = clocks[0]
        self.market = initial_clock.market
        model = SimpleNamespace(video=initial_clock.video, fps=30, config=initial_clock.config,
                                style=initial_clock.style, market=self.market, states=self.states,
                                events=(), critical_points=())
        if drawer_class is None:
            from chinext_v6.film_renderer import _ProjectionDrawer

            class DefaultProjectionDrawer(_ProjectionDrawer):
                editorial_chart_top = 345

                def _coords(self, state):
                    x, _ = super()._coords(state)
                    p = self.projection
                    height = 846 - self.editorial_chart_top
                    return x, lambda price: 846 - (float(price) - p["y_min"]) / (p["y_max"] - p["y_min"]) * height

                def _chart(self, image, state):
                    layer = self._new()
                    super()._chart(layer, state)
                    top = round(self.editorial_chart_top * self.s)
                    image.alpha_composite(layer.crop((0, top, self.w, self.h)), (0, top))

            drawer_class = DefaultProjectionDrawer

        class VisualProjectionDrawer(drawer_class):
            editorial_chart_top = 345

        self.drawer = VisualProjectionDrawer(model, repo_root / "assets")
        self.background = self.drawer.background.copy()
        self.background.alpha_composite(self.drawer.grid)
        self.last_layout = None
        from visual_overlay import draw_visual_overlay
        self._overlay = draw_visual_overlay

    def cue_at(self, frame: int) -> dict:
        if not 0 <= frame < len(self.states):
            raise IndexError(f"Frame outside the approved candidate: {frame}")
        return self.cues[bisect_right(self.cue_starts, frame) - 1]

    @staticmethod
    def _focus(cue, frame):
        active = [window for window in cue["camera_story_clock"]["focus_windows"]
                  if window["start_frame"] <= frame < window["end_frame_exclusive"]]
        if len(active) != 1:
            raise ValueError(f"Expected exactly one visual focus at frame {frame}")
        return active[0]

    def _chart_alpha(self, cue: dict, window: dict, frame: int) -> float:
        from chinext_v6.drawing import smooth

        def level(focus: str) -> float:
            return 1.0 if focus == "L1_MARKET" else .62

        target = level(window["primary_focus"])
        offset = frame - window["start_frame"]
        previous_frame = window["start_frame"] - 1
        if previous_frame < 0 or offset >= 6 or self.segment_for_frame[frame] != self.segment_for_frame[previous_frame]:
            return target
        previous = self._focus(self.cue_at(previous_frame), previous_frame)["primary_focus"]
        return level(previous) + (target - level(previous)) * smooth((offset + 1) / 6)

    def _projection(self, cue: dict, state, frame: int) -> tuple[dict, dict | None]:
        from chinext_v6.drawing import clamp, smooth

        target = self.projections[frame]
        intro = cue["camera_story_clock"].get("intro_camera")
        if intro is None:
            return target, None
        start, settled = intro["start_frame"], intro["settled_frame"]
        low, high = intro["initial_y_domain"]
        initial_span = intro["initial_visible_trading_days"]
        if (cue["beat_id"] != "B01" or intro["easing"] != "smoothstep"
                or not cue["start_frame"] <= start < settled < cue["end_frame_exclusive"]
                or not all(math.isfinite(value) for value in (initial_span, low, high))
                or not (initial_span > 0 and 0 < low < high)):
            raise ValueError("Invalid flash-forward camera track")
        if state.current_date.date().isoformat() != "2015-06-03" or state.current_close != 3982.25:
            raise ValueError("Flash-forward camera must hold the exact June 3 market row")
        progress = clamp((frame - start) / (settled - start))
        eased = smooth(progress)
        span = initial_span + (target["window_span"] - initial_span) * eased
        projection = {
            "window_start": target["window_start"] + (target["window_span"] - span) * state.current_x_frac,
            "window_span": span,
            "y_min": low + (target["y_min"] - low) * eased,
            "y_max": high + (target["y_max"] - high) * eased,
        } if progress < 1 else target
        return projection, {"start_frame": start, "settled_frame": settled,
                            "easing": intro["easing"], "progress": progress, "eased_progress": eased}

    def _header(self, image, state, cue: dict, window: dict) -> dict:
        from chinext_v6.drawing import C

        d = self.drawer
        header = d._new()
        d._header(header, state)
        box = tuple(round(value * d.s) for value in (490, 166, 714, 255))
        ImageDraw.Draw(header).rectangle(box, fill=(0, 0, 0, 0))
        d.text_boxes = [item for item in d.text_boxes if item["role"] != "status"]
        image.alpha_composite(header)
        hud = d._pen(image, True)
        subdued = window["mode"] != "M1_MARKET" or window["primary_focus"] != "L1_MARKET"
        hud.text((668, 179), state.current_date.strftime("%Y.%m.%d"), d.fonts.get(14),
                 (186, 201, 211, 240), anchor="ra", id="current_date", role="status")
        close = None
        if cue["beat_id"] != "B01":
            close = f"{state.current_close:,.2f}"
            hud.text((668, 204), close, d.fonts.get(15 if subdued else 23, True),
                     C["muted"] if subdued else C["text"], anchor="ra", id="current_close", role="status")
            hud.text((668, 235), "当日收盘", d.fonts.get(11), (153, 171, 186, 235),
                     anchor="ra", id="current_close_label", role="status")
        return {"market_date_visible": True, "close_visible": close is not None, "close_text": close,
                "treatment": "opening_value_deferred_to_hero" if close is None else "market_close"}

    def _t2_state(self, cue):
        """Use typed prepared cue metadata where present."""
        visual = cue.get("visual_test") or {}
        return visual.get("t2_state") or cue.get("t2_state") or visual.get("metric") or cue.get("market_structure")

    def frame(self, frame: int):
        cue = self.cue_at(frame)
        state = self.states[frame]
        if state.shot_id != cue["shot_id"]:
            raise ValueError(f"Compiled clock and visual cue disagree at frame {frame}")
        window = self._focus(cue, frame)
        drawer = self.drawer
        drawer.projection, hook_camera = self._projection(cue, state, frame)
        if hook_camera is not None:
            x, y = drawer._coords(state)
            hook_camera["anchor_logical"] = [x(state.current_index), y(state.current_close)]
        drawer.text_boxes, drawer.critical_diagnostics, drawer.active_track_count = [], [], 0
        image = self.background.copy()
        chart = drawer._new()
        drawer._chart(chart, state)
        chart_alpha = self._chart_alpha(cue, window, frame)
        if chart_alpha < 1:
            chart.putalpha(chart.getchannel("A").point(lambda alpha: round(alpha * chart_alpha)))
        image.alpha_composite(chart)
        image.alpha_composite(drawer.earth_layer)
        drawer._world(image, state)
        hud = self._header(image, state, cue, window)
        drawer._rail(image, state)
        drawer._footer(image)
        overlay = self._overlay(image, drawer, state, cue, frame, t2_state=self._t2_state(cue))
        boxes = drawer.text_boxes
        errors = []
        for index, item in enumerate(boxes):
            x0, y0, x1, y1 = item["bbox"]
            if not (0 <= x0 < x1 <= drawer.w and 0 <= y0 < y1 <= drawer.h):
                errors.append({"type": "out_of_bounds", "ids": [item["id"]]})
            for other in boxes[index + 1:]:
                a0, b0, a1, b1 = other["bbox"]
                if min(x1, a1) - max(x0, a0) > 1 and min(y1, b1) - max(y0, b0) > 1:
                    errors.append({"type": "overlapping_text", "ids": [item["id"], other["id"]]})
        if drawer.active_track_count != 1:
            errors.append({"type": "rail_count", "value": drawer.active_track_count})
        rail = self.candidate["rail"]["rise" if state.stage_mode == "single_rise_until_peak_hold" else "drawdown"]
        last_candle = min(state.current_index, math.ceil(drawer.projection["window_start"] + drawer.projection["window_span"]))
        self.last_layout = {
            "frame": frame, "time_seconds": state.t, "beat_id": cue["beat_id"], "shot_id": cue["shot_id"],
            "segment": self.segment_for_frame[frame],
            "market_date": state.current_date.date().isoformat(), "market_close": state.current_close,
            "market_index": state.current_index, "playhead_index": state.playhead_index,
            "last_eligible_candle_index": last_candle,
            "no_future_candles": last_candle <= state.current_index and cue["camera"]["clip_future_candles"],
            "active_track_count": drawer.active_track_count, "stage_mode": state.stage_mode,
            "stage_value": state.stage_value, "stage_base_date": rail["base_date"], "stage_base_close": rail["base_close"],
            "stage_progress": state.stage_progress, "projection": drawer.projection,
            "chart_top_logical": drawer.editorial_chart_top, "chart_alpha": chart_alpha,
            "primary_focus": window["primary_focus"], "visual_mode": window["mode"],
            "text_boxes": boxes, "layout_errors": errors, "overlay": overlay,
            "hook_camera": hook_camera, "hud": hud,
        }
        return image.convert("RGB"), self.last_layout


def build_scene(repo_root: Path, candidate: dict, segments: list[dict], runtime_root: Path, width: int = 1080) -> VisualScene:
    clock_class, drawer_class = _runtime(runtime_root)
    clocks = [clock_class(repo_root, runtime_root / RELEASE, width, director=segment["timeline"], photo_available=True)
              for segment in segments]
    return VisualScene(repo_root, candidate, clocks, segments, width, drawer_class=drawer_class)


def _start_worker(repo_root, candidate, segments, runtime_root, width):
    global WORKER_SCENE
    WORKER_SCENE = build_scene(repo_root, candidate, segments, runtime_root, width)


def _worker_frame(frame: int):
    image, diagnostic = WORKER_SCENE.frame(frame)
    return image.tobytes(), diagnostic


def _frame_results(scene, start, end, pool=None):
    if pool is None:
        for frame in range(start, end):
            yield scene.frame(frame)
    else:
        for cursor in range(start, end, 24):
            yield from pool.map(_worker_frame, range(cursor, min(cursor + 24, end)), chunksize=2)


def render_block(scene: VisualScene, start: int, end: int, output: Path, *, pool=None, smoke=False) -> dict:
    from chinext_v6.renderer import encode_frames
    from chinext_v6.scene_cache import file_sha256, inspect_media

    block = next((name for name, permitted in BLOCKS.items() if permitted[0] <= start < end <= permitted[1]), None)
    if block is None or (not smoke and (start, end) != BLOCKS[block]):
        raise ValueError(f"Video scope is limited to approved representative blocks: [{start},{end})")
    output.mkdir(parents=True, exist_ok=True)
    tagged = "smoke" if smoke else "target"
    media = output / f"{tagged}.mp4"
    diagnostics = []

    def for_encoder():
        for image, row in _frame_results(scene, start, end, pool):
            diagnostics.append(row)
            if len(diagnostics) == 1 or len(diagnostics) % 240 == 0:
                print(f"{block} {tagged}: {len(diagnostics)}/{end - start} frames", flush=True)
            yield image

    count = encode_frames(for_encoder(), scene.width, scene.height, 30, media, preset="veryfast", crf=20)
    probe = inspect_media(media, width=scene.width, height=scene.height, fps=30, expected_frames=end-start,
                          full_decode=True)
    failures = [{"frame": row["frame"], "errors": row["layout_errors"]} for row in diagnostics
                if row["layout_errors"] or not row["no_future_candles"]]
    envelope = {"block": block, "start_frame": start, "end_frame_exclusive": end, "fps": 30,
                "width": scene.width, "height": scene.height, "frame_count": count, "frames": diagnostics,
                "scope": "every_source_rgb_frame_sent_to_encoder", "layout_failures": failures,
                "passed": count == end - start and not failures}
    _write(output / ("smoke_diagnostics.json" if smoke else "diagnostics.json"), envelope)
    evidence = {"passed": bool(probe["passed"]) and envelope["passed"], "block": block,
                "smoke": smoke, "video": media.name, "sha256": file_sha256(media), "probe": probe,
                "global_frame_interval": [start, end], "encoded_frame_count": count,
                "layout_failures": failures, "full_candidate_rendered": False}
    _write(output / ("smoke_media_validation.json" if smoke else "media_validation.json"), evidence)
    return evidence


def _pmi_cue(scene):
    candidates = [cue for cue in scene.cues if cue["beat_id"] == "B13" and
                  (cue.get("event_clock") or {}).get("event_id") == "E-AUG-01-03"]
    if len(candidates) != 1:
        raise ValueError("Expected one B13 PMI page-timestamp cue")
    return candidates[0]


def render_stills(scene, frames, out, *, pmi=False):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for number in sorted(set(frames)):
        cue = scene.cue_at(number)
        approved = any(start <= number < end for start, end in BLOCKS.values())
        pmi_frame = cue["beat_id"] == "B13" and (cue.get("event_clock") or {}).get("event_id") == "E-AUG-01-03"
        if not approved and not pmi_frame or pmi and not pmi_frame:
            raise ValueError(f"Still at frame {number} is outside approved representative/PMI scope")
        image, diagnostic = scene.frame(number)
        name = f"{cue['beat_id']}-f{number:04d}.png"
        image.save(out / name)
        rows.append({"path": name, **diagnostic})
    _write(out / "diagnostics.json", {"frame_count": len(rows), "frames": rows,
                                      "passed": all(not row["layout_errors"] and row["no_future_candles"] for row in rows)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--legacy-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--block", choices=tuple(BLOCKS), action="append", default=[])
    parser.add_argument("--all-blocks", action="store_true")
    parser.add_argument("--pmi-stills", action="store_true")
    parser.add_argument("--still", type=int, action="append", default=[])
    parser.add_argument("--smoke-frames", type=int)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument("--width", type=int, choices=(540, 720, 1080), default=1080)
    args = parser.parse_args()
    repo_root, runtime_root, out = (path.resolve() for path in (args.repo_root, args.runtime_root, args.out))
    if not out.is_relative_to(repo_root / "output") or out == repo_root / "output":
        parser.error("Visual-test output must be under a separate output/ directory")
    if not args.block and not (args.all_blocks or args.pmi_stills or args.still):
        parser.error("Choose at least one approved block or still")
    if args.smoke_frames is not None and not 1 <= args.smoke_frames <= 120:
        parser.error("Smoke encodes are limited to 1–120 frames")
    candidate = _read(args.candidate)
    segments = _read(args.legacy_dir / "segments.json")
    for segment in segments:
        if segment["id"] not in SEGMENT_IDS:
            raise ValueError(f"Undeclared legacy segment: {segment['id']}")
        segment["timeline"] = _read(args.legacy_dir / f"{segment['id']}.json")
    scene = build_scene(repo_root, candidate, segments, runtime_root, args.width)
    selected = tuple(BLOCKS) if args.all_blocks else tuple(dict.fromkeys(args.block))
    stills = []
    if args.pmi_stills:
        cue = _pmi_cue(scene)
        first, end = cue["camera_story_clock"]["reading_window"]
        stills.extend(render_stills(scene, [first, end - 1], out / "B13-PMI", pmi=True))
    if args.still:
        stills.extend(render_stills(scene, args.still, out / "stills"))
    results = []

    def render_selected(pool):
        for block in selected:
            start, end = BLOCKS[block]
            actual_end = min(end, start + args.smoke_frames) if args.smoke_frames is not None else end
            results.append(render_block(scene, start, actual_end, out / block,
                                        pool=pool, smoke=args.smoke_frames is not None))

    if selected and args.workers > 1:
        with ProcessPoolExecutor(
            max_workers=args.workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=_start_worker, initargs=(repo_root, candidate, segments, runtime_root, args.width),
        ) as pool:
            render_selected(pool)
    elif selected:
        render_selected(None)
    if results:
        _write(out / ("smoke_render_summary.json" if args.smoke_frames else "render_summary.json"),
               {"passed": all(row["passed"] for row in results), "runtime_commit": PINNED_COMMIT,
                "frame_intervals": [row["global_frame_interval"] for row in results], "blocks": results})
    return 0 if all(row["passed"] for row in results) and all(
        not row["layout_errors"] and row["no_future_candles"] for row in stills
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
