from datetime import date
from pathlib import Path
import re
import subprocess


SOURCE_COMMIT = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
DASHBOARD_PATH = "docs/production/PROJECT-DASHBOARD.md"
HANDOFF_PATH = "editorial/2015/HANDOFF_TO_CODEX.md"
BASE_REVIEW = "editorial/2015/director/visual-tests/v1.0.2/README.md"
R1_REVIEW = "editorial/2015/director/visual-tests/v1.0.2-r1/README.md"
GITHUB = "https://github.com/chengxx707/chinext-index-story"
EXPECTED_ARTIFACTS = {
    "B01-B02": "RENDERED_AND_TECHNICALLY_VERIFIED",
    "B08-B10": "REUSED_AND_HASH_VERIFIED",
    "B13-PMI": "RENDERED_AND_TECHNICALLY_VERIFIED",
    "B16-B18": "RENDERED_AND_TECHNICALLY_VERIFIED",
}
ARTIFACT_NAMES = {
    "B01-B02": "B01–B02 片头与四月正序",
    "B08-B10": "B08–B10 政策与反弹",
    "B13-PMI": "B13 PMI 静帧",
    "B16-B18": "B16–B18 低点、T2 接力与修复结算",
}
ARTIFACT_LABELS = {
    "RENDERED_AND_TECHNICALLY_VERIFIED": "已重新编码并完成技术检查",
    "REUSED_AND_HASH_VERIFIED": "已复用首轮产物并核对 SHA-256",
    "MEDIA_GENERATED_CHECK_PENDING": "已编码，技术检查待完成",
    "TECHNICAL_ISSUES": "技术检查发现问题，见审阅回执",
    "REUSED_HASH_MISMATCH": "复用摘要未通过检查，见审阅回执",
    "PENDING": "待完成",
}
VISUAL_LABELS = {
    "REVIEWED": "已检查实际解码画面",
    "REVIEWED_WITH_OBSERVATIONS": "已检查实际解码画面，观察项见回执",
    "ISSUES_FOUND": "已检查实际解码画面，发现问题待复核",
    "NOT_PERFORMED": "实际画面待检查",
}
ASSET_LABELS = {
    "VERIFIED_ORIGINAL": "原件已核验",
    "MISSING_ORIGINAL": "原件尚未收到",
    "NOT_VERIFIED": "原件待核验",
}


def load_editorial_inputs(repo_root: Path) -> tuple[str, str]:
    def read(path):
        return subprocess.check_output(
            ["git", "show", f"{SOURCE_COMMIT}:{path}"], cwd=repo_root, encoding="utf-8"
        )

    return read(DASHBOARD_PATH), read(HANDOFF_PATH)


