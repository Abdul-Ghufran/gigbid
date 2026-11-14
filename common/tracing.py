"""One trace id flows UI -> API -> graph -> MCP servers -> audit log.

The id lives in a contextvar; HTTP calls forward it as `X-Trace-Id`, MCP calls pass it as the
`trace_id` tool argument / meta.  Langfuse is used when keys are configured; every span is PII-masked.
"""
from __future__ import annotations

import base64
import contextvars
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from common.security import mask_obj, mask_pii
from common.settings import get_settings

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")
log = logging.getLogger("gigbid.tracing")


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
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _keys() -> tuple[str, str, str]:
    """Keys pasted into a dashboard often carry stray spaces/newlines or quotes; the host must not end with '/'."""
    s = get_settings()
    clean = lambda v: (v or "").strip().strip('"').strip("'").strip()  # noqa: E731
    return clean(s.langfuse_public_key), clean(s.langfuse_secret_key), clean(s.langfuse_host).rstrip("/") or "https://cloud.langfuse.com"


def otel_trace_id(trace_id: str) -> str:
    """OpenTelemetry needs 32 lowercase hex chars; any other id (e.g. a client-sent X-Trace-Id) is hashed into one."""
    t = (trace_id or "").lower().replace("-", "")
    return t if _HEX32.match(t) else hashlib.md5((trace_id or "").encode()).hexdigest()


def _span_id() -> str:
    return os.urandom(8).hex()


def _ns(ts: float) -> str:
    return str(int(ts * 1e9))


def _val(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, str) for x in v):
        return {"arrayValue": {"values": [{"stringValue": x} for x in v]}}
    return {"stringValue": v[:60000] if isinstance(v, str) else json.dumps(v, default=str)[:60000]}


def _attrs(d: dict) -> list[dict]:
    return [{"key": k, "value": _val(v)} for k, v in d.items() if v is not None]


