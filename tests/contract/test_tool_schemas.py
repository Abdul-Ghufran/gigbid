"""Schema snapshot test: fails when an MCP tool's name, input/output schema or annotations change unintentionally.
Intentional change: `UPDATE_SNAPSHOTS=1 pytest tests/contract` and commit the new snapshot with the change."""
import json
import os
from pathlib import Path

import pytest

from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace

SNAP = Path(__file__).parent / "snapshots"


async def describe(server):
    tools = await server.list_tools()
    out = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                    "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None} for t in tools}
    out["_resource_templates"] = sorted(r.uriTemplate for r in await server.list_resource_templates())
    out["_prompts"] = sorted(p.name for p in await server.list_prompts())
    return out


@pytest.mark.parametrize("name,server", [("marketplace", marketplace), ("portfolio", portfolio), ("workspace", workspace)])
async def test_schema_snapshot(name, server):
    cur = await describe(server)
    f = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not f.exists():
        f.write_text(json.dumps(cur, indent=1, sort_keys=True), encoding="utf-8")
    want = json.loads(f.read_text(encoding="utf-8"))
    assert sorted(cur) == sorted(want), "tools added or removed"
    for tool in want:
        assert cur[tool] == want[tool], f"{name}.{tool} schema changed; update snapshots if intentional"


async def test_every_write_tool_requires_idempotency_and_is_not_readonly():
    for server in (marketplace, workspace):
        for t in await server.list_tools():
            if t.annotations and t.annotations.readOnlyHint is False:
                assert "idempotency_key" in t.inputSchema.get("required", []), t.name
