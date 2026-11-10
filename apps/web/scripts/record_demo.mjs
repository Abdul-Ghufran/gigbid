// Records the GigBid demo walkthrough (captioned) against a running demo server (tools/demo_server.py).
// Usage (from apps/web): node scripts/record_demo.mjs http://127.0.0.1:8030
// Output: ../../docs/demo/gigbid-demo.webm (convert with ffmpeg; see tools/make_demo_media.sh)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8030";
const OUT = path.resolve(process.cwd(), "../../docs/demo");
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(p, opts = {}, token) {
  const r = await fetch(BASE + p, { ...opts, headers: { "content-type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(opts.headers || {}) } });
  if (!r.ok) throw new Error(`${p} ${r.status} ${await r.text()}`);
  return r.json();
}

// ---------------------------------------------------------------- prepare data (not recorded)
const login = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email: "reviewer@gigbid.app", password: "demo-reviewer-pass" }) });
const T = login.token;
await api("/api/jobs/scout", { method: "POST" }, T).catch(() => {});
for (let i = 0; i < 120; i++) {
  const jobs = await api("/api/jobs?include_duplicates=false", {}, T);
  if (jobs.length && jobs.every((j) => !["analysing", "new"].includes(j.status))) break;
  await sleep(5000);
}
let jobs = await api("/api/jobs", {}, T);
const scam = jobs.find((j) => j.scam);
const inj = jobs.find((j) => (j.flags || []).includes("prompt_injection"));
const pending = jobs.filter((j) => j.status === "awaiting_approval");
const showcase = pending.find((j) => j.job_id !== inj?.job_id) || pending[0];
console.log("scam", scam?.job_id, "injection", inj?.job_id, "pending", pending.map((j) => j.job_id));
// submit the other drafts so clients can reply, then advance GigSim time
for (const j of pending.filter((j) => j.job_id !== showcase?.job_id)) {
  await api(`/api/proposals/${j.job_id}/decision`, { method: "POST", body: JSON.stringify({ action: "approve" }) }, T).catch((e) => console.log(e.message));
}
await sleep(20000);
await api("/api/demo/tick?minutes=240", { method: "POST" }, T).catch((e) => console.log(e.message));
let convo = null;
for (let i = 0; i < 60 && !convo; i++) {
  const cs = await api("/api/messages", {}, T);
  convo = cs.find((c) => c.status === "awaiting_approval");
  if (!convo) { await api("/api/messages/sync", { method: "POST" }, T).catch(() => {}); await sleep(5000); }
}
console.log("conversation", convo?.thread_id);

// ---------------------------------------------------------------- record
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
const page = await ctx.newPage();
async function caption(text, ms = 3500) {
  await page.evaluate((t) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      el.style.cssText = "position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1100px;padding:12px 20px;border-radius:12px;" +
        "background:rgba(17,24,39,.92);color:#fff;font:600 19px/1.4 system-ui,sans-serif;z-index:99999;box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center";
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
  await sleep(ms);
}
async function go(url, text, ms) { await page.goto(BASE + url); await page.waitForLoadState("networkidle").catch(() => {}); await sleep(900); if (text) await caption(text, ms); }

await go("/login", "GigBid: a team of AI agents finds freelance jobs, flags scams and drafts proposals you approve.", 4500);
await page.getByLabel("Email").fill("reviewer@gigbid.app");
await page.getByLabel("Password").fill("demo-reviewer-pass");
await page.getByTestId("auth-submit").click();
await page.waitForURL(/inbox/);
await sleep(1500);
await caption("Job inbox: the Scout ran saved searches; Analyst, Risk Assessor and Fit Matcher scored each job in parallel.", 5000);
await caption("Jobs are ranked by fit, with risk badges, the recommended action, a suggested price and the Connects cost.", 5000);
if (scam) {
  await go(`/jobs/${scam.job_id}`, "A scam caught: unpaid 'trial', off-platform contact and an unverified client - skipped before any drafting.", 6000);
  await page.mouse.wheel(0, 500); await sleep(2500);
}
if (inj) {
  await go(`/jobs/${inj.job_id}`, "This post hides instructions for AI tools. GigBid quotes them in the risk report and never follows them.", 5000);
  await page.getByTestId("injection-quote").scrollIntoViewIfNeeded().catch(() => {}); await sleep(4500);
}
if (showcase) {
  await go(`/jobs/${showcase.job_id}`, "A good fit: every requirement is mapped to portfolio evidence; price rationale and bid-or-skip reasons are shown.", 5500);
  await page.getByTestId("evidence-matrix").scrollIntoViewIfNeeded().catch(() => {}); await sleep(4000);
  await go(`/studio/${showcase.job_id}`, "Proposal studio: the draft passed claim verification, the Critic and the Compliance Guard.", 5000);
  const claim = page.getByTestId("claim").first();
  if (await claim.count()) { await claim.hover(); await caption("Hover any claim to see the portfolio evidence behind it.", 5000); }
  await page.getByText("Dry-run preview").click().catch(() => {});
  await caption("The dry run shows exactly what will be sent and what it costs in Connects. Nothing is sent without approval.", 5500);
  await page.getByTestId("approve").click();
  await caption("Approved: the paused LangGraph thread resumes and submits exactly once (idempotency keys).", 1000);
  await page.getByTestId("run-timeline").waitFor().catch(() => {});
  await sleep(9000);
}
await go("/pipeline", "The pipeline board updates from marketplace events: submitted, viewed, replied, interview, hired.", 5500);
if (convo) {
  await go(`/messages/${convo.thread_id}`, "A client replied. The Client Liaison classified the intent and drafted an answer (with calendar slots for interviews).", 6500);
  await page.getByTestId("approve-reply").click().catch(() => {});
  await caption("The reply goes out only after approval; interview slots become tentative calendar holds.", 6000);
}
await go("/runs", "Every run is traced node by node: tool calls, tokens, cost and latency, with one trace id end to end.", 3000);
await page.locator("table a").first().click().catch(() => {});
await sleep(1500); await caption("The run viewer replays the execution trace and the MCP audit log for the same trace id.", 5000);
await go("/analytics", "Analytics: funnel, reply rate by category, Connects spent, cost and latency per proposal, A/B test arms.", 5000);
await go("/settings?tab=memory", "Memory you control: style rules learned from your edits and outcome lessons - promoted only by explicit rules, deletable here.", 6000);
await caption("GigBid: open models, MCP tools, grounded proposals - and the freelancer stays in control.", 4500);
await ctx.close();
await browser.close();
const vid = fs.readdirSync(OUT).filter((f) => f.endsWith(".webm")).map((f) => path.join(OUT, f)).sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
fs.renameSync(vid, path.join(OUT, "gigbid-demo.webm"));
console.log("video:", path.join(OUT, "gigbid-demo.webm"));
