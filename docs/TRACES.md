# Public traces

Every GigBid run is traced end to end under one trace id (UI request → API → graph → MCP servers → audit log).
In the deployed app each run is viewable in **Runs → run → Execution trace**. The same run is exported to
Langfuse over OpenTelemetry (OTLP/HTTP): one trace per run with the graph nodes (agent), MCP tool calls (tool) and
one generation per LLM call (model, tokens, list-price cost), PII-masked before export. These were recorded
with `tools/publish_traces.py` on 2026-11-15 (live models, in-process GigSim) and are public (three distinct traces; in the approved run the live critic itself sent the first draft back, so it also
covers the critic loop):

| Trace | What it shows | Observations | Result | Link |
|---|---|---|---|---|
| Skipped scam | parallel analysis (analyst, risk_assessor, fit_matcher); Risk Assessor flags the scam; decide -> skip; no writer call (job: Need CI/CD expert, equipment provided) | 11 | `{"decision": "skip", "scam": true, "drafted": false}` | [open trace](https://cloud.langfuse.com/project/cmwgkffbc00scad0kkimpd1tb/traces/7254e787a2044d1d98f9a0856a95be96) |
| Approved proposal + critic loop | writer -> verifier -> critic (score 6.0, fail) -> writer revision 2 -> verifier -> critic (9.0, pass) -> compliance -> approval interrupt -> resume (approve) -> submit (job: Senior Next.js engineer for insurance product) | 46 | `{"status": "submitted", "revisions": 2, "critic_rounds": 2, "critic_scores": [6.0, 9.0], "compliance": "pass", "connects_spent": 16}` | [open trace](https://cloud.langfuse.com/project/cmwgkffbc00scad0kkimpd1tb/traces/9b37d625d5aa49d2b3dd02244c8bf0c4) |
| Crash and resume | paused at approval, process restarted with a new checkpointer, resumed from the checkpoint; the replayed submit is idempotent (Connects spent once) (job: MongoDB developer for nonprofit platform) | 65 | `{"pending_after_restart": ["approval"], "status": "submitted", "connects_spent": 9, "balance_before": 64, "balance_after": 55, "spent_exactly_once": true}` | [open trace](https://cloud.langfuse.com/project/cmwgkffbc00scad0kkimpd1tb/traces/b7cce73e4d8549d881ff53c7f3208a17) |

Runs in the deployed app are traced the same way (trace name `bid_graph` / `conv_graph`, session = the job's
thread), and marked public, so any run's link from **Runs → Open full trace in Langfuse** can be shared.
Public links open without a Langfuse login and show the full observation tree (graph nodes, MCP tool calls, LLM
generations), timings, models, tokens and cost. Langfuse's anonymous viewer does not load per-observation input/output
bodies (they are stored - signed-in project members see them, and the in-app Run viewer shows the same data).
