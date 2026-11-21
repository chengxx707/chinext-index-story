"""WF-01A offline source inventory, evidence research and external handoff."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import file_digest
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .ingest import MAX_FILE_BYTES, Source, local_path, parse_source
from .requests import SCHEMA, render_request
from .verify import group_events, market_sources, normalized_date, verify_event

DOSSIER = Path("orchestration/workflows/research/2015_drawdown.json")
INBOX = Path("output/research_inbox/2015/response.json")
LEGACY_REGISTRY = Path("config/event_registry.json")


def _load(path: Path) -> dict:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Research input exceeds size limit: {path.name}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Research input must be a JSON object: {path.name}")
    return data


def _below_root(root: Path, path: Path) -> Path:
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Research metadata must reside inside the repository: {path}")
    return resolved


def _original_paths(root: Path, records: object, *, inbox: Path | None = None) -> tuple[str, ...]:
    result = set()
    if not isinstance(records, list):
        return ()
    for record in records:
        if not isinstance(record, dict):
            continue
        keys = ("path",) if inbox else ("path", "archive_path", "text_path")
        for key in keys:
            relative = record.get(key)
            if not isinstance(relative, str) or not relative:
                continue
            try:
                path = local_path(root, relative)
            except (OSError, ValueError, RuntimeError):
                continue
            if inbox is None or path.is_relative_to(inbox):
                result.add(path.relative_to(root).as_posix())
    return tuple(sorted(result))


def research_input_paths(root: Path) -> tuple[str, ...]:
    """Resolve exactly the declared run inputs without parsing their contents."""
    root = root.resolve()
    inputs = {DOSSIER.as_posix(), INBOX.as_posix(), LEGACY_REGISTRY.as_posix()}
    for relative in (DOSSIER, INBOX):
        try:
            loaded = _load(_below_root(root, relative))
        except (OSError, ValueError, RuntimeError):
            continue
        inbox = (root / relative).parent.resolve() if relative == INBOX else None
        inputs.update(_original_paths(root, loaded.get("sources"), inbox=inbox))
    return tuple(sorted(inputs))


def _checked_spec(root: Path, source: dict, *, inbox: Path | None) -> dict:
    spec = dict(source)
    if inbox and spec.get("path"):
        candidate = local_path(root, spec["path"])
        if not candidate.is_relative_to(inbox):
            raise ValueError(f"External source {spec['id']} must reference a file under the response directory")
    if not inbox and spec.get("archive_path"):
        spec["text_path"] = spec["path"]
        spec["path"] = spec["archive_path"]
        spec.pop("sha256", None)
    for field in ("collected_at", "published_at"):
        if spec.get(field):
            spec[field] = normalized_date(spec[field])
    return spec


def _inventory(root: Path, local: list[dict], external: list[dict], *, inbox: Path | None) -> dict[str, Source]:
    sources = {}
    by_hash = {}
    for batch, provenance in ((local, "local_dossier"), (external, "external_response")):
        for item in batch:
            spec = _checked_spec(root, item, inbox=inbox if provenance == "external_response" else None)
            source = parse_source(root, spec, provenance)
            source_id = source.metadata["source_id"]
            if source_id in sources:
                raise ValueError(f"Duplicate source ID in research input: {source_id}")
            digest = source.metadata["sha256"]
            if digest and source.metadata["parse_status"] == "PARSED":
                if digest in by_hash:
                    source.metadata["duplicate_of"] = by_hash[digest]
                else:
                    by_hash[digest] = source_id
            sources[source_id] = source
    return sources


def _safe_cell(value: object) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def _evidence_report(period: dict, events: list[dict], sources: dict[str, Source], counts: dict, questions: list[dict]) -> str:
    lines = [f"# 区间研究证据报告 · {period['title']}", "",
             f"范围 {period['start_date']} 至 {period['end_date']}，时间基准 {period['timezone']}。",
             "此报告基于本次读取的本地文件和冻结行情复算。研究结论可供后续内容取舍，生产资格维持原注册表。",
             "", f"本轮复核 {len(events)} 个事件和 {len(sources)} 条来源记录。", ""]
    lines += [f"- {status} · {count}" for status, count in counts.items()]
    lines += ["", "## 时间与初步结论", "",
              "| 事件 | 发生或观察范围 | 公告 | 刊发 | 实施 | 行情参照 | 证据状态 | 陈述 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for event in events:
        values = [event.get(field) for field in (
            "title", "event_date", "announcement_at", "publication_at", "implementation_date",
            "market_anchor", "evidence_status", "summary",
        )]
        lines.append("| " + " | ".join(_safe_cell(value) for value in values) + " |")
    lines += ["", "## 逐项证据", ""]
    for event in events:
        notes = event["verification_notes"]
        lines += [f"### {event.get('event_id', 'invalid')} · {event.get('title', '格式无效')}", ""]
        for check in notes.get("excerpts", []):
            lines.append(f"- 摘录 `{check['source_id']}` · {check['status']} · {_safe_cell(check['excerpt'])}")
        for check in notes.get("market_assertions", []):
            if "actual" in check:
                lines.append(f"- 行情复算 {check['date']} · {check['operation']} · 实值 {check['actual']} · 预期 {check['expected']}。")
            else:
                lines.append(f"- 行情复算失败 · {check['reason']}")
        dates = [value for value, matched in notes.get("date_matches", {}).items() if not matched]
        if dates and not notes.get("market_assertions"):
            lines.append("- 尚未定位对应日期的正文 " + "、".join(dates) + "。")
        if notes.get("unavailable_source_ids"):
            lines.append("- 尚缺本地可读原件 " + "、".join(notes["unavailable_source_ids"]) + "。")
        for key in ("scope_caution", "editor_review", "rejected"):
            if notes.get(key):
                lines.append(f"- {notes[key]}")
        if notes.get("direct_causal_claim"):
            lines.append("- 发现直接因果表述，需独立证据核实。")
        if notes.get("conflict") or notes.get("conflicting_variants") or notes.get("conflicting_event_id"):
            lines.append("- 陈述存在冲突，保留争议以供复核。")
        lines.append("")
    lines += ["## 来源盘点", "", "| ID | 发布方 | 类型 | 正文状况 | 原件 |",
              "| --- | --- | --- | --- | --- |"]
    for source in sources.values():
        item = source.metadata
        fields = ("source_id", "publisher", "type", "parse_status", "original_path")
        lines.append("| " + " | ".join(_safe_cell(item[key]) for key in fields) + " |")
    lines += ["", "## 外部检索缺口", ""]
    lines += [f"- {question['id']} · {question['question']}" for question in questions]
    return "\n".join([*lines, ""])


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _file_entry(path: Path, base: Path) -> dict:
    with path.open("rb") as handle:
        return {"path": path.relative_to(base).as_posix(), "sha256": file_digest(handle, "sha256").hexdigest(),
                "bytes": path.stat().st_size}


def _local_legacy(root: Path) -> dict:
    path = root / LEGACY_REGISTRY
    if not path.is_file():
        return {}
    return {event["id"]: event for event in _load(path)["events"]}


def run_research(
    root: Path, out: Path, *, dossier: Path | None = None, external_file: Path | None = None,
) -> tuple[str, ...]:
    from orchestration.workflows.schema import validate_schema

    root = root.resolve()
    out = out.resolve()
    dossier = _below_root(root, dossier or DOSSIER)
    external = _below_root(root, external_file or INBOX)
    seed = _load(dossier)
    period = seed["period"]
    zone = ZoneInfo(period["timezone"])
    if period["start_date"] != normalized_date(period["start_date"]) or period["end_date"] != normalized_date(period["end_date"]):
        raise ValueError("Research period boundaries must be ISO dates")
    if period["start_date"] > period["end_date"]:
        raise ValueError("Research period ends before it starts")
    response = {"sources": [], "events": [], "unresolved": []}
    if external.is_file() or external_file is not None:
        response = _load(external)
        validate_schema("external_research_return", response)
        if response["period_id"] != period["id"]:
            raise ValueError("External research response names a different period")

    sources = _inventory(root, seed["sources"], response["sources"], inbox=external.parent)
    market = market_sources(sources)
    legacy = _local_legacy(root)
    events = group_events([
        *(verify_event(row, "local_dossier", sources, market, legacy) for row in seed["events"]),
        *(verify_event(row, "external_response", sources, market, legacy) for row in response["events"]),
    ])
    questions = seed.get("open_questions", [])
    counts = dict(sorted(Counter(event["evidence_status"] for event in events).items()))
    generated = datetime.now(zone).isoformat(timespec="seconds")
    report = {
        "schema_version": 1, "period": period, "generated_at": generated,
        "events": events, "evidence_counts": counts, "open_questions": questions,
        "external_unresolved": response["unresolved"], "production_registry_modified": False,
        "external_import_performed": external.is_file(),
    }
    registry = {"schema_version": 1, "sources": [source.metadata for source in sources.values()]}
    validate_schema("period_research", report)
    validate_schema("source_registry", registry)
    artifacts = {
        "period_research.json": _json(report),
        "source_registry.json": _json(registry),
        "evidence_report.md": _evidence_report(period, events, sources, counts, questions),
    }
    if questions:
        request = {
            "schema_version": 1, "period": period, "questions": questions,
            "return_schema": "return.schema.json", "prompt": "research_request.md",
            "response_path": external.relative_to(root).as_posix(),
            "unresolved_from_previous_response": response["unresolved"],
        }
        validate_schema("research_request", request)
        artifacts["external_research_requests/research_request.json"] = _json(request)
        artifacts["external_research_requests/research_request.md"] = render_request(
            period, questions, sources, response["unresolved"],
        )
        artifacts["external_research_requests/return.schema.json"] = SCHEMA.read_text(encoding="utf-8")

    paths = {dossier, root / LEGACY_REGISTRY}
    paths.update(root / name for name in _original_paths(root, seed["sources"]))
    if external.is_file():
        paths.add(external)
        paths.update(root / name for name in _original_paths(root, response["sources"], inbox=external.parent))
    inputs = [_file_entry(path, root) for path in sorted(paths) if path.is_file()]
    for name in (*artifacts, "research_manifest.json"):
        target = (out / name).resolve()
        if not target.is_relative_to(out) or target in paths or target.exists():
            raise ValueError(f"Choose an unused output directory for research artifact: {name}")
    for name, content in artifacts.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(content)

    manifest = {
        "schema_version": 1, "workflow": "WF-01A", "period_id": period["id"], "generated_at": generated,
        "inputs": inputs, "outputs": [_file_entry(out / name, out) for name in artifacts],
        "evidence_counts": counts, "source_count": len(sources), "open_question_count": len(questions),
        "scope": "local_source_verification_and_research_candidates",
        "network_requests": 0, "production_registry_modified": False,
    }
    validate_schema("research_manifest", manifest)
    with (out / "research_manifest.json").open("x", encoding="utf-8") as handle:
        handle.write(_json(manifest))
    return (*artifacts, "research_manifest.json")
