"""Node runtime: budgets, timeouts, execution trace and streaming for every graph node.

`@node("writer")` wraps a node function so that it
  * refuses to run once the thread's step or token budget is spent (-> visible "needs_attention" state),
  * times out (per-node timeout from config) and lets LangGraph's RetryPolicy retry it,
  * records node_start / node_end / error events with tokens, cost and latency into the execution trace
    (RunEvent rows via the sink set by the runner + LangGraph custom stream for live UI progress),
  * adds `steps` / `tokens` deltas to state (reducers).
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import time
from typing import Any, Callable

from agent.config import config
from agent.llm import current_ledger
from common.security import mask_obj

event_sink: contextvars.ContextVar[Callable[[str, str, dict], None] | None] = contextvars.ContextVar("event_sink", default=None)

NODE_TIMEOUT_S = {"writer": 120, "critic": 90, "verifier": 120, "liaison": 90, "fit_matcher": 90}


class BudgetExceeded(Exception):
    pass


def emit(kind: str, node: str, payload: dict | None = None):
    payload = mask_obj(payload or {})
    sink = event_sink.get()
    if sink:
        try:
            sink(kind, node, payload)
        except Exception:
            pass
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()({"kind": kind, "node": node, **payload})
    except Exception:
        pass


def tool_tracer(node_name: str):
    """Callback for Toolbox: every MCP tool call (name, arguments, result/error, ms) goes to the trace."""

    def cb(server, tool, args, result, ms):
        short = result if len(str(result)) < 1500 else {"truncated": True, "keys": list(result)[:10] if isinstance(result, dict) else None}
        emit("tool_call", node_name, {"server": server, "tool": tool, "args": args, "result": short, "ms": ms})

    return cb


def budgets() -> dict:
    return config()["budgets"]


def node(name: str, budget_key: str = "max_tokens_per_job"):
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(state: dict, *a, **kw) -> dict[str, Any]:
            b = budgets()
            if state.get("status") == "needs_attention":
                return {}
            if state.get("steps", 0) >= b["max_graph_steps"]:
                emit("error", name, {"error": "step budget exceeded"})
                return {"status": "needs_attention", "attention": [f"Step budget ({b['max_graph_steps']}) exceeded before {name}."]}
            if state.get("tokens", 0) >= b[budget_key]:
                emit("error", name, {"error": "token budget exceeded"})
                return {"status": "needs_attention", "attention": [f"Token budget ({b[budget_key]}) exceeded before {name}."]}
            led = current_ledger()
            tok0, cost0 = led.tokens, led.cost_usd
            t0 = time.perf_counter()
            emit("node_start", name, {})
            try:
                out = await asyncio.wait_for(fn(state, *a, **kw), NODE_TIMEOUT_S.get(name, 60))
            except asyncio.TimeoutError:
                emit("error", name, {"error": "timeout"})
                raise
            except Exception as e:
                emit("error", name, {"error": f"{type(e).__name__}: {e}"[:500]})
                raise
            out = dict(out or {})
            dt = time.perf_counter() - t0
            dtok = led.tokens - tok0
            out["steps"] = out.get("steps", 0) + 1
            out["tokens"] = out.get("tokens", 0) + dtok
            emit("node_end", name, {"latency_s": round(dt, 3), "tokens": dtok, "cost_usd": round(led.cost_usd - cost0, 6),
                                    "summary": _summary(out)})
            return out

        return wrapper

    return deco


def _summary(out: dict) -> dict:
    s = {}
    for k, v in out.items():
        if k in ("steps", "tokens"):
            continue
        if isinstance(v, dict):
            s[k] = {kk: vv for kk, vv in list(v.items())[:6] if not isinstance(vv, (list, dict)) or len(str(vv)) < 200}
        elif isinstance(v, (str, int, float, bool)):
            s[k] = v
    return s
