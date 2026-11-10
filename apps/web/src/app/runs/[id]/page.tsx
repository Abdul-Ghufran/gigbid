import { Link, useParams } from "react-router-dom";
import { api, call } from "../../../lib/api/client";
import { useLoad } from "../../../lib/hooks";
import { ErrorBox, Loading, Badge } from "../../../components/ui";
import { RunTimeline } from "../../../components/RunTimeline";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function RunsListPage() {
  const { data, error, loading } = useLoad<Any[]>(() => call(api.GET("/api/runs")), [], 8000);
  return (
    <main className="page"><h1>Agent runs</h1>
      {loading && !data && <Loading />}{error && <ErrorBox error={error} />}
      <table className="table"><thead><tr><th>Run</th><th>Graph</th><th>Status</th><th>Latency</th><th>Tokens</th><th>Cost</th></tr></thead>
        <tbody>{(data || []).map((r) => <tr key={r.run_id}><td><Link to={`/runs/${r.run_id}`}>{r.thread_id.split(":").slice(2).join(":")}</Link></td>
          <td>{r.graph}</td><td><Badge tone={r.status === "failed" ? "bad" : r.status === "interrupted" ? "info" : "neutral"}>{r.status}</Badge></td>
          <td>{r.latency_s.toFixed(1)} s</td><td>{r.tokens}</td><td>${r.cost_usd.toFixed(4)}</td></tr>)}</tbody></table>
    </main>);
}

export default function RunPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useLoad<Any>(() => call(api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } })), [id]);
  if (loading && !data) return <main className="page"><Loading /></main>;
  if (error || !data) return <main className="page"><ErrorBox error={error || "not found"} /></main>;
  return (
    <main className="page">
      <p><Link to="/runs">← Runs</Link></p>
      <h1>Run {id.slice(0, 8)}</h1>
      <p className="small">Trace id <code data-testid="trace-id">{data.trace_id}</code> · {data.status} · {data.tokens} tokens · ${data.cost_usd.toFixed(4)} · {data.latency_s.toFixed(1)} s
        {data.trace_url && <> · <a href={data.trace_url} target="_blank" rel="noreferrer">Open full trace in Langfuse ↗</a></>}</p>
      {data.error && <div className="error">{data.error}</div>}
      <div className="grid2">
        <section className="card"><h2>Live progress</h2><RunTimeline runId={id} onEnd={() => reload()} /></section>
        <section className="card"><h2>Execution trace</h2>
          <ol className="trace small">{data.events.map((e: Any) => (
            <li key={e.id}><code>{e.ts.slice(11, 19)}</code> <Badge tone={e.kind === "error" ? "bad" : e.kind === "interrupt" ? "info" : "neutral"}>{e.kind}</Badge> <strong>{e.node}</strong>
              {e.kind === "tool_call" && <> → <code>{e.payload.server}.{e.payload.tool}</code> ({e.payload.ms} ms)</>}
              {e.kind === "node_end" && <> {e.payload.latency_s}s · {e.payload.tokens} tok · ${Number(e.payload.cost_usd).toFixed(5)}</>}
              {e.kind === "error" && <> {String(e.payload.error).slice(0, 160)}</>}
              {(e.kind === "tool_call") && <details><summary>arguments / result</summary><pre className="pre">{JSON.stringify({ args: e.payload.args, result: e.payload.result }, null, 1).slice(0, 3000)}</pre></details>}
            </li>))}</ol>
          <h3>MCP audit log (same trace id)</h3>
          <ul className="small">{data.audit.map((a: Any, i: number) => <li key={i}><code>{a.server}.{a.tool}</code> {a.ok ? "ok" : "error"} <span className="muted">{a.ts.slice(11, 19)}</span></li>)}</ul>
        </section>
      </div>
    </main>
  );
}
