"""Production invariants, including the failures found in the supplied draft."""
from pathlib import Path
import json
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.model import MarketData, SceneModel


def model(config=None, events=None, csv=None):
    return SceneModel(config or ROOT/"config/v6_sample.json",
                      events or ROOT/"config/events_v6.json", csv or ROOT/"data/cyb_daily.csv")


def write_json(tmp_path, name, value):
    p = tmp_path / name
    p.write_text(json.dumps(value, ensure_ascii=False))
    return p


def test_factual_hud_and_endpoint_are_real_csv_values():
    m = model()
    assert len(m.states) == 42*30
    assert all(s.current_close == float(m.market.close[s.current_index]) for s in m.states)
    assert all(s.current_date == m.market.dates[s.current_index] for s in m.states)
    last = m.states[-1]
    assert last.t == 42.0
    assert str(last.current_date.date()) == "2015-09-15"
    assert last.current_close == 1797.56
    assert last.stage_value == pytest.approx(1797.56/3982.25-1)


def test_events_and_extrema_hit_the_same_date_as_market_cursor():
    m = model()
    for event in (*m.events, *m.critical_points):
        state = m.state(m.frame_for_time(event.hit_t))
        assert state.current_index == event.index
    assert m.state(m.frame_for_time(6)).current_close == 2734.75
    assert m.state(m.frame_for_time(21)).current_close == 3982.25
    assert m.state(m.frame_for_time(32)).current_close == 3314.98


def test_only_verified_enabled_events_enter_production(tmp_path):
    m = model()
    assert {e.id for e in m.events} == {"multi_account_2015", "accounts_2015"}
    assert {e["id"] for e in m.excluded_events} == {"margin_cleanup_2015"}
    events = json.loads((ROOT/"config/events_v6.json").read_text())
    events[0]["release_grade"] = "B"
    events[0]["enabled"] = True
    other = model(events=write_json(tmp_path, "events.json", events))
    assert "multi_account_2015" not in {e.id for e in other.events}
    assert all("multi_account_2015" not in s.active_event_ids for s in other.states)


def test_no_silent_mapping_of_weekends_or_out_of_range_dates():
    market = MarketData(ROOT/"data/cyb_daily.csv")
    with pytest.raises(ValueError, match="No exact trading day"):
        market.index_for_date("2015-06-13")
    with pytest.raises(ValueError, match="No exact trading day"):
        market.index_for_date("2009-10-30")
    index = market.index_for_date("2015-06-13", strict=False)
    assert str(market.dates[index].date()) == "2015-06-12"


def test_wrong_event_hit_cannot_be_rendered(tmp_path):
    events = json.loads((ROOT/"config/events_v6.json").read_text())
    events[1]["hit_t"] = 5.5
    with pytest.raises(ValueError, match="hit_t disagrees"):
        model(events=write_json(tmp_path, "wrong_events.json", events))


def test_supplied_22_second_draft_mismatch_is_rejected():
    with pytest.raises(ValueError, match="post_high_metric.*hit_t disagrees"):
        model(config=ROOT/"config/v6_storyboard_draft.json",
              events=ROOT/"config/events_v6_draft.json")


def test_critical_price_cannot_disagree_with_csv(tmp_path):
    config = json.loads((ROOT/"config/v6_sample.json").read_text())
    config["critical_points"][0]["price"] += 1
    with pytest.raises(ValueError, match="differs from CSV"):
        model(config=write_json(tmp_path, "wrong_price.json", config))


def test_single_stage_transitions_and_real_retracement():
    m = model()
    high = m.state(m.frame_for_time(21))
    retreat = m.state(m.frame_for_time(32))
    assert high.stage_mode == "rise_from_low"
    assert high.stage_value == pytest.approx(3982.25/593.66-1)
    assert high.stage_progress == pytest.approx(1)
    assert retreat.stage_mode == "drawdown_from_high"
    assert retreat.stage_value == pytest.approx(3314.98/3982.25-1)
    assert len(retreat.completed_milestones) == 1
    assert retreat.completed_milestones[0]["id"] == "rise_from_low"
    # A real retracement during the rise must reduce progress, not animate as
    # an ever-increasing elapsed-time meter.
    pairs = [(a, b) for a, b in zip(m.states, m.states[1:])
             if a.stage_mode == b.stage_mode == "rise_from_low" and b.current_close < a.current_close]
    assert pairs
    assert all(b.stage_progress < a.stage_progress for a, b in pairs)


def test_event_reading_camera_is_stable():
    m = model()
    counter = [s for s in m.states if 6.8 < s.t < 12]
    assert len(counter) > 100
    assert len({(s.y_min, s.y_max) for s in counter}) == 1
    assert {s.shot_id for s in counter} == {"accounts_counter"}


def test_invalid_ohlc_and_duplicate_dates_are_not_silently_repaired(tmp_path):
    df = pd.read_csv(ROOT/"data/cyb_daily.csv", encoding="utf-8-sig").head(3)
    df.loc[1, "high"] = df.loc[1, "low"] - 1
    bad = tmp_path/"bad_ohlc.csv"
    df.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="Invalid OHLC"):
        MarketData(bad)
    df = pd.read_csv(ROOT/"data/cyb_daily.csv", encoding="utf-8-sig").head(3)
    df.loc[1, "date"] = df.loc[0, "date"]
    df.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="unique and strictly increasing"):
        MarketData(bad)


def test_high_point_keeps_three_seconds_of_true_closeup_before_pullback():
    m = model()
    # This protects the actual camera behaviour, rather than only the shot
    # name: the initial retreat must not pre-frame September's entire crash.
    closeup = [s for s in m.states if 29 <= s.t < 32]
    assert len(closeup) >= 89
    assert all(s.visible_days <= 45 for s in closeup)
    september_low = next(cp.price for cp in m.critical_points if cp.id == "drawdown_low")
    assert all(s.y_min > september_low for s in closeup)
    assert all(s.y_max-s.y_min < 2200 for s in closeup)
    # The same date cursor still reaches the real June 19 close before a
    # separate shot expands the camera toward September.
    jun19 = m.state(m.frame_for_time(32))
    assert str(jun19.current_date.date()) == "2015-06-19"
    assert jun19.current_close == 3314.98
    later = m.state(m.frame_for_time(35))
    assert later.visible_days > closeup[-1].visible_days
