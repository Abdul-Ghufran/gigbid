import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, call, type JobCard } from "../../lib/api/client";
import { money, useLoad } from "../../lib/hooks";
import { DecisionBadge, Empty, ErrorBox, FitBar, Loading, RiskBadge, Badge } from "../../components/ui";

const STATUS_LABEL: Record<string, string> = {
  awaiting_approval: "Draft ready", analysing: "Analysing", new: "Queued", skipped: "Skipped", watch: "Watching", submitted: "Submitted",
  rejected: "Rejected", needs_attention: "Needs attention", dead_letter: "Failed", queued_retry: "Queued (marketplace down)",
  submitting: "Submitting", rechecking: "Re-checking", duplicate: "Duplicate",
};

export default function InboxPage() {
  const [filter, setFilter] = useState<"all" | "bid" | "watch" | "skip" | "approval">("all");
  const [sort, setSort] = useState<"fit" | "recent" | "price">("fit");
  const [scouting, setScouting] = useState(false);
  const { data, error, loading, reload } = useLoad<JobCard[]>(() => call(api.GET("/api/jobs", { params: { query: { sort } } })), [sort], 8000);
  const rows = useMemo(() => (data || []).filter((j) =>
    filter === "all" ? true : filter === "approval" ? j.status === "awaiting_approval" : j.decision === filter), [data, filter]);
  async function scout() { setScouting(true); try { await call(api.POST("/api/jobs/scout")); await reload(); } finally { setScouting(false); } }
  async function skip(id: string) { await call(api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id }, query: { reason: "skipped from inbox" } } })); reload(); }

  return (
    <main className="page">
      <div className="page-head">
        <h1>Job inbox</h1>
        <div className="row gap wrap">
          <label className="sr-only" htmlFor="sort">Sort</label>
          <select id="sort" className="input input-small" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
            <option value="fit">Best fit first</option><option value="recent">Most recent</option><option value="price">Highest price</option>
          </select>
          <button className="btn" onClick={scout} disabled={scouting} data-testid="scout-now">{scouting ? "Scouting..." : "Scout now"}</button>
        </div>
      </div>
      <div className="chips" role="tablist" aria-label="Filter jobs">
        {(["all", "approval", "bid", "watch", "skip"] as const).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} className={`chip ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>
            {f === "approval" ? "Needs my approval" : f === "all" ? "All" : f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      {loading && !data && <Loading label="Loading your inbox" />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && rows.length === 0 && <Empty title="No jobs here yet">Scouting runs every 20 minutes. Press <em>Scout now</em> to search your saved searches immediately.</Empty>}
      <ul className="job-list" data-testid="job-list">
        {rows.map((j) => (
          <li key={j.job_id} className="card job-card" data-testid="job-card" data-status={j.status}>
            <div className="job-main">
              <Link to={`/jobs/${j.job_id}`} className="job-title">{j.title}</Link>
              <div className="row gap wrap small">
                <Badge tone={j.status === "awaiting_approval" ? "info" : j.status === "needs_attention" || j.status === "dead_letter" ? "bad" : "neutral"}>{STATUS_LABEL[j.status] || j.status}</Badge>
                <DecisionBadge decision={j.decision} />
                <RiskBadge risk={j.risk} scam={j.scam} flags={j.flags} />
                <span className="muted">{j.category} · budget {money(j.budget?.max as number)} {j.budget?.type === "hourly" ? "/h" : ""} · {j.connects_cost ?? "?"} Connects</span>
              </div>
              {(j.attention ?? []).length > 0 && <p className="text-bad small">{(j.attention ?? [])[0]}</p>}
            </div>
            <div className="job-side">
              <FitBar fit={j.fit} />
              <div className="small">Suggested: <strong>{money(j.price)}</strong></div>
              <div className="row gap">
                {j.status === "awaiting_approval" && <Link className="btn btn-primary btn-small" to={`/studio/${j.job_id}`}>Review draft</Link>}
                {!["skipped", "submitted", "rejected"].includes(j.status) && <button className="btn btn-small" onClick={() => skip(j.job_id)}>Skip</button>}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
