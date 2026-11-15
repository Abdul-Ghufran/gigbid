// Records the GigBid demo walkthrough (captioned) against a running demo server (tools/demo_server.py).
// Usage (from apps/web): node scripts/record_demo.mjs http://127.0.0.1:8030
// Output: ../../docs/demo/gigbid-demo.webm (convert with ffmpeg; see tools/make_demo_media.sh)
//
// Human-like recording: a visible cursor that glides to each target on a curved path, a ripple + outline on every
// click, credentials typed character by character, gradual mouse-wheel scrolling, and navigation through the app's own
// menu and links (only the first page is opened by URL).
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
await ctx.addInitScript(() => {
  const install = () => {
    if (document.getElementById("demo-cursor")) return;
    const st = document.createElement("style");
    st.textContent = "#demo-cursor{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;" +
      "transform:translate(-3px,-2px);transition:transform .08s;filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}" +
      "#demo-cursor.down{transform:translate(-3px,-2px) scale(.82)}" +
      ".demo-ripple{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;border:3px solid #f59e0b;" +
      "background:rgba(245,158,11,.25);z-index:2147483646;pointer-events:none;animation:demo-rip .7s ease-out forwards}" +
      "@keyframes demo-rip{to{transform:scale(4.2);opacity:0}}" +
      ".demo-target{outline:3px solid #f59e0b !important;outline-offset:3px}";
    document.head.appendChild(st);
    const c = document.createElement("div");
    c.id = "demo-cursor";
    c.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7.5 19 2.6-7.6L21 10.8z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    const pos = window.__demoPos || { x: 640, y: 360 };
    c.style.left = pos.x + "px"; c.style.top = pos.y + "px";
    document.addEventListener("mousemove", (e) => {
      c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; window.__demoPos = { x: e.clientX, y: e.clientY };
    }, true);
    document.addEventListener("mousedown", (e) => {
      c.classList.add("down");
      const r = document.createElement("div");
      r.className = "demo-ripple"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
      document.body.appendChild(r); setTimeout(() => r.remove(), 800);
    }, true);
    document.addEventListener("mouseup", () => c.classList.remove("down"), true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install); else install();
});
const page = await ctx.newPage();
const rnd = (a, b) => a + Math.random() * (b - a);
let cur = { x: 640, y: 360 };

async function caption(text, ms = 3500) {
  await page.evaluate((t) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      el.style.cssText = "position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1100px;padding:12px 20px;border-radius:12px;" +
        "background:rgba(17,24,39,.92);color:#fff;font:600 19px/1.4 system-ui,sans-serif;z-index:99999;box-shadow:0 8px 30px rgba(0,0,0,.35);" +
        "text-align:center;pointer-events:none";
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
  await sleep(ms);
}

// eased, slightly curved path (~0.4-0.9 s), like a hand moving a mouse
async function glide(x, y) {
  const from = { ...cur };
  const dist = Math.hypot(x - from.x, y - from.y) || 1;
  const n = Math.max(12, Math.min(45, Math.round(dist / 18)));
  const bend = rnd(-0.12, 0.12) * dist;
  for (let i = 1; i <= n; i++) {
    const t = i / n;
    const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const off = Math.sin(Math.PI * t) * bend;
    await page.mouse.move(from.x + (x - from.x) * e + off * ((from.y - y) / dist), from.y + (y - from.y) * e + off * ((x - from.x) / dist));
    await sleep(rnd(8, 18));
  }
  cur = { x, y };
}

// scroll with the wheel, a notch at a time, until the element sits comfortably in view
async function into(loc) {
  await loc.waitFor({ state: "attached", timeout: 15000 });
  for (let i = 0; i < 40; i++) {
    const b = await loc.boundingBox();
    if (!b) break;
    if (b.y > 80 && b.y + Math.min(b.height, 180) < 560) break;
    const dy = b.y < 80 ? -Math.min(240, 140 - b.y) : Math.min(240, b.y - 280);
    await page.mouse.wheel(0, dy);
    await sleep(rnd(110, 180));
  }
}

async function point(loc) {
  await into(loc);
  const b = await loc.boundingBox();
  if (!b) return;
  const w = Math.min(b.width, 260);
  await glide(b.x + w * rnd(0.3, 0.6), b.y + Math.min(b.height, 40) * rnd(0.4, 0.6));
  await loc.evaluate((el) => el.classList.add("demo-target"), undefined, { timeout: 1000 }).catch(() => {});
  await sleep(rnd(280, 450));
}

async function click(loc, after = 900) {
  await point(loc);
  await page.mouse.down(); await sleep(rnd(70, 120)); await page.mouse.up();
  // after a navigating click the element is gone: do not let Playwright wait its default 30 s for it
  await loc.evaluate((el) => el.classList.remove("demo-target"), undefined, { timeout: 400 }).catch(() => {});
  // the app polls in the background, so "networkidle" can take 30 s: settle briefly instead
  await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});
  await sleep(after);
}

async function typeHuman(loc, text) {
  await click(loc, 350);
  for (const ch of text) {
    await page.keyboard.type(ch);
    await sleep(ch === "@" || ch === "." || ch === "-" ? rnd(200, 340) : rnd(60, 160));
  }
  await sleep(rnd(300, 500));
}

