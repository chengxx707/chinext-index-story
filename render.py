from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))

from chinext_v5.model import SceneModel
from chinext_v5.renderer import Renderer, contact_sheet


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--video",action="store_true")
    p.add_argument("--keyframes",action="store_true")
    args=p.parse_args()
    model=SceneModel(ROOT/"config/v5_sample.json",ROOT/"config/events_v5.json",ROOT/"data/cyb_daily.csv")
    renderer=Renderer(model,ROOT/"assets")
    if args.keyframes or not args.video:
        times=[1.8,2.8,4.25,7.65,12.6,15.35,16.8,17.8]
        paths=renderer.keyframes(ROOT/"output/keyframes",times)
        contact_sheet(paths,ROOT/"output/review_contact.jpg",thumb=(360,640),cols=4)
        print(ROOT/"output/review_contact.jpg")
    if args.video:
        print(renderer.video(ROOT/"output/chinext_v5_cinematic_camera.mp4"))

if __name__=="__main__":
    main()
