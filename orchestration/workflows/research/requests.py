"""Generate a UTF-8 research handoff from the unresolved evidence questions."""

import json
from pathlib import Path

SCHEMA = Path(__file__).parents[1] / "schemas/external_research_return.schema.json"


def render_request(period: dict, questions: list[dict], sources: dict, unresolved: list[dict]) -> str:
    lines = [
        f"# 外部资料检索任务 · {period['title']}", "",
        f"工作编号 `{period['id']}`，重点窗口 {period['start_date']} 至 {period['end_date']}。"
        f"时间线用 {period['timezone']} 编排，保留原始时区与精度。",
        "",
        "请查找原始文件和能复核事实的完整正文。把行情、原始政策、具名同期观点及事后分析按材料性质标明。"
        "跨市场资料请说明实际交易时段与适用范围，独立记录发生、公告、实施、报道刊发和行情参照日期。",
        "",
        "先查原始发布机构，再用同期权威媒体补充。逐项记录 URL、发布机构、文题、原文时间、收集时间、"
        "保存原件的相对路径、关键数字口径和支持该命题的短摘录。照片另附原文件、原图注、摄影或机构、"
        "拍摄时间和报道页。日期不详写 null 或较粗精度。原件缺失时列出访问结果、尝试过的来源和缺口。",
        "",
        "不能以搜索摘要、转录、标题或已知涨跌代替原证据。有因果主张时请另列识别依据。"
        "禁止把较晚发布的材料当作此前交易时段已经知道的消息。",
        "",
    ]
    failures = {item["question_id"]: item["reason"] for item in unresolved}
    for question in questions:
        lines.extend([f"## {question['id']} · {question['question']}", ""])
        if question.get("date_range"):
            lines.extend([f"检索时间范围为 {question['date_range']}。", ""])
        for key, heading in [
            ("required_evidence", "需交回的证据"),
            ("authoritative_avenues", "优先检索渠道"),
            ("search_terms", "可直接使用的关键词"),
        ]:
            values = question.get(key, [])
            if isinstance(values, str):
                values = [values]
            if values:
                lines.extend([f"### {heading}", "", *(f"- {value}" for value in values), ""])
        leads = [sources[ref].metadata for ref in question.get("source_ids", []) if ref in sources]
        if leads:
            lines.extend(["### 已有定位", ""])
            for lead in leads:
                suffix = f" [来源]({lead['url']})" if lead["url"] else ""
                lines.append(f"- {lead['title']}（{lead['parse_status']}）。{suffix}")
            lines.append("")
        if question["id"] in failures:
            lines.extend([f"上次未解决的原因是 {failures[question['id']]}。", ""])
    lines.extend([
        "## 回交结构", "",
        f"按下列 JSON Schema 回交 `response.json`，`period_id` 写 `{period['id']}`。"
        "原件及响应 JSON 一起交回，以便在本地从文件重新复核。`unresolved` 按问题编号保留未解决项。"
        "回交文件只记录材料和可复核的证据。",
        "", "```json", json.dumps(json.loads(SCHEMA.read_text(encoding="utf-8")), ensure_ascii=False, indent=2),
        "```", "",
    ])
    return "\n".join(lines)
