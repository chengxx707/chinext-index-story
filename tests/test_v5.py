from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from chinext_v5.model import SceneModel


def model():
    return SceneModel(ROOT/"config/v5_sample.json",ROOT/"config/events_v5.json",ROOT/"data/cyb_daily.csv")


def test_key_prices():
    m=model()
    low=m.market.index_for_date("2012-12-03")
    high=m.market.index_for_date("2015-06-03")
    assert round(m.market.close[low],2)==593.66
    assert round(m.market.close[high],2)==3982.25


def test_camera_changes_scale():
    m=model()
    far=m.state(int(9.1*m.fps)).visible_days
    near=m.state(int(15.4*m.fps)).visible_days
    assert far>200
    assert near<45


def test_time_holds_on_critical_points():
    m=model()
    a=m.state(int(4.15*m.fps)).current_date
    b=m.state(int(4.55*m.fps)).current_date
    assert a==b
    c=m.state(int(15.25*m.fps)).current_date
    d=m.state(int(15.70*m.fps)).current_date
    assert c==d
