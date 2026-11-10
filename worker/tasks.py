"""Background work (E1): scouting on schedule, graph runs, pipeline sync and crash recovery.

Runs under Arq on Redis (`arq worker.tasks.WorkerSettings`).  Without REDIS_URL (laptop / single container)
`enqueue` falls back to an in-process asyncio task so the product still works.

Idempotency: JobRecord's primary key is (user, job) so re-scouting never re-queues a job; Arq job ids are the
run ids so a run is enqueued once; the graph's submit node uses content-derived idempotency keys so a worker
restart in the middle of submission can never double-submit or double-spend Connects.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from agent.config import config
from agent.runner import bid_thread, conv_thread, create_run, execute
from common.db import Conversation, JobRecord, Run, User, UserSettings, init_db, session
from common.settings import get_settings
from common.tracing import configure_logging

log = logging.getLogger("gigbid.worker")
_redis = None
_local_tasks: set[asyncio.Task] = set()
_slots: dict[str, asyncio.Semaphore] = {}


async def _limited(run_id: str, payload: dict):
    """In-process mode: at most 2 background analyses at once (retrieval + reranking are CPU-bound), plus a separate
    lane so a human's approval / reply decision never waits behind background scouting."""
    lane = "interactive" if payload.get("resume") is not None or payload.get("kind") == "conv" else "background"
    sem = _slots.setdefault(lane, asyncio.Semaphore(2))
    async with sem:
        return await execute(run_id, payload)


async def _pool():
    global _redis
    if _redis is None and get_settings().redis_url:
        from arq import create_pool
        from arq.connections import RedisSettings

        _redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _redis


async def enqueue(run_id: str, payload: dict):
    pool = await _pool()
    if pool:
        await pool.enqueue_job("run_graph", run_id, payload, _job_id=f"run:{run_id}")
    else:
        t = asyncio.create_task(_limited(run_id, payload))
        _local_tasks.add(t)
        t.add_done_callback(_local_tasks.discard)


async def start_bid(user_id: str, job_id: str, force_bid: bool = False) -> str:
    run = create_run(user_id, "bid", bid_thread(user_id, job_id))
    with session() as s:
        j = s.get(JobRecord, f"{user_id}:{job_id}")
        persona = s.get(User, user_id).persona_key
        if j:
            j.status = "analysing"
            j.thread_id = run.thread_id
    await enqueue(run.id, {"kind": "bid", "job_id": job_id,
                           "input": {"job_id": job_id, "persona": persona, "force_bid": force_bid}})
    return run.id


async def resume_bid(user_id: str, job_id: str, decision: dict) -> str:
    run = create_run(user_id, "bid", bid_thread(user_id, job_id))
    await enqueue(run.id, {"kind": "bid", "job_id": job_id, "resume": decision})
    return run.id


async def start_conversation(user_id: str, thread_id: str, resume: dict | None = None) -> str:
    run = create_run(user_id, "conversation", conv_thread(user_id, thread_id))
    payload = {"kind": "conv", "thread_id": thread_id}
    if resume is not None:
        payload["resume"] = resume
    else:
        with session() as s:
            persona = s.get(User, user_id).persona_key
        payload["input"] = {"thread_id": thread_id, "persona": persona}
    await enqueue(run.id, payload)
    return run.id


# ------------------------------------------------------------------------------------ scouting
async def scout_user(user_id: str, force: bool = False) -> dict:
    from agent.nodes.scout import run_saved_search

    mode = config()["marketplace"]["mode"]
    with session() as s:
        us = s.get(UserSettings, user_id)
        searches = list(us.saved_searches or []) if us else []
        seen = {fp for (fp,) in s.query(JobRecord.fingerprint).filter_by(user_id=user_id).all()}
        autonomy = us.autonomy if us else "suggest"
    now = dt.datetime.now(dt.UTC)
    new_jobs = 0
    for sr in searches:
        interval = sr.get("interval_minutes") or config()["marketplace"]["scout_interval_minutes"][mode]
        if mode == "upwork_live":
            interval = max(interval, config()["marketplace"]["scout_interval_minutes"]["upwork_live"])
        last = sr.get("last_run")
        if not force and last and (now - dt.datetime.fromisoformat(last)).total_seconds() < interval * 60:
            continue
        jobs = await run_saved_search(user_id, sr, seen, limit=sr.get("limit", 10))
        sr["last_run"] = now.isoformat()
        for j in jobs:
            key = f"{user_id}:{j['job_id']}"
            with session() as s:
                if s.get(JobRecord, key):
                    continue
                dup_of = None
                if j["_duplicate"]:
                    other = s.query(JobRecord).filter_by(user_id=user_id, fingerprint=j["_fingerprint"]).first()
                    dup_of = other.job_id if other else "unknown"
                s.add(JobRecord(id=key, user_id=user_id, job_id=j["job_id"], fingerprint=j["_fingerprint"], duplicate_of=dup_of,
                                job={k: v for k, v in j.items() if not k.startswith("_")},
                                status="duplicate" if dup_of else "new", summary={"search": sr.get("name") or sr.get("query")}))
            if not j["_duplicate"]:
                new_jobs += 1
                await start_bid(user_id, j["job_id"])
    with session() as s:
        us = s.get(UserSettings, user_id)
        if us:
            us.saved_searches = searches
    _ = autonomy
    return {"user_id": user_id, "new_jobs": new_jobs}


