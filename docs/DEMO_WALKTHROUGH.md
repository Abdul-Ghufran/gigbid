# Recording the GigBid demo video yourself — click-by-click walkthrough

Target length: **about 3 minutes** of final video (record more, trim later). Every click below was checked against the
running app on 11 Nov 2026. Job titles come from the seeded GigSim world and should be the same for you; if one differs,
use the badge described next to it to find the right job.

---

## Part A — Before you record (10 min, not recorded)

### 1. Choose the mode
- **Offline mode (recommended for recording).** Same app, same agents and graph, but the LLM calls use the built-in
  deterministic fallbacks, so every screen loads in seconds. Use this today: Groq's free daily token quota is used up by
  the evaluations, and in live mode each analysis would wait minutes for quota. Say this once in the video (Scene 1).
- **Live mode** (`--live`, real Groq models). Only once the quota has refilled (a few hours after the background
  evaluations finish), and expect each job analysis to take 1–3 minutes. Same clicks otherwise.

### 2. Start the app
Open a terminal in the project folder (`C:\Users\MABC\Desktop\i230576_AG2`) and run:
```bash
.venv/Scripts/python.exe tools/demo_server.py 8030
```
(For live mode add `--live` at the end.) Leave this terminal open. It starts a **fresh** demo database every time, with
the reviewer account already created, so you can redo a take by stopping it (Ctrl+C) and running it again.

### 3. Set up the browser and recorder
- Open **Chrome or Edge**, go to **http://127.0.0.1:8030**. Zoom at 100% (Ctrl+0). Hide the bookmarks bar
  (Ctrl+Shift+B). Close other tabs. Make the window about 1280×720 or full-screen (F11).
- Recorder options (pick one):
  - **Xbox Game Bar** (built into Windows): **Win+Alt+R** starts/stops recording the current window. Turn the mic on in
    Win+G → Capture settings if you want to narrate live.
  - **OBS Studio** (free, better quality): Sources → *Window Capture* → the browser; Settings → Output → mp4.
  - **Clipchamp** (built into Windows 11) for trimming and adding captions afterwards.
- Tip: record the narration separately afterwards if talking while clicking is hard; Clipchamp can add a voice-over.

### 4. Optional warm-up
Do one full run-through without recording (Scenes 1–11), then restart the server (Ctrl+C, run the command again) so the
recorded take starts from an empty inbox.

---

## Part B — The walkthrough (record this)

Each scene: **what to click** → **what to point at** → *what to say* (suggested narration, ~10–25 seconds each).

### Scene 1 — Sign in (0:00–0:10)
1. On the login page type **Email** `reviewer@gigbid.app`, **Password** `demo-reviewer-pass` (local demo account only;
   the deployed app uses the private reviewer password).
2. Click **Sign in**. You land on **Job inbox**.

*"This is GigBid, a multi-agent copilot for freelancers. A team of LangGraph agents finds jobs, checks them for scams,
matches them to my portfolio and drafts proposals, but nothing is sent without my approval. This recording runs on the
offline model fallbacks; the deployed version uses open models on Groq."*

### Scene 2 — Scout and the inbox (0:10–0:35)
1. Click **Scout now** (top right of the inbox).
2. Jobs appear with the status **analysing**. Wait ~1 minute (pause the recording or cut this in editing) until every
   job shows a result: you should see **6 drafts waiting for approval and 1 skipped**.
3. Point at: the ranking by fit, the risk badges, the recommended action, the suggested price and the Connects cost.
4. Click the filter chip **Needs my approval** to show only drafts, then click the first chip to show all again.

*"The Scout runs my saved searches over the marketplace MCP server. For each job the Analyst, Risk Assessor and Fit
Matcher run in parallel; the inbox is ranked by fit and shows risk, a suggested price and the Connects cost."*

### Scene 3 — A scam caught (0:35–0:55)
1. Click the job **"Quick paid test task - start today"** (the one marked skipped / scam).
2. Scroll to **Risk report** and **Bid or skip?**

*"This one is a scam: an unpaid 'test task', contact off the platform and an unverified client. The risk rules are
code, not prompts, so the job is skipped before any proposal is drafted."*

### Scene 4 — Prompt injection ignored (0:55–1:10)
1. Back to **Inbox** (top nav). Click **"Build web app with WebSockets and TypeScript"** (it has the prompt-injection
   flag).
2. In **Risk report**, point at the quoted hidden instruction.

*"This post hides instructions aimed at AI tools. GigBid quotes them in the risk report as untrusted data and never
follows them; the Compliance Guard also checks the final proposal."*

### Scene 5 — A good fit, evidence first (1:10–1:30)
1. Back to **Inbox**. Click **"Senior PostgreSQL engineer for advertising product"** (or any job marked draft ready).
2. Scroll through: **Agents at work**, **Bid or skip?** (the reasons), **JobSpec**, and the
   **Requirement → evidence matrix**.

*"For a good fit, every requirement in the post is mapped to evidence from my portfolio through the portfolio MCP
server and advanced RAG. Unsupported requirements are marked, never invented."*

### Scene 6 — Proposal studio and approval (1:30–2:00)
1. On the same job, click **Open proposal studio** (top of the page). From the inbox, the **Review draft** button on a
   job row opens the same page.
