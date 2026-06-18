# Knowledge Base — Ingestion & Indexing

This documents how the standards/regulations corpus is turned into something the
pipeline can query. (Deliverable #2: knowledge base sample + ingestion method.)

## Approach

The corpus is **compiled into clean, labelled sections** rather than queried as
raw PDFs. Each section is a self-contained unit with an ID, jurisdiction, hazard
class, title, and text. This makes citations precise (you cite a section ID, not
a fuzzy chunk) and is the practical core of the "compile then query" idea.

## Section schema

```json
{
  "id": "FSSG-003",
  "jurisdiction": "SG",
  "hazard_class": "storage",
  "title": "Storage of combustible materials and housekeeping",
  "text": "Combustible materials such as cardboard ...",
  "source_ref": "SCDF Fire Code, Ch. X clause Y (edition)"
}
```

`source_ref` records exactly where the section came from. It is optional in code
(defaults to empty) but **mandatory in practice** — for an insurance document the
whole value is traceability to the published standard.

## Pipeline (raw -> sections)

This is implemented in `knowledge_base/ingest.py`:

```bash
python knowledge_base/ingest.py            # raw/ -> sections/fire_safety.json
python knowledge_base/ingest.py --check    # parse only (CI: fails on duplicate IDs)
```

1. **Collect** source documents into `knowledge_base/raw/`. Preferred format is one
   curated **Markdown** file per published document: YAML front matter carries the
   shared provenance (`jurisdiction`, `source`, `url`); each `## ID | hazard_class | title`
   heading is one section, with an optional `source:` line citing the exact clause/URL.
   PDFs are also supported (drop a `.pdf` + `.meta.json`, needs `pdfplumber`).
2. **Parse** front matter + headings (PDFs: extract text with pdfplumber).
3. **Split** on the document's own clause headings — not arbitrary token windows.
4. **Label** each with jurisdiction + hazard class (from the heading / front matter).
5. **Store** as JSON in `knowledge_base/sections/` — **one file per raw source**
   (`sg_electrical.md` → `sg_electrical.json`). `load_sections()` reads every `*.json` in the
   directory, so domains compose automatically. Ingestion fails loudly on duplicate IDs across sources.
6. **Index** — two backends ship in `pipeline/retrieve.py`, chosen by `RETRIEVAL_MODE`:
   - `keyword` (default): token-overlap, zero dependencies.
   - `embeddings`: each section's `title + text` is embedded with sentence-transformers
     and stored in an in-memory Chroma collection; queries are matched by cosine similarity.
   Both expose the same `retrieve(query, k)` interface (`get_retriever()` factory) — only
   the scoring changes, so the rest of the pipeline and the eval harness are unaffected.

## ⚠️ Important

The sections in `sections/` are **paraphrases of real, cited standards** across a
multi-peril Singapore corpus — SCDF Fire Code 2023, Fire Safety Act 1993 and P&FM
Regulations 2020 (fire); SS 638:2018 (electrical); WSH Act 2006 and its General
Provisions / Work at Heights Regulations (workplace safety); PUB Code of Practice on
Surface Water Drainage (flood); WSH statutory examination requirements (lifting /
pressure / machinery); plus Malaysia's UBBL 1984 (comparison) — with a precise
`source_ref` (clause + URL) on each section so a reviewer can trace every claim to its
origin. The raw source files live in `knowledge_base/raw/`.

They are **paraphrases for retrieval, not gazetted text.** Before any real use,
verify each section against the live published clause (codes are revised — e.g. SCDF
moves to 3-year Fire Certificate validity from 1 Apr 2026) and prefer verbatim wording.
For an insurance document, traceability to the real source is the whole point.
