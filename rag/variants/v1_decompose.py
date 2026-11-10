"""V1 - requirement decomposition: one dense retrieval per extracted requirement, merged round-robin."""
from rag.query import decompose
from rag.variants.base import RetrievalResult, Variant, merge_round_robin, to_items


class V1Decompose(Variant):
    name = "v1_decompose"

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        idx, chunks = self.c.dense("structured")
        mask = self.c.mask(chunks, filters)
        reqs = decompose(job, requirements)
        per = {r: to_items(idx.search(r, 20, mask), chunks, r)[:k] for r in reqs}
        return RetrievalResult(hits=merge_round_robin(per, k)[:k], by_requirement=per, requirements=reqs)
