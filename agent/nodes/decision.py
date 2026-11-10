"""Bid-or-skip decision: explicit, explainable rules over the three parallel analyses (thresholds in config)."""
from __future__ import annotations

from agent.config import config
from agent.handoffs import BidDecision
from agent.runtime import node


def decide_from(analyses: dict, job: dict, settings: dict, force_bid: bool = False) -> BidDecision:
    t = config()["thresholds"]
    risk, fit = analyses.get("risk", {}), analyses.get("fit", {})
    reasons: list[str] = []
    b = job.get("budget") or {}
    if risk.get("scam"):
        return BidDecision(action="skip", reasons=[f"Likely scam / policy risk: {', '.join(risk.get('flags', []))}."],
                           auto=settings.get("autonomy") == "auto_skip_low_fit")
    if force_bid:
        return BidDecision(action="bid", reasons=["Freelancer asked GigBid to draft anyway."])
    if risk.get("score", 0) > t["max_risk"]:
        return BidDecision(action="skip", reasons=[f"Risk score {risk['score']:.2f} above limit {t['max_risk']}."])
    floor_ok = (b.get("max") or 0) >= (settings.get("hourly_rate", 0) * 0.8 if b.get("type") == "hourly" else settings.get("min_project", 0))
    fs = fit.get("score", 0)
    reasons.append(f"Fit {fs:.2f}: " + " ".join(fit.get("reasons", [])[:2]))
    if fs < t["watch_min_fit"]:
        return BidDecision(action="skip", reasons=reasons + ["Portfolio cannot prove most requirements."],
                           auto=settings.get("autonomy") == "auto_skip_low_fit")
    if not floor_ok:
        return BidDecision(action="skip", reasons=reasons + [f"Budget {b.get('max')} below your floor."])
    if fs < t["bid_min_fit"]:
        return BidDecision(action="watch", reasons=reasons + ["Partial fit: watch, or draft anyway if you want it."])
    if risk.get("injection_detected"):
        reasons.append("Post contains instruction-like text aimed at AI tools; it was quoted and ignored.")
    return BidDecision(action="bid", reasons=reasons + [f"Client: {risk.get('client_summary', '')}"])


@node("decide")
async def decide(state: dict) -> dict:
    d = decide_from(state.get("analyses", {}), state["job"], state.get("settings", {}), state.get("force_bid", False))
    status = {"skip": "skipped", "watch": "watch", "bid": "running"}[d.action]
    return {"decision": d.model_dump(), "status": status}
