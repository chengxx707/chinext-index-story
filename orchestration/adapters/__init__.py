"""Allowlisted production commands and checks of their current-run outputs."""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path


class PrerequisiteBlocked(RuntimeError):
    """The production check ran and found an unmet prerequisite."""


@dataclass(frozen=True)
class Adapter:
    command: Callable[[Path, Path], tuple[str, ...]] | None
    validate: Callable[[Path], tuple[str, ...]]
    retry_safe: bool = False
    render: bool = False
    timeout: int = 120
    extra_inputs: Callable[[Path], tuple[str, ...]] | None = None
    dependency_command: Callable[[Path, Path, dict[str, Path]], tuple[str, ...]] | None = None

    def __post_init__(self):
        if (self.command is None) == (self.dependency_command is None):
            raise ValueError("An adapter requires exactly one command builder")


def _python(root: Path, script: str, *arguments: str) -> tuple[str, ...]:
    return (str(root / ".venv/bin/python"), f"tools/{script}", *arguments)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Cannot read current-run JSON evidence from {path.name}: {error}") from error


def _check_screen_copy(attempt_dir: Path) -> tuple[str, ...]:
    evidence = _read_json(attempt_dir / "command.log")
    if evidence.get("passed") is not True or evidence.get("mode") != "check":
        raise RuntimeError("Screen copy check did not report a pass")
    return ()


def _check_compilation(attempt_dir: Path) -> tuple[str, ...]:
    evidence = _read_json(attempt_dir / "compile_checks.json")
    if evidence.get("status") != "passed_compilation_checks":
        raise RuntimeError("Compiler report did not confirm passing checks")
    return ("compile_checks.json", "compiled_film_v1.json")


def _check_photos(attempt_dir: Path) -> tuple[str, ...]:
    evidence = _read_json(attempt_dir / "command.log")
    count = evidence.get("qualified_photo_count")
    years = evidence.get("distinct_event_years")
    if type(count) is not int or count < 0 or not isinstance(years, list):
        raise RuntimeError("Photo report has an invalid count or year list")
    if evidence.get("status") == "real_photos_not_ready" and evidence.get("minimum_assets_ready") is False:
        raise PrerequisiteBlocked(
            f"合格档案照片 {count} 张，覆盖 {len(years)} 个年份。现有工具要求至少 3 张且覆盖 3 个年份。"
        )
    if evidence.get("status") != "minimum_photo_assets_ready" or evidence.get("minimum_assets_ready") is not True:
        raise RuntimeError("Photo check did not report readiness")
    return ()


def _read_input_metadata(path: Path) -> dict:
    # The adapter's production tool reports malformed input. The declared
    # metadata file itself still contributes to the task's fingerprint.
    try:
        data = _read_json(path)
    except RuntimeError:
        return {}
    return data if isinstance(data, dict) else {}


def _records(values: object) -> tuple[dict, ...]:
    if isinstance(values, dict):
        values = list(values.values())
    if not isinstance(values, list):
        return ()
    return tuple(item for item in values if isinstance(item, dict))


def _local_inputs(root: Path, values: Iterable[object]) -> tuple[str, ...]:
    root = root.resolve()
    paths = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        try:
            path = (root / value).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if path.is_relative_to(root):
            paths.add(path.relative_to(root).as_posix())
    return tuple(sorted(paths))


def _photo_inputs(root: Path) -> tuple[str, ...]:
    manifest = _read_input_metadata(root / "data/research/photo_retrieval_v2.json")
    records = _records(manifest.get("assets", manifest.get("photos", manifest.get("candidates"))))
    return _local_inputs(root, (
        value for record in records for value in (
            record.get("local_path", record.get("local_asset_path")), record.get("source_page_archive"),
        )
    ))


def _master_inputs(root: Path) -> tuple[str, ...]:
    master = _read_input_metadata(root / "config/production/film_master_v1.json")
    paths = []
    for source in _records(master.get("sources")):
        paths.extend((source.get("document"), source.get("extracted_text")))
        evidence = source.get("evidence")
        if isinstance(evidence, dict):
            paths.append(evidence.get("document"))
    return _local_inputs(root, paths)


def _keyframes(attempt_dir: Path) -> tuple[str, ...]:
    return tuple(path.relative_to(attempt_dir).as_posix() for path in sorted(attempt_dir.glob("keyframes/*.png")))


def _check_components(attempt_dir: Path) -> tuple[str, ...]:
    diagnostics = _read_json(attempt_dir / "layout_diagnostics.json")
    frames = _keyframes(attempt_dir)
    if not frames or len(diagnostics) != len(frames) or any(item.get("out_of_bounds") != [] for item in diagnostics):
        raise RuntimeError("Component keyframe layout checks are incomplete or failed")
    return ("layout_diagnostics.json", "component_contact.jpg", "photo_album_status.json", *frames)


def _render_range(root: Path, attempt_dir: Path, *, first: str, last: str) -> tuple[str, ...]:
    return _python(
        root, "render_film.py", "--from-node", first, "--to-node", last,
        "--keyframes", "--video", "--workers", "2",
        "--output-dir", str(attempt_dir), "--cache-dir", str(attempt_dir / "scene-cache"),
    )