2. **Evidence view** tab: hover a highlighted sentence. A popup shows the portfolio evidence behind that claim.
3. Point at the **Critic** score and the **Compliance** badge on the right, and the **Screening answers**.
4. Optional: click **Regenerate ¶1** to rewrite one paragraph; or **Edit**, change a word, then
   **Save edits & re-check**.
5. In the **Approval** panel, point at **Bid amount**, **Connects**, **Weekly budget**, **Policy**, then open
   **Dry-run preview: exactly what will be sent**.
6. Click **Approve & submit $…**. The run timeline appears and shows the graph resuming and submitting.

*"Every claim in the letter is verified against the evidence; the Critic and the Compliance Guard have passed it. The
dry run shows exactly what will be sent and what it costs. When I approve, the paused LangGraph thread resumes and
submits exactly once, using idempotency keys."*

### Scene 7 — Approve a few more (2:00–2:10, can be cut short)
Clients only reply to submitted proposals, so submit 2–3 more:
1. **Inbox** → **Needs my approval** → **Review draft** on another job → **Approve & submit**. Repeat for 2–3 jobs.
   (Trim this down to a few seconds in editing.)

### Scene 8 — Pipeline and client reactions (2:10–2:20)
1. Click **Pipeline** in the top nav.
2. Click **Advance GigSim clock 3 h**. The cards move: submitted → viewed → replied.

*"The pipeline updates from marketplace events. GigSim is our simulated marketplace, so I can move its clock forward to
let clients react."*

### Scene 9 — A client replied (2:20–2:40)
1. Click **Messages** in the top nav, then **Check for replies**. (One clock advance gave 3 replies in testing; if the
   list is empty, go back to Pipeline, advance once more, and check again.)
2. Open a conversation. Point at **Client (untrusted text)**, the detected intent and the drafted answer (interview
   requests come with calendar slots).
3. Click **Approve & send**.

*"A client replied. The Client Liaison classified the intent and drafted an answer; for interviews it proposes calendar
slots. Again, it only goes out after I approve it."*

### Scene 10 — Tracing and analytics (2:40–2:55)
1. Click **Runs**, then open the top run.
2. Point at the **Trace id**, the **Execution trace** (node by node, with tokens, cost and latency) and the
   **MCP audit log (same trace id)**.
3. Click **Analytics**: **Funnel**, **Reply and hire rate by category**, **Proposal A/B test (X2)**,
   **Top rejection / skip reasons**.

*"Every run is traced node by node with one trace id, end to end through the MCP servers. Analytics shows the funnel,
reply rates, costs and the A/B test of two proposal strategies."*

### Scene 11 — Memory and settings (2:55–3:10)
1. Click **Settings**. Tabs: **general**, **searches**, **memory**, **portfolio**, **accounts**.
2. **memory**: **Style memory** and **Outcome memory**, each with **Forget**. (Rules appear after you have edited three
   drafts the same way; if the list is empty, just say how it works.)
3. **portfolio**: **Add work** (Add and re-index) and the GitHub import box, and the **Portfolio items** list.
4. **accounts**: **Connect Upwork (OAuth)**. Point at it, do not click through.

*"I control the memory: style rules learned from my edits and lessons from outcomes are promoted only by explicit
rules, and I can delete any of them. My portfolio can be updated or imported from GitHub, and the same agents can work
against the real Upwork MCP server through OAuth."*

**Closing line:** *"GigBid: open models, MCP tools, grounded proposals, and the freelancer stays in control."*
Stop recording.

---

## Part C — Optional extra scene: marketplace down (30 s)
Shows the degraded-mode banner (viva question 1). Stop the demo server first (Ctrl+C), then:
```bash
.venv/Scripts/python.exe tools/e2e_server.py 8011 --degraded
```
Open **http://127.0.0.1:8011** → **Create account** (any email such as `demo@test.io` and any password) → complete the
**Set up GigBid** onboarding → **Finish and find jobs**. A red **Marketplace unavailable** banner appears and jobs are
parked as *Queued (marketplace down)* instead of failing.
*"If the marketplace server is down, the user sees it immediately; jobs are queued and retried automatically."*

---

## Part D — After recording
1. Trim pauses (especially the ~1 minute analysis wait and Scene 7) in **Clipchamp** or any editor; keep it near 3 minutes.
2. Export as **MP4, 1080p or 720p**.
3. Upload to **YouTube as Unlisted** (or Google Drive, "anyone with the link"), copy the link, and use it in the
   Classroom submission (SUBMISSION_GUIDE Step 10). Optionally replace `docs/demo/gigbid-demo.mp4` with your video and
   commit it (keep it under ~50 MB).
4. Stop the demo server with Ctrl+C.

### If something goes wrong
- **Inbox stays empty**: you have not clicked **Scout now** (the demo server does not scout on its own).
- **"Address already in use"**: an old server is still running. Close that terminal or use another port
  (`... demo_server.py 8031`, then open http://127.0.0.1:8031).
- **No client replies**: approve at least 3 drafts first, then advance the clock again.
- **Live mode is very slow**: that is Groq's free-tier quota; record in offline mode instead.
