"""SSE bridge to LangGraph progress.

Graph nodes emit node_start / tool_call / node_end / interrupt events (LangGraph custom stream + RunEvent rows,
see agent/runtime.py).  Runs execute in the worker, so the API streams them from the RunEvent table: this works
across processes, survives page refreshes (the client passes Last-Event-ID) and replays history on reconnect.
"""
from __future__ import annotations

import asyncio
import json

from sse_starlette.sse import EventSourceResponse

from common.db import Run, RunEvent, session

TERMINAL = {"done", "failed", "interrupted"}


def stream_run(run_id: str, user_id: str, last_id: int = 0) -> EventSourceResponse:
    async def gen():
        cursor, idle = last_id, 0
        while True:
            with session() as s:
                evs = s.query(RunEvent).filter(RunEvent.run_id == run_id, RunEvent.user_id == user_id,
                                               RunEvent.id > cursor).order_by(RunEvent.id).limit(200).all()
                run = s.get(Run, run_id)
                status = run.status if run and run.user_id == user_id else "missing"
                rows = [(e.id, {"kind": e.kind, "node": e.node, "payload": e.payload, "ts": e.created_at.isoformat()}) for e in evs]
            for eid, data in rows:
                cursor = eid
                yield {"id": str(eid), "event": data["kind"], "data": json.dumps(data, default=str)}
            if status == "missing":
                yield {"event": "end", "data": json.dumps({"status": "missing"})}
                return
            if status in TERMINAL and not rows:
                idle += 1
                if idle > 2:
                    with session() as s:
                        r = s.get(Run, run_id)
                        yield {"event": "end", "data": json.dumps({"status": r.status, "error": r.error, "tokens": r.tokens,
                                                                   "cost_usd": r.cost_usd, "latency_s": r.latency_s})}
                    return
            await asyncio.sleep(0.5)

    return EventSourceResponse(gen(), ping=10)
