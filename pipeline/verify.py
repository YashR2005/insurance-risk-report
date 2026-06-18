"""
Stage 4 - Verify (the quality gate).

For every claim that carries a citation, check whether the cited section actually
supports it. Anything UNSUPPORTED is surfaced, never silently published. This is
the single most important stage for an insurance document and the best thing to
show in a demo.

In the mock, 'support' is lexical overlap (pipeline/llm.py). With a real provider
it becomes a proper entailment judgement by the model.
"""

from dataclasses import dataclass, field

from .draft import ReportField
from .llm import LLMClient


@dataclass
class Check:
    field: str
    claim: str
    citation: str
    status: str   # SUPPORTED | PARTIAL | UNSUPPORTED | NO_CITATION
    reason: str


@dataclass
class VerificationResult:
    checks: list[Check] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        s = {"SUPPORTED": 0, "PARTIAL": 0, "UNSUPPORTED": 0, "NO_CITATION": 0}
        for c in self.checks:
            s[c.status] = s.get(c.status, 0) + 1
        return s

    @property
    def flags(self) -> list[Check]:
        return [c for c in self.checks if c.status in ("UNSUPPORTED", "NO_CITATION")]


def verify(fields: list[ReportField], llm: LLMClient) -> VerificationResult:
    result = VerificationResult()
    for rf in fields:
        if not rf.requires_citation:
            continue
        for claim in rf.claims:
            if not claim.citations:
                result.checks.append(Check(rf.name, claim.text, "-", "NO_CITATION",
                                            "Claim asserts a fact with no supporting source."))
                continue
            for cid in claim.citations:
                evidence = claim.evidence.get(cid, "")
                status, reason = llm.entails(claim.text, evidence)
                result.checks.append(Check(rf.name, claim.text, cid, status, reason))
    return result
