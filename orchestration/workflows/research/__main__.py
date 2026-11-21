"""Command line entry point for offline research verification."""

import argparse
from pathlib import Path

from . import run_research


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Unused directory for research output")
    parser.add_argument("--dossier", type=Path, help="Local dossier JSON inside the checkout")
    parser.add_argument("--import-file", type=Path, help="External response JSON inside the checkout")
    args = parser.parse_args()
    try:
        artifacts = run_research(Path.cwd(), args.out, dossier=args.dossier, external_file=args.import_file)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"WF-01A: {error}\n")
    for artifact in artifacts:
        print(args.out / artifact)


if __name__ == "__main__":
    main()
