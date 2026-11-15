"""Integration checks for continuous representative scenes and actual cached media."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.film_renderer import FilmRenderer
from chinext_v6.scene_cache import inspect_media


@pytest.fixture
def renderer(tmp_path):
    return FilmRenderer(ROOT, width=360, output_dir=tmp_path / "render",
                        cache_dir=tmp_path / "cache")


def date_string(value):
    return str(value.date()) if hasattr(value, "date") else str(value)


def test_content_enhanced_representative_has_its_planned_97_seconds(renderer):
    plans = renderer.prepare(from_node="S07", to_node="S15")
    assert [p.node_id for p in plans] == [f"S{i:02d}" for i in range(7, 16)]
    assert sum(p.end_frame_exclusive - p.start_frame for p in plans) == 2910
    assert sum(p.config["video"]["duration_seconds"] for p in plans) == 97


def test_album_and_closing_have_their_planned_39_seconds(renderer):
    plans = renderer.prepare(from_node="A01", to_node="C03")
    assert [p.node_id for p in plans] == ["A01", "A02", "A03", "A04", "A05", "C01", "C02", "C03"]
    assert sum(p.end_frame_exclusive - p.start_frame for p in plans) == 1170


def test_default_scope_does_not_silently_render_the_unreviewed_whole_film(renderer):
    assert [p.node_id for p in renderer.prepare()] == [f"S{i:02d}" for i in range(7, 16)]
    with pytest.raises(ValueError):
        renderer.prepare(from_node="H01", to_node="C03")
    with pytest.raises(ValueError):
        renderer.prepare(from_node="S01", to_node="S06")


def test_range_endpoint_cannot_move_into_the_next_unselected_node(renderer):
    plans = renderer.prepare(from_node="S07", to_node="S15")
    scene = renderer.scene(plans[-1])
    assert date_string(scene.model.states[-1].current_date) == "2015-09-15"
    assert scene.model.states[-1].current_close == pytest.approx(1797.56)
    assert max(date_string(s.current_date) for s in scene.model.states) == "2015-09-15"


def test_motion_contains_multiple_real_days_and_never_precedes_new_card_anchor(renderer):
    plans = renderer.prepare(from_node="S07", to_node="S15")
    first = renderer.scene(plans[0])
    assert len({date_string(s.current_date) for s in first.model.states}) > 3
    assert all(a.current_index <= b.current_index
               for a, b in zip(first.model.states, first.model.states[1:]))
    for plan in plans:
        scene = renderer.scene(plan)
        for frame in range(scene.model.total_frames):
            context = scene.frame_context(frame)
            if context["content_visible"] and context["content_anchor_date"]:
                assert context["current_date"] >= context["content_anchor_date"]
            state = scene.model.states[frame]
            assert context["current_date"] == date_string(state.current_date)
            assert context["current_close"] == float(state.current_close)


def test_next_scene_context_is_part_of_a_cached_scenes_identity(renderer):
    standalone = renderer.prepare(from_node="S07", to_node="S07")[0]
    in_sequence = renderer.prepare(from_node="S07", to_node="S15")[0]
    assert standalone.next_observation != in_sequence.next_observation
    assert standalone.cache_key != in_sequence.cache_key


def test_explicitly_frozen_policy_holds_market_and_next_card_waits_for_its_day(renderer):
    import csv
    plan = next(p for p in renderer.prepare(from_node="S07", to_node="S15") if p.node_id == "S13")
    scene = renderer.scene(plan)
    with (ROOT / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as handle:
        closes = {row["date"]: float(row["close"]) for row in csv.DictReader(handle)}
    fps = scene.model.fps
    # The 8/25 18:15 policy is an explicitly frozen third beat at 9–15 seconds.
    for frame in range(9 * fps, 15 * fps):
        context = scene.frame_context(frame)
        assert context["beat_index"] == 2
        assert context["content_anchor_date"] == "2015-08-25"
        assert context["current_date"] == "2015-08-25"
        assert context["current_close"] == closes["2015-08-25"]
    # Movement to 8/26 occurs before the next dated card enters, preserving both
    # the frozen policy reading period and the next card's truthful date.
    start, end = 15 * fps, 19 * fps
    for frame in range(start, start + round(.4 * fps)):
        assert not scene.frame_context(frame)["content_visible"]
    contexts = [scene.frame_context(frame) for frame in range(start, end)]
    for context in contexts:
        assert context["current_close"] == closes[context["current_date"]]
        if context["content_visible"]:
            assert context["current_date"] >= "2015-08-26"
    # The original four-second beat promises at least d-1 seconds fully stable.
    assert sum(c["content_opacity"] >= 1 - 1e-6 for c in contexts) >= 3 * fps


def test_return_from_album_hides_hud_and_waits_for_real_endpoint_before_text(renderer):
    plans = renderer.prepare(from_node="A01", to_node="C03")
    scene = renderer.scene(plans[-1])
    assert not scene.frame_context(0)["content_visible"]
    assert date_string(scene.model.states[-1].current_date) == "2026-11-10"
    assert scene.model.states[-1].current_close == pytest.approx(2494.40)
    for frame in range(scene.model.total_frames):
        context = scene.frame_context(frame)
        assert not context["show_hud"]
        assert not context["show_rail"]
        if context["content_visible"]:
            assert context["current_date"] == "2026-11-10"
            assert context["current_close"] == pytest.approx(2494.40)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg and FFprobe are required for real media validation")
def test_real_short_scene_video_is_silent_complete_and_reused_from_cache(renderer):
    first = renderer.video(from_node="S08", to_node="S08", workers=1)
    assert first["frame_count"] == 150
    assert first["cache_hits"] == 0
    assert first["cache_misses"] == 1
    output = Path(first["path"])
    assert output.is_file()
    report = inspect_media(output, width=360, height=640, fps=30,
                           expected_frames=150, full_decode=True)
    assert report["passed"]
    assert report["checks"]["no_audio_stream"]
    assert report["checks"]["full_decode"]
    again = renderer.video(from_node="S08", to_node="S08", workers=1)
    assert again["frame_count"] == 150
    assert again["cache_hits"] == 1
    assert again["cache_misses"] == 0


def test_master_cannot_change_after_renderer_initialization(tmp_path):
    master = tmp_path / "film_master.json"
    master.write_bytes((ROOT / "config/production/film_master_v1.json").read_bytes())
    renderer = FilmRenderer(ROOT, master_path=master, width=360,
                            output_dir=tmp_path / "render", cache_dir=tmp_path / "cache")
    # Preserve valid JSON so rejection demonstrates frozen-input provenance,
    # rather than an incidental parse failure.
    master.write_bytes(master.read_bytes() + b"\n")
    with pytest.raises(RuntimeError):
        renderer.assert_inputs_stable()


def test_archived_source_cannot_change_before_preparing_scenes(tmp_path):
    from tempfile import TemporaryDirectory
    master_data = json.loads((ROOT / "config/production/film_master_v1.json").read_text(encoding="utf-8"))
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    # Keep the temporary archive inside ROOT because production provenance
    # deliberately rejects source files that escape the project directory.
    with TemporaryDirectory(prefix="source_integrity_", dir=output) as directory:
        original = ROOT / master_data["sources"]["AR01"]["document"]
        source_copy = Path(directory) / "interview.html"
        shutil.copy2(original, source_copy)
        master_data["sources"]["AR01"]["document"] = source_copy.relative_to(ROOT).as_posix()
        master = tmp_path / "source_master.json"
        master.write_text(json.dumps(master_data, ensure_ascii=False), encoding="utf-8")
        renderer = FilmRenderer(ROOT, master_path=master, width=360,
                                output_dir=tmp_path / "render", cache_dir=tmp_path / "cache")
        # Original archive bytes and the declared SHA-256 agreed during init;
        # now only the disposable copy changes, so prepare must refuse it.
        source_copy.write_bytes(source_copy.read_bytes() + b"\n")
        with pytest.raises(RuntimeError):
            renderer.prepare()


def test_prepared_scene_refuses_a_modified_derived_configuration(renderer):
    plan = renderer.prepare(from_node="S08", to_node="S08")[0]
    configuration = json.loads(plan.config_path.read_text(encoding="utf-8"))
    configuration["video"]["width"] += 2
    plan.config_path.write_text(json.dumps(configuration), encoding="utf-8")
    with pytest.raises(RuntimeError):
        renderer.scene(plan)


def test_prepared_scene_refuses_modified_derived_events(renderer):
    plan = renderer.prepare(from_node="S08", to_node="S08")[0]
    events = json.loads(plan.events_path.read_text(encoding="utf-8"))
    # Even an ignored legacy event changes the prepared input bytes, so the
    # cached signature cannot still describe the scene that will be rendered.
    events.append({"id": "injected_disabled_event", "enabled": False, "release_grade": "B"})
    plan.events_path.write_text(json.dumps(events), encoding="utf-8")
    with pytest.raises(RuntimeError):
        renderer.scene(plan)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg and FFprobe are required for actual parallel rendering")
def test_parallel_cli_finishes_and_closes_encoder_input(tmp_path):
    # A separate CLI reproduces the real process/encoder lifecycle. A timeout
    # catches workers inheriting FFmpeg's input pipe or native locks after fork.
    output = tmp_path / "parallel"
    completed = subprocess.run([
        sys.executable, str(ROOT / "tools/render_film.py"),
        "--from-node", "S08", "--to-node", "S08", "--video", "--width", "360",
        "--workers", "2", "--output-dir", str(output),
        "--cache-dir", str(tmp_path / "cache"),
    ], capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    manifest = json.loads((output / "render_manifest.json").read_text())
    assert manifest["frame_count"] == 150
    assert manifest["media"]["checks"]["full_decode"]
    assert manifest["media"]["checks"]["no_audio_stream"]
