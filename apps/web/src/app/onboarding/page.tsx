import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, call } from "../../lib/api/client";
import { useAuth } from "../../lib/auth";

const PERSONAS = [
  { key: "ai", title: "AI/ML engineer", text: "Sana Malik - LLM apps, RAG, production ML (18 case studies)", rate: 45, floor: 400 },
  { key: "web", title: "Full-stack web developer", text: "Omar Siddiqui - React, Next.js, Node, Django (17 case studies)", rate: 40, floor: 300 },
  { key: "data", title: "Data analyst", text: "Hira Baig - SQL, BI dashboards, experimentation (16 case studies)", rate: 30, floor: 150 },
] as const;

export default function OnboardingPage() {
  const [persona, setPersona] = useState<"ai" | "web" | "data" | "own">("web");
  const [market, setMarket] = useState<"gigsim" | "upwork">("gigsim");
  const [rate, setRate] = useState(40);
  const [floor, setFloor] = useState(300);
  const [budget, setBudget] = useState(60);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { refresh } = useAuth();
  const nav = useNavigate();

  async function finish() {
    setBusy(true); setErr(null);
    try {
      await call(api.POST("/api/auth/onboarding", { body: {
        persona_key: persona === "own" ? null : persona, marketplace: market, hourly_rate: rate, min_project: floor,
        weekly_connects_budget: budget, saved_searches: [] } }));
      if (market === "upwork") {
        const r = await call(api.GET("/api/auth/upwork/start"));
        location.assign(String((r as Record<string, unknown>).authorize_url));
        return;
      }
      await refresh();
      nav(persona === "own" ? "/settings?tab=portfolio" : "/inbox");
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }

  return (
    <main className="page narrow">
      <h1>Set up GigBid</h1>
      <section className="card stack" aria-labelledby="p1">
        <h2 id="p1">1. Whose portfolio?</h2>
        <div className="grid3" role="radiogroup" aria-label="Portfolio">
          {PERSONAS.map((p) => (
            <button key={p.key} role="radio" aria-checked={persona === p.key} data-testid={`persona-${p.key}`}
                    className={`choice ${persona === p.key ? "selected" : ""}`}
                    onClick={() => { setPersona(p.key); setRate(p.rate); setFloor(p.floor); }}>
              <strong>{p.title}</strong><span className="muted small">{p.text}</span>
            </button>
          ))}
          <button role="radio" aria-checked={persona === "own"} className={`choice ${persona === "own" ? "selected" : ""}`} onClick={() => setPersona("own")}>
            <strong>My own profile</strong><span className="muted small">Upload your CV, case studies, repos and past proposals next.</span>
          </button>
        </div>
      </section>
      <section className="card stack" aria-labelledby="p2">
        <h2 id="p2">2. Marketplace</h2>
        <label className="radio"><input type="radio" name="m" checked={market === "gigsim"} onChange={() => setMarket("gigsim")} /> GigSim (sandbox marketplace used for grading)</label>
        <label className="radio"><input type="radio" name="m" checked={market === "upwork"} onChange={() => setMarket("upwork")} /> Upwork (official MCP server, OAuth; every write is a draft you confirm on Upwork)</label>
      </section>
      <section className="card stack" aria-labelledby="p3">
        <h2 id="p3">3. Rates and budget</h2>
        <div className="grid3">
          <label>Hourly rate (USD)<input className="input" type="number" min={1} value={rate} onChange={(e) => setRate(+e.target.value)} data-testid="rate" /></label>
          <label>Minimum project (USD)<input className="input" type="number" min={0} value={floor} onChange={(e) => setFloor(+e.target.value)} /></label>
          <label>Weekly Connects budget<input className="input" type="number" min={0} value={budget} onChange={(e) => setBudget(+e.target.value)} data-testid="connects-budget" /></label>
        </div>
        <p className="muted small">Saved searches are created for your profile; edit them in Settings. GigBid scouts every 20 minutes in GigSim and at most every 3 hours on Upwork.</p>
      </section>
      {err && <div className="error" role="alert">{err}</div>}
      <button className="btn btn-primary btn-big" onClick={finish} disabled={busy} data-testid="finish-onboarding">
        {busy ? "Scouting your first jobs..." : "Finish and find jobs"}
      </button>
    </main>
  );
}