def _replace_line(text: str, pattern: str, replacement: str) -> str:
    revised, count = re.subn(pattern, lambda match: replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected one source dashboard marker matching {pattern!r}")
    return revised


def update_editorial(dashboard_text: str, handoff_text: str, receipt: dict) -> tuple[str, str]:
    """Refresh editorial status from actual R1 artifacts and keep user approval open.

    ``artifacts`` maps each expected block to one ARTIFACT_LABELS status. Only
    verified new encodes and independently hash-verified reuse close the media
    technical gate. The visual status describes internal decoded-frame review.
    The asset statuses describe availability and verification of original inputs.
    """
    snapshot = date.fromisoformat(receipt["date_beijing"]).isoformat()
    candidate_seconds = receipt["candidate_seconds"]
    if type(candidate_seconds) is not int or candidate_seconds != 244:
        raise ValueError("The approved R1 configuration uses a 244-second candidate budget")
    artifacts = receipt["artifacts"]
    if set(artifacts) != set(EXPECTED_ARTIFACTS):
        raise ValueError("Receipt must state the actual status of each R1 review artifact")
    for key, expected in EXPECTED_ARTIFACTS.items():
        status = artifacts[key]
        if status not in ARTIFACT_LABELS:
            raise ValueError(f"Unknown artifact status for {key}: {status!r}")
        if status in EXPECTED_ARTIFACTS.values() and status != expected:
            raise ValueError(f"Unexpected completion mode for {key}: {status!r}")
    media_technical_status = (
        "媒体技术检查通过" if artifacts == EXPECTED_ARTIFACTS else "媒体技术检查状态见回执"
    )
    visual_status = VISUAL_LABELS[receipt["visual_check_status"]]
    reference_status = ASSET_LABELS[receipt["reference_status"]]
    white_house_status = ASSET_LABELS[receipt["white_house_status"]]
    review_status = f"{media_technical_status}。{visual_status}。待 GPT 与用户审片。"
    asset_status = f"第一张最新参考图：{reference_status}。第二张白宫打底参考图：{white_house_status}。"
    budget_status = f"R1 候选预算 {candidate_seconds} 秒，完整连续片待批准。"
    prior_url = f"{GITHUB}/blob/{SOURCE_COMMIT}/{BASE_REVIEW}"
    prior_handoff_url = f"{GITHUB}/blob/{SOURCE_COMMIT}/{HANDOFF_PATH}"
    dashboard_link = f"[R1 审阅回执与下载](../../{R1_REVIEW})"
    handoff_link = "[R1 审阅回执与下载](director/visual-tests/v1.0.2-r1/README.md)"
    if not handoff_text.startswith("# HANDOFF TO CODEX｜V1.0.2 Representative Visual Tests\n"):
        raise ValueError("Expected the prior V1.0.2 representative visual test handoff")

    dashboard = _replace_line(
        dashboard_text,
        r"^\*\*状态快照：[^\n]+\*\*$",
        f"**状态快照：{snapshot}（北京时间）。V1.0.2 R1 代表块已回执。{review_status}{budget_status}**",
    )
    dashboard = _replace_line(
        dashboard,
        r"^当前阶段：\*\*DIRECTOR-V1\.0\.2-REPRESENTATIVE-VISUAL-TEST\*\*[^\n]+$",
        "当前阶段：**DIRECTOR-V1.0.2-VISUAL-R1**。导演方向为金融纪录片式（A）。"
        "2015 章节结尾继续呈现阶段低点后的反弹与修复，信息严谨程度采用方案 A（T1/T2/T3）。",
    )
    dashboard = _replace_line(
        dashboard,
        r"^\| Codex代表块视觉测试 \|[^\n]+\|$",
        "| Codex 首轮代表块视觉测试 | 已编码 3/3，首轮技术检查已完成 | "
        f"[首轮审阅回执]({prior_url}) |\n"
        f"| Codex R1 代表块视觉修订 | **{review_status}** | {dashboard_link} |\n"
        f"| R1 参考与资料图 | {asset_status} | {dashboard_link} |",
    )
    dashboard = _replace_line(
        dashboard,
        r"^\| V1\.0\.2整段连续预览 \|[^\n]+\|$",
        f"| V1.0.2 R1 整段连续预览 | 尚未批准，尚未渲染 | "
        f"{candidate_seconds} 秒为候选预算，代表块审片后再决定是否采用 |",
    )
    dashboard = _replace_line(
        dashboard,
        r"^## 三段代表块验收范围$",
        "## 首轮代表块验收范围",
    )
    dashboard = _replace_line(
        dashboard,
        r"^另需单独检查 B13[^\n]+$",
        "首轮专项检查覆盖 B13 的 09:30／09:43:10 时间轴和 B17 两项 T2 信息的进入、阅读与退场。",
    )
    labels = {key: ARTIFACT_LABELS[artifacts[key]] for key in EXPECTED_ARTIFACTS}
    if artifacts["B13-PMI"] == "RENDERED_AND_TECHNICALLY_VERIFIED":
        labels["B13-PMI"] = "已重新生成静帧并完成技术检查"
    elif artifacts["B13-PMI"] == "MEDIA_GENERATED_CHECK_PENDING":
        labels["B13-PMI"] = "已生成静帧，技术检查待完成"
    asset_rows = "\n".join(f"| {ARTIFACT_NAMES[key]} | {status} |" for key, status in labels.items())
    dashboard = _replace_line(
        dashboard,
        r"^## GPT已裁定的内容要求$",
        "## R1 代表块交付状态\n\n"
        "| 范围 | 本轮状态 |\n| --- | --- |\n"
        f"{asset_rows}\n\n"
        f"{asset_status} [{candidate_seconds} 秒候选与媒体审阅回执](../../{R1_REVIEW})\n\n"
        "## GPT已裁定的内容要求",
    )
    dashboard = _replace_line(
        dashboard,
        r"^- 当前仅授权三段代表块短片及相应关键帧测试；\*\*未授权完整240秒视频渲染\*\*。$",
        f"- R1 交付限代表块及其证据。完整 {candidate_seconds} 秒视频的渲染待审批。",
    )
    dashboard = _replace_line(
        dashboard,
        r"^- V1\.0\.2配置：[^\n]+$",
        "- 首轮 V1.0.2 配置有 18 个 Beat。编译基线为 46 个 cue，首轮代表块候选为 48 个 cue、"
        f"7,200 帧。R1 候选为 {candidate_seconds} 秒，时基为 30 fps。",
    )

    handoff = (
        "# HANDOFF TO CODEX｜V1.0.2 R1 代表块审阅\n\n"
        f"状态快照为 {snapshot}（北京时间）。{review_status}{budget_status}\n\n"
        f"{handoff_link} · [首轮代表块回执]({prior_url}) · [首轮任务书]({prior_handoff_url})\n\n"
        "## 本轮执行状态\n\n"
        "| 范围 | 本轮状态 |\n| --- | --- |\n"
        f"{asset_rows}\n\n"
        f"{asset_status} 原件证据与后续补验范围见回执。\n\n"
        "## 审阅交接\n\n"
        "1. 查阅 R1 回执中的实际产物、技术检查、画面观察及出处。\n"
        "2. 由 GPT 与用户集中评审片头镜头、B17 两条 T2 信息的阅读接力及结尾结算。\n"
        "3. 完整连续片的时长和渲染待单独审批。冻结 OHLC、V1.0.1、正式 427 秒主表和原始素材继续保留。\n"
    )
    return dashboard, handoff
