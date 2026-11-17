"""Production contracts for the approved continuous-motion chapter."""
import json,math,sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from chinext_v6.continuous import Chapter,MonotoneClock,ContinuousRenderer
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/production/chapter_2015_v3.json'

@pytest.fixture(scope='module')
def chapter():return Chapter(ROOT,CONFIG)

def test_clock_never_reverses_even_at_highly_unequal_speed_knots(chapter):
    values=np.array([chapter.clock.at(i/30) for i in range(chapter.frame_count)])
    assert np.all(np.diff(values)>0)
    assert min(np.diff(values))*30>0
    for k in chapter.data['clock']:
        assert abs(chapter.clock.at(k['t'])-(chapter.market.index_for_date(k['date'])+k['fraction']))<1e-8

@pytest.mark.parametrize('times,positions',[([0,1],[3,3]),([0,0],[1,2]),([0,1],[2,1])])
def test_rejects_stationary_or_reversed_clocks(times,positions):
    with pytest.raises(ValueError):MonotoneClock(times,positions)

def test_hud_does_not_interpolate_daily_closes(chapter):
    for n in range(chapter.frame_count):
        s,_=chapter.state(n)
        assert s.current_index==math.floor(s.playhead_index+1e-8)
        assert s.current_close==float(chapter.market.close[s.current_index])
        assert s.current_date==chapter.market.dates[s.current_index]


def test_policy_weekend_date_is_distinct_from_market_anchor(chapter):
    e=next(e for e in chapter.events if e['id']=='cleanup');s,_=chapter.state(round(e['start']*30))
    assert e['label']=='2015.07.12 周日公布'
    assert str(s.current_date.date())=='2015-07-10'
    after,_=chapter.state(round((e['end']-.1)*30))
    assert after.playhead_index>s.playhead_index


def test_measurements_have_real_distinct_dates_and_closes(chapter):
    for e in chapter.events:
        if not e.get('measurement'):continue
        a,b=[chapter.market.index_for_date(v) for v in e['measurement']]
        assert a<b and b<=math.floor(chapter.clock.at(e['start']))
        if e['id']=='low':assert (chapter.market.dates[b]-chapter.market.dates[a]).days==104


def test_quote_must_exist_in_reviewed_body(tmp_path):
    d=json.loads(CONFIG.read_text());next(e for e in d['events'] if e['id']=='guo')['quote']='invented quote that was never said'
    p=tmp_path/'invalid.json';p.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='quote absent'):Chapter(ROOT,p)


def test_source_hash_cannot_be_bypassed(tmp_path):
    d=json.loads(CONFIG.read_text());d['sources']['GUI']['sha256']='0'*64;p=tmp_path/'invalid.json';p.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='Source integrity'):Chapter(ROOT,p)


def test_modified_configuration_is_detected_after_initialization(tmp_path):
    p=tmp_path/'chapter.json';p.write_bytes(CONFIG.read_bytes());chapter=Chapter(ROOT,p);p.write_bytes(p.read_bytes()+b'\n')
    with pytest.raises(RuntimeError,match='inputs changed'):chapter.assert_stable()


def test_camera_and_projection_are_shared_by_both_measurement_endpoints():
    renderer=ContinuousRenderer(ROOT,CONFIG,360)
    for ident,t in [('high',40),('low',125)]:
        s,c=renderer.chapter.state(round(t*30));e=next(e for e in renderer.chapter.events if e['id']==ident)
        points=[renderer.xy(renderer.m.index_for_date(day),float(renderer.m.close[renderer.m.index_for_date(day)]),s,c) for day in e['measurement']]
        assert all(35<=x<=520 and 480<=y<=800 for x,y in points)
        assert points[0][0]!=points[1][0]
        _,diag=renderer.render(round(t*30));assert diag['measurement_visible']
        assert not diag['out_of_bounds'] and not diag['text_overlaps']


def test_wide_view_filter_cannot_leak_future_candle_pixels():
    renderer=ContinuousRenderer(ROOT,CONFIG,360);n=40*30;s,_=renderer.chapter.state(n)
    before,_=renderer.render(n)
    # Paint all unobserved raster data an impossible magenta. A proper observed
    # prefix remains identical even when a wide-view sampling kernel is used.
    from PIL import ImageDraw
    end=round((s.current_index-renderer.first+1)*renderer.step*renderer.hs)
    ImageDraw.Draw(renderer.raster).rectangle((end,0,renderer.raster.width,renderer.raster.height),fill=(255,0,255,255))
    renderer.lod_index=None
    after,_=renderer.render(n)
    assert before.tobytes()==after.tobytes()
