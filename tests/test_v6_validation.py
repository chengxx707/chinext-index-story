"""Negative acceptance cases: bad inputs must fail rather than look validated."""
from __future__ import annotations

import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("project_validator", ROOT / "tools/validate_project.py")
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


def checks(report):
    return {item["id"]: item for item in report.checks}


@pytest.fixture(scope="module")
def model():
    from chinext_v6.model import SceneModel
    return SceneModel(ROOT / "config/v6_sample.json", ROOT / "config/events_v6.json", ROOT / "data/cyb_daily.csv")


@pytest.fixture(scope="module")
def raw_events():
    return json.loads((ROOT / "config/events_v6.json").read_text())


def test_bad_ohlc_and_duplicate_date_fail():
    report = validator.Report()
    row = {"date": "2020-01-02", "open": "10", "close": "12", "low": "9", "high": "11", "pct_chg": "1"}
    validator.validate_market_rows([row, dict(row)], report)
    assert not checks(report)["market.ohlc"]["passed"]
    # Invalid price rows do not populate the date collection; use valid rows
    # separately to verify original-file date ordering.
    row["high"] = "13"
    report = validator.Report()
    validator.validate_market_rows([row, dict(row)], report)
    assert not checks(report)["market.unique_chronological_dates"]["passed"]
    assert not report.as_dict()["passed"]


def test_interpolated_hud_close_is_rejected(model, raw_events):
    broken = copy.copy(model)
    states = list(model.states)
    states[50] = replace(states[50], current_close=states[50].current_close + 0.123)
    broken.states = tuple(states)
    report = validator.Report()
    validator.validate_model(broken, raw_events, report)
    assert not checks(report)["timeline.real_close_and_date"]["passed"]


def test_omitted_terminal_frame_is_rejected(model, raw_events):
    broken = copy.copy(model)
    # The actual sample intentionally holds the final date. Remove the hold
    # as well as the final frame to emulate the previous seed's early ending.
    broken.states = tuple(s for s in model.states if validator.day_string(s.current_date) != model.config["sample"]["end_date"])
    report = validator.Report()
    validator.validate_model(broken, raw_events, report)
    assert not checks(report)["timeline.last_frame_reaches_end"]["passed"]
    assert not checks(report)["timeline.frame_count"]["passed"]


def test_early_event_hit_is_rejected(model, raw_events):
    broken = copy.copy(model)
    event = next(e for e in model.events if e.id == "accounts_2015")
    broken.events = tuple(replace(e, hit_t=4.0) if e.id == event.id else e for e in model.events)
    report = validator.Report()
    validator.validate_model(broken, raw_events, report)
    assert not checks(report)["events.hit_date_matches_candle_and_frame"]["passed"]


def test_disabled_event_leak_is_rejected(model, raw_events):
    broken_raw = copy.deepcopy(raw_events)
    broken_raw[0]["enabled"] = False
    report = validator.Report()
    validator.validate_model(model, broken_raw, report)
    assert not checks(report)["events.disabled_and_unverified_do_not_leak"]["passed"]


def test_layout_outside_and_colliding_text_are_rejected():
    result = validator.validate_boxes({"text_boxes": [
        {"id": "outside", "bbox": [-3, 0, 20, 20]},
        {"id": "collision", "bbox": [10, 10, 30, 30]},
    ]}, 1080, 1920)
    assert any(item["error"] == "text outside frame" for item in result)
    assert any(item["error"] == "measured text boxes overlap" for item in result)


def test_media_preview_cannot_pass_production_size():
    report = validator.Report()
    validator.validate_video_metadata({"streams": [{"codec_type": "video", "width": 720, "height": 1280,
                                        "avg_frame_rate": "30/1", "nb_frames": "1260"}],
                                       "format": {"duration": "42"}},
                                      {"width": 1080, "height": 1920, "fps": 30, "duration_seconds": 42}, report)
    assert not checks(report)["media.dimensions_and_fps"]["passed"]


def test_source_registry_rejects_changed_metric(tmp_path):
    (tmp_path / "research.md").write_text("known research", encoding="utf-8")
    event = {"id": "counter", "enabled": True, "release_grade": "A", "source_id": "weekly_stat",
             "date": "2015-04-24", "date_precision": "range", "metric_value": 999.0}
    registry = {"events": [{"id": "weekly_stat", "enabled": True, "release_grade": "A",
                            "date_precision": "range", "anchor_date": "2015-04-24", "metric": {"value": 413.03},
                            "evidence": {"document": "research.md", "section": "5.1"}}]}
    report = validator.Report()
    validator.validate_event_sources([event], registry, report, repository_root=tmp_path)
    assert not checks(report)["events.enabled_sources_resolve"]["passed"]


def test_camera_breathing_during_reading_is_rejected(model, raw_events):
    broken = copy.copy(model)
    states = list(model.states)
    states[50] = replace(states[50], y_min=states[50].y_min + 10)
    broken.states = tuple(states)
    report = validator.Report()
    validator.validate_model(broken, raw_events, report)
    assert not checks(report)["camera.reading_range_stable_after_entry"]["passed"]


def test_provenance_changes_when_renderer_or_asset_changes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "assets").mkdir()
    source = tmp_path / "src/draw.py"
    asset = tmp_path / "assets/earth.png"
    source.write_text("color = 'red'\n")
    asset.write_bytes(b"original")
    original = validator.production_provenance(tmp_path)
    source.write_text("color = 'blue'\n")
    changed_source = validator.production_provenance(tmp_path)
    assert changed_source["source_tree_sha256"] != original["source_tree_sha256"]
    assert changed_source["asset_hashes"] == original["asset_hashes"]
    asset.write_bytes(b"new asset")
    changed_asset = validator.production_provenance(tmp_path)
    assert changed_asset["asset_hashes"] != original["asset_hashes"]


def test_missing_input_writes_failed_result(tmp_path):
    result = validator.validate(tmp_path / "missing.json", ROOT / "config/events_v6.json", ROOT / "data/cyb_daily.csv")
    assert not result["passed"]
    assert result["manual_review"]["status"] == "pending"


def test_cli_failure_preserves_exit_status_and_report(tmp_path):
    output = tmp_path / "failed.json"
    completed = subprocess.run([sys.executable, str(ROOT / "tools/validate_project.py"),
                                "--config", str(tmp_path / "missing.json"), "--output", str(output)],
                               capture_output=True, text=True)
    assert completed.returncode == 1
    result = json.loads(output.read_text())
    assert not result["passed"] and result["summary"]["failed"] > 0


def test_unexpected_audio_track_blocks_silent_delivery():
    report = validator.Report()
    validator.validate_video_metadata({"streams": [{"codec_type": "video", "width": 1080, "height": 1920,
                                        "avg_frame_rate": "30/1", "nb_frames": "1260"}, {"codec_type": "audio"}],
                                       "format": {"duration": "42"}},
                                      {"width": 1080, "height": 1920, "fps": 30, "duration_seconds": 42}, report)
    assert not checks(report)["media.one_video_no_audio"]["passed"]


def test_current_real_model_passes_fact_and_state_checks(model, raw_events):
    report = validator.Report()
    validator.validate_model(model, raw_events, report)
    assert report.as_dict()["passed"], report.as_dict()["problems"]
