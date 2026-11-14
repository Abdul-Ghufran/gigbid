"""Langfuse export over OTLP/HTTP JSON: Langfuse Cloud v4 silently dropped the legacy SDK-v2 batch ingestion."""
import re

from common.tracing import LangfuseOTel, otel_trace_id


def _attrs(span):
    out = {}
    for a in span["attributes"]:
        v = a["value"]
        out[a["key"]] = next(iter(v.values()))
    return out


def test_one_run_is_one_public_trace_with_typed_children(monkeypatch):
    lf = LangfuseOTel("pk-lf-test", "sk-lf-test", "https://cloud.langfuse.com")
    sent = []
    monkeypatch.setattr(lf, "post", lambda spans: sent.append(spans) or (200, "ok"))
    tid = "run-trace-not-hex"  # client-supplied ids are hashed into a valid OTel id
    lf.trace(id=tid, name="bid_graph", user_id="u1", session_id="bid:u1:job9", metadata={"run_id": "r1"}, input={"mode": "start"})
    lf.observe(tid, "node_start", "writer", {})
    lf.observe(tid, "tool_call", "submitter", {"server": "marketplace", "tool": "submit_proposal", "args": {"bid": 500},
                                               "result": {"ok": True}, "ms": 120})
    lf.generation(trace_id=tid, name="writer.llm", model="openai/gpt-oss-120b", input=[{"role": "user", "content": "mail me a@b.com"}],
                  output="draft", usage={"input": 100, "output": 50, "total_cost": 0.001}, latency_s=1.5)
    lf.observe(tid, "node_end", "writer", {"latency_s": 2.0, "tokens": 150, "cost_usd": 0.001, "summary": {"status": "drafted"}})
    lf.observe(tid, "error", "critic", {"error": "timeout"})
    assert not sent, "nothing is sent before the run ends"
    lf.end_trace(tid, output={"status": "done"})
    lf.flush()
    spans = sent[0]
    hexid = otel_trace_id(tid)
    assert re.fullmatch(r"[0-9a-f]{32}", hexid) and all(s["traceId"] == hexid for s in spans)
    root = spans[0]
    ra = _attrs(root)
    assert "parentSpanId" not in root and ra["langfuse.trace.name"] == "bid_graph" and ra["langfuse.trace.public"] is True
    assert ra["langfuse.session.id"] == "bid:u1:job9" and ra["langfuse.user.id"] == "u1"
    kids = {s["name"]: _attrs(s) for s in spans[1:]}
    assert all(s["parentSpanId"] == root["spanId"] for s in spans[1:])
    assert kids["marketplace.submit_proposal"]["langfuse.observation.type"] == "tool"
    gen = [a for n, a in kids.items() if a.get("langfuse.observation.type") == "generation"][0]
    assert gen["langfuse.observation.model.name"] == "openai/gpt-oss-120b" and '"total": 150' in gen["langfuse.observation.usage_details"]
    assert "a@b.com" not in gen["langfuse.observation.input"], "PII is masked before export"
    assert kids["writer"]["langfuse.observation.type"] == "agent"
    assert kids["error:critic"]["langfuse.observation.level"] == "ERROR"
    assert "writer" in {s["name"] for s in spans} and not any(s["name"].startswith("node_start") for s in spans)


def test_payload_is_otlp_json_and_auth_header(monkeypatch):
    lf = LangfuseOTel("pk-lf-a", "sk-lf-b", "https://cloud.langfuse.com")
    assert lf.endpoint == "https://cloud.langfuse.com/api/public/otel/v1/traces"
    assert lf.headers["x-langfuse-ingestion-version"] == "4" and lf.headers["Authorization"].startswith("Basic ")
    p = lf.payload([{"traceId": "0" * 32, "spanId": "1" * 16, "name": "x"}])
    assert p["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"] == "x"


def test_concurrent_runs_on_one_trace_id_send_once(monkeypatch):
    lf = LangfuseOTel("pk-lf-a", "sk-lf-b", "https://cloud.langfuse.com")
    sent = []
    monkeypatch.setattr(lf, "post", lambda spans: sent.append(spans) or (200, "ok"))
    t = "a" * 32
    lf.trace(id=t, name="bid_graph")
    lf.trace(id=t, name="bid_graph")
    lf.end_trace(t)
    lf.flush()
    assert not sent
    lf.end_trace(t)
    lf.flush()
    assert len(sent) == 1
