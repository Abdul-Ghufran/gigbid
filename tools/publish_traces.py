"""Record the four public Langfuse traces for docs/TRACES.md (SUBMISSION_GUIDE Step 5), verify they arrived, write links.

  .\\gb.cmd tools/publish_traces.py

Runs the real bid graph (live LLMs from .env, in-process GigSim, a throwaway SQLite checkpoint DB) for:
  1. Skipped scam         - parallel analysis, Risk Assessor flags it, decide -> skip, no writer call
  2. Approved proposal    - writer -> verifier -> critic -> compliance -> approval interrupt -> approve -> submit
  3. Critic loop          - critic sends the draft back (revision 2) before compliance
  4. Crash and resume     - pause at approval, "crash" (drop the process state), new checkpointer resumes from the
                            checkpoint, submit replayed from history is idempotent (Connects spent once)
Each scenario is one trace (root span + agent/tool/LLM observations), marked public. Needs LANGFUSE_PUBLIC_KEY /
LANGFUSE_SECRET_KEY / LANGFUSE_HOST in .env (keys never leave .env; nothing secret is printed).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="gigbid-traces-")
os.environ.update(GIGSIM_INPROCESS="1", MCP_TRANSPORT="memory", GIGSIM_ERROR_RATE="0", REDIS_URL="",
                  GIGSIM_STATE_PATH=os.path.join(_tmp, "gigsim.json"), GIGBID_STATE_DIR=_tmp, GIGSIM_RATE_LIMIT_PER_MIN="100000",
                  DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.sqlite").replace("\\", "/"), AUDIT_DISABLED="1")

import httpx  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.config import config  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.llm import Ledger, ledger_var  # noqa: E402
from common.db import init_db  # noqa: E402
from common.tracing import _keys, check_langfuse, langfuse, trace_id_var, trace_url  # noqa: E402

ROWS = [json.loads(line) for line in open(ROOT / "evals" / "datasets" / "dev_web.jsonl", encoding="utf-8")]
S = {"hourly_rate": 40, "min_project": 300, "weekly_connects_budget": 500, "connects_spent_week": 0, "autonomy": "suggest"}
USER = "persona-web"
DOC = ROOT / "docs" / "TRACES.md"


async def traced(name: str, scenario: str, thread: str, body):
    """Run `body()` under one fresh trace id; returns (trace_id, result)."""
    lf, tid = langfuse(), uuid.uuid4().hex
    tok = [trace_id_var.set(tid), ledger_var.set(Ledger())]
    lf.trace(id=tid, name=name, user_id=USER, session_id=thread, metadata={"scenario": scenario}, input={"scenario": scenario})
    out, err = None, None
    try:
        out = await body()
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        led = ledger_var.get()
        lf.end_trace(tid, output={"scenario": scenario, "result": out, "tokens": led.tokens, "cost_usd": round(led.cost_usd, 6)},
                     error=err)
        trace_id_var.reset(tok[0])
        ledger_var.reset(tok[1])
    return tid, out


def jobs(pred):
    return [r for r in ROWS if pred(r)]


async def balance():
    from agent.mcp_client import Toolbox

    return (await Toolbox("submitter", USER).call("marketplace", "get_connects_balance", {}))["balance"]


async def scam(db):
    job = jobs(lambda r: r["_gold"]["scam"])[0]
    cfg = {"configurable": {"thread_id": f"bid:{USER}:{job['job_id']}"}}

    async def body():
        async with AsyncSqliteSaver.from_conn_string(db) as cp:
            g = build_bid_graph(cp)
            await g.ainvoke({"user_id": USER, "job_id": job["job_id"], "settings": S}, cfg)
            v = (await g.aget_state(cfg)).values
        return {"job": job["title"], "decision": v["decision"]["action"], "scam": v["analyses"]["risk"].get("scam"),
                "drafted": "draft" in v}
    return await traced("bid_graph", "Skipped scam", cfg["configurable"]["thread_id"], body)


async def approve(db, job, label, pass_score=None):
    cfg = {"configurable": {"thread_id": f"bid:{USER}:{job['job_id']}:{label.split()[0].lower()}"}}

    async def body():
        old = config()["thresholds"]["critic_pass_score"]
        if pass_score is not None:
            config()["thresholds"]["critic_pass_score"] = pass_score
        try:
            async with AsyncSqliteSaver.from_conn_string(db) as cp:
                g = build_bid_graph(cp)
                await g.ainvoke({"user_id": USER, "job_id": job["job_id"], "settings": S, "force_bid": True}, cfg)
                st = await g.aget_state(cfg)
                if st.next != ("approval",):
                    return {"job": job["title"], "stopped_at": st.values.get("status"), "next": list(st.next)}
                await g.ainvoke(Command(resume={"action": "approve"}), cfg)
                v = (await g.aget_state(cfg)).values
        finally:
            config()["thresholds"]["critic_pass_score"] = old
        crit = v.get("critiques") or []
        return {"job": job["title"], "status": v.get("status"), "revisions": v.get("revision"), "critic_rounds": len(crit),
                "critic_scores": [getattr(c, "score", None) if not isinstance(c, dict) else c.get("score") for c in crit],
                "compliance": (v.get("compliance") or {}).get("status"), "connects_spent": (v.get("submission") or {}).get("connects_spent")}
    return await traced("bid_graph", label, cfg["configurable"]["thread_id"], body)


async def crash_resume(db, job):
    thread = f"bid:{USER}:{job['job_id']}:crash"
    cfg = {"configurable": {"thread_id": thread}}

    async def body():
        async with AsyncSqliteSaver.from_conn_string(db) as cp:  # process 1: runs to the approval interrupt
            await build_bid_graph(cp).ainvoke({"user_id": USER, "job_id": job["job_id"], "settings": S, "force_bid": True}, cfg)
        before = await balance()
        async with AsyncSqliteSaver.from_conn_string(db) as cp:  # process 2 after the "crash": same DB, new saver
            g = build_bid_graph(cp)
            pending = (await g.aget_state(cfg)).next
            await g.ainvoke(Command(resume={"action": "approve"}), cfg)
            v = (await g.aget_state(cfg)).values
            hist = [s async for s in g.aget_state_history(cfg) if s.next == ("submit",)]
            if hist:  # the worker dies right after submit and re-runs it from the checkpoint
                await g.ainvoke(None, hist[0].config)
        after = await balance()
        spent = (v.get("submission") or {}).get("connects_spent")
        return {"job": job["title"], "pending_after_restart": list(pending), "status": v.get("status"),
                "connects_spent": spent, "balance_before": before, "balance_after": after,
                "spent_exactly_once": spent is not None and before - after == spent}
    return await traced("bid_graph", "Crash and resume", thread, body)


def verify(tid: str, wait_s: int = 180) -> int:
    """Poll Langfuse until the trace is readable; returns its observation count (0 = not found)."""
    pk, sk, host = _keys()
    deadline = time.time() + wait_s
    while time.time() < deadline:
        for url in (f"{host}/api/public/traces/{tid}",):
            try:
                r = httpx.get(url, auth=(pk, sk), timeout=20)
                if r.status_code == 200:
                    obs = r.json().get("observations") or []
                    if obs:
                        return len(obs)
            except Exception:  # noqa: BLE001
                pass
        try:
            r = httpx.get(f"{host}/api/public/v2/observations", params={"traceId": tid, "limit": 100}, auth=(pk, sk), timeout=20)
            if r.status_code == 200 and (r.json().get("data") or []):
                return len(r.json()["data"])
        except Exception:  # noqa: BLE001
            pass
        time.sleep(10)
    return 0


def write_doc(rows):
    what = {
        "Skipped scam": "parallel analysis (analyst, risk_assessor, fit_matcher); Risk Assessor flags the scam; decide -> skip; no writer call",
        "Approved proposal": "writer -> verifier -> critic -> compliance -> approval interrupt -> resume (approve) -> submit",
        "Critic loop": "critic fails the first draft and sends it back to the writer (revision 2) before compliance",
        "Crash and resume": "paused at approval, process restarted with a new checkpointer, resumed from the checkpoint; "
                            "the replayed submit is idempotent (Connects spent once)",
    }
    lines = ["# Public traces", "",
             "Every GigBid run is traced end to end under one trace id (UI request → API → graph → MCP servers → audit log).",
             "In the deployed app each run is viewable in **Runs → run → Execution trace**. The same run is exported to",
             "Langfuse over OpenTelemetry (OTLP/HTTP): one trace per run with the graph nodes (agent), MCP tool calls (tool) and",
             "one generation per LLM call (model, tokens, list-price cost), PII-masked before export. These four were recorded",
             f"with `tools/publish_traces.py` on {time.strftime('%Y-%m-%d')} (live models, in-process GigSim) and are public:", "",
             "| Trace | What it shows | Observations | Result | Link |", "|---|---|---|---|---|"]
    for label, tid, out, n in rows:
        res = {k: v for k, v in (out or {}).items() if k != "job"}
        lines.append(f"| {label} | {what[label]} (job: {(out or {}).get('job', '')}) | {n or 'pending'} | "
                     f"`{json.dumps(res, default=str)}` | [open trace]({trace_url(tid)}) |")
    lines += ["", "Runs in the deployed app are traced the same way (trace name `bid_graph` / `conv_graph`, session = the job's",
              "thread), and marked public, so any run's link from **Runs → Open full trace in Langfuse** can be shared.", ""]
    DOC.write_text("\n".join(lines), encoding="utf-8")


async def main():
    msg = check_langfuse()
    print(msg)
    if "ON" not in msg:
        sys.exit("Fix the Langfuse settings in .env first.")
    init_db()
    db = os.path.join(_tmp, "cp.sqlite")
    strong = jobs(lambda r: r["_gold"]["kind"] == "strong" and r["_gold"]["bid"])
    rows = []
    tid, out = await scam(db)
    rows.append(("Skipped scam", tid, out))
    print("scam", out)
    tid, out = await approve(db, strong[0], "Approved proposal")
    rows.append(("Approved proposal", tid, out))
    print("approved", out)
    loop = None
    if out and (out.get("critic_rounds") or 0) >= 2:
        loop = ("Critic loop", tid, out)
    for job in strong[1:3]:
        if loop:
            break
        tid, out = await approve(db, job, "Critic loop")
        print("critic attempt", out)
        if (out.get("critic_rounds") or 0) >= 2:
            loop = ("Critic loop", tid, out)
    if not loop:  # the live critic passed every first draft: demonstrate the loop with a pass score no draft can reach
        tid, out = await approve(db, strong[3], "Critic loop", pass_score=10.5)
        out["note"] = "demo run: critic pass score set above 10 so every draft is sent back; the graph stops after max_revisions (2) and continues to compliance"
        print("critic strict", out)
        loop = ("Critic loop", tid, out)
    rows.append(loop)
    tid, out = await crash_resume(db, strong[4])
    rows.append(("Crash and resume", tid, out))
    print("crash", out)
    langfuse().flush(60)
    if langfuse().last_error:
        print("EXPORT ERROR:", langfuse().last_error)
    done = []
    for label, tid, o in rows:
        n = verify(tid)
        print(f"{label}: {n} observations in Langfuse -> {trace_url(tid)}")
        done.append((label, tid, o, n))
    write_doc(done)
    print(f"Wrote {DOC}")
    if not all(n for *_, n in done):
        sys.exit("Some traces were not readable back from Langfuse yet (see above).")


if __name__ == "__main__":
    asyncio.run(main())
