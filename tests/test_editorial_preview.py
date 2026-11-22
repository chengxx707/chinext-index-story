"""Focused regressions for the isolated WF-02R1 editorial adapter."""

import json
from pathlib import Path
import sys

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chinext_v6.editorial_clock import EditorialClock
from chinext_v6.editorial_overlay import _event_label
from chinext_v6.editorial_revision import resolve_director
from chinext_v6.editorial_validation import validate_run
from tools.render_editorial_preview import EditorialScene

RELEASE = ROOT / "editorial/2015/releases/v1.0.1"
REVISION = ROOT / "config/editorial/wf-02r1-2015.json"


@pytest.fixture(scope="module")
def director():
    return resolve_director(ROOT, RELEASE, REVISION, photo_available=False)


@pytest.fixture(scope="module")
def clock(director):
    return EditorialClock(ROOT, RELEASE, 540, director=director, photo_available=False)


def test_all_cues_keep_market_row_and_projection_at_joins(clock):
    assert (clock.fps, clock.total_frames, len(clock.cues)) == (30, 5010, 28)
    for cue in clock.cues[1:]:
        start = cue["start_frame"]
        assert clock.states[start - 1].current_index == clock.states[start].current_index
        assert clock.projections[start] == pytest.approx(clock.projections[start - 1])
        assert clock.cue_at(start) == cue
    assert clock.projections[990]["window_span"] == pytest.approx(48)
    with pytest.raises(IndexError):
        clock.cue_at(5010)


def test_historical_month_caption_is_independent_of_hud(clock):
    cue = clock.cue_at(1326)
    assert cue["shot_id"] == "GPT2015-08"
    assert _event_label(cue["event_clock"]) == "2015年6月"
    assert cue["event_clock"]["date"] == "2015-06-18"
    assert clock.states[1326].current_date.date().isoformat() == "2015-06-18"
    assert clock.states[1469].current_date > clock.states[1326].current_date


def test_weekend_and_after_close_event_freezes_use_the_real_close(clock):
    weekend = clock.cue_at(1690)
    assert weekend["event_clock"]["date"] == "2015-06-27"
    assert {(state.current_date.date().isoformat(), state.current_close)
            for state in clock.states[1680:1860]} == {("2015-06-26", 2920.70)}
    assert {(state.current_date.date().isoformat(), state.current_close)
            for state in clock.states[3975:4320]} == {("2015-08-25", 1990.71)}
    policy, voice = clock.cue_at(3981), clock.cue_at(4191)
    assert policy["text_cue"]["full_alpha_from_frame"] == 3981
    assert voice["text_cue"]["full_alpha_from_frame"] == 4191
    assert policy["event_clock"]["time"] == "18:15:34"
    assert voice["event_clock"]["time"] == "19:16"


def test_rail_is_price_based_and_retraces_during_rebound(clock):
    before, after = clock.states[959], clock.states[960]
    assert before.stage_mode != after.stage_mode
    assert sum(left.stage_mode != right.stage_mode
               for left, right in zip(clock.states, clock.states[1:])) == 1
    rebound_start, rebound_end = (
        next(state for state in clock.states if state.current_date.date().isoformat() == day)
        for day in ("2015-07-07", "2015-07-23")
    )
    assert rebound_start.stage_value == pytest.approx(2352.01 / 3982.25 - 1)
    assert rebound_end.stage_value == pytest.approx(2967.95 / 3982.25 - 1)
    assert rebound_end.stage_progress < rebound_start.stage_progress
    assert clock.states[-1].stage_value == pytest.approx(1797.56 / 3982.25 - 1)


def test_photo_clock_and_overlay_branches_preserve_market_and_credit(clock, director):
    present = resolve_director(ROOT, RELEASE, REVISION, photo_available=True)
    present_clock = EditorialClock(ROOT, RELEASE, 540, director=present, photo_available=True)
    photo_frames = slice(3630, 3780)
    assert present_clock.projections[photo_frames] == clock.projections[photo_frames]
    assert all(state.current_close == 2152.61 for state in present_clock.states[photo_frames])
    scene = EditorialScene(RELEASE, 540, director=director)
    scene.frame(3651)
    absent = scene.last_layout["overlay"]
    assert absent["missing_photo"] and not absent["photo_visible"] and not absent["text_visible"]

    # An in-memory synthetic image only exercises drawing code. It is never saved
    # or accepted as the historical photo by the preview entry point.
    scene.photo = Image.new("RGB", (940, 625), "#304050")
    scene.frame(3651)
    shown = scene.last_layout["overlay"]
    assert shown["photo_visible"] and not shown["missing_photo"]
    assert "中新社发 刘冉阳 摄" in scene.clock.cue_at(3651)["text_cue"]["source_line"]


def test_current_run_reports_hashes_and_rejects_tampered_parsed_config(tmp_path, clock, director):
    resolved_path = tmp_path / "resolved_director_timeline.json"
    resolved_path.write_text(json.dumps(director, ensure_ascii=False), encoding="utf-8")
    report = validate_run(ROOT, RELEASE, REVISION, resolved_path, tmp_path, clock, None, None)
    assert report["passed"] and not report["complete_photo_preview_verified"]
    assert report["missing"]["historical_photo_scene"]["asset_id"] == "IMG-20150824-01"
    assert report["input_hashes"]["actual_media"] is None
    assert report["input_hashes"]["resolved_director_timeline"]["sha256"]
    state = json.loads((tmp_path / "clock_validation.json").read_bytes())
    assert state["frames"] == 5010 and state["joins_checked"] == 27

    incompatible = json.loads(resolved_path.read_bytes())
    incompatible["cues"][20]["primary_anchor"]["value"] = 2152.60
    resolved_path.write_text(json.dumps(incompatible, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="verification failed"):
        validate_run(ROOT, RELEASE, REVISION, resolved_path, tmp_path, clock, None, None)
    assert not json.loads((tmp_path / "resolved_config_validation.json").read_bytes())["passed"]
