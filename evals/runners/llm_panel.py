"""Blind pairwise LLM proxy panel on the human-panel pairs (B4 stand-in; NOT a human panel).

The classmates' panel could not be run, so the same 15 blind pairs (V0 vs shipped, sides randomised, key in
human_panel_key.json) are judged by three open-weight models acting as the client.  Each model sees every pair twice,
in both A/B orders; a model's vote on a pair counts only when it picks the same proposal in both orders (otherwise the
pair is a position-biased "tie" for that model).  Caveat reported with the result: the proposals were written by
gpt-oss models, so the gpt-oss raters may prefer their own family's style; Qwen is the out-of-family rater.

  python -m evals.runners.llm_panel        -> evals/results/llm_panel.json
"""
from __future__ import annotations

import asyncio
import csv
import json
import re

from scipy import stats

from agent.config import config
from agent.llm import _call
from evals.runners import harness as H

RATERS = ["strong", "mid", "qwen"]  # gpt-oss-120b, gpt-oss-20b, qwen3 (model aliases from agent/config.yaml)
SYSTEM = ("You are the client who posted this job on a freelance marketplace. Two freelancers sent proposals. "
          "Decide which one you would reply to. Judge only what helps you as the client: does it address your actual "
          "need, is the evidence relevant and believable, is there a clear plan and next step. Ignore length as such. "
          'Answer with JSON only: {"choice": "A" or "B", "reason": "<one sentence>"}')


def _user(job_title, job_desc, first, second):
    return (f"JOB: {job_title}\n{job_desc}\n\n=== PROPOSAL A ===\n{first}\n\n=== PROPOSAL B ===\n{second}\n\n"
            "Which proposal would you reply to? JSON only.")


async def _ask(alias, row, flipped):
    spec = {"alias": alias, **config()["models"][alias]}
    a, b = (row["proposal_B"], row["proposal_A"]) if flipped else (row["proposal_A"], row["proposal_B"])
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _user(row["job_title"], row["job_description"], a, b)}]
    for _ in range(3):
        try:
            out = await _call(spec, msgs, alias != "qwen", f"panel_{alias}", 400)
            m = re.search(r'"choice"\s*:\s*"?([AB])', out) or re.search(r"\b([AB])\b", out)
            if m:
                c = m.group(1)
                reason = (re.search(r'"reason"\s*:\s*"([^"]*)', out) or [None, ""])[1]
                return ({"A": "B", "B": "A"}[c] if flipped else c), reason  # map back to the sheet's A/B
        except Exception as e:  # noqa: BLE001
            reason = f"{type(e).__name__}"
            await asyncio.sleep(5)
    return None, "no answer"


async def run():
    rows = list(csv.DictReader(open(H.DS / "human_panel_pairs.csv", encoding="utf-8-sig")))
    key = json.loads((H.DS / "human_panel_key.json").read_text(encoding="utf-8"))
    detail, per_rater = [], {}
    for alias in RATERS:
        model = config()["models"][alias]["model"]
        wins = consistent = 0
        for r in rows:
            c1, why1 = await _ask(alias, r, False)
            c2, why2 = await _ask(alias, r, True)
            ok = c1 is not None and c1 == c2
            picked = key[r["pair"]][c1] if ok else None
            consistent += ok
            wins += picked == "shipped"
            detail.append({"pair": r["pair"], "rater": model, "order_AB": c1, "order_BA": c2, "consistent": ok,
                           "picked": picked, "reason": why1})
            print(alias, r["pair"], c1, c2, picked)
        per_rater[model] = {"consistent_pairs": consistent, "shipped_wins": wins,
                            "shipped_win_rate": round(wins / consistent, 4) if consistent else None}
    votes = [d for d in detail if d["consistent"]]
    w = sum(d["picked"] == "shipped" for d in votes)
    n = len(votes)
    p = stats.binomtest(w, n, 0.5).pvalue if n else None
    # majority vote per pair across the three raters (ties / inconsistent -> no majority)
    maj = {}
    for pair in {d["pair"] for d in detail}:
        ps = [d["picked"] for d in votes if d["pair"] == pair]
        s, v = ps.count("shipped"), ps.count("v0")
        maj[pair] = "shipped" if s > v else "v0" if v > s else None
    out = {"kind": "LLM proxy panel (not human)", "pairs": len(rows), "raters": len(RATERS),
           "rater_models": list(per_rater), "votes": n, "position_inconsistent": len(detail) - n,
           "shipped_win_rate": round(w / n, 4) if n else None, "binomial_p": round(float(p), 4) if p is not None else None,
           "majority_shipped": sum(v == "shipped" for v in maj.values()), "majority_v0": sum(v == "v0" for v in maj.values()),
           "majority_none": sum(v is None for v in maj.values()), "per_rater": per_rater,
           "caveat": "Proposals were written by gpt-oss models; gpt-oss raters may share that style. Qwen is the out-of-family rater.",
           "detail": detail}
    H.write("llm_panel", out)
    print({k: v for k, v in out.items() if k != "detail"})


if __name__ == "__main__":
    asyncio.run(run())
