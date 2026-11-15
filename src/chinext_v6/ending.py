"""Data-driven silent ending components, independently reviewable at final size."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


@dataclass(frozen=True)
class EndingFacts:
    trading_days: int
    start_date: str
    end_date: str
    final_close: float
    base_point: float
    base_return: float
    max_drawdown: float
    constituents: tuple[dict, ...]
    industry_counts: dict[str, int]

    @property
    def leaders(self):
        return tuple(sorted(self.constituents, key=lambda x: x["market_cap"], reverse=True)[:3])


def load_facts(root: str | Path) -> EndingFacts:
    root = Path(root)
    with (root / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as f:
        market = list(csv.DictReader(f))
    with (root / "data/materials/创业板指_成分股_20261110.csv").open(encoding="utf-8-sig", newline="") as f:
        components = tuple({"code": r["代码"], "name": r["名称"], "industry": r["细分行业(东财)"],
                            "market_cap": float(r["总市值_元"]) / 1e8} for r in csv.DictReader(f))
    stats = json.loads((root / "data/materials/总结卡统计.json").read_text(encoding="utf-8-sig"))
    high = float(market[0]["close"])
    drawdown = 0.0
    for row in market:
        close = float(row["close"])
        high = max(high, close)
        drawdown = min(drawdown, close / high - 1)
    final_close = float(market[-1]["close"])
    base = 1000.0  # Official index base; distinct from first observed close.
    calculated_return = (final_close / base - 1) * 100
    if round(calculated_return, 2) != stats["基点口径涨幅_pct"]:
        raise ValueError("The settlement source disagrees with market CSV")
    if len(components) != 100 or len({r["code"] for r in components}) != len(components):
        raise ValueError("Constituent snapshot must contain 100 unique companies")
    return EndingFacts(len(market), market[0]["date"], market[-1]["date"], final_close, base,
                       calculated_return, drawdown * 100, components,
                       dict(Counter(r["industry"] for r in components)))


def smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


class EndingDrawer:
    duration = 15.0
    fps = 30
    gold = (255, 207, 141)
    white = (238, 243, 248)
    muted = (137, 157, 176)
    red = (255, 62, 54)
    blue = (66, 176, 223)

    def __init__(self, root: str | Path, width: int = 1080):
        self.root = Path(root)
        self.width = width
        self.height = round(width * 16 / 9)
        self.scale = width / 1080
        self.facts = load_facts(root)
        self.font_cache = {}
        self.text_boxes = []
        self.background = self._background()
        group_sizes = self.facts.industry_counts
        self.grid = sorted(self.facts.constituents,
                           key=lambda r: (-group_sizes[r["industry"]], r["industry"], -r["market_cap"]))
        self.grid_text_boxes = []
        self.grid_layer = self._grid_layer()

    def px(self, value):
        return round(value * self.scale)

    def font(self, size, bold=False):
        size = max(1, self.px(size))
        key = (size, bold)
        if key not in self.font_cache:
            path = f"/usr/share/fonts/opentype/noto/NotoSansCJK-{'Bold' if bold else 'Regular'}.ttc"
            self.font_cache[key] = ImageFont.truetype(path, size)
        return self.font_cache[key]

    def text(self, im, xy, content, size, fill=None, bold=False, anchor="la", ident=None, alpha=255):
        d = ImageDraw.Draw(im)
        font = self.font(size, bold)
        pos = tuple(self.px(v) for v in xy)
        color = fill or self.white
        d.text(pos, content, font=font, fill=(*color, alpha), anchor=anchor)
        bbox = d.textbbox(pos, content, font=font, anchor=anchor)
        self.text_boxes.append({"id": ident or content, "bbox": list(bbox), "role": "text", "text": content})
        return bbox

    def _background(self):
        w, h = self.width, self.height
        y, x = np.mgrid[:h, :w]
        q = y / h
        warm = np.exp(-((x / w + .1) ** 2 / .06 + (y / h) ** 2 / .025))
        horizon = np.exp(-((q - .79) ** 2 / .012))
        arr = np.stack([3 + 60 * warm + 1.5 * horizon,
                        8 + 20 * warm + 8 * horizon,
                        14 + 8 * warm + 17 * horizon], axis=-1)
        im = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGBA")
        grid = Image.new("RGBA", im.size)
        d = ImageDraw.Draw(grid)
        for i in range(10):
            yy = self.px(330 + i * 135)
            d.line((0, yy + self.px(90), w, yy - self.px(70)), fill=(36, 89, 117, 28), width=max(1, self.px(1)))
        im.alpha_composite(grid)
        earth_path = self.root / "assets/earth_cinematic.png"
        if earth_path.exists():
            asset = Image.open(earth_path).convert("RGBA")
            earth = asset.resize((self.px(1160), self.px(387)), Image.Resampling.LANCZOS)
            # Preserve the supplied atmospheric alpha; fade only the lower edge for footer contrast.
            alpha = np.asarray(earth.getchannel("A"), dtype=float)
            fade = np.clip((earth.height - np.arange(earth.height)) / self.px(75), 0, 1)
            earth.putalpha(Image.fromarray((alpha * fade[:, None]).astype("uint8")))
            im.alpha_composite(earth, (-self.px(40), self.px(1470)))
        else:
            asset = Image.open(self.root / "assets/earth_body.png").convert("RGB")
            asset = asset.crop((0, 37, asset.width, asset.height))
            asset = ImageEnhance.Brightness(asset).enhance(2.6)
            earth = asset.resize((self.px(1160), self.px(310)), Image.Resampling.LANCZOS).convert("RGBA")
            im.alpha_composite(earth, (-self.px(40), self.px(1510)))
        glow = Image.new("RGBA", im.size)
        gd = ImageDraw.Draw(glow)
        points = [(self.px(x), self.px(1768 - .28 * x + .00008 * x*x)) for x in range(-20, 1110, 5)]
        gd.line(points, fill=(37, 156, 244, 150), width=self.px(9))
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(self.px(12))))
        d = ImageDraw.Draw(im)
        d.line(points, fill=(85, 193, 255, 125), width=max(1, self.px(2)))
        orbit = [(self.px(x), self.px(1732 - .28*x + .00008*x*x)) for x in range(-20, 1110, 5)]
        red_glow = Image.new("RGBA", im.size)
        ImageDraw.Draw(red_glow).line(orbit, fill=(255, 48, 38, 115), width=self.px(7))
        im.alpha_composite(red_glow.filter(ImageFilter.GaussianBlur(self.px(9))))
        d = ImageDraw.Draw(im)
        d.line(orbit, fill=(255, 82, 61, 200), width=max(1, self.px(2)))
        node_x = 870
        node_y = 1732 - .28*node_x + .00008*node_x*node_x
        cx, cy = self.px(node_x), self.px(node_y)
        d.ellipse((cx-self.px(6), cy-self.px(6), cx+self.px(6), cy+self.px(6)), fill=(255, 239, 215, 255))
        d.ellipse((cx-self.px(14), cy-self.px(14), cx+self.px(14), cy+self.px(14)), outline=(255, 78, 53, 170), width=max(1, self.px(1)))
        return im

    def _header(self, im, title, kicker):
        self.text(im, (96, 92), "C H I N E X T   I N D E X", 19, self.muted)
        d = ImageDraw.Draw(im)
        d.line((self.px(72), self.px(164), self.px(72), self.px(266)), fill=self.red, width=self.px(4))
        self.text(im, (96, 155), title, 53, bold=True)
        self.text(im, (98, 242), kicker, 22, self.muted)

    def _footer(self, im):
        self.text(im, (92, 1812), "价格指数 · 不含分红", 20, self.muted)
        self.text(im, (92, 1848), f"数据截至 {self.facts.end_date.replace('-', '.')}", 20, self.muted)

    def _fade_layer(self, im, layer, amount):
        if amount <= 0:
            return
        if amount < 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda x: round(x * amount)))
        im.alpha_composite(layer)

    def render(self, t: float) -> Image.Image:
        self.text_boxes = []
        im = self.background.copy()
        t = max(0.0, min(self.duration, t))
        if t < 5:
            self._settlement(im, t)
        elif t < 10:
            self._constituents(im, t - 5)
        else:
            self._leaders(im, t - 10)
        self._footer(im)
        return im.convert("RGB")

    def _settlement(self, im, t):
        self._header(im, "时间的结算", f"{self.facts.start_date[:4]} → {self.facts.end_date[:4]}  /  真实收盘数据")
        rows = [(0, 405, f"{self.facts.trading_days:,}", "个交易日", 110, self.white),
                (.9, 805, f"{self.facts.base_return:+.2f}%", "官方基点口径涨幅", 85, self.gold),
                (2.1, 1190, f"{self.facts.max_drawdown:.2f}%", "全样本最大回撤", 79, self.blue)]
        for delay, y, value, label, size, color in rows:
            alpha = smooth((t - delay) / .45)
            if alpha <= 0:
                continue
            layer = Image.new("RGBA", im.size)
            self.text(layer, (96, y), value, size, color, bold=True)
            self.text(layer, (101, y + size + 24), label, 26, self.muted)
            if delay == 0:
                self.text(layer, (101, y + size + 75),
                          f"{self.facts.start_date.replace('-', '.')}—{self.facts.end_date.replace('-', '.')}", 23, self.muted)
            elif delay == .9:
                self.text(layer, (101, y + size + 75),
                          f"基点 {self.facts.base_point:,.0f} → {self.facts.final_close:,.2f}", 28, self.white)
            ImageDraw.Draw(layer).line((self.px(98), self.px(y - 26), self.px(958), self.px(y - 26)),
                                       fill=(*color, 90), width=max(1, self.px(1)))
            self._fade_layer(im, layer, alpha)

    def _grid_layer(self):
        layer = Image.new("RGBA", (self.width, self.height))
        d = ImageDraw.Draw(layer)
        for i, company in enumerate(self.grid):
            row, col = divmod(i, 10)
            x, y = 91 + col * 90, 560 + row * 82
            color = self.gold if company["industry"] in ("电池", "半导体", "通信设备") else (158, 187, 207)
            box = tuple(self.px(v) for v in (x, y, x + 82, y + 72))
            d.rounded_rectangle(box, radius=self.px(3), fill=(14, 30, 43, 192), outline=(*color, 62), width=max(1, self.px(1)))
            size = 19
            while d.textlength(company["name"], font=self.font(size)) > self.px(76):
                size -= 1
            font = self.font(size)
            pos = (self.px(x+41), self.px(y+35))
            d.text(pos, company["name"], font=font, fill=(*color, 255), anchor="mm")
            self.grid_text_boxes.append({"id": f"company_{company['code']}", "bbox": list(d.textbbox(pos, company["name"], font=font, anchor="mm")),
                                         "role": "constituent_name", "text": company["name"], "font_size": self.px(size), "cell_bbox": list(box)})
        return layer

    def _constituents(self, im, t):
        self._header(im, "今天这一篮子", f"当期成分股 · 截至 {self.facts.end_date.replace('-', '.')}")
        self.text(im, (96, 342), str(len(self.facts.constituents)), 90, self.gold, bold=True)
        self.text(im, (310, 408), "只公司", 29, self.white)
        self.text(im, (660, 369), str(len(self.facts.industry_counts)), 65, self.white, bold=True)
        self.text(im, (805, 408), "类行业", 26, self.muted)
        reveal = smooth(t / 1.2)
        visible_rows = min(10, max(1, math.ceil(reveal * 10)))
        layer = self.grid_layer.copy()
        if visible_rows < 10:
            ImageDraw.Draw(layer).rectangle((0, self.px(560 + visible_rows * 82), self.width, self.height), fill=(0, 0, 0, 0))
        im.alpha_composite(layer)
        self.text_boxes.extend(self.grid_text_boxes[:visible_rows*10])
        group_text = "  ·  ".join(f"{industry} {self.facts.industry_counts[industry]}" for industry in ["电池", "半导体", "通信设备"])
        self.text(im, (96, 1430), group_text, 25, self.gold)
        self.text(im, (96, 1491), "按行业分组 · 名称格为结构概览", 20, self.muted)
        count = len(self.facts.constituents)
        self.text(im, (96, 1540), f"今天这 {count} 只，不是历史各期的 {count} 只", 24, self.white)

    def _leaders(self, im, t):
        self._header(im, "今天的市值前三", "总市值，非指数权重")
        leaders = self.facts.leaders
        for i, company in enumerate(leaders):
            y = 430 + i * 330
            p = smooth((t - i * .25) / 1.0)
            self.text(im, (96, y), f"0{i+1}", 22, self.red)
            self.text(im, (96, y + 42), company["name"], 43, bold=True)
            self.text(im, (974, y + 58), f"{company['market_cap']:,.2f} 亿", 32, self.gold, anchor="ra")
            d = ImageDraw.Draw(im)
            x0, x1, yy = self.px(98), self.px(976), self.px(y + 143)
            d.line((x0, yy, x1, yy), fill=(35, 53, 67), width=self.px(7))
            endpoint = x0 + (x1-x0) * company["market_cap"] / leaders[0]["market_cap"] * p
            if endpoint > x0:
                d.line((x0, yy, endpoint, yy), fill=self.gold if i == 0 else (180, 153, 115), width=self.px(7))
                d.ellipse((endpoint-self.px(4), yy-self.px(4), endpoint+self.px(4), yy+self.px(4)), fill=self.white)
        self.text(im, (96, 1556), f"截至 {self.facts.end_date.replace('-', '.')}", 24, self.muted)
        self.text(im, (96, 1715), "按当期成分股总市值排序", 24, self.white)

    def diagnostics(self, t):
        self.render(t)
        violations = [box for box in self.text_boxes if box["bbox"][0] < 0 or box["bbox"][1] < 0
                      or box["bbox"][2] > self.width or box["bbox"][3] > self.height]
        return {"t": t, "text_boxes": list(self.text_boxes), "out_of_bounds": violations,
                "width": self.width, "height": self.height}
