"""
Stage 2 - Retrieve.

Given a piece of text (a finding or a report field need), return the most
relevant *sections* from the compiled knowledge base.

The skeleton uses simple keyword overlap so it runs with zero dependencies.
This is the Karpathy 'compiled wiki' idea in miniature: the KB is pre-split
into clean, labelled sections rather than queried as raw documents.

>>> SWAP FOR PRODUCTION: replace _score() with embedding similarity
    (e.g. sentence-transformers -> Chroma). The interface stays identical:
    retrieve(query, k) -> list[Section]. Only the scoring changes.
"""

import json
import os
import re
from dataclasses import dataclass

_STOP = set("the a an of to in on for and or is are with at by from as be this that "
            "it its no not only near against per shall should must may all any".split())


@dataclass
class Section:
    id: str
    jurisdiction: str
    hazard_class: str
    title: str
    text: str
    source_ref: str = ""   # traceability to the real published standard (the point for insurance)

    @property
    def full(self) -> str:
        return f"{self.title}. {self.text}"


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2}


def load_sections(sections_dir: str) -> list[Section]:
    out = []
    for fname in sorted(os.listdir(sections_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(sections_dir, fname)) as f:
                for row in json.load(f):
                    out.append(Section(**row))
    return out


class Retriever:
    def __init__(self, sections: list[Section], jurisdiction: str | None = None):
        self.sections = [s for s in sections
                         if jurisdiction is None or s.jurisdiction == jurisdiction]

    def _score(self, query_tokens: set[str], section: Section) -> float:
        st = _tokens(section.full)
        if not st or not query_tokens:
            return 0.0
        return len(query_tokens & st) / len(query_tokens)  # recall-style overlap

    def rank(self, query: str, k: int = 2, min_score: float = 0.12) -> list[tuple[Section, float]]:
        """Top-k sections with their scores, highest first (scores let the caller
        decide how many citations are actually relevant — see draft.py)."""
        q = _tokens(query)
        scored = [(s, self._score(q, s)) for s in self.sections]
        scored = [(s, sc) for s, sc in scored if sc >= min_score]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    def retrieve(self, query: str, k: int = 2, min_score: float = 0.12) -> list[Section]:
        return [s for s, _ in self.rank(query, k=k, min_score=min_score)]


# --------------------------------------------------------------------------
# Production retrieval: embeddings + Chroma. Same interface as the keyword
# Retriever (retrieve(query, k, min_score) -> list[Section]); only the scoring
# changes. Heavy imports are lazy so the skeleton runs with zero dependencies.
# --------------------------------------------------------------------------
class EmbeddingRetriever:
    """Vector retrieval over the same compiled sections.

    Sections are embedded once and held in an in-memory Chroma collection. The
    query is embedded and matched by cosine similarity; `min_score` is applied
    on similarity (1 - distance) to mirror the keyword retriever's threshold.
    """

    def __init__(self, sections: list[Section], jurisdiction: str | None = None,
                 model_name: str | None = None):
        from . import config
        from sentence_transformers import SentenceTransformer
        import chromadb

        self.sections = [s for s in sections
                         if jurisdiction is None or s.jurisdiction == jurisdiction]
        self._by_id = {s.id: s for s in self.sections}
        self.model = SentenceTransformer(model_name or config.get("EMBED_MODEL"))

        client = chromadb.Client()
        # Unique collection name avoids clashes when several retrievers exist.
        # cosine space (not Chroma's default L2) so 1 - distance is a real similarity.
        self.col = client.create_collection(
            name=f"sections_{id(self)}", metadata={"hnsw:space": "cosine"})
        if self.sections:
            embeddings = self.model.encode(
                [s.full for s in self.sections], normalize_embeddings=True).tolist()
            self.col.add(
                ids=[s.id for s in self.sections],
                embeddings=embeddings,
                documents=[s.full for s in self.sections],
            )

    def rank(self, query: str, k: int = 2, min_score: float = 0.20) -> list[tuple[Section, float]]:
        if not self.sections:
            return []
        q_emb = self.model.encode([query], normalize_embeddings=True).tolist()
        res = self.col.query(query_embeddings=q_emb, n_results=min(k, len(self.sections)))
        ids = res["ids"][0]
        dists = res.get("distances", [[0.0] * len(ids)])[0]
        out = []
        for sid, dist in zip(ids, dists):
            sim = 1.0 - dist  # cosine space -> similarity in [-1, 1]
            if sim >= min_score and sid in self._by_id:
                out.append((self._by_id[sid], sim))
        return out

    def retrieve(self, query: str, k: int = 2, min_score: float = 0.20) -> list[Section]:
        return [s for s, _ in self.rank(query, k=k, min_score=min_score)]


_FALLBACK_WARNED = False


def get_retriever(sections: list[Section], jurisdiction: str | None = None):
    """Factory: pick the retrieval backend from RETRIEVAL_MODE (config default: embeddings).

    Embeddings give better matching on short findings; if the optional deps aren't
    installed we fall back to keyword so the zero-install path still runs.
    """
    from . import config
    if config.retrieval_mode() == "keyword":
        return Retriever(sections, jurisdiction=jurisdiction)
    try:
        return EmbeddingRetriever(sections, jurisdiction=jurisdiction)
    except ImportError:
        global _FALLBACK_WARNED
        if not _FALLBACK_WARNED:
            print("[retrieve] embeddings deps not installed (sentence-transformers, chromadb); "
                  "falling back to keyword retrieval. `pip install -r requirements.txt` to enable.")
            _FALLBACK_WARNED = True
        return Retriever(sections, jurisdiction=jurisdiction)
