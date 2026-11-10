"""Claim verification node: every claim in the draft is checked against portfolio evidence; unsupported claims
are removed before the Critic sees the draft (B3, R5)."""
from __future__ import annotations

from agent.config import config
from agent.mcp_client import Toolbox
from agent.runtime import node, tool_tracer
from rag.verify import verify_texts


@node("verifier")
async def verify(state: dict) -> dict:
    d = dict(state["draft"])
    evidence = {k: v["snippet"] for k, v in (state.get("evidence") or {}).items()}
    tb = Toolbox("verifier", state["user_id"], on_call=tool_tracer("verifier"))

    async def search(claim: str) -> dict[str, str]:
        res = await tb.call("portfolio", "search_evidence", {"requirement": claim[:480], "k": 2})
        return {i["id"]: i["snippet"] for i in res["items"]}

    t = config()["thresholds"]
    rep, cover, answers = await verify_texts(d["cover_letter"], d.get("screening_answers", []), evidence,
                                             t["claim_support_min"], t["claim_partial_min"], search=search)
    d["cover_letter_before_verification"] = d["cover_letter"]
    d["cover_letter"], d["screening_answers"] = cover, answers
    return {"verification": rep.model_dump(), "draft": d}
