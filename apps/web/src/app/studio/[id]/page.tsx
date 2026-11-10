import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, call } from "../../../lib/api/client";
import { useLoad } from "../../../lib/hooks";
import { ErrorBox, Loading, Badge, Empty } from "../../../components/ui";
import { EvidenceText, type Check, type Evidence } from "../../../components/EvidenceHover";
import { ApprovalPanel, type Decision, type Preview } from "../../../components/ApprovalPanel";
import { RunTimeline } from "../../../components/RunTimeline";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function StudioPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useLoad<Any>(() => call(api.GET("/api/proposals/{job_id}", { params: { path: { job_id: id } } })), [id]);
  const [text, setText] = useState("");
  const [answers, setAnswers] = useState<string[]>([]);
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [regen, setRegen] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { if (data) { setText(data.draft.cover_letter); setAnswers(data.draft.screening_answers || []); } }, [data]);

  if (loading && !data) return <main className="page"><Loading label="Loading draft" /></main>;
  if (runId) return (
    <main className="page narrow"><h1>Working on it</h1><RunTimeline runId={runId} onEnd={() => { setMsg("Done."); }} />
      {msg && <p><Link className="btn" to={`/jobs/${id}`}>Back to the job</Link> <button className="btn" onClick={() => { setRunId(null); reload(); }}>Reload studio</button></p>}</main>);
  if (error || !data) return <main className="page"><Empty title="No draft waiting for approval">{error} <Link to={`/jobs/${id}`}>Open the job</Link></Empty></main>;

  const dirty = text !== data.draft.cover_letter || JSON.stringify(answers) !== JSON.stringify(data.draft.screening_answers || []);
  const checks: Check[] = data.verification?.checks || [];
  const evidence: Record<string, Evidence> = data.evidence || {};
  const critique = (data.critiques || []).slice(-1)[0];
  const comp = data.compliance || {};
  const paras = text.split(/\n\s*\n/);
  const v = data.verification || {};

  async function decide(d: Decision) {
    setBusy(true);
    try {
      const body = d.action === "edit" ? { ...d, cover_letter: text, screening_answers: answers } : d;
      const r = await call(api.POST("/api/proposals/{job_id}/decision", { params: { path: { job_id: id } }, body }));
      setRunId(r.run_id);
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }
  async function regenerate(i: number) {
    setRegen(i);
    try {
      const r = await call(api.POST("/api/proposals/{job_id}/regenerate", { params: { path: { job_id: id } }, body: { paragraph_index: i, instruction: "" } }));
      const ps = text.split(/\n\s*\n/); ps[i] = r.paragraph; setText(ps.join("\n\n")); setMode("edit");
    } finally { setRegen(null); }
  }

  return (
    <main className="page">
      <p><Link to={`/jobs/${id}`}>← Job detail</Link></p>
      <div className="page-head"><h1>Proposal studio</h1>
        <div className="row gap" role="tablist">
          <button role="tab" aria-selected={mode === "read"} className={`chip ${mode === "read" ? "active" : ""}`} onClick={() => setMode("read")}>Evidence view</button>
          <button role="tab" aria-selected={mode === "edit"} className={`chip ${mode === "edit" ? "active" : ""}`} onClick={() => setMode("edit")} data-testid="edit-mode">Edit</button>
        </div>
      </div>
      {msg && <div className="error" role="alert">{msg}</div>}
      <div className="studio">
        <div className="stack">
          <section className="card" aria-labelledby="h-draft">
            <h2 id="h-draft">Cover letter {dirty && <Badge tone="warn">edited</Badge>}</h2>
            {mode === "read" ? (
              <>
                <EvidenceText text={text} evidence={evidence} checks={checks} />
                <div className="row gap wrap">{paras.map((_, i) => (
                  <button key={i} className="btn btn-small" disabled={regen !== null} onClick={() => regenerate(i)} data-testid={`regen-${i}`}>
                    {regen === i ? "Rewriting..." : `Regenerate ¶${i + 1}`}</button>))}
                </div>
                <p className="muted small">Hover or focus a highlighted sentence to see the evidence behind it. Green = supported, amber = partly supported.</p>
              </>
            ) : (
              <>
                <label htmlFor="cover" className="sr-only">Cover letter</label>
                <textarea id="cover" className="input editor" value={text} onChange={(e) => setText(e.target.value)} data-testid="editor" rows={14} />
                <p className="muted small">{text.split(/\s+/).filter(Boolean).length} words. Edits are diffed, re-checked by the Compliance Guard and may teach style memory.</p>
              </>
            )}
          </section>
          {answers.length > 0 && <section className="card"><h2>Screening answers</h2>
            {(data.job_questions || answers).map((_: unknown, i: number) => (
              <div key={i} className="stack"><label htmlFor={`a${i}`}><strong>Q{i + 1}</strong></label>
                <textarea id={`a${i}`} className="input" rows={3} value={answers[i] || ""} onChange={(e) => { const a = [...answers]; a[i] = e.target.value; setAnswers(a); }} /></div>))}
          </section>}
        </div>
        <aside className="stack">
          <ApprovalPanel preview={data.preview as Preview} price={data.price?.amount} priceType={data.price?.bid_type} blocked={data.blocked}
                         blockReasons={comp.reasons} dirty={dirty} busy={busy} onDecide={decide} />
          <section className="card" aria-labelledby="h-critic"><h3 id="h-critic">Critic {critique && <Badge tone={critique.passed ? "good" : "warn"}>{critique.score}/10</Badge>}</h3>
            {critique ? <ul className="small">{[...critique.issues].slice(0, 6).map((x: string, i: number) => <li key={i}>{x}</li>)}{critique.issues.length === 0 && <li>No issues.</li>}</ul> : <p className="muted">No review.</p>}
            <p className="muted small">Revisions used: {(data.critiques || []).length - 1} of 2</p>
          </section>
          <section className="card" aria-labelledby="h-comp"><h3 id="h-comp">Compliance <Badge tone={comp.status === "pass" ? "good" : comp.status === "fixed" ? "warn" : "bad"}>{comp.status}</Badge></h3>
            {(comp.removed || []).length > 0 ? <ul className="small">{comp.removed.map((r: string, i: number) => <li key={i}>Removed - {r}</li>)}</ul> : <p className="small muted">Nothing removed.</p>}
            <p className="small muted">Policy {comp.policy_version}</p>
          </section>
          <section className="card"><h3>Claim verification</h3>
            <p className="small" data-testid="verification">{v.claims_before ?? 0} claims checked · {v.unsupported_before ?? 0} unsupported removed before the critic saw the draft.</p>
            {(v.removed || []).length > 0 && <details><summary className="small">Removed claims</summary><ul className="small">{v.removed.map((r: string, i: number) => <li key={i}><s>{r}</s></li>)}</ul></details>}
          </section>
          <section className="card"><h3>Risk</h3><p className="small">{data.risk?.client_summary}</p>
            {(data.risk?.injected_text || []).length > 0 && <p className="small text-bad">Ignored injected text: <q>{data.risk.injected_text[0]}</q></p>}</section>
        </aside>
      </div>
      {error && <ErrorBox error={error} />}
    </main>
  );
}
