"""Calibrate the corrective-RAG evidence grader threshold on the dev set.

For every requirement of every scoreable dev job: label = the persona truly has evidence for it (gold);
score = best cross-encoder logit from V3.  Picks the threshold that maximises F1 for "supported" and
writes evals/results/grader_calibration.json (the value is then copied into agent/config.yaml).
"""
import asyncio
import json
from pathlib import Path

from evals.runners.rag_eval import load_dev
from rag.corpus import get_corpus
from rag.ingest.skills import extract_skills
from rag.variants.v3_rerank import V3Rerank

OUT = Path(__file__).resolve().parents[2] / "evals" / "results"


async def main(limit=70):
    pts = []
    for p in ("ai", "web", "data"):
        c = get_corpus(p)
        v = V3Rerank(c)
        for job in load_dev(p, limit):
            if job["_gold"]["scam"]:
                continue
            for req in job["_gold"]["requirements"]:
                # query = the job sentence that mentions this skill (what the system actually sees)
                sents = [s for s in job["description"].split(".") if req["skill"].lower() in s.lower()]
                q = sents[0].strip() if sents else f"Experience with {req['skill']}"
                r = await v.retrieve({"title": "", "description": q}, k=3, requirements=[q])
                hits = r.by_requirement.get(q, [])
                top = hits[0] if hits else None
                ce = top.signals.get("ce", -99) if top else -99
                lex = bool(top and set(extract_skills(q)) & set(c.by_id[top.item_id].skills))
                pts.append({"persona": p, "label": bool(req["acceptable_items"]), "ce": ce, "lex": lex})
    best = None
    for t10 in range(-120, 41):
        t = t10 / 10
        for use_lex in (False, True):
            tp = sum(1 for x in pts if x["label"] and (x["ce"] >= t or (use_lex and x["lex"] and x["ce"] >= t - 4)))
            fp = sum(1 for x in pts if not x["label"] and (x["ce"] >= t or (use_lex and x["lex"] and x["ce"] >= t - 4)))
            fn = sum(1 for x in pts if x["label"]) - tp
            f1 = 2 * tp / max(1, 2 * tp + fp + fn)
            acc = (tp + sum(1 for x in pts if not x["label"]) - fp) / len(pts)
            if not best or f1 > best["f1"]:
                best = {"threshold": t, "lexical_net": use_lex, "f1": round(f1, 4), "accuracy": round(acc, 4), "tp": tp, "fp": fp, "fn": fn}
    out = {"generated_by": "evals/runners/calibrate_grader.py", "n_requirements": len(pts),
           "positives": sum(x["label"] for x in pts), "best": best}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grader_calibration.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
