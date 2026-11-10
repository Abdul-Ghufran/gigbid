"""One trace id flows UI -> API -> graph -> MCP servers -> audit log.

The id lives in a contextvar; HTTP calls forward it as `X-Trace-Id`, MCP calls pass it as the
`trace_id` tool argument / meta.  Langfuse is used when keys are configured; every span is PII-masked.
"""
from __future__ import annotations

import contextvars
import logging
import uuid

from common.security import mask_obj, mask_pii
from common.settings import get_settings

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str:
    tid = trace_id_var.get()
    if not tid:
        tid = new_trace_id()
        trace_id_var.set(tid)
    return tid


class PIIMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_pii(str(record.msg))
        if record.args:
            record.args = tuple(mask_obj(a) for a in record.args) if isinstance(record.args, tuple) else mask_obj(record.args)
        return True


def configure_logging(level=logging.INFO):
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(PIIMaskingFilter())


_langfuse = None


def langfuse():
    """Return a Langfuse client or None when tracing keys are not configured."""
    global _langfuse
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    if _langfuse is None:
        from langfuse import Langfuse

        _langfuse = Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host,
                             mask=lambda data, **_: mask_obj(data))
    return _langfuse


def trace_url(trace_id: str) -> str | None:
    if not langfuse():
        return None
    return f"{get_settings().langfuse_host}/trace/{trace_id}"
