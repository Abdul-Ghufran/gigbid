# GigBid — what is done, and the steps only you can do

Deadline (extended): **Sunday 15 Nov 2026, midnight PKT**. Commits after the deadline are ignored, so finish steps
1–6 well before it. Do them in this order; each step says how long it takes.

> **Running commands on this laptop.** Windows Smart App Control now blocks `.venv\Scripts\python.exe`, so every
> command below uses **`.\gb.cmd`** instead (in the project folder, from PowerShell or Command Prompt). It runs the
> same project Python with the same packages. Example: `.\gb.cmd -m pytest -q`. Do not run `uv sync` or `uv run`:
> they rebuild the venv launcher, which Smart App Control blocks.

---

## What is already done (no action needed)
- Full system built, tested and pushed to **https://github.com/Abdul-Ghufran/gigbid** (all commits under your name only).
- 50 automated tests + 6 Playwright end-to-end tests pass (report: `docs/playwright-report.pdf`); ruff lint clean; repo-rule checks pass.
- Evaluations run and stored in `evals/results/`: RAG variants V0–V9 + ablation, claim verifier, 600-job decisions, pricing,
  change request, R&D A (tool granularity), injection defence, X2 A/B test, retrieval-vs-outcome significance tests.
- Live-model runs on Groq's free tier: live proposals on gpt-oss-120b (done), judge scores for the 30 calibration items
  (done), and three slower runs that are limited by Groq's **200,000 tokens/day per model** cap (≈ 8,000 tokens/hour
  refill): R&D C (`data/processed/rq_c_log.txt`), the judge's proposal-set means (`data/processed/judge_log.txt`) and
  the all-20b profile run (`data/processed/finish_log.txt`). Every one of them saves as it goes. See **Step 0**.
- Docs: README, `docs/ARCHITECTURE.md`, `docs/TOOLS.md`, `docs/DATA_CARD.md`, `docs/RUNBOOK.md`, `docs/EXTENSION.md`,
  `docs/AI_USAGE.md`, six ADRs in `docs/adr/`, `docs/VIVA.md` (answers to all 10 viva questions), `docs/WRITEUP.md`, `docs/RESUME.md`.
- R&D report PDF: **`docs/report/GigBid_RnD_Report.pdf`**.
- Demo video: **`docs/demo/gigbid-demo.mp4`** (2 min 10 s, captioned: inbox → approved proposal, scam caught, injected
  instruction ignored, client reply handled). README GIF: `docs/images/demo.gif`.
- Portfolio MCP server is installable and was tested end to end:
  `uvx --from git+https://github.com/Abdul-Ghufran/gigbid gigbid-portfolio-mcp --portfolio-dir <folder>`

---

## Step 0 — Fold the latest live-model rows into the report (2 min, any time before you submit)
The slow runs keep going in the background while the laptop is on (plugged in, lid set to "Do nothing"). Whenever you
want the report to include everything finished so far, run this in the project folder; it is safe while they are running:
```bash
.\gb.cmd tools/finalize_report.py "Fold in the latest live-model rows"
```
It summarises R&D C from the rows that **every** architecture has finished (like-for-like), refreshes the README tables
and the report PDF, runs the repo checks, commits under your name and pushes. Run it one last time just before Step 9.
If you want the full R&D C sample sooner, Groq's paid Dev Tier removes the daily cap (R&D C costs well under $1 there);
that is your call, not needed for submission. The report states the sample size it actually used.

## Step 1 — Fix GitHub Actions billing (5 min)
Your CI never started because GitHub says *"the job was not started because your account is locked due to a billing issue."*
1. Go to **github.com/settings/billing** → fix the failed payment / spending limit (public-repo Actions are free once the lock is lifted).
2. If nothing is shown there, open a ticket at **support.github.com** ("Actions blocked: account locked due to billing").
3. When fixed: repo → **Actions** → open the latest "CI" run → **Re-run all jobs**. (Optional: Settings → Secrets → Actions →
   add `GROQ_API_KEY` so the eval gate uses the real model.)

## Step 2 — Database on Neon (5 min)
1. **neon.tech** → your project `gigbid` → **Connection Details**.
2. Choose the **direct** connection (turn *Connection pooling* **off**) and copy the string. It looks like
   `postgresql://USER:PASSWORD@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`. Keep it private.

