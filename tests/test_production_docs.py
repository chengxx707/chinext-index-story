"""The document must preserve selected copy and reject broken production links."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("production_docs", ROOT / "tools/export_production_docs.py")
exporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(exporter)


@pytest.fixture
def master():
    return json.loads((ROOT / "config/production/film_master_v1.json").read_text())


def test_complete_copy_and_evidence_survive_export(master):
    result = exporter.render_markdown(master)
    assert "07:07" in result
    assert "正文44个单元" in result
    for node in master["nodes"]:
        assert f'#### {node["id"]}｜' in result
        for beat in node["beats"]:
            assert "\n".join(beat["screen_lines"]) in result
            if beat.get("source_line"):
                assert beat["source_line"] in result
            if beat.get("implementation_note"):
                assert beat["implementation_note"] in result
    for source_id in master["sources"]:
        assert f"### {source_id}\n" in result
    for item in master["deferred"]:
        assert item["current_fallback"] in result
    assert exporter.render_markdown(master) == result


@pytest.mark.parametrize("damage,match", [
    ("duplicate_id", "Node IDs"),
    ("unknown_source", "Unknown source"),
    ("node_gap", "Node frame coverage"),
    ("beat_gap", "Beat frame coverage"),
    ("missing_copy", "Missing screen text"),
    ("wrong_total", "duration and frame plan"),
])
def test_export_rejects_incomplete_or_ambiguous_master(master, damage, match):
    if damage == "duplicate_id":
        master["nodes"][1]["id"] = master["nodes"][0]["id"]
    elif damage == "unknown_source":
        master["nodes"][0]["source_ids"].append("MISSING")
    elif damage == "node_gap":
        master["nodes"][1]["start_frame"] += 1
    elif damage == "beat_gap":
        master["nodes"][0]["beats"][0]["start_frame"] += 1
    elif damage == "missing_copy":
        master["nodes"][0]["beats"][0]["screen_lines"] = []
    else:
        master["video"]["frame_count_plan"] += 30
    with pytest.raises(ValueError, match=match):
        exporter.render_markdown(master)


def test_check_detects_stale_copy_without_overwriting(tmp_path, master):
    source = tmp_path / "master.json"
    source.write_text(json.dumps(master, ensure_ascii=False))
    target = tmp_path / "screen_copy.md"
    assert exporter.main(["--master", str(source), "--output", str(target)]) == 0
    assert exporter.main(["--master", str(source), "--output", str(target), "--check"]) == 0
    before = target.read_bytes()
    changed = copy.deepcopy(master)
    changed["nodes"][0]["beats"][0]["screen_lines"][2] = "修订后的历史标签"
    source.write_text(json.dumps(changed, ensure_ascii=False))
    assert exporter.main(["--master", str(source), "--output", str(target), "--check"]) == 1
    assert target.read_bytes() == before
