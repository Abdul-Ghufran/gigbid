"""Long-term memory in a LangGraph store (Postgres in production, SQLite / in-memory locally).

Namespaces
  ("style", user_id)              key = pattern       value = promoted style rule
  ("outcome", user_id, category)  key = "summary"     value = {reply_rate, n, lessons}
Only `promotion_rules` writes here (via refresh_*); the UI can list and delete items.
"""
from __future__ import annotations

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from agent.memory import promotion_rules as rules

_STORE: BaseStore | None = None


def set_store(store: BaseStore):
    global _STORE
    _STORE = store


def store() -> BaseStore:
    global _STORE
    if _STORE is None:
        _STORE = InMemoryStore()
    return _STORE


async def style_rules(user_id: str) -> list[dict]:
    items = await store().asearch(("style", user_id), limit=50)
    return [{"key": i.key, **i.value} for i in items]


async def outcome_lessons(user_id: str, category: str | None) -> dict:
    if not category:
        return {}
    it = await store().aget(("outcome", user_id, category), "summary")
    return it.value if it else {}


async def outcome_reply_rate(user_id: str, category: str | None) -> float | None:
    v = await outcome_lessons(user_id, category)
    return v.get("reply_rate") if v else None


async def refresh_style(user_id: str) -> list[dict]:
    """Re-run the style promotion rule over the user's raw edits; write only what passes."""
    from common.db import Edit, session

    with session() as s:
        edits = [{"job_id": e.job_id, "before": e.before, "after": e.after, "created_at": e.created_at}
                 for e in s.query(Edit).filter_by(user_id=user_id).all()]
    promoted = rules.promote_style(edits)
    deleted = {i.key for i in await store().asearch(("style_deleted", user_id), limit=200)}
    for r in promoted:
        if r["key"] in deleted:  # the user deleted it in the UI: never re-promote
            continue
        await store().aput(("style", user_id), r["key"], {k: v for k, v in r.items() if k != "key"})
    return promoted


async def refresh_outcomes(user_id: str) -> dict:
    from common.db import JobRecord, session

    with session() as s:
        rows = []
        for j in s.query(JobRecord).filter_by(user_id=user_id).all():
            stage = j.pipeline_stage
            if stage in (None, "drafted", "submitted", "viewed") or not j.summary.get("features"):
                continue
            rows.append({"category": j.job.get("category"), "replied": stage in ("replied", "interview", "hired"),
                         "features": j.summary["features"]})
    promoted = rules.promote_outcomes(rows)
    for cat, v in promoted.items():
        await store().aput(("outcome", user_id, cat), "summary", v)
    return promoted


async def list_memory(user_id: str) -> dict:
    style = await style_rules(user_id)
    outcome = []
    for it in await store().asearch(("outcome", user_id), limit=50):
        outcome.append({"namespace": list(it.namespace), "key": it.key, **it.value})
    return {"style": style, "outcome": outcome}


async def delete_memory(user_id: str, kind: str, key: str, category: str | None = None):
    if kind == "style":
        await store().adelete(("style", user_id), key)
        await store().aput(("style_deleted", user_id), key, {"deleted": True})
    else:
        await store().adelete(("outcome", user_id, category or key), "summary")
