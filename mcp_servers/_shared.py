"""Helpers shared by GigBid's own MCP servers: bearer auth, user resolution, audit, transport selection."""
from __future__ import annotations

import argparse
import functools
import inspect
import json
import os
import time

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings

from common.security import verify_user_token
from common.tracing import trace_id_var


class SignedTokenVerifier(TokenVerifier):
    """Accepts GigBid-signed per-user tokens (HMAC, short-lived).  client_id carries the user id."""

    async def verify_token(self, token: str) -> AccessToken | None:
        p = verify_user_token(token)
        if not p:
            return None
        return AccessToken(token=token, client_id=p["sub"], scopes=p.get("scopes", []), expires_at=p["exp"])


def http_auth_kwargs(public_url: str, scopes: list[str]) -> dict:
    """Only enable bearer auth when the server is served over HTTP (stdio is a local, trusted pipe)."""
    if os.getenv("MCP_HTTP") != "1":
        return {}
    return {"token_verifier": SignedTokenVerifier(),
            "auth": AuthSettings(issuer_url=os.getenv("PUBLIC_API_URL", "http://localhost:8000"),
                                 resource_server_url=public_url, required_scopes=scopes)}


def current_user_id() -> str:
    """User for this call: from the verified bearer token over HTTP, else MCP_USER_ID (stdio / tests)."""
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token

        tok = get_access_token()
        if tok:
            return tok.client_id
    except Exception:
        pass
    from common.tracing import user_id_var

    return user_id_var.get() or os.getenv("MCP_USER_ID", "local")


def audited(server: str, log_reads: bool = True):
    """Decorator: write (user, tool, arguments, result, trace id) to the append-only audit log."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            trace_id = kwargs.get("trace_id") or ""
            if trace_id:
                trace_id_var.set(trace_id)
            uid = current_user_id()
            t0 = time.perf_counter()
            ok, result = True, None
            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception as e:
                ok, result = False, {"error": f"{type(e).__name__}: {e}"}
                raise
            finally:
                if os.getenv("AUDIT_DISABLED") != "1" and (log_reads or not ok or fn.__name__ in WRITE_TOOLS):
                    try:
                        from common.db import audit

                        dumped = result.model_dump() if hasattr(result, "model_dump") else result
                        text = json.dumps(dumped, default=str)
                        summary = dumped if len(text) < 4000 else {"truncated": True, "chars": len(text)}
                        audit(uid, server, fn.__name__, {k: v for k, v in kwargs.items()},
                              {"result": summary, "ms": round((time.perf_counter() - t0) * 1000)}, trace_id, ok)
                    except Exception:
                        pass

        wrapper.__signature__ = inspect.signature(fn)
        return wrapper

    return deco


WRITE_TOOLS = {"create_proposal_draft", "submit_proposal", "send_message", "create_interview_hold", "create_email_draft"}


def run_server(mcp, default_port: int):
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", default=os.getenv("MCP_TRANSPORT_MODE", "stdio"), choices=["stdio", "http"])
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", default_port)))
    a = ap.parse_args()
    if a.transport == "http":
        import uvicorn

        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=a.port)
    else:
        mcp.run("stdio")
