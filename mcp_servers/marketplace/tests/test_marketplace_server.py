"""Marketplace MCP server tests through an in-memory MCP client (no network, GigSim in-process)."""
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from common.db import init_db
from mcp_servers.marketplace.server import mcp

init_db()


def data(res):
    assert not res.isError, res.content
    return res.structuredContent if res.structuredContent is not None else json.loads(res.content[0].text)


async def test_tools_have_annotations_and_output_schemas():
    async with connect(mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert {"search_jobs", "get_job", "get_client_history", "get_connects_balance", "list_messages",
            "create_proposal_draft", "submit_proposal", "send_message"} <= set(tools)
    for name in ("search_jobs", "get_job", "get_client_history"):
        assert tools[name].annotations.readOnlyHint is True
    assert tools["submit_proposal"].annotations.destructiveHint is True
    assert tools["create_proposal_draft"].annotations.destructiveHint is False
    for t in tools.values():
        assert t.outputSchema, f"{t.name} has no output schema"
        if t.name in ("create_proposal_draft", "submit_proposal", "send_message"):
            assert "idempotency_key" in t.inputSchema["required"]


async def test_search_and_read():
    async with connect(mcp._mcp_server) as c:
        jobs = data(await c.call_tool("search_jobs", {"query": "", "category": "ai", "limit": 3}))
        assert jobs["count"] == 3
        job = data(await c.call_tool("get_job", {"job_id": jobs["jobs"][0]["job_id"]}))
        client = data(await c.call_tool("get_client_history", {"client_id": job["client_id"]}))
        assert "total_spent" in client
        bal = data(await c.call_tool("get_connects_balance", {}))
        assert bal["balance"] > 0


async def test_invalid_arguments_rejected():
    async with connect(mcp._mcp_server) as c:
        r = await c.call_tool("search_jobs", {"category": "crypto"})
        assert r.isError
        r = await c.call_tool("submit_proposal", {"proposal_id": "x", "idempotency_key": "bad key!"})
        assert r.isError


async def test_draft_dry_run_then_submit_exactly_once():
    async with connect(mcp._mcp_server) as c:
        job = data(await c.call_tool("search_jobs", {"category": "ai", "limit": 1}))["jobs"][0]
        args = {"job_id": job["job_id"], "cover_letter": "I built a retrieval assistant for an insurer that cut lookup time by 90 percent.",
                "bid_amount": 500, "bid_type": job["budget"]["type"], "idempotency_key": "test-draft-001",
                "screening_answers": ["answer"] * len(job["screening_questions"])}
        preview = data(await c.call_tool("create_proposal_draft", {**args, "dry_run": True}))
        assert preview["dry_run"] and preview["would_send"]["job_id"] == job["job_id"]
        d1 = data(await c.call_tool("create_proposal_draft", {**args, "dry_run": False}))
        d2 = data(await c.call_tool("create_proposal_draft", {**args, "dry_run": False}))
        assert d2["idempotent_replay"] and d1["result"]["id"] == d2["result"]["id"]
        pid = d1["result"]["id"]
        before = data(await c.call_tool("get_connects_balance", {}))["balance"]
        sp = data(await c.call_tool("submit_proposal", {"proposal_id": pid, "idempotency_key": "test-submit-001", "dry_run": True}))
        assert sp["connects_cost"] > 0 and sp["balance_after"] == before - sp["connects_cost"]
        s1 = data(await c.call_tool("submit_proposal", {"proposal_id": pid, "idempotency_key": "test-submit-001", "dry_run": False}))
        s2 = data(await c.call_tool("submit_proposal", {"proposal_id": pid, "idempotency_key": "test-submit-001", "dry_run": False}))
        assert s2["idempotent_replay"]
        after = data(await c.call_tool("get_connects_balance", {}))["balance"]
        assert after == before - s1["connects_cost"], "connects must be spent exactly once"


async def test_audit_log_written():
    from common.db import AuditLog, session

    with session() as s:
        rows = s.query(AuditLog).filter_by(server="marketplace").all()
    assert any(r.tool == "submit_proposal" for r in rows)


@pytest.mark.parametrize("status", [503, 429])
async def test_adapter_retries_then_degrades(status):
    import httpx

    from mcp_servers.marketplace.adapters.base import MarketplaceUnavailable, RateLimited
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(status, json={"error": "x"}, headers={"Retry-After": "0"})

    ad = GigSimAdapter("http://gigsim", "t", user_key=f"retry{status}", max_retries=2, transport=httpx.MockTransport(handler), rate_per_min=6000)
    with pytest.raises((MarketplaceUnavailable, RateLimited)):
        await ad.get_job("x")
    assert calls["n"] == 3
