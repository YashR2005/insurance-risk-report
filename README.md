# ⚖️ RiskDraft — A Grounded LLM Assistant for Insurance Risk Reports

RiskDraft helps an onsite engineer turn inspection observations — **typed notes, voice
notes, and photos** — into a draft **insurance risk report**, grounded in a knowledge base
of Singapore standards & regulations. Every compliance claim is **cited** to a source
clause and **checked** by a verification gate that flags anything unsupported for human
review.

Built for the Marsh Singapore (Mercer) brief: *"an AI-powered tool that assists onsite
engineers in generating industry-standard insurance risk reports… leveraging a knowledge
base of industry standards and country-specific regulations… with reliable information
retrieval, safety and accuracy validation, and a user-friendly prototype interface."*

---

## 💡 The core idea: grounded, deterministic, verified

LLMs are great at *phrasing* and terrible at *being trusted with facts*. So RiskDraft
keeps the model on a short leash:

1. **Structure is decided in Python.** The report's fields and which standard applies to
   each finding are chosen by code, not the model.
2. **Citations are attached deterministically.** Retrieval picks the source clause; the
   citation `[SECTION-ID]` is bound to the claim before the LLM ever runs.
3. **The LLM only rephrases.** It turns "finding + cited clause" into prose — it cannot
   invent facts, figures, or citations (a grounding guardrail enforces this).
4. **A verification gate is the last word.** Every cited claim is checked against its
   source; anything unsupported is **flagged for human review**, never published silently.

This makes hallucination much harder than "write me a risk report," and every line in the
output is traceable to a real, cited clause.

---

## ✨ Features

- **Multimodal capture** — typed notes, **voice notes** (Whisper transcription), and
  **photos** (OCR) become structured findings.
- **Multi-peril Singapore knowledge base** — ~39 cited sections across fire, electrical,
  workplace safety & health, flood, and machinery/lifting/pressure.
- **Grounded drafting** — one claim per finding, each carrying a `[SECTION-ID]` citation;
  the LLM only phrases, never invents.
- **Verification gate** — each claim labelled Supported / Partial / Unsupported / No-citation;
  unsupported ones are flagged.
- **References appendix** — every citation resolves to its clause + source URL.
- **Editable in the UI** — review the draft, edit any claim, and re-verify.
- **Export** — Markdown, JSON, **PDF**, and **DOCX**.
- **Switchable engine** — runs **offline in mock mode** (no key), or with **OpenAI/Anthropic**
  and **embeddings retrieval**, one env var each.
- **Evaluation harness + tests** — retrieval hit rate, citation precision, unsupported-claim
  rate, and pytest smoke tests.

---

## 🔁 How it works

```
  notes / voice / photo
          │
          ▼
   ┌──────────────┐   findings     ┌──────────────┐   top clause(s)   ┌──────────────┐
   │  1. CAPTURE  │ ─────────────▶ │ 2. RETRIEVE  │ ────────────────▶ │   3. DRAFT   │
   │ notes+OCR+ASR│                │ embeddings / │                   │ claim + [ID] │
   └──────────────┘                │   keyword    │                   │ LLM phrases  │
                                   └──────────────┘                   └──────┬───────┘
                                                                             │ claims
            report.md / .json / .pdf / .docx                                 ▼
   ┌──────────────┐   cited + checked   ┌──────────────┐   flags     ┌──────────────┐
   │  5. RENDER   │ ◀────────────────── │  + REFERENCES│ ◀────────── │  4. VERIFY   │
   │ + References │                     │   appendix   │             │ entailment / │
   └──────────────┘                     └──────────────┘             │ lexical gate │
                                                                      └──────────────┘
```

The retrieval and LLM stages are pluggable: `mock` (offline) ↔ OpenAI/Anthropic, and
`keyword` ↔ `embeddings` — selected by environment variable, same interface either way.

---

## 1. Setup

Python 3.10+. Use a virtual environment (recommended):

```bash
cd insurance-risk-report
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

Install what you need — start minimal, add the rest only when you turn it on:

```bash
# Minimal: run the CLI + UI in mock mode (offline, no key)
pip install streamlit python-dotenv

