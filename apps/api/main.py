"""GigBid API (FastAPI).  Run: uvicorn apps.api.main:app --port 8000"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from agent.mcp_client import MarketplaceDown, ToolCallError
from apps.api.routers import analytics, auth, jobs, messages, proposals, runs, settings
from common.db import User, init_db, session
from common.settings import get_settings
from common.tracing import configure_logging, new_trace_id, trace_id_var

log = logging.getLogger("gigbid.api")


def seed_reviewer():
    """Reviewer login preloaded with a persona (credentials come from env, never from the repo)."""
    s = get_settings()
    if not s.reviewer_password:
        return
    from apps.api.auth.users import create_user
    from apps.api.routers.auth import onboard_user
    from apps.api.schemas.models import OnboardingIn

    with session() as db:
        exists = db.query(User).filter_by(email=s.reviewer_email.lower()).first()
    if exists:
        return
    u = create_user(s.reviewer_email, s.reviewer_password, "Reviewer", "web")
    from apps.api.schemas.models import SavedSearch

    onboard_user(u.id, OnboardingIn(persona_key="web", hourly_rate=40, min_project=300, weekly_connects_budget=80, saved_searches=[
        SavedSearch(name="Python backends", category="web", skills=["Django", "Celery"], limit=4),
        SavedSearch(name="React / Next.js", category="web", skills=["React", "Next.js"], limit=3),
        # so a reviewer immediately sees the safety features: a scam post and a post with planted AI instructions
        SavedSearch(name="Risky posts (demo)", query="paid test task", limit=1),
        SavedSearch(name="Planted instructions (demo)", query="automated bidders", category="web", limit=1)]))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    seed_reviewer()
    from agent.runner import graphs

    await graphs()
    from agent.mcp_client import load_schemas

    await load_schemas()
    bg = None
    if not get_settings().redis_url and os.getenv("INPROCESS_SCHEDULER", "1") == "1":
        from worker.tasks import recover, scout_all

        async def loop():
            await recover()
            while True:  # scout right after start (Render wakes from sleep on the first request), then every 10 min
                with contextlib.suppress(Exception):
                    await scout_all()
                await asyncio.sleep(600)

        bg = asyncio.create_task(loop())
    yield
    if bg:
        bg.cancel()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot: jobs, proposals, approvals, messages, runs, analytics.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Trace-Id"])


@app.middleware("http")
async def trace_mw(request: Request, call_next):
    tid = request.headers.get("x-trace-id") or new_trace_id()
    trace_id_var.set(tid)
    resp = await call_next(request)
    resp.headers["X-Trace-Id"] = tid
    return resp


@app.exception_handler(MarketplaceDown)
async def market_down(_: Request, e: MarketplaceDown):
    return JSONResponse({"detail": "marketplace_unavailable", "message": str(e)}, status_code=503)


@app.exception_handler(ToolCallError)
async def tool_err(_: Request, e: ToolCallError):
    return JSONResponse({"detail": e.code, "message": str(e)}, status_code=502)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "gigbid-api"}


for r in (auth, jobs, proposals, messages, runs, analytics, settings):
    app.include_router(r.router, prefix="/api")

# Single-service deployments can serve the built web app from the API container.
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if WEB_DIST.exists():
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = WEB_DIST / path
        return FileResponse(f if path and f.is_file() else WEB_DIST / "index.html")
