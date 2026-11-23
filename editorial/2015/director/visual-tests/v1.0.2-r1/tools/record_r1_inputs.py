"""Tie the rendered result and reused policy clip to the actual R1 inputs."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path

def checksum(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root",type=Path,required=True)
    cli.add_argument("--verify",action="store_true")
    args=cli.parse_args()
    result=args.root/"result"
    receipt=json.loads((result/"intake.json").read_bytes())
    if not receipt["passed"]:
        raise ValueError("R1 intake and clock must pass before rendering")
    protected=receipt["protected_input_sha256"]
    for path,expected in protected.items():
        if checksum(Path(path))!=expected:
            raise ValueError(f"Protected input changed: {path}")
    sources=(*sorted((result/"legacy").glob("*.json")),result/"candidate.json",
             *[args.root/"work"/name for name in ("render_visual.py","visual_overlay.py","r1_candidate.py","prepare_r1.py",
                                                   "make_review_media.py","review_playback.mjs")],
             *sorted(Path("/usr/share/fonts/opentype/noto").glob("NotoSansCJK-*.ttc")))
    current={**protected,**{str(path):checksum(path) for path in sources}}
    out=result/"render_input_binding.json"
    if args.verify:
        old=json.loads(out.read_bytes())
        changed=sorted(name for name in current.keys()|old["input_sha256"].keys()
                       if current.get(name)!=old["input_sha256"].get(name))
        old.update(verified_unchanged_after_render=not changed,changed_paths=changed)
        payload=old
    else:
        payload={"input_sha256":current,"verified_unchanged_after_render":None}
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    if args.verify and changed:
        raise RuntimeError(f"R1 rendering inputs changed: {changed}")

if __name__=="__main__":
    main()