# Everything (real LLM, embeddings retrieval, voice/photo, exports, tests)
pip install -r requirements.txt
```

> The core pipeline depends only on the Python standard library; the packages above
> enable the UI and the optional real components. Voice/photo also need system binaries
> (`ffmpeg`, `tesseract`) — see §4.

---

## 2. Use the UI (recommended)

```bash
streamlit run app.py
```

Opens at <http://localhost:8501>. The page walks through the full flow:

1. **Capture** — enter site details and findings (one per line; pre-filled with a
   multi-peril example, also in `samples/sample_findings.txt`). Optionally upload a voice
   note (transcribed) or a photo (OCR'd) — a ready-made clip is at
   `samples/sample_voice_note.wav`. Pick the LLM provider and retrieval mode in the **sidebar**.
2. **Generate** — drafts each field; every compliance claim carries a `[SECTION-ID]` citation.
3. **Report (edit)** — edit any claim's wording inline.
4. **Verification** — Supported / Partial / Unsupported / No-citation counts and the items
   **flagged for human review**. Click **Re-verify** after edits.
5. **Export** — download `.md`, `.json`, `.pdf`, or `.docx` (each with a References appendix).

Mock mode is the default and fully offline — good for a reliable demo.

---

## 3. Use the CLI

```bash
python run.py                      # draft the sample observation → output/report.{md,json}
python run.py --pdf --docx         # also write output/report.pdf and report.docx
python run.py --observation path/to/your_observation.json
```

An observation file:

```json
{
  "site_name": "Tuas Logistics Warehouse B",
  "inspection_date": "2026-06-10",
  "inspector": "A. Tan",
  "jurisdiction": "SG",
  "findings": [
    { "text": "Main exit partially blocked by stacked pallets.", "area": "egress" },
    { "text": "Cardboard stored against the electrical distribution board.", "area": "storage" }
  ]
}
```

See `samples/observation_warehouse.json` for a multi-peril example.

---

## 4. ⚙️ Configuration

All configuration is read from the environment (`pipeline/config.py`). The easiest way is a
**`.env`** file in the project root — loaded automatically, and gitignored:

```bash
# .env
LLM_PROVIDER=openai                # mock (default) | openai | anthropic
OPENAI_API_KEY=sk-...              # or ANTHROPIC_API_KEY=sk-ant-...
# RETRIEVAL_MODE=embeddings        # embeddings (default) | keyword
```

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` (offline) · `openai` · `anthropic` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | key for the chosen provider |
| `OPENAI_MODEL` / `ANTHROPIC_MODEL` | `gpt-4o-mini` / `claude-sonnet-4-6` | model id |
| `RETRIEVAL_MODE` | `embeddings` | `embeddings` (Chroma; falls back to keyword if deps absent) · `keyword` |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | embedding model |
| `WHISPER_MODEL` | `base` | Whisper model for voice capture |

**Voice / photo** need system binaries: `ffmpeg` for voice, `tesseract` for photo OCR
(`brew install ffmpeg tesseract` on macOS). Without them the app shows a clear message and
typed notes still work.

---

## 5. Knowledge base — and how to extend it

A **multi-peril Singapore corpus** (~39 sections), paraphrased from real cited standards,
each with a `source_ref` (clause + URL):

| Peril | Sources |
|---|---|
| **Fire** | SCDF Fire Code 2023, Fire Safety Act 1993, Fire Safety (P&FM) Regulations 2020 |
| **Electrical** | SS 638:2018 Code of Practice for Electrical Installations (EMA) |
| **Workplace safety & health** | WSH Act 2006 + WSH (General Provisions) / Work at Heights / Confined Spaces / Noise Regs |
| **Flood / NatCat** | PUB Code of Practice on Surface Water Drainage |
| **Machinery / lifting / pressure** | WSH statutory examination requirements (MOM) |
| _Comparison_ | one Malaysia section (UBBL 1984) |

Sources live in `knowledge_base/raw/` (one Markdown file per domain). Edit/add standards and
regenerate the section JSON:

```bash
python knowledge_base/ingest.py            # raw/ → knowledge_base/sections/*.json
python knowledge_base/ingest.py --check    # parse only (fails on duplicate IDs)
```

