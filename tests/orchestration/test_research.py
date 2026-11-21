"""Check that local research outputs match actual sources and preserve eligibility."""

from hashlib import sha256
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image
import pytest

from orchestration.workflows.research import DOSSIER, INBOX, research_input_paths, run_research
from orchestration.workflows.research.ingest import parse_source
from orchestration.workflows.research.verify import group_events, market_sources, normalized_date, verify_event

ROOT = Path(__file__).resolve().parents[2]
BODY = "<html><head><script>fabricated number 900</script></head><body><p>2015年8月25日，公布数据为3户。</p></body></html>"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def register(path, **metadata):
    return {"id": "archive", "path": path, "title": "本地政策存档", "source_type": "primary", **metadata}


def claim(**updates):
    return {
        "event_id": "report-date", "event_date": "2015年8月25日", "date_precision": "day",
        "event_type": "fact", "title": "政策公布", "summary": "当地机构公布数据为3户",
        "key_figures": [{"label": "数据", "value": 3, "unit": "户"}], "source_ids": ["archive"],
        "evidence": [{"source_id": "archive", "excerpt": "2015年8月25日，公布数据为3户。"}],
        "review": {"body_support": True, "date_support": True, "figures_support": True, "notes": "逐项核对原文"},
        **updates,
    }


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path,body,kind", [
    ("source.html", BODY, "html"), ("source.md", "原文正文", "markdown"),
    ("source.csv", "a,b\n1,2\n", "csv"), ("source.json", '{"label":"正文"}', "json"),
])
def test_ingest_formats_and_record_exact_source_digest(tmp_path, path, body, kind):
    raw = body.encode()
    (tmp_path / path).write_bytes(raw)
    source = parse_source(tmp_path, register(path), "local_dossier")
    assert source.metadata["original_path"] == path
    assert source.metadata["file_type"] == kind
    assert source.metadata["sha256"] == sha256(raw).hexdigest()
    assert source.metadata["parse_status"] == "PARSED"
    assert "fabricated" not in source.text
    assert (tmp_path / path).read_bytes() == raw


def test_ingest_image_and_local_pdf(tmp_path):
    Image.new("RGB", (320, 180)).save(tmp_path / "image.png")
    image = parse_source(tmp_path, register("image.png"), "local_dossier")
    assert image.metadata["parse_status"] == "PARSED"
    assert image.metadata["file_type"] == "image"
    assert image.text is None
    if not shutil.which("pdftotext"):
        pytest.skip("Poppler pdftotext unavailable")
    pdf, = (ROOT / "assets/source_documents").rglob("*.pdf")
    raw = pdf.read_bytes()
    (tmp_path / "source.pdf").write_bytes(raw)
    source = parse_source(tmp_path, register("source.pdf"), "local_dossier")
    assert source.metadata["parse_status"] == "PARSED"
    assert source.metadata["file_type"] == "pdf"
    assert source.text.strip()


def test_ingest_zip_member_and_reject_unsafe_archive(tmp_path):
    good = tmp_path / "source.zip"
    with zipfile.ZipFile(good, "w") as archive:
        archive.writestr("originals/article.html", BODY.encode())
    parsed = parse_source(tmp_path, register("source.zip", archive_member="originals/article.html"), "external_response")
    assert parsed.metadata["original_path"] == "source.zip"
    assert parsed.metadata["sha256"] == sha256(BODY.encode()).hexdigest()
    assert parsed.metadata["archive_sha256"] == sha256(good.read_bytes()).hexdigest()
    assert parsed.metadata["parse_status"] == "PARSED"
    assert "数据为3户" in parsed.text
    container = parse_source(tmp_path, register("source.zip"), "external_response")
    assert container.metadata["archive_members"] == ["originals/article.html"]
    with zipfile.ZipFile(tmp_path / "unsafe.zip", "w") as archive:
        archive.writestr("../escaping.html", BODY.encode())
    unsafe = parse_source(tmp_path, register("unsafe.zip"), "external_response")
    assert unsafe.metadata["parse_status"] == "PARSE_ERROR"
    assert "Unsafe ZIP member" in unsafe.metadata["parse_notes"]
    assert not (tmp_path / "originals").exists()


