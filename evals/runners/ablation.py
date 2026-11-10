"""Ablate the shipped retrieval pipeline (V8 corrective loop over the V9 skill graph) one component at a time.
Writes evals/results/rag_ablation.json."""
import asyncio
import json
from pathlib import Path

from evals.runners.rag_eval import eval_variant

OUT = Path(__file__).resolve().parents[2] / "evals" / "results"
RUNS = [
    ("full: corrective loop + skill graph", "v8_corrective", None),
    ("- corrective loop (plain V9)", "v9_skill_graph", {}),
    ("- skill graph (dense per requirement)", "v9_skill_graph", {"graph": False}),
    ("- requirement decomposition", "v9_skill_graph", {"decompose": False}),
    ("- dense fallback for unrecognised skills", "v9_skill_graph", {"dense_fallback": False}),
    ("- industry / outcome boosts", "v9_skill_graph", {"boosts": False}),
]


async def main():
    out = []
    for label, name, opts in RUNS:
        r = await eval_variant(name, ["ai", "web", "data"], None, opts)
        row = {"config": label, "variant": name, "opts": opts, **r["overall"], "recall@5_many_req": r["many_requirements(>=4)"].get("recall@5"),
               "by_persona": r["by_persona"], "by_kind": r["by_kind"], "p95_latency_s": r["latency_s"]["p95"]}
        print(f"{label:45s} R@5={row['recall@5']} MRR={row['mrr']} nDCG={row['ndcg@10']}", flush=True)
        out.append(row)
    (OUT / "rag_ablation.json").write_text(json.dumps({"generated_by": "evals/runners/ablation.py", "results": out}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
