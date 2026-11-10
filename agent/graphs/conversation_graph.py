"""Conversation graph (one thread per client conversation).

read -> intent -> plan_reply (calendar slots for interview requests) -> draft -> preview(dry_run) ->
approval[interrupt] -> approve: send (+ tentative holds) | edit: re-check compliance -> preview -> approval | reject
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.graphs.bid_graph import RETRY
from agent.nodes import client_liaison as cl
from agent.runtime import node
from agent.state import ConversationState


@node("liaison_recheck", budget_key="max_tokens_per_conversation_turn")
async def _recheck(state):
    return await cl.recheck(state)


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    g.add_node("read", cl.read_thread, retry=RETRY)
    g.add_node("classify_intent", cl.classify, retry=RETRY)
    g.add_node("plan_reply", cl.plan, retry=RETRY)
    g.add_node("draft_reply", cl.draft, retry=RETRY)
    g.add_node("preview_reply", cl.preview, retry=RETRY)
    g.add_node("approval", cl.approval)
    g.add_node("recheck", _recheck)
    g.add_node("send", cl.send, retry=RETRY)
    g.add_edge(START, "read")
    g.add_conditional_edges("read", lambda s: "classify_intent" if s.get("new_messages") else END, ["classify_intent", END])
    g.add_edge("classify_intent", "plan_reply")
    g.add_edge("plan_reply", "draft_reply")
    g.add_edge("draft_reply", "preview_reply")
    g.add_edge("preview_reply", "approval")
    g.add_conditional_edges("approval", lambda s: {"approve": "send", "edit": "recheck", "reject": END}[s["approvals"][-1]["action"]]
                            if s.get("status") != "needs_attention" else END, ["send", "recheck", END])
    g.add_edge("recheck", "preview_reply")
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store)
