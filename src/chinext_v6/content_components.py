"""Shared content layers for the silent production master.

The layer consumes selected master text, never invents a news page, archive
photo, market value or historical cause. ``overlay`` can be composed over the
main renderer; ``render`` supplies an independent, truthful component preview.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from .drawing import C, Fonts, SceneDrawer, clamp, smooth
from .model import MarketData


KINDS = ("stage", "event", "timeline", "quote", "headline", "document",
         "album", "closing", "return")


def component_for(node: dict, beat: dict) -> str:
    """Select one focal template; no permanent stack of four content panels."""
    if node["id"] == "C03":
        return "return"
    if len(beat["screen_lines"]) == 1:
        return "closing"
    if node.get("role") == "album":
        return "album"
    if node.get("role") == "closing":
        return "closing"
    if beat.get("direct_quotes"):
        return "quote"
    if "报道摘要" in beat["screen_lines"][0] or "媒体原题" in beat["screen_lines"][0]:
        return "headline"
    if node["id"] in {"S11", "S14"}:
        return "timeline"
    if any(s.startswith("AR") for s in node["source_ids"]):
        return "document"
    return "event"


class ContentDrawer:
    """Resolution independent content compositor using a 720×1280 space.

    ``progress`` is local to the selected beat, in [0, 1]. Entry and exit take
    0.3 and 0.4 seconds of that beat, leaving its reading budget intact. The
    final C03 frame stays visible. Callers must preserve the master's beat
    duration when building a film; the envelope is not proof of readability.
    """

    def __init__(self, root: str | Path, width: int = 1080, master: dict | None = None):
        self.root = Path(root)
        self.w = int(width)
        self.h = round(self.w * 16 / 9)
        if self.w < 360 or self.w % 2 or self.h % 2:
            raise ValueError("width must give even 9:16 dimensions and be at least 360")
        self.s = self.w / 720
        self.master = master or json.loads((self.root / "config/production/film_master_v1.json").read_text())
        self.nodes = {n["id"]: n for n in self.master["nodes"]}
        self.phases = {p["id"]: p for p in self.master["phases"]}
        self.market = MarketData(self.root / "data/cyb_daily.csv")
        self.fonts = Fonts(self.s, "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                           "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
        # Reuse approved static art/candle/orbit machinery. This deliberately
        # supplies no sample events, extrema, or rails that could leak into the
        # new component preview at the wrong historical date.
        model = SimpleNamespace(video={"width": self.w, "height": self.h}, style={},
                                states=[], market=self.market, events=[],
                                config={"sample": {"timeline_start": "2008-01-01",
                                                   "timeline_end": "2029-01-01",
                                                   "timeline_years": [2010, 2012, 2015, 2018, 2021, 2024, 2026]}})
        self.base = SceneDrawer(model, self.root / "assets")
        self.text_boxes: list[dict] = []
        self._last_metadata: dict = {}
        self._preview_bases: dict[tuple, Image.Image] = {}

    @property
    def width(self):
        return self.w

    @property
    def height(self):
        return self.h

    def _rect(self, box):
        return tuple(round(x * self.s) for x in box)

    def _new(self):
        return Image.new("RGBA", (self.w, self.h))

    def _text(self, im, xy, text, size, *, fill=None, bold=False, numeric=False,
              anchor="la", ident="text", role="body"):
        draw = ImageDraw.Draw(im)
        font = self.fonts.get(size, bold=bold, numeric=numeric)
        pos = tuple(v * self.s for v in xy)
        draw.text(pos, text, font=font, fill=fill or C["text"], anchor=anchor)
        box = draw.textbbox(pos, text, font=font, anchor=anchor)
        self.text_boxes.append({"id": ident, "text": text, "bbox": list(box), "role": role})
        return box

    def _width(self, text, size, bold=False):
        return ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=self.fonts.get(size, bold)) / self.s

    def _wrap(self, text, size, width, bold=False):
        # Keep numeric/date/Latin tokens intact; never break 413.03 or 1,000.
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9,.%/+−—\-]*|.", str(text))
        lines, current = [], ""
        for token in tokens:
            proposed = current + token
            if current and self._width(proposed, size, bold) > width:
                lines.append(current)
                current = token
            else:
                current = proposed
        if current:
            lines.append(current)
        return lines

    def _paragraph(self, im, xy, text, size, width, *, fill=None, bold=False,
                   leading=1.48, ident="paragraph", role="body"):
        x, y = xy
        for i, line in enumerate(self._wrap(text, size, width, bold)):
            self._text(im, (x, y), line, size, fill=fill, bold=bold,
                       ident=f"{ident}_{i}", role=role)
            y += size * leading
        return y

    def _selection(self, node_id, beat_index):
        if node_id not in self.nodes:
            raise ValueError(f"unknown production node: {node_id}")
        node = self.nodes[node_id]
        if not 0 <= beat_index < len(node["beats"]):
            raise IndexError(f"beat outside {node_id}: {beat_index}")
        return node, node["beats"][beat_index]

    def _state(self, beat):
        value = beat.get("market_anchor")
        if not value:
            # Coarse-date facts keep their precision. For a standalone art
            # preview only, a month/year uses its last observed trading day,
            # marked in diagnostics as an observation rather than an event day.
            historical = beat.get("historical_date") or "2026-11-10"
            if beat.get("date_precision") == "month":
                end = pd.Timestamp(historical) + pd.offsets.MonthEnd(0)
            elif beat.get("date_precision") == "year":
                end = pd.Timestamp(historical + "-12-31")
            else:
                return None
            valid = self.market.dates[self.market.dates <= end]
            if not len(valid):
                return None
            value = valid[-1]
        i = self.market.index_for_date(value)
        first, last = max(0, i - 94), min(len(self.market.df) - 1, i + 16)
        lows = self.market.low[first:i+1]
        highs = self.market.high[first:i+1]
        low, high = float(min(lows)), float(max(highs))
        spread = max(high - low, high * .08)
        return SimpleNamespace(current_index=i, current_close=float(self.market.close[i]),
                               current_date=self.market.dates[i], window_start=first,
                               window_end=last, y_min=low-spread*.13, y_max=high+spread*.20,
                               t=0.0)

    def _preview_background(self, node, beat, kind):
        key = (node["id"], node["beats"].index(beat), kind)
        if key in self._preview_bases:
            return self._preview_bases[key].copy()
        im = self.base.background.copy()
        self.base.text_boxes = []
        state = self._state(beat)
        im.alpha_composite(self.base.grid)
        if state and kind not in {"album", "closing", "return", "stage"}:
            self.base._chart(im, state)
        im.alpha_composite(self.base.earth_layer)
        if state and kind != "album":
            self.base._world(im, state)
        else:
            d = ImageDraw.Draw(im)
            d.line([(round(x*self.s), round(y*self.s)) for x,y in self.base.timeline_points],
                   fill=(255, 82, 61, 190), width=max(1,round(1.4*self.s)))
            if state:
                (xx,yy),_=self.base._timeline_point(state.current_date)
                d.ellipse(self._rect((xx-4,yy-4,xx+4,yy+4)),fill=C["gold_light"])
        self._static_header(im)
        if state and kind not in {"album", "closing", "return", "stage"}:
            self._text(im,(666,178),state.current_date.strftime("%Y.%m.%d"),14,
                       fill=C["muted"],anchor="ra",ident="hud_date",role="status")
            self._text(im,(666,202),f"{state.current_close:,.2f}",24,bold=True,
                       anchor="ra",ident="hud_close",role="status")
            self._text(im,(666,236),beat.get("hud_label","当日收盘"),10,
                       fill=C["muted"],anchor="ra",ident="hud_label",role="status")
        if kind != "return":
            self._text(im,(360,1207),"日线开高低收 · 价格指数 · 不含分红",10,
                       fill=C["muted"],anchor="mm",ident="footer_basis",role="footer")
            self._text(im,(360,1229),"东方财富公开接口 / 数据截至2026.11.10",9,
                       fill=(113,132,147,255),anchor="mm",ident="footer_source",role="footer")
        # Keep diagnostics for static text alongside each cached image.
        self._preview_bases[key] = im.copy()
        self._preview_bases[(key,"boxes")] = list(self.text_boxes)
        return im

    def _static_header(self, im):
        self._text(im,(72,55),"C H I N E X T   I N D E X",9.5,
                   fill=(207,216,222,255),ident="header_en",role="header")
        draw = ImageDraw.Draw(im)
        draw.line(self._rect((57,88,57,150)), fill=C["red"], width=max(1,round(2.5*self.s)))
        self._text(im,(71,82),"创业板指",34,bold=True,ident="header_cn",role="header")
        self._text(im,(221,96),"(399006)",21,ident="header_code",role="header")
        self._text(im,(72,141),"中国创业板市场代表指数",12,
                   fill=(188,201,211,255),ident="header_subtitle",role="header")

    def _phase_context(self, im, node):
        phase = self.phases.get(node["phase_id"])
        if not phase:
            return
        # Keep context in the left HUD band: high candles can reach y=250,
        # and must not pass through the stage wording during an extremum.
        self._text(im,(65,219),phase["title"],13,fill=(156,173,185,255),
                   ident="phase_context",role="context")

    def _source(self, im, beat, x, y, width):
        if beat.get("source_line"):
            return self._paragraph(im,(x,y),beat["source_line"],11.5,width,
                                   fill=(166,185,198,255),leading=1.5,
                                   ident="source",role="source")
        return y

    def _event(self, im, node, beat, timeline=False):
        lines = beat["screen_lines"]
        main_width = 367
        layout = []
        y = 344
        for index, text in enumerate(lines[1:]):
            numeric = bool(re.fullmatch(r"[+−\-]?[\d,.]+(?:%|万户|元)?",text))
            size = 43 if numeric else 27
            rendered = self._wrap(text,size,main_width,True)
            layout.append((y,text,size,numeric,index))
            y += len(rendered)*size*1.48+7
        bottom = max(y+57, 484)
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle(self._rect((48,303,449,bottom)),radius=round(7*self.s),fill=(3,11,17,221))
        draw.line(self._rect((48,309,48,bottom-7)),fill=(255,209,138,190),width=max(1,round(self.s)))
        self._text(im,(65,314),lines[0],15.5,bold=True,fill=C["gold"],ident="event_date",role="date")
        for yy,text,size,numeric,index in layout:
            self._paragraph(im,(65,yy),text,size,main_width,bold=True,
                            fill=C["gold_light"] if numeric else C["text"],ident=f"event_line_{index}")
        self._source(im,beat,65,y+8,main_width)
        if timeline:
            entries=[]
            # A timeline is accumulated history. Future policy dates must not
            # be announced by the first card in this node.
            current_beat=node["beats"].index(beat)
            for b in node["beats"][:current_beat+1]:
                title=b["screen_lines"][0]
                if re.match(r"\d{4}\.",title) and title not in entries:
                    entries.append(title)
            yy=bottom+40
            xs=[65+i*min(132,540/max(1,len(entries)-1)) for i in range(len(entries))]
            if len(xs)>1:
                draw.line([(round(x*self.s),round(yy*self.s)) for x in xs],fill=(116,93,70,160),width=max(1,round(self.s)))
            for i,(x,label) in enumerate(zip(xs,entries)):
                active=label==lines[0]
                r=4 if active else 2.5
                draw.ellipse(self._rect((x-r,yy-r,x+r,yy+r)),fill=C["gold"] if active else (136,119,100,255))
                short=label[5:]
                self._text(im,(x,yy+16),short,11,fill=C["gold"] if active else C["muted"],
                           anchor="ma",ident=f"timeline_date_{i}",role="timeline")

    def _wide_card(self, im, node, beat, kind):
        draw=ImageDraw.Draw(im)
        lines=beat["screen_lines"]
        quote=kind=="quote"
        size=33 if quote else 29
        y=378
        for text in lines[1:]:
            y+=len(self._wrap(text,size,550,True))*size*1.6+12
        bottom=max(y+76,604 if quote else 566)
        draw.rounded_rectangle(self._rect((49,314,668,bottom)),radius=round(8*self.s),fill=(3,11,17,237))
        draw.line(self._rect((63,329,63,bottom-18)),fill=(255,209,138,180),width=max(1,round(self.s)))
        self._text(im,(82,337),lines[0],16,bold=True,fill=C["gold"],ident="card_kicker",role="date")
        yy=378
        for i,text in enumerate(lines[1:]):
            yy=self._paragraph(im,(82,yy),text,size,550,bold=True,
                               fill=C["gold_light"] if quote else C["text"],
                               leading=1.6,ident=f"card_line_{i}")+12
        draw.line(self._rect((82,bottom-58,634,bottom-58)),fill=(109,129,143,90),width=max(1,round(.6*self.s)))
        self._source(im,beat,82,bottom-43,550)

    def _history_crop(self, im, beat, box):
        state=self._state(beat)
        if state is None:
            return
        left,top,right,bottom=box
        start=max(0,state.current_index-130)
        end=state.current_index
        lo=min(self.market.low[start:end+1]); hi=max(self.market.high[start:end+1])
        spread=max(hi-lo,hi*.06)
        lo-=spread*.10; hi+=spread*.12
        d=ImageDraw.Draw(im)
        for j in range(5):
            y=top+(bottom-top)*j/4
            d.line(self._rect((left,y,right,y)),fill=(31,61,78,95),width=max(1,round(.6*self.s)))
        for i in range(start,end+1):
            x=left+(i-start)/max(1,end-start)*(right-left)
            o,h,l,c=(float(getattr(self.market,k)[i]) for k in ("open","high","low","close"))
            yp=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
            color=C["red"] if c>=o else C["green"]
            d.line(self._rect((x,yp(h),x,yp(l))),fill=color,width=max(1,round(.6*self.s)))
            a,b=sorted((yp(o),yp(c)))
            d.rectangle(self._rect((x-1.0,a,x+1.0,max(a+.7,b))),fill=color)

    def _album(self, im, node, beat):
        d=ImageDraw.Draw(im)
        d.rounded_rectangle(self._rect((53,292,668,878)),radius=round(5*self.s),fill=(2,10,16,247),outline=(132,110,80,175),width=max(1,round(.8*self.s)))
        # Small offset edge evokes an album leaf, not a simulated newspaper.
        d.line([self._rect((62,885)),self._rect((660,885)),self._rect((676,870)),self._rect((676,306))],
               fill=(119,103,81,125),width=max(1,round(.7*self.s)))
        header=beat["screen_lines"][0]
        year,separator,title=header.partition("｜")
        self._text(im,(83,321),year,53,bold=True,fill=C["gold_light"],ident="album_year",role="album")
        if title:
            self._text(im,(240,344),title,20,fill=C["text"],ident="album_theme",role="album")
        if node["id"] in {"A02","A03"}:
            # Repeat the actual index title next to this history image so the
            # company caption cannot make viewers read it as a stock chart.
            label=self.master["persistent_screen_copy"]["header"][1]
            self._text(im,(86,401),label,11,fill=C["muted"],ident="album_chart_basis",role="source")
            self._history_crop(im,beat,(86,428,634,684))
            y=725
            for i,text in enumerate(beat["screen_lines"][1:]):
                y=self._paragraph(im,(87,y),text,25,540,bold=True,ident=f"album_caption_{i}")+8
            self._source(im,beat,87,829,540)
        else:
            # Only selected master text is re-typeset; no fake body paragraphs,
            # unsupported original headline, publisher logo, or placeholder photo.
            d.line(self._rect((86,421,634,421)),fill=(150,126,91,130),width=max(1,round(.7*self.s)))
            y=484
            for i,text in enumerate(beat["screen_lines"][1:]):
                y=self._paragraph(im,(88,y),text,34,540,bold=True,
                                  fill=C["gold_light"],leading=1.65,ident=f"album_document_{i}")+22
            self._source(im,beat,88,814,540)

    def _closing(self, im, node, beat, returning=False):
        lines=beat["screen_lines"]
        y=430 if not returning else 455
        for i,text in enumerate(lines[:2] if returning else lines):
            size=27 if not returning else (22 if i==0 else 42 if i==1 else 12)
            color=C["gold_light"] if returning and i==1 else C["text"] if i<2 else C["muted"]
            wrapped=self._wrap(text,size,585,True)
            for j,line in enumerate(wrapped):
                self._text(im,(360,y),line,size,bold=i<2,fill=color,anchor="ma",
                           ident=f"closing_{i}_{j}",role="closing")
                y+=size*1.7
            y+=24 if i<2 else 6
        if returning:
            # The last two master lines explicitly reuse the permanent footer
            # positions; they are not a second central reading block. A caller
            # composing this return layer must omit its own base footer.
            for i,text in enumerate(lines[2:]):
                self._text(im,(360,1207+i*22),text,10 if i==0 else 9,
                           fill=C["muted"],anchor="mm",ident=f"return_footer_{i}",role="footer")

    def content_layer(self, node_id: str, beat_index: int = 0,
                      kind: str | None = None) -> Image.Image:
        """Return a fully visible transparent RGBA layer for caller-side cache.

        There is no background or entry/exit opacity. The ``return`` template
        owns its footer region; omit the base composer's footer for that beat.
        Text diagnostics remain
        available in ``text_boxes``; callers can composite this layer many times
        while advancing the real market state, without redoing text layout.
        """
        node,beat=self._selection(node_id,beat_index)
        kind=kind or component_for(node,beat)
        if kind not in KINDS:
            raise ValueError(f"unsupported component: {kind}")
        self.text_boxes=[]
        layer=self._new()
        if kind=="stage":
            phase=self.phases.get(node["phase_id"])
            if not phase:
                raise ValueError("stage component requires a production phase")
            self._paragraph(layer,(67,414),phase["title"],37,590,bold=True,ident="stage_title",role="context")
        else:
            self._phase_context(layer,node)
            if kind in {"event","timeline"}:
                self._event(layer,node,beat,kind=="timeline")
            elif kind in {"quote","headline","document"}:
                self._wide_card(layer,node,beat,kind)
            elif kind=="album":
                self._album(layer,node,beat)
            elif kind in {"closing","return"}:
                self._closing(layer,node,beat,kind=="return")
        self._last_metadata={"node_id":node_id,"beat_index":beat_index,"kind":kind,
                             "progress":None,"opacity":1.0,
                             "source_ids":node["source_ids"],
                             "market_anchor":beat.get("market_anchor"),
                             "historical_date":beat.get("historical_date"),
                             "date_precision":beat.get("date_precision"),
                             "synthetic_archive_photography":False}
        return layer

    def overlay(self, image: Image.Image, node_id: str, beat_index: int = 0,
                progress: float = .5, kind: str | None = None) -> Image.Image:
        """Compose content over a caller-owned truthful chart/background.

        Header, HUD, earth and stage rail remain the caller's responsibility.
        Diagnostics contain this overlay's text only; call ``render`` to obtain
        complete standalone preview diagnostics.
        """
        if image.size != (self.w,self.h):
            raise ValueError("background dimensions must match ContentDrawer")
        node,beat=self._selection(node_id,beat_index)
        layer=self.content_layer(node_id,beat_index,kind)
        elapsed=clamp(progress)*float(beat["duration_seconds"])
        entry=smooth(elapsed/.30)
        exit=1.0 if node_id=="C03" else smooth((float(beat["duration_seconds"])-elapsed)/.40)
        opacity=min(entry,exit)
        if opacity<1:
            layer.putalpha(layer.getchannel("A").point(lambda a:round(a*opacity)))
        im=image.convert("RGBA")
        im.alpha_composite(layer)
        self._last_metadata.update(progress=float(progress),opacity=opacity)
        return im.convert("RGB")

    def render(self, node_id: str, beat_index: int = 0, progress: float = .5,
               kind: str | None = None, background: Image.Image | None = None):
        node,beat=self._selection(node_id,beat_index)
        kind=kind or component_for(node,beat)
        self.text_boxes=[]
        if background is None:
            background=self._preview_background(node,beat,kind)
            static=list(self._preview_bases[((node_id,beat_index,kind),"boxes")])
        else:
            static=[]
        result=self.overlay(background,node_id,beat_index,progress,kind)
        self.text_boxes=static+self.text_boxes
        return result

    def diagnostics(self, node_id: str, beat_index: int = 0, progress: float = .5,
                    kind: str | None = None):
        self.render(node_id,beat_index,progress,kind)
        bad=[]
        for box in self.text_boxes:
            a,b,c,d=box["bbox"]
            if a<0 or b<0 or c>self.w or d>self.h:
                bad.append(box)
        return {"width":self.w,"height":self.h,**self._last_metadata,
                "text_boxes":list(self.text_boxes),"out_of_bounds":bad,
                "actual_readability_review":"pending_representative_sample"}
