from __future__ import annotations

from dataclasses import dataclass, field

from rag.corpus import Corpus
from rag.types import Chunk, Hit


@dataclass
class RetrievalResult:
    hits: list[Hit]  # item-level ranking (best first)
    by_requirement: dict[str, list[Hit]] = field(default_factory=dict)
    unsupported: list[str] = field(default_factory=list)  # requirements with no acceptable evidence (V8)
    requirements: list[str] = field(default_factory=list)
    debug: dict = field(default_factory=dict)

    def item_ids(self, k: int | None = None) -> list[str]:
        ids = [h.item_id for h in self.hits]
        return ids[:k] if k else ids


class Variant:
    name = "base"
    uses_llm = False

    def __init__(self, corpus: Corpus, **opts):
        self.c = corpus
        self.opts = opts

    async def retrieve(self, job: dict, k: int = 10, requirements: list[str] | None = None,
                       filters: dict | None = None) -> RetrievalResult:
        raise NotImplementedError


def to_items(ranked_chunks: list[tuple[str, float]], chunks: list[Chunk], requirement: str | None = None) -> list[Hit]:
    """Chunk ranking -> item ranking (max score per item), keeping the best snippet."""
    by_chunk = {c.id: c for c in chunks}
    best: dict[str, Hit] = {}
    for cid, s in ranked_chunks:
        c = by_chunk[cid]
        if c.item_id not in best or s > best[c.item_id].score:
            best[c.item_id] = Hit(item_id=c.item_id, score=s, chunk_id=cid, snippet=c.raw[:900], requirement=requirement)
    return sorted(best.values(), key=lambda h: -h.score)


def merge_round_robin(per_req: dict[str, list[Hit]], k: int) -> list[Hit]:
    """Interleave requirement rankings so every requirement gets its best evidence near the top."""
    out, seen, depth = [], set(), 0
    lists = [v for v in per_req.values() if v]
    while lists and len(out) < k * 3 and depth < 50:
        for lst in lists:
            if depth < len(lst) and lst[depth].item_id not in seen:
                seen.add(lst[depth].item_id)
                out.append(lst[depth])
        depth += 1
    n = len(out)
    for i, h in enumerate(out):
        h.signals["rr_score"] = 1 - i / max(1, n)
    return out
