// Creates a pre-onboarded user with three drafts waiting for approval, so the approve / reject / edit specs
// each get their own pending proposal.  Token is written to .auth.json for the specs.
import { request } from "@playwright/test";
import fs from "node:fs";

const BASE = "http://127.0.0.1:8010";

export default async function globalSetup() {
  const ctx = await request.newContext({ baseURL: BASE });
  const email = `e2e-${Date.now()}@gigbid.test`;
  const reg = await (await ctx.post("/api/auth/register", { data: { email, password: "e2e-password-1", display_name: "E2E" } })).json();
  const headers = { Authorization: `Bearer ${reg.token}` };
  await ctx.post("/api/auth/onboarding", {
    headers, timeout: 300_000,
    data: { persona_key: "web", marketplace: "gigsim", hourly_rate: 40, min_project: 300, weekly_connects_budget: 200,
      saved_searches: [{ name: "Python backends", category: "web", skills: ["Django", "Celery"], limit: 4, interval_minutes: 20 }] },
  });
  const deadline = Date.now() + 330_000;
  let pending: { job_id: string }[] = [];
  while (Date.now() < deadline) {
    pending = await (await ctx.get("/api/proposals/pending", { headers })).json();
    if (pending.length >= 3) break;
    await new Promise((r) => setTimeout(r, 5000));
  }
  fs.writeFileSync("tests/e2e/.auth.json", JSON.stringify({ token: reg.token, email, pending: pending.map((p) => p.job_id) }));
  await ctx.dispose();
}
