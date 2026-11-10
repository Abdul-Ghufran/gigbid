"""Why did better retrieval NOT give a better GigSim reply rate?  Re-score both fixed-writer proposal sets and compare
the simulated client's features (must-have skill coverage, personalisation, specificity, length).
Writes evals/results/reply_gap_analysis.json."""
import json

from evals.runners import harness as H


def load(tag):
    return [r for r in json.load(open(H.RESULTS / f"proposals_{tag}.json", encoding="utf-8"))["rows"] if "error" not in r]


def main():
    jobs = {j["job_id"]: (p, j) for p in ("ai", "web", "data") for j in H.dev(p)}
    out = {}
    for tag in ("best_fixedwriter", "v0_fixedwriter"):
        feats = []
        for r in load(tag):
            p, job = jobs[r["job_id"]]
            f = H.client_reaction(job["job_id"], p, r["proposal"], r["answers"], job["budget"]["max"] * 0.9, job["budget"]["type"])["features"]
            cited = sorted(set(__import__("re").findall(r"\[([a-z]+-[a-z0-9-]+)\]", r["proposal"])))
            feats.append({"must_cov": f["must_cov"], "personal": f["personal"], "specific": f["specific"], "words": f["words"],
                          "cites_cv": any(c.endswith("-cv") for c in cited), "n_cited": len(cited),
                          "unsupported_before": r["unsupported_before"], "replied": r["replied"]})
        out[tag] = {"n": len(feats), **{k: H.mean([x[k] for x in feats]) for k in ("must_cov", "personal", "specific", "words", "cites_cv",
                                                                                      "n_cited", "unsupported_before", "replied")}}
    out["explanation"] = ("GigSim's simulated client rewards proposals that NAME the client's must-have skills.  V0 retrieves the "
                          "CV and loosely related items for every requirement, so the template letter names more required skills "
                          "(higher must_cov) even when the evidence for them is weak - which is also why it produces more "
                          "unsupported claims before verification.  The shipped corrective pipeline refuses to claim requirements "
                          "it cannot prove, so letters are more honest but mention fewer must-haves.  The simulator measures "
                          "keyword coverage, not truth: a client who checked the claims would penalise V0.")
    H.write("reply_gap_analysis", out)
    print(json.dumps(out, indent=1)[:1500])


if __name__ == "__main__":
    main()
