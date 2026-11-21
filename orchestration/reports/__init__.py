"""Summarize observed workflow records and provide links to their evidence."""

from collections import Counter
from typing import Iterable

from orchestration.state import Status, Store


def build_report(store: Store, current: Iterable[dict] | None = None) -> dict:
    history = store.records()
    if current is None:
        latest = {}
        for record in sorted(history, key=lambda row: row["history"][-1]["at"]):
            latest[record["task_id"]] = record
        selected = latest.values()
    else:
        current_rows = {(row["task_id"], row["input_hash"]): row for row in current}
        selected = [
            record for record in history
            if (row := current_rows.get((record["task_id"], record["input_hash"]))) is not None
            and (record["status"] != Status.PASSED or row["status"] == Status.PASSED)
        ]
    records = sorted(selected, key=lambda record: (record["lane"], record["task_id"]))
    return {
        "scope": "current_input_records" if current is not None else "latest_observed_records",
        "lanes": {lane: dict(Counter(record["status"] for record in records if record["lane"] == lane))
                  for lane in ("A", "B")},
        "records": records,
        "historical_record_count": len(history) - len(records),
    }


def to_markdown(report: dict) -> str:
    lines = ["# 生产调度进度", "", "统计来自已持久化的任务状态与尝试记录。", ""]
    if not report["records"]:
        lines.append("当前范围没有执行记录。")
    else:
        labels = {"A": "完整视频生产", "B": "视觉开发"}
        for lane, counts in report["lanes"].items():
            summary = "，".join(f"{status} {count}" for status, count in sorted(counts.items())) or "无记录"
            lines.append(f"- {lane} 线 · {labels[lane]}　{summary}")
        lines.extend(["", "| 任务 | 状态 | 尝试次数 | 说明 |", "|---|---|---:|---|"])
        for record in report["records"]:
            reason = (record.get("reason") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{record['task_id']}` | {record['status']} | {len(record['attempts'])} | {reason} |")
        lines.extend(["", "日志、产物摘要和历史状态可在同一状态目录下按任务 ID 与输入摘要查阅。"])
    lines.extend(["", f"另有 {report['historical_record_count']} 份历史记录。"])
    return "\n".join(lines) + "\n"
