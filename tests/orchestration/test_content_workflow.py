"""Exercise WF-01B's evidence gate and camera-ready candidate contracts."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from orchestration.workflows.content import OUTPUTS, run_content
from orchestration.workflows.content.market import MARKET_SOURCE, Market
from orchestration.workflows.research import run_research
from orchestration.workflows.schema import SchemaViolation, validate_schema


ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "config/production/film_master_v1.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def candidate(tmp_path_factory):
    audit_root = tmp_path_factory.mktemp("wf01b")
    upstream, output = audit_root / "research", audit_root / "candidate"
    run_research(ROOT, upstream)
    assert run_content(ROOT, upstream, output) == OUTPUTS
    return upstream, output


def test_close_extrema_drawdown_and_intraday_points_are_distinct(candidate):
    _, output = candidate
    market = read(output / "period_storyboard.json")["pilot_market_metrics"]
    assert market["highest_close"] == {"date": "2015-06-03", "value": 3982.25}
    assert market["intraday_high"] == {"date": "2015-06-05", "value": 4037.96}
    assert market["lowest_close"] == {"date": "2015-09-15", "value": 1797.56}
    assert market["intraday_low"] == {"date": "2015-09-02", "value": 1779.18}
    assert market["max_drawdown"]["peak"] == market["highest_close"]
    assert market["max_drawdown"]["trough"] == market["lowest_close"]
    assert market["max_drawdown"]["percent"] == pytest.approx((1797.56 / 3982.25 - 1) * 100, abs=1e-6)
    assert market["calendar_days_inclusive"] > market["trading_days"]
    assert market["daily_volatility_percent"] > 0
    assert market["range_amplitude_percent"] > 0


def test_three_full_gaps_and_three_day_return_use_separate_windows(candidate):
    _, output = candidate
    market = read(output / "period_storyboard.json")["pilot_market_metrics"]
    assert market["august_full_down_gap_dates"] == ["2015-08-21", "2015-08-24", "2015-08-25"]
    rows = market["august_observations"]
    assert all(row["high"] < row["previous_low"] for row in rows[:3])
    assert rows[-1]["date"] == "2015-08-26"
    assert rows[-1]["opened_below_previous_close"] and not rows[-1]["full_down_gap"]
    change = market["august_24_26_return"]
    assert change["start_date"] == "2015-08-24" and change["end_date"] == "2015-08-26"
    assert change["trading_days"] == 3
    assert change["baseline"] == {"date": "2015-08-21", "value": 2341.95}
    assert change["percent"] == pytest.approx((1890.04 / 2341.95 - 1) * 100, abs=1e-6)


def test_period_metrics_use_real_volume_and_keep_missing_volume_unknown(tmp_path):
    market = Market(ROOT / MARKET_SOURCE)
    period = market.analytics("week", "四月观察", "2015-04-20", "2015-04-24")
    assert period["volume"]["source_column"] == "volume"
    assert period["volume"]["total"] == 178548024
    assert period["volume"]["observed_trading_days"] == period["trading_days"] == 5
    assert period["return_basis"] == {"date": "2015-04-17", "value": 2463.99}
    path = tmp_path / "ohlc.csv"
    path.write_text("date,open,high,low,close,amount\n2015-04-20,10,12,9,11,10000\n", encoding="utf-8")
    limited = Market(path).analytics("one", "单日测试", "2015-04-20", "2015-04-20")
    assert limited["volume"] is None
    assert limited["daily_volatility_percent"] is None
    assert limited["period_return_percent"] is None


def test_evidence_policy_and_post_close_timing(candidate):
    _, output = candidate
    story = read(output / "period_storyboard.json")
    events = {item["event_id"]: item for item in story["event_market_mapping"]}
    beats = {item["beat_id"]: item for item in story["story_beats"]}
    saturday = events["june-pbc-faq"]
    assert (saturday["event_date"], saturday["market_anchor"]) == ("2015-06-27", "2015-06-26")
    assert saturday["market_anchor_kind"] == "explicit_previous_trading_day"
    announcement = events["august-pbc-announcement"]
    assert announcement["after_close"] and announcement["relation"] == "co_occurrence"
    assert announcement["announcement_at"] == "2015-08-25T18:15:34+08:00"
    assert announcement["implementation_dates"] == [
        {"measure": "降息", "date": "2015-08-26"}, {"measure": "降准", "date": "2015-09-06"},
    ]
    order = list(beats)
    assert order.index("august-gap-3") < order.index("august-pbc-announcement") < order.index("august-26")
    assert not any(item["causal_claim"] for item in events.values())
    assert beats["july-csrc-voice"]["classification"] == "opinion"
    assert "证监会公告" in beats["july-csrc-voice"]["source_line"]
    assert "april-volume" in beats
    for blocked in ("april-new-a-accounts", "may-letv-context", "industry-mobile-internet", "august-cnr-voice"):
        assert events[blocked]["further_research_needed"]
        assert not events[blocked]["on_screen_eligible"]
        assert blocked not in beats
    assert "413.03" not in (output / "period_screen_copy.md").read_text(encoding="utf-8")


def test_verified_label_alone_does_not_unlock_excerpt_or_quote(tmp_path, candidate):
    upstream, _ = candidate
    evidence = read(upstream / "period_research.json")
    events = {event["event_id"]: event for event in evidence["events"]}
    events["april-new-a-accounts"].update(evidence_status="VERIFIED", display_candidate=True, verification_notes={})
    # The input excerpt still contains the words, but the matched excerpt data no longer supports it.
    event = events["july-csrc-voice"]
    event["verification_notes"]["excerpts"] = [item for item in event["verification_notes"]["excerpts"]
                                                if "非理性下跌" not in item["excerpt"]]
    events["june-pbc-faq"]["verification_notes"]["direct_causal_claim"] = True
    (tmp_path / "period_research.json").write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "source_registry.json").write_bytes((upstream / "source_registry.json").read_bytes())
    output = tmp_path / "candidate"
    run_content(ROOT, tmp_path, output)
    story = read(output / "period_storyboard.json")
    blocked = {"april-new-a-accounts", "july-csrc-voice", "june-pbc-faq"}
    assert blocked.isdisjoint(beat["beat_id"] for beat in story["story_beats"])


def test_shot_unit_schema_provenance_and_deterministic_copy(tmp_path, candidate):
    upstream, output = candidate
    storyboard = read(output / "period_storyboard.json")
    production = read(output / "period_production.json")
    shots, units = production["shots"], production["production_units"]
    assert shots == storyboard["shots"]
    assert len(shots) == len(units) == len(storyboard["story_beats"])
    assert len(storyboard["market_periods"]) == len(storyboard["stage_narratives"]) == 5
    source_ids = {source["source_id"] for source in storyboard["source_registry"]}
    assert all(set(item["source_ids"]) <= source_ids for item in units)
    assert not production["render_performed"] and not production["visual_rules"]["audio"]
    assert production["visual_rules"]["aspect_ratio"] == "9:16"
    assert units[0]["start_frame"] == 0
    assert units[-1]["end_frame_exclusive"] == production["planned_frame_count"]
    assert shots[-1]["end_market_date"] == "2015-09-15"
    for shot in shots:
        validate_schema("shot", shot)
        assert shot["end_market_date"] >= shot["start_market_date"]
    for previous, current in zip(units, units[1:]):
        assert previous["end_frame_exclusive"] == current["start_frame"]
        assert previous["end_market_date"] == current["start_market_date"]
    invalid = shots[0].copy()
    del invalid["event_animation"]
    with pytest.raises(SchemaViolation, match="event_animation"):
        validate_schema("shot", invalid)
    baseline = sha256(MASTER.read_bytes()).hexdigest()
    repeat = tmp_path / "repeat"
    run_content(ROOT, upstream, repeat)
    assert all((output / name).read_bytes() == (repeat / name).read_bytes() for name in OUTPUTS)
    assert baseline == production["provenance"]["frozen_master_sha256"] == sha256(MASTER.read_bytes()).hexdigest()
