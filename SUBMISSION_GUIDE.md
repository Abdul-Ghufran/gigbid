# GigBid — what is done, and the steps only you can do

Deadline: **12 Nov 2026, 11:59 PM PKT**. Commits after the deadline are ignored, so finish steps 1–6 well before it.
Do them in this order; each step says how long it takes.

---

## What is already done (no action needed)
- Full system built, tested and pushed to **https://github.com/Abdul-Ghufran/gigbid** (all commits under your name only).
- 50 automated tests + 6 Playwright end-to-end tests pass (report: `docs/playwright-report.pdf`); ruff lint clean; repo-rule checks pass.
- Evaluations run and stored in `evals/results/`: RAG variants V0–V9 + ablation, claim verifier, 600-job decisions, pricing,
  change request, R&D A (tool granularity), injection defence, X2 A/B test, retrieval-vs-outcome significance tests.
- An unattended finisher (`tools/finish_evals.py`) ran the live-model runs (live proposals, R&D C, model profiles) and
  regenerated the README tables and the report PDF, then committed and pushed. Check it finished:
  open `data/processed/finish_log.txt`; the last line should be `finisher done`.
- Docs: README, `docs/ARCHITECTURE.md`, `docs/TOOLS.md`, `docs/DATA_CARD.md`, `docs/RUNBOOK.md`, `docs/EXTENSION.md`,
  `docs/AI_USAGE.md`, six ADRs in `docs/adr/`, `docs/VIVA.md` (answers to all 10 viva questions), `docs/WRITEUP.md`, `docs/RESUME.md`.
- R&D report PDF: **`docs/report/GigBid_RnD_Report.pdf`**.
- Demo video: **`docs/demo/gigbid-demo.mp4`** (2 min 10 s, captioned: inbox → approved proposal, scam caught, injected
  instruction ignored, client reply handled). README GIF: `docs/images/demo.gif`.
- Portfolio MCP server is installable and was tested end to end:
  `uvx --from git+https://github.com/Abdul-Ghufran/gigbid gigbid-portfolio-mcp --portfolio-dir <folder>`

---

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
1. Open `evals/datasets/judge_calibration_sheet.csv` in Excel.
2. For each row, read the job and the proposal and type a score **1–5** in `your_score_1_to_5`
   (5 = specific, proven with relevant evidence, clear plan; 3 = relevant but generic; 1 = irrelevant/unbelievable). Save as CSV.
3. In a terminal in the project folder:
   ```bash
   .venv/Scripts/python.exe -m evals.runners.judge_calibration --kappa
   ```
   ```bash
   .venv/Scripts/python.exe tools/build_report.py
   ```
   ```bash
   cd apps/web && node scripts/render_pdf.mjs && cd ../..
   ```
   ```bash
   git add -A && git commit -m "Judge calibration with my labels" && git push
   ```

## Step 5 — Langfuse public traces (15 min) — needed for "links to three public traces"
1. **cloud.langfuse.com** → your project → **Settings → API keys** → create keys.
2. Render → service → Environment → add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (host is already set) → Save.
3. In the deployed app: Inbox → **Scout now**; open a scam job; open a good job → Proposal studio → **Approve**; to get a
   critic loop, open any job and click **Re-analyse** until a run shows two `writer` steps in the Run viewer.
4. In Langfuse → **Traces** → open each (scam skip, approved proposal, critic loop) → **Share → Public** → copy links into
   `docs/TRACES.md` → commit and push.
   *(If you skip Langfuse, the in-app Run viewer shows the same traces, but those links need a login.)*

## Step 5b — MCP Inspector screenshots (10 min) — required by A7
I could not run the Inspector myself (the automation sandbox does not allow downloading and running npm tools).
1. In a terminal in the project folder run `npx @modelcontextprotocol/inspector` (it opens http://localhost:6274 in your browser).
2. Left panel: **Transport = STDIO**, **Command** = `C:\Users\MABC\Desktop\i230576_AG2\.venv\Scripts\python.exe`,
   **Arguments** = `-m mcp_servers.portfolio.server --persona web`, **Environment**: add `AUDIT_DISABLED=1`. Click **Connect**
   (first connect takes ~1 minute while the portfolio is indexed).
3. **Tools → List Tools → search_evidence** → requirement `Celery background jobs` → **Run Tool** → screenshot.
   Also screenshot **Resources** (resource templates) and **Prompts** (`answer_screening_question`).
4. Disconnect, then the Marketplace server: Arguments `-m mcp_servers.marketplace.server`, Environment
   `GIGSIM_INPROCESS=1`, `GIGSIM_TOKEN=gigsim-dev-token-web`, `MCP_USER_ID=persona-web`, `GIGSIM_ERROR_RATE=0` →
   Connect → run `search_jobs` (category `web`, limit 3) and `submit_proposal` with `dry_run` true (it will say
   "proposal not found" for a made-up id — that error is fine to show) → screenshot the tool list with annotations.
5. Workspace server: Arguments `-m mcp_servers.workspace.server` → run `free_slots` → screenshot.
6. Save the PNGs as `docs/images/inspector_portfolio.png`, `inspector_marketplace.png`, `inspector_workspace.png`,
   then `git add docs/images && git commit -m "MCP Inspector screenshots" && git push`.

## Step 6 — Human panel with classmates (optional but listed in B4; 10 min of your time)
Send `evals/datasets/human_panel_pairs.csv` to 3–5 classmates; each fills `which_would_you_reply_to_A_or_B` (A or B)
and `rater_name`, and sends it back. Then:
```bash
.venv/Scripts/python.exe -m evals.runners.human_panel --csv rater1.csv --csv rater2.csv --csv rater3.csv
```
Rebuild the report as in Step 4 and push.

## Step 7 — Publish the technical write-up (10 min)
Copy `docs/WRITEUP.md` into a **Medium** story or a **LinkedIn article** (keep the tables and the result-file links),
publish it, and paste the link in the Classroom submission. It is 1,367 words (required 1,200–1,800).

## Step 8 — Demo video (10 min)
Upload `docs/demo/gigbid-demo.mp4` to **YouTube (Unlisted)** or Google Drive (anyone with the link can view) and copy
the link. Optional: record a voice-over while it plays. To re-record it against live models after deployment:
```bash
.venv/Scripts/python.exe tools/demo_server.py 8030 --live
```
then in a second terminal:
```bash
cd apps/web && node scripts/record_demo.mjs http://127.0.0.1:8030
```
and convert: `ffmpeg -i ../../docs/demo/gigbid-demo.webm -c:v libx264 -pix_fmt yuv420p ../../docs/demo/gigbid-demo.mp4`

## Step 9 — Build the ZIP (1 min)
```bash
git pull && make zip
```
(or `git archive --format=zip -o gigbid_submission.zip HEAD`). It contains only committed files, never `.env`.

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
`.venv/Scripts/python.exe -m pytest tests/integration -q`.

---

### Things that are honestly NOT done (and why)
- **Live Upwork mode** was built and tested against a mock (no Upwork account); report and README say so.
- **Real GigSim / official dev set** were not in the starter kit; a documented stand-in was built (see `docs/DATA_CARD.md`).
- Some live-model experiments are small (a few jobs) because Groq's free tier caps each model at 200K tokens/day;
  the report states the sample sizes.
- **Docker** images were not built on this laptop (Docker Desktop wasn't running); Render builds `infra/docker/render.Dockerfile`.
