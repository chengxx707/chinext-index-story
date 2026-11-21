"""CLI for the local workflow runner."""

import argparse
import json
from pathlib import Path
import sys

from orchestration.adapters import ADAPTERS
from orchestration.engine import Runner
from orchestration.registry import load_registry
from orchestration.reports import build_report, to_markdown
from orchestration.state import Status, Store


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path("output/orchestration"))
    actions = parser.add_subparsers(dest="action", required=True)
    plan = actions.add_parser("plan", aliases=["dry-run"], help="Inspect the DAG and readiness without execution")
    run = actions.add_parser("run", help="Execute ready tasks")
    for action in [plan, run]:
        action.add_argument("--allow-render", action="store_true", help="Enable explicitly approved representative renders")
    run.add_argument("--jobs", type=int, default=2)
    approve = actions.add_parser("approve", help="Record an explicit human decision")
    approve.add_argument("task_id")
    approve.add_argument("--input-hash", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--note", required=True)
    report = actions.add_parser("report", help="Summarize stored execution evidence for the current inputs")
    report.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args(argv)

    try:
        state_path = (root / args.state_dir).resolve()
        if not state_path.is_relative_to(root / "output") or state_path == root / "output":
            raise ValueError("State directory must be below this checkout's output directory")
        store = Store(state_path)
        runner = Runner(root, load_registry(), store, ADAPTERS)
        exit_code = 0
        if args.action in {"plan", "dry-run"}:
            result = {"mode": "dry_run", "executed": False, "tasks": runner.plan(allow_render=args.allow_render)}
        elif args.action == "run":
            records = runner.run(jobs=args.jobs, allow_render=args.allow_render)
            exit_code = int(any(record["status"] == Status.FAILED for record in records))
            result = {"mode": "run", "tasks": records}
        elif args.action == "approve":
            result = runner.approve(args.task_id, args.actor, args.note, input_hash=args.input_hash)
        else:
            result = build_report(store, runner.plan())
            if args.format == "markdown":
                print(to_markdown(result), end="")
                return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return exit_code
    except (OSError, RuntimeError, ValueError) as error:
        print(f"orchestration: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
