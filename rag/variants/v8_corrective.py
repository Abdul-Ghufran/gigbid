"""V8 - corrective RAG loop as a LangGraph StateGraph:
retrieve -> grade each requirement's evidence -> re-query weak requirements (synonym expansion, optional LLM
rewrite) -> grade again -> requirements still without evidence are marked UNSUPPORTED so the writer
refuses to claim them (and the Fit Matcher can recommend a skip)."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rag.ingest.skills import expand, extract_skills
from rag.variants.base import RetrievalResult, Variant, merge_round_robin
from rag.variants.v3_rerank import V3Rerank


class CRAGState(TypedDict, total=False):
    job: dict
    requirements: list[str]
    per: dict
    weak: list[str]
    tries: int
    rewrites: dict


class V8Corrective(Variant):
    name = "v8_corrective"

    def __init__(self, corpus, **opts):
        super().__init__(corpus, **opts)
        self.base = V3Rerank(corpus, **opts)
        self.threshold = opts.get("weak_threshold", 0.0)
        self.max_requeries = opts.get("max_requeries", 1)
        self.use_llm = opts.get("llm_rewrite", False)
        self.filters = None
        self.k = 10
        g = StateGraph(CRAGState)
        g.add_node("retrieve", self._retrieve)
        g.add_node("grade", self._grade)
        g.add_node("rewrite", self._rewrite)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", lambda s: "rewrite" if s["weak"] and s["tries"] < self.max_requeries else END)
        g.add_edge("rewrite", "grade")
        self.graph = g.compile()

    def _supported(self, req: str, hits) -> bool:
        if not hits:
            return False
        top = hits[0]
        if top.signals.get("ce", -99) >= self.threshold:
            return True
        req_sk = set(extract_skills(req))
        # lexical safety net: the top item's ingest-time skills cover the requirement's named skill
        return bool(req_sk) and bool(req_sk & set(self.c.by_id[top.item_id].skills)) and top.signals.get("ce", -99) > self.threshold - 4

    async def _retrieve(self, s: CRAGState):
        r = await self.base.retrieve(s["job"], k=self.k, requirements=s.get("requirements"), filters=self.filters)
        return {"per": r.by_requirement, "requirements": r.requirements, "tries": 0, "rewrites": {}}

    async def _grade(self, s: CRAGState):
        return {"weak": [r for r in s["requirements"] if not self._supported(r, s["per"].get(r, []))]}

    async def _rewrite(self, s: CRAGState):
        per = dict(s["per"])
        rewrites = dict(s.get("rewrites", {}))
        for req in s["weak"]:
            q = req
            sks = extract_skills(req)
            if sks:
                q = req + " " + " ".join(x for sk in sks for x in expand(sk))
            elif self.use_llm:
                try:
                    from agent import llm

                    from agent.config import prompt, render

                    pr = prompt("rag_rewrite")
                    q = await llm.text("rag_aux", pr["system"], render(pr["user"], requirement=req), max_tokens=60)
                except Exception:
                    pass
            rewrites[req] = q
            r = await self.base.retrieve({"title": "", "description": ""}, k=self.k, requirements=[q], filters=self.filters)
            new = r.by_requirement.get(q, [])
            for h in new:
                h.requirement = req
            if new and (not per.get(req) or new[0].score > per[req][0].score):
                per[req] = new
        return {"per": per, "tries": s["tries"] + 1, "rewrites": rewrites}

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        self.filters, self.k = filters, k
        out = await self.graph.ainvoke({"job": job, "requirements": requirements})
        weak = out.get("weak", [])
        per = {r: ([] if r in weak else hits) for r, hits in out["per"].items()}
        merged = merge_round_robin({r: h for r, h in out["per"].items() if r not in weak}, k)
        return RetrievalResult(hits=merged[:k], by_requirement=per, unsupported=weak, requirements=out["requirements"],
                               debug={"rewrites": out.get("rewrites", {})})
