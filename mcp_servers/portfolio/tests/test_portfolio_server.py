"""Portfolio MCP server through an in-memory MCP client."""
import json

from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.portfolio.server import mcp


def data(res):
    assert not res.isError, res.content
    return res.structuredContent if res.structuredContent is not None else json.loads(res.content[0].text)


async def test_listing_tools_resources_prompts():
    async with connect(mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        templates = {t.uriTemplate for t in (await c.list_resource_templates()).resourceTemplates}
        prompts = {p.name for p in (await c.list_prompts()).prompts}
    assert {"search_evidence", "get_case_study", "list_skills"} <= set(tools)
    assert all(t.annotations.readOnlyHint for t in tools.values())
    assert {"portfolio://case/{id}", "portfolio://proposal/{id}"} <= templates
    assert "answer_screening_question" in prompts


async def test_search_evidence_finds_exact_library():
    async with connect(mcp._mcp_server) as c:
        r = data(await c.call_tool("search_evidence", {"requirement": "background task processing with Celery", "k": 5}))
    assert r["items"], r
    for it in r["items"]:
        assert {"type", "source", "date", "outcome"} <= set(it)
    assert any("Celery" in it["skills"] for it in r["items"])


async def test_unrelated_requirement_not_supported():
    async with connect(mcp._mcp_server) as c:
        r = data(await c.call_tool("search_evidence", {"requirement": "FPGA firmware in VHDL for satellite radios", "k": 3}))
    assert r["supported"] is False


async def test_case_study_and_resources():
    async with connect(mcp._mcp_server) as c:
        cs = data(await c.call_tool("get_case_study", {"id": "web-case-02"}))
        assert cs["project"] == "clinic-book" and cs["related_items"]
        res = await c.read_resource("portfolio://case/web-case-02")
        assert "clinic" in res.contents[0].text.lower()
        p = await c.read_resource("portfolio://proposal/web-prop-001")
        assert json.loads(p.contents[0].text)["outcome"] in ("won", "replied", "ignored")
        pr = await c.get_prompt("answer_screening_question", {"question": "How do you test?"})
        assert "search_evidence" in pr.messages[0].content.text


async def test_list_skills():
    async with connect(mcp._mcp_server) as c:
        s = data(await c.call_tool("list_skills", {}))
    names = {x["skill"] for x in s["skills"]}
    assert {"React", "Django"} <= names
