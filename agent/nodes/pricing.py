"""Pricing Strategist: bid from market statistics, client spend and the user's floor; decides whether the
Connects cost is worth it (expected value rule from config).  Deterministic and explainable by design."""
from __future__ import annotations

import math

from agent.config import config
from agent.handoffs import PriceQuote
from agent.mcp_client import Toolbox
from agent.runtime import node, tool_tracer

LEVEL = {"entry": 0.85, "intermediate": 1.0, "expert": 1.2}


def connects_with_policy(base_cost: int | None, job: dict) -> int | None:
    """Platform policy from config (the 2 Nov change request lives in config, not in code)."""
    if base_cost is None:
        return None
    pol = config()["platform_policy"]["connects"]
    thr = pol.get("high_competition_threshold")
    if thr is not None and (job.get("proposals_count") or 0) >= thr:
        return int(math.ceil(base_cost * pol.get("high_competition_multiplier", 1.0)))
    return base_cost


def quote(job: dict, stats: dict, fit: float, settings: dict, client: dict | None, connects_cost: int | None,
          memory_reply_rate: float | None = None) -> PriceQuote:
    pc = config()["pricing"]
    b = job.get("budget") or {}
    hourly = b.get("type") == "hourly"
    typ = "hourly" if hourly else "fixed"
    s = stats.get(typ) or {}
    p25, p50, p75 = s.get("p25"), s.get("p50"), s.get("p75")
    rationale = []
    floor = settings.get("hourly_rate", 30) if hourly else settings.get("min_project", 200)
    if hourly:
        anchor = settings.get("hourly_rate", 30) * LEVEL.get(job.get("experience_level") or "intermediate", 1.0)
        rationale.append(f"Your rate {settings.get('hourly_rate')} USD/h adjusted for {job.get('experience_level', 'intermediate')} level.")
    else:
        mid = ((b.get("min") or 0) + (b.get("max") or 0)) / 2 or (p50 or floor)
        anchor = 0.6 * mid + 0.4 * (p50 or mid)
        rationale.append(f"Budget midpoint {mid:,.0f} blended with market median {p50 or 'n/a'}.")
    amount = anchor * (0.95 + 0.1 * fit)  # stronger proof supports a slightly higher price
    if p25:
        amount = max(amount, p25 * pc["undercut_floor_ratio"])
    if b.get("max"):
        amount = min(amount, b["max"] * 1.05)
        rationale.append(f"Kept within 5% of the client's max budget ({b['max']:,.0f}).")
    if client and client.get("recent_jobs"):
        paid = [j["awarded_price"] for j in client["recent_jobs"] if j.get("awarded_price")]
        if paid and not hourly:
            rationale.append(f"Client's recent awards average {sum(paid) / len(paid):,.0f} USD.")
    amount = max(amount, floor)
    rationale.append(f"Never below your floor ({floor:,.0f}).")
    amount = round(amount, 0 if not hourly else 1)
    cost = connects_with_policy(connects_cost, job)
    connects_usd = (cost or 0) * pc["connects_usd_value"]
    comp = job.get("proposals_count") or 10
    p_reply = memory_reply_rate if memory_reply_rate is not None else pc["base_reply_rate"]
    p_reply = min(0.8, p_reply * (0.5 + fit) * (15 / max(5, comp)) ** 0.5)
    value = (amount * (b.get("est_hours") or 20) if hourly else amount) * p_reply * 0.35  # ~35% of replies convert
    worth = value >= pc["min_expected_value_ratio"] * max(connects_usd, 0.01)
    rationale.append(f"Estimated reply chance {p_reply:.0%} with {comp} competing proposals; expected value "
                     f"{value:,.0f} USD vs {cost} Connects ({connects_usd:.2f} USD) -> {'worth it' if worth else 'not worth it'}.")
    return PriceQuote(amount=amount, bid_type=typ, market_p25=p25, market_p50=p50, market_p75=p75, floor=floor,
                      connects_cost=cost, connects_usd=round(connects_usd, 2), est_reply_probability=round(p_reply, 3),
                      expected_value_usd=round(value, 2), worth_connects=worth, rationale=rationale)


@node("pricing")
async def price(state: dict) -> dict:
    job = state["job"]
    tb = Toolbox("pricing", state["user_id"], on_call=tool_tracer("pricing"))
    stats = await tb.call("marketplace", "get_market_stats", {"category": job.get("category") or "web",
                                                              "skills": (job.get("skills_listed") or [])[:3]})
    from agent.memory.store import outcome_reply_rate

    q = quote(job, stats, state["analyses"].get("fit", {}).get("score", 0.5), state.get("settings", {}),
              state["analyses"].get("client"), job.get("connects_cost"),
              await outcome_reply_rate(state["user_id"], job.get("category")))
    out = {"price": q.model_dump()}
    if not q.worth_connects and not state.get("force_bid"):
        out["status"] = "watch"
        out["decision"] = {**state["decision"], "action": "watch",
                           "reasons": state["decision"]["reasons"] + ["Connects cost not justified by expected value."]}
    return out