The raw Markdown format and the PDF-ingestion path are documented in `knowledge_base/INGESTION.md`.

> ⚠️ KB sections are paraphrases for retrieval, **not gazetted text** — verify against the
> source clause before any real use. Traceability is the point of an insurance document,
> which is why every section keeps a `source_ref`.

---

## 6. 📊 Evaluation & tests

```bash
python -m pytest -q        # smoke tests: pipeline contract, retrieval, dedup, render, export
python eval/metrics.py     # retrieval hit rate, citation precision, unsupported-claim rate
RETRIEVAL_MODE=keyword python eval/metrics.py   # compare keyword vs embeddings
```

On the current gold set (`eval/dataset.json`, ~29 cases across all perils):

| Metric | embeddings | keyword |
|---|---|---|
| Retrieval hit rate (recall@2) | 100% | 97% |
| pytest smoke tests | 9 passing | 9 passing |

---

## 7. ✅ Status — what works today

| Component | Status |
|---|---|
| Capture — typed notes | ✅ |
| Capture — voice (Whisper) / photo (OCR) | ✅ (needs `ffmpeg` / `tesseract`) |
| Retrieval — keyword + embeddings (Chroma) | ✅ (embeddings default, auto-fallback) |
| Drafting — mock + OpenAI/Anthropic | ✅ (live LLM needs an API key) |
| Verification gate + human-review flags | ✅ |
| Citations + References appendix | ✅ |
| UI — capture → edit → export | ✅ (Streamlit) |
| Export — md / json / pdf / docx | ✅ |
| Knowledge base + ingestion | ✅ (~39 cited SG sections) |
| Evaluation harness + tests | ✅ |
| Docker | ✅ |

---

## 8. 🎯 What makes this different

- **Citations are not optional.** Unlike "summarise this into a report," every compliance
  claim is bound to a specific clause ID before the model runs — and resolved to its source
  in a References appendix.
- **A verification gate, not blind trust.** The tool tells you what it *couldn't* support and
  asks a human to review it — the opposite of a confident hallucination.
- **Runs offline and deterministic.** Mock mode produces the same clean report every time, so
  demos never depend on a flaky API — then the same pipeline upgrades to a real LLM with one
  env var.
- **Honest about its sources.** Standards are clearly marked as paraphrases with a `source_ref`
  to the real clause, because for an insurance document traceability *is* the product.

---

## 9. 🗺️ Roadmap

1. Verify each KB section against the **live published clause** and prefer verbatim wording.
2. Deeper editing: edit/fix a claim's **citation** in the UI and a **reviewer sign-off** (accept/override).
3. Real-LLM **entailment evaluation** with human-graded labels (beyond the lexical mock check).
4. Broaden the corpus (more perils, more jurisdictions) and tune embedding thresholds.
5. Record the 5–10 min demo (`demo/demo_script.md`).

---

## Project layout

```
app.py                      Streamlit UI (capture → draft → edit → export)
run.py                      CLI runner
pipeline/
  capture.py                observations from notes / voice / photo (+ de-dup)
  retrieve.py               keyword + embeddings (Chroma) retrieval, scored
  draft.py                  structured drafting; deterministic, precision-filtered citations
  verify.py                 verification gate (entailment / lexical check)
  render.py                 report.md / report.json + References
  export.py                 PDF / DOCX export
  llm.py                    mock / OpenAI / Anthropic providers
  config.py                 one place for every env switch
knowledge_base/             raw/ sources, sections/ (generated), ingest.py, INGESTION.md
templates/                  report templates (fields + prompts)
samples/                    example observation, findings, voice clip
eval/                       gold dataset + metrics
tests/                      pytest smoke tests
docs/architecture.md        design notes   ·   demo/demo_script.md   demo outline
```

## How it maps to the brief

| Deliverable | Where |
|---|---|
| Working prototype (runnable, instructions) | `app.py`, `run.py`, `Dockerfile`, this README |
| Knowledge base sample + ingestion method | `knowledge_base/` + `INGESTION.md` |
| Demo (input → draft → edit → export) | the UI + `demo/demo_script.md` |
| Test evidence (dataset, cases, metrics) | `eval/`, `tests/` |
