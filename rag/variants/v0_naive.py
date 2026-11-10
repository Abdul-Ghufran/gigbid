"""V0 - naive dense baseline: fixed 500-char chunks, top-k cosine on the whole job post."""
from rag.query import job_text
from rag.variants.base import RetrievalResult, Variant, to_items


class V0Naive(Variant):
    name = "v0_naive"

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        idx, chunks = self.c.dense("fixed")
        ranked = idx.search(job_text(job), k * 6, self.c.mask(chunks, filters))
        return RetrievalResult(hits=to_items(ranked, chunks)[:k])
