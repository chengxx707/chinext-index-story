from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.ending import EndingDrawer, load_facts


def test_ending_calculates_statistics_from_market_and_snapshot():
    facts = load_facts(ROOT)
    assert facts.trading_days == 3992
    assert round(facts.base_return, 2) == 149.44
    assert round(facts.max_drawdown, 2) == -69.74
    assert len(facts.industry_counts) == 39
    assert [r["name"] for r in facts.leaders] == ["宁德时代", "中际旭创", "东方财富"]
    assert round(facts.leaders[0]["market_cap"], 2) == 11565.81


def test_ending_component_text_stays_inside_target_frame():
    drawer = EndingDrawer(ROOT, 720)
    for t in [0, .5, 2.8, 4.99, 5, 7, 9.99, 10, 12, 15]:
        assert not drawer.diagnostics(t)["out_of_bounds"]
        assert drawer.render(t).size == (720, 1280)
    assert len(drawer.grid_text_boxes) == len(drawer.facts.constituents)
    for box in drawer.grid_text_boxes:
        x0, y0, x1, y1 = box["bbox"]
        cx0, cy0, cx1, cy1 = box["cell_bbox"]
        assert cx0 <= x0 <= x1 <= cx1
        assert cy0 <= y0 <= y1 <= cy1
