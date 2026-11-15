#!/usr/bin/env python3
"""Render shared content-component stills and an optional silent motion study.

This is a component engineering preview, not the complete representative pack
or a rendering of the full production schedule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from PIL import Image, ImageDraw
from chinext_v6.content_components import ContentDrawer
from chinext_v6.renderer import encode_frames


PREVIEWS=[
    ("stage","S10",0), ("event","S07",1), ("timeline","S11",1),
    ("quote","S20",1), ("headline","S34",0), ("document","S24",0),
    ("closing","C01",0), ("return","C03",0),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width",type=int,default=1080)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"output/content_components_v2")
    parser.add_argument("--keyframes",action="store_true")
    parser.add_argument("--video",action="store_true")
    parser.add_argument("--seconds-per-component",type=int,default=4)
    args=parser.parse_args()
    if args.width<360 or args.width%2 or round(args.width*16/9)%2:
        parser.error("width must produce even 9:16 dimensions and be at least 360")
    if args.seconds_per_component<2:
        parser.error("seconds-per-component must be at least 2")
    if not args.keyframes and not args.video:
        args.keyframes=True
    drawer=ContentDrawer(ROOT,args.width)
    out=args.output_dir
    out.mkdir(parents=True,exist_ok=True)
    (out/"photo_album_status.json").write_text(json.dumps({
        "status":"not_included_real_photos_required",
        "reason":"The document-only album was rejected. No document/chart substitute is included in this study.",
        "source_manifest":"data/research/photo_retrieval_v2.json",
        "ready_photo_count":drawer.photo_album.manifest.get("ready_photo_count",0),
    },ensure_ascii=False,indent=2)+"\n")
    diagnostics=[]
    if args.keyframes:
        frames=out/"keyframes"
        frames.mkdir(exist_ok=True)
        tw,th=270,480
        sheet=Image.new("RGB",(tw*3,(th+36)*((len(PREVIEWS)+2)//3)),(3,8,13))
        for i,(kind,node,beat) in enumerate(PREVIEWS):
            im=drawer.render(node,beat,kind=kind)
            im.save(frames/f"{i+1:02d}_{kind}_{node}_{beat}.png")
            diagnostic=drawer.diagnostics(node,beat,kind=kind)
            diagnostics.append(diagnostic)
            if diagnostic["out_of_bounds"]:
                raise RuntimeError(f"text outside frame: {kind}/{node}")
            x,y=i%3*tw,i//3*(th+36)
            sheet.paste(im.resize((tw,th),Image.Resampling.LANCZOS),(x,y))
            ImageDraw.Draw(sheet).text((x+9,y+th+9),f"{kind} | {node}:{beat}",fill=(213,225,236))
        sheet.save(out/"component_contact.jpg",quality=94)
        (out/"layout_diagnostics.json").write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+"\n")
        print(out/"component_contact.jpg",flush=True)
    if args.video:
        fps=30
        frames_per=args.seconds_per_component*fps
        target=out/"content_component_motion_study.mp4"
        dependencies=[Path(__file__).resolve(),ROOT/"src/chinext_v6/content_components.py",
            ROOT/"src/chinext_v6/drawing.py",ROOT/"src/chinext_v6/model.py",ROOT/"src/chinext_v6/renderer.py",
            ROOT/"data/cyb_daily.csv",ROOT/"config/production/film_master_v1.json",
            ROOT/"assets/earth_cinematic.png",ROOT/"assets/earth_body.png",
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),Path(drawer.fonts.number_path)]
        dependency_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies if p.is_file()}
        def frames():
            for kind,node,beat in PREVIEWS:
                for i in range(frames_per):
                    yield drawer.render(node,beat,progress=i/(frames_per-1),kind=kind)
        count=encode_frames(frames(),drawer.width,drawer.height,fps,target)
        probe=json.loads(subprocess.run(["ffprobe","-v","error","-count_frames","-show_entries",
            "stream=codec_type,width,height,r_frame_rate,nb_read_frames:format=duration","-of","json",str(target)],
            capture_output=True,text=True,check=True).stdout)
        streams=probe["streams"]
        video=[x for x in streams if x["codec_type"]=="video"]
        checks={"one_video_stream":len(video)==1,"silent_no_audio":not any(x["codec_type"]=="audio" for x in streams),
                "frame_count":int(video[0]["nb_read_frames"])==count,
                "dimensions":(video[0]["width"],video[0]["height"])==(drawer.width,drawer.height),
                "fps":video[0]["r_frame_rate"]=="30/1",
                "duration":abs(float(probe["format"]["duration"])-count/fps)<=1/fps}
        decode=subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(target),"-an","-f","null","-"],capture_output=True)
        checks["full_decode"]=decode.returncode==0
        checks["inputs_unchanged_during_render"]=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==dependency_hashes[str(p)] for p in dependencies if str(p) in dependency_hashes)
        manifest={"purpose":"component_motion_study_not_full_representative_pack","passed":all(checks.values()),
            "checks":checks,"video_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
            "dependency_sha256":dependency_hashes,
            "master_sha256":hashlib.sha256((ROOT/"config/production/film_master_v1.json").read_bytes()).hexdigest(),
            "frame_count":count,"fps":fps,"width":drawer.width,"height":drawer.height,
            "duration_seconds":count/fps,"audio":False,"actual_readability_review":"pending_representative_sample"}
        (out/"motion_checks.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        if not manifest["passed"]:
            raise RuntimeError("component video checks failed")
        print(target,flush=True)


if __name__=="__main__":
    main()
