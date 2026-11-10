import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { streamRun, type StreamEvent } from "../lib/api/client";

const LABEL: Record<string, string> = {
  scout: "Scout", analyst: "Job Analyst", risk_assessor: "Risk Assessor", fit_matcher: "Fit Matcher", decide: "Bid / skip decision",
  pricing: "Pricing Strategist", writer: "Proposal Writer", verifier: "Claim verification", critic: "Critic",
  compliance: "Compliance Guard", prepare_approval: "Dry-run preview", approval: "Waiting for your approval", record_edit: "Recording your edit",
  submit: "Submitting (exactly once)", liaison_read: "Reading messages", intent: "Classifying intent", plan_reply: "Finding calendar slots",
  liaison_draft: "Drafting reply", liaison_preview: "Dry-run preview", message_approval: "Waiting for your approval", liaison_send: "Sending",
  runner: "Runner",
};

type Step = { node: string; status: "running" | "done" | "error" | "waiting"; latency?: number; tokens?: number; tools: string[]; error?: string };

/** Live node-by-node progress streamed over SSE (replays history after a refresh). */
export function RunTimeline({ runId, onEnd, compact = false }: { runId: string; onEnd?: (s: Record<string, unknown>) => void; compact?: boolean }) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [end, setEnd] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    setEvents([]); setEnd(null);
    streamRun(runId, (e) => setEvents((xs) => [...xs, e]), ac.signal).then((s) => { if (s) { setEnd(s); onEnd?.(s); } });
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);
  const steps = useMemo(() => {
    const out: Step[] = [];
    const last = (n: string) => [...out].reverse().find((s) => s.node === n && s.status === "running");
    for (const e of events) {
      if (e.kind === "node_start") out.push({ node: e.node, status: "running", tools: [] });
      else if (e.kind === "node_end") { const s = last(e.node); if (s) Object.assign(s, { status: "done", latency: e.payload.latency_s as number, tokens: e.payload.tokens as number }); }
      else if (e.kind === "tool_call") { const s = last(e.node); s?.tools.push(`${e.payload.server}.${e.payload.tool} (${e.payload.ms} ms)`); }
      else if (e.kind === "interrupt") out.push({ node: e.node, status: "waiting", tools: [] });
      else if (e.kind === "error") { const s = last(e.node); if (s) Object.assign(s, { status: "error", error: String(e.payload.error) }); else out.push({ node: e.node, status: "error", tools: [], error: String(e.payload.error) }); }
    }
    return out;
  }, [events]);
  return (
    <div className="timeline" aria-live="polite" data-testid="run-timeline">
      {steps.length === 0 && !end && <div className="loading"><span className="spinner" aria-hidden /> Starting agents...</div>}
      <ol>
        {steps.map((s, i) => (
          <li key={i} className={`step step-${s.status}`}>
            <span className="dot" aria-hidden />
            <span className="step-name">{LABEL[s.node] || s.node}</span>
            <span className="step-meta">
              {s.status === "running" && <><span className="spinner" aria-hidden /> working</>}
              {s.status === "done" && `${s.latency?.toFixed(1)} s${s.tokens ? ` · ${s.tokens} tok` : ""}`}
              {s.status === "waiting" && "paused"}
              {s.status === "error" && <span className="text-bad">{s.error?.slice(0, 120)}</span>}
            </span>
            {!compact && s.tools.length > 0 && <ul className="tools">{s.tools.map((t, j) => <li key={j}><code>{t}</code></li>)}</ul>}
          </li>
        ))}
      </ol>
      {end && (
        <p className="muted">
          Run {String(end.status)} · {String(end.tokens ?? 0)} tokens · ${Number(end.cost_usd ?? 0).toFixed(4)} · {Number(end.latency_s ?? 0).toFixed(1)} s ·{" "}
          <Link to={`/runs/${runId}`}>full trace</Link>
        </p>
      )}
    </div>
  );
}
