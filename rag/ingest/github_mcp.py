"""Portfolio ingestion from GitHub through the official GitHub MCP server (third-party server, read-only).

  items = await ingest_github_user("octocat", persona="custom", max_repos=8)

Uses `MultiServerMCPClient` over Streamable HTTP with the user's token (GITHUB_TOKEN, read-only scopes).  For each
public repository it reads the README and up to `max_files` source files; README and code become separate items
(multi-vector friendly) with skills extracted from prose and from imports.  Repo text is untrusted data like any
other portfolio input.  No scraping: only the GitHub MCP tools are used.
"""
from __future__ import annotations

import json
import re

from rag.ingest.skills import extract_skills
from rag.types import Item

CODE_RE = re.compile(r"\.(py|ts|tsx|js|sql|ipynb)$")


def _text(out) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, list):
        return "\n".join(_text(x) for x in out)
    if isinstance(out, dict):
        return out.get("text") or out.get("content") or json.dumps(out)
    return str(out)


async def ingest_github_user(username: str, persona: str = "custom", max_repos: int = 8, max_files: int = 4, client=None) -> list[Item]:
    if client is None:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        from common.settings import get_settings

        s = get_settings()
        client = MultiServerMCPClient({"github": {"transport": "streamable_http", "url": s.github_mcp_url,
                                                  "headers": {"Authorization": f"Bearer {s.github_token}"}}})
    tools = {t.name: t for t in await client.get_tools()}
    search, get_file = tools["search_repositories"], tools["get_file_contents"]
    raw = await search.ainvoke({"query": f"user:{username} fork:false", "perPage": max_repos})
    try:
        repos = json.loads(_text(raw)).get("items", [])
    except (json.JSONDecodeError, AttributeError):
        repos = []
    items: list[Item] = []
    for r in repos[:max_repos]:
        name = r.get("name")
        owner = (r.get("owner") or {}).get("login", username)
        date = (r.get("pushed_at") or r.get("updated_at") or "")[:7] or None
        try:
            readme = _text(await get_file.ainvoke({"owner": owner, "repo": name, "path": "README.md"}))
        except Exception:
            readme = r.get("description") or ""
        items.append(Item(id=f"gh-{owner}-{name}-readme", persona=persona, type="readme", title=f"{name} README", text=readme,
                          project=name, date=date, source=f"github:{owner}/{name}", skills=extract_skills(readme)))
        try:
            listing = json.loads(_text(await get_file.ainvoke({"owner": owner, "repo": name, "path": ""})))
        except Exception:
            listing = []
        paths = [f["path"] for f in listing if isinstance(f, dict) and f.get("type") == "file" and CODE_RE.search(f.get("path", ""))][:max_files]
        code = []
        for p in paths:
            try:
                code.append(f"# file: {p}\n" + _text(await get_file.ainvoke({"owner": owner, "repo": name, "path": p}))[:6000])
            except Exception:
                continue
        if code:
            body = "\n\n".join(code)
            items.append(Item(id=f"gh-{owner}-{name}-code", persona=persona, type="code", title=f"{name} source code", text=body,
                              project=name, date=date, source=f"github:{owner}/{name}", skills=extract_skills(body, code=True)))
    return items
