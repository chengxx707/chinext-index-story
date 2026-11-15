#!/usr/bin/env python3
"""Export complete reviewable screen copy from the single production master.

This command reads the selected master only. It does not select more claims,
rewrite screen text, alter runtime event flags, fetch evidence, or render video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = ROOT / "config/production/film_master_v1.json"
DEFAULT_OUTPUT = ROOT / "docs/production/全片生产主表与完整屏幕文字稿_V1.md"


def timecode(seconds: float) -> str:
    whole = int(seconds)
    fraction = seconds - whole
    base = f"{whole // 60:02d}:{whole % 60:02d}"
    return base if abs(fraction) < 1e-9 else base + f"{fraction:.3f}"[1:]


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def validate_master(master: dict[str, Any]) -> dict[str, Any]:
    """Check the structure whose loss could silently omit or mis-time copy.

    Source bytes, quote support and market facts are checked by the production
    compiler; this exporter only guarantees a complete, linked document view.
    """
    video = master["video"]
    fps = _integer(video["fps"], "video.fps")
    if fps <= 0:
        raise ValueError("video.fps must be positive")
    planned_frames = _integer(video["frame_count_plan"], "video.frame_count_plan")
    if planned_frames <= 0 or abs(video["duration_seconds_estimate"] * fps - planned_frames) > 1e-6:
        raise ValueError("Video duration and frame plan disagree")
    sources = master["sources"]
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Sources must be a non-empty mapping")
    for source_id, source in sources.items():
        if source.get("id") != source_id:
            raise ValueError(f"Source key/id mismatch: {source_id}")
    phases = master["phases"]
    phase_ids = [phase["id"] for phase in phases]
    if len(phase_ids) != len(set(phase_ids)):
        raise ValueError("Phase IDs must be unique")
    nodes = master["nodes"]
    if not nodes:
        raise ValueError("The production master has no nodes")
    node_ids = [node["id"] for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Node IDs must be unique")
    frame_cursor = 0
    beat_count = 0
    used_sources: set[str] = set()
    for node in nodes:
        node_id = node["id"]
        start = _integer(node["start_frame"], f"{node_id}.start_frame")
        end = _integer(node["end_frame_exclusive"], f"{node_id}.end_frame_exclusive")
        if start != frame_cursor or end <= start:
            raise ValueError(f"Node frame coverage is not contiguous: {node_id}")
        if abs(node["start_seconds"] * fps - start) > 1e-6 or abs(node["end_seconds_exclusive"] * fps - end) > 1e-6:
            raise ValueError(f"Node seconds and frames disagree: {node_id}")
        if abs(node["duration_seconds"] * fps - (end - start)) > 1e-6:
            raise ValueError(f"Node duration disagrees: {node_id}")
        if node["role"] == "main" and node["phase_id"] not in phase_ids:
            raise ValueError(f"Main node references an unknown phase: {node_id}")
        node_sources = node["source_ids"]
        if not node_sources:
            raise ValueError(f"Node has no evidence/editorial source: {node_id}")
        for source_id in node_sources:
            if source_id not in sources:
                raise ValueError(f"Unknown source {source_id} in {node_id}")
            used_sources.add(source_id)
        if not node["beats"]:
            raise ValueError(f"Node has no screen-copy beats: {node_id}")
        beat_cursor = start
        for number, beat in enumerate(node["beats"], 1):
            label = f"{node_id}/beat{number}"
            bs = _integer(beat["start_frame"], f"{label}.start_frame")
            be = _integer(beat["end_frame_exclusive"], f"{label}.end_frame_exclusive")
            if bs != beat_cursor or be <= bs:
                raise ValueError(f"Beat frame coverage is not contiguous: {label}")
            if abs(beat["start_seconds"] * fps - bs) > 1e-6 or abs(beat["end_seconds_exclusive"] * fps - be) > 1e-6:
                raise ValueError(f"Beat seconds and frames disagree: {label}")
            if abs(beat["duration_seconds"] * fps - (be - bs)) > 1e-6:
                raise ValueError(f"Beat duration disagrees: {label}")
            stable = beat.get("planned_stable_seconds_min", 0)
            if not 0 <= stable <= beat["duration_seconds"]:
                raise ValueError(f"Invalid reading-time budget: {label}")
            lines = beat["screen_lines"]
            if not isinstance(lines, list) or not lines or any(not isinstance(line, str) or not line.strip() for line in lines):
                raise ValueError(f"Missing screen text: {label}")
            for quote in beat.get("direct_quotes", []):
                if quote["source_id"] not in node_sources or not quote["text"]:
                    raise ValueError(f"Quote source is not linked to node: {label}")
            beat_cursor = be
            beat_count += 1
        if beat_cursor != end:
            raise ValueError(f"Beats do not cover their node: {node_id}")
        frame_cursor = end
    if frame_cursor != planned_frames:
        raise ValueError("Nodes do not cover the declared film duration")
    missing_phases = set(phase_ids) - {node["phase_id"] for node in nodes}
    if missing_phases:
        raise ValueError(f"Declared phases are not covered: {sorted(missing_phases)}")
    return {"node_count": len(nodes), "main_node_count": sum(node["role"] == "main" for node in nodes),
            "beat_count": beat_count, "phase_count": len(phases), "fps": fps,
            "frame_count": planned_frames, "duration_seconds": planned_frames / fps,
            "used_source_count": len(used_sources)}


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _fenced(lines: list[str]) -> list[str]:
    # A literal source line may itself contain Markdown. Longer fences preserve
    # those characters as exact on-screen text rather than interpreting them.
    longest = max((len(run) for line in lines for run in re.findall(r"`+", line)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence + "text", *lines, fence, ""]


def _plain(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def render_markdown(master: dict[str, Any], master_path_label: str = "config/production/film_master_v1.json") -> str:
    summary = validate_master(master)
    nodes = master["nodes"]
    video = master["video"]
    phases = {phase["id"]: phase for phase in master["phases"]}
    copy = master["persistent_screen_copy"]
    source_hash = hashlib.sha256(json.dumps(master, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    doc = [f'# 创业板指数视频：全片生产主表与完整屏幕文字稿 {master["version"]}', "",
           f'> 日期：{master["updated_date"]}｜时区：{master["timezone"]}｜数据截止：{master["data_cutoff"]}。',
           '> 本文件由唯一生产主表导出；文稿与时间预算不代表新视频已渲染、实际读屏已通过或整片已审定。', "",
           '## 1．范围与初排时长', "",
           f'本版初排 **{timecode(summary["duration_seconds"])}（{summary["duration_seconds"]:g}秒）**，'
           f'目标{video["width"]}×{video["height"]}、{video["fps"]}fps、无音轨。'
           f'全稿{summary["node_count"]}个生产单元／{summary["beat_count"]}拍，正文{summary["main_node_count"]}个单元，覆盖{summary["phase_count"]}阶段。'
           '每个单元可以包含连续几拍信息，不等于每个单元都弹出一张大卡。实际段长须经排版、阅读和播放检查调整。', "",
           f'唯一输入：`{master_path_label}`。修改内容须先改主表，再重新导出，不独立维护另一套屏幕文字。', "",
           f'主表状态：`{master["status"]}`。{master["purpose"]}', "",
           '## 2．制作和证据边界', "",
           '- 真实OHLC是行情输入；事件、同期声音、文献情景按同期关系并列，不使用因果箭头。',
           '- `CSV`表示本地冻结行情；`ARxx`表示用户提供并已核读正文的本地存档，不表示本轮重新联网核验；`U:事件ID`表示用户既有研究事实，不用它伪造媒体原版页面；`EDIT`表示本片编辑文字。',
           '- 同一时刻一个主焦点。阶段名和来源是次级信息；文献重排应明确标识，企业题签与对应资料保持一致。',
           '- 片内时间与历史时间分开；倒叙、市场起点插页和相册回看按主表声明。事件日、报道日、实施日与行情观察锚点分别记录。',
           f'- {copy["policy_day_note"]}',
           f'- 阅读关卡：{master["timing_policy"]["reading_gate"]}', "",
           '## 3．常驻文字与动态字段', "",
           '以下文字不在每拍重复。动态字段按主表与行情生成；隐藏HUD的场景不显示虚构收盘。', ""]
    doc += _fenced(copy["header"] + [""] + copy["hud"] + [""] + copy["footers"])
    doc += ['活动轨依状态仅选一项：' + '、'.join(f'`{label}`' for label in copy["rail_labels"]) + '。', "",
            '## 4．全片生产主表', "",
            '时间区间为左闭右开；下表历史区间可包含测量起点，不表示行情游标倒退。', "",
            '| 单元 | 片内时间 | 历史时间／范围 | 内容与画面任务 | 来源 |',
            '|---|---|---|---|---|']
    for node in nodes:
        doc.append(f'| {_cell(node["id"])} | {timecode(node["start_seconds"])}—{timecode(node["end_seconds_exclusive"])} | '
                   f'{_cell(node["historical_period"])} | {_cell(node["title"])}；{_cell(node["visual"])} | {_cell("、".join(node["source_ids"]))} |')
    doc += ["", '### 八阶段小结', "", '| 阶段 | 片内时间 | 屏幕阶段名 | 活动轨规则 |', '|---|---|---|---|']
    for phase in master["phases"]:
        group = [node for node in nodes if node["phase_id"] == phase["id"]]
        doc.append(f'| {_cell(phase["period"])} | {timecode(group[0]["start_seconds"])}—{timecode(group[-1]["end_seconds_exclusive"])} | '
                   f'{_cell(phase["title"])} | {_cell(phase["rail_rule"])} |')
    doc += ["", '## 5．完整屏幕文字稿（逐字）', "",
            '代码块内为逐字屏幕文字，“来源小字”为实际来源行；制作说明、证据编号及本文标题不上屏。'
            '阶段小标题取主表中的阶段名，建立后退为短标签，不额外插入整屏章节卡。', ""]
    previous_phase = None
    role_titles = {"hook": "序章", "prelude": "市场起点", "ending": "时代相册与收束"}
    for node in nodes:
        phase_id = node["phase_id"]
        if phase_id != previous_phase:
            phase = phases.get(phase_id)
            title = f'{phase["period"]}｜{phase["title"]}' if phase else role_titles.get(phase_id, phase_id)
            doc += [f'### {title}', ""]
            if phase:
                doc += [f'阶段小标题逐字：`{phase["title"]}`。', ""]
            previous_phase = phase_id
        doc += [f'#### {node["id"]}｜{timecode(node["start_seconds"])}—{timecode(node["end_seconds_exclusive"])}｜{node["title"]}', "",
                f'画面：{node["visual"]}', ""]
        for number, beat in enumerate(node["beats"], 1):
            doc += [f'**第{number}拍：{timecode(beat["start_seconds"])}—{timecode(beat["end_seconds_exclusive"])}；'
                    f'{beat["duration_seconds"]:g}秒，稳定展示预算至少{beat.get("planned_stable_seconds_min", 0):g}秒。**', ""]
            doc += _fenced(beat["screen_lines"])
            if beat.get("source_line"):
                doc += [f'来源小字：`{beat["source_line"]}`。', ""]
            event = beat.get("historical_date") or "无独立事件日期"
            observation = beat.get("market_anchor") or "未绑定事件日；观察时间由编排器另行记录"
            doc += [f'生产定位（不上屏）：事件／历史日期 `{event}`；精度 `{beat.get("date_precision", "未声明")}`；'
                    f'行情锚点 `{observation}`；HUD标签 `{beat.get("hud_label", "按场景决定")}`。', ""]
            if beat.get("implementation_note"):
                doc += [f'制作注（不上屏）：{beat["implementation_note"]}', ""]
            for quote in beat.get("direct_quotes", []):
                doc += [f'直接引语核对项（不上屏）：`{quote["source_id"]}` → `{quote["text"]}`。', ""]
        doc += [f'依据：{", ".join(node["source_ids"])}。', ""]
        if node.get("production_note"):
            doc += [f'补充制作注：{node["production_note"]}', ""]
        if node.get("declared_time_jump"):
            doc += [f'显式时间跳转（不上屏）：`{_plain(node["declared_time_jump"])}`。', ""]
    doc += ['## 6．主表登记的指标口径', "",
            '下表直接导出主表登记值，不另手填数字。CSV事实复算和源材料核对由生产编译／验收执行；本工具只检查文稿结构。', "",
            '| 单元 | 指标 | 计算区间／日期 | 登记显示值 | 公式 |', '|---|---|---|---|---|']
    metric_count = 0
    for node in nodes:
        for metric in node.get("metrics", []):
            metric_count += 1
            period = (metric.get("start_date", metric.get("previous_date", "")) + " → " + metric.get("end_date", metric.get("date", ""))).strip(" →")
            value = metric.get("display_pct", metric.get("value", metric.get("value_pct", "")))
            doc.append(f'| {node["id"]} | {_cell(metric["kind"])} | {_cell(period)} | {_cell(value)} | {_cell(metric.get("formula", ""))} |')
    if not metric_count:
        doc.append('| — | 主表未登记独立指标 | — | — | — |')
    doc += ["", '## 7．来源与素材索引', "",
            '以下字段来自当前主表。参考URL仅是定位记录，不表示本轮重新访问或验证线上现状。'
            '原研究的摘录不是本轮取得的媒体原页，不将其包装为原版新闻截图。', ""]
    for source_id, source in sorted(master["sources"].items()):
        doc += [f'### {source_id}', ""]
        if source.get("title"):
            doc += [f'文献／报道：{source["title"]}', ""]
        if source.get("description"):
            doc += [source["description"], ""]
        doc += [f'来源类型：`{source["kind"]}`。', ""]
        for field, label in [("document", "原件／数据"), ("extracted_text", "提取正文"), ("sha256", "原件SHA-256"), ("verification", "核验范围")]:
            if source.get(field):
                doc += [f'{label}：`{source[field]}`。', ""]
        if source.get("reference_url"):
            doc += [f'参考URL：{source["reference_url"]}', ""]
        if source.get("date_range"):
            doc += [f'日期范围：`{_plain(source["date_range"])}`。', ""]
        if source.get("rows") is not None:
            doc += [f'记录数：{source["rows"]}。', ""]
        if source.get("date_context"):
            doc += ['时间字段（保持主表原值）：', "", '| 字段 | 值 |', '|---|---|']
            for field, value in source["date_context"].items():
                doc.append(f'| {_cell(field)} | {_cell(_plain(value))} |')
            doc += [""]
        evidence = source.get("evidence", {})
        if evidence:
            doc += ['既有研究定位：', ""]
            for field, label in [("document", "文档"), ("section", "章节"), ("sections", "章节"), ("publishers", "提供研究所列发布者"), ("registry_ids", "旧注册表ID"), ("verification", "核验范围"), ("excerpt_scope", "摘录范围")]:
                if evidence.get(field):
                    doc += [f'- {label}：`{_plain(evidence[field])}`。']
            doc += [""]
    doc += ['## 8．延期素材与当前替代', "",
            '以下是主表明确保留的资料边界；当前稿已有对应替代，不需要将“待补”标记显示给观众。', "",
            '| 项目 | 当前边界 | 本版替代 |', '|---|---|---|']
    for item in master.get("deferred", []):
        doc.append(f'| {_cell(item["item"])} | {_cell(item["reason"])} | {_cell(item["current_fallback"])} |')
    doc += ["", '## 9．导出与验收状态', "",
            f'本文件完整包含{summary["node_count"]}个生产单元、{summary["beat_count"]}拍、{summary["phase_count"]}阶段，'
            f'初排{summary["frame_count"]}帧／{timecode(summary["duration_seconds"])}。'
            '本轮导出检查仅保证ID、来源引用、逐拍文字、时长和帧覆盖完整。来源正文、行情数值、组件布局、真实视频和读屏效果仍须按路线图分别验证，不能以文稿导出成功替代成片验收。', "",
            f'主表语义SHA-256（排序键JSON）：`{source_hash}`。', "",
            '重新导出：', "", '```bash',
            'python tools/export_production_docs.py',
            'python tools/export_production_docs.py --check',
            '```', ""]
    return "\n".join(doc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Read-only: require the existing output to exactly match current deterministic export")
    args = parser.parse_args(argv)
    try:
        master = json.loads(args.master.read_text(encoding="utf-8-sig"))
        summary = validate_master(master)
        try:
            label = args.master.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            label = args.master.name
        content = render_markdown(master, master_path_label=label)
        if args.check:
            if not args.output.is_file() or args.output.read_text(encoding="utf-8") != content:
                print(json.dumps({"passed": False, "mode": "check", "reason": "Document is absent or differs from current master export", "output": str(args.output)}, ensure_ascii=False))
                return 1
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_name(args.output.name + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(args.output)
        print(json.dumps({"passed": True, "mode": "check" if args.check else "export", "output": str(args.output),
                          **summary, "render_performed": False}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Production document export failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
