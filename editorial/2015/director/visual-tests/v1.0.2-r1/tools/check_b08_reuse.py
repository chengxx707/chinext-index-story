"""Check that R1 shared code preserves the exact source pixels of B08-B10."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

TOOLS=("render_visual.py","visual_overlay.py")


def scene_hash(args):
    sys.path.insert(0,str(args.tools.resolve()))
    from render_visual import build_scene
    candidate=json.loads((args.result/"candidate.json").read_bytes())
    legacy=args.result/"legacy"
    segments=json.loads((legacy/"segments.json").read_bytes())
    for segment in segments:
        segment["timeline"]=json.loads((legacy/f'{segment["id"]}.json').read_bytes())
    scene=build_scene(Path.cwd(),candidate,segments,args.runtime.resolve(),1080)
    frames=set()
    for cue in candidate["cues"]:
        if cue["beat_id"] in {"B08","B09","B10"}:
            frames.update((cue["start_frame"],cue["text_cue"]["full_alpha_from_frame"],cue["end_frame_exclusive"]-1))
    hashes={}
    for frame in sorted(frames):
        image,layout=scene.frame(frame)
        assert not layout["layout_errors"]
        hashes[str(frame)]=sha256(image.tobytes()).hexdigest()
    return hashes


def worker(args,tools,result):
    return json.loads(subprocess.check_output([sys.executable,"-B",str(Path(__file__).resolve()),
        "--worker","--tools",str(tools),"--runtime",str(args.runtime),"--result",str(result)]))


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--worker",action="store_true")
    cli.add_argument("--tools",type=Path)
    cli.add_argument("--runtime",type=Path,required=True)
    cli.add_argument("--result",type=Path,required=True)
    cli.add_argument("--baseline",type=Path)
    args=cli.parse_args()
    if args.worker:
        print(json.dumps(scene_hash(args)))
        return 0
    if args.baseline is None:
        cli.error("Provide a delivered baseline result directory")
    before_dir=args.result.parent/"baseline-tools"
    before_dir.mkdir(exist_ok=True)
    with ZipFile(args.baseline/"director-v1.0.2-representative-visual-review.zip") as archive:
        for tool in TOOLS:
            (before_dir/tool).write_bytes(archive.read(f"tools/{tool}"))
    before=worker(args,before_dir,args.baseline)
    after=worker(args,Path(__file__).resolve().parent,args.result)
    report={"passed":before==after,"identical_target_rgb_samples":sum(before.get(n)==after.get(n) for n in before),
            "sample_count":len(before),"frame_sha256_baseline":before,"frame_sha256_r1":after,
            "basis":"cue start, full reading and terminal frame; both renderer versions executed without encoding",
            "reused_encoded_clip":"B08-B10"}
    (args.result/"b08_shared_pixel_check.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if not k.startswith("frame_sha")}))
    return 0 if report["passed"] else 1

if __name__=="__main__":
    raise SystemExit(main())
