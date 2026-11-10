from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from apps.api.auth.token_store import save_account, upwork_authorize_url, upwork_callback
from apps.api.auth.users import check_password, create_user, current_user, issue_token
from apps.api.schemas.models import AuthOut, LoginIn, OnboardingIn, RegisterIn, UserOut
from common.db import User, UserSettings, session
from common.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

DEFAULT_SEARCHES = {
    "ai": [{"name": "LLM & RAG", "query": "", "category": "ai", "skills": ["RAG", "LangChain", "NLP"]},
           {"name": "Classical ML", "query": "", "category": "ai", "skills": ["scikit-learn", "XGBoost", "forecasting"]}],
    "web": [{"name": "React / Next.js", "query": "", "category": "web", "skills": ["React", "Next.js", "TypeScript"]},
            {"name": "Python backends", "query": "", "category": "web", "skills": ["Django", "Celery", "PostgreSQL"]}],
    "data": [{"name": "BI dashboards", "query": "", "category": "data", "skills": ["Power BI", "Tableau", "Looker"]},
             {"name": "SQL & warehouses", "query": "", "category": "data", "skills": ["SQL", "dbt", "BigQuery"]}],
}


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, persona_key=u.persona_key, onboarded=u.onboarded)


@router.post("/register", response_model=AuthOut)
def register(body: RegisterIn):
    u = create_user(body.email, body.password, body.display_name)
    return AuthOut(token=issue_token(u.id), user=user_out(u))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn):
    with session() as s:
        u = s.query(User).filter_by(email=body.email.lower()).first()
        if not u or not check_password(body.password, u.password_hash):
            raise HTTPException(401, "wrong email or password")
        s.expunge(u)
    return AuthOut(token=issue_token(u.id), user=user_out(u))


@router.get("/me", response_model=UserOut)
def me(u: User = Depends(current_user)):
    return user_out(u)


def onboard_user(user_id: str, body: OnboardingIn):
    with session() as s:
        u = s.get(User, user_id)
        u.persona_key = body.persona_key
        u.onboarded = True
        us = s.get(UserSettings, user_id) or UserSettings(user_id=user_id)
        us.hourly_rate, us.min_project, us.weekly_connects_budget = body.hourly_rate, body.min_project, body.weekly_connects_budget
        searches = [x.model_dump() for x in body.saved_searches] or DEFAULT_SEARCHES.get(body.persona_key or "web", [])
        us.saved_searches = [{**x, "id": x.get("id") or uuid.uuid4().hex[:8], "interval_minutes": x.get("interval_minutes", 20),
                              "limit": x.get("limit", 6)} for x in searches]
        us.filters = us.filters or {}
        s.merge(us)
    if body.marketplace == "gigsim":
        # GigSim accounts are the persona sandboxes; own profiles get the web sandbox account
        save_account(user_id, "gigsim", {"access_token": f"gigsim-dev-token-{body.persona_key or 'web'}"})


@router.post("/onboarding", response_model=UserOut)
async def onboarding(body: OnboardingIn, u: User = Depends(current_user)):
    onboard_user(u.id, body)
    from worker.tasks import scout_user

    try:
        await scout_user(u.id, force=True)
    except Exception:
        pass  # marketplace may be down; the worker retries on schedule
    with session() as s:
        return user_out(s.get(User, u.id))


@router.get("/upwork/start")
async def upwork_start(request: Request, u: User = Depends(current_user)):
    redirect = f"{get_settings().public_api_url}/api/auth/upwork/callback"
    try:
        return {"authorize_url": await upwork_authorize_url(u.id, redirect)}
    except Exception as e:
        raise HTTPException(502, f"Upwork OAuth discovery failed: {type(e).__name__}") from e


@router.get("/upwork/callback")
async def upwork_cb(code: str, state: str):
    await upwork_callback(code, state)
    return RedirectResponse(f"{get_settings().public_web_url}/settings?connected=upwork")
