# AI usage disclosure

**Tool:** Claude Code (Anthropic), used as a pair programmer in the terminal throughout the project. I reviewed,
ran and tested everything that was committed, and I am accountable for every line.

| Area | Files | How the assistant was used |
|---|---|---|
| Synthetic world | `tools/synth/*`, `gigsim/*` | drafted the generator and simulator from my spec of the missing starter-kit assets; I set the distributions and gold-label rules |
| MCP servers | `mcp_servers/*` | scaffolding of FastMCP tools, schemas and tests; I chose annotations, idempotency and auth design |
| RAG | `rag/*`, `evals/runners/rag_eval.py`, `ablation.py`, `calibrate_*.py` | implemented variants V0–V9 and the evaluation; shipped choice made from the measured results |
| Agents | `agent/*` | node implementations, prompts, graph wiring, memory rules |
| API / web | `apps/api/*`, `apps/web/*` | routers, SSE bridge, React screens, Playwright tests |
| Infra / docs | `infra/*`, `.github/*`, `docs/*`, `README.md` | Dockerfiles, CI, documentation drafts |

## Things the assistant got wrong that were caught
1. **Claim verifier labelled fabricated numbers as "partly supported".** The first verifier detected 0 % of wrong-number
   claims and 6 % of wrong-tool claims (`evals/results/verifier_eval_v1_rule.json`). Measuring it on a labelled claim set
   exposed the bug; the rule was changed so any number or tool absent from the evidence makes a claim unsupported
   (F1 0.69 → 0.99, `evals/results/verifier_eval.json`).
2. **SSE parser split on `\n\n`** but sse-starlette emits `\r\n\r\n`, so the live run viewer never showed progress. Caught by
   the Playwright tests, fixed in `apps/web/src/lib/api/client.ts`.
3. **Corrective-RAG grader threshold set to 0 by guess**; calibration on dev labels moved it to −7.1 (cross-encoder) and
   0.83 (cosine) — the guessed value would have discarded real evidence (`evals/results/grader_calibration*.json`).
4. **`.rstrip(" before")`** used to trim a suffix (it strips a character set and would turn "Docker" into "Dock"); caught in
   review and replaced with a regex.
5. **Requirement splitter broke "Next.js" at the dot**, giving 0/5 evidence on a strong-fit job in the first smoke test.
6. **An over-broad `taskkill` filter** was proposed to stop a test server; the command was blocked and replaced by killing
   the single PID listening on the test port.
7. **Verifier wiped screening answers to empty strings**, which made the critic reject every draft and burned both
   revisions (found in the first live-model run); fixed with rewrite-then-reverify and a non-empty fallback answer.
