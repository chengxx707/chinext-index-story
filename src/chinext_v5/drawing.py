from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .model import CriticalPoint, Event, FrameState, SceneModel
from .motion import clamp, ease_out_cubic, envelope, pulse, smoothstep


Color = tuple[int, int, int, int]


def hex_rgba(value: str, alpha: int = 255) -> Color:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


C = {
    "bg": hex_rgba("02070C"),
    "bg2": hex_rgba("07121A"),
    "text": hex_rgba("F3F5F7"),
    "muted": hex_rgba("9BA4AE"),
    "grid": hex_rgba("24485B", 75),
    "red": hex_rgba("FF3431"),
    "red2": hex_rgba("FF5A4F"),
    "green": hex_rgba("19D489"),
    "blue": hex_rgba("29BDF4"),
    "gold": hex_rgba("FFD18A"),
    "gold2": hex_rgba("FFF1C8"),
    "darkred": hex_rgba("57191B"),
}


def with_alpha(color: Color, alpha: float) -> Color:
    return color[0], color[1], color[2], int(clamp(alpha) * color[3])


@dataclass(frozen=True)
class Layout:
    w: int
    h: int
    chart_left: int = 34
    chart_right: int = 700
    chart_top: int = 195
    chart_bottom: int = 845
    earth_y: int = 805
    timeline_y: int = 955
    bars_y: int = 1133


class Fonts:
    def __init__(self, regular: str, bold: str):
        self.regular_path = regular
        self.bold_path = bold
        self.cache = {}

    def get(self, size: int, bold: bool = False):
        key = (size, bold)
        if key not in self.cache:
            self.cache[key] = ImageFont.truetype(self.bold_path if bold else self.regular_path, size)
        return self.cache[key]