class LangfuseOTel:
    """Minimal Langfuse exporter over OTLP/HTTP JSON (`/api/public/otel/v1/traces`).

    Langfuse Cloud (server v4) no longer ingests the legacy batch API that Python SDK v2 used, so traces sent that way
    were silently dropped.  One graph run = one trace: a root span (trace name, user, session = thread, public flag)
    with node (agent), MCP tool (tool), LLM (generation) and event observations as children.  Everything is PII-masked
    before it leaves the process; HTTP posts run on a background thread so the event loop never waits on Langfuse.
    """

    def __init__(self, pk: str, sk: str, host: str, public: bool = True):
        self.host, self.public = host, public
        self.endpoint = f"{host}/api/public/otel/v1/traces"
        self.headers = {"Authorization": "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode(),
                        "Content-Type": "application/json", "x-langfuse-ingestion-version": "4"}
        self._open: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="langfuse")
        self._futures: list = []
        self.last_error: str | None = None
        self.sent_spans = 0

    # ---- recording -------------------------------------------------------------------------------------------
    def trace(self, id: str, name: str, user_id: str | None = None, session_id: str | None = None,
              metadata: dict | None = None, input=None) -> str:
        tid = otel_trace_id(id)
        with self._lock:
            ctx = self._open.get(tid)
            if ctx:
                ctx["refs"] += 1
            else:
                self._open[tid] = {"refs": 1, "root": _span_id(), "start": time.time(), "name": name, "user": user_id,
                                   "session": session_id, "meta": metadata or {}, "input": input, "spans": []}
        return tid

    @staticmethod
    def _trace_attrs(ctx: dict) -> dict:
        a = {"langfuse.trace.name": ctx["name"], "langfuse.user.id": ctx["user"], "langfuse.session.id": ctx["session"],
             "langfuse.environment": os.getenv("APP_ENV") or None}
        a.update({f"langfuse.trace.metadata.{k}": v for k, v in (ctx["meta"] or {}).items() if v is not None})
        return a

    def _child(self, trace_id: str, name: str, start: float, end: float, attrs: dict):
        tid = otel_trace_id(trace_id)
        with self._lock:
            ctx = self._open.get(tid)
            if ctx:
                ctx["spans"].append({"name": name, "start": start, "end": max(end, start), "attrs": attrs})
                return
        # not inside a graph run (scripts, one-off API calls): send it on its own as a one-span trace
        self._submit([self._otlp_span(tid, _span_id(), None, name, start, max(end, start),
                                      {**attrs, "langfuse.trace.name": name, "langfuse.trace.public": self.public})])

    def generation(self, trace_id: str, name: str, model: str, input=None, output=None, usage: dict | None = None,
                   metadata: dict | None = None, latency_s: float = 0.0):
        end, u = time.time(), usage or {}
        tin, tout = int(u.get("input") or 0), int(u.get("output") or 0)
        attrs = {"langfuse.observation.type": "generation", "langfuse.observation.model.name": model,
                 "langfuse.observation.input": mask_obj(input), "langfuse.observation.output": mask_obj(output),
                 "langfuse.observation.usage_details": {"input": tin, "output": tout, "total": tin + tout},
                 "langfuse.observation.cost_details": {"total": float(u.get("total_cost") or 0.0)}}
        attrs.update({f"langfuse.observation.metadata.{k}": v for k, v in (metadata or {}).items()})
        self._child(trace_id, name, end - latency_s, end, attrs)

    def observe(self, trace_id: str, kind: str, node: str, payload: dict):
        """Map runtime events (agent.runtime.emit) onto Langfuse observations."""
        now, p = time.time(), mask_obj(payload or {})
        if kind == "node_start":
            return
        if kind == "node_end":
            dur = float(p.get("latency_s") or 0)
            self._child(trace_id, node, now - dur, now, {
                "langfuse.observation.type": "agent", "langfuse.observation.output": p.get("summary"),
                "langfuse.observation.metadata.tokens": p.get("tokens"), "langfuse.observation.metadata.cost_usd": p.get("cost_usd")})
        elif kind == "tool_call":
            dur = float(p.get("ms") or 0) / 1000
            self._child(trace_id, f"{p.get('server')}.{p.get('tool')}", now - dur, now, {
                "langfuse.observation.type": "tool", "langfuse.observation.input": p.get("args"),
                "langfuse.observation.output": p.get("result"), "langfuse.observation.metadata.node": node})
        else:
            err = kind == "error"
            self._child(trace_id, f"{kind}:{node}", now, now, {
                "langfuse.observation.type": "event", "langfuse.observation.input": p,
                "langfuse.observation.level": "ERROR" if err else "DEFAULT",
                "langfuse.observation.status_message": str(p.get("error"))[:500] if err else None})

    def end_trace(self, trace_id: str, output=None, error: str | None = None):
        """Close the run: send the root span and every buffered child in one OTLP request (background thread)."""
        tid = otel_trace_id(trace_id)
        with self._lock:
            ctx = self._open.get(tid)
            if not ctx:
                return
            ctx["refs"] -= 1
            if ctx["refs"] > 0:
                return
            self._open.pop(tid)
        end, tattrs = time.time(), self._trace_attrs(ctx)
        root = {**tattrs, "langfuse.trace.public": self.public, "langfuse.observation.type": "agent",
                "langfuse.observation.input": mask_obj(ctx["input"]), "langfuse.observation.output": mask_obj(output),
                "langfuse.observation.level": "ERROR" if error else "DEFAULT", "langfuse.observation.status_message": error}
        spans = [self._otlp_span(tid, ctx["root"], None, ctx["name"], ctx["start"], end, root, error=bool(error))]
        spans += [self._otlp_span(tid, _span_id(), ctx["root"], s["name"], s["start"], s["end"], {**tattrs, **s["attrs"]})
                  for s in ctx["spans"]]
        self._submit(spans)

    # ---- transport -------------------------------------------------------------------------------------------
    @staticmethod
    def _otlp_span(tid, sid, parent, name, start, end, attrs, error=False) -> dict:
        s = {"traceId": tid, "spanId": sid, "name": name, "kind": 1, "startTimeUnixNano": _ns(start),
             "endTimeUnixNano": _ns(end), "attributes": _attrs(attrs), "status": {"code": 2 if error else 1}}
        if parent:
            s["parentSpanId"] = parent
        return s

    @staticmethod
    def payload(spans: list[dict]) -> dict:
        return {"resourceSpans": [{
            "resource": {"attributes": _attrs({"service.name": "gigbid", "deployment.environment": os.getenv("APP_ENV") or None})},
            "scopeSpans": [{"scope": {"name": "gigbid.tracing", "version": "2"}, "spans": spans}]}]}

    def post(self, spans: list[dict]) -> tuple[int, str]:
        """Send spans now (blocking).  Returns (status, body); a rejected batch is logged with Langfuse's reason."""
        import httpx

        for i in range(0, len(spans), 200):
            r = httpx.post(self.endpoint, headers=self.headers, json=self.payload(spans[i:i + 200]), timeout=20)
            body = r.text[:400]
            rejected = 0
            try:
                rejected = int(((r.json() or {}).get("partialSuccess") or {}).get("rejectedSpans") or 0)
            except Exception:  # noqa: BLE001
                pass
            if r.status_code >= 300 or rejected:
                self.last_error = f"HTTP {r.status_code}: {body}"
                log.warning("Langfuse rejected spans: %s", self.last_error)
                return r.status_code, body
        self.sent_spans += len(spans)
        return 200, "ok"

    def _submit(self, spans: list[dict]):
        def run():
            try:
                self.post(spans)
            except Exception as e:  # noqa: BLE001  tracing must never break a run
                self.last_error = f"{type(e).__name__}: {e}"
                log.warning("Langfuse export failed: %s", self.last_error)

        with self._lock:
            self._futures = [f for f in self._futures if not f.done()] + [self._pool.submit(run)]

    def flush(self, timeout: float = 30):
        with self._lock:
            fs = list(self._futures)
        for f in fs:
            try:
                f.result(timeout=timeout)
            except Exception:  # noqa: BLE001
                pass


