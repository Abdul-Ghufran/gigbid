# ADR-001: One marketplace port, adapters behind the Marketplace MCP server

**Decision.** Agents only see GigBid's Marketplace MCP tools. The server selects `GigSimAdapter` or `UpworkLiveAdapter` (config / connected account); the Upwork adapter is itself an MCP client of Upwork's official server.

**Why.** The graph cannot tell which marketplace it is using (R1, A4); platform rules (drafts only, 3 h polling floor) live in one adapter instead of in prompts.

**Cost.** One extra hop in live mode; tool names on Upwork are mapped in `upwork_tool_map.yaml` and verified at connect time.
