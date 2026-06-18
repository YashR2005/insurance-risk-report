"""
End-to-end runner for the insurance risk report prototype.

    python run.py                         # mock mode, offline, reproducible
    LLM_PROVIDER=anthropic python run.py  # real generation + verification (Claude)
    LLM_PROVIDER=openai    python run.py  # real generation + verification (ChatGPT)
    RETRIEVAL_MODE=embeddings python run.py   # vector retrieval instead of keyword

Flow:  capture -> retrieve -> draft -> verify -> render (json + markdown)
"""

import argparse
import json
import os

from pipeline import (
    load_observation, load_sections, get_retriever,
    load_template, draft_report, verify, get_llm,
    render_markdown, render_dict, config,
)

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--observation", default=os.path.join(ROOT, "samples/observation_warehouse.json"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "output"))
    ap.add_argument("--pdf", action="store_true", help="also write report.pdf")
    ap.add_argument("--docx", action="store_true", help="also write report.docx")
    args = ap.parse_args()

    llm = get_llm()
    obs = load_observation(args.observation)
    sections = load_sections(os.path.join(ROOT, "knowledge_base/sections"))
    retriever = get_retriever(sections, jurisdiction=obs.jurisdiction)
    template = load_template(os.path.join(ROOT, "templates/property_risk_report.json"))

    try:
        fields = draft_report(obs, retriever, llm, template)
        vr = verify(fields, llm)
    except Exception as exc:  # noqa: BLE001 - surface a clean message, not a trace
        from pipeline.llm import friendly_llm_error
        raise SystemExit(f"\n{friendly_llm_error(exc)}")

    os.makedirs(args.outdir, exist_ok=True)
    report = render_dict(obs, fields, vr, sections)
    with open(os.path.join(args.outdir, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    md = render_markdown(obs, fields, vr, sections)
    with open(os.path.join(args.outdir, "report.md"), "w") as f:
        f.write(md)

    written = ["report.json", "report.md"]
    if args.pdf or args.docx:
        from pipeline.export import to_pdf, to_docx
        if args.pdf:
            to_pdf(report, os.path.join(args.outdir, "report.pdf")); written.append("report.pdf")
        if args.docx:
            to_docx(report, os.path.join(args.outdir, "report.docx")); written.append("report.docx")

    print(md)
    print(f"\nProvider: {config.llm_provider()} · Retrieval: {config.retrieval_mode()}")
    print(f"Wrote {args.outdir}/: {', '.join(written)}")


if __name__ == "__main__":
    main()
