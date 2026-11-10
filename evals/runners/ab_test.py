"""Signature extension X2: proposal A/B experiment in GigSim with a significance test.

Paired design: for every drafted job the SAME facts are written in two structures (proof_first vs plan_first, see
agent/config.yaml experiments.strategies) and both are scored by GigSim's simulated client (admin scoring endpoint,
no Connects).  Reply outcomes are compared with McNemar's exact test on discordant pairs, and mean client score with
a paired t-test.  Source proposals: evals/results/proposals_best_fixedwriter.json (and live-model proposals if present).
"""
import json
import re

from scipy import stats

from evals.runners import harness as H


def arms(text: str) -> tuple[str, str] | None:
    """Same sentences, two structures.  proof_first: opening, cited proof, approach, next step.
    plan_first: opening, approach, cited proof, next step."""
    sents = [x for x in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()) if x]
    if len(sents) < 4:
        return None
    opening, nxt = sents[0], sents[-1]
    proof = [x for x in sents[1:-1] if "[" in x]
    plan = [x for x in sents[1:-1] if "[" not in x]
    if not proof or not plan:
        return None
    a = "\n\n".join([opening, " ".join(proof), " ".join(plan) + " " + nxt])
    b = "\n\n".join([opening, " ".join(plan), " ".join(proof) + " " + nxt])
    return a, b


def main():
    src = json.load(open(H.RESULTS / "proposals_best_fixedwriter.json", encoding="utf-8"))["rows"]
    pairs = []
    jobs = {j["job_id"]: (p, j) for p in ("ai", "web", "data") for j in H.dev(p)}
    for r in src:
        if "error" in r:
            continue
        p, job = jobs[r["job_id"]]
        pair = arms(r["proposal"])
        if not pair:
            continue
        a_text, b_text = pair
        bid = job["budget"]["max"] * 0.9
        a = H.client_reaction(job["job_id"], p, a_text, r["answers"], bid, job["budget"]["type"])
        b = H.client_reaction(job["job_id"], p, b_text, r["answers"], bid, job["budget"]["type"])
        pairs.append({"job_id": job["job_id"], "persona": p, "a_replied": a["replied"], "b_replied": b["replied"],
                      "a_score": a["score"], "b_score": b["score"]})
    n = len(pairs)
    b01 = sum((not x["a_replied"]) and x["b_replied"] for x in pairs)
    b10 = sum(x["a_replied"] and not x["b_replied"] for x in pairs)
    mcnemar_p = stats.binomtest(min(b01, b10), b01 + b10, 0.5).pvalue if b01 + b10 else 1.0
    t = stats.ttest_rel([x["a_score"] for x in pairs], [x["b_score"] for x in pairs]) if n > 1 else None
    out = {"design": "paired, same facts, two structures", "n_pairs": n,
           "arms": {"proof_first": {"reply_rate": H.mean([x["a_replied"] for x in pairs]), "mean_client_score": H.mean([x["a_score"] for x in pairs])},
                    "plan_first": {"reply_rate": H.mean([x["b_replied"] for x in pairs]), "mean_client_score": H.mean([x["b_score"] for x in pairs])}},
           "discordant": {"only_plan_first_replied": b01, "only_proof_first_replied": b10},
           "mcnemar_exact_p": round(float(mcnemar_p), 4),
           "paired_t_on_client_score": {"t": round(float(t.statistic), 3), "p": round(float(t.pvalue), 4)} if t is not None and t.statistic == t.statistic else None,
           "pairs": pairs}
    H.write("ab_test", out)
    print({k: v for k, v in out.items() if k != "pairs"})


if __name__ == "__main__":
    main()
