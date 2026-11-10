"""Client Liaison: reads new client messages, classifies intent, drafts a reply or interview slots, and (after
human approval) sends it and places tentative calendar holds."""
from __future__ import annotations

import hashlib
import re

from langgraph.types import interrupt

from agent import llm
from agent.config import config, prompt, render
from agent.guards import delimit, detect_injection, strip_injection
from agent.handoffs import ApprovalDecision, ClientIntent, ReplyDraft
from agent.mcp_client import Toolbox
from agent.nodes.compliance import check_text
from agent.runtime import emit, node, tool_tracer

SCAM_RX = re.compile(r"telegram|whats\s?app|skype|onboarding fee|pay the \$|send (me )?your (email|phone|bank)|outside (the )?platform", re.I)
INTERVIEW_RX = re.compile(r"\b(call|interview|meeting|schedule|time slots?|when are you free|video)\b", re.I)
NEGOTIATE_RX = re.compile(r"\$\s?(\d[\d,]*)|budget is tighter|lower (price|rate)|would you accept", re.I)


def rule_intent(text: str) -> ClientIntent:
    inj = bool(detect_injection(text))
    if SCAM_RX.search(text):
        return ClientIntent(intent="scam_signal", confidence=0.9, injection_detected=inj, summary="Asks to move off-platform or pay a fee.")
    if INTERVIEW_RX.search(text):
        return ClientIntent(intent="interview_request", confidence=0.8, injection_detected=inj, summary="Wants a call.")
    m = NEGOTIATE_RX.search(text)
    if m:
        amt = re.search(r"\$\s?(\d[\d,]*)", text)
        num = float(amt.group(1).replace(",", "")) if amt else None
        return ClientIntent(intent="negotiation", confidence=0.8, injection_detected=inj, counter_offer=num, summary="Negotiates price.")
    if re.search(r"move forward|hire you|sending the contract|let's start", text, re.I):
        return ClientIntent(intent="acceptance", confidence=0.8, injection_detected=inj, summary="Accepts.")
    return ClientIntent(intent="question", confidence=0.6, injection_detected=inj, summary="Asks a question.")


@node("liaison_read", budget_key="max_tokens_per_conversation_turn")
async def read_thread(state: dict) -> dict:
    tb = Toolbox("liaison", state["user_id"], on_call=tool_tracer("liaison_read"))
    t = await tb.call("marketplace", "get_thread", {"thread_id": state["thread_id"]})
    msgs = t["messages"]
    last_out = max([i for i, m in enumerate(msgs) if m["sender"] == "freelancer"], default=-1)
    new = [m for m in msgs[last_out + 1:] if m["sender"] == "client"]
    job = state.get("job") or await tb.call("marketplace", "get_job", {"job_id": t["job_id"]})
    return {"messages": msgs, "new_messages": new, "job": job, "job_id": t["job_id"],
            "status": "running" if new else "idle"}


@node("intent", budget_key="max_tokens_per_conversation_turn")
async def classify(state: dict) -> dict:
    text = "\n".join(m["text"] for m in state["new_messages"])
    rules = rule_intent(text)
    p = prompt("intent")
    user = render(p["user"], rule_flags=[rules.intent] + (["prompt_injection"] if rules.injection_detected else []),
                  messages=delimit(text, "client_message"))
    it = await llm.structured("intent", p["system"], user, ClientIntent, offline=lambda: rules)
    if rules.intent == "scam_signal":  # rules win for safety-critical intents
        it.intent = "scam_signal"
    it.injection_detected = it.injection_detected or rules.injection_detected
    it.counter_offer = it.counter_offer or rules.counter_offer
    return {"intent": it.model_dump()}


@node("plan_reply", budget_key="max_tokens_per_conversation_turn")
async def plan(state: dict) -> dict:
    out = {}
    if state["intent"]["intent"] == "interview_request":
        tb = Toolbox("liaison", state["user_id"], on_call=tool_tracer("plan_reply"))
        r = await tb.call("workspace", "free_slots", {"days_ahead": 5, "duration_minutes": 30, "max_slots": 3,
                                                      "timezone": state.get("settings", {}).get("timezone", "Asia/Karachi")})
        out["slots"] = r["slots"]
    return out


def negotiate_counter(state: dict) -> float:
    """Walk-away rule: never below the user's floor; meet the client ~10% above their offer, capped at our budget max."""
    floor = state.get("settings", {}).get("min_project", 0)
    offer = state["intent"].get("counter_offer") or 0
    cap = (state.get("job", {}).get("budget") or {}).get("max") or offer * 1.1
    return round(max(floor, min(offer * 1.1, max(cap, offer))), 0)


