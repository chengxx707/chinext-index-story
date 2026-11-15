#!/usr/bin/env python3
"""Compile the supplied V0.9 tables and documented factual corrections."""
from pathlib import Path
import hashlib
import json
import re
import csv

ROOT = Path(__file__).resolve().parents[1]


def seconds(value):
    minute, second = value.split(":")
    return 60 * int(minute) + int(second)


def build():
    source = ROOT / "docs/source/visual_script_v0.9.md"
    text = source.read_text(encoding="utf-8")
    with (ROOT / "data/cyb_daily.csv").open(encoding="utf-8-sig", newline="") as file:
        closes = {row["date"]: float(row["close"]) for row in csv.DictReader(file)}
    july_return = (closes["2026-07-31"] / closes["2026-06-30"] - 1) * 100
    scenes, chapter = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            chapter = re.sub(r"（.*?）", "", line[3:]).strip()
        cells = [x.strip() for x in line.split("|")[1:-1]]
        if not cells or not re.fullmatch(r"\d{2}:\d{2}–\d{2}:\d{2}", cells[0]):
            continue
        start, end = cells[0].split("–")
        scene = {"id": f"scene_{len(scenes)+1:03d}", "chapter": chapter,
                 "start_seconds": seconds(start), "end_seconds": seconds(end),
                 "visual": cells[1], "screen_text": cells[2],
                 "source_note": cells[3] if len(cells) > 3 else "",
                 "source_document": str(source.relative_to(ROOT))}
        if "单月 −21.52%" in scene["screen_text"]:
            scene["screen_text"] = scene["screen_text"].replace("单月 −21.52%", f"单月 {july_return:+.2f}%")
            scene["correction_id"] = "july_month_end_basis"
        if scene["start_seconds"] == 23:
            scene["visual"] = "2010节点亮起；显示基日1000标记，尚不画不存在的5月31日OHLC蜡烛。"
            scene["correction_id"] = "base_date_not_ohlc"
        if "2014.01.08" in scene["screen_text"] and "IPO 重启" in scene["screen_text"]:
            scene["screen_text"] = scene["screen_text"].replace("2014.01.08", "2014.01")
            scene["anchor_date"] = "2014-01-08"
            scene["event_date_precision"] = "month"
            scene["correction_id"] = "ipo_month_precision"
        if "摘牌 · 收盘 0.18 元" in scene["screen_text"]:
            scene["screen_text"] = scene["screen_text"].replace("摘牌 · 收盘 0.18 元", "摘牌 · 最后收盘 0.18 元")
            scene["correction_id"] = "letv_last_traded_close"
        if "创业板史上最大 IPO" in scene["screen_text"]:
            scene["screen_text"] = scene["screen_text"].replace("创业板史上最大 IPO", "当时创业板最大 IPO")
            scene["correction_id"] = "catl_record_at_listing"
        scenes.append(scene)
    scenes.append({"id": "tailnote", "chapter": "尾注", "start_seconds": 297,
                   "end_seconds": 303, "visual": "完整曲线低亮度保留后退场。",
                   "screen_text": "价格指数，不含分红\n数据截至2026.11.10\n历史数据复盘，不构成投资建议",
                   "source_document": str(source.relative_to(ROOT))})
    previous = 0
    chapters = {}
    for scene in scenes:
        if scene["start_seconds"] != previous or scene["end_seconds"] <= previous:
            raise ValueError(f"Timeline gap/overlap at {scene['id']}")
        previous = scene["end_seconds"]
        ch = chapters.setdefault(scene["chapter"], {"start_seconds": scene["start_seconds"], "end_seconds": previous})
        ch["end_seconds"] = previous
    assert previous == 303, "Expected the agreed 5:03 primary timeline"
    result = {"version": "v0.9-production-1", "duration_seconds": 303,
              "width": 1080, "height": 1920, "fps": 30, "audio": "none",
              "data_cutoff": "2026-11-10", "visual_status": "pending_representative_sample_review",
              "main_reference": "user_supplied_nasdaq100_recording",
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "corrections": [
                  {"id": "july_month_end_basis", "before": "2026年7月单月−21.52%", "after": "2026年7月单月−23.00%", "basis": "2026-07-31 close / 2026-06-30 close - 1"},
                  {"id": "base_date_not_ohlc", "basis": "CSV starts 2010-06-01; 2010-05-31 is a base marker, not a fabricated candle"},
                  {"id": "chapter_boundaries", "basis": "derive chapter times from scene rows rather than stale Markdown headings"},
                  {"id": "ipo_month_precision", "basis": "observation anchor is not proof of exact institutional event date"},
                  {"id": "letv_last_traded_close", "basis": "delisting date is not a trading day carrying a new close"},
                  {"id": "catl_record_at_listing", "basis": "record at the time, not an unqualified all-time statement"}],
              "chapters": chapters, "scenes": scenes}
    dest = ROOT / "config/full_storyboard.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{dest}: {len(scenes)} scenes including tailnote, continuous 0–{previous}s")


if __name__ == "__main__":
    build()
