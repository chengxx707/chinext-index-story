"""Whole-film invariants across the explicit historical jumps and source layers."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.production import ProductionError, ProductionTimeline

MASTER = ROOT / "config/production/film_master_v1.json"


@pytest.fixture(scope="module")
def timeline():
    return ProductionTimeline(MASTER, root=ROOT)


def changed_master(tmp_path, mutate):
    data = json.loads(MASTER.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "film_master.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def node(data, node_id):
    return next(item for item in data["nodes"] if item["id"] == node_id)


def beat(timeline, node_id, beat_index=0):
    return next(item for item in timeline.beats
                if item.node_id == node_id and item.beat_index == beat_index)


def last_state(timeline, node_id, beat_index=0):
    return timeline.state_at_frame(beat(timeline, node_id, beat_index).end_frame_exclusive - 1)


def test_complete_master_has_exact_media_endpoint(timeline):
    assert timeline.fps == 30
    assert timeline.duration_seconds == 427
    assert timeline.total_frames == 12810
    assert len(timeline.nodes) == 57
    assert len(timeline.beats) == 75
    first = timeline.state_at_frame(0)
    last = timeline.state_at_frame(timeline.total_frames - 1)
    assert first.node_id == "H01"
    assert last.node_id == "C03"
    assert last.current_date == "2026-11-10"
    assert last.current_close == pytest.approx(2494.40)
    with pytest.raises(IndexError):
        timeline.state_at_frame(-1)
    with pytest.raises(IndexError):
        timeline.state_at_frame(timeline.total_frames)


def test_each_boundary_selects_the_correct_half_open_beat(timeline):
    for current, following in zip(timeline.beats, timeline.beats[1:]):
        assert current.end_frame_exclusive == following.start_frame
        at_end = timeline.state_at_frame(current.end_frame_exclusive - 1)
        at_next = timeline.state_at_frame(following.start_frame)
        assert (at_end.node_id, at_end.beat_index) == (current.node_id, current.beat_index)
        assert (at_next.node_id, at_next.beat_index) == (following.node_id, following.beat_index)
    assert timeline.beats[0].start_frame == 0
    assert timeline.beats[-1].end_frame_exclusive == timeline.total_frames


def test_all_dated_hud_facts_equal_one_real_csv_record(timeline):
    import csv
    with (ROOT / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as handle:
        closes = {row["date"]: float(row["close"]) for row in csv.DictReader(handle)}
    # Cover every frame in the half-open intervals, not only the declared anchors.
    for frame_number in range(timeline.total_frames):
        state = timeline.state_at_frame(frame_number)
        if state.show_hud:
            assert state.current_date in closes
            assert state.current_close == closes[state.current_date]


def test_explicit_rewind_declaration_is_required(tmp_path):
    path = changed_master(tmp_path, lambda data: node(data, "H04").update(declared_time_jump=None))
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_era_album_recap_is_declared_and_does_not_change_main_history(timeline):
    assert last_state(timeline, "S44").current_date == "2026-11-10"
    album = last_state(timeline, "A01")
    assert album.historical_date == "2010-06-01"
    assert not album.show_hud
    assert last_state(timeline, "C03").current_date == "2026-11-10"


def test_main_market_clock_cannot_silently_reverse(tmp_path):
    path = changed_master(tmp_path, lambda data: node(data, "S10")["beats"][0].update(market_anchor="2015-04-13"))
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_nontrading_policy_date_is_separate_from_hud_trade_date(timeline):
    state = last_state(timeline, "S11", 0)
    assert state.historical_date == "2015-06-27"
    assert state.event_market_anchor == "2015-06-26"
    assert state.current_date == "2015-06-26"
    assert state.hud_label == "上一交易日"


def test_intraday_policy_never_displays_unfinished_close(timeline):
    policy = last_state(timeline, "S42", 0)
    close = last_state(timeline, "S42", 1)
    assert policy.historical_date == "2026-11-04"
    assert policy.current_date == "2026-11-03"
    assert policy.hud_label == "上一交易日"
    assert close.current_date == "2026-11-04"
    assert close.current_close == pytest.approx(2544.73)
    assert close.hud_label == "当日收盘"


def test_market_origin_and_base_marker_never_fabricate_a_candle(timeline):
    for node_id in ["P00", "S01"]:
        state = last_state(timeline, node_id)
        assert not state.show_hud
        assert not state.show_chart
        assert state.current_date is None
        assert state.current_close is None
    first_candle = last_state(timeline, "S01", 1)
    assert first_candle.current_date == "2010-06-01"
    assert first_candle.current_close == pytest.approx(973.23)


def test_unbound_month_fact_keeps_its_original_precision(timeline):
    state = last_state(timeline, "S06")
    assert state.historical_date == "2014-01"
    assert state.date_precision == "month"
    assert state.event_market_anchor is None
    assert "2014.01" in state.screen_lines
    assert "2014.01.08" not in " ".join(state.screen_lines)


def test_claimed_direct_quote_must_exist_in_its_archived_body(tmp_path):
    def mutate(data):
        quote = node(data, "S20")["beats"][1]["direct_quotes"][0]
        quote["text"] = "全体投资者已经恢复信心"
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_quote_on_screen_cannot_disagree_with_verified_quote_field(tmp_path):
    def mutate(data):
        node(data, "S20")["beats"][1]["screen_lines"][1] = "“全体投资者已经恢复信心”"
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_selected_source_file_is_mandatory(tmp_path):
    def mutate(data):
        data["sources"]["AR01"]["document"] = "assets/source_documents/missing-interview.html"
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_selected_source_hash_cannot_be_stale(tmp_path):
    def mutate(data):
        data["sources"]["AR01"]["sha256"] = "0" * 64
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_coverage_gap_is_rejected_before_render(tmp_path):
    def mutate(data):
        node(data, "S03")["beats"][1]["start_frame"] += 1
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_unregistered_source_cannot_be_drawn(tmp_path):
    def mutate(data):
        node(data, "S20")["source_ids"].append("AR_NOT_PROVIDED")
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_pending_fact_cannot_bypass_qualification_by_reusing_A_source_kind(tmp_path):
    def mutate(data):
        data["sources"]["U:huayi_2013"]["claim_id"] = "industry_ai"
    path = changed_master(tmp_path, mutate)
    with pytest.raises(ProductionError):
        ProductionTimeline(path, root=ROOT)


def test_explicit_market_override_must_match_the_frozen_csv_hash(tmp_path):
    import csv
    with (ROOT / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    # This remains inside the real candle's OHLC range, so range checks alone
    # cannot detect that an explicit override silently changed the frozen facts.
    rows[0]["close"] = "973.24"
    replacement = tmp_path / "changed_market.csv"
    with replacement.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ProductionError):
        ProductionTimeline(MASTER, root=ROOT, csv_path=replacement)
