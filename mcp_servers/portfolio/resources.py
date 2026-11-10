"""Resource templates so a host (Claude Desktop, Cursor, GigBid) can load full portfolio items."""
import json

from mcp_servers.portfolio.tools import corpus


def register(mcp):
    @mcp.resource("portfolio://case/{id}", name="case_study", mime_type="text/markdown",
                  description="Full Markdown of a case study")
    def case(id: str) -> str:
        it = corpus().by_id[id]
        return f"# {it.title}\n\n{it.text}"

    @mcp.resource("portfolio://proposal/{id}", name="past_proposal", mime_type="application/json",
                  description="A past proposal with its outcome (won / replied / ignored)")
    def proposal(id: str) -> str:
        it = corpus().by_id[id]
        return json.dumps({**it.card(), "text": it.text, "bid_amount": it.meta.get("bid_amount")}, indent=1)

    @mcp.resource("portfolio://item/{id}", name="evidence_item", mime_type="text/plain",
                  description="Any evidence item (README, code, review, CV, upload) in full")
    def item(id: str) -> str:
        it = corpus().by_id[id]
        return f"[{it.type}] {it.title}\nsource: {it.source}\n\n{it.text}"

    @mcp.resource("portfolio://profile", name="profile", mime_type="application/json",
                  description="Index of every item in the portfolio")
    def profile() -> str:
        c = corpus()
        return json.dumps({"persona": c.persona, "items": [i.card() for i in c.items if i.type != "past_proposal"],
                           "past_proposals": len(c.proposals)}, indent=1)
