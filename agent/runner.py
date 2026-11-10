"""Executes graph runs durably (used by the worker, and by the API when no Redis worker is configured).

* Postgres checkpointer + store in production (SQLite locally): a thread paused at interrupt() survives API and
  worker restarts; `resume` continues it from the checkpoint.
* Every run gets a trace id, a token/cost ledger and an event sink that writes the execution trace (RunEvent).
* MarketplaceDown -> the job is parked as `queued_retry` (degraded mode) and retried later; after
  MAX_ATTEMPTS failed runs a job goes to `dead_letter`.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import time
import uuid

from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.llm import Ledger, ledger_var
from agent.mcp_client import MarketplaceDown
from agent.memory import store as memstore
from agent.runtime import event_sink
from common.db import Conversation, JobRecord, Run, RunEvent, UserSettings, session
from common.settings import get_settings
from common.tracing import langfuse, trace_id_var, user_id_var

log = logging.getLogger("gigbid.runner")
MAX_ATTEMPTS = 3
_P: dict = {}
_lock = asyncio.Lock()


async def persistence():
    """(checkpointer, store), opened once per process."""
    async with _lock:
        if "cp" in _P:
            return _P["cp"], _P["store"]
        stack = contextlib.AsyncExitStack()
        url = get_settings().database_url
        if url.startswith("postgres"):
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.store.postgres.aio import AsyncPostgresStore

            pg = url.replace("postgresql+psycopg://", "postgresql://")
            cp = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(pg))
            st = await stack.enter_async_context(AsyncPostgresStore.from_conn_string(pg))
        else:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            from langgraph.store.sqlite.aio import AsyncSqliteStore

            import os
            from pathlib import Path

            from common.settings import ROOT

            d = Path(os.getenv("GIGBID_STATE_DIR") or ROOT / "data" / "processed")
            d.mkdir(parents=True, exist_ok=True)
            cp = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(d / "checkpoints.sqlite")))
            st = await stack.enter_async_context(AsyncSqliteStore.from_conn_string(str(d / "store.sqlite")))
        await cp.setup()
        await st.setup()
        memstore.set_store(st)
        _P.update(cp=cp, store=st, stack=stack)
        return cp, st


async def graphs():
    cp, st = await persistence()
    if "bid" not in _P:
        _P["bid"] = build_bid_graph(cp, st)
        _P["conv"] = build_conversation_graph(cp, st)
    return _P["bid"], _P["conv"]


def bid_thread(user_id: str, job_id: str) -> str:
    return f"bid:{user_id}:{job_id}"


def conv_thread(user_id: str, thread_id: str) -> str:
    return f"conv:{user_id}:{thread_id}"


def user_settings(user_id: str) -> dict:
    with session() as s:
        us = s.get(UserSettings, user_id)
        if not us:
            return {"hourly_rate": 40, "min_project": 300, "weekly_connects_budget": 60, "autonomy": "suggest", "connects_spent_week": 0}
        week_ago = dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
        spent = 0
        for j in s.query(JobRecord).filter(JobRecord.user_id == user_id, JobRecord.status == "submitted").all():
            ts = j.updated_at if j.updated_at.tzinfo else j.updated_at.replace(tzinfo=dt.UTC)
            if ts >= week_ago:
                spent += (j.summary.get("connects_spent") or 0)
        return {"hourly_rate": us.hourly_rate, "min_project": us.min_project, "weekly_connects_budget": us.weekly_connects_budget,
                "autonomy": us.autonomy, "connects_spent_week": spent}


def _sink(run_id: str, user_id: str):
    def write(kind: str, node: str, payload: dict):
        with session() as s:
            s.add(RunEvent(run_id=run_id, user_id=user_id, kind=kind, node=node, payload=payload))
    return write


def create_run(user_id: str, graph: str, thread_id: str) -> Run:
    with session() as s:
        from common.tracing import trace_id_var as _t

        r = Run(user_id=user_id, graph=graph, thread_id=thread_id, trace_id=_t.get() or uuid.uuid4().hex, status="queued")
        s.add(r)
        s.flush()
        return r


async def execute(run_id: str, payload: dict) -> dict:
    """Run (or resume) one graph thread.  payload: {kind: bid|conv, input|resume, job_id|thread_id}."""
    with session() as s:
        run = s.get(Run, run_id)
        if run.status in ("done", "interrupted") and not payload.get("resume"):
            return {"skipped": "already processed"}  # idempotent worker processing
        run.status = "running"
        user_id, thread, trace = run.user_id, run.thread_id, run.trace_id
    bid, conv = await graphs()
    g = bid if payload["kind"] == "bid" else conv
    led = Ledger()
    tokens = [ledger_var.set(led), trace_id_var.set(trace), user_id_var.set(user_id), event_sink.set(_sink(run_id, user_id))]
    lf = langfuse()
    if lf:
        lf.trace(id=trace, name=f"{payload['kind']}_graph", user_id=user_id, session_id=thread,
                 metadata={"run_id": run_id, "job_id": payload.get("job_id"), "thread_id": payload.get("thread_id")})
    cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 80}
    t0 = time.perf_counter()
    status, err = "done", None
    try:
        if payload.get("resume") is not None:
            inp = Command(resume=payload["resume"])
        elif payload.get("continue"):
            inp = None  # crash recovery: continue from the last checkpoint
        else:
            inp = payload["input"] | {"user_id": user_id, "trace_id": trace, "settings": user_settings(user_id)}
        async for _ in g.astream(inp, cfg, stream_mode="updates"):
            pass
        st = await g.aget_state(cfg)
        if st.next:
            status = "interrupted"
        values = st.values
    except MarketplaceDown as e:
        status, err, values = "failed", f"marketplace_unavailable: {e}", {}
        _sink(run_id, user_id)("error", "runner", {"error": err, "degraded": True})
    except Exception as e:  # noqa: BLE001
        log.exception("run %s failed", run_id)
        status, err, values = "failed", f"{type(e).__name__}: {e}"[:800], {}
        _sink(run_id, user_id)("error", "runner", {"error": err})
    finally:
        for var, tok in zip((ledger_var, trace_id_var, user_id_var, event_sink), tokens, strict=True):
            var.reset(tok)
    latency = time.perf_counter() - t0
    with session() as s:
        run = s.get(Run, run_id)
        run.status, run.error = status, err
        run.tokens, run.cost_usd, run.latency_s = led.tokens, round(led.cost_usd, 6), round(latency, 3)
    if payload["kind"] == "bid":
        _update_job(user_id, payload["job_id"], values, status, err, run_id, led, latency)
    else:
        _update_conv(user_id, payload["thread_id"], values, status, err)
    if lf:
        with contextlib.suppress(Exception):
            lf.flush()
    return {"status": status, "error": err, "tokens": led.tokens, "cost_usd": led.cost_usd, "latency_s": latency}


def _update_job(user_id, job_id, v: dict, run_status, err, run_id, led, latency):
    from agent.memory.promotion_rules import proposal_features

    with session() as s:
        j = s.get(JobRecord, f"{user_id}:{job_id}")
        if not j:
            return
        summ = dict(j.summary or {})
        summ["last_run"] = run_id
        if run_status == "failed":
            summ["attempts"] = summ.get("attempts", 0) + 1
            degraded = (err or "").startswith("marketplace_unavailable")
            j.status = "dead_letter" if summ["attempts"] >= MAX_ATTEMPTS else ("queued_retry" if degraded else "needs_attention")
            summ["error"] = err
        else:
            an = v.get("analyses", {})
            summ.update({
                "fit": an.get("fit", {}).get("score"), "risk": an.get("risk", {}).get("score"),
                "scam": an.get("risk", {}).get("scam"), "flags": an.get("risk", {}).get("flags", []),
                "decision": v.get("decision", {}).get("action"), "reasons": v.get("decision", {}).get("reasons", []),
                "price": v.get("price", {}).get("amount"), "connects_cost": v.get("price", {}).get("connects_cost") or v.get("job", {}).get("connects_cost"),
                "attention": v.get("attention", []), "tokens": summ.get("tokens", 0) + led.tokens,
                "cost_usd": round(summ.get("cost_usd", 0) + led.cost_usd, 6),
                "latency_s": round(summ.get("latency_s", 0) + latency, 2), "attempts": 0})
            st = v.get("status")
            j.status = {"skipped": "skipped", "watch": "watch", "awaiting_approval": "awaiting_approval", "submitted": "submitted",
                        "rejected": "rejected", "needs_attention": "needs_attention"}.get(st, "awaiting_approval" if run_status == "interrupted" else j.status)
            if v.get("approvals"):
                last = v["approvals"][-1]
                if last["action"] == "reject":
                    summ["reject_reason"] = last.get("reason")
            if st == "submitted":
                sub = v.get("submission", {})
                j.proposal_id = sub.get("proposal_id")
                j.pipeline_stage = "submitted"
                summ["connects_spent"] = sub.get("connects_spent")
                pr = v.get("price", {})
                summ["strategy"] = v["draft"].get("strategy")
                summ["features"] = proposal_features(v["draft"]["cover_letter"], pr.get("amount"), pr.get("market_p50"),
                                                     v.get("job", {}).get("category"))
            elif st == "awaiting_approval" or run_status == "interrupted":
                j.pipeline_stage = "drafted"
        j.summary = summ


def _update_conv(user_id, thread_id, v, run_status, err):
    with session() as s:
        c = s.get(Conversation, f"{user_id}:{thread_id}")
        if not c:
            return
        summ = dict(c.summary or {})
        if run_status == "failed":
            c.status, summ["error"] = "needs_attention", err
        else:
            c.status = {"sent": "replied", "awaiting_approval": "awaiting_approval", "rejected": "rejected", "idle": "up_to_date"}.get(
                v.get("status"), "awaiting_approval" if run_status == "interrupted" else c.status)
            summ.update({"intent": v.get("intent", {}).get("intent"), "reply": v.get("reply", {}).get("text")})
            if v.get("messages"):
                c.last_seen_message = v["messages"][-1]["id"]
        c.summary = summ


async def pending_interrupt(thread: str, kind: str = "bid") -> dict | None:
    bid, conv = await graphs()
    g = bid if kind == "bid" else conv
    st = await g.aget_state({"configurable": {"thread_id": thread}})
    for t in st.tasks:
        for it in t.interrupts:
            return it.value
    return None


async def thread_values(thread: str, kind: str = "bid") -> dict:
    bid, conv = await graphs()
    g = bid if kind == "bid" else conv
    return (await g.aget_state({"configurable": {"thread_id": thread}})).values


async def history(thread: str, kind: str = "bid") -> list[dict]:
    """Checkpoint history (for replay from any node)."""
    bid, conv = await graphs()
    g = bid if kind == "bid" else conv
    out = []
    async for snap in g.aget_state_history({"configurable": {"thread_id": thread}}):
        out.append({"checkpoint_id": snap.config["configurable"]["checkpoint_id"], "next": list(snap.next),
                    "step": snap.metadata.get("step"), "created_at": snap.created_at})
    return out


async def replay_from(thread: str, checkpoint_id: str, kind: str = "bid"):
    """Fork the thread from an earlier checkpoint and run forward (C6: replay any job from any node)."""
    bid, conv = await graphs()
    g = bid if kind == "bid" else conv
    cfg = {"configurable": {"thread_id": thread, "checkpoint_id": checkpoint_id}}
    async for _ in g.astream(None, cfg, stream_mode="updates"):
        pass