async def sync_pipeline(user_id: str) -> dict:
    """Marketplace events -> pipeline board stages; new client messages -> conversation runs; outcomes -> memory."""
    from agent.mcp_client import Toolbox

    tb = Toolbox("pipeline", user_id)
    with session() as s:
        us = s.get(UserSettings, user_id)
        cursor = int((us.filters or {}).get("_event_cursor", 0)) if us else 0
    ev = (await tb.call("marketplace", "list_events", {"since_id": cursor}))["events"]
    stage_map = {"proposal_viewed": "viewed", "proposal_replied": "replied", "proposal_interview": "interview",
                 "proposal_hired": "hired", "proposal_lost": "lost"}
    threads = set()
    for e in ev:
        if e["type"] in stage_map and e.get("job_id"):
            with session() as s:
                j = s.get(JobRecord, f"{user_id}:{e['job_id']}")
                if j:
                    j.pipeline_stage = stage_map[e["type"]]
        if e["type"] == "message_received":
            threads.add((e["thread_id"], e["job_id"]))
        cursor = max(cursor, e["id"])
    for tid, job_id in threads:
        with session() as s:
            c = s.get(Conversation, f"{user_id}:{tid}")
            if not c:
                s.add(Conversation(id=f"{user_id}:{tid}", user_id=user_id, marketplace_thread_id=tid, job_id=job_id, status="new"))
            elif c.status == "awaiting_approval":
                continue
        await start_conversation(user_id, tid)
    with session() as s:
        us = s.get(UserSettings, user_id)
        if us:
            us.filters = {**(us.filters or {}), "_event_cursor": cursor}
    from agent.memory.store import refresh_outcomes

    await refresh_outcomes(user_id)
    return {"events": len(ev), "threads": len(threads)}


# ------------------------------------------------------------------------------- arq functions
async def run_graph(ctx, run_id: str, payload: dict):
    return await execute(run_id, payload)


async def scout_all(ctx=None):
    with session() as s:
        users = [u.id for u in s.query(User).filter_by(onboarded=True).all()]
    out = []
    for u in users:
        try:
            out.append(await scout_user(u))
            out.append(await sync_pipeline(u))
        except Exception as e:  # degraded mode: keep other users going
            log.warning("scout/sync failed for %s: %s", u, e)
    return out


async def recover(ctx=None):
    """On worker start: continue runs that were mid-flight when the process died, and retry degraded jobs."""
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=2)
    with session() as s:
        stale = [(r.id, r.user_id, r.thread_id, r.graph) for r in s.query(Run).filter(Run.status.in_(["running", "queued"])).all()
                 if (r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=dt.UTC)) < cutoff]
        retry = [(j.user_id, j.job_id) for j in s.query(JobRecord).filter_by(status="queued_retry").all()]
    for rid, _uid, thread, graph in stale:
        kind = "bid" if graph == "bid" else "conv"
        ident = thread.split(":", 2)[2]
        await enqueue(rid, {"kind": kind, ("job_id" if kind == "bid" else "thread_id"): ident, "continue": True})
    for uid, job_id in retry:
        await start_bid(uid, job_id)
    return {"continued": len(stale), "retried": len(retry)}


async def startup(ctx):
    configure_logging()
    init_db()
    await recover()


def _cron():
    from arq import cron

    return [cron(scout_all, minute=set(range(0, 60, 10)), run_at_startup=False), cron(recover, minute={5, 35})]


class WorkerSettings:
    functions = [run_graph]
    on_startup = startup
    max_jobs = 2
    job_timeout = 900

    @staticmethod
    def _redis():
        from arq.connections import RedisSettings

        return RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")


WorkerSettings.redis_settings = WorkerSettings._redis()
try:
    WorkerSettings.cron_jobs = _cron()
except Exception:  # pragma: no cover
    pass
