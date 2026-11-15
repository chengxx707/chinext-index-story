#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_ROOT"
command -v ffmpeg >/dev/null
test -r /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
test -r /usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python tools/build_storyboard.py
.venv/bin/python tools/export_production_docs.py --check
.venv/bin/python tools/compile_film.py --report output/production/compile_checks.json
.venv/bin/python -m pytest -q
