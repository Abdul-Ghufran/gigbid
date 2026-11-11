"""LLM judge + calibration against my own labels (B4).

  python -m evals.runners.judge_calibration --make-sheets   # 30-item labelling sheet + 15-pair human panel sheet
  python -m evals.runners.judge_calibration --judge         # LLM judge scores the 30 items and both proposal sets
  python -m evals.runners.judge_calibration --kappa         # Cohen's kappa (plain + quadratic-weighted) human vs judge

The labelling sheet is anonymised (no variant names); the key stays in evals/datasets/judge_key.json.
Rubric (1-5) is the one in agent/prompts/judge.md.
"""
import argparse
import asyncio
import csv
import json
import random

from pydantic import BaseModel, Field

from evals.runners import harness as H
from agent import llm  # noqa: E402
from agent.config import prompt, render  # noqa: E402

SHEET = H.DS / "judge_calibration_sheet.csv"
KEY = H.DS / "judge_key.json"
PANEL = H.DS / "human_panel_pairs.csv"
PANEL_KEY = H.DS / "human_panel_key.json"
SETS = ["best_fixedwriter_v2", "v0_fixedwriter_v2", "best_fixedwriter"]


class Verdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str = ""


def rows(tag):
    p = H.RESULTS / f"proposals_{tag}.json"
    return [r for r in json.load(open(p, encoding="utf-8"))["rows"] if "error" not in r] if p.exists() else []


def make_sheets():
    rng = random.Random(30)
    jobs = {j["job_id"]: j for p in ("ai", "web", "data") for j in H.dev(p)}
    pool = [(t, r) for t in SETS for r in rows(t)]
    rng.shuffle(pool)
    picked = pool[:30]
    key = {}
    with open(SHEET, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "job_title", "job_description", "proposal", "your_score_1_to_5", "notes"])
        for i, (t, r) in enumerate(picked, 1):
            j = jobs[r["job_id"]]
            w.writerow([i, j["title"], j["description"][:700], r["proposal"], "", ""])
            key[str(i)] = {"set": t, "job_id": r["job_id"]}
    KEY.write_text(json.dumps(key, indent=1), encoding="utf-8")
    a = {r["job_id"]: r for r in rows("best_fixedwriter_v2")}
    b = {r["job_id"]: r for r in rows("v0_fixedwriter_v2")}
    common = sorted(set(a) & set(b))
    rng.shuffle(common)
    pkey = {}
    with open(PANEL, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pair", "job_title", "job_description", "proposal_A", "proposal_B", "which_would_you_reply_to_A_or_B", "rater_name"])
        for i, jid in enumerate(common[:15], 1):
            flip = rng.random() < 0.5
            left, right = (b[jid], a[jid]) if flip else (a[jid], b[jid])
            w.writerow([i, jobs[jid]["title"], jobs[jid]["description"][:700], left["proposal"], right["proposal"], "", ""])
            pkey[str(i)] = {"job_id": jid, "A": "v0" if flip else "shipped", "B": "shipped" if flip else "v0"}
    PANEL_KEY.write_text(json.dumps(pkey, indent=1), encoding="utf-8")
    print(f"wrote {SHEET.name} (30 items) and {PANEL.name} ({len(pkey)} pairs)")


async def judge_one(job, proposal):
    p = prompt("judge")
    user = render(p["user"], job=f"{job['title']}\n{job['description'][:1200]}", proposal=proposal)
    return await llm.structured("judge", p["system"], user, Verdict, max_tokens=1200)  # gpt-oss spends part of the budget on reasoning


async def run_judge():
    jobs = {j["job_id"]: j for p in ("ai", "web", "data") for j in H.dev(p)}
    key = json.loads(KEY.read_text(encoding="utf-8"))
    by_item = {}
    for i, k in key.items():
        r = next(x for x in rows(k["set"]) if x["job_id"] == k["job_id"])
        v = await judge_one(jobs[k["job_id"]], r["proposal"])
        by_item[i] = {"score": v.score, "reason": v.reason}
        print("item", i, v.score, flush=True)
    per_set = {}
    for t in ("best_fixedwriter_v2", "v0_fixedwriter_v2"):
        sc = []
        for r in rows(t)[:30]:
            sc.append((await judge_one(jobs[r["job_id"]], r["proposal"])).score)
        per_set[t] = {"n": len(sc), "mean_judge_score": H.mean(sc)}
        print(t, per_set[t], flush=True)
    H.write("judge_scores", {"model": "judge node (see agent/config.yaml)", "calibration_items": by_item, "sets": per_set})


def kappa(a, b, weighted=False):
    cats = [1, 2, 3, 4, 5]
    n = len(a)
    obs = sum((1 - ((x - y) ** 2 / 16 if weighted else (x != y))) for x, y in zip(a, b, strict=True)) / n
    pa = {c: sum(x == c for x in a) / n for c in cats}
    pb = {c: sum(y == c for y in b) / n for c in cats}
    exp = sum(pa[i] * pb[j] * (1 - ((i - j) ** 2 / 16 if weighted else (i != j))) for i in cats for j in cats)
    return round((obs - exp) / (1 - exp), 4) if exp < 1 else 1.0


def run_kappa():
    human = {}
    with open(SHEET, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["your_score_1_to_5"].strip():
                human[r["item"]] = int(r["your_score_1_to_5"])
    judge = json.loads((H.RESULTS / "judge_scores.json").read_text(encoding="utf-8"))["calibration_items"]
    items = sorted(set(human) & set(judge), key=int)
    a = [human[i] for i in items]
    b = [judge[i]["score"] for i in items]
    disagreements = [{"item": i, "human": human[i], "judge": judge[i]["score"], "judge_reason": judge[i]["reason"]}
                     for i in items if abs(human[i] - judge[i]["score"]) >= 2]
    out = {"n_labelled": len(items), "cohen_kappa": kappa(a, b), "quadratic_weighted_kappa": kappa(a, b, True),
           "exact_agreement": round(sum(x == y for x, y in zip(a, b, strict=True)) / max(1, len(a)), 4),
           "within_one": round(sum(abs(x - y) <= 1 for x, y in zip(a, b, strict=True)) / max(1, len(a)), 4),
           "big_disagreements": disagreements}
    H.write("judge_calibration", out)
    print(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheets", action="store_true")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--kappa", action="store_true")
    a = ap.parse_args()
    if a.make_sheets:
        make_sheets()
    if a.judge:
        asyncio.run(run_judge())
    if a.kappa:
        run_kappa()
