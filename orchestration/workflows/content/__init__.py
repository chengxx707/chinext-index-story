"""Generate reviewable storyboard and production candidates for the 2015 pilot."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestration.workflows.schema import validate_schema

from .mapping import map_events
from .market import MARKET_SOURCE, METRIC_RULES, Market, percent
from .pilot import PILOT_END, PILOT_START, STAGES, Beat, build_beats


OUTPUTS = ("period_storyboard.json", "period_screen_copy.md", "period_production.json", "story_audit.md")
MARKET_SOURCE_ID = "cyb-ohlc"
VISUAL_RULES = {
    "aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 30, "audio": False,
    "ohlc": "实心日K，红涨绿跌，极值连线按真实投影和实际比较口径绘制",
    "background": "黑色太空、东亚夜景地球、红色时间轨和细微光效",
    "typography": "轻量无衬线，暖金仅用于关键极值",
    "glass": "轻玻璃质感仅用于小面积信息层，文字进入留白区",
    "stage_rail": "持续一条活动轨；6月3日高点停留结束后转为回撤轨，反弹时按实际收盘回退",
    "hud": "当日收盘始终与真实交易日绑定；盘后或周末事件有独立信息日期",
}


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _market_metrics(market: Market) -> dict:
    whole = market.analytics("pilot", "2015年试点窗口", PILOT_START, PILOT_END)
    gap_observations = market.observations("2015-08-21", "2015-08-26")
    window = market.analytics("august_returns", "8月24日至26日累计收益", "2015-08-24", "2015-08-26")
    gaps = [row["date"] for row in gap_observations if row["full_down_gap"]]
    if gaps != ["2015-08-21", "2015-08-24", "2015-08-25"] or window["trading_days"] != 3:
        raise ValueError("August gap and return windows do not match the frozen pilot")
    april_volumes = [market.analytics("april_volume", "4月周度成交量", first, last)["volume"]
                     for first, last in (("2015-04-13", "2015-04-17"), ("2015-04-20", "2015-04-24"))]
    first_volume, second_volume = [record["total"] if record else None for record in april_volumes]
    return {
        **whole,
        "april_volume_week_on_week_percent": percent(second_volume, first_volume)
        if first_volume and second_volume is not None else None,
        "august_observations": gap_observations,
        "august_full_down_gap_dates": gaps,
        "august_24_26_return": {
            "start_date": window["start_date"], "end_date": window["end_date"],
            "baseline": window["return_basis"], "end_close": window["end_close"],
            "trading_days": window["trading_days"], "percent": window["period_return_percent"],
        },
        "peak_to_low_drawdown_percent": percent(whole["lowest_close"]["value"], whole["highest_close"]["value"]),
    }


def _stage_narratives(periods: list[dict], mappings: list[dict], events: list[dict], beats: list[Beat]) -> list[dict]:
    event_map = {event["event_id"]: event for event in events}
    selected = {beat.event_id for beat in beats if beat.event_id}
    result = []
    for (stage_id, title, _, _, change, takeaway), period in zip(STAGES, periods, strict=True):
        associated = [item for item in mappings if any(window["period_id"] == stage_id
                      for window in item["relevant_market_intervals"])]
        active = [item for item in associated if item["event_id"] in selected]
        research = [{"event_id": item["event_id"], "title": item["title"], "status": item["evidence_status"]}
                    for item in associated if item["further_research_needed"]]
        policy = [item["event_id"] for item in active if item["event_type"] == "fact" and
                  item["event_id"] != "may-letv-context"]
        industry = [{"event_id": item["event_id"], "status": item["evidence_status"],
                     "selected": item["event_id"] in selected} for item in associated
                    if item["event_id"] == "may-letv-context" or item["event_id"].startswith("industry-")]
        voices = [{"event_id": item["event_id"], "title": item["title"],
                   "summary": event_map[item["event_id"]]["summary"], "source_ids": item["source_ids"]}
                  for item in active if item["event_type"] == "attributed_view"]
        result.append({
            "period_id": stage_id, "title": title,
            "market_performance": {key: period[key] for key in (
                "start_close", "end_close", "period_return_percent", "max_drawdown", "daily_volatility_percent",
            )},
            "institutional_background": policy, "industry_context": industry,
            "representative_events": [item["event_id"] for item in active], "sourced_views": voices,
            "change": change, "audience_takeaway": takeaway,
            "epistemic_notes": {
                "fact": "行情指标来自真实交易日，制度节点保留来源与公开时序。",
                "interpretation": change,
                "hypothesis": research,
                "opinion": [item["event_id"] for item in voices],
            },
        })
    return result


def _shots(beats: list[Beat], market: Market, mapped: dict) -> tuple[list[dict], list[dict], list[dict]]:
    previous = PILOT_START
    cursor = 0
    story_beats, shots, units = [], [], []
    chart_components = {"close_extremum": "extreme_close", "intraday_extremum": "intraday_extreme",
                        "event": "floating_event_caption", "attributed_voice": "floating_attribution", "gap": "ohlc_gap"}
    for index, beat in enumerate(beats, start=1):
        point = market.by_date[beat.market_date]
        if beat.market_date < previous:
            raise ValueError(f"Pilot shot reverses market dates: {beat.beat_id}")
        event = mapped.get(beat.event_id)
        source_ids = event["source_ids"] if event else [MARKET_SOURCE_ID]
        story_beats.append({
            "beat_id": beat.beat_id, "period_id": beat.stage, "market_anchor": point.date,
            "market_close": point.close, "story_purpose": beat.purpose, "primary_focus": beat.focus,
            "classification": beat.kind, "event_ids": [beat.event_id] if event else [],
            "source_ids": source_ids, "source_line": beat.source_line or "冻结日线行情｜创业板指 399006",
            "screen_text": list(beat.lines), "causal_claim": False,
        })
        moving = previous != point.date
        linked = [market.by_date[day].close_point() for day in beat.link] if beat.link else []
        shot_id = f"WF2015-{index:02d}"
        shots.append({
            "shot_id": shot_id, "beat_id": beat.beat_id,
            "start_market_date": previous, "end_market_date": point.date,
            "story_purpose": beat.purpose, "primary_focus": beat.focus, "screen_text": list(beat.lines),
            "visual_component": chart_components.get(beat.focus, "daily_candles"),
            "camera_scale": beat.camera,
            "time_speed": "连续推进至观察日，入读后停留" if moving else "停留在同一真实交易日",
            "event_animation": "留白区短淡入，共用日期线，关键日K保持可见" if event else "none",
            "keypoint_animation": "按真实几何依次点亮双端点并显示区间" if linked else (
                "只在真实极值位置短暂暖金强调" if beat.focus == "intraday_extremum" else "none"),
            "keypoint_close_anchors": linked,
            "timeline_behavior": "冻结在上一交易日，事件日期独立显示" if event and
                event["market_anchor_kind"] == "explicit_previous_trading_day" else (
                    "冻结在当日收盘，日期线显示盘后公告时间" if event and event["after_close"] else
                    "日期和收盘来自同一真实K线"),
            "stage_rail_behavior": "single_rise_until_peak_hold" if beat.stage == "P01" else "single_drawdown",
            "reading_duration": beat.reading,
            "transition_in": "从前一镜实际投影延续，缓动重构相机位置" if index > 1 else "由黑场渐入",
            "transition_out": "保留阶段语境与红色时间轨，传递摄影机投影" if index < len(beats) else "区间同框停留后淡出",
        })
        duration_frames = (beat.reading + (2 if moving else 1)) * VISUAL_RULES["fps"]
        units.append({
            "unit_id": f"UNIT-{index:02d}", "period_id": beat.stage, "shot_id": shot_id,
            "beat_id": beat.beat_id, "source_ids": source_ids,
            "start_frame": cursor, "end_frame_exclusive": cursor + duration_frames,
            "duration_frames": duration_frames, "reading_duration": beat.reading,
            "start_market_date": previous, "end_market_date": point.date,
            "readiness": "candidate_pending_human_review",
        })
        previous = point.date
        cursor += duration_frames
    return story_beats, shots, units


def _copy(beats: list[dict], shots: list[dict]) -> str:
    lines = ["# 创业板指数 · 2015 年试点屏幕文字候选", "", "无声竖屏草案。秒数为完整可读的计划停留。", ""]
    for beat, shot in zip(beats, shots, strict=True):
        lines.extend([f"## {shot['shot_id']} · {beat['market_anchor']}", ""])
        lines.extend(f"> {text}  " for text in beat["screen_text"])
        lines.extend(["", f"署名行：{beat['source_line']}", "",
                      f"稳定阅读 {shot['reading_duration']} 秒。{beat['story_purpose']}", ""])
    return "\n".join(lines)


def _audit(metrics: dict, narrative: list[dict], mappings: list[dict], beats: list[dict], production: dict) -> str:
    lines = ["# 2015 年候选故事审计", "", "## 行情复核", ""]
    for key, label in (("highest_close", "最高收盘"), ("intraday_high", "盘中最高"),
                       ("lowest_close", "最低收盘"), ("intraday_low", "盘中最低")):
        point = metrics[key]
        lines.append(f"- {label}为 {point['date']} 的 {point['value']:,.2f}。")
    gaps = "、".join(metrics["august_full_down_gap_dates"])
    change = metrics["august_24_26_return"]
    lines.extend([
        f"- 三个连续交易日完整向下缺口为 {gaps}。8 月 26 日低开且与前一日区间重叠。",
        f"- 8 月 24—26 日三个交易日累计收益为 {change['percent']:.2f}%，以前一交易日 {change['baseline']['date']} 收盘为基准。",
        f"- 6 月最高收盘至 9 月最低收盘的变化为 {metrics['peak_to_low_drawdown_percent']:.2f}%。",
        "- 成交量使用冻结 CSV 的 volume 原始列。波动率为日收益样本标准差。",
        "", "## 分阶段观看目标", "",
    ])
    for period in narrative:
        lines.append(f"- {period['title']}。{period['change']}{period['audience_takeaway']}")
    selected = {event_id for beat in beats for event_id in beat["event_ids"]}
    lines.extend(["", "## 证据与候选使用", "", "事件和行情按同期时序并列，市场走势的成因需要独立证据。", "",
                  "| 事件 | 证据状态 | 用途 | 交易日锚点 |", "| --- | --- | --- | --- |"])
    for item in mappings:
        usage = "屏幕候选" if item["event_id"] in selected else (
            "复算行情，按观察窗口选取" if item["event_type"] == "market_observation" else "仅供研究或语境核对")
        title = item["title"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {title} | {item['evidence_status']} | {usage} | {item['market_anchor'] or '待定'} |")
    lines.extend(["", "## 评议与放行", "",
                  f"本候选含 {len(beats)} 个节拍、{production['planned_frame_count']} 个计划帧。",
                  "待确认内容取舍、实际画面布局、手机阅读节奏和连续镜头衔接。当前状态为候选待审。", ""])
    return "\n".join(lines)


def run_content(root: Path, research_dir: Path, out: Path) -> tuple[str, ...]:
    """Read verified research and emit deterministic artifacts in the candidate path."""
    root, out = root.resolve(), out.resolve()
    if out.is_relative_to(root) and (not out.is_relative_to(root / "output") or out == root / "output"):
        raise ValueError("Candidate output must be in a dedicated directory beneath output/")
    evidence_path = research_dir / "period_research.json"
    registry_path = research_dir / "source_registry.json"
    market_path = root / MARKET_SOURCE
    master_path = root / "config/production/film_master_v1.json"
    evidence = _read_json(evidence_path)
    source_registry = _read_json(registry_path)["sources"]
    sources = {source["source_id"]: source for source in source_registry}
    if len(sources) != len(source_registry):
        raise ValueError("Source registry contains duplicate IDs")
    master = _read_json(master_path)
    market_sha = _sha(market_path)
    if master["sources"]["CSV"]["sha256"] != market_sha:
        raise ValueError("OHLC input does not match the frozen master, review input provenance")
    if sources.get(MARKET_SOURCE_ID, {}).get("sha256") != market_sha:
        raise ValueError("Research market source does not match the frozen OHLC input")
    market = Market(market_path)
    events = evidence["events"]
    periods = [market.analytics(stage_id, title, start, end) for stage_id, title, start, end, _, _ in STAGES]
    mappings = map_events(market, periods, events, sources)
    mapped = {item["event_id"]: item for item in mappings}
    metrics = _market_metrics(market)
    beats = build_beats(market, mappings, events, metrics)
    story_beats, shots, units = _shots(beats, market, mapped)
    for name, items in (("market_period", periods), ("story_beat", story_beats), ("shot", shots), ("production_unit", units)):
        for item in items:
            validate_schema(name, item)
    if any(source_id not in sources for beat in story_beats for source_id in beat["source_ids"]):
        raise ValueError("A selected beat has no source registry record")
    narrative = _stage_narratives(periods, mappings, events, beats)
    provenance = {"market_source": MARKET_SOURCE, "market_sha256": market_sha,
                  "frozen_master_sha256": _sha(master_path), "period_research_sha256": _sha(evidence_path),
                  "source_registry_sha256": _sha(registry_path)}
    storyboard = {
        "schema_version": 1, "period": {"start_date": PILOT_START, "end_date": PILOT_END},
        "status": "candidate_pending_human_review", "provenance": provenance,
        "market_metric_rules": METRIC_RULES, "pilot_market_metrics": metrics, "market_periods": periods,
        "event_market_mapping": mappings, "stage_narratives": narrative,
        "story_beats": story_beats, "shots": shots, "source_registry": source_registry,
    }
    production = {
        "schema_version": 1, "period": storyboard["period"], "status": "candidate_pending_human_review",
        "provenance": provenance, "visual_rules": VISUAL_RULES, "production_units": units, "shots": shots,
        "planned_frame_count": units[-1]["end_frame_exclusive"], "render_performed": False,
        "manual_review": ["事实及文本取舍", "布局及关键价位无遮挡", "实际连续播放与阅读时长"],
    }
    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).is_symlink() for name in OUTPUTS):
        raise ValueError("Candidate output files cannot be symlinks")
    contents = {
        "period_storyboard.json": json.dumps(storyboard, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "period_production.json": json.dumps(production, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "period_screen_copy.md": _copy(story_beats, shots),
        "story_audit.md": _audit(metrics, narrative, mappings, story_beats, production),
    }
    with TemporaryDirectory(dir=out, prefix=".draft-") as temporary:
        staging = Path(temporary)
        for name, content in contents.items():
            (staging / name).write_text(content, encoding="utf-8")
        for name in OUTPUTS:
            (staging / name).replace(out / name)
    return OUTPUTS
