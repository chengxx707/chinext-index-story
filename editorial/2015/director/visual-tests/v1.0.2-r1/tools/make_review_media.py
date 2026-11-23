"""Create phone transcodes and contact sheets from the actual representative MP4s."""

import argparse
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

BLOCKS = {"B01-B02": (0, 540), "B08-B10": (2280, 3600), "B16-B18": (5520, 7320)}


def movie_frames(video, indexes, width, height):
    choice = "+".join(f"eq(n\\,{n})" for n in indexes)
    data = subprocess.check_output([
        "ffmpeg", "-v", "error", "-threads", "2", "-i", str(video),
        "-vf", f"select={choice},scale={width}:{height}:flags=lanczos", "-fps_mode", "vfr",
        "-frames:v", str(len(indexes)), "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "-",
    ])
    frame_bytes = width * height * 3
    assert len(data) == frame_bytes * len(indexes), (len(data), indexes)
    return [Image.frombytes("RGB",(width,height),data[i:i+frame_bytes])
            for i in range(0,len(data),frame_bytes)]


def describe(cue, frame):
    name = cue["shot_id"].removeprefix("V102-")
    return f"{name}  ·  frame {frame}"


def render_contact(images, labels, size, page_title):
    cols = min(4, len(images))
    rows = math.ceil(len(images)/cols)
    gap, top, stripe = 12, 46, 27
    width, height = size
    canvas = Image.new("RGB",(gap+cols*(width+gap),top+rows*(height+stripe+gap)), "#111a24")
    pen = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("DejaVuSans.ttf",12)
    title = ImageFont.truetype("DejaVuSans.ttf",18)
    pen.text((gap,13),page_title, font=title, fill="#e2eaf0")
    for i, (frame,label) in enumerate(zip(images,labels,strict=True)):
        x,y = gap+(width+gap)*(i%cols),top+(height+stripe+gap)*(i//cols)
        pen.text((x,y+3),label,font=font,fill="#b6c5d4")
        canvas.paste(frame,(x,y+stripe))
    return canvas


def part(block, root, candidate):
    start,end = BLOCKS[block]
    path = root/block
    movie = path/"target.mp4"
    phone = path/"phone-390.mp4"
    subprocess.run([
        "ffmpeg","-v","error","-y","-i",str(movie),"-map","0:v:0","-vf",
        "scale=390:-2:flags=lanczos,setsar=1","-an","-c:v","libx264","-threads","2",
        "-preset","fast","-crf","17","-movflags","+faststart",str(phone),
    ], check=True)
    cues = [cue for cue in candidate["cues"] if start <= cue["start_frame"] < end]
    by_frame = {}
    for cue in cues:
        text = cue["text_cue"]
        n = min(cue["end_frame_exclusive"]-1,text["full_alpha_from_frame"]+9)
        by_frame[n] = cue
    extra = {
        "B01-B02": [0,239,240,539],
        "B08-B10": [2280,2759,2760,3239,3240,3599],
        "B16-B18": [5520,7319],
    }[block]
    for cue in cues:
        if cue["shot_id"] in {"V102-B17-ETF","V102-B17-TURNOVER"}:
            extra.extend((cue["start_frame"]-1,cue["start_frame"],cue["end_frame_exclusive"]-1,
                          cue["end_frame_exclusive"]))
    for n in extra:
        by_frame[n] = next(cue for cue in cues if cue["start_frame"] <= n < cue["end_frame_exclusive"])
    frames = sorted(by_frame)
    target = movie_frames(movie,[f-start for f in frames],216,384)
    path.joinpath("keyframe-contact.jpg").unlink(missing_ok=True)
    render_contact(target,[describe(by_frame[n],n) for n in frames],(216,384),
                   f"{block} | encoded target keyframes").save(path/"keyframe-contact.jpg",quality=94)
    if block == "B16-B18":
        selected = []
        for cue in cues:
            if cue["shot_id"] not in {"V102-B17-ETF","V102-B17-TURNOVER"}:
                continue
            begin,stop = cue["start_frame"],cue["end_frame_exclusive"]
            selected.extend((begin, cue["text_cue"]["full_alpha_from_frame"]+9, stop-3, stop+4))
        selected = sorted(set(selected))
        outputs = movie_frames(phone,[f-start for f in selected],390,694)
        render_contact(outputs,[f"f{frame} · {((frame-start)/30):.2f}s" for frame in selected],
                       (390,694),"B17 | encoded phone view · ETF and turnover transition").save(
                           path/"b17-t2-phone-contact.jpg",quality=94)
    with (path/"contact_sources.json").open("w",encoding="utf-8") as out:
        json.dump({"derived_from_encoded_video":True,"frame_span":[start,end],"target_full_size":[1080,1920],
                   "phone_encoded_size":[390,694],"contact_frames":frames},out,indent=2)
        out.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result",type=Path,required=True)
    parser.add_argument("--block",choices=list(BLOCKS),action="append")
    args = parser.parse_args()
    candidate = json.loads((args.result/"candidate.json").read_bytes())
    for block in args.block or list(BLOCKS):
        part(block,args.result,candidate)


if __name__ == "__main__":
    main()
