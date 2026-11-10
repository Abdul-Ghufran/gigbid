"""Proposal quality + GigSim outcomes (B4/B5, E5).

For a fixed set of gold-bid dev jobs, runs the real bid graph (live models of the chosen profile) up to the approval
interrupt with a given retrieval variant, then records for every proposal:
  unsupported claims per proposal before and after verification, critic revisions, compliance removals,
  GigSim simulated client verdict (reply / interview / hire, via the admin scoring endpoint: no Connects spent),
  latency and tokens / USD per proposal.
  python -m evals.runners.gigsim_outcomes --variant v8_corrective --per-persona 8 [--profile open] [--tag best]
Proposals are saved for the LLM judge and the human calibration sheet.
"""
import argparse
import asyncio
import os
import time

from evals.runners import harness as H
from agent.config import config  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.llm import Ledger, ledger_var  # noqa: E402
from common.db import init_db  # noqa: E402
from rag.verify import check_claim, is_claim, split_sentences  # noqa: E402


async def draft(g, persona, job, tag):
    led = Ledger()
    ledger_var.set(led)
    cfg = {"configurable": {"thread_id": f"{tag}:{job['job_id']}"}, "recursion_limit": 80}
    t0 = time.perf_counter()
    await g.ainvoke({"user_id": f"persona-{persona}", "job_id": job["job_id"], "settings": H.settings(persona), "force_bid": True}, cfg)
    v = (await g.aget_state(cfg)).values
    return v, led, time.perf_counter() - t0


def residual_unsupported(text: str, evidence: dict, t) -> int:
    """Independent post-hoc audit of the FINAL text (what the client would read)."""
    n = 0
    for s in split_sentences(text):
        if is_claim(s) and check_claim(s, evidence, t["claim_support_min"], t["claim_partial_min"]).label == "unsupported":
            n += 1
    return n


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=None)
    ap.add_argument("--profile", default="open")
    ap.add_argument("--per-persona", type=int, default=8)
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    os.environ["MODEL_PROFILE"] = a.profile
    if a.variant:
        config()["rag"]["shipped_variant"] = a.variant
    variant = config()["rag"]["shipped_variant"]
    tag = a.tag or f"{variant}_{a.profile}"
    init_db()
    from langgraph.checkpoint.memory import InMemorySaver

    g = build_bid_graph(InMemorySaver())
    t = config()["thresholds"]
    jobs = H.fixed_set(a.per_persona, kinds={"strong", "partial", "vague", "injection"}, bid_only=True, seed=21)
    rows = []
    for i, (p, job) in enumerate(jobs):
        try:
            v, led, secs = await draft(g, p, job, tag)
        except Exception as e:  # keep going; failures are part of the record
            rows.append({"job_id": job["job_id"], "persona": p, "error": f"{type(e).__name__}: {e}"[:300]})
            continue
        d = v.get("draft") or {}
        if not d:
            rows.append({"job_id": job["job_id"], "persona": p, "error": f"no draft (status {v.get('status')})"})
            continue
        ver = v.get("verification", {})
        ev = {k: x["snippet"] for k, x in (v.get("evidence") or {}).items()}
        price = v.get("price", {})
        react = H.client_reaction(job["job_id"], p, d["cover_letter"], d.get("screening_answers", []), price.get("amount", 1), price.get("bid_type", "fixed"))
        rows.append({
            "job_id": job["job_id"], "persona": p, "kind": job["_gold"]["kind"], "title": job["title"],
            "claims_before": ver.get("claims_before", 0), "unsupported_before": ver.get("unsupported_before", 0),
            "removed": len(ver.get("removed", [])), "rewritten": len(ver.get("rewritten", [])),
            "unsupported_final_audit": residual_unsupported(d["cover_letter"] + " " + " ".join(d.get("screening_answers", [])), ev, t),
            "revisions": len(v.get("critiques", [])) - 1, "critic_score": (v.get("critiques") or [{}])[-1].get("score"),
            "compliance": v.get("compliance", {}).get("status"), "compliance_removed": len(v.get("compliance", {}).get("removed", [])),
            "words": len(d["cover_letter"].split()), "replied": react["replied"], "interview": react["interview"], "hired": react["hired"],
            "client_score": react["score"], "latency_s": round(secs, 2), "tokens": led.tokens, "cost_usd": round(led.cost_usd, 6),
            "fallbacks": led.fallbacks, "offline_fallbacks": led.offline,
            "proposal": d["cover_letter"], "answers": d.get("screening_answers", []),
        })
        print(i + 1, len(jobs), job["job_id"], "replied" if react["replied"] else "-", f"{secs:.0f}s", flush=True)
    ok = [r for r in rows if "error" not in r]
    summary = {
        "variant": variant, "profile": a.profile, "n_jobs": len(jobs), "n_drafted": len(ok), "errors": len(rows) - len(ok),
        "unsupported_per_proposal_before": H.mean([r["unsupported_before"] for r in ok]),
        "unsupported_per_proposal_after": H.mean([r["unsupported_final_audit"] for r in ok]),
        "claims_per_proposal": H.mean([r["claims_before"] for r in ok]),
        "gigsim_reply_rate": H.mean([r["replied"] for r in ok]), "gigsim_interview_rate": H.mean([r["interview"] for r in ok]),
        "gigsim_hire_rate": H.mean([r["hired"] for r in ok]), "mean_client_score": H.mean([r["client_score"] for r in ok]),
        "mean_revisions": H.mean([r["revisions"] for r in ok]),
        "p50_latency_s": H.pct([r["latency_s"] for r in ok], .5), "p95_latency_s": H.pct([r["latency_s"] for r in ok], .95),
        "mean_tokens_per_proposal": H.mean([r["tokens"] for r in ok]), "mean_cost_usd_per_proposal": H.mean([r["cost_usd"] for r in ok]),
        "p95_cost_usd_per_proposal": H.pct([r["cost_usd"] for r in ok], .95),
        "by_persona": {p: {"n": len([r for r in ok if r["persona"] == p]), "reply_rate": H.mean([r["replied"] for r in ok if r["persona"] == p]),
                           "unsupported_before": H.mean([r["unsupported_before"] for r in ok if r["persona"] == p])} for p in ("ai", "web", "data")},
    }
    H.write(f"proposals_{tag}", {"summary": summary, "rows": rows})
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