def langfuse() -> LangfuseOTel | None:
    """Return the Langfuse exporter, or None when tracing keys are not configured."""
    global _langfuse
    pk, sk, host = _keys()
    if not (pk and sk):
        return None
    if _langfuse is None:
        public = os.getenv("LANGFUSE_PUBLIC_TRACES", "1").strip().lower() not in ("0", "false", "no")
        _langfuse = LangfuseOTel(pk, sk, host, public=public)
    return _langfuse


def check_langfuse() -> str:
    """Startup self-check (blocking, run it in a thread): says in the log whether traces will actually arrive."""
    global _project_id
    import httpx

    pk, sk, host = _keys()
    if not (pk and sk):
        return "Langfuse tracing OFF: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set"
    if not pk.startswith("pk-lf-") or not sk.startswith("sk-lf-"):
        return "Langfuse tracing MISCONFIGURED: public key must start with pk-lf- and secret key with sk-lf- (swapped?)"
    try:
        r = httpx.get(f"{host}/api/public/projects", auth=(pk, sk), timeout=15)
        r.raise_for_status()
        data = r.json().get("data") or []
        _project_id = data[0]["id"] if data else None
    except Exception as e:  # noqa: BLE001
        return (f"Langfuse tracing FAILED auth against {host}: {type(e).__name__} {str(e)[:160]} - check the keys and that "
                "LANGFUSE_HOST matches the region of your project (EU https://cloud.langfuse.com, US https://us.cloud.langfuse.com)")
    if not _project_id:
        return f"Langfuse tracing FAILED: no project found for these keys on {host}"
    return f"Langfuse tracing ON (OTLP export): {host} project {_project_id}"


def trace_url(trace_id: str) -> str | None:
    if not langfuse():
        return None
    host, tid = _keys()[2], otel_trace_id(trace_id)
    return f"{host}/project/{_project_id}/traces/{tid}" if _project_id else f"{host}/trace/{tid}"
