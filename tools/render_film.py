#!/usr/bin/env python3
"""Render a master-driven representative range, preserving the sample gate."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master",type=Path,default=ROOT/"config/production/film_master_v1.json")
    parser.add_argument("--from-node",default="S07")
    parser.add_argument("--to-node",default="S15")
    parser.add_argument("--width",type=int,default=1080)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"output/content_review")
    parser.add_argument("--cache-dir",type=Path,default=ROOT/"output/scene_cache")
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--keyframes",action="store_true")
    parser.add_argument("--video",action="store_true")
    args=parser.parse_args(argv)
    if not (args.keyframes or args.video):
        parser.error("Choose --keyframes and/or --video; full-film expansion is not implicit")
    from chinext_v6.film_renderer import FilmRenderer
    try:
        renderer=FilmRenderer(ROOT,master_path=args.master,width=args.width,
            output_dir=args.output_dir,cache_dir=args.cache_dir)
        if args.keyframes:
            result=renderer.keyframes(args.from_node,args.to_node)
            print(json.dumps({"contact_sheet":result["contact_sheet"],"frames":len(result["paths"])},ensure_ascii=False))
        if args.video:
            result=renderer.video(args.from_node,args.to_node,workers=args.workers)
            print(json.dumps({k:result[k] for k in ["path","frame_count","duration_seconds","cache_hits","cache_misses"]},ensure_ascii=False))
        return 0
    except (ValueError,RuntimeError,OSError) as error:
        print(json.dumps({"status":"failed","error":str(error)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