async function scrollBy(total, step = 100) {
  const dir = Math.sign(total);
  for (let s = 0; s < Math.abs(total); s += step) { await page.mouse.wheel(0, dir * step); await sleep(rnd(120, 200)); }
}

const nav = (label) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label, exact: true });
async function openJob(id) {
  await click(nav("Inbox"), 1200);
  await click(page.locator(`a.job-title[href="/jobs/${id}"]`), 1300);
}

await page.goto(BASE + "/login");
await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
await page.mouse.move(cur.x, cur.y);
await sleep(800);
await caption("GigBid: a team of AI agents finds freelance jobs, flags scams and drafts proposals you approve.", 4000);
await typeHuman(page.getByLabel("Email"), "reviewer@gigbid.app");
await typeHuman(page.getByLabel("Password"), "demo-reviewer-pass");
await click(page.getByTestId("auth-submit"), 600);
await page.waitForURL(/inbox/);
await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});
await sleep(1500);
await caption("Job inbox: the Scout ran saved searches; Analyst, Risk Assessor and Fit Matcher scored each job in parallel.", 4500);
await point(page.locator("a.job-title").first());
await caption("Jobs are ranked by fit, with risk badges, the recommended action, a suggested price and the Connects cost.", 4500);
if (scam) {
  await openJob(scam.job_id);
  await caption("A scam caught: unpaid 'trial', off-platform contact and an unverified client - skipped before any drafting.", 5500);
  await scrollBy(480);
  await sleep(2000);
}
if (inj) {
  await openJob(inj.job_id);
  await caption("This post hides instructions for AI tools. GigBid quotes them in the risk report and never follows them.", 4500);
  const q = page.getByTestId("injection-quote");
  if (await q.count()) { await point(q); await sleep(3500); }
}
if (showcase) {
  await openJob(showcase.job_id);
  await caption("A good fit: every requirement is mapped to portfolio evidence; price rationale and bid-or-skip reasons are shown.", 5000);
  const m = page.getByTestId("evidence-matrix");
  if (await m.count()) { await point(m); await sleep(3000); }
  await scrollBy(-1500, 250);
  await click(page.getByTestId("open-studio"), 1500);
  await caption("Proposal studio: the draft passed claim verification, the Critic and the Compliance Guard.", 4500);
  const claim = page.getByTestId("claim").first();
  if (await claim.count()) { await point(claim); await caption("Hover any claim to see the portfolio evidence behind it.", 4500); }
  const dry = page.getByText("Dry-run preview");
  if (await dry.count()) { await click(dry, 800); await scrollBy(220); }
  await caption("The dry run shows exactly what will be sent and what it costs in Connects. Nothing is sent without approval.", 5000);
  await click(page.getByTestId("approve"), 300);
  await caption("Approved: the paused LangGraph thread resumes and submits exactly once (idempotency keys).", 1000);
  await page.getByTestId("run-timeline").waitFor({ timeout: 10000 }).catch(() => {});
  await sleep(6000);
}
await scrollBy(-2000, 300);
await click(nav("Pipeline"), 1200);
await caption("The pipeline board updates from marketplace events: submitted, viewed, replied, interview, hired.", 5000);
if (convo) {
  await click(nav("Messages"), 1200);
  const c = page.getByTestId("convo").first();
  if (await c.count()) await click(c, 1500);
  await caption("A client replied. The Client Liaison classified the intent and drafted an answer (with calendar slots for interviews).", 6000);
  const ar = page.getByTestId("approve-reply");
  if (await ar.count()) await click(ar, 600);
  await caption("The reply goes out only after approval; interview slots become tentative calendar holds.", 5500);
  await scrollBy(-2000, 300);
}
await click(nav("Runs"), 1200);
await caption("Every run is traced node by node: tool calls, tokens, cost and latency, with one trace id end to end.", 3000);
const firstRun = page.locator("table a").first();
if (await firstRun.count()) await click(firstRun, 1500);
await caption("The run viewer replays the execution trace and the MCP audit log for the same trace id.", 4000);
await scrollBy(440);
await sleep(1200);
await scrollBy(-2000, 300);
await click(nav("Analytics"), 1500);
await caption("Analytics: funnel, reply rate by category, Connects spent, cost and latency per proposal, A/B test arms.", 4500);
await scrollBy(330);
await sleep(1000);
await scrollBy(-2000, 300);
await click(nav("Settings"), 1000);
await click(page.getByTestId("tab-memory"), 1200);
await caption("Memory you control: style rules learned from your edits and outcome lessons - promoted only by explicit rules, deletable here.", 5500);
await caption("GigBid: open models, MCP tools, grounded proposals - and the freelancer stays in control.", 4500);
await ctx.close();
await browser.close();
const vid = fs.readdirSync(OUT).filter((f) => f.endsWith(".webm") && f !== "gigbid-demo.webm").map((f) => path.join(OUT, f))
  .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
fs.renameSync(vid, path.join(OUT, "gigbid-demo.webm"));
console.log("video:", path.join(OUT, "gigbid-demo.webm"));
