#!/usr/bin/env python3
"""Render the current, silent representative sample; no implicit full-film expansion."""
from pathlib import Path
import argparse
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=str(ROOT / "config/v6_sample.json"))
    p.add_argument("--events", default=str(ROOT / "config/events_v6.json"))
    p.add_argument("--csv", default=str(ROOT / "data/cyb_daily.csv"))
    p.add_argument("--output-dir", default=str(ROOT / "output/v6_review"))
    p.add_argument("--width", type=int)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--keyframes", action="store_true")
    p.add_argument("--video", action="store_true")
    p.add_argument("--benchmark", action="store_true")
    args = p.parse_args()
    if not (args.video or args.keyframes or args.benchmark):
        p.error("Choose --keyframes, --video or --benchmark")
    if args.width and (args.width < 360 or args.width % 2):
        p.error("--width must be an even integer >=360")
    if args.workers < 1 or args.workers > 4:
        p.error("--workers must be between 1 and 4")
    from chinext_v6.renderer import Renderer
    renderer = Renderer(args.config, args.events, args.csv, ROOT / "assets", args.width)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    renderer.diagnostics(out)
    if args.benchmark:
        start = time.monotonic()
        samples = [0, len(renderer.model.states)//2, len(renderer.model.states)-1]
        for n in samples:
            renderer.frame(n)
        print(f"seconds/frame={(time.monotonic()-start)/len(samples):.3f}", flush=True)
    if args.keyframes:
        renderer.keyframes(out)
        print(out / "review_contact.jpg", flush=True)
    if args.video:
        print(renderer.video(out, args.workers), flush=True)


if __name__ == "__main__":
    main()
