# Demo Script (5–10 min)

The recorded demo (deliverable #3). The whole flow runs in the Streamlit UI:
`streamlit run app.py`. Record in mock mode if APIs are flaky on the day — it's
deterministic and always produces the same clean run.

## Storyline: input -> draft -> edit -> export

1. **Frame the problem (30s).** Onsite engineers spend hours writing risk
   reports by hand; mistakes are costly. This tool drafts a grounded first cut.
2. **Input (1.5 min).** In the UI **Capture** section, fill site details and paste
   findings (pre-filled with the Tuas warehouse sample). Optionally upload a voice
   note (→ Whisper transcript) and a photo (→ OCR) to show multimodal capture.
3. **Run (1 min).** Click **Generate report**. Walk the drafted fields — hazards
   identified, compliance assessment — each claim carrying a `[section ID]` citation.
4. **The trust bit (2 min).** Show the **Verification** metrics and the
   "flagged for human review" list. Make the point: nothing unsupported is
   silently published. This is the differentiator — say so.
5. **Edit + export (1.5 min).** Edit a flagged claim inline, click **Re-verify**
   to watch the status change, then **Download report.md / report.json**.
6. **Evidence (1 min).** `python eval/metrics.py` — retrieval hit rate, citation
   precision, and unsupported-claim rate on the gold set. Re-run with
   `RETRIEVAL_MODE=embeddings` to show the vector-retrieval upgrade.
7. **Honest limits (30s).** Placeholder standards must be replaced with real
   sources (the `source_ref` field is ready); human stays in the loop.
