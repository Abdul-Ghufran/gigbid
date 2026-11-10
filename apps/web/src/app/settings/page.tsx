import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, call, type SettingsOut } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";
import { Badge, ErrorBox, Loading } from "../../components/ui";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "general";
  const tabs = ["general", "searches", "memory", "portfolio", "accounts"];
  return (
    <main className="page">
      <h1>Settings</h1>
      <div className="chips" role="tablist">{tabs.map((t) => (
        <button key={t} role="tab" aria-selected={tab === t} className={`chip ${tab === t ? "active" : ""}`} onClick={() => setParams({ tab: t })} data-testid={`tab-${t}`}>{t}</button>))}</div>
      {tab === "general" && <General />}{tab === "searches" && <Searches />}{tab === "memory" && <Memory />}
      {tab === "portfolio" && <Portfolio />}{tab === "accounts" && <Accounts />}
    </main>
  );
}

function useSettings() { return useLoad<SettingsOut>(() => call(api.GET("/api/settings")), []); }

function General() {
  const { data, error, reload, setData } = useSettings();
  const [saved, setSaved] = useState(false);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  async function save() {
    setData(await call(api.PUT("/api/settings", { body: { hourly_rate: data!.hourly_rate, min_project: data!.min_project, weekly_connects_budget: data!.weekly_connects_budget, autonomy: data!.autonomy } })));
    setSaved(true); setTimeout(() => setSaved(false), 2000);
  }
  return (
    <section className="card stack narrow">
      <label>Hourly rate (USD)<input className="input" type="number" value={data.hourly_rate} onChange={(e) => setData({ ...data, hourly_rate: +e.target.value })} /></label>
      <label>Minimum project (USD)<input className="input" type="number" value={data.min_project} onChange={(e) => setData({ ...data, min_project: +e.target.value })} /></label>
      <label>Weekly Connects budget<input className="input" type="number" value={data.weekly_connects_budget} onChange={(e) => setData({ ...data, weekly_connects_budget: +e.target.value })} /></label>
      <fieldset><legend>Autonomy</legend>
        <label className="radio"><input type="radio" checked={data.autonomy === "suggest"} onChange={() => setData({ ...data, autonomy: "suggest" })} /> Suggest only: I review every skip and every draft</label>
        <label className="radio"><input type="radio" checked={data.autonomy === "auto_skip_low_fit"} onChange={() => setData({ ...data, autonomy: "auto_skip_low_fit" })} /> Auto-skip low-fit and scam jobs (GigBid never auto-sends)</label>
      </fieldset>
      <p className="small muted">Model profile: <code>{data.model_profile}</code> · marketplace: <code>{data.marketplace_mode}</code></p>
      <button className="btn btn-primary" onClick={save}>{saved ? "Saved" : "Save"}</button>
    </section>);
}

