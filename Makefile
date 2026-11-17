.PHONY: setup test storyboard production-docs production-check components representative photo-status album keyframes sample ending legacy-ending review
TASK_PYTHON := .venv/bin/python
setup:
	bash tools/setup.sh
test:
	$(TASK_PYTHON) -m pytest -q
storyboard:
	$(TASK_PYTHON) tools/build_storyboard.py
production-docs:
	$(TASK_PYTHON) tools/export_production_docs.py
production-check:
	$(TASK_PYTHON) tools/export_production_docs.py --check
	$(TASK_PYTHON) tools/compile_film.py --report output/production/compile_checks.json
components:
	$(TASK_PYTHON) tools/preview_components.py --keyframes --video --output-dir output/content_components_v2
representative:
	$(TASK_PYTHON) tools/render_film.py --from-node S07 --to-node S15 --keyframes --video --workers 2 --output-dir output/representative_2015_v2
photo-status:
	$(TASK_PYTHON) tools/check_archive_photos.py
album:
	$(TASK_PYTHON) tools/check_archive_photos.py --require-ready
	$(TASK_PYTHON) tools/render_film.py --from-node A01 --to-node C03 --keyframes --video --workers 2 --output-dir output/representative_album_v2
keyframes:
	$(TASK_PYTHON) render_v6.py --keyframes --output-dir output/v6_review
sample:
	$(TASK_PYTHON) render_v6.py --keyframes --video --workers 2 --output-dir output/v6_review
ending:
	$(TASK_PYTHON) tools/check_archive_photos.py --require-ready
	$(TASK_PYTHON) tools/render_film.py --from-node A01 --to-node C03 --keyframes --video --workers 2 --output-dir output/representative_album_v2
legacy-ending:
	$(TASK_PYTHON) tools/render_ending.py --keyframes --video --output-dir output/ending_review
review:
	$(TASK_PYTHON) tools/validate_project.py --layout --video output/v6_review/chinext_v6_sample.mp4 --output output/v6_review/validation.json

.PHONY: chapter-2015 chapter-2015-layout
chapter-2015:
	$(TASK_PYTHON) tools/render_chapter.py --keyframes --video --workers 2 --output-dir output/chapter_2015_v3
chapter-2015-layout:
	$(TASK_PYTHON) tools/render_chapter.py --keyframes --output-dir output/chapter_2015_v3

.PHONY: chapter-2015-docs chapter-2015-review
chapter-2015-docs:
	$(TASK_PYTHON) tools/export_chapter_docs.py
chapter-2015-review:
	$(TASK_PYTHON) tools/review_chapter.py output/chapter_2015_v3
