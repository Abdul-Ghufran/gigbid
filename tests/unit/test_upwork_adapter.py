"""Live Upwork adapter against a fake Upwork MCP server (no account / network): tool mapping onto the marketplace port,
drafts-only writes, the 3-hour polling floor, idempotent drafts and degraded mode."""
import json

import pytest

from mcp_servers.marketplace.adapters.base import MarketplaceUnavailable
from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter


class Tool:
    def __init__(self, name, fn, calls):
        self.name, self.fn, self.calls = name, fn, calls

    async def ainvoke(self, args):
        self.calls.append((self.name, args))
        return self.fn(args)


class FakeUpwork:
    def __init__(self):
        self.calls = []

    def factory(self):
        calls = self.calls

        class C:
            async def get_tools(self):
                return [
                    Tool("jobs_search", lambda a: json.dumps({"jobs": [{"id": "~01abc", "title": "Django API", "description": "Need Celery",
                                                                        "budget": {"amount": 900}, "client": {"id": "c9"},
                                                                        "connectPrice": 8, "skills": [{"name": "Django"}]}]}), calls),
                    Tool("get_job_details", lambda a: json.dumps({"id": a["job_id"], "title": "Django API", "description": "x",
                                                                  "hourlyBudget": {"min": 30, "max": 50}}), calls),
                    Tool("draft_proposal", lambda a: json.dumps({"draftId": "d-1", "url": "https://www.upwork.com/drafts/d-1"}), calls),
                    Tool("create_message_draft", lambda a: json.dumps({"ok": True}), calls),
                ]
        return C()


async def test_maps_tools_and_normalises_jobs():
    up = FakeUpwork()
    ad = UpworkLiveAdapter("https://mcp.upwork.com/mcp", "token", client_factory=up.factory)
    jobs = await ad.search_jobs("django", None, [], 0, None, 5)
    assert jobs[0]["job_id"] == "~01abc" and jobs[0]["budget"]["max"] == 900 and jobs[0]["connects_cost"] == 8
    job = await ad.get_job("~01abc")
    assert job["budget"]["type"] == "hourly" and job["budget"]["max"] == 50


async def test_polling_floor_blocks_rapid_searches():
    up = FakeUpwork()
    ad = UpworkLiveAdapter("u", "t", client_factory=up.factory)
    await ad.search_jobs("django", None, [], 0, None, 5)
    assert await ad.search_jobs("django", None, [], 0, None, 5) == []  # second call inside 30 min: refused
    assert sum(1 for n, _ in up.calls if n == "jobs_search") == 1


async def test_writes_are_drafts_only_and_idempotent():
    up = FakeUpwork()
    ad = UpworkLiveAdapter("u", "t", client_factory=up.factory)
    d1 = await ad.create_proposal_draft("~01abc", "cover letter text", [], 40, "hourly", "key-123456")
    d2 = await ad.create_proposal_draft("~01abc", "cover letter text", [], 40, "hourly", "key-123456")
    assert d1["id"] == "d-1" and d2["idempotent_replay"] and sum(1 for n, _ in up.calls if n == "draft_proposal") == 1
    sub = await ad.submit_proposal("d-1", "key-submit-1", dry_run=False)
    assert sub["status"] == "awaiting_confirmation_on_upwork"  # never presses submit on the user's behalf
    msg = await ad.send_message("room-1", "hello", "key-msg-1", dry_run=False)
    assert msg["status"] == "draft_created_confirm_on_upwork"


async def test_unreachable_server_is_degraded_mode():
    class Broken:
        async def get_tools(self):
            raise ConnectionError("down")

    ad = UpworkLiveAdapter("u", "t", client_factory=lambda: Broken())
    with pytest.raises(MarketplaceUnavailable):
        await ad.get_job("x")
