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
_project_id: str | None = None


def _keys() -> tuple[str, str, str]:
    """Keys pasted into a dashboard often carry stray spaces/newlines or quotes; the host must not end with '/'."""
    s = get_settings()
    clean = lambda v: (v or "").strip().strip('"').strip("'").strip()  # noqa: E731
    return clean(s.langfuse_public_key), clean(s.langfuse_secret_key), clean(s.langfuse_host).rstrip("/") or "https://cloud.langfuse.com"


def langfuse():
    """Return a Langfuse client or None when tracing keys are not configured."""
    global _langfuse
    pk, sk, host = _keys()
    if not (pk and sk):
        return None
    if _langfuse is None:
        from langfuse import Langfuse

        _langfuse = Langfuse(public_key=pk, secret_key=sk, host=host, mask=lambda data, **_: mask_obj(data))
    return _langfuse


def check_langfuse() -> str:
    """Startup self-check (blocking, run it in a thread): says in the log whether traces will actually arrive."""
    global _project_id
    pk, sk, host = _keys()
    if not (pk and sk):
        return "Langfuse tracing OFF: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set"
    if not pk.startswith("pk-lf-") or not sk.startswith("sk-lf-"):
        return "Langfuse tracing MISCONFIGURED: public key must start with pk-lf- and secret key with sk-lf- (swapped?)"
    try:
        proj = langfuse().client.projects.get()
        _project_id = proj.data[0].id if proj.data else None
    except Exception as e:  # noqa: BLE001
        return (f"Langfuse tracing FAILED auth against {host}: {type(e).__name__} {str(e)[:160]} - check the keys and that "
                "LANGFUSE_HOST matches the region of your project (EU https://cloud.langfuse.com, US https://us.cloud.langfuse.com)")
    if not _project_id:
        return f"Langfuse tracing FAILED: no project found for these keys on {host}"
    return f"Langfuse tracing ON: {host} project {_project_id}"


def trace_url(trace_id: str) -> str | None:
    if not langfuse():
        return None
    host = _keys()[2]
    return f"{host}/project/{_project_id}/traces/{trace_id}" if _project_id else f"{host}/trace/{trace_id}"
