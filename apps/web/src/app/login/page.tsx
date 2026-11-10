import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, call } from "../../lib/api/client";
import { useAuth } from "../../lib/auth";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { signIn } = useAuth();
  const nav = useNavigate();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = mode === "login"
        ? await call(api.POST("/api/auth/login", { body: { email, password } }))
        : await call(api.POST("/api/auth/register", { body: { email, password, display_name: "" } }));
      signIn(r.token, r.user);
      nav(r.user.onboarded ? "/inbox" : "/onboarding");
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }
  return (
    <main className="auth-page">
      <section className="card auth-card">
        <h1 className="brand-big">GigBid</h1>
        <p className="muted">A team of AI agents that finds freelance jobs, flags scams and drafts proposals where every claim is backed by your portfolio. You approve everything before it is sent.</p>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "tab active" : "tab"} onClick={() => setMode("login")}>Sign in</button>
          <button role="tab" aria-selected={mode === "register"} className={mode === "register" ? "tab active" : "tab"} onClick={() => setMode("register")}>Create account</button>
        </div>
        <form onSubmit={submit} className="stack">
          <label htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" className="input" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
          {err && <div className="error" role="alert">{err}</div>}
          <button className="btn btn-primary" disabled={busy} data-testid="auth-submit">{busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}</button>
        </form>
      </section>
    </main>
  );
}
