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


def test_rejected_document_album_cannot_be_exported_as_a_new_photo_ending(renderer):
    # The original manuscript may still be compiled for historical comparison;
    # a user-facing export must not silently reuse its rejected paper pages.
    with pytest.raises(ValueError,match="需要真实照片"):
        renderer.keyframes(from_node="A01",to_node="C03")
    with pytest.raises(ValueError,match="需要真实照片"):
        renderer.video(from_node="A01",to_node="C03",workers=1)


def test_landmark_overlay_uses_the_same_wide_camera_as_the_ohlc(renderer):
    plan=next(p for p in renderer.prepare(from_node="S07",to_node="S15") if p.node_id=="S09")
    scene=renderer.scene(plan)
    scene.frame(2*scene.model.fps)
    link=scene.last_layout["landmark_link"]
    assert link["projection_mode"]=="true_chart_close_path"
    assert not link["source_position_relocated"]
    assert link["from_close"]==pytest.approx(593.66)
    assert link["to_close"]==pytest.approx(3982.25)


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


@pytest.mark.parametrize("change",["earlier_time_label","earlier_quote_metadata"])
def test_outgoing_node_dependency_covers_earlier_beats_not_only_last_text(tmp_path,change):
    original=json.loads((ROOT/"config/production/film_master_v1.json").read_text())
    altered=json.loads(json.dumps(original))
    prior=next(n for n in altered["nodes"] if n["id"]=="S11")
    if change=="earlier_time_label":
        prior["beats"][0]["screen_lines"][0]="2015.06.27｜同期货币政策"
    else:
        prior["beats"][2]["direct_quotes"][0]["attribution"]="中国证监会当时公告"
    baseline_prior=next(n for n in original["nodes"] if n["id"]=="S11")
    assert prior["beats"][-1]==baseline_prior["beats"][-1]
    assert next(n for n in original["nodes"] if n["id"]=="S12")==next(n for n in altered["nodes"] if n["id"]=="S12")

    keys=[]
    for label,master_data in [("original",original),("changed",altered)]:
        path=tmp_path/f"{label}.json"
        path.write_text(json.dumps(master_data,ensure_ascii=False))
        renderer=FilmRenderer(ROOT,master_path=path,width=360,
            output_dir=tmp_path/label,cache_dir=tmp_path/"cache")
        plan=next(p for p in renderer.prepare("S10","S12") if p.node_id=="S12")
        keys.append(plan.cache_key)
        assert plan.signature_extra["previous_content"]["node_sha256"]
    assert keys[0]!=keys[1]


def test_unrelated_later_node_does_not_invalidate_outgoing_annotation_cache(tmp_path):
    original=json.loads((ROOT/"config/production/film_master_v1.json").read_text())
    altered=json.loads(json.dumps(original))
    unrelated=next(n for n in altered["nodes"] if n["id"]=="S15")
    unrelated["production_note"]="与S12前景无关的后段制作备注"
    keys=[]
    for label,master_data in [("original",original),("changed",altered)]:
        path=tmp_path/f"{label}.json"
        path.write_text(json.dumps(master_data,ensure_ascii=False))
        renderer=FilmRenderer(ROOT,master_path=path,width=360,
            output_dir=tmp_path/label,cache_dir=tmp_path/"cache")
        keys.append(next(p for p in renderer.prepare("S10","S12") if p.node_id=="S12").cache_key)
    assert keys[0]==keys[1]


def test_every_segment_join_preserves_projection_not_only_market_facts(renderer):
    plans=renderer.prepare(from_node="S07",to_node="S15")
    for left,right in zip(plans,plans[1:]):
        before=renderer.scene(left)
        after=renderer.scene(right)
        last=before.projected_market_point(left.total_frames-1)
        first=after.projected_market_point(0)
        assert last==pytest.approx(first,abs=1e-8)
        assert before.camera_projection(left.total_frames-1)==pytest.approx(after.camera_projection(0),abs=1e-8)
        # The previous annotation remains until the new dated wording enters;
        # an encoding seam is not a blank-card or empty-content frame.
        old=before.frame_context(left.total_frames-1)
        new=after.frame_context(0)
        assert old["content_opacity"]==pytest.approx(1.)
        assert new["previous_content_opacity"]==pytest.approx(1.)


def test_camera_pan_is_fractional_even_while_exact_close_is_held(renderer):
    plan=renderer.prepare(from_node="S07",to_node="S15")[0]
    scene=renderer.scene(plan)
    a,b=scene.model.state(1),scene.model.state(2)
    assert a.current_date==b.current_date
    assert a.current_close==b.current_close
    assert scene.camera_projection(1)["window_start"]!=scene.camera_projection(2)["window_start"]
    assert not scene.camera_projection(2)["window_start"].is_integer()


def test_zoom_is_a_curve_after_the_join_and_not_a_single_frame_cut(renderer):
    plan=next(p for p in renderer.prepare(from_node="S07",to_node="S15") if p.node_id=="S09")
    scene=renderer.scene(plan)
    early=scene.camera_projection(0)
    midway=scene.camera_projection(12)
    wide=scene.camera_projection(30)
    settled=scene.camera_projection(6*scene.model.fps)
    assert early["window_span"]<midway["window_span"]<wide["window_span"]
    assert wide["window_span"]>600
    assert settled["window_span"]==36


def test_2012_low_and_2015_high_share_the_same_true_price_projection(renderer):
    plan=next(p for p in renderer.prepare(from_node="S07",to_node="S15") if p.node_id=="S09")
    scene=renderer.scene(plan)
    camera=scene.camera_projection(2*scene.model.fps)
    for date in ["2012-12-03","2015-06-03"]:
        index=scene.model.market.index_for_date(date)
        price=float(scene.model.market.close[index])
        x=26+(index-camera["window_start"])/camera["window_span"]*678
        y=846-(price-camera["y_min"])/(camera["y_max"]-camera["y_min"])*596
        assert 26<x<704
        assert 252<y<846
    # The factual market still holds the same actual high while the camera
    # recalls the low. The historical source is never moved into a close-up.
    assert date_string(scene.model.state(2*scene.model.fps).current_date)=="2015-06-03"


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


def test_landmark_history_caption_does_not_overlap_actual_timeline_years(tmp_path):
    # The standalone layer fits the canvas but can still cross a year label
    # once composed over the earth. Exercise the target-size real composition.
    target = FilmRenderer(ROOT, width=1080, output_dir=tmp_path / "landmark_layout",
                          cache_dir=tmp_path / "cache")
    plans = {p.node_id: p for p in target.prepare("S07", "S15")}
    for node_id in ["S09", "S15"]:
        scene = target.scene(plans[node_id])
        for seconds in [.9, 1.5, 2.5, 3.5, 4.4]:
            scene.frame(round(seconds * 30))
            diagnostic = scene.last_layout
            assert not diagnostic["out_of_bounds"], (node_id, seconds)
            assert not diagnostic["text_overlaps"], (node_id, seconds, diagnostic["text_overlaps"])
