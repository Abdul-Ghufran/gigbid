"""Factory: the deployed variant is chosen by config (agent/config.yaml rag.shipped_variant), which in turn is
chosen by evals/results/rag_variants.json - not by default."""
from __future__ import annotations

from agent.config import config
from rag.corpus import get_corpus
from rag.variants.base import RetrievalResult, Variant
from rag.variants.v0_naive import V0Naive
from rag.variants.v1_decompose import V1Decompose
from rag.variants.v2_hybrid import V2Hybrid
from rag.variants.v3_rerank import V3Rerank
from rag.variants.v4_outcome import V4Outcome
from rag.variants.v5_multivector import V5MultiVector
from rag.variants.v6_contextual import V6Contextual
from rag.variants.v7_hyde import V7HyDE
from rag.variants.v8_corrective import V8Corrective
from rag.variants.v9_skill_graph import V9SkillGraph

VARIANTS: dict[str, type[Variant]] = {v.name: v for v in (V0Naive, V1Decompose, V2Hybrid, V3Rerank, V4Outcome, V5MultiVector,
                                                          V6Contextual, V7HyDE, V8Corrective, V9SkillGraph)}
_cache: dict[tuple, Variant] = {}


def get_retriever(persona: str, user_id: str | None = None, variant: str | None = None, **opts) -> Variant:
    name = variant or config()["rag"]["shipped_variant"]
    corpus = get_corpus(persona, user_id)
    if name == "v8_corrective":
        opts = {**config()["rag"]["corrective"], **opts}
    key = (name, id(corpus), tuple(sorted(opts.items())))
    if key not in _cache:
        _cache[key] = VARIANTS[name](corpus, **opts)
    return _cache[key]


async def search(persona: str, job: dict, k: int = 8, requirements=None, filters=None, user_id=None,
                 variant=None) -> RetrievalResult:
    return await get_retriever(persona, user_id, variant).retrieve(job, k=k, requirements=requirements, filters=filters)
