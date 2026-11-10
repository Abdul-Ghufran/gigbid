"""Does better retrieval change GigSim outcomes?  Paired by job (same 90 jobs, same deterministic writer v3,
only the retrieval pipeline differs): McNemar exact tests on reply / interview / hire, paired t-test on client score,
and a Wilcoxon test on unsupported claims.  Writes evals/results/retrieval_outcome_test.json."""
import json

from scipy import stats

from evals.runners import harness as H


def rows(tag):
    return {r["job_id"]: r for r in json.load(open(H.RESULTS / f"proposals_{tag}.json", encoding="utf-8"))["rows"] if "error" not in r}


def mcnemar(a, b):
    b01 = sum((not x) and y for x, y in zip(a, b, strict=True))
    b10 = sum(x and not y for x, y in zip(a, b, strict=True))
    p = stats.binomtest(min(b01, b10), b01 + b10, 0.5).pvalue if b01 + b10 else 1.0
    return {"only_v0": b01, "only_shipped": b10, "p": round(float(p), 4)}


def main(tag_best="best_fixedwriter_v3", tag_v0="v0_fixedwriter_v3"):
    best, v0 = rows(tag_best), rows(tag_v0)
    ids = sorted(set(best) & set(v0))
    out = {"n_jobs": len(ids), "sets": [tag_best, tag_v0]}
    for m in ("replied", "interview", "hired"):
        a, b = [best[i][m] for i in ids], [v0[i][m] for i in ids]
        out[m] = {"shipped": H.mean(a), "v0": H.mean(b), "mcnemar": mcnemar(a, b)}
    sa, sb = [best[i]["client_score"] for i in ids], [v0[i]["client_score"] for i in ids]
    t = stats.ttest_rel(sa, sb)
    out["client_score"] = {"shipped": H.mean(sa), "v0": H.mean(sb), "paired_t": round(float(t.statistic), 3), "p": round(float(t.pvalue), 4)}
    ua, ub = [best[i]["unsupported_before"] for i in ids], [v0[i]["unsupported_before"] for i in ids]
    w = stats.wilcoxon(ua, ub) if any(x != y for x, y in zip(ua, ub, strict=True)) else None
    out["unsupported_before"] = {"shipped": H.mean(ua), "v0": H.mean(ub), "wilcoxon_p": round(float(w.pvalue), 6) if w else None}
    H.write("retrieval_outcome_test", out)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
