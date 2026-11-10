import { useId, useState } from "react";

export type Evidence = { item_id: string; title: string; type: string; snippet: string; score?: number; source?: string };
export type Check = { claim: string; label: string; evidence_ids: string[]; best_evidence?: string | null; reason?: string };

const CITE = /\[([a-z]+-[a-z0-9-]+)\]/g;

function labelFor(sentence: string, checks: Check[]): Check | undefined {
  const bare = sentence.replace(CITE, "").trim().slice(0, 60);
  return checks.find((c) => c.claim.replace(CITE, "").trim().slice(0, 60) === bare);
}

/** Renders proposal text sentence by sentence; every claim shows its evidence (and verifier label) on hover/focus. */
export function EvidenceText({ text, evidence, checks }: { text: string; evidence: Record<string, Evidence>; checks: Check[] }) {
  const paras = text.split(/\n\s*\n/);
  return (
    <div className="evidence-text">
      {paras.map((p, pi) => (
        <p key={pi}>
          {p.split(/(?<=[.!?])\s+/).map((s, si) => {
            const ids = [...s.matchAll(CITE)].map((m) => m[1]);
            const check = labelFor(s, checks);
            if (!ids.length && !check) return <span key={si}>{s} </span>;
            return <Claim key={si} sentence={s} ids={ids} evidence={evidence} check={check} />;
          })}
        </p>
      ))}
    </div>
  );
}

function Claim({ sentence, ids, evidence, check }: { sentence: string; ids: string[]; evidence: Record<string, Evidence>; check?: Check }) {
  const [open, setOpen] = useState(false);
  const tid = useId();
  const tone = check?.label === "supported" ? "good" : check?.label === "partly_supported" ? "warn" : check?.label === "unsupported" ? "bad" : "info";
  const shown = ids.length ? ids : check?.evidence_ids || [];
  return (
    <span className={`claim claim-${tone}`} tabIndex={0} aria-describedby={tid} data-testid="claim"
          onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
      {sentence.replace(CITE, (m) => m)}{" "}
      <span role="tooltip" id={tid} className={`evidence-pop ${open ? "open" : ""}`} data-testid="evidence-pop">
        {check && <span className={`badge badge-${tone}`}>{check.label.replace("_", " ")}</span>}
        {shown.length === 0 && <em>No evidence cited.</em>}
        {shown.map((id) => {
          const e = evidence[id];
          return (
            <span key={id} className="ev">
              <strong>[{id}] {e?.title || "unknown item"}</strong> <small>{e?.type}</small>
              <span className="ev-snip">{(e?.snippet || check?.best_evidence || "").slice(0, 320)}</span>
            </span>
          );
        })}
        {check?.reason && <small className="muted">Verifier: {check.reason}</small>}
      </span>
    </span>
  );
}
