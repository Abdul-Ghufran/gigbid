import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, call, type JobDetail } from "../../../lib/api/client";
import { money, pct, useLoad } from "../../../lib/hooks";
import { DecisionBadge, ErrorBox, FitBar, Loading, RiskBadge, Badge } from "../../../components/ui";
import { RunTimeline } from "../../../components/RunTimeline";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function JobDetailPage() {
  const { id = "" } = useParams();
  const [runId, setRunId] = useState<string | null>(null);
  const { data, error, loading, reload } = useLoad<JobDetail>(() => call(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })), [id], 0);
  if (loading && !data) return <main className="page"><Loading /></main>;
  if (error || !data) return <main className="page"><ErrorBox error={error || "not found"} onRetry={reload} /></main>;
  const job = data.job as Any, an = data.analyses as Any, spec = an.job_spec as Any | undefined, risk = an.risk as Any | undefined;
  const fit = an.fit as Any | undefined, price = data.price as Any, dec = data.decision as Any;
  const latestRun = runId || (["analysing", "submitting", "rechecking", "new"].includes(data.card.status) ? (data.runs ?? [])[0]?.run_id as string | undefined : null);

  async function analyze(force: boolean) {
    const r = await call(api.POST("/api/jobs/{job_id}/analyze", { params: { path: { job_id: id }, query: { force_bid: force } } }));
    setRunId(r.run_id);
  }

  return (
    <main className="page">
      <p><Link to="/inbox">← Inbox</Link></p>
      <div className="page-head">
        <h1>{job.title}</h1>
        <div className="row gap wrap">
          <Badge tone={data.card.status === "submitted" ? "good" : data.card.status === "awaiting_approval" ? "info" : "neutral"}>
            <span data-testid="job-status">{data.card.status.replace(/_/g, " ")}</span></Badge>
          <DecisionBadge decision={dec?.action} /><RiskBadge risk={risk?.score} scam={risk?.scam} flags={risk?.flags} />
          {data.pending_approval && <Link className="btn btn-primary" to={`/studio/${id}`} data-testid="open-studio">Open proposal studio</Link>}
          {!data.pending_approval && dec?.action !== "bid" && <button className="btn" onClick={() => analyze(true)}>Draft anyway</button>}
          <button className="btn" onClick={() => analyze(false)}>Re-analyse</button>
        </div>
      </div>
      {latestRun ? <section className="card"><h2>Agents at work</h2><RunTimeline runId={latestRun} onEnd={() => reload()} /></section> : null}
      <div className="grid2">
        <section className="card" aria-labelledby="h-post">
          <h2 id="h-post">Job post</h2>
          <p className="muted small">{job.category} · {job.experience_level} · {money(job.budget?.min)}-{money(job.budget?.max)} {job.budget?.type} · {job.proposals_count} proposals · {job.connects_cost} Connects</p>
          <p className="prewrap untrusted" title="Client-written text: treated as untrusted data">{job.description}</p>
          {job.screening_questions?.length > 0 && <><h3>Screening questions</h3><ol>{job.screening_questions.map((q: string, i: number) => <li key={i}>{q}</li>)}</ol></>}
        </section>
        <section className="card" aria-labelledby="h-dec">
          <h2 id="h-dec">Bid or skip?</h2>
          <DecisionBadge decision={dec?.action} />
          <ul>{(dec?.reasons || []).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
          <h3>Price rationale</h3>
          {price?.amount ? <>
            <p><strong>{money(price.amount, price.bid_type === "hourly")}</strong> ({price.bid_type}) · market p25/p50/p75: {money(price.market_p25)} / {money(price.market_p50)} / {money(price.market_p75)} · your floor {money(price.floor)}</p>
            <ul>{price.rationale.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            <p className="small">Connects: {price.connects_cost} ({money(price.connects_usd)}) · est. reply chance {pct(price.est_reply_probability)} · {price.worth_connects ? <Badge tone="good">worth it</Badge> : <Badge tone="warn">not worth it</Badge>}</p>
          </> : <p className="muted">Priced only for jobs worth bidding on.</p>}
        </section>
      </div>
      <div className="grid2">
        <section className="card" aria-labelledby="h-risk">
          <h2 id="h-risk">Risk report</h2>
          {risk ? <>
            <p>Score <strong>{pct(risk.score)}</strong> · client quality {pct(risk.client_quality)} {risk.scam && <Badge tone="bad">scam</Badge>}</p>
            <p className="small">{risk.client_summary}</p>
            <div className="row gap wrap">{risk.flags.map((f: string) => <Badge key={f} tone="warn">{f.replace(/_/g, " ")}</Badge>)}</div>
            <p className="small">{risk.explanation}</p>
            {risk.injected_text?.length > 0 && <div className="banner banner-warn" data-testid="injection-quote"><strong>Injected instructions found and ignored:</strong><ul>{risk.injected_text.map((t: string, i: number) => <li key={i}><q>{t}</q></li>)}</ul></div>}
          </> : <p className="muted">Not analysed yet.</p>}
        </section>
        <section className="card" aria-labelledby="h-spec">
          <h2 id="h-spec">JobSpec</h2>
          {spec ? <dl className="kv">
            <dt>Summary</dt><dd>{spec.summary}</dd>
            <dt>Deliverables</dt><dd>{spec.deliverables.join("; ") || "-"}</dd>
            <dt>Skills</dt><dd>{spec.required_skills.join(", ") || "-"}</dd>
            <dt>Timeline</dt><dd>{spec.timeline || "-"}</dd>
            <dt>Hidden needs</dt><dd>{spec.hidden_needs.join("; ") || "-"}</dd>
          </dl> : <p className="muted">Not analysed yet.</p>}
        </section>
      </div>
      <section className="card" aria-labelledby="h-matrix">
        <h2 id="h-matrix">Requirement → evidence matrix</h2>
        {fit ? <>
          <FitBar fit={fit.score} /><p className="small muted">Retrieval pipeline: {fit.retrieval_variant}</p>
          <table className="table" data-testid="evidence-matrix">
            <thead><tr><th scope="col">Requirement</th><th scope="col">Proven by</th></tr></thead>
            <tbody>{fit.matrix.map((m: Any, i: number) => (
              <tr key={i}><td>{m.requirement}</td>
                <td>{m.supported ? m.evidence.map((e: Any) => <div key={e.item_id} title={e.snippet}><Badge tone="good">{e.type.replace("_", " ")}</Badge> {e.title} <code className="small">[{e.item_id}]</code></div>)
                  : <Badge tone="bad">No evidence - will not be claimed</Badge>}</td></tr>))}</tbody>
          </table>
        </> : <p className="muted">Not analysed yet.</p>}
      </section>
      <section className="card"><h2>Runs</h2>
        <ul>{(data.runs ?? []).map((r) => <li key={String(r.run_id)}><Link to={`/runs/${r.run_id}`}>{String(r.status)} · {Number(r.latency_s).toFixed(1)} s · {String(r.tokens)} tok · ${Number(r.cost_usd).toFixed(4)}</Link> <span className="muted small">{String(r.created_at)}</span></li>)}</ul>
      </section>
    </main>
  );
}
