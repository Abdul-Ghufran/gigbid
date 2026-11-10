"""GigBid Workspace MCP server: calendar free slots, tentative interview holds and email drafts.

Backed by a documented local mock (deterministic working hours + busy blocks per user, holds and drafts
persisted in the `workspace_items` table).  Swapping in Google Calendar / Gmail only changes the
`_busy_blocks` / `_store` functions; the agent sees the same MCP tools either way.
"""
import datetime as dt
import hashlib
from typing import Annotated
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from common.settings import get_settings
from mcp_servers._shared import audited, current_user_id, http_auth_kwargs, run_server

mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative interview holds and email drafts for the freelancer.",
              **http_auth_kwargs(get_settings().mcp_workspace_url, ["workspace"]))

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
TraceId = Annotated[str, Field(default="", max_length=64)]
IdemKey = Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9:_\-.]+$")]


class Slot(BaseModel):
    start: str = Field(description="ISO-8601 start in the requested timezone")
    end: str
    label: str = Field(description="Human-friendly label, e.g. 'Tue 12 Nov, 3:00-3:30 PM PKT'")


class SlotList(BaseModel):
    timezone: str
    slots: list[Slot]


class Hold(BaseModel):
    id: str
    status: str = "tentative"
    start: str
    end: str
    title: str
    idempotent_replay: bool = False


class EmailDraft(BaseModel):
    id: str
    to: str
    subject: str
    body: str
    status: str = "draft"
    idempotent_replay: bool = False


def _busy_blocks(user: str, day: dt.date) -> list[tuple[int, int]]:
    """Mock calendar: deterministic busy hours per user/day (minutes from midnight)."""
    h = int(hashlib.sha256(f"{user}:{day.isoformat()}".encode()).hexdigest()[:8], 16)
    blocks = [(12 * 60, 13 * 60)]  # lunch
    blocks.append(((9 + h % 4) * 60, (10 + h % 4) * 60))
    if h % 3 == 0:
        blocks.append(((14 + h % 3) * 60, (15 + h % 3) * 60 + 30))
    return blocks


def _holds(user: str):
    from common.db import WorkspaceItem, session

    with session() as s:
        return [w.data for w in s.query(WorkspaceItem).filter_by(user_id=user, kind="hold").all()]


@mcp.tool(annotations=READ, title="Find free calendar slots")
@audited("workspace")
async def free_slots(
    days_ahead: Annotated[int, Field(ge=1, le=14)] = 5,
    duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
    timezone: Annotated[str, Field(max_length=64)] = "Asia/Karachi",
    max_slots: Annotated[int, Field(ge=1, le=10)] = 3,
    start_date: Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    trace_id: TraceId = "",
) -> SlotList:
    """Free interview slots in working hours (09:00-18:00, Mon-Fri), skipping busy blocks and existing holds."""
    tz = ZoneInfo(timezone)
    user = current_user_id()
    day = dt.date.fromisoformat(start_date) if start_date else (dt.datetime.now(tz) + dt.timedelta(days=1)).date()
    held = {(h["start"]) for h in _holds(user)}
    slots: list[Slot] = []
    for d in range(days_ahead):
        cur = day + dt.timedelta(days=d)
        if cur.weekday() >= 5:
            continue
        busy = _busy_blocks(user, cur)
        m = 10 * 60
        while m + duration_minutes <= 18 * 60 and len(slots) < max_slots:
            if not any(b0 < m + duration_minutes and m < b1 for b0, b1 in busy):
                start = dt.datetime.combine(cur, dt.time(m // 60, m % 60), tz)
                end = start + dt.timedelta(minutes=duration_minutes)
                if start.isoformat() not in held:
                    slots.append(Slot(start=start.isoformat(), end=end.isoformat(),
                                      label=f"{start:%a %d %b}, {start:%I:%M %p}-{end:%I:%M %p} {start.tzname()}"))
                    m += 150  # spread offered slots across the day
                    continue
            m += 30
        if len(slots) >= max_slots:
            break
    return SlotList(timezone=timezone, slots=slots)


def _store(kind: str, key: str, data: dict) -> tuple[dict, bool]:
    from common.db import WorkspaceItem, session

    user = current_user_id()
    with session() as s:
        prev = s.query(WorkspaceItem).filter_by(user_id=user, kind=kind, idempotency_key=key).first()
        if prev:
            return prev.data, True
        item = WorkspaceItem(user_id=user, kind=kind, data={}, idempotency_key=key)
        s.add(item)
        s.flush()
        item.data = {"id": item.id, **data}
        return item.data, False


@mcp.tool(annotations=WRITE, title="Create tentative interview hold")
@audited("workspace")
async def create_interview_hold(
    start: Annotated[str, Field(description="ISO-8601 start returned by free_slots")],
    end: Annotated[str, Field(description="ISO-8601 end")],
    title: Annotated[str, Field(min_length=3, max_length=200)],
    idempotency_key: IdemKey,
    trace_id: TraceId = "",
) -> Hold:
    """Place a TENTATIVE hold on the freelancer's own calendar (nothing is sent to the client)."""
    dt.datetime.fromisoformat(start)
    dt.datetime.fromisoformat(end)
    data, replay = _store("hold", idempotency_key, {"status": "tentative", "start": start, "end": end, "title": title})
    return Hold(**data, idempotent_replay=replay)


@mcp.tool(annotations=WRITE, title="Create email draft")
@audited("workspace")
async def create_email_draft(
    to: Annotated[str, Field(min_length=3, max_length=200)],
    subject: Annotated[str, Field(min_length=1, max_length=200)],
    body: Annotated[str, Field(min_length=1, max_length=6000)],
    idempotency_key: IdemKey,
    trace_id: TraceId = "",
) -> EmailDraft:
    """Create an email DRAFT in the freelancer's mailbox (never sends)."""
    data, replay = _store("email_draft", idempotency_key, {"to": to, "subject": subject, "body": body, "status": "draft"})
    return EmailDraft(**data, idempotent_replay=replay)


if __name__ == "__main__":
    from common.db import init_db

    init_db()
    run_server(mcp, 8093)