class SceneDrawer:
    def __init__(self, model: SceneModel, asset_dir: str | Path):
        self.model = model
        self.layout = Layout(int(model.video["width"]), int(model.video["height"]))
        self.fonts = Fonts(model.style["font_regular"], model.style["font_bold"])
        self.earth = self._prepare_earth(Path(asset_dir) / "earth_body.png")
        self.stars = self._make_stars()
        self.timeline_start = pd.Timestamp(model.config["sample"]["timeline_start"])
        self.timeline_end = pd.Timestamp(model.config["sample"]["timeline_end"])

    def _prepare_earth(self, path: Path) -> Image.Image:
        im = Image.open(path).convert("RGB")
        # Remove the tiny residual chart at the very top of the reference crop.
        im = im.crop((0, 35, im.width, im.height))
        im = ImageEnhance.Contrast(im).enhance(1.12)
        im = ImageEnhance.Color(im).enhance(0.9)
        im = im.resize((840, 245), Image.Resampling.LANCZOS)
        alpha = Image.new("L", im.size, 0)
        ad = ImageDraw.Draw(alpha)
        ad.rectangle((0, 20, im.width, im.height - 15), fill=238)
        alpha = alpha.filter(ImageFilter.GaussianBlur(18))
        rgba = im.convert("RGBA")
        rgba.putalpha(alpha)
        return rgba

    def _make_stars(self):
        rng = random.Random(71421)
        stars = []
        for _ in range(105):
            x = rng.randint(12, self.layout.w - 12)
            y = rng.randint(25, 940)
            r = rng.choice([1, 1, 1, 2])
            a = rng.randint(50, 170)
            c = rng.choice([(92, 184, 231, a), (217, 236, 246, a), (53, 127, 169, a)])
            stars.append((x, y, r, c))
        return stars

    def render(self, state: FrameState) -> Image.Image:
        im = self._background(state)
        self._draw_title(im)
        self._draw_current_status(im, state)
        chart = self._draw_chart_layer(state)
        im.alpha_composite(chart)
        self._draw_earth_and_timeline(im, state)
        self._draw_events(im, state)
        self._draw_critical_points(im, state)
        self._draw_stage_tracks(im, state)
        return im.convert("RGB")

    def _background(self, state: FrameState) -> Image.Image:
        w, h = self.layout.w, self.layout.h
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        for y in range(h):
            q = y / h
            arr[y, :, 0] = int(2 + 3 * q)
            arr[y, :, 1] = int(7 + 7 * q)
            arr[y, :, 2] = int(12 + 11 * q)
            arr[y, :, 3] = 255
        im = Image.fromarray(arr, "RGBA")
        d = ImageDraw.Draw(im)
        for x, y, r, c in self.stars:
            twinkle = 0.72 + 0.28 * math.sin(state.t * 0.85 + x * 0.04)
            d.ellipse((x-r, y-r, x+r, y+r), fill=(c[0], c[1], c[2], int(c[3] * twinkle)))
        # Subtle warm light in the top-left, matching the approved visual reference.
        glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-210, -270, 360, 250), fill=(255, 121, 59, 38))
        glow = glow.filter(ImageFilter.GaussianBlur(70))
        im.alpha_composite(glow)
        return im

    def _draw_letterspaced(self, d: ImageDraw.ImageDraw, xy, text, font, fill, spacing=6):
        x, y = xy
        for ch in text:
            d.text((x, y), ch, font=font, fill=fill)
            x += d.textlength(ch, font=font) + spacing

    def _draw_text_shadow(self, layer: Image.Image, xy, text, font, fill, anchor=None, shadow=3):
        sd = ImageDraw.Draw(layer)
        x, y = xy
        sd.text((x+shadow, y+shadow), text, font=font, fill=(0,0,0,170), anchor=anchor)
        sd.text((x, y), text, font=font, fill=fill, anchor=anchor)

    def _draw_title(self, im: Image.Image):
        d = ImageDraw.Draw(im)
        self._draw_letterspaced(d, (82, 52), self.model.style["title_en"], self.fonts.get(12), (180,188,197,220), spacing=6)
        d.rounded_rectangle((67, 88, 72, 150), radius=2, fill=C["red"])
        d.text((84, 79), self.model.style["title_cn"], font=self.fonts.get(37, True), fill=C["text"])
        title_w = d.textlength(self.model.style["title_cn"], font=self.fonts.get(37, True))
        d.text((91 + title_w, 92), f"({self.model.style['code']})", font=self.fonts.get(22, True), fill=C["text"])
        self._draw_letterspaced(d, (84, 134), self.model.style["subtitle"], self.fonts.get(13), (190,196,202,215), spacing=5)

    def _draw_current_status(self, im: Image.Image, state: FrameState):
        d = ImageDraw.Draw(im)
        date = state.current_date.strftime("%Y.%m.%d")
        d.text((682, 54), date, font=self.fonts.get(15), fill=(190,198,205,220), anchor="ra")
        d.text((682, 79), f"{state.current_close:,.2f}", font=self.fonts.get(25, True), fill=C["text"], anchor="ra")
        d.text((682, 111), "收盘", font=self.fonts.get(12), fill=(127,137,148,190), anchor="ra")

    def _chart_coords(self, state: FrameState):
        L = self.layout
        span_idx = max(1, state.window_end - state.window_start)
        span_y = max(1.0, state.y_max - state.y_min)
        def x_for(idx: float):
            return L.chart_left + (idx - state.window_start) / span_idx * (L.chart_right - L.chart_left)
        def y_for(price: float):
            return L.chart_bottom - (price - state.y_min) / span_y * (L.chart_bottom - L.chart_top)
        return x_for, y_for

    def _draw_chart_layer(self, state: FrameState) -> Image.Image:
        L = self.layout
        layer = Image.new("RGBA", (L.w, L.h), (0,0,0,0))
        d = ImageDraw.Draw(layer)
        # Open grid, no PPT-like border.
        for i in range(1, 6):
            y = L.chart_top + (L.chart_bottom - L.chart_top) * i / 6
            d.line((L.chart_left, y, L.chart_right, y), fill=C["grid"], width=1)
        for i in range(1, 7):
            x = L.chart_left + (L.chart_right - L.chart_left) * i / 7
            d.line((x, L.chart_top, x, L.chart_bottom), fill=C["grid"], width=1)

        x_for, y_for = self._chart_coords(state)
        px_per_day = (L.chart_right - L.chart_left) / max(1, state.window_end - state.window_start)
        body_w = int(max(2, min(16, px_per_day * 0.70)))
        glow_w = max(body_w + 5, 8)

        # Candles render in a dedicated layer for soft cinematic bloom.
        bloom = Image.new("RGBA", layer.size, (0,0,0,0))
        bd = ImageDraw.Draw(bloom)
        crisp = Image.new("RGBA", layer.size, (0,0,0,0))
        cd = ImageDraw.Draw(crisp)
        m = self.model.market
        for idx in range(state.window_start, min(state.current_index, state.window_end) + 1):
            x = x_for(idx)
            yo, yc = y_for(m.open[idx]), y_for(m.close[idx])
            yh, yl = y_for(m.high[idx]), y_for(m.low[idx])
            up = m.close[idx] >= m.open[idx]
            color = C["red"] if up else C["green"]
            cd.line((x, yh, x, yl), fill=with_alpha(color, 0.95), width=max(1, body_w // 5))
            top, bottom = sorted((yo, yc))
            if bottom - top < 2:
                bottom = top + 2
            cd.rounded_rectangle((x-body_w/2, top, x+body_w/2, bottom), radius=max(1, body_w//6), fill=color)
            if idx >= state.current_index - 2:
                bd.line((x, yh, x, yl), fill=with_alpha(color, 0.45), width=glow_w)
                bd.rectangle((x-glow_w/2, top-2, x+glow_w/2, bottom+2), fill=with_alpha(color, 0.35))
        bloom = bloom.filter(ImageFilter.GaussianBlur(8))
        layer.alpha_composite(bloom)
        layer.alpha_composite(crisp)

        # Small current-price marker; critical point labels replace it when needed.
        cx = x_for(state.playhead_index)
        cy = y_for(state.current_close)
        d.line((cx, cy, L.chart_right, cy), fill=(255,255,255,30), width=1)
        d.ellipse((cx-3, cy-3, cx+3, cy+3), fill=(255,255,255,175))
        return layer

    @staticmethod
    def _bezier(p0, p1, p2, p3, u):
        a=(1-u)**3; b=3*(1-u)**2*u; c=3*(1-u)*u*u; e=u**3
        return (a*p0[0]+b*p1[0]+c*p2[0]+e*p3[0], a*p0[1]+b*p1[1]+c*p2[1]+e*p3[1])

    def _timeline_point(self, date: pd.Timestamp):
        total = (self.timeline_end - self.timeline_start).days
        u = clamp((date - self.timeline_start).days / total)
        return self._bezier((-25, 1040), (220, 950), (480, 925), (755, 955), u), u

    def _draw_earth_and_timeline(self, im: Image.Image, state: FrameState):
        L = self.layout
        # Slow parallax: the earth moves less than the K-line camera.
        xoff = int(-58 + 7 * math.sin(state.t * 0.19))
        yoff = int(L.earth_y + 2 * math.sin(state.t * 0.27))
        im.alpha_composite(self.earth, (xoff, yoff))

        layer = Image.new("RGBA", im.size, (0,0,0,0))
        d = ImageDraw.Draw(layer)
        points=[]
        for i in range(181):
            u=i/180
            points.append(self._bezier((-25,1040),(220,950),(480,925),(755,955),u))
        d.line(points, fill=(92,20,24,180), width=2)
        cur_pt, cur_u = self._timeline_point(state.current_date)
        past=[p for i,p in enumerate(points) if i/180 <= cur_u]
        if len(past)>1:
            # Glow and crisp trail.
            glow=Image.new("RGBA", im.size,(0,0,0,0)); gd=ImageDraw.Draw(glow)
            gd.line(past, fill=(255,45,39,130), width=10)
            glow=glow.filter(ImageFilter.GaussianBlur(12)); layer.alpha_composite(glow)
            d.line(past, fill=C["red"], width=3)

        for year in self.model.config["sample"]["timeline_years"]:
            p,_=self._timeline_point(pd.Timestamp(f"{year}-01-01"))
            active = year == state.current_date.year
            r=7 if active else 4
            d.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r), fill=(255,255,255,240) if active else (130,134,140,180))
            d.line((p[0],p[1]-10,p[0],p[1]-23), fill=(220,225,230,150), width=1)
            d.text((p[0],p[1]-47), str(year), font=self.fonts.get(20 if active else 15, active), fill=C["text"] if active else (160,165,172,185), anchor="mm")

        # Current day node and red reflection on the Earth.
        x,y=cur_pt
        glow=Image.new("RGBA", im.size,(0,0,0,0)); gd=ImageDraw.Draw(glow)
        gd.ellipse((x-42,y-42,x+42,y+42), fill=(255,44,38,90))
        gd.ellipse((x-18,y-10,x+18,y+92), fill=(255,62,42,55))
        glow=glow.filter(ImageFilter.GaussianBlur(24)); layer.alpha_composite(glow)
        d.ellipse((x-8,y-8,x+8,y+8), fill=(255,255,255,245), outline=C["red2"], width=2)
        d.ellipse((x-17,y-17,x+17,y+17), outline=(255,71,61,130), width=2)
        im.alpha_composite(layer)

    def _event_strength(self, event: Event, t: float):
        return envelope(t, event.hit_t, event.pre_seconds, event.post_seconds)

    def _event_phase(self, event: Event, t: float):
        start=event.hit_t-event.pre_seconds
        end=event.hit_t+event.post_seconds
        return clamp((t-start)/(end-start))

    def _event_anchor(self, state: FrameState, event: Event):
        x_for,y_for=self._chart_coords(state)
        if not (state.window_start <= event.index <= state.window_end):
            return None
        return x_for(event.index), y_for(float(self.model.market.close[event.index]))

    def _draw_events(self, im: Image.Image, state: FrameState):
        for e in self.model.events:
            s=self._event_strength(e,state.t)
            if s<=0.01:
                continue
            anchor=self._event_anchor(state,e)
            if anchor is None:
                continue
            self._draw_event(im,state,e,anchor,s,self._event_phase(e,state.t))

    def _draw_event(self, im, state, event, anchor, strength, phase):
        L=self.layout; ax,ay=anchor
        layer=Image.new("RGBA", im.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
        # Exact date link: timeline node -> lower chart edge -> event candle.
        tp,_=self._timeline_point(event.date)
        link_alpha=int(180*strength)
        mid_y=L.chart_bottom+22
        d.line((tp[0],tp[1]-4,tp[0],mid_y), fill=(255,66,55,link_alpha//2), width=1)
        d.line((tp[0],mid_y,ax,mid_y,ax,ay), fill=(255,79,61,link_alpha), width=1)
        d.ellipse((ax-5,ay-5,ax+5,ay+5), fill=(255,235,200,220), outline=(255,75,55,230), width=2)
        d.ellipse((tp[0]-5,tp[1]-5,tp[0]+5,tp[1]+5), fill=(255,255,255,220), outline=(255,54,48,230), width=2)

        if event.placement=="right_mid":
            tx,ty=420,330
        elif event.placement=="left_top":
            tx,ty=80,260
        else:
            tx,ty=82,340
        slide=(1-ease_out_cubic(min(1,phase*2.2)))*22
        tx-=slide
        a=int(255*strength)

        if event.type=="market_phenomenon":
            d.rounded_rectangle((tx,ty,tx+112,ty+31),radius=4,fill=(211,35,31,a))
            d.text((tx+56,ty+15),event.date_label,font=self.fonts.get(14,True),fill=(255,255,255,a),anchor="mm")
            d.text((tx,ty+47),event.lines[0],font=self.fonts.get(22,True),fill=(245,247,249,a))
            # Counter is tied to event animation phase.
            counter_phase=smoothstep(clamp((phase-0.18)/0.45))
            val=413.03*counter_phase
            d.text((tx,ty+80),f"{val:,.2f}万户",font=self.fonts.get(35,True),fill=(255,132,105,a))
            # Information-driven particles, not decorative UI chrome.
            rng=random.Random(20150424)
            for i in range(28):
                px=tx+315+rng.uniform(-70,70); py=ty+62+rng.uniform(-38,38)
                rr=rng.choice([2,2,3]); aa=int(a*counter_phase*rng.uniform(.35,.8))
                d.ellipse((px-rr,py-rr,px+rr,py+rr),fill=(255,71,55,aa))
        else:
            accent=(255,55,48,a) if event.type=="institution" else (255,105,65,a)
            d.rounded_rectangle((tx,ty,tx+108,ty+31),radius=4,fill=accent)
            d.text((tx+54,ty+15),event.date_label,font=self.fonts.get(14,True),fill=(255,255,255,a),anchor="mm")
            yy=ty+48
            for line in event.lines:
                d.text((tx,yy),line,font=self.fonts.get(24,True),fill=(246,247,249,a))
                yy+=32
            d.line((tx,yy+3,tx+185,yy+3),fill=(255,58,48,int(a*.9)),width=2)
        # Soft bloom around the link, much lighter than metal UI.
        blur=layer.filter(ImageFilter.GaussianBlur(7))
        im.alpha_composite(blur)
        im.alpha_composite(layer)

    def _critical_pos(self,state,cp):
        x_for,y_for=self._chart_coords(state)
        if not (state.window_start<=cp.index<=state.window_end):
            return None
        return x_for(cp.index),y_for(cp.price)

    def _draw_critical_points(self,im,state):
        for cp in self.model.critical_points:
            hit=pulse(state.t,cp.hit_t,0.42)
            persistent=cp.leave_anchor and state.t>=cp.hit_t
            if hit<0.02 and not persistent:
                continue
            pos=self._critical_pos(state,cp)
            if pos is None:
                continue
            x,y=pos
            layer=Image.new("RGBA",im.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
            if persistent and cp.id=="stage_high":
                # The 2015 high becomes a historical memory line.
                d.line((self.layout.chart_left,y,self.layout.chart_right,y),fill=(255,184,90,85),width=1)
                d.text((self.layout.chart_right-5,y-17),f"{cp.price:,.2f}",font=self.fonts.get(13,True),fill=(255,214,150,190),anchor="ra")
            intensity=max(hit,0.30 if state.t<=cp.hold_until else 0.12)
            glow=Image.new("RGBA",im.size,(0,0,0,0)); gd=ImageDraw.Draw(glow)
            gd.ellipse((x-32*intensity,y-32*intensity,x+32*intensity,y+32*intensity),fill=(255,159,65,int(130*intensity)))
            glow=glow.filter(ImageFilter.GaussianBlur(15)); layer.alpha_composite(glow)
            r=5+int(4*hit)
            d.ellipse((x-r,y-r,x+r,y+r),fill=(255,255,236,245),outline=(255,166,70,245),width=2)
            for rr,aa in [(14,150),(25,80)]:
                d.ellipse((x-rr*hit,y-rr*hit,x+rr*hit,y+rr*hit),outline=(255,167,71,int(aa*hit)),width=2)

            show_label=hit>0.10 or (persistent and state.t<cp.hit_t+1.3)
            if show_label:
                if cp.id=="stage_high":
                    tx,ty=430,215
                else:
                    tx,ty=330,640
                a=int(255*max(hit,0.55))
                d.line((x,y,tx+10,ty+70),fill=(255,198,121,int(a*.85)),width=1)
                d.text((tx,ty),cp.date.strftime("%Y.%m.%d"),font=self.fonts.get(20,True),fill=(215,218,222,a))
                d.text((tx,ty+28),f"{cp.price:,.2f}",font=self.fonts.get(42,True),fill=(255,221,163,a))
                d.rounded_rectangle((tx,ty+78,tx+122,ty+108),radius=3,fill=(190,32,28,a))
                d.text((tx+61,ty+93),cp.label,font=self.fonts.get(16,True),fill=(255,255,255,a),anchor="mm")
            im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1)))
            im.alpha_composite(layer)

    def _stage_values(self,state):
        cfg=self.model.config["stages"]
        low_idx=self.model.market.index_for_date(cfg["rise"]["start_date"])
        high_idx=self.model.market.index_for_date(cfg["rise"]["end_date"])
        pre_target=cfg["pre_low"]["end_price"]/cfg["pre_low"]["start_price"]-1
        rise_target=cfg["rise"]["end_price"]/cfg["rise"]["start_price"]-1
        close=state.current_close
        if state.playhead_index<low_idx:
            b=close/cfg["pre_low"]["start_price"]-1
            return 0.0,0.0,b,clamp(abs(b/pre_target)),"blue"
        if state.playhead_index<=high_idx:
            r=close/cfg["rise"]["start_price"]-1
            return r,clamp(r/rise_target),pre_target,1.0,"red"
        b=close/cfg["post_high"]["start_price"]-1
        return rise_target,1.0,b,clamp(abs(b)/0.5486),"blue"

    def _draw_stage_tracks(self,im,state):
        red_v,red_p,blue_v,blue_p,active=self._stage_values(state)
        layer=Image.new("RGBA",im.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
        x0,x1=72,666
        y0=self.layout.bars_y
        def track(y,label,val,prog,color,is_active):
            a=245 if is_active else 130
            d.text((x0,y-8),label,font=self.fonts.get(14,True),fill=(235,238,240,a))
            d.text((x1,y-8),f"{val*100:+.2f}%",font=self.fonts.get(20,True),fill=with_alpha(color,a/255),anchor="ra")
            d.line((x0,y+23,x1,y+23),fill=(90,99,107,80),width=5)
            fx=x0+(x1-x0)*clamp(prog)
            if fx>x0+1:
                glow=Image.new("RGBA",im.size,(0,0,0,0)); gd=ImageDraw.Draw(glow)
                gd.line((x0,y+23,fx,y+23),fill=with_alpha(color,.65),width=14)
                glow=glow.filter(ImageFilter.GaussianBlur(9)); layer.alpha_composite(glow)
                d.line((x0,y+23,fx,y+23),fill=with_alpha(color,.95),width=5)
                d.ellipse((fx-6,y+17,fx+6,y+29),fill=(255,255,255,220),outline=with_alpha(color,.9),width=2)
        track(y0,"阶段上涨",red_v,red_p,C["red2"],active=="red")
        track(y0+61,"阶段回撤",blue_v,blue_p,C["blue"],active=="blue")
        im.alpha_composite(layer)
