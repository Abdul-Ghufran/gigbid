"""Calibrate the skill-graph corrective grader: a requirement is supported when the skill graph links it to a
project, or (no recognised skill) when the best dense match clears a cosine threshold tau.  Picks tau by F1 on dev
gold labels and writes evals/results/grader_calibration_v9.json."""
import asyncio
import json
from pathlib import Path

from evals.runners.rag_eval import load_dev
from rag.corpus import get_corpus
from rag.variants.v9_skill_graph import V9SkillGraph

OUT = Path(__file__).resolve().parents[2] / "evals" / "results"


async def main():
    pts = []
    for p in ("ai", "web", "data"):
        v = V9SkillGraph(get_corpus(p))
        for job in load_dev(p):
            if job["_gold"]["scam"]:
                continue
            for req in job["_gold"]["requirements"]:
                sents = [s for s in job["description"].split(". ") if req["skill"].lower() in s.lower()]
                q = sents[0].strip() if sents else f"Experience with {req['skill']}"
                r = await v.retrieve({"title": "", "description": q}, k=3, requirements=[q])
                top = (r.by_requirement.get(q) or [None])[0]
                pts.append({"label": bool(req["acceptable_items"]), "graph": bool(top and "graph" in top.signals),
                            "cos": top.signals.get("cos", 0) if top else 0})
    best = None
    for t100 in range(30, 95):
        t = t100 / 100
        pred = [x["graph"] or x["cos"] >= t for x in pts]
        tp = sum(1 for x, y in zip(pts, pred, strict=True) if x["label"] and y)
        fp = sum(1 for x, y in zip(pts, pred, strict=True) if not x["label"] and y)
        fn = sum(1 for x, y in zip(pts, pred, strict=True) if x["label"] and not y)
        f1 = 2 * tp / max(1, 2 * tp + fp + fn)
        if not best or f1 > best["f1"]:
            best = {"cos_threshold": t, "f1": round(f1, 4), "precision": round(tp / max(1, tp + fp), 4),
                    "recall": round(tp / max(1, tp + fn), 4), "tp": tp, "fp": fp, "fn": fn}
    out = {"generated_by": "evals/runners/calibrate_grader_v9.py", "n_requirements": len(pts),
           "graph_hits": sum(x["graph"] for x in pts), "best": best}
    (OUT / "grader_calibration_v9.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
