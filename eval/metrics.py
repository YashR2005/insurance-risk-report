"""
Evaluation harness (deliverable #4: test evidence).

Three metrics, all printed in one run:

  1. Retrieval hit rate  — recall@k: for each gold finding, did the retriever return
     at least one expected section in its top-k?
  2. Citation precision  — of the sections the retriever cited for gold findings, what
     fraction are in the expected set? (measures spurious citations)
  3. Unsupported-claim rate — run the full draft -> verify flow on the sample observation;
     what fraction of cited claims does the verify gate flag (UNSUPPORTED / NO_CITATION)?

Honours the same env switches as the CLI, so you can compare backends:

    python eval/metrics.py                          # keyword retrieval, mock LLM
    RETRIEVAL_MODE=embeddings python eval/metrics.py # vector retrieval
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import (  # noqa: E402
    load_sections, get_retriever, load_observation, load_template,
    draft_report, verify, get_llm, config,
)

K = 2


def _retrieval_metrics(cases, retriever):
    hits, cited_total, cited_correct = 0, 0, 0
    print("Retrieval evaluation")
    print("-" * 64)
    for case in cases:
        expected = set(case["expected_sections"])
        got = [s.id for s in retriever.retrieve(case["finding"], k=K)]
        ok = any(e in expected for e in got)
        hits += ok
        cited_total += len(got)
        cited_correct += sum(1 for g in got if g in expected)
        print(f"[{'PASS' if ok else 'FAIL'}] expected {sorted(expected)} got {got}")
    n = len(cases)
    print("-" * 64)
    hit_rate = hits / n if n else 0.0
    precision = cited_correct / cited_total if cited_total else 0.0
    return hit_rate, precision


def _unsupported_rate():
    llm = get_llm()
    obs = load_observation(os.path.join(ROOT, "samples/observation_warehouse.json"))
    sections = load_sections(os.path.join(ROOT, "knowledge_base/sections"))
    retriever = get_retriever(sections, jurisdiction=obs.jurisdiction)
    template = load_template(os.path.join(ROOT, "templates/property_risk_report.json"))
    fields = draft_report(obs, retriever, llm, template)
    vr = verify(fields, llm)
    total = len(vr.checks)
    flagged = len(vr.flags)
    return (flagged / total if total else 0.0), flagged, total


def main():
    with open(os.path.join(ROOT, "eval/dataset.json")) as f:
        cases = json.load(f)["cases"]
    sections = load_sections(os.path.join(ROOT, "knowledge_base/sections"))
    retriever = get_retriever(sections)

    hit_rate, precision = _retrieval_metrics(cases, retriever)
    unsupported, flagged, total = _unsupported_rate()

    print(f"\nMode: retrieval={config.retrieval_mode()} · llm={config.llm_provider()}")
    print(f"Retrieval hit rate (recall@{K}): {hit_rate:.0%}")
    print(f"Citation precision:              {precision:.0%}")
    print(f"Unsupported-claim rate:          {unsupported:.0%}  ({flagged}/{total} checks flagged)")


if __name__ == "__main__":
    main()
