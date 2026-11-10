import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api, call, type ConversationCard } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";
import { Badge, Empty, ErrorBox, Loading } from "../../components/ui";
import { RunTimeline } from "../../components/RunTimeline";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function MessagesPage() {
  const { thread } = useParams();
  const nav = useNavigate();
  const list = useLoad<ConversationCard[]>(() => call(api.GET("/api/messages")), [], 10000);
  async function sync() { await call(api.POST("/api/messages/sync")); list.reload(); }
  return (
    <main className="page">
      <div className="page-head"><h1>Messages</h1><button className="btn" onClick={sync}>Check for replies</button></div>
      <div className="split">
        <nav aria-label="Conversations" className="card convo-list">
          {list.loading && !list.data && <Loading />}
          {list.data?.length === 0 && <Empty title="No client replies yet">Replies appear here when clients answer your proposals.</Empty>}
          <ul>{(list.data || []).map((c) => (
            <li key={c.thread_id}><button className={`convo ${thread === c.thread_id ? "active" : ""}`} onClick={() => nav(`/messages/${c.thread_id}`)} data-testid="convo">
              <strong>{c.job_title}</strong><span className="row gap small"><Badge tone={c.status === "awaiting_approval" ? "info" : "neutral"}>{c.status.replace("_", " ")}</Badge>{c.intent && <Badge>{c.intent.replace("_", " ")}</Badge>}</span>
            </button></li>))}</ul>
        </nav>
        {thread ? <Thread id={thread} onChange={list.reload} /> : <div className="card"><p className="muted">Select a conversation.</p></div>}
      </div>
    </main>
  );
}

function Thread({ id, onChange }: { id: string; onChange: () => void }) {
  const { data, error, loading, reload } = useLoad<Any>(() => call(api.GET("/api/messages/{thread_id}", { params: { path: { thread_id: id } } })), [id], 0);
  const [text, setText] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const pend = data?.pending_approval;
  useEffect(() => { if (pend) setText(pend.reply.text); }, [pend]);
  if (loading && !data) return <div className="card"><Loading /></div>;
  if (error || !data) return <ErrorBox error={error || "not found"} onRetry={reload} />;
  async function decide(action: "approve" | "edit" | "reject") {
    const edited = pend && text !== pend.reply.text;
    const body = action === "reject" ? { action, reason } : edited ? { action: "edit" as const, cover_letter: text } : { action };
    const r = await call(api.POST("/api/messages/{thread_id}/decision", { params: { path: { thread_id: id } }, body }));
    setRunId(r.run_id);
  }
  return (
    <section className="card stack" aria-label="Conversation">
      <ol className="bubbles">{data.thread.messages.map((m: Any) => (
        <li key={m.id} className={`bubble ${m.sender}`}><span className="small muted">{m.sender === "client" ? "Client (untrusted text)" : "You"}</span><p>{m.text}</p></li>))}</ol>
      {runId && <RunTimeline runId={runId} compact onEnd={() => { setRunId(null); reload(); onChange(); }} />}
      {pend && !runId && (
        <div className="stack" data-testid="reply-approval">
          <h3>Suggested reply <Badge tone="info">{pend.intent.intent.replace("_", " ")}</Badge>{pend.intent.injection_detected && <Badge tone="warn">injection ignored</Badge>}</h3>
          {pend.slots?.length > 0 && <p className="small">Offered interview slots (from your calendar): {pend.slots.map((s: Any) => s.label).join(" · ")}</p>}
          <label htmlFor="reply" className="sr-only">Reply</label>
          <textarea id="reply" className="input" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row gap wrap">
            <button className="btn btn-primary" onClick={() => decide("approve")} data-testid="approve-reply">{text !== pend.reply.text ? "Save edit & re-check" : "Approve & send"}</button>
            <input className="input input-small" placeholder="reason to reject" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason to reject" />
            <button className="btn" disabled={!reason.trim()} onClick={() => decide("reject")}>Reject</button>
          </div>
          <p className="muted small">Nothing is sent until you approve.</p>
        </div>)}
      {!pend && !runId && <p className="muted small">No reply waiting. {data.state?.status === "sent" && "Your last reply was sent."} <Link to={`/jobs/${data.thread.job_id}`}>Open job</Link></p>}
    </section>
  );
}
