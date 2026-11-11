"""Build the R&D report: docs/report/REPORT.md with {{name}} placeholders filled from evals/results/*.json,
tables pulled from evals/results/results_tables.md ({{table:Section title prefix}}), rendered to HTML.
PDF: `node apps/web/scripts/render_pdf.mjs` (headless Chromium).  Missing values render as 'pending'."""
import json
import re
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"


def j(name):
    p = RES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def get(d, path, default=None):
    for k in path.split("."):
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d


def pct(x):
    return "pending" if x is None else f"{x * 100:.1f}%"


def num(x, nd=3):
    return "pending" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def values():
    rag = j("rag_variants_offline")
    v = {r["variant"]: r for r in rag.get("results", [])}
    abl = {r["config"].split(":")[0].split(" (")[0]: r for r in j("rag_ablation").get("results", [])}
    full = next((r for k, r in abl.items() if k.startswith("full")), {})
    dec = j("decision_eval_offline")
    sweep = {s["threshold"]: s for s in j("threshold_sweep").get("sweep", [])}
    ver, ver1 = j("verifier_eval"), j("verifier_eval_v1_rule")
    rot = j("retrieval_outcome_test")
    cr = j("change_request_eval")
    a = j("rq_a_tools").get("results", {})
    c = j("rq_c_architectures").get("results", {})
    inj = j("injection_eval")
    ab = j("ab_test")
    pr = j("pricing_eval")
    live = get(j("proposals_best_live"), "summary", {}) or {}
    prof = j("model_profiles").get("profiles", {})
    kap = j("judge_calibration")
    gap = j("reply_gap_analysis")
    def arg(metric, best=max):
        vals = {k: r.get(metric) for k, r in c.items() if isinstance(r.get(metric), (int, float))}
        return best(vals, key=vals.get) if vals else "pending"

    out = {
        "c_best_acc_arch": arg("bid_skip_accuracy"), "c_fewest_tokens_arch": arg("mean_tokens", min),
        "c_fastest_arch": arg("p95_latency_s", min), "c_fewest_unsup_arch": arg("unsupported_claims_per_letter", min),
        "c_react_tok": num(get(c, "react.mean_tokens"), 0), "c_graph_tok": num(get(c, "graph.mean_tokens"), 0),
        "c_sup_tok": num(get(c, "supervisor.mean_tokens"), 0),
        "c_react_viol": str(get(c, "react.letters_with_violations", "pending")), "c_graph_viol": str(get(c, "graph.letters_with_violations", "pending")),
        "c_react_rej": str(get(c, "react.rejected_tool_calls", "pending")), "c_sup_rej": str(get(c, "supervisor.rejected_tool_calls", "pending")),
        "v0_r5":num(get(v, "v0_naive.overall.recall@5")), "v0_mrr": num(get(v, "v0_naive.overall.mrr")), "v0_ndcg": num(get(v, "v0_naive.overall.ndcg@10")),
        "v0_r5_many": num(get(v, "v0_naive.many_requirements(>=4).recall@5")),
        "v1_r5": num(get(v, "v1_decompose.overall.recall@5")), "v2_r5": num(get(v, "v2_hybrid.overall.recall@5")),
        "v3_r5": num(get(v, "v3_rerank.overall.recall@5")), "v3_p95": num(get(v, "v3_rerank.latency_s.p95"), 2),
        "v3_r5_many": num(get(v, "v3_rerank.many_requirements(>=4).recall@5")),
        "v4_r5": num(get(v, "v4_outcome.overall.recall@5")), "v5_r5": num(get(v, "v5_multivector.overall.recall@5")),
        "v6_r5": num(get(v, "v6_contextual.overall.recall@5")), "v9_r5": num(get(v, "v9_skill_graph.overall.recall@5")),
        "v9_r5_many": num(get(v, "v9_skill_graph.many_requirements(>=4).recall@5")),
        "full_r5": num(full.get("recall@5")), "full_mrr": num(full.get("mrr")), "full_ndcg": num(full.get("ndcg@10")),
        "n_rag_jobs": str(get(v, "v0_naive.overall.n", "pending")),
        "bid_f1_055": num(get(sweep, "0.55.bid_f1") if 0.55 in sweep else None), "bid_f1_070": num(sweep.get(0.7, {}).get("bid_f1")),
        "partial_acc_055": pct(sweep.get(0.55, {}).get("partial_accuracy")), "partial_acc_070": pct(sweep.get(0.7, {}).get("partial_accuracy")),
        "scam_p": num(get(dec, "overall.scam_precision")), "scam_r": num(get(dec, "overall.scam_recall")),
        "inj_detect": pct(get(dec, "overall.injection_detected")), "price_band": pct(get(dec, "overall.price_in_fair_band")),
        "price_old": pct(pr.get("old_rule_in_band")), "price_new": pct(pr.get("new_rule_in_band")), "price_n": str(pr.get("n", "pending")),
        "ver_f1_v1": num(get(ver1, "modes.cross_encoder.f1")), "ver_f1": num(get(ver, "modes.bi_encoder.f1")),
        "ver_n": str(ver.get("n_claims", "pending")),
        "unsup_best": num(get(rot, "unsupported_before.shipped"), 2), "unsup_v0": num(get(rot, "unsupported_before.v0"), 2),
        "score_best": num(get(rot, "client_score.shipped"), 2), "score_v0": num(get(rot, "client_score.v0"), 2), "score_p": num(get(rot, "client_score.p"), 4),
        "reply_best": pct(get(rot, "replied.shipped")), "reply_v0": pct(get(rot, "replied.v0")), "reply_p": num(get(rot, "replied.mcnemar.p"), 2),
        "int_best": pct(get(rot, "interview.shipped")), "int_v0": pct(get(rot, "interview.v0")), "int_p": num(get(rot, "interview.mcnemar.p"), 2),
        "gap_must_v0": num(get(gap, "v0_fixedwriter.must_cov"), 2), "gap_must_best": num(get(gap, "best_fixedwriter.must_cov"), 2),
        "gap_reply_v0": pct(get(gap, "v0_fixedwriter.replied")), "gap_reply_best": pct(get(gap, "best_fixedwriter.replied")),
        "cr_err_before": pct(get(cr, "before_change (config 2026-10-27).connects_prediction_error_rate")),
        "cr_err_after": pct(get(cr, "after_change (config 2026-11-02).connects_prediction_error_rate")),
        "cr_rej_before": str(get(cr, "before_change (config 2026-10-27).rejected_by_marketplace", "pending")),
        "cr_caught_after": str(get(cr, "after_change (config 2026-11-02).blank_answers_caught_before_submit", "pending")),
        "a_fine_sel": pct(get(a, "fine.tool_selection_accuracy")), "a_coarse_sel": pct(get(a, "coarse.tool_selection_accuracy")),
        "a_best_sel": pct(get(a, "best.tool_selection_accuracy")), "a_fine_arg": pct(get(a, "fine.argument_accuracy")),
        "a_coarse_arg": pct(get(a, "coarse.argument_accuracy")), "a_best_arg": pct(get(a, "best.argument_accuracy")),
        "a_fine_tok": num(get(a, "fine.tokens_per_task"), 0), "a_coarse_tok": num(get(a, "coarse.tokens_per_task"), 0), "a_best_tok": num(get(a, "best.tokens_per_task"), 0),
        "c_react_acc": num(get(c, "react.bid_skip_accuracy")), "c_sup_acc": num(get(c, "supervisor.bid_skip_accuracy")), "c_graph_acc": num(get(c, "graph.bid_skip_accuracy")),
        "c_jobs": (lambda rc: (f"{min(rc.values())}–{max(rc.values())}" if len(set(rc.values())) > 1 else str(min(rc.values())))
                   if rc else str(j("rq_c_architectures").get("jobs", "pending")))(j("rq_c_architectures").get("rows_completed") or {}), "c_model": str(j("rq_c_architectures").get("model", "pending")),
        "inj_n": str(inj.get("n_attacks", "pending")), "inj_before": pct(inj.get("attack_success_rate_undefended")),
        "inj_after": pct(inj.get("attack_success_rate_defended_shipped")), "inj_model_out": pct(inj.get("attack_success_rate_defended_model_output")),
        "inj_fp": pct(inj.get("detector_false_positive_rate_on_clean_posts")),
        "ab_n": str(ab.get("n_pairs", "pending")), "ab_a": pct(get(ab, "arms.proof_first.reply_rate")), "ab_b": pct(get(ab, "arms.plan_first.reply_rate")),
        "ab_p": num(ab.get("mcnemar_exact_p"), 2),
        "live_n": str(live.get("n_drafted", "pending")), "live_p95": num(live.get("p95_latency_s"), 1), "live_p50": num(live.get("p50_latency_s"), 1),
        "live_cost": num(live.get("mean_cost_usd_per_proposal"), 4), "live_tokens": num(live.get("mean_tokens_per_proposal"), 0),
        "live_unsup_before": num(live.get("unsupported_per_proposal_before"), 2), "live_unsup_after": num(live.get("unsupported_per_proposal_after"), 2),
        "live_reply": pct(live.get("gigsim_reply_rate")),
        "dec_p95": num(get(dec, "overall.p95_latency_s"), 1),
        "kappa": num(kap.get("cohen_kappa"), 2), "wkappa": num(kap.get("quadratic_weighted_kappa"), 2), "kappa_n": str(kap.get("n_labelled", "pending")),
        "panel_win": pct(j("human_panel").get("shipped_win_rate")), "panel_n": str(j("human_panel").get("votes", "pending")),
        "panel_raters": str(j("human_panel").get("raters", "pending")), "panel_p": num(j("human_panel").get("binomial_p"), 3),
        "prof_open_cost":num(get(prof, "open.mean_cost_usd_per_proposal"), 5), "prof_mid_cost": num(get(prof, "open_mid.mean_cost_usd_per_proposal"), 5),
    }
    return out


