"""V6 - contextual retrieval: a generated context line (LLM, cached in .cache/context_lines.json; falls back
to a deterministic title/type/industry header) is prepended to every chunk before dense and BM25 indexing."""
import json

from rag.index.core import CACHE
from rag.variants.base import Variant
from rag.variants.v2_hybrid import V2Hybrid


class V6Contextual(Variant):
    name = "v6_contextual"
    uses_llm = True

    def __init__(self, corpus, **opts):
        super().__init__(corpus, **opts)
        self.base = V2Hybrid(corpus, decompose=opts.get("decompose", True), contextual=True)

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        return await self.base.retrieve(job, k=k, requirements=requirements, filters=filters)


async def build_context_lines(corpus, limit: int | None = None) -> int:
    """Generate (and cache) one context line per evidence item with the configured `rag_aux` model."""
    from agent import llm

    p = CACHE / "context_lines.json"
    cache = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    n = 0
    for it in corpus.evidence[: limit or None]:
        if it.id in cache:
            continue
        try:
            from agent.config import prompt, render

            pr = prompt("rag_context")
            line = await llm.text("rag_aux", pr["system"], render(pr["user"], type=it.type, title=it.title, text=it.text[:1500]),
                                  max_tokens=80)
        except Exception:
            continue
        cache[it.id] = line.strip().replace("\n", " ")[:300]
        n += 1
        if n % 20 == 0:
            p.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    p.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    corpus._contexts = None
    corpus._chunks.clear()
    corpus._idx.clear()
    return n