function Searches() {
  const { data, error, reload, setData } = useSettings();
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const ss = data.saved_searches;
  const upd = (i: number, patch: Any) => setData({ ...data, saved_searches: ss.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  async function save() { setData(await call(api.PUT("/api/settings", { body: { saved_searches: data!.saved_searches } }))); }
  return (
    <section className="card stack">
      {ss.map((s, i) => (
        <div key={s.id || i} className="row gap wrap search-row">
          <input className="input" aria-label="Name" value={s.name} onChange={(e) => upd(i, { name: e.target.value })} />
          <select className="input input-small" aria-label="Category" value={s.category || ""} onChange={(e) => upd(i, { category: e.target.value || null })}>
            <option value="">any</option><option value="ai">ai</option><option value="web">web</option><option value="data">data</option></select>
          <input className="input" aria-label="Skills" value={(s.skills ?? []).join(", ")} onChange={(e) => upd(i, { skills: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
          <label className="small">every <input className="input input-small" type="number" min={5} value={s.interval_minutes} onChange={(e) => upd(i, { interval_minutes: +e.target.value })} /> min</label>
          <button className="btn btn-small" onClick={() => setData({ ...data, saved_searches: ss.filter((_, j) => j !== i) })}>Remove</button>
        </div>))}
      <div className="row gap"><button className="btn" onClick={() => setData({ ...data, saved_searches: [...ss, { id: "", name: "New search", query: "", category: null, skills: [], min_budget: 0, interval_minutes: 20, limit: 10, last_run: null }] })}>Add search</button>
        <button className="btn btn-primary" onClick={save}>Save searches</button></div>
      <p className="small muted">Live Upwork mode never searches more often than every 3 hours (see docs/RUNBOOK.md).</p>
    </section>);
}

function Memory() {
  const { data, error, loading, reload, setData } = useLoad<Any>(() => call(api.GET("/api/memory")), []);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error || ""} onRetry={reload} />;
  async function forget(kind: string, key: string, category?: string) {
    setData(await call(api.DELETE("/api/memory/{kind}/{key}", { params: { path: { kind, key }, query: { category } } })));
  }
  return (
    <div className="grid2">
      <section className="card" data-testid="style-memory"><h2>Style memory</h2>
        <p className="small muted">Promoted only when the same edit appears in 3+ drafts for 3+ different jobs (rule style.v1).</p>
        {data.style.length === 0 && <p className="muted">Nothing learned yet. Edit a few drafts the same way.</p>}
        <ul>{data.style.map((s: Any) => <li key={s.key} className="row gap between"><span>{s.rule} <span className="muted small">({s.occurrences}× across {s.jobs.length} jobs)</span></span>
          <button className="btn btn-small" onClick={() => forget("style", s.key)} aria-label={`Forget ${s.rule}`}>Forget</button></li>)}</ul>
        <h3>Recent raw edits (not memory)</h3><ul className="small">{data.recent_edits.map((e: Any, i: number) => <li key={i}>{e.job_id} · {e.diff.length} changed tokens</li>)}</ul>
      </section>
      <section className="card"><h2>Outcome memory</h2>
        <p className="small muted">Per category, after 5+ outcomes; a lesson needs a 10-point reply-rate lift (rule outcome.v1).</p>
        {data.outcome.length === 0 && <p className="muted">No outcomes yet.</p>}
        <ul>{data.outcome.map((o: Any) => <li key={o.namespace.join("/")}><strong>{o.namespace[2]}</strong>: reply rate {Math.round(o.reply_rate * 100)}% (n={o.n})
          <ul>{o.lessons.map((l: Any) => <li key={l.feature}>{l.lesson} <span className="muted small">+{Math.round(l.lift * 100)} pts</span></li>)}</ul>
          <button className="btn btn-small" onClick={() => forget("outcome", o.namespace[2], o.namespace[2])}>Forget</button></li>)}</ul>
      </section>
    </div>);
}

function Portfolio() {
  const { data, error, loading, reload } = useLoad<Any[]>(() => call(api.GET("/api/portfolio")), []);
  const [form, setForm] = useState({ kind: "case_study", title: "", content: "", project: "", client_industry: "" });
  const [msg, setMsg] = useState<string | null>(null);
  async function add(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      const r = await call(api.POST("/api/portfolio", { body: { ...form, kind: form.kind as "case_study", project: form.project || null, client_industry: form.client_industry || null } }));
      setMsg(`Added. Detected skills: ${r.skills.join(", ") || "none"}. Re-indexed.`); setForm({ ...form, title: "", content: "" }); reload();
    } catch (err) { setMsg(String(err)); }
  }
  async function del(id: string) { await call(api.DELETE("/api/portfolio/{item_id}", { params: { path: { item_id: id } } })); reload(); }
  return (
    <div className="grid2">
      <form className="card stack" onSubmit={add}><h2>Add work</h2>
        <label>Type<select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          <option value="case_study">Case study</option><option value="repo">Repository README / code</option><option value="review">Client review</option><option value="proposal">Past proposal</option><option value="cv">CV text</option></select></label>
        <label>Title<input className="input" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label>Project (optional)<input className="input" value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} /></label>
        <label>Client industry (optional)<input className="input" value={form.client_industry} onChange={(e) => setForm({ ...form, client_industry: e.target.value })} /></label>
        <label>Content<textarea className="input" rows={8} required minLength={20} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} /></label>
        <button className="btn btn-primary">Add and re-index</button>{msg && <p className="small" role="status">{msg}</p>}
      </form>
      <section className="card"><h2>Portfolio items</h2>{loading && !data && <Loading />}{error && <ErrorBox error={error} />}
        <ul className="small">{(data || []).map((i) => <li key={i.id}><Badge>{i.type}</Badge> {i.title} <span className="muted">{i.skills.slice(0, 4).join(", ")}</span>
          {i.uploaded && <button className="btn btn-small" onClick={() => del(i.id)}>Delete</button>}</li>)}</ul></section>
    </div>);
}

function Accounts() {
  const { data, error, reload, setData } = useSettings();
  const [params] = useSearchParams();
  useEffect(() => { if (params.get("connected")) reload(); }, [params, reload]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  async function connectUpwork() { const r = await call(api.GET("/api/auth/upwork/start")); location.assign(String((r as Any).authorize_url)); }
  async function remove(id: string) { setData(await call(api.DELETE("/api/settings/accounts/{account_id}", { params: { path: { account_id: id } } }))); }
  return (
    <section className="card stack narrow"><h2>Connected marketplaces</h2>
      <ul>{data.connected_accounts.filter((a) => a.status === "connected").map((a) => <li key={String(a.id)}><Badge tone="good">{String(a.provider)}</Badge> connected {String(a.connected_at).slice(0, 10)} <button className="btn btn-small" onClick={() => remove(String(a.id))}>Disconnect</button></li>)}</ul>
      <button className="btn" onClick={connectUpwork}>Connect Upwork (OAuth)</button>
      <p className="small muted">Tokens are stored encrypted and never logged. On Upwork every proposal and message is created as a draft you confirm on Upwork.</p>
    </section>);
}
