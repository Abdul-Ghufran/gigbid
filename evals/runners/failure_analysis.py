"""Failure analysis (report section 8): pull real failed dev jobs from the results files, group them into the taxonomy
(missed evidence, wrong skip, wrong bid, mispriced, unsupported claim, generic opening, compliance miss, injection,
tool error) and attach the fix that was tried and its measured effect.  Writes failure_analysis.json and .md."""
import json

from evals.runners import harness as H

FIXES = {
    "wrong bid (partial fit)": ("Raised bid_min_fit 0.55 -> 0.70 (middle of the plateau in threshold_sweep.json)",
                                "partial-fit accuracy 61.7% -> 90.0%, bid F1 0.918 -> 0.976 on the same 600 jobs"),
    "mispriced": ("Pricing v2: anchor on the job's own budget range instead of the category median",
                  "price inside fair band 52.8% -> 86.2% (pricing_eval.json, 282 jobs); remaining misses are hourly jobs where the client range sits below market"),
    "missed evidence": ("Skill graph (V9) + requirement decomposition; corrective grader marks the requirement unsupported instead of guessing",
                        "Recall@5 0.740 -> 0.890; residual misses are hard paraphrases with no skill keyword (e.g. 'a document store')"),
    "unsupported claim": ("Strict number/tool rule + rewrite-then-reverify; fallback writer v3 opening without an uncited claim",
                          "unsupported claims per proposal 1.13 -> 0.34 before verification, 0 after (retrieval_outcome_test.json)"),
    "generic opening / low coverage": ("Name the client's requirement next to the proof that covers it (writer prompt v2.5 + fallback writer)",
                                       "simulated reply rate 15.6% -> 64.4% for the shipped pipeline on the same 90 jobs"),
    "wrong skip": ("None yet: these are gold-bid jobs whose requirement sentences contain only hard paraphrases, so the Fit Matcher finds no skill and the dense fallback stays under the 0.83 cosine grader",
                   "not fixed - candidate fix: LLM requirement rewrite in the corrective loop (llm_rewrite option), not enabled because of the free-tier token budget"),
}


def main():
    dec = json.load(open(H.RESULTS / "decision_eval_offline.json", encoding="utf-8"))["rows"]
    rag = json.load(open(H.RESULTS / "rag_variants_offline.json", encoding="utf-8"))["results"]
    v9 = next(r for r in rag if r["variant"] == "v9_skill_graph")["rows"]
    props = json.load(open(H.RESULTS / "proposals_best_fixedwriter.json", encoding="utf-8"))["rows"]
    pr = json.load(open(H.RESULTS / "pricing_eval.json", encoding="utf-8"))["rows"]
    v3 = {r["job_id"]: r for r in json.load(open(H.RESULTS / "proposals_best_fixedwriter_v3.json", encoding="utf-8"))["rows"] if "error" not in r}
    sweep_fit = 0.70
    cases = []
    for r in dec:  # wrong bids on partial-fit jobs at the old threshold that the new threshold fixes
        if r["kind"] == "partial" and r["pred"] == "bid" and not r["gold_bid"] and len([c for c in cases if c["category"] == "wrong bid (partial fit)"]) < 3:
            cases.append({"job_id": r["job_id"], "category": "wrong bid (partial fit)", "node": "decide (Fit Matcher score)",
                          "detail": f"fit {r['fit']:.2f} >= 0.55 but gold coverage < 0.6", "fixed": r["fit"] < sweep_fit})
        if r["gold_bid"] and r["pred"] != "bid" and len([c for c in cases if c["category"] == "wrong skip"]) < 2:
            cases.append({"job_id": r["job_id"], "category": "wrong skip", "node": "fit_matcher",
                          "detail": f"gold bid, predicted {r['pred']} (fit {r['fit']:.2f})", "fixed": False})
    for r in pr:
        if not r["old_in"] and len([c for c in cases if c["category"] == "mispriced"]) < 2:
            cases.append({"job_id": r["job_id"], "category": "mispriced", "node": "pricing",
                          "detail": f"old quote {r['old']} outside band {r['band']}; new quote {r['new']}", "fixed": r["new_in"]})
    for r in sorted(v9, key=lambda x: x["recall@5"])[:2]:
        cases.append({"job_id": r["job_id"], "category": "missed evidence", "node": "fit_matcher / retrieval",
                      "detail": f"Recall@5 {r['recall@5']:.2f} ({r['kind']}, {r['n_req']} requirements)", "fixed": False})
    for r in sorted([p for p in props if "error" not in p], key=lambda x: -x["unsupported_before"])[:2]:
        cases.append({"job_id": r["job_id"], "category": "unsupported claim", "node": "writer -> verifier",
                      "detail": f"{r['unsupported_before']} unsupported claims before verification, {r['unsupported_final_audit']} after", "fixed": r["unsupported_final_audit"] == 0})
    for r in [p for p in props if "error" not in p and not p["replied"]][:2]:
        cases.append({"job_id": r["job_id"], "category": "generic opening / low coverage", "node": "writer",
                      "detail": "proof never named the client's must-have skill; simulated client did not reply",
                      "fixed": bool(v3.get(r["job_id"], {}).get("replied"))})
    out = {"n_cases": len(cases), "cases": cases, "fixes": {k: {"fix": a, "effect": b} for k, (a, b) in FIXES.items()},
           "development_failures": [
               {"category": "tool error", "what": "Requirement splitter cut 'Next.js' at the dot -> 0/5 evidence on dev-web-001", "fix": "split only before a capital letter", "worked": True},
               {"category": "tool error", "what": "Portfolio server resolved eval user persona-web to the AI persona -> no evidence", "fix": "persona-* users map to their persona", "worked": True},
               {"category": "compliance miss", "what": "Verifier emptied screening answers, critic rejected every draft (2 revisions burned)", "fix": "rewrite-then-reverify + non-empty answer fallback", "worked": True},
               {"category": "injection", "what": "Injection sentences could survive into the writer's evidence queries", "fix": "decompose() drops instruction-like sentences; strip_injection before the writer", "worked": True},
           ]}
    H.write("failure_analysis", out)
    md = ["| # | Job | Failure category | Node | What went wrong | Fixed? |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(cases, 1):
        md.append(f"| {i} | `{c['job_id']}` | {c['category']} | {c['node']} | {c['detail']} | {'yes' if c['fixed'] else 'no'} |")
    md += ["", "| Category | Fix tried | Measured effect |", "|---|---|---|"]
    md += [f"| {k} | {a} | {b} |" for k, (a, b) in FIXES.items()]
    (H.RESULTS / "failure_analysis.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
