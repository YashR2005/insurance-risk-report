"""
Stage 3 - Draft.

Builds the report by filling a fixed template, field by field. Every claim that
asserts a compliance fact carries a citation to the section ID it came from.

Key design choice: structure is decided in Python and citations are attached
deterministically; the LLM is used only to phrase claims as prose. That makes
hallucination much harder than free-form 'write me a risk report'. In the mock,
phrasing is templated; with a real provider the same claims are sent to the model
to rewrite naturally (see pipeline/llm.py).
"""

import json
from dataclasses import dataclass, field

from .capture import Observation
from .retrieve import Retriever, Section
from .llm import LLMClient


@dataclass
class Claim:
    text: str
    citations: list[str] = field(default_factory=list)  # section IDs
    evidence: dict[str, str] = field(default_factory=dict)  # id -> section text (for verify)


@dataclass
class ReportField:
    name: str
    requires_citation: bool
    claims: list[Claim] = field(default_factory=list)


def load_template(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)["fields"]


def draft_report(obs: Observation, retriever: Retriever, llm: LLMClient,
                 template: list[dict]) -> list[ReportField]:
    fields: list[ReportField] = []
    for spec in template:
        rf = ReportField(name=spec["name"], requires_citation=spec["requires_citation"])

        if not spec["requires_citation"]:
            # Narrative field, e.g. site description: no regulatory claim, no citation.
            text = _phrase(llm, spec["prompt"], _site_summary(obs))
            rf.claims.append(Claim(text=text))
        else:
            # One claim per finding, each grounded in retrieved sections.
            for f in obs.findings:
                hits = _relevant_hits(retriever, f.text)
                if not hits:
                    # No supporting standard found -> still record it, flagged downstream.
                    rf.claims.append(Claim(text=f"Observation: {f.text} (no matching standard found)."))
                    continue
                cited = [h.id for h in hits]
                evidence = {h.id: h.full for h in hits}
                claim_text = _phrase(llm, spec["prompt"], _field_content(rf.name, f.text, hits))
                rf.claims.append(Claim(text=claim_text, citations=cited, evidence=evidence))
        fields.append(rf)
    return fields


# Cite the best section, and a second only if it is nearly as strong as the top hit.
# This stops weak, off-topic sections being attached just to fill k=2.
_CITE_MARGIN = 0.75


def _relevant_hits(retriever, finding_text: str, k: int = 2) -> list[Section]:
    ranked = retriever.rank(finding_text, k=k)
    if not ranked:
        return []
    top_score = ranked[0][1]
    return [s for s, score in ranked if score >= _CITE_MARGIN * top_score]


def _field_content(field_name: str, finding_text: str, hits: list[Section]) -> str:
    """The user content sent to the LLM, framed per field so Hazards and Compliance
    read differently (the field's system prompt drives the actual assessment)."""
    standards = " | ".join(f"[{h.id}] {h.full}" for h in hits)
    if "compliance" in field_name:
        return f"Observed condition: {finding_text}\nCited requirement(s): {standards}"
    return f"Finding: {finding_text}\nRelevant standard(s): {standards}"


def _site_summary(obs: Observation) -> str:
    return (f"Site {obs.site_name}, inspected {obs.inspection_date} by {obs.inspector}, "
            f"jurisdiction {obs.jurisdiction}, {len(obs.findings)} findings recorded.")


# Guardrail prepended to every drafting instruction. Structure and citations are
# already decided in Python; the model only phrases prose. This makes hallucination
# much harder than free-form "write me a risk report". (Mock ignores the system.)
_GROUNDING = (
    "You write insurance risk reports. Rephrase ONLY the provided content into clear, "
    "neutral professional prose. Do not introduce facts, figures, standards, or "
    "citations that are not in the input. Do not output citation tags — citations are "
    "attached separately. Keep it to one or two sentences."
)


def _phrase(llm: LLMClient, instruction: str, content: str) -> str:
    # The LLM rewrites the structured content per the field instruction, under the
    # grounding guardrail. Mock returns content unchanged; real providers produce prose.
    return llm.complete(system=f"{_GROUNDING}\n\n{instruction}", user=content)
