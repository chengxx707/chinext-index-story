"""Deterministic, resolution-independent visual compositor for ChiNext V6.

The approved poster is an art reference, never a rendered background. Every
candle and fact label here is reconstructed from the scene model's CSV state.
Logical coordinates use a 720 x 1280 portrait and scale to the output size.
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

C = {
    "bg": (2, 7, 12, 255), "text": (242, 245, 247, 255),
    "muted": (151, 166, 179, 255), "red": (255, 61, 56, 255),
    "green": (24, 207, 136, 255), "blue": (61, 187, 239, 255),
    "gold": (255, 209, 138, 255), "gold_light": (255, 240, 208, 255),
}

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))

def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)

def rgba(color, alpha):
    return tuple(color[:3]) + (int(clamp(alpha) * 255),)

class Fonts:
    def __init__(self, scale, regular, bold):
        self.scale = scale
        self.paths = (regular, bold)
        self.cache = {}
        self.number_path = next((p for p in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Oblique.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf",
        ] if Path(p).is_file()), regular)

    def get(self, size, bold=False, numeric=False):
        path = self.number_path if numeric else self.paths[int(bold)]
        key = (path, round(size * self.scale))
        if key not in self.cache:
            self.cache[key] = ImageFont.truetype(path, key[1])
        return self.cache[key]

class Pen:
    """Draw logical coordinates while retaining actual output-pixel text bounds."""
    def __init__(self, image, scale, drawer=None):
        self.d = ImageDraw.Draw(image)
        self.s = scale
        self.owner = drawer

    def xy(self, points):
        if not points:
            return points
        if isinstance(points[0], (tuple, list)):
            return [(x * self.s, y * self.s) for x, y in points]
        return tuple(v * self.s for v in points)

    def line(self, points, fill, width=1, **kwargs):
        self.d.line(self.xy(points), fill=fill, width=max(1, round(width * self.s)), **kwargs)

    def rectangle(self, box, fill=None, outline=None, width=1):
        self.d.rectangle(self.xy(box), fill=fill, outline=outline, width=max(1, round(width * self.s)))

    def rounded_rectangle(self, box, radius=0, fill=None, outline=None, width=1):
        self.d.rounded_rectangle(self.xy(box), radius=radius * self.s, fill=fill,
                                 outline=outline, width=max(1, round(width * self.s)))

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self.xy(box), fill=fill, outline=outline, width=max(1, round(width * self.s)))

    def polygon(self, points, fill, outline=None, width=1):
        self.d.polygon(self.xy(points), fill=fill, outline=outline, width=max(1, round(width * self.s)))

    def text(self, xy, text, font, fill, anchor=None, id=None, role="body"):
        pos = self.xy(xy)
        self.d.text(pos, str(text), font=font, fill=fill, anchor=anchor,
                    stroke_width=0)
        if self.owner is not None and id:
            box = self.d.textbbox(pos, str(text), font=font, anchor=anchor)
            self.owner.text_boxes.append({"id": id, "bbox": list(box), "role": role,
                                          "overlaps_allowed": False})

    def textlength(self, text, font):
        return self.d.textlength(text, font=font) / self.s

class SceneDrawer:
    def __init__(self, model, asset_dir):
        self.model = model
        self.w = int(model.video["width"])
        self.h = int(model.video["height"])
        if abs(self.w / self.h - 9 / 16) > 0.001:
            raise ValueError("V6 visual compositor expects a 9:16 portrait")
        self.s = self.w / 720
        style = getattr(model, "style", {})
        regular = style.get("font_regular", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
        bold = style.get("font_bold", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
        self.fonts = Fonts(self.s, regular, bold)
        self.style = style
        self.text_boxes = []
        self.critical_diagnostics = []
        self.active_track_count = 0
        self.stage_transitions = []
        prior = None
        for state in model.states:
            mode = getattr(state, "stage_mode", None)
            if prior is not None and mode != prior:
                self.stage_transitions.append((state.t, prior, mode))
            prior = mode
        self.background = self._background()
        self.earth_layer, self.earth_mask = self._earth(Path(asset_dir) / "earth_body.png")
        self.grid = self._grid()
        sample = model.config.get("sample", {})
        self.timeline_start = pd.Timestamp(sample.get("timeline_start", "2012-01-01"))
        self.timeline_end = pd.Timestamp(sample.get("timeline_end", "2015-12-31"))
        self.timeline_years = sample.get("timeline_years", [2012, 2013, 2014, 2015])
        self.timeline_points = [self._curve(i / 180) for i in range(181)]
        self.node_glow = self._glow_sprite(84, (255, 62, 39), 0.47)
        self.gold_glow = self._glow_sprite(180, (255, 158, 63), 0.72)

    def _new(self):
        return Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))

    def _pen(self, image, record=False):
        return Pen(image, self.s, self if record else None)

    def _background(self):
        # Static space, rays, dust and broad warm key light are cached once.
        y, x = np.mgrid[0:self.h, 0:self.w]
        qx, qy = x / self.w, y / self.h
        radial = np.exp(-((qx + .10) ** 2 / .080 + (qy + .03) ** 2 / .014))
        ocean = np.exp(-((qx - .65) ** 2 / .6 + (qy - .72) ** 2 / .18))
        ray = np.exp(-((qx-.64*qy+.015)**2)/.0008) * np.exp(-qy/.13) * np.exp(-qx/.25)
        arr = np.empty((self.h, self.w, 4), dtype=np.uint8)
        arr[:, :, 0] = np.clip(2 + 103 * radial + 0.7 * ocean + 18*ray, 0, 255)
        arr[:, :, 1] = np.clip(7 + 52 * radial + 5 * ocean + 9*ray, 0, 255)
        arr[:, :, 2] = np.clip(12 + 29 * radial + 10 * ocean + 4*ray, 0, 255)
        arr[:, :, 3] = 255
        im = Image.fromarray(arr)
        d = self._pen(im)
        rng = random.Random(76213)
        for _ in range(29):
            xx, yy = rng.uniform(16, 704), rng.uniform(170, 1050)
            r = rng.choice([.45, .6, .8])
            d.ellipse((xx-r, yy-r, xx+r, yy+r), fill=(52, 137, 178, rng.randint(55, 118)))
        return im

    def _earth(self, path):
        # Prefer the generated, transparent eastern-Asia night asset. It contains
        # only the planet body and atmosphere: no poster typography/chart/track.
        cinematic = path.with_name("earth_cinematic.png")
        modern = cinematic.is_file()
        source = Image.open(cinematic if modern else path).convert("RGBA")
        if not modern:
            source = source.crop((0, 35, source.width, source.height))
            source = ImageEnhance.Brightness(source).enhance(1.85)
            source = ImageEnhance.Contrast(source).enhance(1.16)
        target_w = 820
        target_h = target_w * source.height / source.width if modern else 270
        # No aspect-ratio distortion of the cinematic asset.
        source = source.resize((round(target_w*self.s), round(target_h*self.s)), Image.Resampling.LANCZOS)
        rgb = source.copy()
        alpha = np.asarray(source.getchannel("A"), dtype=np.float32)
        yy = np.linspace(0, 1, source.height)[:, None]
        xx = np.linspace(0, 1, source.width)[None, :]
        fade = np.minimum(1, (1-yy)/.16) * np.minimum(1, xx/.025) * np.minimum(1, (1-xx)/.025)
        if not modern:
            fade *= np.minimum(1, yy/.10)
        rgb.putalpha(Image.fromarray(np.clip(alpha*fade,0,255).astype(np.uint8)))
        earth_x, earth_y = -50, 815 if modern else 824
        # Extract the real alpha horizon before edge fades. This makes the red
        # time rail parallel to, and above, the atmosphere instead of crossing
        # through land as a hand-tuned unrelated Bezier did in the V5 baseline.
        raw_alpha = np.asarray(source.getchannel("A"))
        if modern:
            horizon=[]
            for x in range(source.width):
                ys=np.flatnonzero(raw_alpha[:,x]>135)
                horizon.append(float(ys[0])/self.s+earth_y if len(ys) else earth_y+target_h)
            self.earth_horizon_x=np.arange(source.width)/self.s+earth_x
            r=max(3,round(18*self.s))
            self.earth_horizon_y=np.convolve(np.pad(np.asarray(horizon),(r,r),mode="edge"),np.ones(2*r+1)/(2*r+1),mode="valid")
        else:
            self.earth_horizon_x=np.array([-50,0,200,400,600,770])
            self.earth_horizon_y=np.array([1110,1090,998,952,924,918])
        layer = self._new()
        layer.alpha_composite(rgb, (round(earth_x*self.s), round(earth_y*self.s)))
        mask = Image.new("L",layer.size,0)
        mask.paste(rgb.getchannel("A"),(round(earth_x*self.s),round(earth_y*self.s)))
        return layer, mask

    def _grid(self):
        layer = self._new()
        d = self._pen(layer)
        # Open perspective grid. It is decorative; actual candle coordinates stay
        # linear in price and trading-day index, with no per-candle exaggeration.
        for yy in range(300, 881, 72):
            d.line([(-20, yy+35), (740, yy-55)], fill=(29, 65, 84, 52), width=.6)
        for xx in range(25, 721, 66):
            d.line([(xx, 265), (xx+10, 886)], fill=(24, 58, 78, 52), width=.6)
        return layer

    def _glow_sprite(self, size, color, strength):
        n = max(3, round(size*self.s))
        y, x = np.mgrid[0:n, 0:n]
        r = np.sqrt((x-n/2)**2 + (y-n/2)**2)/(n/2)
        alpha = np.exp(-r*r*6.4) * strength * 255
        arr = np.zeros((n, n, 4), dtype=np.uint8)
        arr[:, :, :3] = color
        arr[:, :, 3] = alpha.astype(np.uint8)
        return Image.fromarray(arr)

    def _sprite(self, image, sprite, x, y, opacity=1.0):
        if opacity <= 0:
            return
        if opacity < .99:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel("A").point(lambda a: round(a*opacity)))
        image.alpha_composite(sprite, (round(x*self.s-sprite.width/2), round(y*self.s-sprite.height/2)))

    def _curve(self, u):
        u=clamp(u)
        x=-28+779*u
        y=float(np.interp(x,self.earth_horizon_x,self.earth_horizon_y))-19
        return x,y

    def _timeline_point(self, date):
        span = max(1, (self.timeline_end-self.timeline_start).days)
        u = clamp((pd.Timestamp(date)-self.timeline_start).days/span)
        return self._curve(u), u

    def _coords(self, state):
        # Clear chart zone is generous while leaving air above the earth.
        left, right, top, bottom = 26, 704, 250, 846
        span_i = max(1, state.window_end-state.window_start)
        span_y = max(1., state.y_max-state.y_min)
        def xp(index):
            return left + (index-state.window_start)/span_i*(right-left)
        def yp(price):
            return bottom - (price-state.y_min)/span_y*(bottom-top)
        return xp, yp

    def render(self, state):
        self.text_boxes = []
        self.critical_diagnostics = []
        self.active_track_count = 0
        image = self.background.copy()
        image.alpha_composite(self.grid)
        self._chart(image, state)
        image.alpha_composite(self.earth_layer)
        self._world(image, state)
        self._header(image, state)
        self._events(image, state)
        self._critical(image, state)
        self._rail(image, state)
        self._footer(image)
        return image.convert("RGB")

    def _header(self, image, state):
        d = self._pen(image, True)
        # Main title matches the approved poster's restrained visual hierarchy.
        en = self.style.get("title_en", "CHINEXT INDEX")
        spacing = 4.8
        xx = 70
        for ch in en:
            d.text((xx, 55), ch, self.fonts.get(9.5), (207, 216, 222, 235))
            xx += d.textlength(ch, self.fonts.get(9.5)) + spacing
        # One aggregate box for tracking measurement, not each glyph.
        self.text_boxes.append({"id":"title_en","bbox":[round(70*self.s),round(55*self.s),round(xx*self.s),round(71*self.s)],"role":"title","overlaps_allowed":False})
        d.line((57, 88, 57, 150), C["red"], 2.5)
        title = self.style.get("title_cn", "创业板指")
        d.text((71, 81), title, self.fonts.get(34, True), C["text"], id="title_cn", role="title")
        tw = d.textlength(title, self.fonts.get(34, True))
        d.text((80+tw, 95), f"({self.style.get('code','399006')})", self.fonts.get(21), C["text"], id="index_code", role="title")
        d.text((72, 140), self.style.get("subtitle", "中国创业板市场代表指数"), self.fonts.get(12), (188, 201, 211, 230), id="subtitle", role="title")
        d.text((668, 179), state.current_date.strftime("%Y.%m.%d"), self.fonts.get(14), (186,201,211,240), anchor="ra", id="current_date", role="status")
        d.text((668, 202), f"{state.current_close:,.2f}", self.fonts.get(24, True), C["text"], anchor="ra", id="current_close", role="status")
        d.text((668, 235), "当日收盘", self.fonts.get(10), (133,151,165,235), anchor="ra", id="current_close_label", role="status")

    def _chart(self, image, state):
        xp, yp = self._coords(state)
        market = self.model.market
        layer = self._new()
        d = self._pen(layer)
        px = 678/max(1,state.window_end-state.window_start)
        body_w = max(1.6, min(14.5, px*.73))
        for i in range(state.window_start, min(state.current_index,state.window_end)+1):
            x = xp(i)
            if not -15 < x < 735:
                continue
            o, h, l, c = (float(market.open[i]), float(market.high[i]),float(market.low[i]),float(market.close[i]))
            top, bottom = sorted([yp(o),yp(c)])
            color = C["red"] if c >= o else C["green"]
            # Avoid chart strokes escaping into the header or stage rail.
            yh, yl = max(252,yp(h)), min(866,yp(l))
            if yh > yl:
                continue
            d.line((x,yh,x,yl), rgba(color,.93), max(.7,body_w*.13))
            if bottom < 252 or top > 866:
                continue
            top, bottom = max(252,top), min(866,max(top+1.15,bottom))
            d.rectangle((x-body_w/2,top,x+body_w/2,bottom), fill=color)
            if body_w >= 5:
                # A crisp lit edge makes candles legible without permanent bloom.
                d.line((x-body_w/2+.5,top+.5,x-body_w/2+.5,bottom), rgba((255,255,255),.13), .6)
        image.alpha_composite(layer)
        cx,cy = xp(state.current_index),yp(state.current_close)
        if 249 < cy < 866:
            self._sprite(image,self.node_glow,cx,cy,.40)
            d = self._pen(image)
            d.line((cx,cy,704,cy), (145,174,187,65), .7)
            d.ellipse((cx-2.8,cy-2.8,cx+2.8,cy+2.8), fill=(255,246,228,242))

    def _world(self, image, state):
        current, u = self._timeline_point(state.current_date)
        layer = self._new()
        d = self._pen(layer)
        d.line(self.timeline_points, (110,30,32,160), 1.1)
        stop = max(2, min(len(self.timeline_points), round(u*180)+1))
        past = self.timeline_points[:stop]
        d.line(past, (255,62,46,36), 9)
        d.line(past, (255,58,45,95), 3.7)
        d.line(past, (255,94,73,245), 1.6)
        d.line(past, (255,222,182,145), .6)
        image.alpha_composite(layer)
        d = self._pen(image, True)
        active_year = state.current_date.year
        for year in self.timeline_years:
            if year > active_year:
                continue
            point,_ = self._timeline_point(pd.Timestamp(f"{year}-01-01"))
            x,y=point
            # A year whose real timeline anchor lies outside the frame is not
            # drawn; moving its label inward would imply a false date location.
            if x < 32 or x > 688:
                continue
            # Small elapsed-year nodes, with active year elevated in hierarchy.
            active = int(year)==active_year
            r=3.5 if active else 2.4
            d.ellipse((x-r,y-r,x+r,y+r),fill=(247,240,224,240))
            d.line((x,y-8,x,y-19),(206,218,225,145),.7)
            d.text((x,y-39),str(year),self.fonts.get(23 if active else 16, numeric=True),
                   C["text"] if active else (174,188,199,230),anchor="mm",id=f"timeline_year_{year}",role="timeline")
        x,y=current
        self._sprite(image,self.node_glow,x,y,1)
        d.ellipse((x-5.8,y-5.8,x+5.8,y+5.8),fill=(255,247,234,255),outline=(255,90,65,245),width=1)
        d.ellipse((x-11,y-11,x+11,y+11),outline=(255,122,91,170),width=.8)
        # Subtle red surface light remains inside photographed earth silhouette.
        reflection=self._new(); rd=self._pen(reflection)
        pulse=.5+.5*math.sin(state.t*3.5)
        rd.ellipse((x-30,y+20,x+32,y+124),fill=(255,70,40,round(10+10*pulse)))
        reflection.putalpha(Image.composite(reflection.getchannel("A"),Image.new("L",image.size,0),self.earth_mask))
        image.alpha_composite(reflection)
        for event in self.model.events:
            if state.t >= event.hit_t:
                (ex,ey),_=self._timeline_point(event.date)
                d.ellipse((ex-1.8,ey-1.8,ex+1.8,ey+1.8),fill=(255,188,149,170))

    def _event_alpha(self,event,t):
        # Preheat is a node pulse, not a prematurely dated text card.
        if t < event.hit_t or t >= event.hit_t+event.post_seconds:
            return 0.
        elapsed=t-event.hit_t
        return min(smooth(elapsed/.30),smooth((event.hit_t+event.post_seconds-t)/.40))

    def _events(self,image,state):
        active=[e for e in self.model.events if self._event_alpha(e,state.t)>.001]
        # A director configuration may keep an auxiliary year label active;
        # only one primary story card receives the main composition zone.
        active.sort(key=lambda e:(getattr(e,"importance","primary")!="primary",e.hit_t))
        for event in active[:1]:
            a=self._event_alpha(event,state.t)
            elapsed=state.t-event.hit_t
            xx,yy=64,318
            shift=(1-smooth(elapsed/.34))*8
            xx-=shift
            layer=self._new(); d=self._pen(layer,True)
            # Discreet local glass panel: border on one edge only.
            if event.type != "market_phenomenon":
                d.rounded_rectangle((xx-14,yy-13,xx+281,yy+117),radius=7,fill=(3,11,17,round(165*a)))
                d.line((xx-14,yy-8,xx-14,yy+109),rgba(C["gold"],.47*a),.7)
            label=getattr(event,"date_label",event.date.strftime("%Y.%m.%d"))
            datefont=self.fonts.get(15,True)
            labelw=max(91,d.textlength(label,datefont)+20)
            d.polygon([(xx+5,yy),(xx+labelw+5,yy),(xx+labelw-1,yy+29),(xx-1,yy+29)],fill=(211,39,36,round(246*a)))
            d.text((xx+labelw/2+2,yy+14),label,datefont,rgba(C["text"],a),anchor="mm",id=event.id+"_date",role="event")
            y=yy+43
            if event.type=="market_phenomenon":
                for j,line in enumerate(event.lines[:2]):
                    d.text((xx,y),line,self.fonts.get(19,True),rgba(C["text"],a),id=f"{event.id}_line{j}",role="event")
                    y+=30
                metric_value=getattr(event,"metric_value",None)
                metric_unit=getattr(event,"metric_unit","")
                if metric_value is None:
                    metric=str(event.metric or "")
                    found=re.search(r"[-+]?\d[\d,]*(?:\.\d+)?",metric)
                    if found:
                        metric_value=float(found.group().replace(",",""))
                        metric_unit=metric[found.end():]
                if metric_value is not None:
                    # Count-up is brief, then the exact verified terminal value holds.
                    value=float(metric_value)*smooth(max(0,elapsed-.25)/.95)
                    metric=f"{value:,.2f}{metric_unit}"
                else:
                    metric=str(event.metric or "")
                d.text((xx-1,y+3),metric,self.fonts.get(38,True),rgba((255,173,134),a),id=event.id+"_metric",role="event_metric")
                d.line((xx,y+68,xx+206,y+68),rgba(C["red"],a*.80),1.5)
                # Information-associated density pulse, restrained and deterministic.
                rng=random.Random(event.id)
                density=smooth(elapsed/.7)
                for i in range(18):
                    px=xx+247+rng.uniform(-23,23);py=yy+67+rng.uniform(-28,37)
                    r=rng.choice([.7,1.0,1.2])
                    d.ellipse((px-r,py-r,px+r,py+r),fill=(255,102,70,round(135*a*density)))
            else:
                for j,line in enumerate(event.lines[:2]):
                    d.text((xx,y),line,self.fonts.get(23 if len(line)<=12 else 19,True),rgba(C["text"],a),id=f"{event.id}_line{j}",role="event")
                    y+=33
                if event.metric:
                    d.text((xx,y+2),str(event.metric),self.fonts.get(23,True),rgba(C["gold"],a),id=event.id+"_metric",role="event_metric")
                d.line((xx,y+9,xx+166,y+9),rgba(C["red"],.80*a),1.4)
            # Date-to-candle confirmation is a short local pulse, never an arrow
            # connecting a policy card to a later high/low.
            if elapsed<.55 and state.current_index==event.index:
                xp,yp=self._coords(state);ax,ay=xp(event.index),yp(float(self.model.market.close[event.index]))
                d.ellipse((ax-5,ay-5,ax+5,ay+5),outline=rgba(C["gold"],a),width=1)
            image.alpha_composite(layer)

    def _critical(self,image,state):
        xp,yp=self._coords(state)
        for cp in self.model.critical_points:
            if state.t<cp.hit_t:
                continue
            x,y=xp(cp.index),yp(cp.price)
            visible=26<=x<=704 and 252<=y<=866
            self.critical_diagnostics.append({"id":cp.id,"x":x*self.s,"y":y*self.s,"visible":visible})
            held=state.t<=cp.hold_until
            is_high="high" in cp.id
            # The remembered high remains a thin truthful price reference.
            if cp.leave_anchor and is_high and 252<y<867:
                memory_layer=self._new()
                d=self._pen(memory_layer,True)
                d.line((27,y,704,y),(255,185,102,90),.7)
                if not held:
                    d.text((692,y-12),f"{cp.price:,.2f}",self.fonts.get(10), (235,194,136,220),anchor="ra",id=cp.id+"_memory",role="anchor")
                image.alpha_composite(memory_layer)
            if not visible:
                continue
            elapsed=state.t-cp.hit_t
            fade=smooth(elapsed/.28)
            # Soft broad glow + crisp hot center + hairline lens flare.
            intensity=.54+.11*math.sin(elapsed*2.2) if held else .18
            self._sprite(image,self.gold_glow,x,y,intensity*fade)
            d=self._pen(image,True)
            if held:
                d.line((x-105,y,x+112,y),(244,155,74,75),.7)
                d.line((x-42,y,x+45,y),(255,194,111,120),.7)
                for rr,alpha in [(12,175),(23,84)]:
                    r=rr*(.8+.2*fade)
                    d.ellipse((x-r,y-r,x+r,y+r),outline=(255,185,108,round(alpha*fade)),width=.7)
            d.ellipse((x-4,y-4,x+4,y+4),fill=(255,250,231,round(250*fade)))
            if not held:
                continue
            # Date, value and tag constitute one label; choose the less crowded
            # side, then clamp to the safe composition zone.
            tx=clamp(x-115,60,409)
            ty=max(276,min(598,y-169)) if is_high else max(385,min(622,y-165))
            if is_high and y<405:
                ty=270
                tx=clamp(x-270,55,360)
            layer=self._new(); p=self._pen(layer,True)
            label_width=max(222,p.textlength(f"{cp.price:,.2f}",self.fonts.get(42,numeric=True))+22)
            # Thin asymmetric open plaque, no heavy gold frame or metal bevel.
            p.polygon([(tx+9,ty-6),(tx+label_width,ty-6),(tx+label_width+8,ty+110),(tx-13,ty+110)],fill=(4,11,16,round(205*fade)))
            p.line([(tx+8,ty-6),(tx-13,ty+110),(tx+label_width-12,ty+110)],rgba(C["gold"],fade*.75),.8)
            p.text((tx+2,ty+4),cp.date.strftime("%Y.%m.%d"),self.fonts.get(19,numeric=True),rgba(C["text"],fade),id=cp.id+"_date",role="critical")
            p.text((tx,ty+34),f"{cp.price:,.2f}",self.fonts.get(42,numeric=True),rgba(C["gold_light"],fade),id=cp.id+"_price",role="critical")
            tagw=max(94,p.textlength(cp.label,self.fonts.get(17,True))+22)
            p.polygon([(tx+3,ty+86),(tx+tagw+5,ty+86),(tx+tagw,ty+115),(tx-2,ty+115)],fill=(207,38,33,round(246*fade)))
            p.text((tx+tagw/2+1,ty+100),cp.label,self.fonts.get(17,True),rgba(C["text"],fade),anchor="mm",id=cp.id+"_label",role="critical")
            # Leader ends at actual closing-price coordinate, never the wick high.
            edge_x=tx+label_width*.75;edge_y=ty+110
            p.line([(edge_x,edge_y),(x-12,y-14),(x,y)],rgba(C["gold"],fade*.68),.7)
            image.alpha_composite(layer)

    def _rail(self,image,state):
        layer=self._new()
        d=self._pen(layer,True)
        self.active_track_count += 1
        mode=getattr(state,"stage_mode","rise_from_low")
        color=C["blue"] if "drawdown" in mode else C["red"]
        for hit, previous, current in self.stage_transitions:
            if hit <= state.t < hit+.42:
                old = C["blue"] if "drawdown" in previous else C["red"]
                u=smooth((state.t-hit)/.42)
                color=tuple(round(old[i]*(1-u)+color[i]*u) for i in range(4))
        label=getattr(state,"stage_label","阶段上涨")
        value=float(getattr(state,"stage_value",0.0))
        progress=clamp(getattr(state,"stage_progress",0.0))
        x0,x1,y=66,656,1142
        # One active stage rail; prior stages are a tiny non-track memory.
        d.text((x0,y-29),label,self.fonts.get(15), (218,229,235,245),id="stage_label",role="rail")
        d.text((x1,y-39),f"{value*100:+.2f}%",self.fonts.get(29,numeric=True),color,anchor="ra",id="stage_value",role="rail")
        d.line((x0,y,x1,y),(62,84,98,120),2.5)
        end=x0+(x1-x0)*progress
        if end>x0+1:
            d.line((x0,y,end,y),rgba(color,.12),7)
            d.line((x0,y,end,y),rgba(color,.45),3.5)
            d.line((x0,y,end,y),color,2)
            d.ellipse((end-3,y-3,end+3,y+3),fill=(248,248,242,255))
        milestones=getattr(state,"completed_milestones",())
        if milestones:
            m=milestones[-1]
            text=f"已完成  {m.get('label','阶段上涨')}  {float(m.get('value',0))*100:+.2f}%"
            d.text((x0,y+20),text,self.fonts.get(10), (162,177,190,235),id="completed_milestone",role="milestone")
        d.line((66,1090,656,1090),(65,90,104,100),.7)
        image.alpha_composite(layer)

    def _footer(self,image):
        d=self._pen(image,True)
        d.text((360,1207),"日线开高低收 · 价格指数 · 不含分红",self.fonts.get(10), (137,155,169,235),anchor="mm",id="data_basis",role="footer")
        d.text((360,1229),"东方财富公开接口  /  数据截至 2026.11.10",self.fonts.get(9), (113,132,147,230),anchor="mm",id="data_source",role="footer")

    def get_layout_diagnostics(self,state):
        self.render(state)
        return {"width":self.w,"height":self.h,"text_boxes":list(self.text_boxes),
                "active_track_count":self.active_track_count,"critical_points":list(self.critical_diagnostics)}
