from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.mcp_client import Toolbox
from agent.runner import conv_thread, pending_interrupt, thread_values
from apps.api.auth.users import current_user
from apps.api.schemas.models import ConversationCard, DecisionIn, RunRef
from common.db import Conversation, JobRecord, Run, User, session

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=list[ConversationCard])
def conversations(u: User = Depends(current_user)):
    with session() as s:
        out = []
        for c in s.query(Conversation).filter_by(user_id=u.id).order_by(Conversation.updated_at.desc()).all():
            j = s.get(JobRecord, f"{u.id}:{c.job_id}")
            out.append(ConversationCard(thread_id=c.marketplace_thread_id, job_id=c.job_id, job_title=(j.job.get("title") if j else c.job_id),
                                        status=c.status, intent=(c.summary or {}).get("intent"),
                                        last_message=(c.summary or {}).get("reply"), updated_at=c.updated_at.isoformat()))
        return out


@router.get("/{thread_id}", response_model=dict)
async def thread(thread_id: str, u: User = Depends(current_user)):
    with session() as s:
        if not s.get(Conversation, f"{u.id}:{thread_id}"):
            raise HTTPException(404, "conversation not found")
    tb = Toolbox("liaison", u.id)
    t = await tb.call("marketplace", "get_thread", {"thread_id": thread_id})
    th = conv_thread(u.id, thread_id)
    return {"thread": t, "pending_approval": await pending_interrupt(th, "conv"), "state": {
        k: v for k, v in (await thread_values(th, "conv")).items() if k in ("intent", "reply", "slots", "status", "sent", "compliance")}}


@router.post("/{thread_id}/decision", response_model=RunRef)
async def decide(thread_id: str, body: DecisionIn, u: User = Depends(current_user)):
    th = conv_thread(u.id, thread_id)
    if not await pending_interrupt(th, "conv"):
        raise HTTPException(409, "nothing to approve")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    from worker.tasks import start_conversation

    rid = await start_conversation(u.id, thread_id, resume=body.model_dump(exclude_none=True))
    with session() as s:
        c = s.get(Conversation, f"{u.id}:{thread_id}")
        c.status = "sending" if body.action == "approve" else c.status
        return RunRef(run_id=rid, trace_id=s.get(Run, rid).trace_id)


@router.post("/sync", response_model=dict)
async def sync(u: User = Depends(current_user)):
    from worker.tasks import sync_pipeline

    return await sync_pipeline(u.id)
