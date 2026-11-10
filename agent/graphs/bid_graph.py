"""Bid graph (one thread per job), hand-written LangGraph StateGraph.

intake -> Send(analyst, risk_assessor, fit_matcher) in parallel -> decide -> pricing -> writer -> verifier ->
critic -(fail, max 2 revisions)-> writer ... -> compliance -> prepare_approval -> approval[interrupt] ->
  approve -> submit | edit -> record_edit -> compliance (re-check) -> ... | reject -> END
Any node can move the thread to `needs_attention` (budgets, blocks); routers then end the run visibly.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent.config import config
from agent.llm import LLMUnavailable
from agent.nodes import (
    analyst,
    approval,
    compliance,
    critic,
    decision,
    fit_matcher,
    pricing,
    risk_assessor,
    scout,
    verifier,
    writer,
)
from agent.state import BidState

RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0, max_interval=10.0,
                    retry_on=lambda e: isinstance(e, (LLMUnavailable, TimeoutError)))


def _attention(state) -> bool:
    return state.get("status") == "needs_attention"


def fan_out(state: BidState):
    if _attention(state):
        return END
    return [Send("analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


def after_decide(state: BidState):
    if _attention(state):
        return END
    return "pricing" if state["decision"]["action"] == "bid" else END


def after_pricing(state: BidState):
    return END if state.get("status") in ("watch", "needs_attention") else "writer"


def after_critic(state: BidState):
    if _attention(state):
        return END
    last = state["critiques"][-1]
    if not last["passed"] and state.get("revision", 1) <= config()["budgets"]["max_revisions"]:
        return "writer"
    return "compliance_guard"


def after_approval(state: BidState):
    a = state["approvals"][-1]["action"]
    if state.get("status") == "needs_attention":
        return END
    return {"approve": "submit", "edit": "record_edit", "reject": END}[a]


def build_bid_graph(checkpointer=None, store=None):
    g = StateGraph(BidState)
    g.add_node("intake", scout.intake, retry=RETRY)
    g.add_node("analyst", analyst.analyse, retry=RETRY)
    g.add_node("risk_assessor", risk_assessor.assess, retry=RETRY)
    g.add_node("fit_matcher", fit_matcher.match, retry=RETRY)
    g.add_node("decide", decision.decide)
    g.add_node("pricing", pricing.price, retry=RETRY)
    g.add_node("writer", writer.write, retry=RETRY)
    g.add_node("verifier", verifier.verify, retry=RETRY)
    g.add_node("critic", critic.critique, retry=RETRY)
    g.add_node("compliance_guard", compliance.comply, retry=RETRY)
    g.add_node("prepare_approval", approval.prepare_approval, retry=RETRY)
    g.add_node("approval", approval.approval)
    g.add_node("record_edit", approval.record_edit)
    g.add_node("submit", approval.submit, retry=RETRY)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    for n in ("analyst", "risk_assessor", "fit_matcher"):
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", after_decide, ["pricing", END])
    g.add_conditional_edges("pricing", after_pricing, ["writer", END])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance_guard", END])
    g.add_conditional_edges("compliance_guard", lambda s: END if _attention(s) and s.get("compliance", {}).get("status") != "block" else "prepare_approval",
                            ["prepare_approval", END])
    g.add_conditional_edges("prepare_approval", lambda s: END if _attention(s) else "approval", ["approval", END])
    g.add_conditional_edges("approval", after_approval, ["submit", "record_edit", END])
    g.add_edge("record_edit", "compliance_guard")
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store)
