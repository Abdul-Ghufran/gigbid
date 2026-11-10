"""Shared evaluation harness: isolated in-process GigSim + MCP servers, per-job ledgers, fixed job sets."""
from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="gigbid-eval-")
os.environ.setdefault("GIGSIM_INPROCESS", "1")
os.environ.setdefault("MCP_TRANSPORT", "memory")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_STATE_PATH", os.path.join(_TMP, "gigsim.json"))
os.environ.setdefault("GIGBID_STATE_DIR", _TMP)
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(_TMP, "eval.sqlite").replace("\\", "/"))
os.environ.setdefault("AUDIT_DISABLED", "1")

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "evals" / "datasets"
RESULTS = ROOT / "evals" / "results"
SETTINGS = {"ai": {"hourly_rate": 45, "min_project": 400}, "web": {"hourly_rate": 40, "min_project": 300},
            "data": {"hourly_rate": 30, "min_project": 150}}


def settings(p):
    return {**SETTINGS[p], "weekly_connects_budget": 100000, "connects_spent_week": 0, "autonomy": "suggest"}


def dev(persona: str) -> list[dict]:
    return [json.loads(line) for line in open(DS / f"dev_{persona}.jsonl", encoding="utf-8")]


def fixed_set(n_per_persona: int, kinds=None, seed: int = 11, bid_only=False) -> list[tuple[str, dict]]:
    """Deterministic, stratified job sample (same jobs for every system being compared)."""
    import random

    rng = random.Random(seed)
    out = []
    for p in ("ai", "web", "data"):
        rows = [r for r in dev(p) if (not kinds or r["_gold"]["kind"] in kinds) and (not bid_only or r["_gold"]["bid"])]
        rng.shuffle(rows)
        out += [(p, r) for r in rows[:n_per_persona]]
    return out


def gigsim_admin():
    from fastapi.testclient import TestClient

    from gigsim.app import app

    c = TestClient(app)
    h = {"X-Admin-Token": os.getenv("GIGSIM_ADMIN_TOKEN", "gigsim-admin")}
    for fid in ("ai_ml_engineer", "fullstack_web_dev", "data_analyst"):
        c.post("/v1/admin/grant_connects", params={"freelancer_id": fid, "amount": 5000}, headers=h)
    return c, h


def client_reaction(job_id: str, persona: str, cover: str, answers: list[str], bid: float, bid_type: str) -> dict:
    """GigSim's simulated client verdict for a proposal (admin scoring endpoint: no Connects, no side effects)."""
    c, h = gigsim_admin()
    fid = {"ai": "ai_ml_engineer", "web": "fullstack_web_dev", "data": "data_analyst"}[persona]
    return c.post("/v1/admin/score", json={"job_id": job_id, "freelancer_id": fid, "cover_letter": cover,
                                           "screening_answers": answers, "bid_amount": bid, "bid_type": bid_type}, headers=h).json()


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(math.ceil(p * len(xs))) - 1)], 3) if xs else None


def f1(tp, fp, fn):
    return round(2 * tp / max(1, 2 * tp + fp + fn), 4)


def mean(xs):
    return round(statistics.mean(xs), 4) if xs else None


def write(name: str, payload: dict):
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"generated_by": f"evals/runners/{name}.py", "generated_at": time.strftime("%Y-%m-%d %H:%M"), **payload}
    (RESULTS / f"{name}.json").write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return payload
