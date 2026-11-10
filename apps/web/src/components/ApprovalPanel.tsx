import { useState } from "react";
import { money } from "../lib/hooks";

export type Preview = { connects_cost?: number; balance_before?: number; balance_after?: number; weekly_budget?: number; spent_this_week?: number;
  within_weekly_budget?: boolean; would_send?: Record<string, unknown>; policy_version?: string };
export type Decision = { action: "approve" | "edit" | "reject"; reason?: string; cover_letter?: string; bid_amount?: number; screening_answers?: string[] };

/** The human gate: shows exactly what will be sent and what it costs, then approve / edit / reject (with a reason). */
export function ApprovalPanel({ preview, price, priceType, blocked, blockReasons, dirty, busy, onDecide }: {
  preview: Preview; price?: number; priceType?: string; blocked?: boolean; blockReasons?: string[]; dirty: boolean; busy: boolean;
  onDecide: (d: Decision) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [bid, setBid] = useState<string>(price ? String(price) : "");
  const bidNum = Number(bid) || undefined;
  return (
    <section className="card approval" aria-labelledby="approval-h" data-testid="approval-panel">
      <h3 id="approval-h">Approval</h3>
      {blocked && (
        <div className="banner banner-bad" role="alert" data-testid="compliance-block">
          <strong>Blocked by the Compliance Guard.</strong> {blockReasons?.join(" ")} Edit the draft to continue.
        </div>
      )}
      <dl className="kv">
        <dt>Bid</dt>
        <dd><label className="sr-only" htmlFor="bid">Bid amount</label>
          <input id="bid" type="number" min={1} value={bid} onChange={(e) => setBid(e.target.value)} className="input input-small" /> {priceType === "hourly" ? "USD/h" : "USD"}
        </dd>
        <dt>Connects</dt><dd data-testid="connects-cost">{preview.connects_cost ?? "-"} (balance {preview.balance_before ?? "?"} → {preview.balance_after ?? "?"})</dd>
        <dt>Weekly budget</dt>
        <dd className={preview.within_weekly_budget === false ? "text-bad" : ""}>{preview.spent_this_week ?? 0} of {preview.weekly_budget ?? "-"} used{preview.within_weekly_budget === false ? " - over budget" : ""}</dd>
        <dt>Policy</dt><dd>{preview.policy_version || "-"}</dd>
      </dl>
      <details>
        <summary>Dry-run preview: exactly what will be sent</summary>
        <pre className="pre" data-testid="dry-run">{JSON.stringify(preview.would_send, null, 2)}</pre>
      </details>
      {!rejecting ? (
        <div className="row gap">
          <button className="btn btn-primary" disabled={busy || blocked} data-testid="approve"
                  onClick={() => onDecide(dirty ? { action: "edit", bid_amount: bidNum } : { action: "approve", bid_amount: bidNum !== price ? bidNum : undefined })}>
            {dirty ? "Save edits & re-check" : `Approve & submit ${money(bidNum)}`}
          </button>
          <button className="btn" disabled={busy} data-testid="reject" onClick={() => setRejecting(true)}>Reject</button>
        </div>
      ) : (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) onDecide({ action: "reject", reason }); }}>
          <label htmlFor="reason">Why reject? (GigBid learns from this)</label>
          <input id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. client too far in time zone" data-testid="reject-reason" autoFocus />
          <div className="row gap">
            <button className="btn btn-danger" type="submit" disabled={!reason.trim() || busy} data-testid="confirm-reject">Reject proposal</button>
            <button className="btn" type="button" onClick={() => setRejecting(false)}>Cancel</button>
          </div>
        </form>
      )}
      <p className="muted small">Nothing is sent to the client until you approve. GigBid never auto-sends.</p>
    </section>
  );
}