def test_date_normalization_preserves_precision_and_offset():
    assert normalized_date("2015年8月", "month") == "2015-08"
    assert normalized_date("2015.8.21", "day") == "2015-08-21"
    assert normalized_date("2015-08-21/2015-08-25", "range") == "2015-08-21/2015-08-25"
    assert normalized_date("2015-08-25T18:15:34+08:00", "timestamp") == "2015-08-25T18:15:34+08:00"
    with pytest.raises(ValueError, match="timezone offset"):
        normalized_date("2015-08-25T18:15:34", "timestamp")
    with pytest.raises(ValueError):
        normalized_date("2015-08", "day")


def test_evidence_missing_figures_causality_and_production_grade(tmp_path):
    (tmp_path / "article.html").write_text(BODY, encoding="utf-8")
    sources = {"archive": parse_source(tmp_path, register("article.html"), "local_dossier")}
    result = verify_event(claim(), "local_dossier", sources, {})
    assert result["evidence_status"] == "VERIFIED"
    assert result["display_candidate"]
    assert result["event_date"] == "2015-08-25"

    mismatched = claim(evidence=[{"source_id": "archive", "excerpt": "fabricated number 900"}])
    assert verify_event(mismatched, "local_dossier", sources, {})["evidence_status"] == "DISPUTED"
    missing_amount = claim(key_figures=[{"label": "数据", "value": 13, "unit": "户"}])
    assert verify_event(missing_amount, "local_dossier", sources, {})["evidence_status"] == "PARTIALLY_VERIFIED"
    wrong_date = claim(event_date="2015-08-06")
    assert verify_event(wrong_date, "local_dossier", sources, {})["evidence_status"] == "PARTIALLY_VERIFIED"
    causal = claim(summary="公告导致创业板当日下跌")
    assert verify_event(causal, "local_dossier", sources, {})["evidence_status"] == "DISPUTED"
    qualified = claim(summary="本公告只记录数据，不能据此认定政策导致下跌")
    assert verify_event(qualified, "local_dossier", sources, {})["evidence_status"] == "VERIFIED"

    legacy = {"blocked-id": {"id": "blocked-id", "release_grade": "B", "enabled": False}}
    tied = verify_event(claim(production_event_id="blocked-id", release_grade="A"), "local_dossier", sources, {}, legacy)
    assert tied["evidence_status"] == "VERIFIED"
    assert tied["grade_provenance"]["existing_grade"] == "B"
    assert tied["grade_provenance"]["production_enabled"] is False
    assert tied["display_candidate"] is False


def test_duplicates_merge_sources_and_conflicts_are_not_candidates(tmp_path):
    (tmp_path / "article.html").write_text(BODY, encoding="utf-8")
    sources = {key: parse_source(tmp_path, register("article.html", id=key), "local_dossier")
               for key in ("archive", "copy")}
    left = verify_event(claim(), "local_dossier", sources, {})
    right = verify_event(claim(event_id="other-id", source_ids=["copy"],
                               evidence=[{"source_id": "copy", "excerpt": "公布数据为3户"}]), "local_dossier", sources, {})
    merged, = group_events([left, right])
    assert merged["source_ids"] == ["archive", "copy"]
    assert {entry["source_id"] for entry in merged["evidence"]} == {"archive", "copy"}
    assert merged["evidence_status"] == "VERIFIED"

    alternate = verify_event(claim(event_id="other", summary="当地机构公布数据为7户"), "local_dossier", sources, {})
    contested, = group_events([left, alternate])
    assert contested["evidence_status"] == "DISPUTED"
    assert contested["display_candidate"] is False
    assert len(contested["verification_notes"]["conflicting_variants"]) == 2


