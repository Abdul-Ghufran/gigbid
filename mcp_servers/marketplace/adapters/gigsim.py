"""GigSim adapter: REST over httpx with timeouts, bounded retries + exponential backoff with jitter,
Retry-After handling for 429s, and a client-side token bucket that stays under GigSim's limit."""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from common.tracing import current_trace_id
from mcp_servers.marketplace.adapters.base import (
    InsufficientConnects,
    MarketplaceAdapter,
    MarketplaceError,
    MarketplaceUnavailable,
    NotFound,
    PolicyRejected,
    RateLimited,
)


class TokenBucket:
    """Per-user limiter: `rate` requests per minute, refilled continuously."""

    def __init__(self, rate_per_min: float):
        self.capacity = max(1.0, rate_per_min / 6)  # allow short bursts of ~10 s worth
        self.tokens = self.capacity
        self.rate = rate_per_min / 60.0
        self.ts = time.monotonic()
        self.lock = asyncio.Lock()

    async def take(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.rate)
                self.ts = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


_BUCKETS: dict[str, TokenBucket] = {}


class GigSimAdapter(MarketplaceAdapter):
    name = "gigsim"

    def __init__(self, base_url: str, token: str, user_key: str = "default", rate_per_min: float = 40,
                 timeout_s: float = 10, max_retries: int = 3, transport: httpx.AsyncBaseTransport | None = None):
        self.base = base_url.rstrip("/")
        self.token = token
        self.max_retries = max_retries
        self.bucket = _BUCKETS.setdefault(f"{user_key}:{rate_per_min}", TokenBucket(rate_per_min))
        self.http = httpx.AsyncClient(timeout=timeout_s, transport=transport)

    async def aclose(self):
        await self.http.aclose()

    async def _req(self, method: str, path: str, *, params=None, json=None, idem: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "X-Trace-Id": current_trace_id()}
        if idem:
            headers["Idempotency-Key"] = idem
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            await self.bucket.take()
            try:
                r = await self.http.request(method, self.base + path, params=params, json=json, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last = MarketplaceUnavailable(f"GigSim unreachable: {type(e).__name__}")
            else:
                if r.status_code < 300:
                    return r.json()
                detail = _detail(r)
                if r.status_code == 404:
                    raise NotFound(detail)
                if r.status_code == 402:
                    raise InsufficientConnects(detail)
                if r.status_code == 422:
                    raise PolicyRejected(detail)
                if r.status_code == 409:
                    raise MarketplaceError(detail)
                if r.status_code == 429:
                    last = RateLimited(detail)
                    await asyncio.sleep(min(30.0, float(r.headers.get("Retry-After", "2"))))
                    continue
                if r.status_code >= 500:
                    last = MarketplaceUnavailable(f"GigSim {r.status_code}: {detail}")
                else:
                    raise MarketplaceError(f"{r.status_code}: {detail}")
            if attempt < self.max_retries:
                await asyncio.sleep(min(8.0, 0.5 * 2 ** attempt) * (0.5 + random.random()))
        raise last or MarketplaceUnavailable("unknown error")

    # ------------------------------------------------------------------ reads
    async def search_jobs(self, query, category, skills, min_budget, posted_within_minutes, limit):
        params = {"q": query, "limit": limit, "min_budget": min_budget}
        if category:
            params["category"] = category
        if skills:
            params["skills"] = ",".join(skills)
        if posted_within_minutes is not None:
            params["posted_within_minutes"] = posted_within_minutes
        return [normalise_job(j) for j in (await self._req("GET", "/v1/jobs/search", params=params))["jobs"]]

    async def get_job(self, job_id):
        return normalise_job(await self._req("GET", f"/v1/jobs/{job_id}"))

    async def get_client_history(self, client_id):
        return await self._req("GET", f"/v1/clients/{client_id}")

    async def get_connects_balance(self):
        r = await self._req("GET", "/v1/me/connects")
        return {"balance": r["balance"], "weekly_grant": r.get("weekly_grant")}

    async def get_market_stats(self, category, skills):
        params = {"category": category}
        if skills:
            params["skills"] = ",".join(skills)
        return await self._req("GET", "/v1/market/stats", params=params)

    async def list_threads(self):
        return (await self._req("GET", "/v1/threads"))["threads"]

    async def get_thread(self, thread_id):
        return await self._req("GET", f"/v1/threads/{thread_id}")

    async def list_proposals(self):
        return (await self._req("GET", "/v1/proposals"))["proposals"]

    async def list_events(self, since_id):
        return (await self._req("GET", "/v1/events", params={"since_id": since_id}))["events"]

    async def get_policy(self):
        return await self._req("GET", "/v1/policy")

    # ----------------------------------------------------------------- writes
    async def create_proposal_draft(self, job_id, cover_letter, screening_answers, bid_amount, bid_type, idempotency_key):
        body = {"job_id": job_id, "cover_letter": cover_letter, "screening_answers": screening_answers,
                "bid_amount": bid_amount, "bid_type": bid_type}
        return await self._req("POST", "/v1/proposals", json=body, idem=idempotency_key)

    async def submit_proposal(self, proposal_id, idempotency_key, dry_run):
        return await self._req("POST", f"/v1/proposals/{proposal_id}/submit", params={"dry_run": str(dry_run).lower()},
                               idem=idempotency_key)

    async def send_message(self, thread_id, text, idempotency_key, dry_run):
        if dry_run:
            return {"dry_run": True, "would_send": {"thread_id": thread_id, "text": text}, "connects_cost": 0}
        return await self._req("POST", f"/v1/threads/{thread_id}/messages", json={"text": text}, idem=idempotency_key)


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json()
        return str(d.get("detail") or d.get("error") or d)
    except Exception:
        return r.text[:200]


def normalise_job(j: dict) -> dict:
    keep = ("job_id", "title", "description", "category", "skills_listed", "experience_level", "budget",
            "duration_weeks", "screening_questions", "client_id", "proposals_count", "connects_cost", "pool")
    return {k: j.get(k) for k in keep}