def _template_reply(state: dict) -> ReplyDraft:
    it = state["intent"]["intent"]
    title = state.get("job", {}).get("title", "the project")
    if it == "interview_request":
        slots = "; ".join(s["label"] for s in state.get("slots", []))
        return ReplyDraft(text=f"Thanks for getting back to me about {title}. I'd be glad to talk. I'm free at: {slots}. "
                               f"Please pick whichever suits you and we can do the call through the platform.", proposed_slots=state.get("slots", []))
    if it == "negotiation":
        floor = state.get("settings", {}).get("min_project", 0)
        counter = negotiate_counter(state)
        return ReplyDraft(text=f"Thanks for the open discussion. I can work within {counter:,.0f} USD if we trim the scope to the "
                               f"core deliverables first; happy to propose that split here on the platform.", counter_price=counter)
    if it == "scam_signal":
        return ReplyDraft(text="Thanks! To keep both of us protected I keep all communication, contracts and payments on this "
                               "platform, so let's continue here. Happy to answer any question about the work.")
    if it == "acceptance":
        return ReplyDraft(text="Great news, thank you! I'll accept the contract on the platform and share a short kickoff plan "
                               "with the first milestone today.")
    return ReplyDraft(text=f"Thanks for the question about {title}. I'd start by confirming the success criteria with you, then "
                           f"deliver a first working version early so you can give feedback. Happy to go into more detail here.")


@node("liaison_draft", budget_key="max_tokens_per_conversation_turn")
async def draft(state: dict) -> dict:
    it = state["intent"]
    convo = "\n".join(f"{m['sender'].upper()}: {strip_injection(m['text'])[0] if m['sender'] == 'client' else m['text']}"
                      for m in state["messages"][-8:])
    floor = state.get("settings", {}).get("min_project", 0)
    counter = None
    if it["intent"] == "negotiation":
        counter = negotiate_counter(state)
    tb = Toolbox("writer", state["user_id"], on_call=tool_tracer("liaison_draft"))
    ev = await tb.call("portfolio", "search_evidence", {"requirement": state.get("job", {}).get("title", "")[:200] or "relevant work", "k": 2})
    p = prompt("liaison")
    user = render(p["user"], intent=it, job={k: state.get("job", {}).get(k) for k in ("title", "budget")},
                  evidence=[{"id": i["id"], "title": i["title"], "snippet": i["snippet"][:300]} for i in ev["items"]],
                  slots=[s["label"] for s in state.get("slots", [])] or "none", counter=counter or "n/a",
                  messages=delimit(convo, "conversation"))
    r = await llm.structured("liaison", p["system"], user, ReplyDraft, offline=lambda: _template_reply(state))
    r.proposed_slots = state.get("slots", [])
    r.counter_price = counter
    v = await check_text(r.text, [], {})
    r.text = v.cover_letter if v.status != "block" or len(v.cover_letter.split()) > 8 else _template_reply(state).text
    return {"reply": r.model_dump(), "compliance": v.model_dump()}


@node("liaison_preview", budget_key="max_tokens_per_conversation_turn")
async def preview(state: dict) -> dict:
    tb = Toolbox("liaison", state["user_id"], on_call=tool_tracer("liaison_preview"))
    key = _key(state)
    pv = await tb.call("marketplace", "send_message", {"thread_id": state["thread_id"], "text": state["reply"]["text"],
                                                        "idempotency_key": key, "dry_run": True})
    return {"preview": pv, "status": "awaiting_approval"}


def _key(state: dict) -> str:
    h = hashlib.sha1(state["reply"]["text"].encode()).hexdigest()[:10]
    return re.sub(r"[^A-Za-z0-9:_\-.]", "-", f"{state['user_id']}:{state['thread_id']}:msg:{h}")[:120]


def approval(state: dict) -> dict:
    emit("interrupt", "message_approval", {"thread_id": state["thread_id"]})
    raw = interrupt({"type": "message_approval", "thread_id": state["thread_id"], "intent": state["intent"],
                     "reply": state["reply"], "slots": state.get("slots", []), "preview": state.get("preview"),
                     "compliance": state.get("compliance"), "messages": state["messages"][-8:]})
    dec = ApprovalDecision.model_validate(raw)
    out = {"approvals": [dec.model_dump()]}
    if dec.action == "edit" and dec.cover_letter:
        out["reply"] = {**state["reply"], "text": dec.cover_letter, "edited_by_user": True}
        out["status"] = "running"
    elif dec.action == "reject":
        out["status"] = "rejected"
    else:
        out["status"] = "approved"
    return out


@node("liaison_send", budget_key="max_tokens_per_conversation_turn")
async def send(state: dict) -> dict:
    tb = Toolbox("liaison", state["user_id"], on_call=tool_tracer("liaison_send"))
    res = await tb.call("marketplace", "send_message", {"thread_id": state["thread_id"], "text": state["reply"]["text"],
                                                         "idempotency_key": _key(state), "dry_run": False})
    holds = []
    for s in state["reply"].get("proposed_slots", [])[:3]:
        h = await tb.call("workspace", "create_interview_hold", {
            "start": s["start"], "end": s["end"], "title": f"Tentative: call about {state.get('job', {}).get('title', '')[:80]}",
            "idempotency_key": f"{_key(state)}:hold:{s['start'][:16]}".replace("+", "p")[:120]})
        holds.append(h)
    return {"sent": {"result": res, "holds": holds}, "status": "sent"}


def recheck_needed(state: dict) -> bool:
    return bool(state["approvals"] and state["approvals"][-1]["action"] == "edit")


async def recheck(state: dict) -> dict:
    v = await check_text(state["reply"]["text"], [], {})
    return {"compliance": v.model_dump(), "reply": {**state["reply"], "text": v.cover_letter}}


_ = config
