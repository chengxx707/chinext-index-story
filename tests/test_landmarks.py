"""Landmark motion links real dates/prices without manufacturing a second K."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
from PIL import Image
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from chinext_v6.landmarks import LandmarkOverlay


@pytest.fixture(scope="module")
def overlay():
    return LandmarkOverlay(ROOT,width=720)


def projected(overlay,node_id="S09",offscreen_source=False):
    link=overlay.links[node_id]
    ia=overlay.market.index_for_date(link.from_date)
    ib=overlay.market.index_for_date(link.to_date)
    low,high=sorted([link.from_close,link.to_close])
    first=ib-36 if offscreen_source else ia-8
    last=ib+15
    xp=lambda index:50+(index-first)/(last-first)*620
    yp=lambda value:780-(value-low)/(high-low)*480
    state=SimpleNamespace(current_index=ib,current_date=pd.Timestamp(link.to_date),
                          window_start=first,window_end=last)
    def orbit(value):
        start,end=pd.Timestamp("2010-01-01"),pd.Timestamp("2016-01-01")
        u=(pd.Timestamp(value)-start).days/(end-start).days
        return ((40+u*620,1020-u*60),u)
    return state,(xp,yp),orbit


def test_link_values_and_positions_are_derived_from_real_closes(overlay):
    for node_id,expected in [("S09",570.80),("S15",-54.86)]:
        state,coords,orbit=projected(overlay,node_id)
        frame=Image.new("RGBA",(720,1280))
        overlay.draw(frame,node_id,state,3.5,chart_coords=coords,orbit_point=orbit)
        result=overlay.last_diagnostics
        link=overlay.links[node_id]
        assert round(result["value_pct"],2)==expected
        assert result["projection_mode"]=="true_chart_close_path"
        assert result["revealed_observations"]==result["total_observations"]
        assert result["total_observations"]==overlay.market.index_for_date(link.to_date)-overlay.market.index_for_date(link.from_date)+1
        assert result["source_chart_position"]==[coords[0](overlay.market.index_for_date(link.from_date)),coords[1](link.from_close)]
        assert result["target_chart_position"]==[coords[0](state.current_index),coords[1](link.to_close)]
        assert result["source_position_relocated"] is False
        assert result["extra_active_rails"]==0
        assert np.asarray(frame.getchannel("A")).max()>0


def test_landmark_is_not_revealed_before_the_real_date_arrives(overlay):
    state,coords,orbit=projected(overlay)
    state.current_index-=1
    state.current_date=overlay.market.dates[state.current_index]
    frame=Image.new("RGBA",(720,1280))
    overlay.draw(frame,"S09",state,2,chart_coords=coords,orbit_point=orbit)
    assert frame.getbbox() is None
    assert not overlay.last_diagnostics["active"]


def test_offscreen_low_uses_dated_orbit_recall_without_relocating_chart_point(overlay):
    state,coords,orbit=projected(overlay,offscreen_source=True)
    frame=Image.new("RGBA",(720,1280))
    overlay.draw(frame,"S09",state,2,chart_coords=coords,orbit_point=orbit)
    result=overlay.last_diagnostics
    assert result["projection_mode"]=="dated_time_orbit_recall"
    assert result["source_chart_position"][0]<26
    assert result["source_position_relocated"] is False
    assert any(box["text"]=="2012.12.03" for box in overlay.text_boxes)
    # Explicitly dated history captions may sit below the price path. Once
    # their glyph bounds are excluded, the chart must contain no invented
    # 2012 candle/point or connecting price path for an offscreen source.
    alpha=np.asarray(frame.getchannel("A")).copy()
    for box in overlay.text_boxes:
        x0,y0,x1,y1=map(int,box["bbox"])
        alpha[y0:y1,x0:x1]=0
    assert alpha[250:846].max()==0


def test_reveal_finishes_before_camera_pushes_back_in(overlay):
    state,coords,orbit=projected(overlay)
    for elapsed in [0,.7,4.81,7.5]:
        frame=Image.new("RGBA",(720,1280))
        overlay.draw(frame,"S09",state,elapsed,chart_coords=coords,orbit_point=orbit)
        assert frame.getbbox() is None


def test_wrong_master_range_cannot_override_real_percentage(overlay):
    master=copy.deepcopy(overlay.master)
    node=next(n for n in master["nodes"] if n["id"]=="S09")
    node["metrics"][0]["value_pct"]+=.1
    with pytest.raises(ValueError,match="frozen market closes"):
        LandmarkOverlay(ROOT,width=720,master=master)


def test_history_annotation_is_not_a_large_occluding_panel(overlay):
    state,coords,orbit=projected(overlay)
    frame=Image.new("RGBA",(720,1280))
    overlay.draw(frame,"S09",state,1.0,chart_coords=coords,orbit_point=orbit)
    alpha=np.asarray(frame.getchannel("A"))
    assert alpha[50:200].max()==0
    assert alpha[600:700,500:650].max()==0
    for box in overlay.text_boxes:
        x0,y0,x1,y1=box["bbox"]
        assert 0<=x0<x1<=720 and 0<=y0<y1<=1280
