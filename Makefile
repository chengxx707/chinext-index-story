.PHONY: setup test storyboard keyframes sample ending review
TASK_PYTHON := .venv/bin/python
setup:
	bash tools/setup.sh
test:
	$(TASK_PYTHON) -m pytest -q
storyboard:
	$(TASK_PYTHON) tools/build_storyboard.py
keyframes:
	$(TASK_PYTHON) render_v6.py --keyframes --output-dir output/v6_review
sample:
	$(TASK_PYTHON) render_v6.py --keyframes --video --workers 2 --output-dir output/v6_review
ending:
	$(TASK_PYTHON) tools/render_ending.py --keyframes --video --output-dir output/ending_review
review:
	$(TASK_PYTHON) tools/validate_project.py --layout --video output/v6_review/chinext_v6_sample.mp4 --output output/v6_review/validation.json
