"""Pricing Strategist: share of quotes inside the gold fair-price band, old vs new anchoring rule, all gold-bid jobs.
Writes evals/results/pricing_eval.json (the chosen rule is the one in agent/nodes/pricing.py)."""
from evals.runners import harness as H
from agent.nodes import pricing  # noqa: E402


def old_rule(job, stats, fit, s):
    b = job["budget"]
    if b["type"] == "hourly":
        return s["hourly_rate"] * pricing.LEVEL.get(job.get("experience_level") or "intermediate", 1.0)
    mid = (b["min"] + b["max"]) / 2
    p50 = (stats.get("fixed") or {}).get("p50") or mid
    return max((0.6 * mid + 0.4 * p50), s["min_project"])


def main():
    c, h = H.gigsim_admin()
    tok = {"ai": "gigsim-dev-token-ai", "web": "gigsim-dev-token-web", "data": "gigsim-dev-token-data"}
    stats_cache = {}
    rows = []
    for p in ("ai", "web", "data"):
        for job in H.dev(p):
            g = job["_gold"]
            if not g["bid"]:
                continue
            cat = job["category"]
            if cat not in stats_cache:
                stats_cache[cat] = c.get("/v1/market/stats", params={"category": cat}, headers={"Authorization": f"Bearer {tok[p]}"}).json()
            st = stats_cache[cat]
            s = H.settings(p)
            new = pricing.quote(job, st, 1.0, s, None, job["connects_cost"]).amount
            old = old_rule(job, st, 1.0, s)
            lo, hi = g["fair_band"]
            rows.append({"job_id": job["job_id"], "type": job["budget"]["type"], "old_in": lo <= old <= hi, "new_in": lo <= new <= hi,
                         "old": round(old, 1), "new": new, "band": g["fair_band"]})
    out = {"n": len(rows),
           "old_rule_in_band": H.mean([r["old_in"] for r in rows]), "new_rule_in_band": H.mean([r["new_in"] for r in rows]),
           "by_type": {t: {"n": sum(r["type"] == t for r in rows), "old": H.mean([r["old_in"] for r in rows if r["type"] == t]),
                           "new": H.mean([r["new_in"] for r in rows if r["type"] == t])} for t in ("fixed", "hourly")},
           "rows": rows}
    H.write("pricing_eval", out)
    print({k: v for k, v in out.items() if k != "rows"})


if __name__ == "__main__":
    main()
