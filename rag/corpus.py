"""Per-persona (or per-user) evidence corpus with lazily built, cached indexes."""
from __future__ import annotations

import json
import threading
from functools import lru_cache

import numpy as np

from rag.ingest import chunkers
from rag.ingest.loaders import load_persona, load_uploads
from rag.index.core import CACHE, BM25Index, DenseIndex, embeddings
from rag.types import Chunk, Item

EVIDENCE_TYPES = {"case_study", "readme", "code", "review", "cv", "upload"}


class Corpus:
    def __init__(self, persona: str, items: list[Item]):
        self.persona = persona
        self.items = items
        self.by_id = {i.id: i for i in items}
        self.evidence = [i for i in items if i.type != "past_proposal"]
        self.proposals = [i for i in items if i.type == "past_proposal"]
        self._chunks: dict[str, list[Chunk]] = {}
        self._idx: dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._contexts: dict[str, str] | None = None

    # ------------------------------------------------------------------ chunks
    def chunks(self, strategy: str, contextual: bool = False, multivector: bool = False) -> list[Chunk]:
        key = f"{strategy}|{contextual}|{multivector}"
        if key not in self._chunks:
            out: list[Chunk] = []
            for it in self.evidence:
                cs = chunkers.fixed(it) if strategy == "fixed" else chunkers.structured(it)
                if multivector:
                    for c in cs:
                        c.kind = {"case_study": "body", "readme": "readme", "code": "code"}.get(it.type, "body")
                    if it.type == "case_study":
                        first = it.text.split("## Outcome")[-1].strip()[:300]
                        cs.append(Chunk(id=f"{it.id}#summary", item_id=it.id, kind="summary",
                                        text=f"{it.title}. {first}", raw=f"{it.title}. {first}"))
                if contextual:
                    ctx = self.context_line(it)
                    for c in cs:
                        c.text = f"{ctx}\n{c.raw}"
                out += cs
            self._chunks[key] = out
        return self._chunks[key]

    def context_line(self, it: Item) -> str:
        if self._contexts is None:
            p = CACHE / "context_lines.json"
            self._contexts = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return self._contexts.get(it.id) or chunkers.header(it)

    # ----------------------------------------------------------------- indexes
    def dense(self, strategy="structured", contextual=False, multivector=False) -> tuple[DenseIndex, list[Chunk]]:
        key = f"dense|{strategy}|{contextual}|{multivector}"
        with self._lock:
            if key not in self._idx:
                cs = self.chunks(strategy, contextual, multivector)
                self._idx[key] = (DenseIndex([c.id for c in cs], [c.text for c in cs]), cs)
                embeddings().save()
        return self._idx[key]

    def bm25(self, strategy="structured", contextual=False) -> tuple[BM25Index, list[Chunk]]:
        key = f"bm25|{strategy}|{contextual}"
        with self._lock:
            if key not in self._idx:
                cs = self.chunks(strategy, contextual)
                self._idx[key] = (BM25Index([c.id for c in cs], [c.text for c in cs]), cs)
        return self._idx[key]

    def proposal_index(self) -> DenseIndex:
        with self._lock:
            if "props" not in self._idx:
                self._idx["props"] = (DenseIndex([p.id for p in self.proposals], [p.text for p in self.proposals]),)
                embeddings().save()
        return self._idx["props"][0]

    def mask(self, chunks: list[Chunk], filters: dict | None) -> np.ndarray | None:
        if not filters:
            return None
        types = set(filters.get("types") or [])
        excl = set(filters.get("exclude_items") or [])
        m = []
        for c in chunks:
            it = self.by_id[c.item_id]
            ok = (not types or it.type in types) and c.item_id not in excl
            if filters.get("since") and it.date and it.date < filters["since"]:
                ok = False
            if filters.get("industry") and it.client_industry and it.client_industry != filters["industry"]:
                ok = False
            m.append(ok)
        return np.array(m, dtype=bool)


_CORPORA: dict[str, Corpus] = {}


def get_corpus(persona: str, user_id: str | None = None) -> Corpus:
    """Persona corpus plus the user's own uploads.  Rebuilt when uploads change (incremental re-index)."""
    uploads = load_uploads(user_id, persona) if user_id else []
    key = f"{persona}|{user_id}|{len(uploads)}|{max([u.id for u in uploads], default='')}"
    if key not in _CORPORA:
        base = list(_persona_items(persona)) if persona in ("ai", "web", "data") else []
        _CORPORA[key] = Corpus(persona, base + uploads)
    return _CORPORA[key]


@lru_cache(maxsize=8)
def _persona_items(persona: str) -> tuple[Item, ...]:
    return tuple(load_persona(persona))


def get_corpus_for_dir(path: str, persona: str = "custom") -> Corpus:
    """Standalone Portfolio MCP usage: any folder with the persona layout."""
    from rag.ingest.loaders import load_dir

    key = f"dir|{path}"
    if key not in _CORPORA:
        _CORPORA[key] = Corpus(persona, load_dir(path, persona))
    return _CORPORA[key]


def invalidate(user_id: str):
    for k in [k for k in _CORPORA if f"|{user_id}|" in k]:
        _CORPORA.pop(k, None)
