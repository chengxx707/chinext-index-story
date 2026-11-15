from pathlib import Path
import copy
import hashlib
import json
import sys

import numpy as np
import pytest
from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from chinext_v6.content_components import ContentDrawer, PhotoNotReady, StrictPhotoAlbum, component_for


@pytest.fixture(scope="module")
def drawer():
    return ContentDrawer(ROOT,720)


def test_all_selected_master_beats_have_layout_inside_frame(drawer):
    # Every factual copy/source string is measured, including the longest policy
    # line and coarse-date facts, rather than only a hand-picked short example.
    for node in drawer.master["nodes"]:
        for i,beat in enumerate(node["beats"]):
            if node.get("role")=="album":
                with pytest.raises(PhotoNotReady):
                    drawer.diagnostics(node["id"],i)
                continue
            result=drawer.diagnostics(node["id"],i)
            assert not result["out_of_bounds"],(node["id"],i,result["out_of_bounds"])


def test_policy_previous_day_is_preserved_in_preview(drawer):
    result=drawer.diagnostics("S42",0)
    assert result["market_anchor"]=="2026-11-03"
    assert result["historical_date"]=="2026-11-04"
    assert any(x["text"]=="上一交易日" for x in result["text_boxes"])


def test_album_refuses_missing_photos_instead_of_reusing_document_or_chart(drawer):
    for node in drawer.master["nodes"]:
        if node.get("role")=="album":
            with pytest.raises(PhotoNotReady):
                drawer.content_layer(node["id"])


def test_overlay_preserves_callers_background_away_from_content(drawer):
    base=Image.new("RGB",(720,1280),(13,29,41))
    result=drawer.overlay(base,"S20",1)
    assert result.getpixel((10,10))==base.getpixel((10,10))
    assert result.getpixel((700,1100))==base.getpixel((700,1100))
    assert ImageChops.difference(result,base).getbbox() is not None


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
    layer=drawer.content_layer("S07",1)
    assert layer.mode=="RGBA"
    assert layer.getpixel((10,10))[3]==0
    assert np.asarray(layer.getchannel("A")).max()>0
    assert any(x["text"]=="413.03万户" for x in drawer.text_boxes)


@pytest.mark.parametrize("node,beat,kind",[("S07",1,"event"),("S11",1,"timeline"),("S20",1,"quote"),("S24",0,"document"),("S34",0,"headline")])
def test_body_layers_leave_former_dark_board_areas_fully_transparent(drawer,node,beat,kind):
    layer=drawer.content_layer(node,beat,kind=kind)
    alpha=np.asarray(layer.getchannel("A"))
    # These regions were solid dark fills in V1. They contain no text or
    # hairline in V2, so original candles must remain literally untouched.
    if kind in {"event","timeline"}:
        clear=alpha[450:480,300:430]
    else:
        clear=alpha[470:550,200:550]
    assert clear.max()==0
    assert drawer._last_metadata["large_background_plate"] is False


def test_policy_timeline_does_not_preannounce_future_dates(drawer):
    drawer.content_layer("S11",0,kind="timeline")
    dates=[x["text"] for x in drawer.text_boxes if x["role"]=="timeline"]
    assert dates==["06.27"]
    drawer.content_layer("S11",1,kind="timeline")
    dates=[x["text"] for x in drawer.text_boxes if x["role"]=="timeline"]
    assert dates==["06.27","07.08"]


@pytest.mark.parametrize("beat_index",[0,1])
def test_september_policy_text_and_timeline_use_the_upper_right_whitespace(drawer,beat_index):
    layer=drawer.content_layer("S14",beat_index,kind="timeline")
    boxes=list(drawer.text_boxes)
    for box in boxes:
        x0,y0,x1,y1=box["bbox"]
        assert 0<=x0<x1<=720 and 0<=y0<y1<=1280
        if box["role"] in {"date","body","source"}:
            assert x0>=344
            assert x1<=657
        if box["role"]=="timeline":
            assert x0>=310 and x1<=690
    # The left-side historical high and its earlier candles remain untouched.
    assert np.asarray(layer.getchannel("A"))[250:430,55:320].max()==0
    raw=drawer.nodes["S14"]["beats"][beat_index]
    assert any(box["text"]==raw["screen_lines"][0] for box in boxes)
    assert "".join(box["text"] for box in boxes if box["role"]=="source")==raw["source_line"]


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


def qualified_fixture(tmp_path):
    # A contract fixture, not a claim that generated test pixels are a usable
    # historical photo. Production still needs recorded actual visual review.
    path=tmp_path/"photo.jpg"
    Image.new("RGB",(640,400),(70,90,110)).save(path)
    page=tmp_path/"story.html"
    page.write_text('<img src="https://example.invalid/photo.jpg"><p>TEST_PHOTO_CAPTION</p>')
    record={"asset_id":"fixture_photo","kind":"photograph","status":"qualified",
            "local_path":"photo.jpg","sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_page_url":"https://example.invalid/story","source_page_archive":"story.html",
            "source_page_sha256":hashlib.sha256(page.read_bytes()).hexdigest(),
            "image_url":"https://example.invalid/photo.jpg","original_caption":"TEST_PHOTO_CAPTION",
            "caption_locator":"p[0]","credit":"TEST_CREDIT","event_date":"2018-06-11",
            "article_publish_date":"2018-06-12","capture_date":"2018-06-11",
            "capture_date_precision":"day","is_file_photo":False,
            "depicted_entities":["TEST_SUBJECT"],"scene_event_id":"fixture_event",
            "visual_review":{"inspected":True,"is_real_photo":True,"subject_matches":True}}
    return {"assets":[record]},record


def test_real_photo_contract_requires_file_source_caption_and_matching_event(tmp_path):
    manifest,record=qualified_fixture(tmp_path)
    album=StrictPhotoAlbum(tmp_path,manifest)
    assert album.require_photo("fixture_photo","fixture_event")==record
    with pytest.raises(PhotoNotReady):
        album.require_photo("fixture_photo","wrong_company_or_event")
    (tmp_path/"photo.jpg").write_bytes(b"changed bytes")
    with pytest.raises(PhotoNotReady):
        album.require_photo("fixture_photo","fixture_event")


@pytest.mark.parametrize("kind",["document","logo","chart","generated"])
def test_non_photographic_material_never_qualifies_as_album_photo(tmp_path,kind):
    manifest,record=qualified_fixture(tmp_path)
    record["kind"]=kind
    with pytest.raises(PhotoNotReady):
        StrictPhotoAlbum(tmp_path,manifest).require_photo("fixture_photo","fixture_event")


def test_title_transcription_does_not_substitute_for_original_photo_caption(tmp_path):
    manifest,record=qualified_fixture(tmp_path)
    (tmp_path/"story.html").write_text('<img src="https://example.invalid/photo.jpg"><p>A different caption</p>')
    record["source_page_sha256"]=hashlib.sha256((tmp_path/"story.html").read_bytes()).hexdigest()
    with pytest.raises(PhotoNotReady):
        StrictPhotoAlbum(tmp_path,manifest).require_photo("fixture_photo","fixture_event")


def test_uninspected_or_unmatched_photo_remains_unusable(tmp_path):
    manifest,record=qualified_fixture(tmp_path)
    record["visual_review"]["subject_matches"]=False
    with pytest.raises(PhotoNotReady):
        StrictPhotoAlbum(tmp_path,manifest).require_photo("fixture_photo","fixture_event")
