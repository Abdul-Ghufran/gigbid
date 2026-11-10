"""Live Upwork adapter: talks to Upwork's official MCP server (Streamable HTTP, OAuth 2.1 bearer token)
through `MultiServerMCPClient` and maps its tools onto the same MarketplaceAdapter interface as GigSim.

Platform rules enforced here (not just in prompts):
  * no scraping, no browser automation, no cookies: the only transport is the official MCP endpoint;
  * reads are throttled (search no more often than `min_search_interval_s`, default 30 min);
  * writes only ever create DRAFTS.  `submit_proposal` / `send_message` never press "send" on Upwork:
    they return the draft plus a link so the freelancer confirms it on Upwork themselves.

Upwork's tool names are not hard-coded in the agent: `upwork_tool_map.yaml` lists candidate names per
port method and the adapter picks whichever the server actually advertises (list_tools at connect).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from mcp_servers.marketplace.adapters.base import MarketplaceAdapter, MarketplaceError, MarketplaceUnavailable

TOOL_MAP = yaml.safe_load((Path(__file__).parent / "upwork_tool_map.yaml").read_text(encoding="utf-8"))


class UpworkLiveAdapter(MarketplaceAdapter):
    name = "upwork_live"

    def __init__(self, url: str, access_token: str, min_search_interval_s: int = 1800, client_factory=None):
        self.url = url
        self.access_token = access_token
        self.min_search_interval_s = min_search_interval_s
        self._client_factory = client_factory
        self._tools: dict[str, Any] | None = None
        self._last_search: dict[str, float] = {}
        self._drafts: dict[str, dict] = {}

    async def _load_tools(self) -> dict[str, Any]:
        if self._tools is None:
            if self._client_factory:
                client = self._client_factory()
            else:
                from langchain_mcp_adapters.client import MultiServerMCPClient

                client = MultiServerMCPClient({"upwork": {
                    "transport": "streamable_http", "url": self.url,
                    "headers": {"Authorization": f"Bearer {self.access_token}"}, "timeout": 20}})
            try:
                tools = await client.get_tools()
            except Exception as e:  # network / auth failure -> degraded mode upstream
                raise MarketplaceUnavailable(f"Upwork MCP unavailable: {type(e).__name__}") from e
            self._tools = {t.name: t for t in tools}
        return self._tools

    async def _call(self, method: str, args: dict) -> Any:
        tools = await self._load_tools()
        spec = TOOL_MAP[method]
        name = next((n for n in spec["candidates"] if n in tools), None)
        if not name:
            raise MarketplaceError(f"Upwork MCP server exposes no tool for '{method}' (looked for {spec['candidates']})")
        mapped = {spec.get("args", {}).get(k, k): v for k, v in args.items() if v is not None}
        try:
            out = await tools[name].ainvoke(mapped)
        except Exception as e:
            raise MarketplaceUnavailable(f"Upwork tool {name} failed: {type(e).__name__}") from e
        if isinstance(out, str):
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"text": out}
        return out

    # ------------------------------------------------------------------ reads
    async def search_jobs(self, query, category, skills, min_budget, posted_within_minutes, limit):
        key = f"{query}|{category}|{','.join(skills)}"
        if time.time() - self._last_search.get(key, 0) < self.min_search_interval_s:
            return []  # polite scheduling: refuse to poll faster than the documented interval
        self._last_search[key] = time.time()
        raw = await self._call("search_jobs", {"query": " ".join([query, *skills]).strip(), "limit": limit})
        jobs = raw.get("jobs", raw if isinstance(raw, list) else [])
        return [normalise_upwork_job(j) for j in jobs if (normalise_upwork_job(j)["budget"]["max"] or 0) >= min_budget]

    async def get_job(self, job_id):
        return normalise_upwork_job(await self._call("get_job", {"job_id": job_id}))

    async def get_client_history(self, client_id):
        raw = await self._call("get_client_history", {"client_id": client_id})
        return {"client_id": client_id, "total_spent": raw.get("totalSpent", raw.get("total_spent")),
                "hires": raw.get("totalHires", raw.get("hires")), "payment_verified": raw.get("paymentVerified", raw.get("payment_verified")),
                "avg_rating_given": raw.get("rating"), "country": raw.get("country"), "raw": raw}

    async def get_connects_balance(self):
        raw = await self._call("get_connects_balance", {})
        return {"balance": raw.get("connects", raw.get("balance")), "weekly_grant": None}

    async def get_market_stats(self, category, skills):
        return {"category": category, "skills": skills, "note": "Upwork exposes no market statistics; GigBid falls back to its own history."}

    async def list_threads(self):
        raw = await self._call("list_threads", {})
        return raw.get("rooms", raw.get("threads", []))

    async def get_thread(self, thread_id):
        return await self._call("get_thread", {"thread_id": thread_id})

    async def list_proposals(self):
        raw = await self._call("list_proposals", {})
        return raw.get("proposals", [])

    async def list_events(self, since_id):
        return []  # Upwork has no event feed over MCP; the pipeline is refreshed from list_proposals

    async def get_policy(self):
        return {"version": "upwork-live", "rules": ["Every write is a draft confirmed by the freelancer on Upwork."]}

    # ----------------------------------------------------------------- writes (drafts only)
    async def create_proposal_draft(self, job_id, cover_letter, screening_answers, bid_amount, bid_type, idempotency_key):
        if idempotency_key in self._drafts:
            return {**self._drafts[idempotency_key], "idempotent_replay": True}
        raw = await self._call("create_proposal_draft", {
            "job_id": job_id, "cover_letter": cover_letter, "screening_answers": screening_answers,
            "bid_amount": bid_amount, "bid_type": bid_type})
        res = {"id": raw.get("id", raw.get("draftId", idempotency_key)), "job_id": job_id, "status": "draft",
               "confirm_url": raw.get("url"), "raw": raw}
        self._drafts[idempotency_key] = res
        return res

    async def submit_proposal(self, proposal_id, idempotency_key, dry_run):
        # Live mode never submits on the user's behalf: the draft already exists on Upwork.
        return {"dry_run": dry_run, "status": "awaiting_confirmation_on_upwork", "proposal_id": proposal_id,
                "message": "Draft created on Upwork. Open Upwork to review and confirm the submission.",
                "connects_cost": None}

    async def send_message(self, thread_id, text, idempotency_key, dry_run):
        if dry_run:
            return {"dry_run": True, "would_send": {"thread_id": thread_id, "text": text}}
        raw = await self._call("send_message_draft", {"thread_id": thread_id, "text": text})
        return {"status": "draft_created_confirm_on_upwork", "raw": raw}


def normalise_upwork_job(j: dict) -> dict:
    budget = j.get("budget") or {}
    amount = budget.get("amount") if isinstance(budget, dict) else budget
    hourly = j.get("hourlyBudget") or {}
    is_hourly = bool(hourly) or j.get("type") == "HOURLY"
    return {
        "job_id": str(j.get("id") or j.get("job_id") or j.get("ciphertext")),
        "title": j.get("title", ""),
        "description": j.get("description", ""),
        "category": j.get("category", "unknown"),
        "skills_listed": [s.get("name", s) if isinstance(s, dict) else s for s in j.get("skills", [])],
        "experience_level": j.get("experienceLevel", "intermediate"),
        "budget": {"type": "hourly" if is_hourly else "fixed",
                   "min": hourly.get("min", amount) if is_hourly else amount,
                   "max": hourly.get("max", amount) if is_hourly else amount, "currency": "USD"},
        "duration_weeks": None,
        "screening_questions": j.get("questions", []),
        "client_id": str((j.get("client") or {}).get("id", j.get("client_id", ""))),
        "proposals_count": j.get("proposalsCount", j.get("totalApplicants")),
        "connects_cost": j.get("connectPrice", j.get("connects")),
        "pool": "upwork",
    }
