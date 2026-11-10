import type { ReactNode } from "react";

export function Badge({ tone = "neutral", children, title }: { tone?: "good" | "warn" | "bad" | "info" | "neutral"; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function RiskBadge({ risk, scam, flags }: { risk?: number | null; scam?: boolean | null; flags?: string[] }) {
  if (scam) return <Badge tone="bad" title={flags?.join(", ")}>Scam risk</Badge>;
  if (risk == null) return <Badge>Unscored</Badge>;
  if (flags?.includes("prompt_injection")) return <Badge tone="warn" title="Instruction-like text found in the post; it was quoted and ignored">Injection ignored</Badge>;
  if (risk >= 0.5) return <Badge tone="warn" title={flags?.join(", ")}>Risk {Math.round(risk * 100)}%</Badge>;
  return <Badge tone="good" title={flags?.join(", ") || "no risk signals"}>Low risk</Badge>;
}

export function DecisionBadge({ decision }: { decision?: string | null }) {
  const tone = decision === "bid" ? "good" : decision === "watch" ? "info" : decision === "skip" ? "bad" : "neutral";
  return <Badge tone={tone}>{decision ? decision.toUpperCase() : "PENDING"}</Badge>;
}

export function FitBar({ fit }: { fit?: number | null }) {
  const v = Math.round((fit ?? 0) * 100);
  return (
    <div className="fitbar" role="meter" aria-label="Fit score" aria-valuenow={v} aria-valuemin={0} aria-valuemax={100}>
      <div className="fitbar-fill" style={{ width: `${v}%` }} />
      <span>{fit == null ? "-" : `${v}% fit`}</span>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty" role="status"><h3>{title}</h3>{children}</div>;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="loading" role="status" aria-live="polite"><span className="spinner" aria-hidden /> {label}...</div>;
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="error" role="alert">
      <strong>Something went wrong.</strong> {error}
      {onRetry && <button className="btn btn-small" onClick={onRetry}>Retry</button>}
    </div>
  );
}
