"""Graph state (C2).

Three things are kept apart:
  * STATE (below): only what this job / conversation needs right now - typed fields per stage.
  * EXECUTION TRACE: every node, tool call, argument, result and LLM generation goes to the RunEvent table,
    the MCP audit log and Langfuse (agent/runtime.py) - never into state.
  * LONG-TERM MEMORY: promoted knowledge only, in the LangGraph store (agent/memory/).
Reducers are used wherever the parallel branches (analyst, risk, fit) write.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def keep_last(a, b):
    return b if b is not None else a


class BidState(TypedDict, total=False):
    # identity / context
    user_id: str
    persona: str
    job_id: str
    trace_id: str
    settings: dict  # rates, floor, connects budget, autonomy (snapshot at run start)
    force_bid: bool
    # stage outputs (hand-off objects serialised as dicts)
    job: dict
    analyses: Annotated[dict, merge_dicts]  # {"job_spec": ..., "risk": ..., "fit": ...} written by parallel branches
    evidence: Annotated[dict, merge_dicts]  # item_id -> EvidenceRef (union of what fit/writer retrieved)
    decision: dict
    price: dict
    draft: dict
    verification: dict
    critiques: Annotated[list, operator.add]
    compliance: dict
    preview: dict  # dry_run previews shown on the approval screen
    approvals: Annotated[list, operator.add]  # every human decision (approve / edit / reject)
    submission: dict
    outcome: dict
    # control
    revision: int
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    status: str  # running | skipped | watch | awaiting_approval | submitted | rejected | needs_attention | dead_letter
    attention: Annotated[list, operator.add]  # reasons shown in the UI
    errors: Annotated[list, operator.add]


class ConversationState(TypedDict, total=False):
    user_id: str
    persona: str
    thread_id: str
    job_id: str
    trace_id: str
    settings: dict
    messages: list[dict]
    new_messages: list[dict]
    job: dict
    intent: dict
    slots: list[dict]
    reply: dict
    compliance: dict
    preview: dict
    approvals: Annotated[list, operator.add]
    sent: dict
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    status: str
    attention: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]


def as_dict(obj: Any) -> Any:
    return obj.model_dump() if hasattr(obj, "model_dump") else obj
