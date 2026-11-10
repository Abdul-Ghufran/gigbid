"""Sweep the bid fit threshold on stored dev-set decisions (evals/results/decision_eval_offline.json).
A job counts as 'bid' at threshold t when it passed risk and budget rules (pred bid/watch) and fit >= t."""
import json

from evals.runners import harness as H

d = json.load(open(H.RESULTS / "decision_eval_offline.json", encoding="utf-8"))
rows = d["rows"]
out = []
for t in [0.5, 0.55, 0.6, 0.65, 0.67, 0.7, 0.75, 0.8]:
    pred = [(r["pred"] in ("bid", "watch")) and r["fit"] >= t for r in rows]
    tp = sum(p and r["gold_bid"] for p, r in zip(pred, rows))
    fp = sum(p and not r["gold_bid"] for p, r in zip(pred, rows))
    fn = sum((not p) and r["gold_bid"] for p, r in zip(pred, rows))
    part = [(p, r) for p, r in zip(pred, rows) if r["kind"] == "partial"]
    out.append({"threshold": t, "bid_f1": H.f1(tp, fp, fn), "precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / max(1, tp + fn), 4),
                "partial_accuracy": round(sum(p == r["gold_bid"] for p, r in part) / len(part), 4)})
    print(out[-1])
H.write("threshold_sweep", {"source": "evals/results/decision_eval_offline.json", "sweep": out})
