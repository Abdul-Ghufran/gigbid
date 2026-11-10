"""Claim-verifier evaluation + calibration (B3).  v2 rule: number/tool mismatch => unsupported.

Builds a labelled claim set from the gold portfolio: for every case study a TRUE claim (its real outcome, cited) and
FABRICATED variants - wrong number, a tool the project never used, invented years of experience, a wrong citation.
Scores the verifier in both semantic modes (cross-encoder, bi-encoder), picks thresholds by F1 on detecting
fabrications, and writes evals/results/verifier_eval.json.
"""
import json
import random
import re
from pathlib import Path

from rag.corpus import get_corpus
from rag.ingest.skills import taxonomy
from rag.verify import SEMANTIC, check_claim

OUT = Path(__file__).resolve().parents[2] / "evals" / "results"


def build_claims(seed=7):
    rng = random.Random(seed)
    rows = []
    for p in ("ai", "web", "data"):
        c = get_corpus(p)
        evidence = {i.id: i.text for i in c.evidence}
        persona_skills = {s for i in c.evidence for s in i.skills}
        foreign = [s for s in taxonomy() if s not in persona_skills]
        for it in [i for i in c.evidence if i.type == "case_study"]:
            m = re.search(r"The work ([^.]+)\.", it.text)
            if not m:
                continue
            outcome = m.group(1)
            title = it.title.split(" for ")[0].lower()
            true = f"In the {title} project, the work {outcome} [{it.id}]."
            rows.append({"claim": true, "label": "supported", "kind": "true", "persona": p})
            skill = rng.choice(it.skills) if it.skills else None
            if skill:
                rows.append({"claim": f"I used {skill} on the {title} project [{it.id}].", "label": "supported", "kind": "true_skill", "persona": p})
            nums = re.findall(r"\d+", outcome)
            if nums:
                n = nums[0]
                wrong = outcome.replace(n, str(int(n) * 3 + 7), 1)
                rows.append({"claim": f"In the {title} project, the work {wrong} [{it.id}].", "label": "unsupported", "kind": "wrong_number", "persona": p})
            rows.append({"claim": f"I built the {title} project with {rng.choice(foreign)} [{it.id}].", "label": "unsupported", "kind": "wrong_tool", "persona": p})
            rows.append({"claim": "I have 12 years of experience delivering projects like this for Fortune 500 clients.", "label": "unsupported", "kind": "invented", "persona": p})
            other = rng.choice([x for x in c.evidence if x.type == "case_study" and x.id != it.id])
            rows.append({"claim": f"In the {title} project, the work {outcome} [{other.id}].", "label": "unsupported", "kind": "wrong_citation", "persona": p})
            rows[-1]["evidence"] = None
        for r in rows:
            if r["persona"] == p and "evidence_ref" not in r:
                r["evidence_ref"] = p
        yield p, evidence
    return rows


def score(rows, evid, mode, t_s, t_p):
    SEMANTIC["mode"] = mode
    preds = []
    for r in rows:
        cited = re.findall(r"\[([a-z]+-[a-z0-9-]+)\]", r["claim"])
        ev = {i: evid[r["persona"]][i] for i in cited if i in evid[r["persona"]]}
        if not ev:  # uncited: the verifier searches; emulate with the 3 most similar case studies
            ev = dict(list(evid[r["persona"]].items())[:3])
        c = check_claim(r["claim"], ev, t_s, t_p)
        preds.append(c.label)
    return preds


def f1_unsupported(rows, preds):
    tp = sum(1 for r, p in zip(rows, preds, strict=True) if r["label"] == "unsupported" and p == "unsupported")
    fp = sum(1 for r, p in zip(rows, preds, strict=True) if r["label"] != "unsupported" and p == "unsupported")
    fn = sum(1 for r, p in zip(rows, preds, strict=True) if r["label"] == "unsupported" and p != "unsupported")
    return {"f1": round(2 * tp / max(1, 2 * tp + fp + fn), 4), "precision": round(tp / max(1, tp + fp), 4),
            "recall": round(tp / max(1, tp + fn), 4), "tp": tp, "fp": fp, "fn": fn}


def main():
    gen = build_claims()
    evid = {}
    rows = []
    try:
        while True:
            p, ev = next(gen)
            evid[p] = ev
    except StopIteration as stop:
        rows = stop.value
    out = {"generated_by": "evals/runners/verifier_eval.py", "n_claims": len(rows),
           "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in sorted({r["kind"] for r in rows})}, "modes": {}}
    grids = {"cross_encoder": [(0.0, -3.0), (-2.0, -6.0)], "bi_encoder": [(0.8, 0.65), (0.7, 0.55)]}
    for mode, grid in grids.items():
        best = None
        for t_s, t_p in grid:
            preds = score(rows, evid, mode, t_s, t_p)
            m = f1_unsupported(rows, preds)
            per_kind = {k: round(sum(1 for r, p in zip(rows, preds, strict=True) if r["kind"] == k and (p == "unsupported") == (r["label"] == "unsupported"))
                                 / max(1, sum(1 for r in rows if r["kind"] == k)), 3) for k in out["by_kind"]}
            cand = {"t_support": t_s, "t_partial": t_p, **m, "accuracy_by_kind": per_kind}
            print(mode, cand["t_support"], cand["t_partial"], m, flush=True)
            if not best or m["f1"] > best["f1"]:
                best = cand
        out["modes"][mode] = best
    SEMANTIC["mode"] = "bi_encoder"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verifier_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in ("t_support", "t_partial", "f1", "precision", "recall")} for k, v in out["modes"].items()}, indent=1))


if __name__ == "__main__":
    main()
