"""V3 - cross-encoder reranking (open MiniLM cross-encoder on CPU) of hybrid candidates, per requirement."""
import asyncio

from rag.index.core import rerank
from rag.query import decompose, job_text
from rag.types import Hit
from rag.variants.base import RetrievalResult, Variant, merge_round_robin
from rag.variants.v2_hybrid import V2Hybrid


class V3Rerank(Variant):
    name = "v3_rerank"

    def __init__(self, corpus, **opts):
        super().__init__(corpus, **opts)
        self.hybrid = V2Hybrid(corpus, decompose=True, contextual=opts.get("contextual", False))

    def _rerank(self, query: str, cands: list[Hit], requirement: str | None) -> list[Hit]:
        docs = [self.c.by_id[h.item_id].title + "\n" + h.snippet for h in cands]
        scores = rerank(query, docs)
        out = [Hit(item_id=h.item_id, score=s, chunk_id=h.chunk_id, snippet=h.snippet, requirement=requirement,
                   signals={"ce": s, "fused": h.score}) for h, s in zip(cands, scores, strict=True)]
        return sorted(out, key=lambda h: -h.score)

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        n_cand = self.opts.get("candidates", 15)
        if self.opts.get("decompose", True):
            base = await self.hybrid.retrieve(job, k=n_cand, requirements=requirements, filters=filters)
            per = await asyncio.to_thread(lambda: {r: self._rerank(r, hits, r)[:k] for r, hits in base.by_requirement.items()})
            return RetrievalResult(hits=merge_round_robin(per, k)[:k], by_requirement=per, requirements=base.requirements)
        self.hybrid.opts["decompose"] = False
        base = await self.hybrid.retrieve(job, k=n_cand, filters=filters)
        hits = await asyncio.to_thread(self._rerank, job_text(job), base.hits, None)
        return RetrievalResult(hits=hits[:k],
                               requirements=decompose(job, requirements))
