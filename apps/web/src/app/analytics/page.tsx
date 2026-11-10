import { api, call } from "../../lib/api/client";
import { pct, useLoad } from "../../lib/hooks";
import { ErrorBox, Loading } from "../../components/ui";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div className="hbar"><span className="hbar-label">{label}</span>
      <span className="hbar-track"><span className="hbar-fill" style={{ width: `${max ? (value / max) * 100 : 0}%` }} /></span>
      <span className="hbar-val">{value}</span></div>);
}

export default function AnalyticsPage() {
  const { data, error, loading, reload } = useLoad<Any>(() => call(api.GET("/api/analytics")), [], 20000);
  if (loading && !data) return <main className="page"><Loading /></main>;
  if (error || !data) return <main className="page"><ErrorBox error={error || "no data"} onRetry={reload} /></main>;
  const f = data.funnel, cl = data.cost_latency, max = Math.max(1, ...Object.values(f as Record<string, number>));
  return (
    <main className="page">
      <h1>Analytics</h1>
      <div className="stats">
        <div className="stat"><span>Jobs seen</span><strong>{f.seen || 0}</strong></div>
        <div className="stat"><span>Scams caught</span><strong>{f.scams_caught || 0}</strong></div>
        <div className="stat"><span>Submitted</span><strong>{f.submitted || 0}</strong></div>
        <div className="stat"><span>Reply rate</span><strong>{f.submitted ? pct((f.replied || 0) / f.submitted) : "-"}</strong></div>
        <div className="stat"><span>Connects spent</span><strong>{data.connects_spent}</strong></div>
        <div className="stat"><span>p95 latency / run</span><strong>{cl.p95_latency_s ?? "-"} s</strong></div>
        <div className="stat"><span>Cost / proposal</span><strong>{cl.mean_cost_per_proposal_usd != null ? `$${cl.mean_cost_per_proposal_usd}` : "-"}</strong></div>
      </div>
      <div className="grid2">
        <section className="card"><h2>Funnel</h2>{["seen", "recommended_bid", "submitted", "replied", "hired"].map((k) => <Bar key={k} label={k.replace("_", " ")} value={f[k] || 0} max={max} />)}</section>
        <section className="card"><h2>Reply and hire rate by category</h2>
          <table className="table"><thead><tr><th>Category</th><th>Submitted</th><th>Reply</th><th>Hire</th><th>Connects</th></tr></thead>
            <tbody>{data.by_category.map((c: Any) => <tr key={c.category}><td>{c.category}</td><td>{c.submitted}</td><td>{pct(c.reply_rate)}</td><td>{pct(c.hire_rate)}</td><td>{c.connects}</td></tr>)}</tbody></table>
          {data.by_category.length === 0 && <p className="muted">No submitted proposals yet.</p>}</section>
      </div>
      <section className="card"><h2>Top rejection / skip reasons</h2>
        <ul>{data.top_rejection_reasons.map(([r, n]: [string, number]) => <li key={r}>{r} <span className="muted">×{n}</span></li>)}</ul>
        {data.top_rejection_reasons.length === 0 && <p className="muted">None yet.</p>}
        <p className="muted small">Total model cost ${cl.total_cost_usd} over {cl.runs} runs · {cl.total_tokens} tokens · p50 {cl.p50_latency_s ?? "-"} s</p></section>
    </main>
  );
}
