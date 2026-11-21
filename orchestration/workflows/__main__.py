"""Run one read-only stage of the production workflow."""

import argparse
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("research", "content", "preview"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--upstream", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(root / "output") or out == root / "output":
        parser.error("Output must be a directory below output/")
    if args.stage != "research" and args.upstream is None:
        parser.error("--upstream is required for content and preview")
    if args.stage == "research":
        from orchestration.workflows.research import run_research

        external = root / "output/research_inbox/2015/response.json"
        artifacts = run_research(root, out, external_file=external if external.is_file() else None)
    elif args.stage == "content":
        from orchestration.workflows.content import run_content

        artifacts = run_content(root, args.upstream, out)
    else:
        from orchestration.workflows.preview import build_preview

        build_preview(args.upstream / "compiled_film_v1.json", out)
        artifacts = ("preview_timing.json", "preview.html")
    print(json.dumps({"stage": args.stage, "artifacts": artifacts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
