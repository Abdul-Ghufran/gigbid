"""MCP client discipline (A6).

* Every agent gets only the tools it needs, filtered by name (ALLOWLIST).  Asking for anything else raises.
* Timeouts, bounded retries with exponential backoff for transient errors, and a clear degraded signal
  (`MarketplaceDown`) the graph turns into a queued "needs attention / retry" state and the UI shows as a banner.
* Transports:
    http   - MultiServerMCPClient over Streamable HTTP with a per-user signed bearer token (docker / deployed)
    memory - real MCP JSON-RPC over in-memory streams to the in-process FastMCP servers (tests, evals, laptop)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any

from common.security import sign_user_token
from common.settings import get_settings
from common.tracing import current_trace_id, user_id_var

ALLOWLIST: dict[str, dict[str, set[str]]] = {
    "scout": {"marketplace": {"search_jobs", "get_job"}},
    "analyst": {},
    "risk_assessor": {"marketplace": {"get_client_history"}},
    "fit_matcher": {"portfolio": {"search_evidence", "list_skills"}},
    "pricing": {"marketplace": {"get_market_stats", "get_connects_balance", "get_client_history"}},
    "writer": {"portfolio": {"search_evidence", "get_case_study"}},
    "verifier": {"portfolio": {"search_evidence"}},
    "critic": {"portfolio": {"search_evidence"}},
    "compliance": {"marketplace": {"get_policy"}},
    "submitter": {"marketplace": {"create_proposal_draft", "submit_proposal", "get_connects_balance"}},
    "liaison": {"marketplace": {"get_thread", "list_messages", "send_message", "get_job"},
                "workspace": {"free_slots", "create_interview_hold", "create_email_draft"}},
    "pipeline": {"marketplace": {"list_proposals", "list_events", "list_messages"}},
    # baselines for R&D question C get everything
    "react_baseline": {"marketplace": {"search_jobs", "get_job", "get_client_history", "get_market_stats", "get_connects_balance"},
                       "portfolio": {"search_evidence", "get_case_study", "list_skills"}},
}
TRANSIENT = ("marketplace_unavailable", "rate_limited", "timeout")


class ToolNotAllowed(Exception):
    pass


class ToolCallError(Exception):
    def __init__(self, server: str, tool: str, message: str):
        super().__init__(f"{server}.{tool}: {message}")
        self.server, self.tool, self.message = server, tool, message
        self.code = message.split(":", 1)[0].strip() if ":" in message else "tool_error"


class MarketplaceDown(ToolCallError):
    """Marketplace unreachable after retries: the graph parks the job and the UI shows degraded mode."""


def _servers():
    from mcp_servers.marketplace.server import mcp as m
    from mcp_servers.portfolio.server import mcp as p
    from mcp_servers.workspace.server import mcp as w

    return {"marketplace": m, "portfolio": p, "workspace": w}


class Toolbox:
    """Per-agent, per-user view of the MCP tool layer."""

    def __init__(self, agent: str, user_id: str, timeout_s: float = 30, max_retries: int = 2, on_call=None):
        if agent not in ALLOWLIST:
            raise ToolNotAllowed(f"unknown agent {agent}")
        self.agent, self.user_id = agent, user_id
        self.allowed = ALLOWLIST[agent]
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self.on_call = on_call  # callback(server, tool, args, result|error, ms) -> execution trace
        self.transport = os.getenv("MCP_TRANSPORT", get_settings().mcp_transport)

    def names(self) -> list[str]:
        return sorted(f"{s}.{t}" for s, ts in self.allowed.items() for t in ts)

    async def call(self, server: str, tool: str, args: dict | None = None) -> dict:
        if tool not in self.allowed.get(server, set()):
            raise ToolNotAllowed(f"agent '{self.agent}' may not call {server}.{tool}")
        args = {**(args or {}), "trace_id": current_trace_id()}
        last: ToolCallError | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                res = await asyncio.wait_for(self._raw_call(server, tool, args), self.timeout_s)
                self._trace(server, tool, args, res, t0)
                return res
            except asyncio.TimeoutError:
                last = ToolCallError(server, tool, "timeout: tool call exceeded timeout")
            except ToolCallError as e:
                last = e
            except Exception as e:  # connection refused, server process gone, ...
                last = ToolCallError(server, tool, f"marketplace_unavailable: {type(e).__name__}: {e}")
            self._trace(server, tool, args, {"error": last.message}, t0)
            if last.code not in TRANSIENT:
                raise last
            if attempt < self.max_retries:
                await asyncio.sleep(min(6.0, 0.5 * 2 ** attempt) * (0.5 + random.random()))
        if server == "marketplace":
            raise MarketplaceDown(server, tool, last.message if last else "unavailable")
        raise last  # type: ignore[misc]

    def _trace(self, server, tool, args, result, t0):
        if self.on_call:
            try:
                self.on_call(server, tool, args, result, round((time.perf_counter() - t0) * 1000))
            except Exception:
                pass

    async def _raw_call(self, server: str, tool: str, args: dict) -> dict:
        if self.transport == "http":
            return await self._http_call(server, tool, args)
        from mcp.shared.memory import create_connected_server_and_client_session as connect

        token = user_id_var.set(self.user_id)
        try:
            async with connect(_servers()[server]._mcp_server) as c:
                r = await c.call_tool(tool, args)
        finally:
            user_id_var.reset(token)
        return _unwrap(server, tool, r)

    async def _http_call(self, server: str, tool: str, args: dict) -> dict:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        s = get_settings()
        url = {"marketplace": s.mcp_marketplace_url, "portfolio": s.mcp_portfolio_url, "workspace": s.mcp_workspace_url}[server]
        tok = sign_user_token(self.user_id, [f"{server}:read", f"{server}:write"], ttl_s=600)
        headers = {"Authorization": f"Bearer {tok}", "X-Trace-Id": current_trace_id()}
        async with streamablehttp_client(url, headers=headers, timeout=self.timeout_s) as (r, w, _):
            async with ClientSession(r, w) as c:
                await c.initialize()
                res = await c.call_tool(tool, args)
        return _unwrap(server, tool, res)

    def langchain_tools(self):
        """LangChain StructuredTools (same allowlist) for tool-calling agents (ReAct / supervisor baselines)."""
        from langchain_core.tools import StructuredTool

        schemas = _tool_schemas()
        tools = []
        for server, names in self.allowed.items():
            for name in sorted(names):
                spec = schemas[(server, name)]

                async def _run(_server=server, _name=name, **kw):
                    try:
                        return json.dumps(await self.call(_server, _name, kw), default=str)[:6000]
                    except Exception as e:
                        return f"ERROR {e}"

                props = {k: v for k, v in spec["inputSchema"].get("properties", {}).items() if k != "trace_id"}
                schema = {"type": "object", "properties": props,
                          "required": [r for r in spec["inputSchema"].get("required", []) if r != "trace_id"]}
                tools.append(StructuredTool(name=name, description=spec["description"], args_schema=schema, coroutine=_run))
        return tools


def _unwrap(server, tool, r) -> dict:
    if r.isError:
        msg = " ".join(getattr(c, "text", "") for c in r.content) or "tool error"
        msg = msg.replace("Error executing tool " + tool + ": ", "")
        raise ToolCallError(server, tool, msg)
    if r.structuredContent is not None:
        return r.structuredContent
    try:
        return json.loads(r.content[0].text)
    except Exception:
        return {"text": " ".join(getattr(c, "text", "") for c in r.content)}


_SCHEMAS: dict | None = None


def _tool_schemas() -> dict:
    global _SCHEMAS
    if _SCHEMAS is None:
        out = {}
        for sname, srv in _servers().items():
            for t in asyncio.run(srv.list_tools()) if not _loop_running() else []:
                out[(sname, t.name)] = {"description": t.description, "inputSchema": t.inputSchema}
        _SCHEMAS = out
    return _SCHEMAS


async def load_schemas():
    global _SCHEMAS
    out = {}
    for sname, srv in _servers().items():
        for t in await srv.list_tools():
            out[(sname, t.name)] = {"description": t.description, "inputSchema": t.inputSchema}
    _SCHEMAS = out
    return out


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


