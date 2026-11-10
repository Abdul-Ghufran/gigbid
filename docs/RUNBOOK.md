# Runbook

## Run locally
| Goal | Command |
|---|---|
| Full stack (web, API, worker, 3 MCP servers, GigSim, Postgres+pgvector, Redis) | `make up` (= `docker compose -f infra/docker-compose.yml up --build`) → web http://localhost:8080 |
| + local open models (Ollama: qwen3:4b, gpt-oss:20b) | `docker compose -f infra/docker-compose.yml --profile local up` and `MODEL_PROFILE=local` |
| Single process, no Docker | `make install` then `make dev` (API with in-process worker, MCP over in-memory transport, GigSim in-process; Vite on :5173) |
| Tests | `make test` (unit, integration, contract) · `make e2e` (Playwright) · `make lint` (ruff + repo rules + typecheck) |
| Evaluations | `make eval` (writes `evals/results/*.json`) · `make eval-smoke` (CI gate) |

Copy `.env.example` to `.env`. Secrets only come from environment variables.

## Deploy (Render free tier)
Render's free web service has 0.1 CPU and 512 MB RAM and sleeps after 15 idle minutes. GigBid therefore deploys as **one
container** (`infra/docker/render.Dockerfile`, blueprint `render.yaml`): FastAPI + in-process worker + the three MCP
servers over the in-memory MCP transport (real JSON-RPC, no extra processes) + GigSim in-process, serving the built web
app. Measured idle RSS ≈ 260 MB after removing the cross-encoder from the runtime path (verification uses the bi-encoder,
same F1 — `evals/results/verifier_eval.json`). Postgres is Neon (free); GigSim persists its state in the same database
(`GIGSIM_STATE_DB`) because Render's disk is ephemeral. Redis (Upstash) is optional: with `REDIS_URL` set the API enqueues
to Arq, but a separate worker process does not fit in 512 MB, so production leaves it unset and uses the in-process worker.

Cold start after sleep: ~40–60 s (model load). The reviewer should open the URL once and wait for the inbox to appear.

## Scheduling and rate limits
| Mode | Scout interval | Why |
|---|---|---|
| GigSim | every 20 min per saved search (cron every 10 min checks which searches are due) | GigSim releases one live job per 20 simulated minutes |
| Upwork live | **at least 3 hours** per saved search, enforced twice (scheduler and `UpworkLiveAdapter.min_search_interval_s`) | Upwork treats aggressive polling as scraping; freelancers realistically check a few times a day; 3 h keeps us far below any API quota and still catches jobs within a working session |

Marketplace calls go through a per-user token bucket at 40 req/min (GigSim allows 60), with exponential backoff + jitter
and `Retry-After` handling. LLM calls go through a per-model RPM/TPM limiter; a 429 with a long wait (daily quota) fails
over to the fallback model immediately and finally to the deterministic offline path.

## Degraded mode (viva question 1)
Kill the marketplace (stop GigSim, or point `GIGSIM_BASE_URL` at a dead port):
1. `/api/system/status` probes the Marketplace MCP server (`get_policy`, 6 s timeout) → `marketplace: down`.
2. The UI shows the red **Marketplace unavailable** banner (`apps/web/src/components/DegradedBanner.tsx`) on every page.
3. Graph runs that hit it raise `MarketplaceDown` (`agent/mcp_client.py`) after bounded retries; `agent/runner.py` parks the job
   as `queued_retry`; drafts and pending approvals are untouched (they live in Postgres checkpoints).
4. `worker/tasks.py::recover` (on start and every 30 min) re-enqueues `queued_retry` jobs; after 3 failed runs → `dead_letter`.
Covered by the Playwright test "degraded mode".

## Crash and exactly-once (viva question 2)
Approve a proposal, kill the API/worker before `submit` finishes, restart. `recover()` continues runs left in `running`
from their last checkpoint; the submit node reuses the same idempotency keys, so the marketplace (and our own
`idempotency` table) return the stored result: one submission, Connects spent once. Proof: integration test
`test_crash_while_waiting_then_resume_submits_exactly_once` and the audit log (one non-replayed `submit_proposal` row).

## Switching GigSim → live Upwork (viva question 7)
Set `MARKETPLACE_MODE=upwork_live` (or connect Upwork in Settings, which stores an encrypted OAuth token for that user).
What changes: the Marketplace MCP server picks `UpworkLiveAdapter`, which calls Upwork's official MCP server through
`MultiServerMCPClient` and maps tools via `upwork_tool_map.yaml`. What does not change: the agents, the graph, the tool
names and schemas the agents see, the approval flow. In live mode `submit_proposal` never submits — it leaves a draft the
freelancer confirms on Upwork.

## Change request (2 Nov 2026 policy update)
Absorbed in one commit touching only `agent/config.yaml` (+4/−4) and the policy pack (+2). See
`evals/results/change_request_eval.json` and the report.

## Budgets (declared in agent/config.yaml)
p95 latency per job analysed ≤ 25 s, per proposal ≤ 90 s; ≤ $0.002 per job analysed and ≤ $0.01 per proposal at Groq list
prices (the free tier bills $0). Measured values: report §10 and `evals/results/`.

## Groq free-tier limits we designed around
Per model: 30 RPM, 1,000 requests/day, 8,000 tokens/min, **200,000 tokens/day**; Qwen additionally 1,000 output
tokens/min. One full proposal costs ~12–17K tokens, so a busy day can exhaust the strong model; GigBid then falls back
(other model → deterministic templates) instead of failing, and the token diet (deterministic critic pre-checks, trimmed
evidence) cut writer/critic tokens.
