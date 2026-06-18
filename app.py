"""
RiskDraft UI — capture -> draft -> edit -> export.

    streamlit run app.py

Runs offline in mock mode by default; pick a real provider / retrieval mode in the
sidebar (they set the same env vars the CLI reads, via pipeline.config). This is the
deliverable-3 demo surface: enter findings (or upload a voice note / photo), generate a
grounded report, review the verification flags, edit anything flagged, and export.
"""

import json
import os
import tempfile

import streamlit as st

from pipeline import (
    observation_from_inputs,
    load_sections, get_retriever, load_template,
    draft_report, verify, get_llm,
    render_markdown, render_dict,
)
from pipeline.llm import friendly_llm_error

ROOT = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="RiskDraft", layout="wide")
st.title("RiskDraft — Grounded Insurance Risk Reports")
st.caption("Capture → draft → verify → edit → export. Every compliance claim is cited and checked.")


# --- sidebar: engine settings (write the same env vars the CLI uses) ----------
with st.sidebar:
    st.header("Engine")
    provider = st.selectbox("LLM provider", ["mock", "anthropic", "openai"], index=0,
                            help="mock runs offline and reproducible; anthropic/openai need an API key.")
    retrieval = st.selectbox("Retrieval", ["keyword", "embeddings"], index=0,
                             help="keyword = zero-dependency; embeddings = sentence-transformers + Chroma.")
    os.environ["LLM_PROVIDER"] = provider
    os.environ["RETRIEVAL_MODE"] = retrieval
    st.markdown("---")
    st.caption("⚠️ KB sections are paraphrases of real cited standards (SCDF Fire Code "
               "2023, Fire Safety Act, UBBL 1984) — verify against the live clause before "
               "real use. Each claim carries a source_ref.")


# --- capture ------------------------------------------------------------------
st.subheader("1 · Capture")
c1, c2, c3, c4 = st.columns(4)
site = c1.text_input("Site name", "Tuas Logistics Warehouse B")
date = c2.text_input("Inspection date", "2026-06-10")
inspector = c3.text_input("Inspector", "A. Tan")
jurisdiction = c4.text_input("Jurisdiction", "SG")

notes_text = st.text_area(
    "Findings (one per line)",
    "Main exit on the east side is partially blocked by stacked pallets reducing the clear exit width.\n"
    "Only one portable fire extinguisher visible across the 800 square metre floor, located near the office.\n"
    "Cardboard packaging stored directly against the electrical distribution board.\n"
    "Socket outlets on the packing line are not protected by a 30 mA residual current device.\n"
    "Rotating drive shaft on the conveyor is exposed with no guard fitted.\n"
    "Workers retrieve stock from a mezzanine edge that has no guard-rail or fall protection.\n"
    "The forklift's lifting examination certificate on display expired fourteen months ago.\n"
    "Main switch room and standby generator are located below the surrounding flood level.",
    height=180,
)

u1, u2 = st.columns(2)
audio_file = u1.file_uploader("Voice note (optional)", type=["wav", "mp3", "m4a", "ogg"])
photo_file = u2.file_uploader("Photo (optional)", type=["png", "jpg", "jpeg"])


def _save_upload(upload) -> str:
    suffix = os.path.splitext(upload.name)[1]
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload.getbuffer())
    return path


def _run_pipeline():
    notes = [ln.strip() for ln in notes_text.splitlines() if ln.strip()]
    audio_paths, image_paths = [], []
    try:
        if audio_file is not None:
            audio_paths.append(_save_upload(audio_file))
        if photo_file is not None:
            image_paths.append(_save_upload(photo_file))
        obs = observation_from_inputs(
            site, date, inspector, jurisdiction,
            notes=notes, audio_paths=audio_paths, image_paths=image_paths,
        )
    except RuntimeError as e:
        st.error(str(e))   # optional backend (Whisper / OCR) not installed
        return

    llm = get_llm()
    sections = load_sections(os.path.join(ROOT, "knowledge_base/sections"))
    retriever = get_retriever(sections, jurisdiction=obs.jurisdiction)
    template = load_template(os.path.join(ROOT, "templates/property_risk_report.json"))
    try:
        fields = draft_report(obs, retriever, llm, template)
        vr = verify(fields, llm)
    except Exception as exc:  # noqa: BLE001 - show a clean message, not a trace
        st.error(friendly_llm_error(exc))
        return
    st.session_state.update(obs=obs, fields=fields, vr=vr, sections=sections)


if st.button("Generate report", type="primary"):
    with st.spinner("Drafting and verifying…"):
        _run_pipeline()


# --- view + edit + export -----------------------------------------------------
if "fields" in st.session_state:
    obs, fields, vr = st.session_state.obs, st.session_state.fields, st.session_state.vr
    sections = st.session_state.get("sections")

    st.subheader("2 · Report (edit any claim)")
    for rf in fields:
        st.markdown(f"**{rf.name.replace('_', ' ').title()}**")
        for i, claim in enumerate(rf.claims):
            key = f"{rf.name}-{i}"
            claim.text = st.text_area(
                f"{rf.name} · claim {i + 1}", value=claim.text, key=key, height=68,
                label_visibility="collapsed",
            )
            if claim.citations:
                st.caption(f"citations: {', '.join(claim.citations)}")

    if st.button("Re-verify edited claims"):
        st.session_state.vr = verify(fields, get_llm())
        vr = st.session_state.vr

    st.subheader("3 · Verification")
    s = vr.summary
    m = st.columns(4)
    m[0].metric("Supported", s["SUPPORTED"])
    m[1].metric("Partial", s["PARTIAL"])
    m[2].metric("Unsupported", s["UNSUPPORTED"])
    m[3].metric("No citation", s["NO_CITATION"])
    if vr.flags:
        st.warning("Flagged for human review — nothing unsupported is published silently:")
        for c in vr.flags:
            st.write(f"- **[{c.status}]** ({c.field}) {c.claim} — _{c.reason}_")
    else:
        st.success("No claims flagged.")

    st.subheader("4 · Export")
    md = render_markdown(obs, fields, vr, sections)
    report = render_dict(obs, fields, vr, sections)
    report_json = json.dumps(report, indent=2)
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button("report.md", md, file_name="report.md", mime="text/markdown")
    e2.download_button("report.json", report_json, file_name="report.json",
                       mime="application/json")
    try:
        from pipeline.export import to_pdf, to_docx
        e3.download_button("report.pdf", to_pdf(report), file_name="report.pdf",
                           mime="application/pdf")
        e4.download_button(
            "report.docx", to_docx(report), file_name="report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    except RuntimeError as e:
        e3.caption(f"PDF/DOCX unavailable: {e}")
    with st.expander("Preview Markdown"):
        st.markdown(md)
