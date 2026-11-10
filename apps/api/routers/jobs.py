from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.runner import bid_thread, history, pending_interrupt, replay_from, thread_values
from apps.api.auth.users import current_user
from apps.api.schemas.models import JobCard, JobDetail, RunRef
from common.db import JobRecord, Run, User, session

router = APIRouter(prefix="/jobs", tags=["jobs"])


def card(j: JobRecord) -> JobCard:
    s = j.summary or {}
    return JobCard(job_id=j.job_id, title=j.job.get("title", ""), category=j.job.get("category"), budget=j.job.get("budget") or {},
                   connects_cost=s.get("connects_cost") or j.job.get("connects_cost"), status=j.status, pipeline_stage=j.pipeline_stage,
                   fit=s.get("fit"), risk=s.get("risk"), scam=s.get("scam"), flags=s.get("flags", []), decision=s.get("decision"),
                   price=s.get("price"), duplicate_of=j.duplicate_of, attention=s.get("attention", []) + ([s["error"]] if s.get("error") and j.status in ("needs_attention", "dead_letter", "queued_retry") else []),
                   updated_at=j.updated_at.isoformat())


def get_record(user_id: str, job_id: str) -> JobRecord:
    with session() as s:
        j = s.get(JobRecord, f"{user_id}:{job_id}")
        if not j:
            raise HTTPException(404, "job not in your inbox")
        s.expunge(j)
        return j


@router.get("", response_model=list[JobCard])
def inbox(status: str | None = None, decision: str | None = None, include_duplicates: bool = False,
          sort: str = Query("fit", pattern="^(fit|recent|price)$"), u: User = Depends(current_user)):
    with session() as s:
        q = s.query(JobRecord).filter(JobRecord.user_id == u.id)
        if status:
            q = q.filter(JobRecord.status == status)
        rows = [card(j) for j in q.all() if include_duplicates or j.status != "duplicate"]
    if decision:
        rows = [r for r in rows if r.decision == decision]
    key = {"fit": lambda r: (r.status != "awaiting_approval", -(r.fit or -1), r.updated_at),
           "recent": lambda r: r.updated_at, "price": lambda r: -(r.price or 0)}[sort]
    rows.sort(key=key, reverse=(sort == "recent"))
    return rows


@router.get("/{job_id}", response_model=JobDetail)
async def detail(job_id: str, u: User = Depends(current_user)):
    j = get_record(u.id, job_id)
    v = {}
    pend = None
    if j.thread_id:
        v = await thread_values(j.thread_id)
        pend = await pending_interrupt(j.thread_id)
    with session() as s:
        runs = [{"run_id": r.id, "status": r.status, "trace_id": r.trace_id, "tokens": r.tokens, "cost_usd": r.cost_usd,
                 "latency_s": r.latency_s, "created_at": r.created_at.isoformat(), "error": r.error}
                for r in s.query(Run).filter_by(user_id=u.id, thread_id=bid_thread(u.id, job_id)).order_by(Run.created_at.desc()).all()]
    return JobDetail(card=card(j), job=v.get("job") or j.job, analyses=v.get("analyses", {}), decision=v.get("decision", {}),
                     price=v.get("price", {}), draft=v.get("draft"), verification=v.get("verification"),
                     critiques=v.get("critiques", []), compliance=v.get("compliance"), approvals=v.get("approvals", []),
                     submission=v.get("submission"), pending_approval=pend, runs=runs, summary=j.summary or {})


@router.post("/{job_id}/analyze", response_model=RunRef)
async def analyze(job_id: str, force_bid: bool = False, u: User = Depends(current_user)):
    get_record(u.id, job_id)
    from worker.tasks import start_bid

    rid = await start_bid(u.id, job_id, force_bid=force_bid)
    with session() as s:
        return RunRef(run_id=rid, trace_id=s.get(Run, rid).trace_id)


@router.post("/{job_id}/skip", response_model=JobCard)
def skip(job_id: str, reason: str = "", u: User = Depends(current_user)):
    with session() as s:
        j = s.get(JobRecord, f"{u.id}:{job_id}")
        if not j:
            raise HTTPException(404, "job not in your inbox")
        j.status = "skipped"
        j.summary = {**(j.summary or {}), "skip_reason": reason or "skipped by you", "decision": "skip"}
        s.flush()
        return card(j)


@router.post("/scout", response_model=dict)
async def scout_now(u: User = Depends(current_user)):
    from worker.tasks import scout_user, sync_pipeline

    a = await scout_user(u.id, force=True)
    b = await sync_pipeline(u.id)
    return {**a, **b}


@router.get("/{job_id}/history", response_model=list[dict])
async def job_history(job_id: str, u: User = Depends(current_user)):
    j = get_record(u.id, job_id)
    return await history(j.thread_id) if j.thread_id else []


@router.post("/{job_id}/replay", response_model=dict)
async def job_replay(job_id: str, checkpoint_id: str, u: User = Depends(current_user)):
    j = get_record(u.id, job_id)
    await replay_from(j.thread_id, checkpoint_id)
    return {"ok": True}
