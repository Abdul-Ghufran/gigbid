"""Graph runs against GigSim (in-process), offline LLM fallbacks: parallel analysis, scam skip, approval
interrupt, crash-and-resume exactly-once submission, edit -> compliance re-check, conversation graph."""
import json
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from common.db import init_db

init_db()
ROWS = [json.loads(line) for line in open(Path(__file__).resolve().parents[2] / "evals" / "datasets" / "dev_web.jsonl")]
S = {"hourly_rate": 40, "min_project": 300, "weekly_connects_budget": 500, "connects_spent_week": 0, "autonomy": "suggest"}


def pick(pred):
    return next(r for r in ROWS if pred(r))


async def balance(user="persona-web"):
    from agent.mcp_client import Toolbox

    return (await Toolbox("submitter", user).call("marketplace", "get_connects_balance", {}))["balance"]


async def test_scam_is_skipped_without_drafting(tmp_path):
    job = pick(lambda r: r["_gold"]["scam"])
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.sqlite")) as cp:
        g = build_bid_graph(cp)
        cfg = {"configurable": {"thread_id": "scam"}}
        await g.ainvoke({"user_id": "persona-web", "job_id": job["job_id"], "settings": S}, cfg)
        v = (await g.aget_state(cfg)).values
    assert v["decision"]["action"] == "skip" and v["analyses"]["risk"]["scam"] and "draft" not in v


async def test_parallel_branches_all_write_state(tmp_path):
    job = pick(lambda r: r["_gold"]["kind"] == "strong" and r["_gold"]["bid"])
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.sqlite")) as cp:
        g = build_bid_graph(cp)
        cfg = {"configurable": {"thread_id": "par"}}
        steps = [list(ev) async for ev in g.astream({"user_id": "persona-web", "job_id": job["job_id"], "settings": S}, cfg, stream_mode="updates")]
        v = (await g.aget_state(cfg)).values
    assert {"job_spec", "risk", "fit"} <= set(v["analyses"])
    flat = [k for s in steps for k in s]
    assert flat.index("decide") > max(flat.index("analyst"), flat.index("risk_assessor"), flat.index("fit_matcher"))


async def test_crash_while_waiting_then_resume_submits_exactly_once(tmp_path):
    job = pick(lambda r: r["_gold"]["kind"] == "strong" and r["_gold"]["bid"] and r["job_id"] != "dev-web-001")
    db = str(tmp_path / "cp.sqlite")
    cfg = {"configurable": {"thread_id": "crash"}}
    async with AsyncSqliteSaver.from_conn_string(db) as cp:  # "API process" 1
        g = build_bid_graph(cp)
        await g.ainvoke({"user_id": "persona-web", "job_id": job["job_id"], "settings": S}, cfg)
        st = await g.aget_state(cfg)
        assert st.next == ("approval",), "graph must pause for the human"
    before = await balance()
    async with AsyncSqliteSaver.from_conn_string(db) as cp:  # process restarted: new saver, same database
        g = build_bid_graph(cp)
        assert (await g.aget_state(cfg)).next == ("approval",), "pending approval survives the restart"
        await g.ainvoke(Command(resume={"action": "approve"}), cfg)
        v = (await g.aget_state(cfg)).values
        spent = v["submission"]["connects_spent"]
        # simulate the worker crashing after submit and re-running the submit node from its checkpoint
        hist = [s async for s in g.aget_state_history(cfg) if s.next == ("submit",)]
        await g.ainvoke(None, hist[0].config)
    after = await balance()
    assert v["status"] == "submitted" and after == before - spent, "Connects spent exactly once"


async def test_edit_goes_back_through_compliance(tmp_path):
    job = pick(lambda r: r["_gold"]["kind"] == "strong" and r["_gold"]["bid"] and r["job_id"] not in ("dev-web-001",))
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.sqlite")) as cp:
        g = build_bid_graph(cp)
        cfg = {"configurable": {"thread_id": "edit"}}
        await g.ainvoke({"user_id": "persona-web", "job_id": job["job_id"], "settings": S}, cfg)
        draft = (await g.aget_state(cfg)).values["draft"]["cover_letter"]
        edited = draft + " Email me at someone@example.com to talk."
        await g.ainvoke(Command(resume={"action": "edit", "cover_letter": edited}), cfg)
        st = await g.aget_state(cfg)
    assert st.next == ("approval",)
    assert "someone@example.com" not in st.values["draft"]["cover_letter"]
    assert any("contact" in r for r in st.values["compliance"]["removed"])


