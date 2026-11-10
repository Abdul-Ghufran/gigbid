from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from apps.api.auth.users import current_user
from apps.api.streaming import stream_run
from common.db import AuditLog, Run, RunEvent, User, session
from common.tracing import trace_url

router = APIRouter(prefix="/runs", tags=["runs"])


def _run(r: Run) -> dict:
    return {"run_id": r.id, "graph": r.graph, "thread_id": r.thread_id, "trace_id": r.trace_id, "status": r.status,
            "error": r.error, "tokens": r.tokens, "cost_usd": r.cost_usd, "latency_s": r.latency_s,
            "created_at": r.created_at.isoformat(), "trace_url": trace_url(r.trace_id)}


@router.get("", response_model=list[dict])
def runs(limit: int = 50, u: User = Depends(current_user)):
    with session() as s:
        return [_run(r) for r in s.query(Run).filter_by(user_id=u.id).order_by(Run.created_at.desc()).limit(limit).all()]


@router.get("/{run_id}", response_model=dict)
def run(run_id: str, u: User = Depends(current_user)):
    with session() as s:
        r = s.get(Run, run_id)
        if not r or r.user_id != u.id:
            raise HTTPException(404, "run not found")
        events = [{"id": e.id, "kind": e.kind, "node": e.node, "payload": e.payload, "ts": e.created_at.isoformat()}
                  for e in s.query(RunEvent).filter_by(run_id=run_id, user_id=u.id).order_by(RunEvent.id).all()]
        audit = [{"ts": a.ts.isoformat(), "server": a.server, "tool": a.tool, "ok": a.ok, "arguments": a.arguments}
                 for a in s.query(AuditLog).filter_by(trace_id=r.trace_id, user_id=u.id).order_by(AuditLog.id).all()]
        return {**_run(r), "events": events, "audit": audit}


@router.get("/{run_id}/stream")
def stream(run_id: str, u: User = Depends(current_user), last_event_id: str | None = Header(default=None)):
    return stream_run(run_id, u.id, int(last_event_id or 0))
