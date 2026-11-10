"""V7 - HyDE: retrieve with a hypothetical ideal proposal for the job (LLM), fused with the raw post."""
from rag.index.core import rrf
from rag.query import decompose, job_text
from rag.variants.base import RetrievalResult, Variant, to_items


class V7HyDE(Variant):
    name = "v7_hyde"
    uses_llm = True

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        from agent import llm

        idx, chunks = self.c.dense("structured")
        mask = self.c.mask(chunks, filters)
        try:
            from agent.config import prompt, render
            from agent.guards import delimit

            pr = prompt("rag_hyde")
            hypo = await llm.text("rag_aux", pr["system"], render(pr["user"], job=delimit(job_text(job)[:2500])), max_tokens=250)
        except Exception:
            hypo = ""
        rankings = [idx.search(job_text(job), 40, mask)]
        if hypo:
            rankings.append(idx.search(hypo, 40, mask))
        return RetrievalResult(hits=to_items(rrf(*rankings, weights=[1.0, 1.5][: len(rankings)]), chunks)[:k],
                               requirements=decompose(job, requirements), debug={"hyde": hypo[:600]})