async def test_reject_requires_no_send(tmp_path):
    job = pick(lambda r: r["_gold"]["kind"] == "strong" and r["_gold"]["bid"])
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.sqlite")) as cp:
        g = build_bid_graph(cp)
        cfg = {"configurable": {"thread_id": "rej"}}
        await g.ainvoke({"user_id": "persona-data", "job_id": job["job_id"], "settings": S}, cfg)
        if (await g.aget_state(cfg)).next != ("approval",):
            pytest.skip("job not drafted for this persona")
        await g.ainvoke(Command(resume={"action": "reject", "reason": "not interested"}), cfg)
        v = (await g.aget_state(cfg)).values
    assert v["status"] == "rejected" and "submission" not in v


async def test_conversation_graph_classifies_and_waits_for_approval(tmp_path):
    from fastapi.testclient import TestClient

    from gigsim.app import app

    c = TestClient(app)
    h = {"Authorization": "Bearer gigsim-dev-token-web"}
    c.post("/v1/admin/grant_connects", params={"freelancer_id": "fullstack_web_dev", "amount": 2000}, headers={"X-Admin-Token": "gigsim-admin"})
    for r in [r for r in ROWS if r["_gold"]["bid"]][30:50]:
        must = r["_hidden"]["must_have"]
        txt = f"Your {r['title']} project needs {', '.join(must)}. I built a similar system that cut costs by 31% using {', '.join(must)}."
        d = c.post("/v1/proposals", json={"job_id": r["job_id"], "cover_letter": txt, "screening_answers": ["Yes, with tests and docs."] * len(r["screening_questions"]),
                                          "bid_amount": r["budget"]["max"] * 0.8, "bid_type": r["budget"]["type"]}, headers={**h, "Idempotency-Key": "it" + r["job_id"]}).json()
        c.post(f"/v1/proposals/{d['id']}/submit", headers={**h, "Idempotency-Key": "is" + r["job_id"]})
    c.post("/v1/admin/tick", params={"minutes": 200}, headers={"X-Admin-Token": "gigsim-admin"})
    threads = c.get("/v1/threads", headers=h).json()["threads"]
    assert threads
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.sqlite")) as cp:
        g = build_conversation_graph(cp)
        t = threads[0]
        cfg = {"configurable": {"thread_id": t["id"]}}
        await g.ainvoke({"user_id": "persona-web", "thread_id": t["id"], "settings": S}, cfg)
        st = await g.aget_state(cfg)
        assert st.next == ("approval",) and st.values["intent"]["intent"]
        await g.ainvoke(Command(resume={"action": "approve"}), cfg)
        assert (await g.aget_state(cfg)).values["status"] == "sent"


async def test_crash_recovery_starts_a_run_that_never_began():
    """A run queued (no checkpoint yet) when the process restarted must start fresh, not fail with EmptyInputError."""
    from agent.runner import bid_thread, create_run, execute
    from common.db import JobRecord, User, session

    job = pick(lambda r: r["_gold"]["scam"])
    uid = "persona-web"
    with session() as s:
        if not s.get(User, uid):
            s.add(User(id=uid, email="recover@test.io", password_hash="x", persona_key="web", onboarded=True))
            s.add(JobRecord(id=f"{uid}:{job['job_id']}", user_id=uid, job_id=job["job_id"], fingerprint="fp-recover",
                            job={}, status="analysing", summary={}))
    run = create_run(uid, "bid", bid_thread(uid, job["job_id"]))
    out = await execute(run.id, {"kind": "bid", "job_id": job["job_id"], "continue": True})
    assert out["status"] == "done", out
    with session() as s:
        assert s.get(JobRecord, f"{uid}:{job['job_id']}").status == "skipped"
