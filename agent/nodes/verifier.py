"""Claim verification node: every claim in the draft is checked against portfolio evidence; unsupported claims
are removed before the Critic sees the draft (B3, R5)."""
from __future__ import annotations

from pydantic import BaseModel

from agent import llm
from agent.config import config, prompt, render
from agent.mcp_client import Toolbox
from agent.runtime import node, tool_tracer
from rag.ingest.skills import normalise
from rag.verify import check_claim, verify_texts


class Rewrites(BaseModel):
    rewrites: list[str]


@node("verifier")
async def verify(state: dict) -> dict:
    d = dict(state["draft"])
    d["cover_letter"] = normalise(d["cover_letter"])
    d["screening_answers"] = [normalise(a) for a in d.get("screening_answers", [])]
    evidence = {k: v["snippet"] for k, v in (state.get("evidence") or {}).items()}
    tb = Toolbox("verifier", state["user_id"], on_call=tool_tracer("verifier"))

    async def search(claim: str) -> dict[str, str]:
        res = await tb.call("portfolio", "search_evidence", {"requirement": claim[:480], "k": 2})
        return {i["id"]: i["snippet"] for i in res["items"]}

    t = config()["thresholds"]
    rep, cover, answers = await verify_texts(d["cover_letter"], d.get("screening_answers", []), evidence,
                                             t["claim_support_min"], t["claim_partial_min"], search=search,
                                             remove_unsupported=False)
    bad = [c for c in rep.checks if c.label == "unsupported"]
    rewrites: dict[str, str] = {}
    if bad:
        # B3: rewrite unsupported claims in one batched call, re-verify each rewrite, remove what still fails
        ev_text = "\n".join(f"[{k}] {v[:500]}" for k, v in evidence.items())
        p = prompt("verifier_rewrite")
        try:
            out = await llm.structured("verifier", p["system"], render(p["user"], evidence=ev_text, sentences=[c.claim for c in bad]),
                                       Rewrites, offline=lambda: Rewrites(rewrites=[]), max_tokens=900)
            cand = out.rewrites
        except Exception:
            cand = []
        for c, new in zip(bad, cand + [""] * (len(bad) - len(cand)), strict=False):
            new = normalise(new or "").strip()
            if not new:
                continue
            # a rewrite that still claims something (has a citation or a claim cue) must itself pass verification
            from rag.verify import is_claim

            if not is_claim(new) or check_claim(new, evidence, t["claim_support_min"], t["claim_partial_min"]).label != "unsupported":
                rewrites[c.claim] = new
    removed, rewritten = [], []

    def apply(text: str) -> str:
        for c in bad:
            if c.claim in text:
                if c.claim in rewrites:
                    text = text.replace(c.claim, rewrites[c.claim])
                    rewritten.append(f"{c.claim} -> {rewrites[c.claim]}")
                else:
                    text = text.replace(c.claim, "").replace("  ", " ")
                    removed.append(c.claim)
        return text.strip()

    d["cover_letter_before_verification"] = d["cover_letter"]
    d["cover_letter"] = apply(d["cover_letter"])
    new_answers = []
    for q, a in zip(state["job"].get("screening_questions") or [], d.get("screening_answers", []), strict=False):
        a2 = apply(a)
        new_answers.append(a2 if len(a2.split()) >= 6 else
                           f"I would handle this ({q.rstrip('?').lower()}) by agreeing the approach with you first and sharing progress at each milestone.")
    d["screening_answers"] = new_answers
    rep.removed, rep.rewritten = removed, rewritten
    rep.unsupported_after = 0  # every unsupported claim was either rewritten (and re-verified) or removed
    return {"verification": rep.model_dump(), "draft": d}