def tables():
    t = (RES / "results_tables.md").read_text(encoding="utf-8") if (RES / "results_tables.md").exists() else ""
    return {s.split("\n", 1)[0]: s.split("\n", 1)[1] if "\n" in s else "" for s in re.split(r"(?m)^## ", t)[1:]}


def main():
    subprocess.run([sys.executable, "-m", "evals.runners.results_table"], cwd=ROOT, check=True, capture_output=True)
    src = (ROOT / "docs" / "report" / "REPORT.md").read_text(encoding="utf-8")
    vals, tabs = values(), tables()

    def sub(m):
        key = m.group(1).strip()
        if key == "failures":
            p = RES / "failure_analysis.md"
            return p.read_text(encoding="utf-8") if p.exists() else "_pending_"
        if key.startswith("table:"):
            pref = key[6:].strip()
            return next((body for title, body in tabs.items() if title.startswith(pref)), "_pending_")
        return vals.get(key, f"[{key}?]")

    filled = re.sub(r"\{\{([^}]+)\}\}", sub, src)
    (ROOT / "docs" / "report" / "REPORT.filled.md").write_text(filled, encoding="utf-8")
    html = markdown.markdown(filled, extensions=["tables", "fenced_code", "toc"])
    css = (ROOT / "docs" / "report" / "report.css").read_text(encoding="utf-8")
    (ROOT / "docs" / "report" / "report.html").write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>GigBid R&D report</title><style>{css}</style></head><body>{html}</body></html>",
        encoding="utf-8")
    missing = sorted(set(re.findall(r"\[([a-z0-9_]+)\?\]", filled)))
    print("report.html written; unknown placeholders:", missing, "; pending values:", filled.count("pending"))


if __name__ == "__main__":
    main()
