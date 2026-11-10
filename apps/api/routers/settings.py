"""Settings, memory viewer, portfolio uploads and system status (degraded-mode banner)."""
from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException

from agent.config import config, profile_name
from agent.memory.store import delete_memory, list_memory
from agent.mcp_client import Toolbox
from apps.api.auth.token_store import connected_accounts, disconnect
from apps.api.auth.users import current_user
from apps.api.schemas.models import MemoryOut, PortfolioItemIn, PortfolioItemOut, SettingsIn, SettingsOut, SystemStatus
from common.db import Edit, PortfolioUpload, User, UserSettings, session
from common.settings import get_settings
from common.tracing import langfuse

router = APIRouter(tags=["settings"])


def _settings_out(user_id: str) -> SettingsOut:
    with session() as s:
        us = s.get(UserSettings, user_id) or UserSettings(user_id=user_id, hourly_rate=40, min_project=300,
                                                          weekly_connects_budget=60, autonomy="suggest", saved_searches=[])
        return SettingsOut(hourly_rate=us.hourly_rate, min_project=us.min_project, weekly_connects_budget=us.weekly_connects_budget,
                           autonomy=us.autonomy, saved_searches=us.saved_searches or [], connected_accounts=connected_accounts(user_id),
                           model_profile=profile_name(), marketplace_mode=config()["marketplace"]["mode"])


@router.get("/settings", response_model=SettingsOut)
def get_settings_(u: User = Depends(current_user)):
    return _settings_out(u.id)


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, u: User = Depends(current_user)):
    with session() as s:
        us = s.get(UserSettings, u.id) or UserSettings(user_id=u.id)
        for k, v in body.model_dump(exclude_none=True).items():
            if k == "saved_searches":
                v = [{**x, "id": x.get("id") or uuid.uuid4().hex[:8]} for x in v]
            setattr(us, k, v)
        s.merge(us)
    return _settings_out(u.id)


@router.delete("/settings/accounts/{account_id}", response_model=SettingsOut)
def remove_account(account_id: str, u: User = Depends(current_user)):
    disconnect(u.id, account_id)
    return _settings_out(u.id)


@router.get("/memory", response_model=MemoryOut)
async def memory(u: User = Depends(current_user)):
    m = await list_memory(u.id)
    with session() as s:
        edits = [{"job_id": e.job_id, "created_at": e.created_at.isoformat(), "diff": (e.diff or {}).get("lines", [])[:12]}
                 for e in s.query(Edit).filter_by(user_id=u.id).order_by(Edit.id.desc()).limit(10).all()]
    return MemoryOut(style=m["style"], outcome=m["outcome"], recent_edits=edits)


@router.delete("/memory/{kind}/{key}", response_model=MemoryOut)
async def forget(kind: str, key: str, category: str | None = None, u: User = Depends(current_user)):
    if kind not in ("style", "outcome"):
        raise HTTPException(422, "kind must be style or outcome")
    await delete_memory(u.id, kind, key, category)
    return await memory(u)


@router.get("/portfolio", response_model=list[PortfolioItemOut])
def portfolio(u: User = Depends(current_user)):
    from rag.corpus import get_corpus

    c = get_corpus(u.persona_key or "none", u.id)
    return [PortfolioItemOut(id=i.id, type=i.type, title=i.title, source=i.source, skills=i.skills, date=i.date, project=i.project,
                             outcome=i.outcome, uploaded=bool(i.meta.get("upload"))) for i in c.items if i.type != "past_proposal"][:300]


@router.post("/portfolio", response_model=PortfolioItemOut)
def upload(body: PortfolioItemIn, u: User = Depends(current_user)):
    from rag.corpus import invalidate
    from rag.ingest.skills import extract_skills

    with session() as s:
        p = PortfolioUpload(user_id=u.id, kind=body.kind, title=body.title, content=body.content,
                            meta={k: v for k, v in body.model_dump().items() if k in ("project", "date", "client_industry", "outcome") and v})
        s.add(p)
        s.flush()
        pid = p.id
    invalidate(u.id)  # incremental re-index on next retrieval
    return PortfolioItemOut(id=f"upload-{pid}", type=body.kind, title=body.title, source="upload",
                            skills=extract_skills(body.content, code=body.kind == "repo"), uploaded=True)


@router.post("/portfolio/github", response_model=dict)
async def import_github(username: str, u: User = Depends(current_user)):
    """Import the user's public repos (README + code) through the official GitHub MCP server, then re-index."""
    from common.settings import get_settings
    from rag.corpus import invalidate
    from rag.ingest.github_mcp import ingest_github_user

    if not get_settings().github_token:
        raise HTTPException(400, "GITHUB_TOKEN is not configured on the server")
    try:
        items = await ingest_github_user(username.strip().lstrip("@"), persona=u.persona_key or "custom")
    except Exception as e:
        raise HTTPException(502, f"GitHub MCP unavailable: {type(e).__name__}") from e
    with session() as s:
        for it in items:
            s.add(PortfolioUpload(user_id=u.id, kind="repo", title=it.title, content=it.text[:50000],
                                  meta={"project": it.project, "date": it.date, "source": it.source}))
    invalidate(u.id)
    return {"imported": len(items), "repos": sorted({i.project for i in items})}


@router.delete("/portfolio/{item_id}", response_model=dict)
def delete_upload(item_id: str, u: User = Depends(current_user)):
    from rag.corpus import invalidate

    with session() as s:
        p = s.get(PortfolioUpload, item_id.removeprefix("upload-"))
        if not p or p.user_id != u.id:
            raise HTTPException(404, "not your upload")
        p.deleted = True
    invalidate(u.id)
    return {"ok": True}


_status_cache: dict = {}


@router.get("/system/status", response_model=SystemStatus)
async def status(u: User = Depends(current_user)):
    s = get_settings()
    up, err, pol = "up", None, None
    try:
        r = await asyncio.wait_for(Toolbox("compliance", u.id, max_retries=0, timeout_s=6).call("marketplace", "get_policy", {}), 8)
        pol = r.get("version")
    except Exception as e:
        up, err = "down", str(e)[:200]
    return SystemStatus(api="up", marketplace=up, marketplace_mode=config()["marketplace"]["mode"], marketplace_error=err,
                        policy_version=pol, model_profile=profile_name(), llm_offline=s.llm_offline or os.getenv("LLM_OFFLINE") == "1",
                        tracing=langfuse() is not None, worker="arq" if s.redis_url else "in-process")


@router.post("/demo/tick", response_model=dict)
async def demo_tick(minutes: int = 120, u: User = Depends(current_user)):
    """Demo control: advance GigSim's simulated clock so client reactions arrive (GigSim only)."""
    import httpx

    s = get_settings()
    if config()["marketplace"]["mode"] != "gigsim":
        raise HTTPException(400, "only available against GigSim")
    if os.getenv("GIGSIM_INPROCESS") == "1":
        from gigsim.app import app as gs

        transport = httpx.ASGITransport(app=gs)
    else:
        transport = None
    async with httpx.AsyncClient(transport=transport, timeout=15) as h:
        r = await h.post(f"{s.gigsim_base_url}/v1/admin/tick", params={"minutes": minutes}, headers={"X-Admin-Token": s.gigsim_admin_token})
    from worker.tasks import sync_pipeline

    return {**r.json(), **(await sync_pipeline(u.id))}
