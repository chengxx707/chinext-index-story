"""Representative master-driven scenes, reusable layers and checked assembly.

This is the representative gate: the 2015 content sample, the selected album
and a declared rewind are supported. It is not a finished eight-stage film.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw

from .content_components import ContentDrawer, component_for
from .drawing import C, SceneDrawer, smooth
from .model import SceneModel
from .production import ProductionTimeline
from .renderer import encode_frames
from .scene_cache import SceneCache, concat_segments, file_sha256


SUPPORTED_BODY = tuple(f"S{i:02d}" for i in range(7, 16))
SUPPORTED_ENDING = ("A01", "A02", "A03", "A04", "A05", "C01", "C02", "C03")
SUPPORTED_NODES = frozenset((*SUPPORTED_BODY, *SUPPORTED_ENDING, "H04"))
MOTION_MODE = "continuous_historical_annotations_v1"
_MODULE_DIR = Path(__file__).resolve().parent
_IMPORTED_CODE_HASHES = {_MODULE_DIR/name:file_sha256(_MODULE_DIR/name) for name in
    ["film_renderer.py","production.py","model.py","drawing.py","content_components.py","renderer.py","scene_cache.py"]}


@dataclass(frozen=True)
class NodePlan:
    node_id: str
    node: dict[str, Any]
    start_frame: int
    end_frame_exclusive: int
    config: dict[str, Any]
    config_path: Path
    events_path: Path
    beat_timings: tuple[dict[str, Any], ...]
    previous_observation: str | None
    next_observation: str | None
    cache_key: str
    signature_extra: dict[str, Any]

    @property
    def total_frames(self):
        return self.end_frame_exclusive-self.start_frame


def _write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


class FilmScene:
    def __init__(self, root: Path, timeline: ProductionTimeline, plan: NodePlan, width: int):
        self.root, self.timeline, self.plan = root, timeline, plan
        self.model = SceneModel(plan.config_path, plan.events_path, root/"data/cyb_daily.csv")
        self.drawer = SceneDrawer(self.model, root/"assets")
        self.content = ContentDrawer(root, width=width, master=timeline.master)
        self.layers: dict[int, Image.Image] = {}
        self.overlay_boxes: dict[int, list[dict]] = {}
        for index in range(len(plan.node["beats"])):
            self.layers[index] = self.content.content_layer(plan.node_id, index)
            self.overlay_boxes[index] = list(self.content.text_boxes)
        self.last_layout: dict[str, Any] = {}

    def frame_context(self, local_frame: int) -> dict[str, Any]:
        if not 0 <= local_frame < self.plan.total_frames:
            raise IndexError("Scene frame outside its half-open frame range")
        global_frame = self.plan.start_frame+local_frame
        beat_index = self.timeline.state_at_frame(global_frame).beat_index
        timing = self.plan.beat_timings[beat_index]
        state = self.model.state(local_frame)
        elapsed = (local_frame-timing["start_frame"])/self.model.fps
        duration = (timing["end_frame_exclusive"]-timing["start_frame"])/self.model.fps
        delay = timing["content_delay_seconds"]
        entry = .25 if delay else .30
        exit_seconds = .30 if delay else .40
        opacity = smooth((elapsed-delay)/entry)
        if self.plan.node_id != "C03":
            opacity = min(opacity, smooth((duration-elapsed)/exit_seconds))
        role = self.plan.node["role"]
        visible = timing["observation_date"] is not None
        show_market = visible and role == "main"
        raw = self.plan.node["beats"][beat_index]
        hud_label = raw.get("hud_label", "当日收盘")
        current_date = state.current_date.strftime("%Y-%m-%d")
        if current_date != timing["observation_date"]:
            hud_label = "当日收盘"
        return {"node_id": self.plan.node_id, "beat_index": beat_index,
            "global_frame": global_frame, "local_frame": local_frame,
            "current_date": current_date, "current_close": float(state.current_close),
            "market_index": state.current_index,
            "content_anchor_date": timing["observation_date"],
            "historical_date": raw.get("historical_date"),
            "date_precision": raw.get("date_precision", "day"),
            "content_opacity": float(opacity), "content_visible": opacity > .001,
            "hud_label": hud_label, "show_hud": show_market,
            "show_chart": show_market, "show_rail": show_market,
            "market_is_advancing": current_date != timing["observation_date"],
            "clock_mode": MOTION_MODE,
            "historical_annotation_while_market_advances": True}

    def frame(self, local_frame: int) -> Image.Image:
        context = self.frame_context(local_frame)
        state = self.model.state(local_frame)
        drawer = self.drawer
        drawer.text_boxes, drawer.critical_diagnostics, drawer.active_track_count = [], [], 0
        image = drawer.background.copy()
        image.alpha_composite(drawer.grid)
        if context["show_chart"]:
            drawer._chart(image, state)
            high_index = self.model.market.index_for_date("2015-06-03")
            if state.current_index >= high_index:
                xp, yp = drawer._coords(state)
                yy = yp(float(self.model.market.close[high_index]))
                if 252 < yy < 846:
                    d = drawer._pen(image, True)
                    d.line((27, yy, 704, yy), (255,185,102,90), .7)
                    d.text((692, yy-12), "3,982.25", drawer.fonts.get(10),
                           (235,194,136,220), anchor="ra", id="old_high_memory", role="anchor")
            if self.plan.node_id in {"S09", "S15"}:
                timing = self.plan.beat_timings[context["beat_index"]]
                index = self.model.market.index_for_date(timing["observation_date"])
                xp, yp = drawer._coords(state)
                xx, yy = xp(index), yp(float(self.model.market.close[index]))
                if 26 <= xx <= 704 and 252 <= yy <= 846:
                    drawer._sprite(image, drawer.gold_glow, xx, yy, .46*context["content_opacity"])
                    drawer._pen(image).ellipse((xx-3, yy-3, xx+3, yy+3), fill=C["gold_light"])
        image.alpha_composite(drawer.earth_layer)
        world_state = state
        if self.plan.node_id == "H04":
            u = local_frame/max(1, self.plan.total_frames-1)
            first, last = pd.Timestamp("2026-05-13"), pd.Timestamp("2010-06-01")
            world_state = replace(state, current_date=first+(last-first)*smooth(u))
        drawer._world(image, world_state)
        # Reuse the approved header while owning the HUD's prior-day label.
        header = drawer._new()
        drawer._header(header, state)
        ImageDraw.Draw(header).rectangle((round(350*drawer.s),round(169*drawer.s),
                                         round(711*drawer.s),round(252*drawer.s)), fill=(0,0,0,0))
        drawer.text_boxes = [b for b in drawer.text_boxes if b["role"] != "status"]
        image.alpha_composite(header)
        if context["show_hud"]:
            d = drawer._pen(image, True)
            d.text((668,179),state.current_date.strftime("%Y.%m.%d"),drawer.fonts.get(14),
                   (186,201,211,240),anchor="ra",id="current_date",role="status")
            d.text((668,202),f"{state.current_close:,.2f}",drawer.fonts.get(24,True),C["text"],
                   anchor="ra",id="current_close",role="status")
            d.text((668,235),context["hud_label"],drawer.fonts.get(10),(133,151,165,235),
                   anchor="ra",id="current_close_label",role="status")
        if context["show_rail"]:
            drawer._rail(image, state)
        if self.plan.node_id != "C03":
            drawer._footer(image)
        layer = self.layers[context["beat_index"]]
        opacity = context["content_opacity"]
        if opacity < .999:
            layer = layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda a: round(a*opacity)))
        image.alpha_composite(layer)
        boxes = list(drawer.text_boxes)
        if opacity > .001:
            boxes += self.overlay_boxes[context["beat_index"]]
        outside = [b for b in boxes if b["bbox"][0] < 0 or b["bbox"][1] < 0 or
                   b["bbox"][2] > drawer.w or b["bbox"][3] > drawer.h]
        overlaps = []
        for i, a in enumerate(boxes):
            for b in boxes[i+1:]:
                ax,ay,ar,ab = a["bbox"]; bx,by,br,bb = b["bbox"]
                if min(ar,br)-max(ax,bx) > 1 and min(ab,bb)-max(ay,by) > 1:
                    overlaps.append([a["id"], b["id"]])
        self.last_layout = {**context,"width":drawer.w,"height":drawer.h,"text_boxes":boxes,
            "out_of_bounds":outside,"text_overlaps":overlaps,"active_track_count":drawer.active_track_count,
            "actual_readability_review":"pending_representative_playback"}
        return image.convert("RGB")


_WORKER_SCENE = None


def _worker_init(root, master_path, plan, width):
    global _WORKER_SCENE
    root = Path(root)
    _WORKER_SCENE = FilmScene(root, ProductionTimeline(master_path, root=root), plan, width)


def _worker_frame(n):
    return _WORKER_SCENE.frame(n).tobytes()


class FilmRenderer:
    def __init__(self, root: str | Path, *, master_path: str | Path | None = None,
                 width: int = 1080, output_dir: str | Path | None = None,
                 cache_dir: str | Path | None = None):
        self.root = Path(root).resolve()
        self.master_path = Path(master_path or self.root/"config/production/film_master_v1.json").resolve()
        master_bytes=self.master_path.read_bytes()
        self.master_sha256=hashlib.sha256(master_bytes).hexdigest()
        self.timeline = ProductionTimeline(self.master_path, root=self.root)
        self.width, self.height = int(width), round(int(width)*16/9)
        if self.width < 360 or self.width % 2 or self.height % 2:
            raise ValueError("Width must give even 9:16 dimensions and be at least 360")
        self.output_dir = Path(output_dir or self.root/"output/film_review").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache = SceneCache(self.root, cache_dir or self.root/"output/scene_cache")
        self.node_map = {n["id"]: n for n in self.timeline.nodes}
        self.code_paths = [self.root/"src/chinext_v6"/name for name in
            ["film_renderer.py","production.py","model.py","drawing.py","content_components.py","renderer.py","scene_cache.py"]]
        self.asset_paths = [self.root/"data/cyb_daily.csv", self.root/"assets"/
                            ("earth_cinematic.png" if (self.root/"assets/earth_cinematic.png").is_file() else "earth_body.png")]
        self.font_paths = [Path("/usr/share/fonts/opentype/noto")/name for name in
                           ["NotoSansCJK-Regular.ttc","NotoSansCJK-Bold.ttc"]]
        for path in [Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Oblique.ttf"),
                     Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf")]:
            if path.is_file():
                self.font_paths.append(path)
                break
        self._frozen_inputs={self.master_path:self.master_sha256,
            **{self.root/path:digest for path,digest in self.timeline.dependencies.items()},
            **_IMPORTED_CODE_HASHES,
            **{p:file_sha256(p) for p in (*self.asset_paths,*self.font_paths)}}
        self.master_snapshot_path=self.output_dir/"derived_scenes"/f"master_snapshot_{self.master_sha256}.json"
        self.master_snapshot_path.parent.mkdir(parents=True,exist_ok=True)
        if self.master_snapshot_path.is_file():
            if self.master_snapshot_path.read_bytes()!=master_bytes:
                raise RuntimeError("Frozen master snapshot has been changed")
        else:
            self.master_snapshot_path.write_bytes(master_bytes)
        self._frozen_inputs[self.master_snapshot_path]=self.master_sha256
        self.assert_inputs_stable()

    def assert_inputs_stable(self):
        """Reject changed qualification, drawing code or real consumed inputs."""
        for path,digest in self._frozen_inputs.items():
            if not path.is_file() or file_sha256(path)!=digest:
                raise RuntimeError(f"Production input changed after validation: {path}")

    def select_nodes(self, from_node="S07", to_node="S15"):
        ids = [n["id"] for n in self.timeline.nodes]
        if from_node not in ids or to_node not in ids or ids.index(from_node) > ids.index(to_node):
            raise ValueError("Choose an ordered range of existing production nodes")
        selected = tuple(ids[ids.index(from_node):ids.index(to_node)+1])
        if not selected or any(n not in SUPPORTED_NODES for n in selected):
            raise ValueError("Full-film rendering is not implemented: supported ranges are S07–S15, A01–C03, or H04")
        if not (set(selected) <= set(SUPPORTED_BODY) or set(selected) <= set(SUPPORTED_ENDING) or selected == ("H04",)):
            raise ValueError("Choose one representative range; full-film assembly awaits the sample review")
        return selected

    def _signature(self, node, extra):
        return self.cache.signature_for(node, source_records=self.timeline.sources,
            code_paths=self.code_paths, asset_paths=self.asset_paths, font_paths=self.font_paths,
            width=self.width,height=self.height,fps=self.timeline.fps,extra=extra)

    def prepare(self, from_node="S07", to_node="S15") -> tuple[NodePlan, ...]:
        self.assert_inputs_stable()
        selected = self.select_nodes(from_node, to_node)
        selected_beats = [b for b in self.timeline.beats if b.node_id in selected]
        positions = {b.id:i for i,b in enumerate(self.timeline.beats)}
        phases = {p["id"]:p for p in self.timeline.master["phases"]}
        plans=[]
        generated = self.output_dir/"derived_scenes"
        generated.mkdir(parents=True, exist_ok=True)
        events_path = generated/"no_legacy_events.json"
        _write_json(events_path, [])
        self._frozen_inputs[events_path]=file_sha256(events_path)
        incoming_actual=None
        for node_id in selected:
            node = self.node_map[node_id]
            beats = [b for b in selected_beats if b.node_id == node_id]
            previous = next((b.observation_date for b in reversed(self.timeline.beats[:positions[beats[0].id]])
                             if b.observation_date), None)
            if incoming_actual is None:
                incoming_actual=(previous if node_id=="C03" else beats[0].observation_date) or previous or "2010-06-01"
            node_incoming=incoming_actual
            next_global = next((b.observation_date for b in selected_beats[selected_beats.index(beats[-1])+1:]
                                if b.observation_date), None)
            duration_frames=node["end_frame_exclusive"]-node["start_frame"]
            duration=duration_frames/self.timeline.fps
            model_time=lambda frame:duration*frame/(duration_frames-1)
            keys=[]
            def key(t,d):
                if keys and abs(keys[-1]["t"]-t)<1e-9:
                    if keys[-1]["date"] != d:
                        raise ValueError("Two different market observations share one director time")
                    return
                keys.append({"t":float(t),"date":d})
            timings=[]
            camera=[]
            for i, beat in enumerate(beats):
                local_start=beat.start_frame-node["start_frame"]
                local_end=beat.end_frame_exclusive-node["start_frame"]
                start_t,end_t=model_time(local_start),model_time(local_end-1)
                observed=beat.observation_date
                baseline=observed or incoming_actual or "2010-06-01"
                later=beats[i+1].observation_date if i+1<len(beats) else next_global
                raw_beat=node["beats"][i]
                freeze=bool(raw_beat.get("freeze_market",False))
                if later is None or later < baseline or node["role"] != "main" or freeze:
                    later=baseline
                content_delay=0.0
                hold=3.0 if node_id in {"S09","S15"} else min(1.5,(local_end-local_start)/self.timeline.fps*.40)
                if incoming_actual and incoming_actual < baseline:
                    key(start_t,incoming_actual)
                    arrival=min(end_t,start_t+.4)
                    key(arrival,baseline)
                    content_delay=.4
                else:
                    key(start_t,baseline)
                    arrival=start_t
                hold_end=min(end_t,arrival+hold)
                key(hold_end,baseline)
                key(end_t,later)
                timings.append({"start_frame":local_start,"end_frame_exclusive":local_end,
                    "observation_date":observed,"next_observation_date":later,
                    "content_delay_seconds":content_delay,"hold_seconds":hold,
                    "historical_date":beat.historical_date,"date_precision":beat.date_precision,
                    "freeze_market":freeze,"actual_entry_observation":incoming_actual,
                    "actual_exit_observation":later})
                visible=36 if node_id=="S09" else 95 if node_id=="S15" else 55 if node_id=="S13" else 100
                shot={"id":f"{node_id}_b{i:02d}","start_t":start_t,
                      "end_t":model_time(local_end) if local_end<duration_frames else duration,
                      "visible_days_start":visible,"visible_days_end":visible,
                      "current_x_start":.78,"current_x_end":.78,
                      "y_policy":"lookahead_locked","transition_seconds":.30}
                if node_id in {"S09","S15"}:
                    shot.update(y_policy="critical_anchor",focus_date=observed,
                                anchor_y_frac=.30 if node_id=="S09" else .73)
                camera.append(shot)
                incoming_actual=later
            if keys[-1]["t"] != duration:
                key(duration,keys[-1]["date"])
            modes=[]
            for ident,label,a,b in [
                ("rise_from_low","阶段上涨","2012-12-03","2015-06-03"),
                ("drawdown_from_high","高点后回撤","2015-06-03","2015-07-07"),
                ("july_rebound","阶段反弹","2015-07-07","2015-07-23"),
                ("drawdown_after_rebound","7月反弹后回撤","2015-07-23","2015-09-15")]:
                modes.append({"id":ident,"label":label,"start_date":a,"end_date":b})
            ending=node["role"] in {"album","closing"}
            config={"version":"master_representative_v1","purpose":"代表片验证，非完整成片",
                "video":{"width":self.width,"height":self.height,"fps":self.timeline.fps,
                         "duration_seconds":duration,"audio":False,"preset":"fast","crf":18},
                "sample":{"timeline_start":"2008-01-01" if ending or node_id=="H04" else "2012-01-01",
                          "timeline_end":"2029-01-01" if ending or node_id=="H04" else "2016-01-01",
                          "timeline_years":[] if ending or node_id=="H04" else [2012,2013,2014,2015]},
                "playhead_keyframes":keys,"camera_shots":camera,"critical_points":[],
                "stage_rail":{"single_active_track":True,"modes":modes},"style":{}}
            semantic=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:16]
            config_path=generated/f"{node_id}_{semantic}.json"
            _write_json(config_path,config)
            self._frozen_inputs[config_path]=file_sha256(config_path)
            prev = next((b.observation_date for b in reversed(self.timeline.beats[:positions[beats[0].id]])
                         if b.observation_date), None)
            extra={"motion_mode":MOTION_MODE,"derived_config":config,"beat_timings":timings,
                   "previous_observation":prev,"next_observation":next_global,
                   "previous_actual_exit_observation":node_incoming,
                   "actual_exit_observation":incoming_actual,
                   "derived_config_sha256":file_sha256(config_path),
                   "derived_events_sha256":file_sha256(events_path),
                   "phase":phases.get(node["phase_id"]),"header":self.timeline.master["persistent_screen_copy"]}
            cache_key=self._signature(node,extra)
            plans.append(NodePlan(node_id,node,node["start_frame"],node["end_frame_exclusive"],config,
                                  config_path,events_path,tuple(timings),node_incoming,next_global,cache_key,extra))
        self.assert_inputs_stable()
        return tuple(plans)

    def scene(self, plan: NodePlan) -> FilmScene:
        self.assert_inputs_stable()
        return FilmScene(self.root,self.timeline,plan,self.width)

    def _layout_check(self,plan):
        scene=self.scene(plan); checks=[]
        for beat in plan.beat_timings:
            first=beat["start_frame"];last=beat["end_frame_exclusive"]-1
            points={first,last,min(last,first+round((beat["content_delay_seconds"]+.8)*self.timeline.fps))}
            for frame in sorted(points):
                scene.frame(frame)
                checks.append(scene.last_layout)
        passed=all(not d["out_of_bounds"] and not d["text_overlaps"] and
                   d["active_track_count"]==(1 if d["show_rail"] else 0) for d in checks)
        result={"node_id":plan.node_id,"scene_key":plan.cache_key,"passed":passed,
                "frames":checks,"actual_readability_review":"pending_playback"}
        _write_json(self.output_dir/"layout_checks"/f"{plan.node_id}_{plan.cache_key}.json",result)
        if not passed:
            raise RuntimeError(f"Scene layout checks failed: {plan.node_id}; see layout_checks")
        return result

    def keyframes(self, from_node="S07", to_node="S15") -> dict[str, Any]:
        plans=self.prepare(from_node,to_node)
        folder=self.output_dir/"keyframes"; folder.mkdir(parents=True,exist_ok=True)
        paths=[]; diagnostics=[]; images=[]
        for plan in plans:
            self.assert_inputs_stable()
            scene=self.scene(plan)
            frames={0,plan.total_frames-1}
            for b in plan.beat_timings:
                start,end=b["start_frame"],b["end_frame_exclusive"]
                frames.update({start,min(end-1,start+round(self.timeline.fps*.9)),(start+end-1)//2,end-1})
            for frame in sorted(frames):
                image=scene.frame(frame)
                path=folder/f"{plan.node_id}_f{frame:05d}.png"; image.save(path)
                paths.append(str(path)); diagnostics.append(scene.last_layout)
                thumb=image.copy(); thumb.thumbnail((216,384)); images.append((thumb,f"{plan.node_id} {frame/self.timeline.fps:.2f}s"))
        columns=4; rows=(len(images)+columns-1)//columns
        sheet=Image.new("RGB",(columns*216,rows*410),(3,8,13)); d=ImageDraw.Draw(sheet)
        for i,(image,label) in enumerate(images):
            x,y=i%columns*216,i//columns*410
            sheet.paste(image,(x,y));d.text((x+4,y+388),label,fill=(220,228,234))
        contact=self.output_dir/"keyframe_contact.jpg";sheet.save(contact,quality=92)
        self.assert_inputs_stable()
        result={"paths":paths,"contact_sheet":str(contact),"diagnostics":diagnostics,
                "master_sha256":self.master_sha256,
                "scene_signatures":{p.node_id:self.cache._signatures[p.cache_key] for p in plans},
                "output_hashes":{path:file_sha256(path) for path in [*paths,str(contact)]},
                "layout_passed":all(not d["out_of_bounds"] and not d["text_overlaps"] for d in diagnostics),
                "actual_visual_review":"pending","supported_ranges":["S07–S15","A01–C03","H04"]}
        _write_json(self.output_dir/"layout_diagnostics.json",result)
        if not result["layout_passed"]:
            raise RuntimeError("Representative keyframe layout failed; see layout_diagnostics.json")
        return result

    def video(self, from_node="S07", to_node="S15", workers=2, output_name=None) -> dict[str, Any]:
        if not 1 <= workers <= 4:
            raise ValueError("Use one to four bounded rendering workers")
        plans=self.prepare(from_node,to_node)
        segments=[]; records=[];layouts=[]; hits=0; start=time.monotonic()
        for plan in plans:
            self.assert_inputs_stable()
            layouts.append(self._layout_check(plan))
            cached=self.cache.lookup(plan.cache_key,expected_frames=plan.total_frames,
                width=self.width,height=self.height,fps=self.timeline.fps)
            if cached:
                hits+=1; path=cached; state="cache_hit"
            else:
                path=self.output_dir/"segments"/f"{plan.node_id}.mp4"
                if workers==1:
                    scene=self.scene(plan)
                    frames=(scene.frame(n) for n in range(plan.total_frames))
                    encode_frames(frames,self.width,self.height,self.timeline.fps,path)
                else:
                    # FFmpeg has already opened a stdin pipe when the frame
                    # iterator starts. Spawn avoids inheriting that pipe and
                    # native image/font locks into forked rendering workers.
                    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"), initializer=_worker_init,
                            initargs=(str(self.root),str(self.master_snapshot_path),plan,self.width)) as pool:
                        def frames():
                            size=workers*4
                            for first in range(0,plan.total_frames,size):
                                yield from pool.map(_worker_frame,range(first,min(first+size,plan.total_frames)))
                        encode_frames(frames(),self.width,self.height,self.timeline.fps,path)
                self.assert_inputs_stable()
                if self._signature(plan.node,plan.signature_extra) != plan.cache_key:
                    raise RuntimeError("Selected production dependencies changed during scene rendering")
                path=self.cache.store(plan.cache_key,path,expected_frames=plan.total_frames,
                    width=self.width,height=self.height,fps=self.timeline.fps)
                state="rendered"
            self.assert_inputs_stable()
            segments.append(path)
            records.append({"node_id":plan.node_id,"key":plan.cache_key,"status":state,
                            "path":str(path),"frames":plan.total_frames,
                            "previous_observation":plan.previous_observation,"next_observation":plan.next_observation})
            print(f"{plan.node_id}: {state}",flush=True)
        self.assert_inputs_stable()
        output=self.output_dir/(output_name or f"chinext_{from_node}_{to_node}.mp4")
        frame_count=sum(p.total_frames for p in plans)
        media=concat_segments(segments,output,width=self.width,height=self.height,
                              fps=self.timeline.fps,expected_frames=frame_count,full_decode=True)
        self.assert_inputs_stable()
        black=_black_check(output)
        if not black["passed"]:
            raise RuntimeError(f"Representative assembly contains unexpected black frames: {black}")
        self.assert_inputs_stable()
        seam_frames=[];offset=0
        for left,right in zip(plans,plans[1:]):
            offset+=left.total_frames
            seam_frames.append({"left_node":left.node_id,"right_node":right.node_id,
                "last_left_frame":offset-1,"first_right_frame":offset,
                "left_exit_observation":left.signature_extra["actual_exit_observation"],
                "right_entry_observation":right.signature_extra["previous_actual_exit_observation"],
                "continuous_market_boundary":left.signature_extra["actual_exit_observation"]==right.signature_extra["previous_actual_exit_observation"],
                "actual_visual_join_review":"pending_playback"})
        report={"status":"rendered_technical_checks_passed_manual_review_pending","path":str(output),
            "width":self.width,"height":self.height,"fps":self.timeline.fps,"frame_count":frame_count,
            "duration_seconds":frame_count/self.timeline.fps,"audio":"none","cache_hits":hits,
            "cache_misses":len(plans)-hits,"scenes":records,"media":media,"blackdetect":black,
            "master_path":str(self.master_path),"master_sha256":self.master_sha256,
            "output_sha256":file_sha256(output),"elapsed_seconds":round(time.monotonic()-start,2),
            "motion_mode":MOTION_MODE,"motion_and_readability_review":"pending_actual_representative_playback",
            "scene_signatures":{p.node_id:self.cache._signatures[p.cache_key] for p in plans},
            "input_hashes":{str(path):digest for path,digest in sorted(self._frozen_inputs.items())},
            "layout_checks":layouts,"join_boundaries":seam_frames,
            "implemented_ranges":["S07–S15 (2015 sample)","A01–C03 (album/closing)","H04 (declared rewind)"],
            "full_film_implemented":False}
        _write_json(self.output_dir/"render_manifest.json",report)
        return report


def _black_check(path: Path) -> dict[str, Any]:
    result=subprocess.run(["ffmpeg","-hide_banner","-loglevel","info","-threads","2","-i",str(path),
        "-vf","blackdetect=d=0.1:pic_th=0.98:pix_th=0.02","-an","-f","null","-"],
        capture_output=True,text=True)
    intervals=re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)",result.stderr)
    return {"passed":result.returncode==0 and not intervals,"intervals":intervals,
            "filter":"blackdetect=d=0.1:pic_th=0.98:pix_th=0.02"}
