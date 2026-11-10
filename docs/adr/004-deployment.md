# ADR-004: Single container on Render free tier

**Decision.** Production runs API + in-process worker + MCP servers over the in-memory MCP transport + GigSim in one 512 MB container; Neon Postgres for checkpoints, store, app data and GigSim state.

**Why.** Separate worker/MCP processes each need ~250 MB of Python + models. Docker compose keeps the full multi-service layout (Arq worker on Redis, MCP over HTTP with bearer auth) for local runs and the viva.

**Cost.** No separate worker scaling; cold starts after Render sleeps.
