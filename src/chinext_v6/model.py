"""Deterministic facts and director time for the silent ChiNext production.

A chart camera may interpolate; dated facts never do. All layers consume the
same immutable FrameState. CSV dates are exact unless a source explicitly
provides an anchor_date for a non-trading day or coarser event date.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _ease(u: float) -> float:
    return (1.0 - math.cos(math.pi * min(1.0, max(0.0, u)))) / 2.0


@dataclass(frozen=True)
class Event:
    id: str
    date: pd.Timestamp
    index: int
    type: str
    date_label: str
    lines: tuple[str, ...]
    metric: str | None
    hit_t: float
    pre_seconds: float
    post_seconds: float
    placement: str
    importance: str = "primary"
    visual: str = "glass_gold_hairline"
    enabled: bool = True
    release_grade: str = "A"
    date_precision: str = "day"
    source_id: str = ""
    metric_value: float | None = None
    metric_unit: str = ""
    anchor_date: pd.Timestamp | None = None


@dataclass(frozen=True)
class CriticalPoint:
    id: str
    date: pd.Timestamp
    index: int
    price: float
    label: str
    hit_t: float
    hold_until: float
    leave_anchor: bool


@dataclass(frozen=True)
class FrameState:
    t: float
    frame_number: int
    playhead_index: float
    current_index: int
    current_date: pd.Timestamp
    current_close: float
    visible_days: int
    current_x_frac: float
    window_start: int
    window_end: int
    y_min: float
    y_max: float
    shot_id: str
    stage_mode: str
    stage_label: str
    stage_value: float
    stage_progress: float
    active_event_ids: tuple[str, ...]
    completed_milestones: tuple[dict[str, Any], ...]


class MarketData:
    def __init__(self, csv_path: str | Path):
        df = pd.read_csv(csv_path, encoding="utf-8-sig", parse_dates=["date"])
        required = ["date", "open", "high", "low", "close", "pct_chg"]
        missing = set(required).difference(df.columns)
        if missing:
            raise ValueError(f"Missing market columns: {sorted(missing)}")
        if df.empty or df[required].isna().any().any():
            raise ValueError("Market data is empty or contains missing facts")
        if not df.date.is_monotonic_increasing or df.date.duplicated().any():
            raise ValueError("Market dates must be unique and strictly increasing")
        values = df[required[1:]].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Market data contains nonfinite prices")
        if ((df.low > df[["open", "close"]].min(axis=1)) |
                (df.high < df[["open", "close"]].max(axis=1)) |
                (df.low > df.high) | (df.low <= 0)).any():
            raise ValueError("Invalid OHLC range")
        self.df = df.reset_index(drop=True)
        self.dates = pd.DatetimeIndex(self.df.date)
        for name in required[1:]:
            setattr(self, name, self.df[name].to_numpy(dtype=float))
        self._map = {d.normalize(): i for i, d in enumerate(self.dates)}

    def index_for_date(self, value: str | pd.Timestamp, strict: bool = True) -> int:
        date = pd.Timestamp(value).normalize()
        if date in self._map:
            return self._map[date]
        if strict:
            raise ValueError(f"No exact trading day in market data: {date.date()}")
        # Explicit opt-in means previous trading day, never silent nearest-day.
        index = int(self.dates.searchsorted(date, side="right")) - 1
        if index < 0 or date > self.dates[-1]:
            raise ValueError(f"Date outside market data: {date.date()}")
        return index


class SceneModel:
    def __init__(self, config_path: str | Path, events_path: str | Path, csv_path: str | Path):
        self.config_path = Path(config_path)
        self.config = load_json(config_path)
        self.video = self.config["video"]
        self.duration = float(self.video["duration_seconds"])
        self.fps = int(self.video["fps"])
        self.total_frames = round(self.duration * self.fps)
        if self.duration <= 0 or self.fps <= 0 or self.total_frames < 2:
            raise ValueError("Video needs a positive duration, fps, and at least two frames")
        self.style = {
            "title_en": "CHINEXT INDEX", "title_cn": "创业板指", "code": "399006",
            "subtitle": "中国创业板市场代表指数",
            "font_regular": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "font_bold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            **self.config.get("style", {}),
        }
        self.market = MarketData(csv_path)
        self.playhead_keys = [(float(k["t"]), float(self.market.index_for_date(k["date"])))
                              for k in self.config["playhead_keyframes"]]
        if not self.playhead_keys or self.playhead_keys[0][0] != 0:
            raise ValueError("Playhead timeline must start at zero")
        if abs(self.playhead_keys[-1][0] - self.duration) > 1e-9:
            raise ValueError("Playhead timeline must end at video duration")
        if any(a[0] >= b[0] or a[1] > b[1]
               for a, b in zip(self.playhead_keys, self.playhead_keys[1:])):
            raise ValueError("Playhead times must increase and market dates cannot reverse")
        self.camera_shots = tuple(self.config.get("camera_shots", []))
        if not self.camera_shots:
            raise ValueError("V6 requires semantic camera_shots")
        self._validate_shots()
        raw_events = load_json(events_path)
        self.excluded_events = tuple(e for e in raw_events
                                    if not e.get("enabled", False) or e.get("release_grade") not in {"A", "DATA"})
        self.events = tuple(self._event(e) for e in raw_events
                            if e.get("enabled", False) and e.get("release_grade") in {"A", "DATA"})
        if len({e.id for e in self.events}) != len(self.events):
            raise ValueError("Event ids must be unique")
        self.critical_points = tuple(self._critical(c) for c in self.config.get("critical_points", []))
        self._locked_ranges = {s["id"]: self._shot_range(s) for s in self.camera_shots
                               if s.get("y_policy") in {"lookahead_locked", "critical_anchor"}}
        self.stage_modes = tuple(self.config.get("stage_rail", {}).get("modes", []))
        if not self.stage_modes:
            raise ValueError("At least one active stage mode is required")
        self.states = self._precompute()

    def _validate_shots(self):
        if abs(float(self.camera_shots[0]["start_t"])) > 1e-9:
            raise ValueError("Camera shots must start at zero")
        if abs(float(self.camera_shots[-1]["end_t"]) - self.duration) > 1e-9:
            raise ValueError("Camera shots must cover the full duration")
        for i, shot in enumerate(self.camera_shots):
            if float(shot["end_t"]) <= float(shot["start_t"]):
                raise ValueError("Camera shot has nonpositive duration")
            if shot.get("y_policy") not in {"follow_window", "lookahead_locked", "critical_anchor"}:
                raise ValueError(f"Unsupported camera y_policy: {shot.get('y_policy')}")
            if i and abs(float(self.camera_shots[i-1]["end_t"]) - float(shot["start_t"])) > 1e-9:
                raise ValueError("Camera shots must be contiguous without overlaps")

    def _event(self, raw: dict[str, Any]) -> Event:
        date = pd.Timestamp(raw["date"])
        anchor = pd.Timestamp(raw.get("anchor_date", raw["date"]))
        index = self.market.index_for_date(anchor)
        hit_t = float(raw["hit_t"])
        if not 0 <= hit_t <= self.duration:
            raise ValueError(f"Event {raw['id']} hit outside video")
        if abs(self.playhead_index(hit_t) - index) > 1e-6:
            raise ValueError(f"Event {raw['id']} hit_t disagrees with playhead date")
        return Event(
            id=raw["id"], date=date, index=index, type=raw["type"],
            date_label=raw.get("date_label", date.strftime("%Y.%m.%d")),
            lines=tuple(raw.get("lines", [])), metric=raw.get("metric"),
            hit_t=hit_t, pre_seconds=float(raw.get("pre_seconds", 0.25)),
            post_seconds=float(raw.get("post_seconds", 2.5)), placement=raw.get("placement", "left_mid"),
            importance=raw.get("importance", "primary"), visual=raw.get("visual", "glass_gold_hairline"),
            enabled=True, release_grade=raw["release_grade"], date_precision=raw.get("date_precision", "day"),
            source_id=raw.get("source_id", raw["id"]),
            metric_value=float(raw["metric_value"]) if "metric_value" in raw else None,
            metric_unit=raw.get("metric_unit", ""), anchor_date=anchor,
        )

    def _critical(self, raw: dict[str, Any]) -> CriticalPoint:
        date = pd.Timestamp(raw["date"])
        index = self.market.index_for_date(date)
        actual_price = float(self.market.close[index])
        if "price" in raw and abs(actual_price - float(raw["price"])) > 0.005:
            raise ValueError(f"Critical point {raw['id']} differs from CSV close")
        hit_t = float(raw["hit_t"])
        if abs(self.playhead_index(hit_t) - index) > 1e-6:
            raise ValueError(f"Critical point {raw['id']} hit_t disagrees with playhead")
        hold_until = float(raw["hold_until"])
        if not hit_t <= hold_until <= self.duration:
            raise ValueError("Critical point hold range is outside video")
        return CriticalPoint(raw["id"], date, index, actual_price, raw["label"],
                             hit_t, hold_until, bool(raw.get("leave_anchor", True)))

    @staticmethod
    def _interp(keys: list[tuple[float, float]], t: float) -> float:
        if t <= keys[0][0]:
            return keys[0][1]
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t <= t1:
                return v0 + (v1-v0)*_ease((t-t0)/(t1-t0))
        return keys[-1][1]

    def playhead_index(self, t: float) -> float:
        return self._interp(self.playhead_keys, t)

    def shot_for_time(self, t: float) -> dict[str, Any]:
        for shot in self.camera_shots:
            if float(shot["start_t"]) <= t < float(shot["end_t"]):
                return shot
        return self.camera_shots[-1]

    def camera(self, t: float) -> tuple[float, float]:
        shot = self.shot_for_time(t)
        u = _ease((t-float(shot["start_t"]))/(float(shot["end_t"])-float(shot["start_t"])))
        visible = float(shot["visible_days_start"]) + (float(shot["visible_days_end"])-float(shot["visible_days_start"]))*u
        current_x = float(shot["current_x_start"]) + (float(shot["current_x_end"])-float(shot["current_x_start"]))*u
        return visible, current_x

    def _window(self, t: float) -> tuple[int, int, int, float, int]:
        index = min(len(self.market.df)-1, max(0, int(math.floor(self.playhead_index(t)+1e-9))))
        visible_f, current_x = self.camera(t)
        visible = max(20, round(visible_f))
        start = max(0, index-round(visible*current_x))
        end = min(len(self.market.df)-1, start+visible)
        return index, start, end, current_x, visible

    def _shot_range(self, shot: dict[str, Any]) -> tuple[float, float]:
        # Include all candles that can be revealed in this shot, but never draw
        # future candles. Future information is used only to stabilize framing.
        indices = [self._window(float(t)) for t in np.linspace(shot["start_t"], shot["end_t"], 40)]
        start = min(w[1] for w in indices)
        end = max(w[0] for w in indices)
        low = float(self.market.low[start:end+1].min())
        high = float(self.market.high[start:end+1].max())
        span = max(40.0, high-low)
        if shot.get("y_policy") == "critical_anchor" and shot.get("focus_date"):
            focus = float(self.market.close[self.market.index_for_date(shot["focus_date"])])
            top_fraction = float(shot.get("anchor_y_frac", 0.28))
            span = max(span*1.35, (focus-low)/(1-top_fraction), (high-focus)/top_fraction, 40)
            return focus-(1-top_fraction)*span, focus+top_fraction*span
        return low-span*0.18, high+span*0.25

    def _stage(self, index: int, current_close: float):
        # At an extreme's held frame its previous stage is still complete. The
        # next stage takes over once the shared playhead passes that date.
        mode = self.stage_modes[-1]
        completed = []
        labels = {"drawdown_pre_low": "阶段回撤", "rise_from_low": "阶段上涨", "drawdown_from_high": "高点后回撤"}
        for candidate in self.stage_modes:
            end_date = candidate.get("end_date")
            if end_date and index > self.market.index_for_date(end_date):
                anchor = float(self.market.close[self.market.index_for_date(candidate["start_date"])])
                terminal = float(self.market.close[self.market.index_for_date(end_date)])/anchor-1
                completed.append({"id": candidate["id"], "label": candidate.get("label", labels.get(candidate["id"], "阶段结果")),
                                  "value": terminal, "date": end_date})
            else:
                mode = candidate
                break
        anchor = float(self.market.close[self.market.index_for_date(mode["start_date"])])
        if "anchor_price" in mode and abs(anchor-float(mode["anchor_price"])) > 0.005:
            raise ValueError(f"Stage {mode['id']} anchor price differs from CSV")
        value = current_close/anchor-1
        target = abs(float(mode.get("target_value", 1.0)))
        if mode.get("end_date"):
            target = abs(float(self.market.close[self.market.index_for_date(mode["end_date"])])/anchor-1)
        progress = min(1.0, max(0.0, abs(value)/max(target, 1e-12)))
        return mode["id"], mode.get("label", labels.get(mode["id"], "阶段变化")), value, progress, tuple(completed)

    def _precompute(self) -> tuple[FrameState, ...]:
        states = []
        transition_from = None
        for frame in range(self.total_frames):
            # Include the director endpoint in a fixed number of video frames.
            # Encoded presentation timestamps remain frame/fps; director time
            # differs by < one frame and is the sole animation/state clock.
            t = self.duration*frame/(self.total_frames-1)
            index, start, end, current_x, visible = self._window(t)
            shot = self.shot_for_time(t)
            if shot["id"] in self._locked_ranges:
                y_min, y_max = self._locked_ranges[shot["id"]]
            else:
                low = float(self.market.low[start:index+1].min())
                high = float(self.market.high[start:index+1].max())
                span = max(40.0, high-low)
                y_min, y_max = low-span*0.18, high+span*0.25
            # Blend only camera-shot entry, never smooth factual prices or
            # allow reading-time vertical breathing. All locked shots settle
            # after a short deterministic transition.
            if states and states[-1].shot_id != shot["id"]:
                transition_from = (states[-1].y_min, states[-1].y_max)
            transition_seconds = float(shot.get("transition_seconds", 0.7))
            if transition_from and transition_seconds > 0:
                elapsed = t-float(shot["start_t"])
                if elapsed < transition_seconds:
                    mix = _ease(elapsed/transition_seconds)
                    y_min = transition_from[0] + (y_min-transition_from[0])*mix
                    y_max = transition_from[1] + (y_max-transition_from[1])*mix
            close = float(self.market.close[index])
            mode, label, value, progress, milestones = self._stage(index, close)
            active_ids = tuple(e.id for e in self.events
                               if e.hit_t-e.pre_seconds <= t < e.hit_t+e.post_seconds)
            states.append(FrameState(t, frame, self.playhead_index(t), index, self.market.dates[index], close,
                                     visible, current_x, start, end, y_min, y_max, shot["id"], mode, label,
                                     value, progress, active_ids, milestones))
        return tuple(states)

    def state(self, frame: int) -> FrameState:
        return self.states[min(max(0, frame), len(self.states)-1)]

    def frame_for_time(self, t: float) -> int:
        """First encoded frame at or after a director time."""
        return min(self.total_frames-1, max(0, math.ceil(t/self.duration*(self.total_frames-1)-1e-9)))
