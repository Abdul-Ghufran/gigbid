"""GigSim: a marketplace simulator (REST) used for GigBid development and grading.

Run:  uvicorn gigsim.app:app --port 8081
Env:  GIGSIM_RATE_LIMIT_PER_MIN (60)  GIGSIM_ERROR_RATE (0.02)  GIGSIM_POLICY_VERSION
      GIGSIM_ADMIN_TOKEN  GIGSIM_SPEED (simulated minutes per real minute, default 1)
      GIGSIM_STATE_PATH (default gigsim/state/state.json)
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gigsim import brain
from gigsim.policy import active_policy, connects_cost

SEED = Path(__file__).parent / "seed"
STATE_PATH = Path(os.getenv("GIGSIM_STATE_PATH", Path(__file__).parent / "state" / "state.json"))
STATE_DB = os.getenv("GIGSIM_STATE_DB", "")  # optional Postgres URL: persist state where the disk is ephemeral
RATE = int(os.getenv("GIGSIM_RATE_LIMIT_PER_MIN", "60"))
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.02"))
ADMIN = os.getenv("GIGSIM_ADMIN_TOKEN", "gigsim-admin")
SPEED = float(os.getenv("GIGSIM_SPEED", "1"))


def _load_jsonl(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class World:
    """Immutable seed + mutable state (persisted to JSON so restarts keep proposals and threads)."""

    def __init__(self):
        self.lock = threading.RLock()
        self.clients = {c["client_id"]: c for c in json.loads((SEED / "clients.json").read_text(encoding="utf-8"))}
        self.freelancers = {f["token"]: f for f in json.loads((SEED / "freelancers.json").read_text(encoding="utf-8"))}
        self.lexicon = json.loads((SEED / "lexicon.json").read_text(encoding="utf-8"))
        self.hist = _load_jsonl(SEED / "jobs_historical.jsonl")
        self.jobs: dict[str, dict] = {}
        for j in _load_jsonl(SEED / "jobs_dev.jsonl"):
            j["pool"] = "dev"
            self.jobs[j["job_id"]] = j
        for j in _load_jsonl(SEED / "jobs_live.jsonl"):
            j["pool"] = "live"
            self.jobs[j["job_id"]] = j
        extra = os.getenv("GIGSIM_EXTRA_JOBS")  # e.g. a hidden test pool mounted at grading time
        if extra and Path(extra).exists():
            for j in _load_jsonl(Path(extra)):
                j["pool"] = "test"
                self.jobs[j["job_id"]] = j
        self.t0 = time.time()
        self.reset(load=True)

    # ------------------------------------------------------------------ state
    def reset(self, load=False):
        with self.lock:
            self.state = {"offset_min": 0.0, "epoch": time.time(), "proposals": {}, "threads": {}, "events": [], "idem": {},
                          "connects": {f["freelancer_id"]: f["connects_weekly"] for f in self.freelancers.values()},
                          "connects_ledger": []}
            if load:
                loaded = self._load()
                if loaded:
                    self.state = loaded
            self.state.setdefault("epoch", time.time())
            self.save()

    def _load(self):
        try:
            if STATE_DB:
                import psycopg

                with psycopg.connect(STATE_DB.replace("postgresql+psycopg://", "postgresql://")) as c:
                    c.execute("CREATE TABLE IF NOT EXISTS gigsim_state (id int PRIMARY KEY, state jsonb)")
                    row = c.execute("SELECT state FROM gigsim_state WHERE id = 1").fetchone()
                    return row[0] if row else None
            if STATE_PATH.exists():
                return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
        return None

    def save(self):
        if STATE_DB:
            import psycopg
            from psycopg.types.json import Jsonb

            with psycopg.connect(STATE_DB.replace("postgresql+psycopg://", "postgresql://")) as c:
                c.execute("CREATE TABLE IF NOT EXISTS gigsim_state (id int PRIMARY KEY, state jsonb)")
                c.execute("INSERT INTO gigsim_state VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state",
                          (Jsonb(self.state),))
            return
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state), encoding="utf-8")
        tmp.replace(STATE_PATH)

    def now_min(self) -> float:
        """Simulated minutes since the world was created (survives restarts: epoch is persisted)."""
        return (time.time() - self.state["epoch"]) / 60 * SPEED + self.state["offset_min"]

    def visible(self, j: dict) -> bool:
        return j["pool"] != "live" or j["release_minute"] <= self.now_min()

    def event(self, kind: str, freelancer_id: str, **data):
        e = {"id": len(self.state["events"]) + 1, "type": kind, "freelancer_id": freelancer_id,
             "sim_minute": round(self.now_min(), 1), **data}
        self.state["events"].append(e)
        return e

    # ------------------------------------------------------- client reactions
    def process_due(self):
        """Advance scheduled client reactions whose simulated time has come."""
        now = self.now_min()
        changed = False
        for p in self.state["proposals"].values():
            for step in p.get("schedule", []):
                if step["done"] or step["at"] > now:
                    continue
                step["done"] = True
                changed = True
                p["status"] = step["status"]
                self.event("proposal_" + step["status"], p["freelancer_id"], proposal_id=p["id"], job_id=p["job_id"])
                if step.get("message"):
                    self._client_message(p, step["message"], step.get("intent"))
        for t in self.state["threads"].values():
            for step in t.get("schedule", []):
                if step["done"] or step["at"] > now:
                    continue
                step["done"] = True
                changed = True
                p = self.state["proposals"][t["proposal_id"]]
                if step.get("status"):
                    p["status"] = step["status"]
                    self.event("proposal_" + step["status"], p["freelancer_id"], proposal_id=p["id"], job_id=p["job_id"])
                if step.get("message"):
                    self._client_message(p, step["message"], step.get("intent"))
        if changed:
            self.save()

    def _client_message(self, p: dict, text: str, intent: str | None):
        tid = p.get("thread_id")
        if not tid:
            tid = f"t-{p['id']}"
            p["thread_id"] = tid
            job = self.jobs[p["job_id"]]
            self.state["threads"][tid] = {"id": tid, "proposal_id": p["id"], "job_id": p["job_id"],
                                          "client_id": job["client_id"], "freelancer_id": p["freelancer_id"],
                                          "messages": [], "schedule": []}
        t = self.state["threads"][tid]
        t["messages"].append({"id": f"m-{uuid.uuid4().hex[:8]}", "from": "client", "text": text, "intent_hint": intent,
                              "sim_minute": round(self.now_min(), 1)})
        self.event("message_received", p["freelancer_id"], thread_id=tid, job_id=p["job_id"])


WORLD = World()
app = FastAPI(title="GigSim", version="1.0.0", description="Marketplace simulator for GigBid (AI-4016).")
_calls: dict[str, deque] = defaultdict(deque)


# ------------------------------------------------------------------------------ middleware/auth
@app.middleware("http")
async def chaos_and_limits(request: Request, call_next):
    if request.url.path.startswith("/v1/") and not request.url.path.startswith("/v1/admin") and request.url.path != "/v1/health":
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        q = _calls[token]
        now = time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE:
            return JSONResponse({"error": "rate_limited", "detail": f"limit {RATE}/min"}, status_code=429,
                                headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
        q.append(now)
        if ERROR_RATE and random.random() < ERROR_RATE:
            return JSONResponse({"error": "upstream_unavailable", "detail": "simulated 503"}, status_code=503)
    with WORLD.lock:
        WORLD.process_due()
    return await call_next(request)


def me(authorization: str = Header(default="")) -> dict:
    tok = authorization.removeprefix("Bearer ").strip()
    f = WORLD.freelancers.get(tok)
    if not f:
        raise HTTPException(401, "invalid token")
    return f


def admin(x_admin_token: str = Header(default="")):
    if x_admin_token != ADMIN:
        raise HTTPException(401, "admin token required")


def public_job(j: dict) -> dict:
    out = {k: v for k, v in j.items() if not k.startswith("_") and k not in ("release_minute",)}
    out["connects_cost"] = connects_cost(j["budget"]["max"], j.get("proposals_count", 0))
    return out


def public_client(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def idem(key: str | None, scope: str, fn):
    if not key:
        raise HTTPException(400, "Idempotency-Key header required for writes")
    k = f"{scope}:{key}"
    if k in WORLD.state["idem"]:
        return {**WORLD.state["idem"][k], "idempotent_replay": True}
    res = fn()
    WORLD.state["idem"][k] = res
    WORLD.save()
    return res


# ------------------------------------------------------------------------------------- reads
@app.get("/v1/health")
def health():
    return {"status": "ok", "sim_minute": round(WORLD.now_min(), 1), "policy_version": active_policy()["version"]}


@app.get("/v1/policy")
def policy():
    return active_policy()


@app.get("/v1/me")
def get_me(f: dict = Depends(me)):
    return {k: v for k, v in f.items() if k != "token"}


@app.get("/v1/me/connects")
def get_connects(f: dict = Depends(me)):
    return {"freelancer_id": f["freelancer_id"], "balance": WORLD.state["connects"][f["freelancer_id"]],
            "weekly_grant": active_policy()["weekly_connects_grant"],
            "ledger": [x for x in WORLD.state["connects_ledger"] if x["freelancer_id"] == f["freelancer_id"]][-20:]}


@app.get("/v1/jobs/search")
def search_jobs(q: str = "", category: str | None = None, skills: str | None = None, min_budget: float = 0,
                pool: str | None = None, posted_within_minutes: float | None = None, limit: int = Query(20, le=100),
                offset: int = 0, f: dict = Depends(me)):
    terms = [t for t in q.lower().split() if t]
    sk = [s.strip().lower() for s in skills.split(",")] if skills else []
    now = WORLD.now_min()
    rows = []
    for j in WORLD.jobs.values():
        if pool and j["pool"] != pool:
            continue
        if not WORLD.visible(j):
            continue
        if category and j["category"] != category:
            continue
        if j["budget"]["max"] < min_budget:
            continue
        if posted_within_minutes is not None and j["pool"] == "live" and now - j["release_minute"] > posted_within_minutes:
            continue
        hay = (j["title"] + " " + j["description"] + " " + " ".join(j.get("skills_listed", []))).lower()
        if terms and not all(t in hay for t in terms):
            continue
        if sk and not any(s in hay for s in sk):
            continue
        rows.append(j)
    rows.sort(key=lambda j: (j["pool"] != "live", -j.get("release_minute", 0), j["job_id"]))
    return {"total": len(rows), "jobs": [public_job(j) for j in rows[offset: offset + limit]]}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, f: dict = Depends(me)):
    j = WORLD.jobs.get(job_id)
    if not j or not WORLD.visible(j):
        raise HTTPException(404, "job not found")
    return public_job(j)


@app.get("/v1/clients/{client_id}")
def client_history(client_id: str, f: dict = Depends(me)):
    c = WORLD.clients.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    past = [h for h in WORLD.hist if h["client_id"] == client_id][:10]
    out = public_client(c)
    out["recent_jobs"] = [{"title": h["title"], "awarded_price": h["awarded_price"], "category": h["category"]} for h in past]
    return out


@app.get("/v1/market/stats")
def market_stats(category: str, skills: str | None = None, f: dict = Depends(me)):
    sk = [s.strip().lower() for s in skills.split(",")] if skills else []
    rows = [h for h in WORLD.hist if h["category"] == category]
    if sk:
        narrowed = [h for h in rows if any(s in " ".join(h.get("skills_listed", []) + [h["title"]]).lower() for s in sk)]
        rows = narrowed if len(narrowed) >= 15 else rows
    out = {}
    for typ in ("fixed", "hourly"):
        vals = sorted(h["awarded_price"] for h in rows if h["budget"]["type"] == typ)
        if vals:
            q = lambda p: vals[min(len(vals) - 1, int(p * len(vals)))]  # noqa: E731
            out[typ] = {"n": len(vals), "p25": q(0.25), "p50": q(0.5), "p75": q(0.75)}
    out["avg_proposals"] = round(sum(h["proposals_count"] for h in rows) / max(1, len(rows)), 1)
    return {"category": category, "skills": sk, **out}


@app.get("/v1/proposals")
def list_proposals(f: dict = Depends(me)):
    return {"proposals": [_pub_prop(p) for p in WORLD.state["proposals"].values() if p["freelancer_id"] == f["freelancer_id"]]}


@app.get("/v1/proposals/{pid}")
def get_proposal(pid: str, f: dict = Depends(me)):
    p = WORLD.state["proposals"].get(pid)
    if not p or p["freelancer_id"] != f["freelancer_id"]:
        raise HTTPException(404, "proposal not found")
    return _pub_prop(p)


def _pub_prop(p):
    return {k: v for k, v in p.items() if k not in ("schedule", "reaction")}


@app.get("/v1/threads")
def list_threads(f: dict = Depends(me)):
    return {"threads": [{k: v for k, v in t.items() if k != "schedule"} for t in WORLD.state["threads"].values()
                        if t["freelancer_id"] == f["freelancer_id"]]}


@app.get("/v1/threads/{tid}")
def get_thread(tid: str, f: dict = Depends(me)):
    t = WORLD.state["threads"].get(tid)
    if not t or t["freelancer_id"] != f["freelancer_id"]:
        raise HTTPException(404, "thread not found")
    return {k: v for k, v in t.items() if k != "schedule"}


@app.get("/v1/events")
def events(since_id: int = 0, f: dict = Depends(me)):
    return {"events": [e for e in WORLD.state["events"] if e["id"] > since_id and e["freelancer_id"] == f["freelancer_id"]][:200]}


# ------------------------------------------------------------------------------------ writes
class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str = Field(min_length=20, max_length=5000)
    screening_answers: list[str] = Field(default_factory=list, max_length=10)
    bid_amount: float = Field(gt=0, le=100000)
    bid_type: str = Field(pattern="^(fixed|hourly)$")


@app.post("/v1/proposals", status_code=201)
def create_proposal(body: ProposalIn, f: dict = Depends(me), idempotency_key: str | None = Header(default=None)):
    with WORLD.lock:
        j = WORLD.jobs.get(body.job_id)
        if not j or not WORLD.visible(j):
            raise HTTPException(404, "job not found")

        def do():
            pid = f"p-{uuid.uuid4().hex[:10]}"
            p = {"id": pid, "job_id": body.job_id, "freelancer_id": f["freelancer_id"], "status": "draft",
                 "cover_letter": body.cover_letter, "screening_answers": body.screening_answers,
                 "bid_amount": body.bid_amount, "bid_type": body.bid_type,
                 "connects_cost": connects_cost(j["budget"]["max"], j.get("proposals_count", 0)),
                 "created_sim_minute": round(WORLD.now_min(), 1)}
            WORLD.state["proposals"][pid] = p
            WORLD.event("proposal_drafted", f["freelancer_id"], proposal_id=pid, job_id=body.job_id)
            return _pub_prop(p)

        return idem(idempotency_key, f"create:{f['freelancer_id']}", do)


@app.post("/v1/proposals/{pid}/submit")
def submit_proposal(pid: str, dry_run: bool = False, f: dict = Depends(me), idempotency_key: str | None = Header(default=None)):
    with WORLD.lock:
        p = WORLD.state["proposals"].get(pid)
        if not p or p["freelancer_id"] != f["freelancer_id"]:
            raise HTTPException(404, "proposal not found")
        j = WORLD.jobs[p["job_id"]]
        pol = active_policy()
        cost = connects_cost(j["budget"]["max"], j.get("proposals_count", 0), pol)
        problems = []
        if pol["require_all_screening_answers"]:
            answered = len([a for a in p["screening_answers"] if a.strip()])
            if answered < len(j.get("screening_questions", [])):
                problems.append(f"policy {pol['version']}: {len(j['screening_questions']) - answered} screening question(s) unanswered")
        balance = WORLD.state["connects"][f["freelancer_id"]]
        if dry_run:
            return {"dry_run": True, "would_send": _pub_prop(p), "connects_cost": cost, "balance_before": balance,
                    "balance_after": balance - cost, "policy_version": pol["version"], "problems": problems}
        if p["status"] != "draft":
            if idempotency_key and f"submit:{f['freelancer_id']}:{idempotency_key}" in WORLD.state["idem"]:
                return {**WORLD.state["idem"][f"submit:{f['freelancer_id']}:{idempotency_key}"], "idempotent_replay": True}
            raise HTTPException(409, f"proposal already {p['status']}")
        if problems:
            raise HTTPException(422, "; ".join(problems))
        if balance < cost:
            raise HTTPException(402, f"insufficient connects: need {cost}, have {balance}")

        def do():
            WORLD.state["connects"][f["freelancer_id"]] -= cost
            WORLD.state["connects_ledger"].append({"freelancer_id": f["freelancer_id"], "delta": -cost, "proposal_id": pid,
                                                   "sim_minute": round(WORLD.now_min(), 1)})
            p["status"] = "submitted"
            p["submitted_sim_minute"] = round(WORLD.now_min(), 1)
            client = WORLD.clients[j["client_id"]]
            r = brain.react(j, {**p, "freelancer_id": f["freelancer_id"]}, f, WORLD.lexicon, client)
            p["reaction"] = r
            t = WORLD.now_min()
            sched = [{"at": t + 30, "status": "viewed", "done": False}]
            if r["replied"]:
                sk = (j["_hidden"]["must_have"] or ["the work"])[0]
                tmpl = random.Random(pid).choice(brain.REPLY_TEMPLATES[r["reply_intent"]])
                msg = tmpl.format(skill=sk, counter=int(p["bid_amount"] * 0.8))
                if j.get("_gold", {}).get("injection") and random.Random(pid + "inj").random() < 0.5:
                    msg += " " + brain.INJECTED_REPLY
                sched.append({"at": t + 90, "status": "replied", "done": False, "message": msg, "intent": r["reply_intent"]})
            else:
                sched.append({"at": t + 60 * 24 * 3, "status": "lost", "done": False})
            p["schedule"] = sched
            WORLD.event("proposal_submitted", f["freelancer_id"], proposal_id=pid, job_id=p["job_id"], connects_spent=cost)
            return {"proposal": _pub_prop(p), "connects_spent": cost,
                    "balance_after": WORLD.state["connects"][f["freelancer_id"]]}

        return idem(idempotency_key, f"submit:{f['freelancer_id']}", do)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@app.post("/v1/threads/{tid}/messages", status_code=201)
def send_message(tid: str, body: MessageIn, f: dict = Depends(me), idempotency_key: str | None = Header(default=None)):
    with WORLD.lock:
        t = WORLD.state["threads"].get(tid)
        if not t or t["freelancer_id"] != f["freelancer_id"]:
            raise HTTPException(404, "thread not found")

        def do():
            m = {"id": f"m-{uuid.uuid4().hex[:8]}", "from": "freelancer", "text": body.text,
                 "sim_minute": round(WORLD.now_min(), 1)}
            t["messages"].append(m)
            p = WORLD.state["proposals"][t["proposal_id"]]
            r = p.get("reaction", {})
            now = WORLD.now_min()
            flags = brain.features(WORLD.jobs[p["job_id"]], {"cover_letter": body.text, "job_id": p["job_id"]}, f,
                                   WORLD.lexicon, WORLD.clients[t["client_id"]])
            if flags["contact_info"]:
                WORLD.event("policy_warning", f["freelancer_id"], thread_id=tid, reason="off-platform contact in message")
            has_slots = any(w in body.text.lower() for w in ("am", "pm", ":00", "monday", "tuesday", "wednesday", "thursday", "friday"))
            if r.get("interview") and p["status"] in ("replied", "viewed") and has_slots:
                t.setdefault("schedule", []).append({"at": now + 60, "status": "interview", "done": False,
                                                     "message": "Great, the first slot works. Talk then!"})
                if r.get("hired"):
                    t["schedule"].append({"at": now + 60 * 24, "status": "hired", "done": False,
                                          "message": "We'd like to move forward. Sending the contract on the platform now."})
            elif p["status"] == "replied" and not t.get("followup"):
                t["followup"] = True
                t.setdefault("schedule", []).append({"at": now + 120, "done": False,
                                                     "message": "Thanks, that helps. We'll get back to you soon."})
            WORLD.event("message_sent", f["freelancer_id"], thread_id=tid)
            return m

        return idem(idempotency_key, f"msg:{f['freelancer_id']}", do)


# ------------------------------------------------------------------------------------ admin
@app.post("/v1/admin/tick", dependencies=[Depends(admin)])
def tick(minutes: float = 60):
    with WORLD.lock:
        WORLD.state["offset_min"] += minutes
        WORLD.process_due()
        WORLD.save()
    return {"sim_minute": round(WORLD.now_min(), 1)}


@app.post("/v1/admin/reset", dependencies=[Depends(admin)])
def reset():
    WORLD.reset()
    return {"ok": True}


@app.post("/v1/admin/grant_connects", dependencies=[Depends(admin)])
def grant(freelancer_id: str, amount: int = 80):
    with WORLD.lock:
        WORLD.state["connects"][freelancer_id] = WORLD.state["connects"].get(freelancer_id, 0) + amount
        WORLD.save()
    return {"balance": WORLD.state["connects"][freelancer_id]}


@app.get("/v1/admin/outcomes", dependencies=[Depends(admin)])
def outcomes() -> dict[str, Any]:
    """Ground-truth reactions for evaluation runs (never exposed to the agent)."""
    return {"proposals": [{"id": p["id"], "job_id": p["job_id"], "freelancer_id": p["freelancer_id"], "status": p["status"],
                           "reaction": p.get("reaction")} for p in WORLD.state["proposals"].values()]}


@app.post("/v1/admin/score", dependencies=[Depends(admin)])
def score_offline(body: dict):
    """Score a proposal without submitting it (used by offline A/B experiments and evals)."""
    j = WORLD.jobs.get(body["job_id"])
    if not j:
        raise HTTPException(404, "job not found")
    f = next(x for x in WORLD.freelancers.values() if x["freelancer_id"] == body["freelancer_id"])
    r = brain.react(j, {**body, "freelancer_id": f["freelancer_id"]}, f, WORLD.lexicon, WORLD.clients[j["client_id"]])
    return r
