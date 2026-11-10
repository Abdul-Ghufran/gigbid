"""V2 - hybrid BM25 + dense with reciprocal rank fusion.

`decompose=False` (the V2 row) fuses on the whole post; `decompose=True` runs the fusion per requirement
(used by V3/V4/V8 and the ablation)."""
from rag.index.core import rrf
from rag.query import decompose, job_text
from rag.variants.base import RetrievalResult, Variant, merge_round_robin, to_items


class V2Hybrid(Variant):
    name = "v2_hybrid"

    def _fused(self, q: str, mask_d, mask_b, n=30, contextual=False):
        d_idx, chunks = self.c.dense("structured", contextual)
        b_idx, _ = self.c.bm25("structured", contextual)
        fused = rrf(d_idx.search(q, n, mask_d), b_idx.search(q, n, mask_b))
        return fused, chunks

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        contextual = self.opts.get("contextual", False)
        _, chunks = self.c.dense("structured", contextual)
        mask = self.c.mask(chunks, filters)
        if not self.opts.get("decompose", False):
            fused, chunks = self._fused(job_text(job), mask, mask, contextual=contextual)
            return RetrievalResult(hits=to_items(fused, chunks)[:k])
        reqs = decompose(job, requirements)
        per = {}
        for r in reqs:
            fused, chunks = self._fused(r, mask, mask, contextual=contextual)
            per[r] = to_items(fused, chunks, r)[:k]
        return RetrievalResult(hits=merge_round_robin(per, k)[:k], by_requirement=per, requirements=reqs)
