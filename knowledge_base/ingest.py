"""
Knowledge base ingestion: raw source documents -> compiled section JSON.

This is the executable form of the method described in INGESTION.md. It turns
human-curated source files in `knowledge_base/raw/` into the labelled, citable
sections the retriever consumes (`knowledge_base/sections/`).

    python knowledge_base/ingest.py            # ingest all of raw/ -> sections/
    python knowledge_base/ingest.py --check     # parse only, don't write (CI-friendly)

Source format (Markdown, one file per published document)
---------------------------------------------------------
A YAML-style front-matter block carries provenance shared by every section in the
file; each section is one `##` heading whose line is `ID | hazard_class | title`,
followed by the clause text until the next heading. Splitting on the document's own
clause headings (not arbitrary token windows) keeps citations precise.

    ---
    jurisdiction: SG
    source: SCDF Fire Code 2023, Chapter 2
    url: https://www.scdf.gov.sg/firecode
    ---

    ## FSSG-001 | egress | Means of escape and exit access
    Exit routes ... (clause text) ...

PDFs: drop a `.pdf` beside a `.meta.json` ({"jurisdiction","source","url"}) and, if
pdfplumber is installed, text is extracted and split on lines that look like clause
numbers. Markdown is preferred — it keeps the verbatim wording reviewable in git.
"""

import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "knowledge_base", "raw")
SECTIONS_DIR = os.path.join(ROOT, "knowledge_base", "sections")

_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_HEADING = re.compile(r"^##\s+(?P<id>[^|]+?)\s*\|\s*(?P<hazard>[^|]+?)\s*\|\s*(?P<title>.+?)\s*$",
                      re.MULTILINE)


def _parse_front_matter(text: str) -> tuple[dict, str]:
    m = _FRONT_MATTER.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def parse_markdown(path: str) -> list[dict]:
    """One Markdown source file -> list of section dicts."""
    with open(path) as f:
        raw = f.read()
    meta, body = _parse_front_matter(raw)
    jurisdiction = meta.get("jurisdiction", "")
    source = meta.get("source", "")
    url = meta.get("url", "")
    source_ref = f"{source} — {url}".strip(" —") if (source or url) else ""

    sections, headings = [], list(_HEADING.finditer(body))
    for i, h in enumerate(headings):
        start = h.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        block = body[start:end].strip()
        # Optional per-section override: a leading `source: ...` line cites the exact
        # clause/URL, falling back to the file-level front matter otherwise.
        ref = source_ref
        if block.lower().startswith("source:"):
            first, _, rest = block.partition("\n")
            ref = first.split(":", 1)[1].strip()
            block = rest.strip()
        clause_text = " ".join(block.split())  # collapse whitespace
        if not clause_text:
            continue
        sections.append({
            "id": h.group("id").strip(),
            "jurisdiction": jurisdiction,
            "hazard_class": h.group("hazard").strip(),
            "title": h.group("title").strip(),
            "text": clause_text,
            "source_ref": ref,
        })
    return sections


def _strip_running_headers(pages: list[str]) -> list[str]:
    """Drop lines that repeat on most pages (running headers/footers, page numbers)."""
    from collections import Counter
    line_pages = Counter()
    for pg in pages:
        for ln in {l.strip() for l in pg.splitlines() if l.strip()}:
            line_pages[ln] += 1
    threshold = max(3, int(0.5 * len(pages)))  # appears on ≥half the pages
    noise = {ln for ln, n in line_pages.items() if n >= threshold}
    cleaned = []
    for pg in pages:
        kept = [l for l in pg.splitlines()
                if l.strip() not in noise and not re.fullmatch(r"\s*\d+\s*", l)]
        cleaned.append("\n".join(kept))
    return cleaned


# A clause heading like "2.3.1" or "6.1.2a" at the start of a line.
_CLAUSE = re.compile(r"(?m)^(?P<num>\d+(?:\.\d+)+[a-z]?)\s+(?P<rest>.+)$")


def parse_pdf(path: str, min_words: int = 12) -> list[dict]:
    """Bulk-extract clause-numbered sections from an official PDF.

    Reads a sidecar `<name>.meta.json` ({jurisdiction, hazard_class, id_prefix, source, url}),
    strips running headers/footers, then splits on the document's own clause numbering. Short
    boilerplate chunks are dropped. Output is rougher than curated Markdown — spot-check it.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError("PDF ingestion needs pdfplumber: pip install pdfplumber.") from e
    meta_path = os.path.splitext(path)[0] + ".meta.json"
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    source_ref = f"{meta.get('source', '')} — {meta.get('url', '')}".strip(" —")
    prefix = meta.get("id_prefix", "SEC")

    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    text = "\n".join(_strip_running_headers(pages))

    # Find each clause heading; the body runs to the next heading.
    matches = list(_CLAUSE.finditer(text))
    best: dict[str, dict] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = " ".join(text[m.start():end].split())
        if len(body.split()) < min_words:   # skip bare headings / TOC fragments
            continue
        num = m.group("num")
        # Title = heading text with any trailing page-number / dotted-leader noise removed.
        title = re.sub(r"[\s.]*\d+(?:-\d+)?$", "", m.group("rest")).strip()[:80]
        row = {
            "id": f"{prefix}-{num}",
            "jurisdiction": meta.get("jurisdiction", ""),
            "hazard_class": meta.get("hazard_class", "general"),
            "title": title,
            "text": body,
            "source_ref": f"{source_ref} (clause {num})".strip(),
        }
        # The same clause number can appear in the TOC and the body; keep the longest body.
        if num not in best or len(body) > len(best[num]["text"]):
            best[num] = row
    return list(best.values())


def _parse(path: str) -> list[dict]:
    return parse_markdown(path) if path.endswith(".md") else parse_pdf(path)


def ingest_all() -> list[dict]:
    """All sections across every raw source (used by tests / eval)."""
    sources = sorted(glob.glob(os.path.join(RAW_DIR, "*.md")) +
                     glob.glob(os.path.join(RAW_DIR, "*.pdf")))
    sections: list[dict] = []
    for path in sources:
        sections.extend(_parse(path))
    # Fail loudly on duplicate IDs — citations must be unique across the whole corpus.
    ids = [s["id"] for s in sections]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate section IDs across raw sources: {sorted(dupes)}")
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="parse only; do not write")
    args = ap.parse_args()

    if not os.path.isdir(RAW_DIR):
        raise SystemExit(f"No raw corpus at {RAW_DIR}. Add source .md/.pdf files first.")

    sources = sorted(glob.glob(os.path.join(RAW_DIR, "*.md")) +
                     glob.glob(os.path.join(RAW_DIR, "*.pdf")))
    print(f"Ingesting {RAW_DIR} ->")
    ingest_all()  # validates uniqueness across all sources before writing anything

    total = 0
    os.makedirs(SECTIONS_DIR, exist_ok=True)
    for path in sources:
        parsed = _parse(path)
        total += len(parsed)
        out = os.path.join(SECTIONS_DIR, os.path.splitext(os.path.basename(path))[0] + ".json")
        print(f"  {os.path.basename(path)}: {len(parsed)} sections -> {os.path.basename(out)}")
        if not args.check:
            with open(out, "w") as f:
                json.dump(parsed, f, indent=2)
    print(f"Total: {total} sections.")
    if args.check:
        print("--check: parsed OK, nothing written.")


if __name__ == "__main__":
    main()
