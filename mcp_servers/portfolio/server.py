"""GigBid Portfolio MCP server (read-only).

Standalone, for any freelancer (Claude Desktop / Cursor):
    uvx --from git+https://github.com/Abdul-Ghufran/gigbid gigbid-portfolio-mcp --portfolio-dir /path/to/my_portfolio
Inside GigBid (per-user, HTTP + bearer auth):
    MCP_HTTP=1 python -m mcp_servers.portfolio.server --transport http --port 8092
"""
import argparse
import os

from mcp.server.fastmcp import FastMCP

from common.settings import get_settings
from mcp_servers._shared import http_auth_kwargs
from mcp_servers.portfolio import prompts, resources, tools

mcp = FastMCP(
    "gigbid-portfolio",
    instructions=("Read-only access to a freelancer's portfolio: case studies, repositories and code, client reviews, "
                  "CV and past proposals with outcomes. Use search_evidence to prove one requirement at a time and "
                  "never claim experience when supported=false."),
    **http_auth_kwargs(get_settings().mcp_portfolio_url, ["portfolio:read"]),
)
tools.register(mcp)
resources.register(mcp)
prompts.register(mcp)


def main():
    ap = argparse.ArgumentParser(description="GigBid Portfolio MCP server")
    ap.add_argument("--portfolio-dir", help="Folder with cv.pdf, case_studies/, repos/, reviews.jsonl, proposals.jsonl")
    ap.add_argument("--persona", help="Built-in demo persona: ai | web | data (when running from a repo checkout)")
    ap.add_argument("--transport", default=os.getenv("MCP_TRANSPORT_MODE", "stdio"), choices=["stdio", "http"])
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", 8092)))
    a = ap.parse_args()
    if a.portfolio_dir:
        os.environ["PORTFOLIO_DIR"] = os.path.abspath(a.portfolio_dir)
        # installed via uvx/pip: keep model + embedding caches in the user's cache dir, not site-packages
        os.environ.setdefault("GIGBID_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".cache", "gigbid"))
    if a.persona:
        os.environ["PORTFOLIO_PERSONA"] = a.persona
    os.environ.setdefault("AUDIT_DISABLED", "1" if a.portfolio_dir else os.getenv("AUDIT_DISABLED", "0"))
    if a.transport == "http":
        import uvicorn

        from common.db import init_db

        init_db()
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=a.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
