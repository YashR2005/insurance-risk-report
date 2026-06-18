# Architecture

```
  inputs                 knowledge base
  (notes / voice / photo) (compiled, labelled sections)
        |                        |
        v                        |
  [1] CAPTURE                    |
   normalize -> Observation      |
        |                        |
        v                        v
  [2] RETRIEVE  --- section-level lookup (keyword now, embeddings later)
        |
        v
  [3] DRAFT     --- fill fixed template, one grounded claim per finding,
        |           each claim carries citations to section IDs
        v
  [4] VERIFY    --- quality gate: check every cited claim against its source;
        |           SUPPORTED / PARTIAL / UNSUPPORTED / NO_CITATION
        v
  [5] RENDER    --- report.json + report.md, with a verification summary
                    and a "flagged for human review" list
```

## Why this shape

- **Grounding over cleverness.** An insurance risk report is quasi-legal; an
  invented standard is a liability. Every claim points to a real section.
- **Structure in code, prose in the model.** The template and citations are
  decided deterministically; the LLM only phrases claims. This makes
  hallucination much harder than free-form generation.
- **One critic, not a swarm.** A single verification stage catches unsupported
  claims. A full multi-agent debate was considered and deliberately left out:
  more cost, latency, and variance for accuracy that's largely redundant with
  good retrieval + a verify gate. (Reserve heavy machinery for the high-stakes
  fields only, if at all.)

## Swap points (skeleton -> production)

| Stage    | Skeleton            | Production                          |
|----------|---------------------|-------------------------------------|
| Capture  | JSON typed notes    | + Whisper (voice), OCR/vision (photo) |
| Retrieve | keyword overlap     | embeddings + Chroma                 |
| Draft    | templated phrasing  | real LLM (Anthropic/OpenAI)         |
| Verify   | lexical overlap     | real LLM entailment                 |
| UI       | CLI                 | FastAPI + Streamlit/React, export   |
