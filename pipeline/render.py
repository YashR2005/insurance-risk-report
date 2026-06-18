"""
Stage 5 - Render.

Turns the drafted fields + verification result into the two outputs the brief
asks for: a structured `report.json` (for programs) and a human-readable
`report.md` (for the reviewer). Shared by the CLI (`run.py`) and the UI (`app.py`)
so both produce byte-identical reports.
"""

from .capture import Observation
from .draft import ReportField
from .retrieve import Section
from .verify import VerificationResult


def _cited_ids(fields: list[ReportField]) -> list[str]:
    """Every cited section ID across the report, in first-seen order."""
    seen: list[str] = []
    for rf in fields:
        for claim in rf.claims:
            for cid in claim.citations:
                if cid not in seen:
                    seen.append(cid)
    return seen


def build_references(fields: list[ReportField],
                     sections: list[Section] | None) -> list[dict]:
    """Resolve each cited ID to its source — closes the traceability loop.

    For an insurance document the citation must be followable to the published
    standard, so each reference carries the section title and its `source_ref`.
    """
    if not sections:
        return []
    by_id = {s.id: s for s in sections}
    refs = []
    for cid in _cited_ids(fields):
        s = by_id.get(cid)
        refs.append({
            "id": cid,
            "title": s.title if s else "",
            "source_ref": s.source_ref if s else "",
        })
    return refs


def render_markdown(obs: Observation, fields: list[ReportField], vr: VerificationResult,
                    sections: list[Section] | None = None) -> str:
    out = [f"# Insurance Risk Report — {obs.site_name}",
           f"_Inspected {obs.inspection_date} by {obs.inspector} · jurisdiction {obs.jurisdiction}_\n"]
    for rf in fields:
        out.append(f"## {rf.name.replace('_', ' ').title()}")
        for claim in rf.claims:
            cites = f"  _[{', '.join(claim.citations)}]_" if claim.citations else ""
            out.append(f"- {claim.text}{cites}")
        out.append("")
    s = vr.summary
    out.append("## Verification Summary")
    out.append(f"- Supported: {s['SUPPORTED']} | Partial: {s['PARTIAL']} "
               f"| Unsupported: {s['UNSUPPORTED']} | No citation: {s['NO_CITATION']}")
    if vr.flags:
        out.append("\n**Flagged for human review:**")
        for c in vr.flags:
            out.append(f"- [{c.status}] ({c.field}) {c.claim} — {c.reason}")
    refs = build_references(fields, sections)
    if refs:
        out.append("\n## References")
        for r in refs:
            tail = f" — {r['source_ref']}" if r["source_ref"] else ""
            out.append(f"- [{r['id']}] {r['title']}{tail}")
    return "\n".join(out)


def render_dict(obs: Observation, fields: list[ReportField], vr: VerificationResult,
                sections: list[Section] | None = None) -> dict:
    """The structured report payload written to report.json."""
    return {
        "meta": obs.as_dict(),
        "fields": [
            {"name": rf.name,
             "claims": [{"text": c.text, "citations": c.citations} for c in rf.claims]}
            for rf in fields
        ],
        "verification": {
            "summary": vr.summary,
            "checks": [vars(c) for c in vr.checks],
        },
        "references": build_references(fields, sections),
    }
