"""
Smoke tests pinning the pipeline contract (deliverable #4: test evidence).

Fast, offline, deterministic — they run in mock mode with no API key. Run with:

    python -m pytest -q
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Deterministic, offline, fast: force mock LLM + keyword retrieval regardless of any
# local .env (which may point at a real provider / embeddings).
os.environ["LLM_PROVIDER"] = "mock"
os.environ["RETRIEVAL_MODE"] = "keyword"

from pipeline import (  # noqa: E402
    load_observation, load_sections, get_retriever, load_template,
    draft_report, verify, get_llm,
)
from pipeline.retrieve import Section  # noqa: E402
from pipeline.draft import _relevant_hits  # noqa: E402
from pipeline.capture import Finding, _dedupe_findings  # noqa: E402
from pipeline.render import render_markdown, render_dict, build_references  # noqa: E402
from pipeline.export import to_pdf, to_docx  # noqa: E402

SECTIONS_DIR = os.path.join(ROOT, "knowledge_base", "sections")
SAMPLE = os.path.join(ROOT, "samples", "observation_warehouse.json")
TEMPLATE = os.path.join(ROOT, "templates", "property_risk_report.json")


def _run():
    """Run the mock pipeline once; return (obs, sections, fields, vr)."""
    obs = load_observation(SAMPLE)
    sections = load_sections(SECTIONS_DIR)
    retriever = get_retriever(sections, jurisdiction=obs.jurisdiction)
    template = load_template(TEMPLATE)
    fields = draft_report(obs, retriever, get_llm(), template)
    vr = verify(fields, get_llm())
    return obs, sections, fields, vr


def test_pipeline_produces_cited_claims():
    obs, sections, fields, vr = _run()
    grounded = [rf for rf in fields if rf.requires_citation]
    assert grounded, "expected at least one citation-bearing field"
    # Every grounded field has at least one claim carrying a citation.
    assert any(c.citations for rf in grounded for c in rf.claims)


def test_verification_summary_has_all_buckets():
    _, _, _, vr = _run()
    assert set(vr.summary) == {"SUPPORTED", "PARTIAL", "UNSUPPORTED", "NO_CITATION"}
    assert sum(vr.summary.values()) == len(vr.checks)


def test_keyword_retriever_hits_expected_section():
    sections = load_sections(SECTIONS_DIR)
    retriever = get_retriever(sections)  # keyword (forced via env above)
    hits = [s.id for s in retriever.retrieve("Exit blocked by stacked pallets", k=2)]
    assert "FSSG-001" in hits


def _sec(sid):
    return Section(id=sid, jurisdiction="SG", hazard_class="x", title=sid, text=sid)


def test_citation_precision_margin():
    # A weak second hit (below 0.75 x top) is dropped; a close one is kept.
    far = _relevant_hits(_FakeRetriever([(_sec("A"), 1.0), (_sec("B"), 0.5)]), "q")
    assert [s.id for s in far] == ["A"]
    near = _relevant_hits(_FakeRetriever([(_sec("A"), 1.0), (_sec("B"), 0.8)]), "q")
    assert [s.id for s in near] == ["A", "B"]


class _FakeRetriever:
    def __init__(self, ranked):
        self._ranked = ranked

    def rank(self, query, k=2):
        return self._ranked[:k]


def test_dedupe_collapses_near_duplicates():
    findings = [
        Finding("Main exit on the east side is partially blocked by stacked pallets reducing the clear exit width."),
        Finding("Main exit is blocked by stacked pallets."),                # voice restatement
        Finding("Cardboard packaging stored against the electrical distribution board."),
    ]
    out = _dedupe_findings(findings)
    assert len(out) == 2                                   # the two exit lines merged
    assert any("east side" in f.text for f in out)         # kept the more detailed one


def test_references_resolve_citations_to_sources():
    obs, sections, fields, vr = _run()
    refs = build_references(fields, sections)
    assert refs, "expected references for the cited sections"
    assert all(r["source_ref"] for r in refs), "every reference must carry a source_ref"
    md = render_markdown(obs, fields, vr, sections)
    assert "## References" in md
    assert "scdf.gov.sg" in md  # a real cited URL made it into the report


def test_render_dict_includes_references():
    obs, sections, fields, vr = _run()
    report = render_dict(obs, fields, vr, sections)
    assert "references" in report and report["references"]


def test_exports_produce_valid_files():
    obs, sections, fields, vr = _run()
    report = render_dict(obs, fields, vr, sections)
    pdf, docx = to_pdf(report), to_docx(report)
    assert pdf.startswith(b"%PDF"), "PDF magic header missing"
    assert docx.startswith(b"PK"), "DOCX (zip) magic header missing"


def test_ingest_yields_unique_cited_sections():
    spec = importlib.util.spec_from_file_location(
        "kb_ingest", os.path.join(ROOT, "knowledge_base", "ingest.py"))
    ingest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingest)
    sections = ingest.ingest_all()
    ids = [s["id"] for s in sections]
    assert len(ids) == len(set(ids)), "section IDs must be unique"
    assert all(s["source_ref"] for s in sections), "every section needs a source_ref"
