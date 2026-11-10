import { Link } from "react-router-dom";
import { api, call, type JobCard } from "../../lib/api/client";
import { money, useLoad } from "../../lib/hooks";
import { ErrorBox, Loading } from "../../components/ui";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"] as const;

export default function PipelinePage() {
  const { data, error, loading, reload } = useLoad<JobCard[]>(() => call(api.GET("/api/jobs", { params: { query: { sort: "recent" } } })), [], 10000);
  async function advance() { await call(api.POST("/api/demo/tick", { params: { query: { minutes: 180 } } })); reload(); }
  const jobs = (data || []).filter((j) => j.pipeline_stage);
  return (
    <main className="page">
      <div className="page-head"><h1>Pipeline</h1>
        <button className="btn" onClick={advance} title="GigSim only: advance simulated time so clients react">Advance GigSim clock 3 h</button></div>
      <p className="muted small">Cards move automatically as marketplace events arrive (viewed, replied, interview, hired, lost).</p>
      {loading && !data && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      <div className="kanban" data-testid="kanban">
        {COLS.map((c) => {
          const items = jobs.filter((j) => j.pipeline_stage === c);
          return (
            <section key={c} className="kcol" aria-label={`${c} (${items.length})`}>
              <h2>{c} <span className="muted">{items.length}</span></h2>
              {items.map((j) => (
                <Link key={j.job_id} to={c === "drafted" ? `/studio/${j.job_id}` : `/jobs/${j.job_id}`} className="kcard">
                  <strong>{j.title}</strong><span className="small muted">{money(j.price)} · {j.category}</span>
                </Link>))}
              {items.length === 0 && <p className="muted small">Empty</p>}
            </section>);
        })}
      </div>
    </main>
  );
}
