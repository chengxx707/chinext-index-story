from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from .drawing import SceneDrawer
from .model import SceneModel


class Renderer:
    def __init__(self, model: SceneModel, asset_dir: str | Path):
        self.model = model
        self.drawer = SceneDrawer(model, asset_dir)

    def frame(self, number: int):
        return self.drawer.render(self.model.state(number))

    def video(self, output: str | Path):
        output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
        v=self.model.video; w=int(v["width"]); h=int(v["height"]); fps=int(v["fps"])
        total=int(round(self.model.duration*fps))
        cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{w}x{h}","-r",str(fps),"-i","-","-an","-c:v","libx264","-preset",str(v.get("preset","medium")),"-crf",str(v.get("crf",17)),"-pix_fmt","yuv420p","-movflags","+faststart",str(output)]
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        assert p.stdin is not None
        try:
            for i in range(total):
                p.stdin.write(self.frame(i).tobytes())
                if i%(fps*2)==0:
                    print(f"render {i}/{total}",flush=True)
        finally:
            p.stdin.close()
        rc=p.wait()
        if rc:
            raise RuntimeError(f"ffmpeg exited {rc}")
        return output

    def keyframes(self, out_dir: str | Path, times: list[float]):
        out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
        paths=[]
        for t in times:
            n=min(int(round(t*self.model.fps)),len(self.model.states)-1)
            p=out/f"frame_{t:04.1f}.png"
            self.frame(n).save(p)
            paths.append(p)
        return paths


def contact_sheet(paths: list[Path], output: str | Path, thumb=(360,640), cols=3):
    images=[]
    for p in paths:
        im=Image.open(p).convert("RGB")
        im.thumbnail(thumb,Image.Resampling.LANCZOS)
        images.append((p,im.copy()))
    rows=(len(images)+cols-1)//cols
    sheet=Image.new("RGB",(cols*thumb[0],rows*(thumb[1]+42)),(4,7,10))
    d=ImageDraw.Draw(sheet)
    for i,(p,im) in enumerate(images):
        x=(i%cols)*thumb[0]; y=(i//cols)*(thumb[1]+42)
        sheet.paste(im,(x,y))
        d.text((x+8,y+thumb[1]+8),p.stem,fill=(225,230,235))
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); sheet.save(output,quality=92)
    return output
