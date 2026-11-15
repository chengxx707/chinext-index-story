from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .motion import ease_in_out_sine


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


class MarketData:
    def __init__(self, csv_path: str | Path):
        df = pd.read_csv(csv_path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
        required = ["date", "open", "high", "low", "close", "pct_chg"]
        missing = set(required).difference(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")
        if df[required[1:]].isna().any().any():
            raise ValueError("OHLC contains missing values")
        self.df = df
        self.dates = pd.DatetimeIndex(df.date)
        self.open = df.open.to_numpy(float)
        self.high = df.high.to_numpy(float)
        self.low = df.low.to_numpy(float)
        self.close = df.close.to_numpy(float)
        self.pct_chg = df.pct_chg.to_numpy(float)
        self._map = {d.normalize(): i for i, d in enumerate(self.dates)}

    def index_for_date(self, value: str | pd.Timestamp) -> int:
        d = pd.Timestamp(value).normalize()
        if d in self._map:
            return self._map[d]
        pos = int(self.dates.searchsorted(d))
        if pos <= 0:
            return 0
        if pos >= len(self.dates):
            return len(self.dates) - 1
        return pos - 1 if abs(d - self.dates[pos - 1]) <= abs(self.dates[pos] - d) else pos

    def interpolated_close(self, idx: float) -> float:
        lo = max(0, min(len(self.close) - 1, int(np.floor(idx))))
        hi = min(len(self.close) - 1, lo + 1)
        f = idx - lo
        return float(self.close[lo] * (1.0 - f) + self.close[hi] * f)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


class SceneModel:
    def __init__(self, config_path: str | Path, events_path: str | Path, csv_path: str | Path):
        self.config = load_json(config_path)
        self.video = self.config["video"]
        self.style = self.config["style"]
        self.duration = float(self.video["duration_seconds"])
        self.fps = int(self.video["fps"])
        self.market = MarketData(csv_path)

        self.playhead_keys = [(float(k["t"]), float(self.market.index_for_date(k["date"]))) for k in self.config["playhead_keyframes"]]
        self.camera_keys = [(float(k["t"]), float(k["visible_days"]), float(k["current_x"])) for k in self.config["camera_keyframes"]]

        self.events = tuple(self._event(e) for e in load_json(events_path))
        self.critical_points = tuple(self._critical(c) for c in self.config["critical_points"])
        self.states = self._precompute()

    def _event(self, raw: dict[str, Any]) -> Event:
        return Event(
            id=raw["id"],
            date=pd.Timestamp(raw["date"]),
            index=self.market.index_for_date(raw["date"]),
            type=raw["type"],
            date_label=raw["date_label"],
            lines=tuple(raw.get("lines", [])),
            metric=raw.get("metric"),
            hit_t=float(raw["hit_t"]),
            pre_seconds=float(raw["pre_seconds"]),
            post_seconds=float(raw["post_seconds"]),
            placement=raw.get("placement", "left_mid"),
        )

    def _critical(self, raw: dict[str, Any]) -> CriticalPoint:
        return CriticalPoint(
            id=raw["id"],
            date=pd.Timestamp(raw["date"]),
            index=self.market.index_for_date(raw["date"]),
            price=float(raw["price"]),
            label=raw["label"],
            hit_t=float(raw["hit_t"]),
            hold_until=float(raw["hold_until"]),
            leave_anchor=bool(raw["leave_anchor"]),
        )

    @staticmethod
    def _interp(keys: list[tuple[float, float]], t: float) -> float:
        if t <= keys[0][0]:
            return keys[0][1]
        if t >= keys[-1][0]:
            return keys[-1][1]
        for (t0, v0), (t1, v1) in zip(keys[:-1], keys[1:]):
            if t0 <= t <= t1:
                if t1 == t0:
                    return v1
                u = ease_in_out_sine((t - t0) / (t1 - t0))
                return v0 + (v1 - v0) * u
        return keys[-1][1]

    def playhead_index(self, t: float) -> float:
        return self._interp(self.playhead_keys, t)

    def camera(self, t: float) -> tuple[float, float]:
        if t <= self.camera_keys[0][0]:
            return self.camera_keys[0][1], self.camera_keys[0][2]
        if t >= self.camera_keys[-1][0]:
            return self.camera_keys[-1][1], self.camera_keys[-1][2]
        for a, b in zip(self.camera_keys[:-1], self.camera_keys[1:]):
            t0, v0, x0 = a
            t1, v1, x1 = b
            if t0 <= t <= t1:
                u = ease_in_out_sine((t - t0) / (t1 - t0))
                return v0 + (v1 - v0) * u, x0 + (x1 - x0) * u
        return self.camera_keys[-1][1], self.camera_keys[-1][2]

    def _precompute(self) -> tuple[FrameState, ...]:
        total = int(round(self.duration * self.fps))
        raw = []
        for frame in range(total):
            t = frame / self.fps
            idxf = self.playhead_index(t)
            idx = int(np.floor(idxf))
            visible_f, current_x = self.camera(t)
            visible = max(20, int(round(visible_f)))
            chart_span = max(1, visible)
            past = int(round(chart_span * current_x))
            future = max(5, chart_span - past)
            start = max(0, idx - past)
            end = min(len(self.market.df) - 1, idx + future)
            low = float(np.min(self.market.low[start : idx + 1]))
            high = float(np.max(self.market.high[start : idx + 1]))
            span = max(40.0, high - low)
            # Dynamic vertical breathing; close-up still preserves OHLC ratios.
            pad_lo = 0.14 if visible > 80 else 0.19
            pad_hi = 0.20 if visible > 80 else 0.26
            raw.append({
                "t": t,
                "frame_number": frame,
                "playhead_index": idxf,
                "current_index": idx,
                "current_date": self.market.dates[idx],
                "current_close": self.market.interpolated_close(idxf),
                "visible_days": visible,
                "current_x_frac": current_x,
                "window_start": start,
                "window_end": end,
                "y_min": low - span * pad_lo,
                "y_max": high + span * pad_hi,
            })

        # Bi-directional smoothing keeps zoom transitions cinematic and deterministic.
        ymins = np.array([r["y_min"] for r in raw], dtype=float)
        ymaxs = np.array([r["y_max"] for r in raw], dtype=float)
        for _ in range(2):
            for i in range(1, len(raw)):
                ymins[i] = ymins[i - 1] * 0.86 + ymins[i] * 0.14
                ymaxs[i] = ymaxs[i - 1] * 0.86 + ymaxs[i] * 0.14
            for i in range(len(raw) - 2, -1, -1):
                ymins[i] = ymins[i + 1] * 0.90 + ymins[i] * 0.10
                ymaxs[i] = ymaxs[i + 1] * 0.90 + ymaxs[i] * 0.10
        out = []
        for i, r in enumerate(raw):
            r["y_min"] = float(ymins[i])
            r["y_max"] = float(ymaxs[i])
            out.append(FrameState(**r))
        return tuple(out)

    def state(self, frame: int) -> FrameState:
        return self.states[min(frame, len(self.states) - 1)]
