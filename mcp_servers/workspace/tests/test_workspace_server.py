import json

from mcp.shared.memory import create_connected_server_and_client_session as connect

from common.db import init_db
from mcp_servers.workspace.server import mcp

init_db()


def data(res):
    assert not res.isError, res.content
    return res.structuredContent if res.structuredContent is not None else json.loads(res.content[0].text)


async def test_free_slots_are_weekday_working_hours():
    async with connect(mcp._mcp_server) as c:
        r = data(await c.call_tool("free_slots", {"start_date": "2026-11-16", "days_ahead": 3, "max_slots": 3}))
    assert len(r["slots"]) == 3
    for s in r["slots"]:
        h = int(s["start"][11:13])
        assert 10 <= h < 18


async def test_hold_is_idempotent_and_removes_slot():
    async with connect(mcp._mcp_server) as c:
        s = data(await c.call_tool("free_slots", {"start_date": "2026-11-17", "days_ahead": 1, "max_slots": 1}))["slots"][0]
        h1 = data(await c.call_tool("create_interview_hold", {"start": s["start"], "end": s["end"], "title": "Interview", "idempotency_key": "hold-0001"}))
        h2 = data(await c.call_tool("create_interview_hold", {"start": s["start"], "end": s["end"], "title": "Interview", "idempotency_key": "hold-0001"}))
        assert h1["id"] == h2["id"] and h2["idempotent_replay"]
        s2 = data(await c.call_tool("free_slots", {"start_date": "2026-11-17", "days_ahead": 1, "max_slots": 1}))["slots"][0]
        assert s2["start"] != s["start"]


async def test_email_draft_never_sends():
    async with connect(mcp._mcp_server) as c:
        d = data(await c.call_tool("create_email_draft", {"to": "client", "subject": "Hi", "body": "Hello", "idempotency_key": "mail-0001"}))
    assert d["status"] == "draft"
