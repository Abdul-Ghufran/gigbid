"""CI smoke eval (E2): 30 dev jobs through the analysis half of the graph + 9 drafted proposals; fails (exit 1) when
bid-or-skip F1 drops or unsupported claims rise past evals/thresholds.yaml.  Runs offline (deterministic fallbacks)
when no GROQ_API_KEY secret is configured, so forks and PRs from contributors still get a gate.
  python -m evals.runners.smoke --jobs 30"""
import argparse
import asyncio
import os
import sys

import yaml

from evals.runners import harness as H
from common.db import init_db  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=30)
    a = ap.parse_args()
    if not os.getenv("GROQ_API_KEY"):
        os.environ["LLM_OFFLINE"] = "1"
    from agent.graphs.bid_graph import build_bid_graph
    from evals.runners.decision_eval import analyse
    from langgraph.checkpoint.memory import InMemorySaver

    init_db()
    thr = yaml.safe_load((H.ROOT / "evals" / "thresholds.yaml").read_text(encoding="utf-8"))
    jobs = H.fixed_set(max(1, a.jobs // 3), seed=101)
    tp = fp = fn = 0
    scam_missed = 0
    for p, job in jobs:
        st = await analyse(p, job)
        pred = st["decision"]["action"] == "bid"
        g = job["_gold"]
        tp += pred and g["bid"]
        fp += pred and not g["bid"]
        fn += (not pred) and g["bid"]
        scam_missed += g["scam"] and not st["analyses"]["risk"]["scam"]
    g = build_bid_graph(InMemorySaver())
    unsup = []
    for p, job in H.fixed_set(3, kinds={"strong"}, bid_only=True, seed=101):
        cfg = {"configurable": {"thread_id": job["job_id"]}}
        await g.ainvoke({"user_id": f"persona-{p}", "job_id": job["job_id"], "settings": H.settings(p), "force_bid": True}, cfg)
        v = (await g.aget_state(cfg)).values
        from evals.runners.gigsim_outcomes import residual_unsupported
        from agent.config import config

        ev = {k: x["snippet"] for k, x in (v.get("evidence") or {}).items()}
        d = v.get("draft") or {}
        unsup.append(residual_unsupported(d.get("cover_letter", "") + " " + " ".join(d.get("screening_answers", [])), ev, config()["thresholds"]))
    out = {"jobs": len(jobs), "bid_f1": H.f1(tp, fp, fn), "scams_missed": scam_missed,
           "unsupported_claims_per_proposal_after": H.mean(unsup), "offline": os.getenv("LLM_OFFLINE") == "1", "thresholds": thr}
    H.write("smoke_latest", out)
    fails = []
    if out["bid_f1"] < thr["min_bid_f1"]:
        fails.append(f"bid F1 {out['bid_f1']} < {thr['min_bid_f1']}")
    if out["unsupported_claims_per_proposal_after"] > thr["max_unsupported_claims_per_proposal"]:
        fails.append(f"unsupported claims {out['unsupported_claims_per_proposal_after']} > {thr['max_unsupported_claims_per_proposal']}")
    if scam_missed > thr["max_scams_missed"]:
        fails.append(f"{scam_missed} scams missed")
    print(out)
    if fails:
        print("SMOKE EVAL FAILED:", "; ".join(fails))
        sys.exit(1)
    print("smoke eval passed")


if __name__ == "__main__":
    asyncio.run(main())
