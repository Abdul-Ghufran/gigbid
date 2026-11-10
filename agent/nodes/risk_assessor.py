"""Risk Assessor: client quality from marketplace history + scam / free-work / off-platform / injection flags.

Deterministic rules decide hard flags (they are cheap, auditable and hard to talk around); the small LLM adds
subtle flags and the explanation but cannot lower a rule-based score.
"""
from __future__ import annotations

import re

from agent import llm
from agent.config import config, prompt, render
from agent.guards import delimit, detect_injection
from agent.handoffs import RiskReport
from agent.mcp_client import MarketplaceDown, Toolbox
from agent.runtime import node, tool_tracer

RULES = [
    ("free_work", 0.75, r"\b(unpaid|for free|free sample|free trial|without pay|best free sample)\b|\bsample\b.{0,40}\bwins? the contract\b"),
    ("off_platform_contact", 0.55, r"whats\s?app|telegram|skype|wechat|signal app|\bcontact me on\b|\bemail (me|our hr)\b|[\w.+-]+@[\w-]+\.[a-z]{2,}"),
    ("off_platform_payment", 0.8, r"\b(usdt|crypto|bitcoin|btc|wallet address|western union|outside the platform|avoid (the )?fees|pay(ment)? (directly|outside))\b"),
    ("identity_request", 0.8, r"\b(copy of your id|passport|national id|bank (details|account)|ssn|social security)\b"),
    ("advance_fee", 0.85, r"\b(purchase|buy|pay)\b.{0,40}\b(license|fee|kit|equipment)\b.{0,60}\b(refund|reimburs)"),
    ("too_good_to_be_true", 0.4, r"no experience (needed|required)|easy (money|job)|\$\s?\d{2,3}\s?/\s?h(ou)?r.{0,40}simple"),
]
HARD = {"free_work", "off_platform_payment", "identity_request", "advance_fee"}


def rule_assess(job: dict, client: dict | None) -> tuple[float, list[str], list[str]]:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    flags, notes, probs = [], [], []
    for name, w, rx in RULES:
        if re.search(rx, text, re.I):
            flags.append(name)
            probs.append(w)
    b = job.get("budget") or {}
    if (b.get("max") or 0) <= 0:
        flags.append("no_budget")
        probs.append(0.35)
    if client:
        if client.get("payment_verified") is False:
            flags.append("payment_unverified")
            probs.append(0.2)
        if not client.get("total_spent") and not client.get("hires"):
            flags.append("no_hiring_history")
            probs.append(0.15)
        if str(client.get("member_since", "")).startswith("2026"):
            notes.append("new account")
            probs.append(0.05)
    score = 1.0
    for p in probs:
        score *= 1 - p
    return round(1 - score, 3), flags, notes


def client_quality(c: dict | None) -> tuple[float, str]:
    if not c:
        return 0.5, "Client history unavailable."
    q = 0.3 + (0.25 if c.get("payment_verified") else 0) + min(0.25, (c.get("total_spent") or 0) / 40000) \
        + min(0.1, (c.get("hires") or 0) / 50) + (0.1 * ((c.get("avg_rating_given") or 4) - 4) if c.get("avg_rating_given") else 0)
    q = max(0.0, min(1.0, q))
    s = (f"{'Payment verified' if c.get('payment_verified') else 'Payment NOT verified'}, ${c.get('total_spent') or 0:,.0f} spent, "
         f"{c.get('hires') or 0} hires, member since {c.get('member_since', '?')}, hire rate {c.get('hire_rate', '?')}.")
    return round(q, 3), s


@node("risk_assessor")
async def assess(state: dict) -> dict:
    job = state["job"]
    tb = Toolbox("risk_assessor", state["user_id"], on_call=tool_tracer("risk_assessor"))
    client = None
    try:
        client = await tb.call("marketplace", "get_client_history", {"client_id": job.get("client_id") or "unknown"})
    except MarketplaceDown:
        raise
    except Exception:
        client = None
    rscore, flags, notes = rule_assess(job, client)
    spans = detect_injection(job.get("description", ""))
    if spans:
        flags.append("prompt_injection")
    cq, csum = client_quality(client)
    thr = config()["thresholds"]

    def offline():
        return RiskReport(score=rscore, scam=bool(HARD & set(flags)) or rscore >= thr["scam_risk"], flags=flags,
                          client_quality=cq, client_summary=csum,
                          explanation="; ".join(flags) or "No risk signals found by rules.")

    p = prompt("risk_assessor")
    user = render(p["user"], rule_flags=flags or ["none"], client=client or "unavailable",
                  job_post=delimit(f"{job.get('title', '')}\n\n{job.get('description', '')}"))
    rep = await llm.structured("risk_assessor", p["system"], user, RiskReport, offline=offline)
    # rules are a floor: the LLM may add risk, never remove a rule finding
    rep.flags = sorted(set(rep.flags) | set(flags))
    rep.score = round(max(rscore, min(rep.score, rscore + 0.3)), 3)
    rep.scam = bool(HARD & set(rep.flags)) or rep.score >= thr["scam_risk"] or (rep.scam and rscore >= 0.35)
    rep.injection_detected = bool(spans) or rep.injection_detected
    rep.injected_text = spans or rep.injected_text
    rep.client_quality, rep.client_summary = cq, csum
    return {"analyses": {"risk": rep.model_dump(), "client": client or {}}}