## Step 3 — Deploy on Render (15 min + ~10–15 min build)
1. **render.com** → **New +** → **Blueprint** → connect GitHub → pick **Abdul-Ghufran/gigbid** (it reads `render.yaml`).
2. Render asks for the secret values. Fill in:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon string from Step 2 |
   | `GIGSIM_STATE_DB` | the **same** Neon string |
   | `GROQ_API_KEY` | your Groq key (same as in your local `.env`) |
   | `REVIEWER_PASSWORD` | make up a password for the reviewer account (write it down) |
   | `PUBLIC_WEB_URL` and `PUBLIC_API_URL` | leave empty for now |
   | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | from Step 5 (optional; can be added later) |
   | `GITHUB_TOKEN` | leave empty (only needed for "Import GitHub repos") |
3. Click **Apply**. The first build takes 10–15 minutes (it builds the web app and downloads the open embedding model).
4. When it shows **Live**, copy the URL (e.g. `https://gigbid-xxxx.onrender.com`). In the service → **Environment**,
   set `PUBLIC_WEB_URL` and `PUBLIC_API_URL` to that URL → **Save** (it redeploys).
5. Test: open the URL → sign in with `reviewer@gigbid.app` and your `REVIEWER_PASSWORD`. The inbox fills within a few
   minutes (first visit after sleep takes ~1 minute: Render's free tier sleeps after 15 idle minutes).
6. *(Recommended)* Keep it awake for the hidden test: **uptimerobot.com** (free) → New monitor → HTTP(s) →
   `https://<your-url>/health` every 5 minutes. One always-on free service stays within Render's 750 free hours/month.

If the build fails, open the deploy log and send me (or any AI assistant) the last 30 lines; the Dockerfile is
`infra/docker/render.Dockerfile`.

## Step 4 — Label 30 proposals for judge calibration (20 min) — required by the rubric
The scores must be **yours**: this step measures how well the LLM judge agrees with a human (Cohen's kappa).
1. Open the labelling page: double-click `evals\datasets\label_helper.html` (or run `.\gb.cmd tools/label_helper.py`).
   It shows one job and its proposal at a time, with the rubric.
2. For each item, read the job, then the proposal, and click a score **1–5** (or press the 1–5 key). It moves to the
   next item by itself. Optionally type a short note on why (useful in the viva). About 30–60 seconds per item.
   (5 = answers this client's need with relevant evidence and a clear plan; 3 = on topic but generic;
   1 = irrelevant/unbelievable.) Your progress is kept if you close the tab.
3. When the counter says **All 30 scored**, click **Save CSV**. Move the downloaded `judge_calibration_sheet.csv` from
   your Downloads folder into `evals\datasets\`, replacing the old one.
   (Alternative: fill the `your_score_1_to_5` column of that CSV directly in Excel.)
4. In a terminal in the project folder:
   ```bash
   .\gb.cmd -m evals.runners.judge_calibration --kappa
   ```
   then rebuild the report and PDF, commit and push in one go:
   ```bash
   .\gb.cmd tools/finalize_report.py "Judge calibration with my labels"
   ```

## Step 5 — Langfuse public traces — DONE (2026-11-15)
Traces are exported over OpenTelemetry (Langfuse Cloud v4 no longer accepts the old SDK-v2 batch API, which is why the
first attempts showed nothing). The public links are in `docs/TRACES.md`, recorded and verified with
`.\gb.cmd tools/publish_traces.py` (needs `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` in your local `.env`; re-run it to
record fresh ones). Runs in the deployed app are also traced and marked public automatically (Render needs the same keys).

## Step 5b — MCP Inspector screenshots — DONE (2026-11-15, see docs/MCP_INSPECTOR.md)
Tested end to end on this laptop (all three servers over stdio through `gb.cmd`; Smart App Control blocks
`.venv\Scripts\python.exe`, so do not use that as the command).

**Start the Inspector**
1. In a terminal run `npx @modelcontextprotocol/inspector`; the browser opens the Inspector. Keep the terminal open.
2. Inspector v2 (server cards): **Add Servers ▾ → Import from client config → From file…** → pick
   `C:\Users\MABC\Desktop\i230576_AG2\docs\inspector\gigbid_servers.json` → **Import**. Three cards appear:
   `gigbid-portfolio`, `gigbid-marketplace`, `gigbid-workspace` (all start through `tools\mcp_stdio.cmd`, tested).
   Turn a card's switch on to connect it (portfolio needs 10–60 s), then use its Tools / Resources / Prompts views for the
   screenshots below. Older Inspector (single form): use the Command / Arguments / Environment values from that JSON
   file and set Configuration → Request Timeout to `300000`.

**Server 1: Portfolio** (screenshot `inspector_portfolio.png`)
3. **Transport Type** = `STDIO`; **Command** = `C:\Users\MABC\Desktop\i230576_AG2\gb.cmd`;
   **Arguments** = `-m mcp_servers.portfolio.server --persona web`.
   **Environment Variables** → Add: `AUDIT_DISABLED` = `1`. Click **Connect** (10–60 s; it shows *Connected*).
4. **Tools** tab → **List Tools** → click `search_evidence` → requirement `Celery background jobs` → **Run Tool**.
   Screenshot with the tool list and the green result visible.
5. **Resources** tab → **List Templates** (shows `portfolio://case/{id}` …) → screenshot.
   **Prompts** tab → **List Prompts** → `answer_screening_question` → question `How do you handle background jobs?` →
   **Get Prompt** → screenshot. Click **Disconnect**.

**Server 2: Marketplace** (screenshot `inspector_marketplace.png`)
6. **Arguments** = `-m mcp_servers.marketplace.server`. Environment: remove `AUDIT_DISABLED` row or keep it, and add
   `GIGSIM_INPROCESS`=`1`, `GIGSIM_TOKEN`=`gigsim-dev-token-web`, `MCP_USER_ID`=`persona-web`, `GIGSIM_ERROR_RATE`=`0`.
   **Connect** → **Tools → List Tools** (13 tools; read tools vs write tools carry different annotations) →
   `search_jobs`: category `web`, limit `3` → **Run Tool** → screenshot.
7. Optional second shot: `submit_proposal` with proposal_id `p-demo`, idempotency_key `demo-key-0001`, dry_run ticked →
   Run → it returns a "not found" problem for the made-up id: that is the guard working. **Disconnect**.

**Server 3: Workspace** (screenshot `inspector_workspace.png`)
8. **Arguments** = `-m mcp_servers.workspace.server` (same environment is fine) → **Connect** → **List Tools** →
   `free_slots` → **Run Tool** with the defaults → screenshot (three slots in Asia/Karachi).

**Save and push**
9. Save the PNGs as `docs\images\inspector_portfolio.png`, `inspector_marketplace.png`, `inspector_workspace.png`
   (extra shots: `inspector_portfolio_prompts.png` etc. are fine). Then, one at a time:
   `git add docs/images` · `git commit -m "MCP Inspector screenshots"` · `git push` — or just tell Claude "screenshots saved".

If **Connect** fails: check Command is the full path to `gb.cmd` and the terminal was opened in the project folder;
the Inspector's **Server Notifications / stderr** area shows `gigbid-portfolio: ready ...` when the portfolio server is up.

## Step 6 — Blind pairwise panel — DONE (2026-11-15: 15 human votes + LLM proxy panel)
Classmates were not available, so the panel has two clearly separated parts (the report labels both honestly):
- **LLM proxy panel — done:** `.\gb.cmd -m evals.runners.llm_panel` (three open models judge the 15 blind pairs as the
  client, in both A/B orders) → `evals/results/llm_panel.json`. This is *not* a human result and is never reported as one.
- **Your own votes (the human rater):**
  1. Double-click `evals\datasets\panel_helper.html` (or run `.\gb.cmd tools/panel_helper.py`).
  2. Type your name, then for each of the 15 pairs click the proposal **you would reply to** as the client (keys A / B).
     Which pipeline wrote which is hidden and the sides are shuffled. About 20 seconds per pair.
  3. **Save CSV** → move `human_panel_votes.csv` from Downloads into `evals\datasets\` → tell Claude "panel votes saved"
     (or run `.\gb.cmd -m evals.runners.human_panel --csv evals/datasets/human_panel_votes.csv` and Step 4's
     `finalize_report.py` command yourself).
  If classmates do send filled CSVs later, add each with another `--csv`.

## Step 7 — Publish the technical write-up (15 min)
1. Double-click `docs\writeup_publish.html` (or run `.\gb.cmd tools/writeup_publish.py`): the article, paste-ready
   (1,372 words; the results table is a list because Medium/LinkedIn articles have no tables).
2. **Medium:** medium.com → sign in (Google is fine) → **Write** (pencil icon, top right).
   In the paste-ready page click **1. Copy title** → click Medium's **Title** line → Ctrl+V → press **Enter**.
   Click **2. Copy article body** → Ctrl+V into the story body. Check the links are blue and the headings are bold.
   Optional cover image: on an empty line click **+** → image icon → `docs\images\bid_graph.png`.
3. **Publish** (top right) → Topics: `Artificial Intelligence`, `Machine Learning`, `LLM`, `Retrieval Augmented Generation`,
   `Software Engineering` → **Publish now**. Copy the story URL from the address bar.
   (LinkedIn instead: linkedin.com → **Write article** → same paste steps → **Next** → **Publish**.)
4. Open the URL in a private window to confirm it is public, then send the link to Claude (it goes in the Classroom
   submission and the README).

## Step 8 — Demo video (10 min, or ~45 min to record your own)
**To record it yourself**, follow `docs/DEMO_WALKTHROUGH.md`: it lists every click, scene by scene, with suggested
narration and timings for a 3-minute video. Otherwise use the ready-made video:
Upload `docs/demo/gigbid-demo.mp4` to **YouTube (Unlisted)** or Google Drive (anyone with the link can view) and copy
the link. Optional: record a voice-over while it plays. To re-record it against live models after deployment:
```bash
.\gb.cmd tools/demo_server.py 8030 --live
```
then in a second terminal:
```bash
cd apps/web; node scripts/record_demo.mjs http://127.0.0.1:8030; cd ../..
```
and convert: `ffmpeg -i ../../docs/demo/gigbid-demo.webm -c:v libx264 -pix_fmt yuv420p ../../docs/demo/gigbid-demo.mp4`

## Step 9 — Build the ZIP (1 min)
```bash
git archive --format=zip -o gigbid_submission.zip HEAD
```
It contains only committed files, never `.env`. Run it after the last Step 0 / Step 4 push.

## Step 10 — Submit on Google Classroom (5 min)
Attach / paste, in one submission:
- **R&D report PDF:** `docs/report/GigBid_RnD_Report.pdf`
- **ZIP:** `gigbid_submission.zip`
- **Deployed URL:** your Render URL
- **GitHub repo:** https://github.com/Abdul-Ghufran/gigbid
- **Demo video link** (Step 8)
- **Portfolio MCP server:** https://github.com/Abdul-Ghufran/gigbid/tree/main/mcp_servers/portfolio
  (install command in its README)
- **Technical write-up link** (Step 7)

**Private comment** (Classroom → "Add private comment", NOT in the repo):
```
Reviewer login for GigBid: <your Render URL>
Email: reviewer@gigbid.app
Password: <your REVIEWER_PASSWORD>
The account is preloaded with the full-stack developer persona and demo searches (including a scam and a planted-injection post).
First load after idle can take ~1 minute (free tier).
```

## Step 11 — Viva preparation (30–60 min)
Read `docs/VIVA.md` — it answers each of the 10 viva questions with the exact file, function and test to show.
Practise locally: `make dev` (or `python tools/demo_server.py 8030 --live`), and run the crash/exactly-once proof:
`.\gb.cmd -m pytest tests/integration -q`.

---

### Things that are honestly NOT done (and why)
- **Live Upwork mode** was built and tested against a mock (no Upwork account); report and README say so.
- **Real GigSim / official dev set** were not in the starter kit; a documented stand-in was built (see `docs/DATA_CARD.md`).
- Some live-model experiments are small (a few jobs) because Groq's free tier caps each model at 200K tokens/day;
  the report states the sample sizes.
- **Docker** images were not built on this laptop (Docker Desktop wasn't running); Render builds `infra/docker/render.Dockerfile`.
