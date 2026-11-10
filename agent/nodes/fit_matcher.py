"""Fit Matcher: maps every requirement to portfolio evidence (Portfolio MCP, shipped retrieval pipeline) and
produces a fit score with reasons.  Runs in parallel with the analyst, so it decomposes requirements itself."""
from __future__ import annotations

import asyncio

from agent.guards import strip_injection
from agent.handoffs import EvidenceRef, FitReport, RequirementMatch
from agent.mcp_client import Toolbox
from agent.runtime import node, tool_tracer
from rag.ingest.skills import extract_skills
from rag.query import decompose


def requirements_for(job: dict) -> list[str]:
    clean, _ = strip_injection(job.get("description", ""))
    reqs = decompose({**job, "description": clean})
    skillful = [r for r in reqs if extract_skills(r)]
    return skillful or reqs


@node("fit_matcher")
async def match(state: dict) -> dict:
    job = state["job"]
    tb = Toolbox("fit_matcher", state["user_id"], on_call=tool_tracer("fit_matcher"))
    reqs = requirements_for(job)
    results = await asyncio.gather(*[tb.call("portfolio", "search_evidence", {"requirement": r, "k": 3}) for r in reqs])
    matrix, evidence = [], {}
    for r, res in zip(reqs, results, strict=True):
        refs = [EvidenceRef(item_id=i["id"], title=i["title"], type=i["type"], snippet=i["snippet"], score=i["score"],
                            source=i.get("source", "")) for i in res["items"]] if res["supported"] else []
        matrix.append(RequirementMatch(requirement=r, supported=res["supported"], evidence=refs))
        for e in refs:
            evidence[e.item_id] = e.model_dump()
    n = len(matrix) or 1
    supported = [m for m in matrix if m.supported]
    score = len(supported) / n
    matched = sorted({s for m in supported for s in extract_skills(m.requirement)})
    missing = [m.requirement for m in matrix if not m.supported]
    reasons = [f"{len(supported)}/{len(matrix)} requirements proven by portfolio evidence."]
    if missing:
        reasons.append("No evidence for: " + "; ".join(missing[:4]))
    if supported:
        top = supported[0].evidence[0]
        reasons.append(f"Strongest proof: {top.title} [{top.item_id}].")
    rep = FitReport(score=round(score, 3), matrix=matrix, matched_skills=matched, missing=missing, reasons=reasons,
                    retrieval_variant=results[0]["variant"] if results else "")
    return {"analyses": {"fit": rep.model_dump()}, "evidence": evidence}
