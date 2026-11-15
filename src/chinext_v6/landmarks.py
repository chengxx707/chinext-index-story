"""Truthful cross-date landmark animation, separate from the active stage rail.

Source and target positions always use real trading-day closes.  The primary
effect reveals those observed close points in the current chart projection. If
the camera cannot show both dates, a visibly dated time-orbit recall is used;
an offscreen low is never relocated into the current candle window.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Callable, Any

import pandas as pd
from PIL import Image, ImageDraw

from .drawing import C, Fonts, clamp, smooth
from .model import MarketData


@dataclass(frozen=True)
class LandmarkLink:
    node_id: str
    from_date: str
    to_date: str
    from_close: float
    to_close: float
    value_pct: float
    source_label: str
    node_duration: float


class LandmarkOverlay:
    """A single source-to-landmark reveal, with no additional statistic rail.

    ``draw`` consumes the caller's current ``chart_coords`` and ``orbit_point``
    functions. Coordinates are the shared logical 720×1280 space. ``elapsed``
    is node-local seconds, independent of the scene's global camera clock.
    """

    def __init__(self, root: str | Path, width: int = 1080,
                 master: dict | None = None, market: MarketData | None = None):
        self.root = Path(root)
        self.width = int(width)
        self.height = round(self.width * 16 / 9)
        self.scale = self.width / 720
        self.master = master or json.loads((self.root / "config/production/film_master_v1.json").read_text())
        self.market = market or MarketData(self.root / "data/cyb_daily.csv")
        self.fonts = Fonts(self.scale, "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                           "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
        self.links: dict[str, LandmarkLink] = {}
        for node in self.master["nodes"]:
            if node["id"] not in {"S09", "S15"}:
                continue
            metric = next(m for m in node["metrics"] if m["kind"] == "interval_return")
            a, b = metric["start_date"], metric["end_date"]
            ia, ib = self.market.index_for_date(a), self.market.index_for_date(b)
            ca, cb = float(self.market.close[ia]), float(self.market.close[ib])
            value = (cb / ca - 1) * 100
            if abs(value - float(metric["value_pct"])) > .00001:
                raise ValueError(f"Landmark {node['id']} differs from frozen market closes")
            self.links[node["id"]] = LandmarkLink(node["id"], a, b, ca, cb, value,
                "历史低点回看" if cb > ca else "历史高点回看", float(node["duration_seconds"]))
        self.configuration = {key: asdict(value) for key, value in self.links.items()}
        self.text_boxes: list[dict] = []
        self.last_diagnostics: dict[str, Any] = {}

    def _point(self, point):
        return tuple(float(v) * self.scale for v in point)

    def _text(self, layer, point, text, size, *, ident, color=C["gold_light"], bold=False, alpha=1):
        draw = ImageDraw.Draw(layer)
        font = self.fonts.get(size, bold=bold)
        xy = self._point(point)
        fill = (*color[:3], round(255 * clamp(alpha)))
        draw.text(xy, text, font=font, fill=fill)
        self.text_boxes.append({"id": ident, "text": text,
            "bbox": list(draw.textbbox(xy, text, font=font)), "role": "landmark"})

    def _dot(self, draw, point, radius, alpha=1):
        x, y = point
        draw.ellipse(self._point((x-radius, y-radius, x+radius, y+radius)),
                     fill=(*C["gold_light"][:3], round(255 * clamp(alpha))))

    def draw(self, image: Image.Image, node_id: str, state, elapsed: float, *,
             chart_coords: tuple[Callable, Callable], orbit_point: Callable) -> Image.Image:
        self.text_boxes = []
        self.last_diagnostics = {"node_id": node_id, "active": False,
                                 "extra_active_rails": 0, "synthetic_candles": False}
        link = self.links.get(node_id)
        if link is None:
            return image
        ia, ib = self.market.index_for_date(link.from_date), self.market.index_for_date(link.to_date)
        self.last_diagnostics.update(**asdict(link), elapsed=float(elapsed),
            current_date=str(pd.Timestamp(state.current_date).date()))
        if state.current_index < ib or elapsed < .8:
            self.last_diagnostics["phase"] = "awaiting_observed_landmark"
            return image
        fade = min(smooth((elapsed-.8)/.35), smooth((min(4.8, link.node_duration-.15)-elapsed)/.30))
        if fade <= .001:
            self.last_diagnostics["phase"] = "finished"
            return image
        xp, yp = chart_coords
        source_xy, target_xy = (float(xp(ia)), float(yp(link.from_close))), (float(xp(ib)), float(yp(link.to_close)))
        inside = lambda p: 26 <= p[0] <= 704 and 250 <= p[1] <= 866
        both_visible = (state.window_start <= ia <= ib <= state.window_end
                        and inside(source_xy) and inside(target_xy))
        if not both_visible and elapsed < 1.5:
            self.last_diagnostics["phase"] = "awaiting_shared_projection"
            return image
        mode = "true_chart_close_path" if both_visible else "dated_time_orbit_recall"
        u = smooth((elapsed-1.15)/2.0)
        layer = Image.new("RGBA", image.size)
        draw = ImageDraw.Draw(layer)
        if both_visible:
            points = [(float(xp(i)), float(yp(float(self.market.close[i])))) for i in range(ia, ib+1)]
        else:
            # Orbit positions encode dates, not prices. Explicit source date
            # and recall wording below distinguish this from a relocated K.
            first, last = pd.Timestamp(link.from_date), pd.Timestamp(link.to_date)
            points = [tuple(float(v) for v in orbit_point(first+(last-first)*(i/100))[0]) for i in range(101)]
        count = max(1, min(len(points), math.floor((len(points)-1)*u)+1))
        revealed = points[:count]
        if len(revealed) > 1:
            draw.line([self._point(p) for p in revealed], fill=(255, 207, 140, round(172*fade)),
                      width=max(1, round(1.1*self.scale)), joint="curve")
        self._dot(draw, points[0], 3.7, fade)
        self._dot(draw, revealed[-1], 4.4, fade)
        # This is a dated history caption below the chart, not a second rail.
        self._text(layer, (72, 800), link.source_label, 11.5, ident="landmark_history_label", alpha=fade)
        self._text(layer, (72, 819), link.from_date.replace("-", "."), 13,
                   ident="landmark_history_date", color=C["muted"], alpha=fade)
        self._text(layer, (72, 841), f"{link.from_close:,.2f}", 25, bold=True,
                   ident="landmark_history_close", alpha=fade)
        if u >= .995:
            # The endpoint is always the actual target close coordinate; no
            # interpolated value is displayed as a dated observation.
            hit = smooth((elapsed-3.1)/.35)
            tx, ty = target_xy
            if inside(target_xy):
                for radius, strength in [(11+5*hit, 150), (24+5*hit, 70)]:
                    draw.ellipse(self._point((tx-radius, ty-radius, tx+radius, ty+radius)),
                                 outline=(255, 207, 140, round(strength*fade)), width=max(1, round(.7*self.scale)))
                self._dot(draw, target_xy, 4.5, fade)
        rgba = image if image.mode == "RGBA" else image.convert("RGBA")
        rgba.alpha_composite(layer)
        self.last_diagnostics.update(active=True, phase="path_reveal" if u < .995 else "landmark_hit",
            projection_mode=mode, source_chart_position=list(source_xy), target_chart_position=list(target_xy),
            source_position_relocated=False, revealed_observations=count,
            total_observations=len(points), reveal_progress=u, opacity=fade,
            factual_value_source="frozen_daily_close", displayed_pct=f"{link.value_pct:+.2f}%".replace("-", "−"))
        return rgba if image.mode == "RGBA" else rgba.convert("RGB")
