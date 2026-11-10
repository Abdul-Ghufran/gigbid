"""Indexes: dense (fastembed, CPU, disk-cached embeddings), BM25 and a cross-encoder reranker."""
from __future__ import annotations

import hashlib
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.getenv("GIGBID_CACHE_DIR", str(ROOT / ".cache")))
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
_lock = threading.Lock()


@lru_cache(maxsize=2)
def _embedder(name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(name, cache_dir=str(CACHE / "fastembed"), threads=os.cpu_count())


class EmbeddingCache:
    """content-hash -> vector, persisted as .npz so evaluation reruns do not re-embed the corpus."""

    def __init__(self, model: str = EMB_MODEL):
        self.model = model
        self.path = CACHE / f"emb_{re.sub(r'[^A-Za-z0-9]', '_', model)}.npz"
        self.store: dict[str, np.ndarray] = {}
        self.dirty = False
        if self.path.exists():
            d = np.load(self.path)
            self.store = {k: d[k] for k in d.files}

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        keys = [("q:" if query else "d:") + hashlib.sha1(t.encode()).hexdigest() for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in self.store]
        if missing:
            with _lock:
                emb = _embedder(self.model)
                gen = emb.query_embed([t for _, t in missing]) if query else emb.passage_embed([t for _, t in missing])
                for (k, _), v in zip(missing, gen, strict=True):
                    self.store[k] = np.asarray(v, dtype=np.float32)
            self.dirty = True
        m = np.stack([self.store[k] for k in keys]) if keys else np.zeros((0, 384), dtype=np.float32)
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)

    def save(self):
        if self.dirty:
            CACHE.mkdir(exist_ok=True)
            np.savez(self.path, **self.store)
            self.dirty = False


_EMB: EmbeddingCache | None = None


def embeddings() -> EmbeddingCache:
    global _EMB
    if _EMB is None:
        _EMB = EmbeddingCache()
    return _EMB


class DenseIndex:
    def __init__(self, ids: list[str], texts: list[str]):
        self.ids = ids
        self.m = embeddings().embed(texts) if texts else np.zeros((0, 384), dtype=np.float32)

    def search(self, query: str, k: int, mask: np.ndarray | None = None) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        q = embeddings().embed([query], query=True)[0]
        s = self.m @ q
        if mask is not None:
            s = np.where(mask, s, -1e9)
        top = np.argsort(-s)[:k]
        return [(self.ids[i], float(s[i])) for i in top if s[i] > -1e8]


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.+#/_-]*[a-z0-9+#]|[a-z0-9]")
STOP = set("the a an and or of to in for with on at by from is are be we you our your i it this that as have has can will need".split())


def tokenize(text: str) -> list[str]:
    toks = TOKEN_RE.findall(text.lower())
    out = []
    for t in toks:
        if t in STOP:
            continue
        out.append(t)
        if any(c in t for c in ".-/_") and len(t) > 3:  # next.js -> next.js, next, js
            out += [p for p in re.split(r"[.\-/_]", t) if p and p not in STOP]
    return out


class BM25Index:
    def __init__(self, ids: list[str], texts: list[str]):
        from rank_bm25 import BM25Okapi

        self.ids = ids
        self.bm = BM25Okapi([tokenize(t) or ["_"] for t in texts]) if texts else None

    def search(self, query: str, k: int, mask: np.ndarray | None = None) -> list[tuple[str, float]]:
        if not self.bm:
            return []
        s = np.asarray(self.bm.get_scores(tokenize(query)))
        if mask is not None:
            s = np.where(mask, s, -1e9)
        top = np.argsort(-s)[:k]
        return [(self.ids[i], float(s[i])) for i in top if s[i] > 0]


def rrf(*rankings: list[tuple[str, float]], k: int = 60, weights: list[float] | None = None) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for r_i, ranking in enumerate(rankings):
        w = weights[r_i] if weights else 1.0
        for rank, (doc, _) in enumerate(ranking):
            scores[doc] = scores.get(doc, 0.0) + w / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


@lru_cache(maxsize=1)
def _cross_encoder():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(RERANK_MODEL, cache_dir=str(CACHE / "fastembed"))


def rerank(query: str, docs: list[str]) -> list[float]:
    if not docs:
        return []
    with _lock:
        return [float(x) for x in _cross_encoder().rerank(query, docs)]
