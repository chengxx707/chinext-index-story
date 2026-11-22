"""One frame-indexed OHLC, projection, and stage clock for editorial releases."""

from bisect import bisect_right
import json
import math
from pathlib import Path

from .drawing import smooth
from .model import FrameState, MarketData


_CURRENT_X = 0.80


def _market_positions(keys: list[tuple[int, int]]) -> tuple[float, ...]:
    """Interpolate exact trading-index keys with monotone C1 Hermite segments."""
    slopes = [(right_index - left_index) / (right_frame - left_frame)
              for (left_frame, left_index), (right_frame, right_index) in zip(keys, keys[1:])]
    tangents = [0.0]
    for left, right in zip(slopes, slopes[1:]):
        tangents.append(2 * left * right / (left + right) if left > 0 and right > 0 else 0.0)
    tangents.append(0.0)
    positions = []
    for index, ((first, left), (last, right)) in enumerate(zip(keys, keys[1:])):
        size = last - first
        for frame in range(first, last):
            t = (frame - first) / size
            # Hermite interpolation in relative units avoids loss of precision
            # from combining two large, nearly equal absolute market indices.
            offset = ((3 - 2 * t) * t * t * (right - left)
                      + t * (1 - t)**2 * tangents[index] * size
                      + t * t * (t - 1) * tangents[index + 1] * size)
            positions.append(min(float(right), max(float(left), left + offset)))
    positions.append(float(keys[-1][1]))
    return tuple(positions)


