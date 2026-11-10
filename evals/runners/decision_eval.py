"""Decision quality (B4): bid-or-skip F1, scam precision/recall, injection detection, price inside the fair band.

Runs the analysis half of the bid graph (intake -> analyst | risk | fit -> decide -> pricing) per dev job.
  python -m evals.runners.decision_eval --mode offline            # rules + retrieval only, all 600 jobs (free)
  python -m evals.runners.decision_eval --mode llm --per-persona 40   # with the open-profile LLM nodes
"""
import argparse
import asyncio
import time

from evals.runners import harness as H  # noqa: F401  (sets env first)
from agent.llm import Ledger, ledger_var  # noqa: E402
from agent.nodes import analyst, decision, fit_matcher, pricing, risk_assessor, scout  # noqa: E402
from common.db import init_db  # noqa: E402


async def analyse(persona: str, job: dict) -> dict:
    st = {"user_id": f"persona-{persona}", "job_id": job["job_id"], "settings": H.settings(persona), "analyses": {}}
    st.update(await scout.intake(st))
    outs = await asyncio.gather(analyst.analyse(st), risk_assessor.assess(st), fit_matcher.match(st))
    for o in outs:
        st["analyses"].update(o.get("analyses", {}))
    st.update(await decision.decide(st))
    if st["decision"]["action"] == "bid":
        st.update(await pricing.price(st))
    return st


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["offline", "llm"], default="offline")
    ap.add_argument("--per-persona", type=int, default=200)
    a = ap.parse_args()
    import os

    if a.mode == "offline":
        os.environ["LLM_OFFLINE"] = "1"
    init_db()
    jobs = H.fixed_set(a.per_persona, seed=3) if a.per_persona < 200 else [(p, r) for p in ("ai", "web", "data") for r in H.dev(p)]
    rows = []
    for i, (p, job) in enumerate(jobs):
        led = Ledger()
        ledger_var.set(led)
        t0 = time.perf_counter()
        st = await analyse(p, job)
        g = job["_gold"]
        price = st.get("price", {}).get("amount")
        band = g["fair_band"]
        rows.append({"job_id": job["job_id"], "persona": p, "kind": g["kind"], "gold_bid": g["bid"], "pred": st["decision"]["action"],
                     "gold_scam": g["scam"], "pred_scam": st["analyses"]["risk"]["scam"], "gold_injection": g["injection"],
                     "pred_injection": st["analyses"]["risk"]["injection_detected"], "fit": st["analyses"]["fit"]["score"],
                     "price": price, "in_band": (band[0] <= price <= band[1]) if price and g["bid"] else None,
                     "latency_s": round(time.perf_counter() - t0, 3), "tokens": led.tokens, "cost_usd": led.cost_usd,
                     "fallbacks": led.fallbacks, "offline": led.offline})
        if i % 25 == 0:
            print(i, len(jobs), flush=True)

    def metrics(rs):
        tp = sum(r["gold_bid"] and r["pred"] == "bid" for r in rs)
        fp = sum((not r["gold_bid"]) and r["pred"] == "bid" for r in rs)
        fn = sum(r["gold_bid"] and r["pred"] != "bid" for r in rs)
        stp = sum(r["gold_scam"] and r["pred_scam"] for r in rs)
        sfp = sum((not r["gold_scam"]) and r["pred_scam"] for r in rs)
        sfn = sum(r["gold_scam"] and not r["pred_scam"] for r in rs)
        inj = [r for r in rs if r["gold_injection"]]
        priced = [r for r in rs if r["in_band"] is not None]
        return {"n": len(rs), "bid_f1": H.f1(tp, fp, fn), "bid_precision": round(tp / max(1, tp + fp), 4), "bid_recall": round(tp / max(1, tp + fn), 4),
                "accuracy_bid_vs_not": round(sum((r["pred"] == "bid") == r["gold_bid"] for r in rs) / max(1, len(rs)), 4),
                "scam_precision": round(stp / max(1, stp + sfp), 4), "scam_recall": round(stp / max(1, stp + sfn), 4),
                "injection_detected": round(sum(r["pred_injection"] for r in inj) / max(1, len(inj)), 4) if inj else None,
                "price_in_fair_band": round(sum(r["in_band"] for r in priced) / max(1, len(priced)), 4) if priced else None,
                "p50_latency_s": H.pct([r["latency_s"] for r in rs], .5), "p95_latency_s": H.pct([r["latency_s"] for r in rs], .95),
                "mean_tokens": H.mean([r["tokens"] for r in rs]), "mean_cost_usd": H.mean([r["cost_usd"] for r in rs])}

    out = {"mode": a.mode, "overall": metrics(rows),
           "by_persona": {p: metrics([r for r in rows if r["persona"] == p]) for p in ("ai", "web", "data")},
           "by_kind": {k: metrics([r for r in rows if r["kind"] == k]) for k in sorted({r["kind"] for r in rows})},
           "rows": rows}
    H.write(f"decision_eval_{a.mode}", out)
    print({k: out["overall"][k] for k in ("n", "bid_f1", "scam_precision", "scam_recall", "injection_detected", "price_in_fair_band", "p95_latency_s")})


if __name__ == "__main__":
    asyncio.run(main())