def test_external_return_is_revalidated_and_does_not_import_approval(tmp_path):
    seed = {
        "period": {"id": "trial", "title": "示例", "start_date": "2015-08-01", "end_date": "2015-08-31",
                   "timezone": "Asia/Shanghai"},
        "sources": [], "events": [],
        "open_questions": [{"id": "Q01", "question": "核对政策原件", "required_evidence": ["实际公告全文"],
                            "search_terms": ["2015 央行公告"], "authoritative_avenues": ["发布机构原站"]}],
    }
    write_json(tmp_path / DOSSIER, seed)
    local_doc = INBOX.parent / "archive.html"
    inbox = tmp_path / INBOX
    inbox.parent.mkdir(parents=True)
    (tmp_path / local_doc).write_text(BODY, encoding="utf-8")
    response = {
        "schema_version": 1, "period_id": "trial",
        "sources": [register(local_doc.as_posix(), publisher="机构", url=None, published_at="2015-08-25", collected_at=None)],
        "events": [claim(evidence_status="VERIFIED", display_candidate=True, release_grade="A")],
        "unresolved": [{"question_id": "Q01", "reason": "另一项来源限制", "attempted_sources": ["原站"]}],
    }
    write_json(inbox, response)
    assert local_doc.as_posix() in research_input_paths(tmp_path)
    out = tmp_path / "first-run"
    run_research(tmp_path, out)
    result, = load(out / "period_research.json")["events"]
    assert result["verification_notes"]["excerpts"][0]["status"] == "matched"
    assert result["evidence_status"] == "PARTIALLY_VERIFIED"
    assert result["grade_provenance"]["existing_grade"] is None
    assert result["display_candidate"] is False
    handoff_dir = out / "external_research_requests"
    assert "另一项来源限制" in (handoff_dir / "research_request.md").read_text(encoding="utf-8")
    assert load(handoff_dir / "research_request.json")["response_path"] == INBOX.as_posix()
    assert (tmp_path / local_doc).read_text(encoding="utf-8") == BODY

    (tmp_path / local_doc).write_text("<p>不同正文</p>", encoding="utf-8")
    second = tmp_path / "second-run"
    run_research(tmp_path, second)
    changed, = load(second / "period_research.json")["events"]
    assert changed["evidence_status"] == "DISPUTED"
    assert changed["verification_notes"]["excerpts"][0]["status"] == "not_in_body"


def test_pilot_manifest_and_known_frozen_ohlc_results(tmp_path):
    frozen = ROOT / "config/production/film_master_v1.json"
    before = sha256(frozen.read_bytes()).hexdigest()
    names = run_research(ROOT, tmp_path)
    assert sha256(frozen.read_bytes()).hexdigest() == before
    period_report = load(tmp_path / "period_research.json")
    events = {event["event_id"]: event for event in period_report["events"]}
    assert events["june-high-close"]["evidence_status"] == "VERIFIED"
    assert events["june-high-close"]["key_figures"][0]["value"] == 3982.25
    assert events["september-low-close"]["key_figures"][0]["value"] == 1797.56
    assert events["april-new-a-accounts"]["display_candidate"] is False
    assert events["august-pbc-announcement"]["announcement_at"] == "2015-08-25T18:15:34+08:00"
    assert events["august-pbc-announcement"]["implementation_date"] == "2015-08-26"
    manifest = load(tmp_path / "research_manifest.json")
    assert len(manifest["outputs"]) + 1 == len(names)
    assert manifest["network_requests"] == 0
    for entry in manifest["outputs"]:
        assert sha256((tmp_path / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_market_math_refutes_wrong_return_instead_of_trusting_editor(tmp_path):
    (tmp_path / "prices.csv").write_text(
        "date,open,close,high,low\n2015-08-24,11,10,12,9\n2015-08-25,9,9.5,10,8\n", encoding="utf-8",
    )
    source = parse_source(tmp_path, register("prices.csv", source_type="market_data"), "local_dossier")
    market = market_sources({"archive": source})
    incorrect = claim(event_type="market_observation", evidence=[], key_figures=[], market_assertions=[
        {"date": "2015-08-25", "operation": "daily_return", "expected": -8},
    ])
    result = verify_event(incorrect, "local_dossier", {"archive": source}, market)
    assert result["evidence_status"] == "DISPUTED"
    assert result["verification_notes"]["market_assertions"][0]["actual"] == -5.0
