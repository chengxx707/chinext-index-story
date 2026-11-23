"""Build frame-matched phone comparisons from the delivered and revised media."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
from PIL import Image

from make_review_media import movie_frames, render_contact


def stamp(frame,start):
    seconds=(frame-start)/30
    return f"{int(seconds//60):02d}:{seconds%60:06.3f}"


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()


def lookup(data):
    return {cue["shot_id"]:cue for cue in data["cues"]}


def point(cues,shot,mode,after=0):
    cue=cues[shot]
    if mode=="exit":
        return cue["camera_story_clock"]["exit_window"][0]+after
    if mode=="full":
        return cue["text_cue"]["full_alpha_from_frame"]+after
    raise ValueError(mode)


def video_sheet(old_path,new_path,base,matches,destination,title):
    old_nums=sorted({old-base for _,old,_ in matches})
    new_nums=sorted({new-base for _,_,new in matches})
    old=dict(zip(old_nums,movie_frames(old_path,old_nums,390,694),strict=True))
    new=dict(zip(new_nums,movie_frames(new_path,new_nums,390,694),strict=True))
    frames,labels,records=[],[],[]
    for name,before,after in matches:
        frames.extend((old[before-base],new[after-base]))
        labels.extend((f"Before | {name} | {stamp(before,base)} / f{before}",
                       f"R1 | {name} | {stamp(after,base)} / f{after}"))
        records.append({"node":name,"baseline":{"frame":before,"local_timecode":stamp(before,base)},
                        "r1":{"frame":after,"local_timecode":stamp(after,base)}})
    render_contact(frames,labels,(390,694),title).save(destination,quality=94)
    return {"sheet":destination.name,"media":"decoded_from_390px_phone_mp4","matches":records,
            "baseline_mp4_sha256":digest(old_path),"r1_mp4_sha256":digest(new_path)}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--old",type=Path,required=True)
    cli.add_argument("--new",type=Path,required=True)
    args=cli.parse_args()
    old,new=args.old,args.new
    prev=lookup(json.loads((old/"candidate.json").read_bytes()))
    after=lookup(json.loads((new/"candidate.json").read_bytes()))
    manifest=json.loads((old/"manifest.json").read_bytes())
    dest=new/"comparisons"
    dest.mkdir(exist_ok=True)
    clips={"B01-B02":0,"B16-B18":5520}
    for name in clips:
        old_movie=old/name/"phone-390.mp4"
        assert digest(old_movie)==manifest["artifacts"][f"{name}/phone-390.mp4"]["sha256"]
    s=lambda shot,mode,n:(point(prev,shot,mode,n),point(after,shot,mode,n))
    specs=[
        ("B01-B02","intro-and-cut.jpg","B01-B02 | intro reveals and April cut",
         [("Date cue",6,6),("Zoom in flight",24,24),("Close figure",59,59),("April return",246,246)]),
        ("B16-B18","daily-and-etf.jpg","B17 | daily close, ETF hold, exit and resumed trading",
         [("Sep 25 daily",*s("V102-B17-03","full",9)),("ETF full",*s("V102-B17-ETF","full",9)),
          ("ETF exit",*s("V102-B17-ETF","exit",3)),("Sep 28 daily",*s("V102-B17-04","full",9))]),
        ("B16-B18","turnover-and-repair.jpg","B17-B18 | turnover reading and return to real prices",
         [("Turnover full",*s("V102-B17-TURNOVER","full",9)),("Turnover exit",*s("V102-B17-TURNOVER","exit",3)),
          ("Sep 29 daily",*s("V102-B17-05","full",9)),("Nov 25 repair",*s("V102-B18-04","full",9))]),
    ]
    index={}
    for block,name,title,rows in specs:
        index[name]=video_sheet(old/block/"phone-390.mp4",new/block/"phone-390.mp4",
                                clips[block],rows,dest/name,title)
    b13=new/"B13-PMI"
    baseline=old/"B13-PMI"/"B13-f4440.png"
    revised=b13/"B13-f4440.png"
    frames=[]
    for path in (baseline,revised):
        with Image.open(path) as img:
            frames.append(img.convert("RGB").resize((390,694),Image.Resampling.LANCZOS))
    frames[1].save(b13/"phone-390.png")
    name="pmi-context.jpg"
    render_contact(frames,["Before | B13 · f4440","R1 | B13 · f4440"],(390,694),
                   "B13 | same daily bar and timestamp anchors").save(dest/name,quality=94)
    index[name]={"sheet":name,"media":"actual_target_stills_resized_to_390px","frame":4440,
                 "baseline_still_sha256":digest(baseline),"r1_still_sha256":digest(revised)}
    (dest/"index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    main()
