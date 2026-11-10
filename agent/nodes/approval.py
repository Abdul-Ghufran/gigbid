"""Human-in-the-loop (C5) and exactly-once submission (C6).

prepare_approval  builds the dry_run previews (exact payload + Connects cost + weekly budget) via MCP.
approval          interrupt(): pauses the thread durably (Postgres checkpointer) until the UI resumes it with
                  approve / edit / reject.  Nothing is ever sent without passing through here.
record_edit       diffs the edit, stores it raw (not memory), re-runs the style promotion rule, then the graph
                  re-checks the edited text with the Compliance Guard.
submit            creates the marketplace draft and submits it with idempotency keys derived from the thread and
                  draft content, so a crash + resume (or a worker retry) can never submit twice or spend Connects twice.
"""
from __future__ import annotations

import difflib
import hashlib
import re

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision
from agent.mcp_client import Toolbox
from agent.runtime import emit, node, tool_tracer


def _key(state: dict, kind: str) -> str:
    d = state["draft"]
    h = hashlib.sha1((d["cover_letter"] + "|".join(d.get("screening_answers", [])) + str(state["price"]["amount"])).encode()).hexdigest()[:10]
    raw = f"{state['user_id']}:{state['job_id']}:{kind}:{h}"
    return re.sub(r"[^A-Za-z0-9:_\-.]", "-", raw)[:120]


@node("prepare_approval")
async def prepare_approval(state: dict) -> dict:
    tb = Toolbox("submitter", state["user_id"], on_call=tool_tracer("prepare_approval"))
    d, price = state["draft"], state["price"]
    prev = await tb.call("marketplace", "create_proposal_draft", {
        "job_id": state["job_id"], "cover_letter": d["cover_letter"], "screening_answers": d.get("screening_answers", []),
        "bid_amount": price["amount"], "bid_type": price["bid_type"], "idempotency_key": _key(state, "draft"), "dry_run": True})
    bal = await tb.call("marketplace", "get_connects_balance", {})
    s = state.get("settings", {})
    cost = price.get("connects_cost") or prev.get("connects_cost") or 0
    spent = s.get("connects_spent_week", 0)
    preview = {"would_send": prev.get("would_send"), "connects_cost": cost, "balance_before": bal.get("balance"),
               "balance_after": (bal.get("balance") or 0) - cost, "weekly_budget": s.get("weekly_connects_budget"),
               "spent_this_week": spent, "within_weekly_budget": spent + cost <= (s.get("weekly_connects_budget") or 10**6),
               "policy_version": state.get("compliance", {}).get("policy_version")}
    return {"preview": preview, "status": "awaiting_approval"}


def approval(state: dict) -> dict:
    """Pause for the human.  The payload is everything the approval screen shows."""
    comp = state.get("compliance", {})
    payload = {
        "type": "proposal_approval", "job_id": state["job_id"], "draft": state["draft"],
        "evidence": state.get("evidence", {}), "verification": state.get("verification", {}),
        "risk": state["analyses"].get("risk", {}), "fit": state["analyses"].get("fit", {}),
        "price": state.get("price", {}), "preview": state.get("preview", {}), "compliance": comp,
        "critiques": state.get("critiques", []), "blocked": comp.get("status") == "block",
    }
    emit("interrupt", "approval", {"job_id": state["job_id"], "blocked": payload["blocked"]})
    raw = interrupt(payload)
    dec = ApprovalDecision.model_validate(raw)
    if dec.action == "approve" and payload["blocked"]:
        dec = ApprovalDecision(action="edit", cover_letter=state["draft"]["cover_letter"], reason="approve refused: draft is blocked by compliance")
    if dec.action == "approve" and not state.get("preview", {}).get("within_weekly_budget", True) and not (dec.reason or "").startswith("override"):
        return {"approvals": [dec.model_dump()], "status": "needs_attention",
                "attention": ["Weekly Connects budget would be exceeded; approve with reason 'override' to spend anyway."]}
    out = {"approvals": [dec.model_dump()]}
    if dec.action == "reject":
        out["status"] = "rejected"
    elif dec.action == "edit":
        out["status"] = "running"
    else:
        out["status"] = "approved"
        if dec.bid_amount:
            out["price"] = {**state["price"], "amount": dec.bid_amount}
    return out


@node("record_edit")
async def record_edit(state: dict) -> dict:
    dec = state["approvals"][-1]
    before = state["draft"]["cover_letter"]
    after = dec.get("cover_letter") or before
    answers = dec.get("screening_answers") or state["draft"].get("screening_answers", [])
    diff = list(difflib.unified_diff(before.split(), after.split(), lineterm="", n=0))
    try:
        from common.db import Edit, session

        with session() as s:
            s.add(Edit(user_id=state["user_id"], job_id=state["job_id"], category=state["job"].get("category") or "",
                       before=before, after=after, diff={"lines": diff[:200]}))
        from agent.memory.store import refresh_style

        promoted = await refresh_style(state["user_id"])
    except Exception:
        promoted = []
    emit("memory", "record_edit", {"diff_lines": len(diff), "style_rules_promoted": [p["key"] for p in promoted]})
    price = {**state["price"], "amount": dec["bid_amount"]} if dec.get("bid_amount") else state["price"]
    return {"draft": {**state["draft"], "cover_letter": after, "screening_answers": answers, "edited_by_user": True}, "price": price}


@node("submit")
async def submit(state: dict) -> dict:
    tb = Toolbox("submitter", state["user_id"], on_call=tool_tracer("submit"))
    d, price = state["draft"], state["price"]
    draft = await tb.call("marketplace", "create_proposal_draft", {
        "job_id": state["job_id"], "cover_letter": d["cover_letter"], "screening_answers": d.get("screening_answers", []),
        "bid_amount": price["amount"], "bid_type": price["bid_type"], "idempotency_key": _key(state, "draft"), "dry_run": False})
    pid = draft["result"].get("id")
    res = await tb.call("marketplace", "submit_proposal", {"proposal_id": pid, "idempotency_key": _key(state, "submit"), "dry_run": False})
    return {"submission": {"proposal_id": pid, "connects_spent": res.get("connects_cost"), "balance_after": res.get("balance_after"),
                           "idempotent_replay": res.get("idempotent_replay", False), "result": res.get("result", {})},
            "status": "submitted"}
