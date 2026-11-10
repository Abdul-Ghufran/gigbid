"""Retrieval evaluation: evidence Recall@5, MRR and nDCG@10 per variant, persona and job type.

  python -m evals.runners.rag_eval --variants v0_naive,v1_decompose,... [--limit 60] [--out rag_variants]

Definitions (also in docs/DATA_CARD.md):
  Recall@5  fraction of a job's coverable requirements (requirements the persona truly has evidence for)
            for which at least one acceptable gold item appears in the top-5 retrieved items.
  MRR       1 / rank of the first retrieved item that demonstrates any required skill (top 10).
  nDCG@10   graded relevance = number of the job's required skills the item demonstrates.
Only non-scam jobs with at least one coverable requirement are scored.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path

from rag.corpus import get_corpus
from rag.retriever import VARIANTS

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "evals" / "datasets"
OUT = ROOT / "evals" / "results"


def load_dev(persona: str, limit: int | None = None, kinds: set[str] | None = None) -> list[dict]:
    rows = [json.loads(line) for line in open(DS / f"dev_{persona}.jsonl", encoding="utf-8")]
    if kinds:
        rows = [r for r in rows if r["_gold"]["kind"] in kinds]
    return rows[:limit] if limit else rows


def scoreable(job: dict) -> bool:
    g = job["_gold"]
    return not g["scam"] and any(r["acceptable_items"] for r in g["requirements"])


def metrics(ranked: list[str], gold: dict) -> dict:
    reqs = [r for r in gold["requirements"] if r["acceptable_items"]]
    top5 = set(ranked[:5])
    recall = sum(bool(top5 & set(r["acceptable_items"])) for r in reqs) / len(reqs)
    rel = gold["relevance"]
    mrr = next((1 / (i + 1) for i, iid in enumerate(ranked[:10]) if rel.get(iid, 0) > 0), 0.0)
    dcg = sum((2 ** rel.get(iid, 0) - 1) / math.log2(i + 2) for i, iid in enumerate(ranked[:10]))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return {"recall@5": recall, "mrr": mrr, "ndcg@10": dcg / idcg if idcg else 0.0}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else 0.0


async def eval_variant(name: str, personas: list[str], limit: int | None, opts: dict | None = None) -> dict:
    rows, lat = [], []
    if name == "v8_corrective" and opts is None:
        from agent.config import config

        opts = dict(config()["rag"]["corrective"])
    for p in personas:
        v = VARIANTS[name](get_corpus(p), **(opts or {}))
        for job in load_dev(p, limit):
            if not scoreable(job):
                continue
            t0 = time.perf_counter()
            res = await v.retrieve(job, k=10)
            lat.append(time.perf_counter() - t0)
            m = metrics(res.item_ids(10), job["_gold"])
            rows.append({"persona": p, "kind": job["_gold"]["kind"], "n_req": job["_gold"]["n_requirements"],
                         "job_id": job["job_id"], **m})

    def agg(rs):
        return {k: round(statistics.mean(r[k] for r in rs), 4) for k in ("recall@5", "mrr", "ndcg@10")} | {"n": len(rs)} if rs else {}

    by_p = defaultdict(list)
    by_k = defaultdict(list)
    for r in rows:
        by_p[r["persona"]].append(r)
        by_k[r["kind"]].append(r)
    return {"variant": name, "opts": opts or {}, "overall": agg(rows),
            "by_persona": {k: agg(v) for k, v in by_p.items()}, "by_kind": {k: agg(v) for k, v in by_k.items()},
            "many_requirements(>=4)": agg([r for r in rows if r["n_req"] >= 4]),
            "latency_s": {"p50": round(pct(lat, 0.5), 4), "p95": round(pct(lat, 0.95), 4)}, "rows": rows}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="v0_naive,v1_decompose,v2_hybrid,v3_rerank,v4_outcome,v5_multivector,v6_contextual,v8_corrective,v9_skill_graph")
    ap.add_argument("--personas", default="ai,web,data")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="rag_variants")
    a = ap.parse_args()
    results = []
    for name in a.variants.split(","):
        t = time.time()
        r = await eval_variant(name, a.personas.split(","), a.limit)
        print(f"{name:16s} R@5={r['overall'].get('recall@5')} MRR={r['overall'].get('mrr')} nDCG={r['overall'].get('ndcg@10')} "
              f"R@5(>=4req)={r['many_requirements(>=4)'].get('recall@5')} p95={r['latency_s']['p95']}s ({time.time() - t:.0f}s)", flush=True)
        results.append(r)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.out}.json").write_text(json.dumps({"generated_by": "evals/runners/rag_eval.py", "args": vars(a),
                                                   "results": results}, indent=1), encoding="utf-8")
    with open(OUT / f"{a.out}.csv", "w", encoding="utf-8") as f:
        f.write("variant,recall@5,mrr,ndcg@10,recall@5_many_req,p95_latency_s,n\n")
        for r in results:
            o = r["overall"]
            f.write(f"{r['variant']},{o['recall@5']},{o['mrr']},{o['ndcg@10']},{r['many_requirements(>=4)'].get('recall@5')},"
                    f"{r['latency_s']['p95']},{o['n']}\n")


if __name__ == "__main__":
    asyncio.run(main())
