from pathlib import Path
import sys

import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from chinext_v6.content_components import ContentDrawer, component_for


@pytest.fixture(scope="module")
def drawer():
    return ContentDrawer(ROOT,720)


def test_all_selected_master_beats_have_layout_inside_frame(drawer):
    # Every factual copy/source string is measured, including the longest policy
    # line and coarse-date facts, rather than only a hand-picked short example.
    for node in drawer.master["nodes"]:
        for i,beat in enumerate(node["beats"]):
            result=drawer.diagnostics(node["id"],i)
            assert not result["out_of_bounds"],(node["id"],i,result["out_of_bounds"])


def test_policy_previous_day_is_preserved_in_preview(drawer):
    result=drawer.diagnostics("S42",0)
    assert result["market_anchor"]=="2026-11-03"
    assert result["historical_date"]=="2026-11-04"
    assert any(x["text"]=="上一交易日" for x in result["text_boxes"])


def test_archive_and_company_album_do_not_invent_photographs(drawer):
    document=drawer.diagnostics("A04")
    company=drawer.diagnostics("A03")
    assert document["synthetic_archive_photography"] is False
    assert company["synthetic_archive_photography"] is False
    assert any("文献节选重排" in x["text"] for x in document["text_boxes"])
    assert any("宁德时代" in x["text"] for x in company["text_boxes"])
    assert not any("宁德时代" in x["text"] for x in document["text_boxes"])


def test_overlay_preserves_callers_background_away_from_content(drawer):
    base=Image.new("RGB",(720,1280),(13,29,41))
    result=drawer.overlay(base,"S20",1)
    assert result.getpixel((10,10))==base.getpixel((10,10))
    assert result.getpixel((700,1100))==base.getpixel((700,1100))
    assert result.getpixel((100,400))!=base.getpixel((100,400))


def test_unknown_component_and_invalid_beat_fail(drawer):
    with pytest.raises(ValueError):
        drawer.render("MISSING")
    with pytest.raises(IndexError):
        drawer.render("S20",99)
    with pytest.raises(ValueError):
        drawer.render("S20",0,kind="fake_photo")


def test_transition_budget_and_final_hold_follow_master(drawer):
    # A long reading card must not spend a percentage of its whole duration
    # fading. At .3 seconds it is fully visible until the final .4 seconds.
    duration=drawer.nodes["S34"]["beats"][0]["duration_seconds"]
    drawer.render("S34",progress=.3/duration)
    assert drawer._last_metadata["opacity"]==1.0
    drawer.render("S34",progress=(duration-.4)/duration)
    assert drawer._last_metadata["opacity"]==pytest.approx(1.0)
    drawer.render("C03",progress=1)
    assert drawer._last_metadata["opacity"]==1.0


def test_cached_content_layer_keeps_transparency_and_chart_identity(drawer):
    layer=drawer.content_layer("A03")
    assert layer.mode=="RGBA"
    assert layer.getpixel((10,10))[3]==0
    assert layer.getpixel((100,400))[3]>0
    assert any(x["text"]=="创业板指（399006）" and x["id"]=="album_chart_basis" for x in drawer.text_boxes)


def test_policy_timeline_does_not_preannounce_future_dates(drawer):
    drawer.content_layer("S11",0,kind="timeline")
    dates=[x["text"] for x in drawer.text_boxes if x["role"]=="timeline"]
    assert dates==["06.27"]
    drawer.content_layer("S11",1,kind="timeline")
    dates=[x["text"] for x in drawer.text_boxes if x["role"]=="timeline"]
    assert dates==["06.27","07.08"]


def test_return_uses_each_master_line_once_and_footer_only_at_bottom(drawer):
    result=drawer.diagnostics("C03",progress=1)
    lines=drawer.nodes["C03"]["beats"][0]["screen_lines"]
    for line in lines:
        assert sum(x["text"]==line for x in result["text_boxes"])==1
    footers=[x for x in result["text_boxes"] if x["role"]=="footer"]
    assert [x["text"] for x in footers]==lines[2:]
    assert all(x["bbox"][1]>drawer.height*.9 for x in footers)
    assert not any(x["id"] in {"footer_basis","footer_source"} for x in result["text_boxes"])


def test_first_and_final_actual_market_nodes_remain_inside_orbit_safe_area(drawer):
    # The shared curve extends beyond the canvas at u=0 and u=1. Time-axis
    # padding, rather than falsifying the node date, keeps both endpoints visible.
    for value in ["2010-06-01","2026-11-10"]:
        (x,y),_=drawer.base._timeline_point(value)
        assert 32<=x<=688
        assert 0<y<1280