def _check_render(attempt_dir: Path, *, first: str, last: str) -> tuple[str, ...]:
    layout = _read_json(attempt_dir / "layout_diagnostics.json")
    evidence = _read_json(attempt_dir / "render_manifest.json")
    frames = _keyframes(attempt_dir)
    if (
        layout.get("layout_passed") is not True
        or evidence.get("status") != "rendered_technical_checks_passed_manual_review_pending"
        or not frames
    ):
        raise RuntimeError("Representative render did not report complete technical checks")
    return (
        "layout_diagnostics.json", "render_manifest.json", "keyframe_contact.jpg",
        f"chinext_{first}_{last}.mp4", *frames,
    )


def _workflow(root: Path, out: Path, stage: str, upstream: Path | None = None) -> tuple[str, ...]:
    command = (str(root / ".venv/bin/python"), "-m", "orchestration.workflows", stage, "--out", str(out))
    return command if upstream is None else (*command, "--upstream", str(upstream))


def _check_timing_preview(attempt_dir: Path) -> tuple[str, ...]:
    data = _read_json(attempt_dir / "preview_timing.json")
    if data.get("status") != "timing_preview_ready" or data.get("visual_rendered") is not False:
        raise RuntimeError("Full timing preview did not report successful schedule validation")
    return "preview_timing.json", "preview.html"


def _check_research(attempt_dir: Path) -> tuple[str, ...]:
    research = _read_json(attempt_dir / "period_research.json")
    sources = _read_json(attempt_dir / "source_registry.json")
    if not research.get("events") or not sources.get("sources"):
        raise RuntimeError("Research output has no evaluated events or local sources")
    if any(event["display_candidate"] and event["evidence_status"] != "VERIFIED" for event in research["events"]):
        raise RuntimeError("Research output would display an event without verified evidence")
    return (
        "period_research.json", "source_registry.json", "evidence_report.md", "research_manifest.json",
        *(path.relative_to(attempt_dir).as_posix()
          for path in sorted(attempt_dir.glob("external_research_requests/**/*")) if path.is_file()),
    )


def _research_inputs(root: Path) -> tuple[str, ...]:
    from orchestration.workflows.research import research_input_paths

    return research_input_paths(root)


def _check_content(attempt_dir: Path) -> tuple[str, ...]:
    storyboard = _read_json(attempt_dir / "candidate/period_storyboard.json")
    production = _read_json(attempt_dir / "candidate/period_production.json")
    if not storyboard.get("shots") or production.get("shots") != storyboard["shots"]:
        raise RuntimeError("Content workflow did not produce a consistent storyboard")
    if production.get("status") != "candidate_pending_human_review" or production.get("render_performed") is not False:
        raise RuntimeError("Pilot production output must be an unrendered candidate")
    return tuple(f"candidate/{name}" for name in (
        "period_storyboard.json", "period_screen_copy.md", "period_production.json", "story_audit.md",
    ))


ADAPTERS = {
    "production-docs": Adapter(
        command=lambda root, _: _python(root, "export_production_docs.py", "--check"),
        validate=_check_screen_copy,
    ),
    "production-check": Adapter(
        command=lambda root, out: _python(
            root, "compile_film.py",
            "--output", str(out / "compiled_film_v1.json"),
            "--report", str(out / "compile_checks.json"),
        ),
        validate=_check_compilation,
        retry_safe=True,
        extra_inputs=_master_inputs,
    ),
    "photo-status": Adapter(
        command=lambda _root, _out: ("make", "--silent", "--no-print-directory", "photo-status"),
        validate=_check_photos,
        extra_inputs=_photo_inputs,
    ),
    "component-keyframes": Adapter(
        command=lambda root, out: _python(
            root, "preview_components.py", "--width", "720", "--keyframes", "--output-dir", str(out),
        ),
        validate=_check_components,
    ),
    "representative-render": Adapter(
        command=partial(_render_range, first="S07", last="S15"),
        validate=partial(_check_render, first="S07", last="S15"),
        render=True,
        timeout=3600,
    ),
    "album-render": Adapter(
        command=partial(_render_range, first="A01", last="C03"),
        validate=partial(_check_render, first="A01", last="C03"),
        render=True,
        timeout=3600,
        extra_inputs=_photo_inputs,
    ),
    "full-timing-preview": Adapter(
        command=None,
        dependency_command=lambda root, out, deps: _workflow(root, out, "preview", deps["A.production-check"]),
        validate=_check_timing_preview,
    ),
    "wf01-research": Adapter(
        command=lambda root, out: _workflow(root, out, "research"),
        validate=_check_research,
        retry_safe=True,
        extra_inputs=_research_inputs,
    ),
    "wf01-content": Adapter(
        command=None,
        dependency_command=lambda root, out, deps: _workflow(root, out / "candidate", "content", deps["A.2015-research"]),
        validate=_check_content,
    ),
}
