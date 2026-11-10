"""LLM access for every node.

* Model per node comes from agent/config.yaml (profile -> alias -> provider/model); never from code.
* `structured()` asks for JSON, validates it against a Pydantic model, repairs once, then falls back to
  the profile's fallback model, then to the caller's deterministic `offline` function (degraded mode).
* Client-side RPM/TPM limiter per model, Retry-After aware retries, per-call timeout.
* Token + list-price cost accounting into a per-run ledger (contextvar) and Langfuse generations.
* SQLite response cache keyed by (model, messages): makes evals reproducible and cheap (an optimisation
  we measure in the report); disable with LLM_CACHE=0.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from agent.config import ROOT, config, model_for
from common.security import mask_obj
from common.settings import get_settings
from common.tracing import current_trace_id, langfuse

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    pass


# ------------------------------------------------------------------------------------- ledger
@dataclass
class Ledger:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cached: int = 0
    fallbacks: int = 0
    offline: int = 0
    per_node: dict[str, dict] = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def add(self, node: str, tin: int, tout: int, cost: float, cached: bool):
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        self.cost_usd += cost
        self.cached += int(cached)
        d = self.per_node.setdefault(node, {"calls": 0, "tokens": 0, "cost_usd": 0.0})
        d["calls"] += 1
        d["tokens"] += tin + tout
        d["cost_usd"] = round(d["cost_usd"] + cost, 6)


ledger_var: contextvars.ContextVar[Ledger | None] = contextvars.ContextVar("ledger", default=None)


def current_ledger() -> Ledger:
    led = ledger_var.get()
    if led is None:
        led = Ledger()
        ledger_var.set(led)
    return led


# -------------------------------------------------------------------------------------- cache
class _Cache:
    def __init__(self):
        p = ROOT / ".cache"
        p.mkdir(exist_ok=True)
        self.db = sqlite3.connect(p / "llm_cache.sqlite", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, v TEXT)")
        self.lock = threading.Lock()

    def get(self, k):
        with self.lock:
            r = self.db.execute("SELECT v FROM c WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else None

    def put(self, k, v):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO c VALUES (?,?)", (k, json.dumps(v)))
            self.db.commit()


_cache: _Cache | None = None


def cache() -> _Cache:
    global _cache
    if _cache is None:
        _cache = _Cache()
    return _cache


# ------------------------------------------------------------------------------------ limiter
class _Limiter:
    def __init__(self, rpm: int, tpm: int):
        self.rpm, self.tpm = rpm, tpm
        self.req: deque = deque()
        self.tok: deque = deque()
        self.lock = asyncio.Lock()

    async def wait(self, est_tokens: int):
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.req and now - self.req[0] > 60:
                    self.req.popleft()
                while self.tok and now - self.tok[0][0] > 60:
                    self.tok.popleft()
                used = sum(t for _, t in self.tok)
                if len(self.req) < self.rpm and (used + est_tokens <= self.tpm or not self.tok):
                    self.req.append(now)
                    self.tok.append((now, est_tokens))
                    return
                oldest = min([self.req[0]] + ([self.tok[0][0]] if self.tok else []))
                await asyncio.sleep(max(0.2, 60 - (now - oldest)))


_limiters: dict[str, _Limiter] = {}


def _limiter(spec: dict) -> _Limiter:
    key = spec["provider"] + ":" + spec["model"]
    if key not in _limiters:
        _limiters[key] = _Limiter(int(spec.get("rpm", 1000)), int(spec.get("tpm", 10_000_000)))
    return _limiters[key]


# ------------------------------------------------------------------------------------ clients
def _api_key(spec: dict) -> str | None:
    prov = config()["providers"][spec["provider"]]
    if not prov.get("key_env"):
        return "ollama"
    return os.getenv(prov["key_env"]) or getattr(get_settings(), prov["key_env"].lower(), "") or None


def _base_url(spec: dict) -> str:
    prov = config()["providers"][spec["provider"]]
    return prov.get("base_url") or os.getenv(prov.get("base_url_env", ""), get_settings().ollama_base_url)


def chat_model(node: str, profile: str | None = None, **kw):
    """LangChain chat model for a node (used by tool-calling baselines and the supervisor)."""
    from langchain_openai import ChatOpenAI

    spec = model_for(node, profile)
    key = _api_key(spec)
    if not key:
        raise LLMUnavailable(f"no API key for provider {spec['provider']}")
    extra = {}
    if spec.get("reasoning_effort"):
        extra["reasoning_effort"] = spec["reasoning_effort"]
    return ChatOpenAI(model=spec["model"], base_url=_base_url(spec), api_key=key,
                      temperature=kw.get("temperature", config()["llm"]["temperature"]),
                      timeout=config()["llm"]["timeout_s"], max_retries=2, **extra)


def offline_mode() -> bool:
    return get_settings().llm_offline or os.getenv("LLM_OFFLINE") == "1"


def _price(spec: dict, tin: int, tout: int) -> float:
    return (tin * spec.get("price_in", 0) + tout * spec.get("price_out", 0)) / 1_000_000


async def _call(spec: dict, messages: list[dict], json_mode: bool, node: str, max_tokens: int) -> str:
    """One chat completion against an OpenAI-compatible endpoint, with limiter + retries + cache."""
    import httpx

    body: dict[str, Any] = {"model": spec["model"], "messages": messages, "temperature": config()["llm"]["temperature"],
                            "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if spec.get("reasoning_effort"):
        body["reasoning_effort"] = spec["reasoning_effort"]
    if "qwen3" in spec["model"] and spec["provider"] == "groq":
        body["reasoning_format"] = "hidden"
    use_cache = config()["llm"]["cache"] and os.getenv("LLM_CACHE", "1") == "1"
    ck = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    led = current_ledger()
    if use_cache and (hit := cache().get(ck)):
        led.add(node, hit["tin"], hit["tout"], _price(spec, hit["tin"], hit["tout"]), cached=True)
        return hit["text"]
    key = _api_key(spec)
    if not key:
        raise LLMUnavailable(f"no API key for {spec['provider']}")
    est = sum(len(m["content"]) for m in messages) // 3 + max_tokens // 2
    t0 = time.perf_counter()
    last: Exception | None = None
    for attempt in range(config()["llm"]["max_retries"] + 1):
        await _limiter(spec).wait(est)
        try:
            async with httpx.AsyncClient(timeout=config()["llm"]["timeout_s"]) as http:
                r = await http.post(f"{_base_url(spec)}/chat/completions", json=body,
                                    headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after", 2 ** attempt * 2))
                last = LLMUnavailable(f"{spec['model']} HTTP {r.status_code}")
                if wait > 20:  # daily quota or long throttle: fail over to the fallback model now, do not stall the run
                    raise last
                await asyncio.sleep(wait)
                continue
            if r.status_code >= 400:
                raise LLMUnavailable(f"{spec['model']} HTTP {r.status_code}: {r.text[:200]}")
            d = r.json()
            text = d["choices"][0]["message"].get("content") or ""
            u = d.get("usage", {})
            tin, tout = int(u.get("prompt_tokens", est)), int(u.get("completion_tokens", len(text) // 4))
            led.add(node, tin, tout, _price(spec, tin, tout), cached=False)
            _trace_generation(node, spec, messages, text, tin, tout, time.perf_counter() - t0)
            if use_cache:
                cache().put(ck, {"text": text, "tin": tin, "tout": tout})
            return text
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = LLMUnavailable(f"{spec['model']} {type(e).__name__}")
            await asyncio.sleep(2 ** attempt)
    raise last or LLMUnavailable("unknown")


def _trace_generation(node, spec, messages, text, tin, tout, secs):
    lf = langfuse()
    if not lf:
        return
    try:
        lf.generation(trace_id=current_trace_id(), name=node, model=spec["model"], input=mask_obj(messages),
                      output=mask_obj(text), usage={"input": tin, "output": tout, "unit": "TOKENS",
                                                    "total_cost": _price(spec, tin, tout)},
                      metadata={"latency_s": round(secs, 3), "alias": spec["alias"]})
    except Exception:
        pass


def _extract_json(text: str) -> Any:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start: end + 1])


async def text(node: str, system: str, user: str, *, max_tokens: int = 700, profile: str | None = None) -> str:
    spec = model_for(node, profile)
    if offline_mode():
        raise LLMUnavailable("offline mode")
    try:
        return re.sub(r"<think>.*?</think>", "", await _call(spec, _msgs(system, user), False, node, max_tokens), flags=re.S).strip()
    except LLMUnavailable:
        fb = model_for("fallback_strong" if node in ("writer", "critic", "liaison") else "fallback_small", profile)
        current_ledger().fallbacks += 1
        return re.sub(r"<think>.*?</think>", "", await _call(fb, _msgs(system, user), False, node, max_tokens), flags=re.S).strip()


def _msgs(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def structured(node: str, system: str, user: str, schema: type[T], *, offline: Callable[[], T] | None = None,
                     max_tokens: int = 900, profile: str | None = None) -> T:
    """JSON -> Pydantic with one repair attempt, fallback model, then deterministic offline function."""
    sys_full = system + "\n\nReturn ONLY a JSON object matching this JSON schema:\n" + json.dumps(_compact_schema(schema))
    if offline_mode():
        if offline:
            current_ledger().offline += 1
            return offline()
        raise LLMUnavailable("offline mode and no offline fallback")
    specs = [model_for(node, profile),
             model_for("fallback_strong" if node in ("writer", "critic", "liaison", "judge") else "fallback_small", profile)]
    last_err: Exception | None = None
    for i, spec in enumerate(specs):
        if i:
            current_ledger().fallbacks += 1
        msgs = _msgs(sys_full, user)
        for _repair in range(2):
            try:
                raw = await _call(spec, msgs, True, node, max_tokens)
                return schema.model_validate(_extract_json(raw))
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_err = e
                msgs = msgs + [{"role": "assistant", "content": raw if "raw" in locals() else ""},
                               {"role": "user", "content": f"That JSON was invalid: {str(e)[:400]}. Return corrected JSON only."}]
            except LLMUnavailable as e:
                last_err = e
                break
    if offline:
        current_ledger().offline += 1
        return offline()
    raise LLMUnavailable(f"{node}: {last_err}")


def _compact_schema(schema: type[BaseModel]) -> dict:
    s = schema.model_json_schema()

    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("title",)}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o

    return strip(s)
