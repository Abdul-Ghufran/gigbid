"""Proposal studio + approvals.  Decisions resume the interrupted graph thread (C5); pending approvals are
read from the checkpoint, so a page refresh or API restart never loses one."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from agent import llm
from agent.runner import pending_interrupt
from apps.api.auth.users import current_user
from apps.api.routers.jobs import get_record
from apps.api.schemas.models import DecisionIn, RegenerateIn, RegenerateOut, RunRef
from common.db import JobRecord, Run, User, session

router = APIRouter(prefix="/proposals", tags=["proposals"])


@router.get("/pending", response_model=list[dict])
async def pending(u: User = Depends(current_user)):
    with session() as s:
        rows = [(j.job_id, j.thread_id, j.job.get("title")) for j in s.query(JobRecord).filter_by(user_id=u.id, status="awaiting_approval").all()]
    out = []
    for job_id, thread, title in rows:
        p = await pending_interrupt(thread) if thread else None
        if p:
            out.append({"job_id": job_id, "title": title, "blocked": p.get("blocked"), "price": p.get("price", {}).get("amount"),
                        "connects_cost": p.get("preview", {}).get("connects_cost")})
    return out


@router.get("/{job_id}", response_model=dict)
async def get_pending(job_id: str, u: User = Depends(current_user)):
    j = get_record(u.id, job_id)
    p = await pending_interrupt(j.thread_id) if j.thread_id else None
    if not p:
        raise HTTPException(404, "no proposal waiting for approval")
    return p


@router.post("/{job_id}/decision", response_model=RunRef)
async def decide(job_id: str, body: DecisionIn, u: User = Depends(current_user)):
    j = get_record(u.id, job_id)
    if not j.thread_id or not await pending_interrupt(j.thread_id):
        raise HTTPException(409, "nothing to approve (already decided?)")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    from worker.tasks import resume_bid

    with session() as s:
        rec = s.get(JobRecord, j.id)
        rec.status = {"approve": "submitting", "edit": "rechecking", "reject": "rejected"}[body.action]
    rid = await resume_bid(u.id, job_id, {**body.model_dump(exclude_none=True), "user_id": u.id})
    with session() as s:
        return RunRef(run_id=rid, trace_id=s.get(Run, rid).trace_id)


@router.post("/{job_id}/regenerate", response_model=RegenerateOut)
async def regenerate_paragraph(job_id: str, body: RegenerateIn, u: User = Depends(current_user)):
    """Rewrite one paragraph with the writer model, grounded in the same evidence.  Not saved until the user
    submits it as an edit (which re-runs compliance)."""
    j = get_record(u.id, job_id)
    p = await pending_interrupt(j.thread_id) if j.thread_id else None
    if not p:
        raise HTTPException(404, "no draft")
    paras = [x for x in re.split(r"\n\s*\n", p["draft"]["cover_letter"]) if x.strip()]
    if body.paragraph_index >= len(paras):
        raise HTTPException(422, "no such paragraph")
    ev = "\n".join(f"[{k}] {v['title']}: {v['snippet'][:300]}" for k, v in (p.get("evidence") or {}).items())
    from agent.config import prompt, render

    pr = prompt("writer")
    try:
        new = await llm.text("writer", render(pr["system"], min_words="20", max_words="90", style_rules=""),
                             f"Rewrite ONLY this paragraph of a proposal{(' - ' + body.instruction) if body.instruction else ''}. "
                             f"Keep every claim grounded with [item-id] citations from the evidence; return the paragraph only.\n\n"
                             f"PARAGRAPH:\n{paras[body.paragraph_index]}\n\nEVIDENCE:\n{ev}", max_tokens=400)
    except Exception:
        new = paras[body.paragraph_index]
    paras[body.paragraph_index] = new.strip()
    return RegenerateOut(paragraph=new.strip(), cover_letter="\n\n".join(paras))