class EditorialClock:
    """Consume the editorial keyframes directly, keeping evidence dates separate."""

    def __init__(self, root: Path, release: Path, width: int, *, photo_available: bool = True):
        director = json.loads((release / "director_timeline.json").read_text(encoding="utf-8"))
        self.fps = director["fps"]
        self.total_frames = director["frame_count"]
        height = round(width * 16 / 9)
        if self.fps != 30 or width < 360 or width % 2 or height % 2 or width * 16 != height * 9:
            raise ValueError("Editorial preview requires 30 fps and even 9:16 dimensions")
        self.video = {"width": width, "height": height, "fps": self.fps, "audio": False}
        self.market = MarketData(root / "data/cyb_daily.csv")
        self.cues = tuple(director["cues"])
        self.events = ()
        self.critical_points = ()
        self.config = {"sample": {"timeline_start": "2012-01-01", "timeline_end": "2016-01-01",
                                  "timeline_years": [2012, 2013, 2014, 2015]}}
        self.style = {}
        self._cue_start_frames = tuple(cue["start_frame"] for cue in self.cues)
        keys = self._keyframes()
        market_positions = _market_positions(keys)
        self.projections, self.camera_adjustments = self._projections(market_positions, photo_available)
        self.states = self._states(market_positions, director["rail"])
        self._validate_hits()

    def cue_at(self, frame: int) -> dict:
        if frame < 0 or frame >= self.total_frames:
            raise IndexError(f"Editorial frame outside half-open range: {frame}")
        return self.cues[bisect_right(self._cue_start_frames, frame) - 1]

    def _keyframes(self) -> list[tuple[int, int]]:
        keys = []
        expected_start = 0
        if len({cue["shot_id"] for cue in self.cues}) != len(self.cues):
            raise ValueError("Duplicate editorial shot ID")
        for cue in self.cues:
            start, end = cue["start_frame"], cue["end_frame_exclusive"]
            if start != expected_start or end <= start:
                raise ValueError(f"Editorial cues must be contiguous and nonempty: {cue['shot_id']}")
            clock = cue["market_clock"]
            if clock["mode"] != "monotone_trading_index":
                raise ValueError(f"Unsupported editorial market clock: {clock['mode']}")
            current = [(start + key["frame_offset"], self.market.index_for_date(key["date"]))
                       for key in clock["keyframes"]]
            if not current or current[0][0] != start or current[-1][0] != end - 1:
                raise ValueError(f"Market keys must cover the exact cue endpoints: {cue['shot_id']}")
            if keys and current[0][1] != keys[-1][1]:
                raise ValueError(f"Trading-index discontinuity at scene join: {cue['shot_id']}")
            keys.extend(current)
            expected_start = end
        if expected_start != self.total_frames or any(a >= b or x > y for (a, x), (b, y) in zip(keys, keys[1:])):
            raise ValueError("Market keys must advance through the declared frame count without reversing")
        return keys

    def _projections(self, positions: tuple[float, ...], photo_available: bool) -> tuple[tuple[dict, ...], list[dict]]:
        """Carry the preceding global camera into each authored target."""
        projections = []
        adjustments = []
        previous = None
        for cue in self.cues:
            start, end = cue["start_frame"], cue["end_frame_exclusive"]
            spec = cue["camera"]
            raw_span = float(spec["visible_trading_days"])
            low, high = map(float, spec["target_y_domain"])
            if not (raw_span > 0 and 0 < low < high and all(map(math.isfinite, (raw_span, low, high)))):
                raise ValueError(f"Invalid camera bounds: {cue['shot_id']}")
            geometry = cue["link_geometry"]
            dates = [cue["primary_anchor"]["date"], *(p["date"] for p in geometry["close_endpoints"])]
            dates.extend(geometry["statistics_range"] or ())
            if geometry["gap"]:
                dates.append(geometry["gap"]["previous_date"])
            oldest = min(self.market.index_for_date(day) for day in dates)
            # Include an inset for endpoint markers and brackets when a crop
            # would otherwise move already visible history off the left edge.
            span = max(raw_span, math.ceil((positions[end - 1] - oldest) / (_CURRENT_X - .04)))
            if span != raw_span:
                adjustments.append({"shot_id": cue["shot_id"], "field": "visible_trading_days",
                                    "authored": raw_span, "applied": span, "reason": "preserve_geometry_endpoints"})
            target = (span, low, high)
            if cue["photo_asset_id"] and not photo_available and previous is not None:
                adjustments.append({"shot_id": cue["shot_id"], "field": "camera_target",
                                    "authored_span_and_domain": target, "applied_span_and_domain": previous,
                                    "reason": "continue_incoming_chart_when_photo_is_missing"})
                target = previous
            previous = previous if previous is not None else target
            authored_frames = round(spec["transition_seconds"] * self.fps)
            y_changed = previous[1:] != target[1:]
            reading_start = cue["text_cue"]["in_frame"]
            if not start <= reading_start < end:
                raise ValueError(f"Text cue outside editorial shot: {cue['shot_id']}")
            allowed = reading_start - start if spec["lock_y_scale_while_text_reading"] and y_changed else end - start - 1
            duration = min(authored_frames, allowed)
            if duration != authored_frames and previous != target:
                adjustments.append({"shot_id": cue["shot_id"], "field": "transition_seconds",
                                    "authored": spec["transition_seconds"], "applied": duration / self.fps,
                                    "reason": "settle_vertical_scale_before_reading"})
            if duration == 0 and previous != target:
                raise ValueError(f"Camera discontinuity before locked reading at {cue['shot_id']}")
            for n in range(start, end):
                ratio = smooth((n - start) / duration) if duration else 1.0
                visible, y_min, y_max = (old + (new - old) * ratio for old, new in zip(previous, target))
                projections.append({
                    "window_start": positions[n] - _CURRENT_X * visible, "window_span": visible,
                    "y_min": y_min, "y_max": y_max,
                })
            previous = target
        return tuple(projections), adjustments

    def _states(self, positions: tuple[float, ...], rails: dict) -> tuple[FrameState, ...]:
        rise, drawdown = rails["rise"], rails["drawdown"]
        if rise["switch_after_frame"] + 1 != drawdown["start_frame"]:
            raise ValueError("Editorial rail transition must have exactly one active track")
        for rail in (rise, drawdown):
            actual = self.market.close[self.market.index_for_date(rail["base_date"])]
            if not math.isclose(actual, rail["base_close"], abs_tol=1e-7):
                raise ValueError("Editorial rail base does not match frozen OHLC")
        peak = {"label": rise["label"], "date": drawdown["base_date"],
                "value": drawdown["base_close"] / rise["base_close"] - 1}
        output = []
        for frame, (position, projection) in enumerate(zip(positions, self.projections, strict=True)):
            cue = self.cue_at(frame)
            index = math.floor(position + 1e-9)
            close = float(self.market.close[index])
            drawing_down = frame >= drawdown["start_frame"]
            rail = drawdown if drawing_down else rise
            if cue["rail_mode"] != rail["mode"]:
                raise ValueError(f"Editorial rail mode conflicts with the frame boundary: {cue['shot_id']}")
            value = close / rail["base_close"] - 1
            domain = max(abs(value) for value in rail["display_domain_percent"]) / 100
            progress = min(1.0, max(0.0, (-value if drawing_down else value) / domain))
            window_start, span = projection["window_start"], projection["window_span"]
            output.append(FrameState(
                frame / self.fps, frame, position, index, self.market.dates[index], close,
                round(span), _CURRENT_X, max(0, math.floor(window_start)), math.ceil(window_start + span),
                projection["y_min"], projection["y_max"], cue["shot_id"], rail["mode"], rail["label"],
                value, progress, tuple(cue["link_geometry"]["event_ids"]) if frame >= cue["text_cue"]["in_frame"] else (),
                (peak,) if drawing_down else (),
            ))
        return tuple(output)

    def _validate_hits(self) -> None:
        for cue in self.cues:
            anchor = cue["primary_anchor"]
            frame = anchor["hit_frame"]
            if not cue["start_frame"] <= frame < cue["end_frame_exclusive"]:
                raise ValueError(f"Primary hit outside editorial shot: {cue['shot_id']}")
            index = self.market.index_for_date(anchor["date"])
            if (self.states[frame].current_index != index or anchor["field"] not in {"open", "high", "low", "close"}
                    or not math.isclose(getattr(self.market, anchor["field"])[index], anchor["value"], abs_tol=1e-7)):
                raise ValueError(f"Primary hit does not match exact frozen OHLC: {cue['shot_id']}")
            clock = cue["event_clock"] or {}
            if clock.get("market_freeze_after_hit"):
                if any(state.current_index != index for state in self.states[frame:cue["end_frame_exclusive"]]):
                    raise ValueError(f"Required event hold would advance market clock: {cue['shot_id']}")
