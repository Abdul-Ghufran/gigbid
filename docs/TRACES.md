# Public traces

Every GigBid run is traced end to end under one trace id (UI request → API → graph → MCP servers → audit log). In the
deployed app each run is viewable in **Runs → run → Execution trace** (node timings, tool calls with arguments and
results, tokens and cost per node, MCP audit rows). When Langfuse keys are configured the same trace id is sent to
Langfuse with one generation per LLM call (tokens + list-price cost per node).

| Trace | What it shows | Link |
|---|---|---|
| Skipped scam | parallel analysis; Risk Assessor flags free work + off-platform contact; decide → skip; no writer call | _add Langfuse public link_ |
| Approved proposal | writer → verifier → critic → compliance → interrupt → resume → submit (exactly once) | _add Langfuse public link_ |
| Critic loop | critic sends the draft back (revision 2) before compliance | _add Langfuse public link_ |
| Crash and resume | run continued from its checkpoint after a restart; submit replayed idempotently | _add Langfuse public link_ |

How to publish one (Langfuse UI): open the trace → **Share** → toggle **Public** → copy the URL into the table above.
