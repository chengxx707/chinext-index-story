#!/usr/bin/env python3
"""Validate the current production master and emit a derived scene schedule."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chinext_v6.production import ProductionError, ProductionTimeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=ROOT / "config/production/film_master_v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output/production/compiled_film_v1.json")
    parser.add_argument("--report", type=Path, help="Optional separate compilation-check report")
    args = parser.parse_args(argv)
    try:
        timeline = ProductionTimeline(args.master, root=ROOT)
        if args.output.resolve() == args.master.resolve():
            raise ProductionError("Derived output must not overwrite the source master")
        result = timeline.to_dict()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = {"status": "passed_compilation_checks", "nodes": len(timeline.nodes),
                   "beats": len(timeline.beats), "frames": timeline.total_frames,
                   "duration_seconds": timeline.duration_seconds, "output": str(args.output),
                   "clock_policy": result["market_clock_policy"],
                   "checks": timeline.checks, "warnings": timeline.warnings,
                   "rendered": False, "actual_layout_or_readability_review": False}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (ProductionError, OSError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
