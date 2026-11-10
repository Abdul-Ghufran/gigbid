"""Render both LangGraph graphs from code to Mermaid (docs/images/*.mmd).  PNGs are rendered locally by
apps/web/scripts/render_png.mjs with a locally installed Mermaid (nothing is uploaded to a third-party service)."""
import os
from pathlib import Path

os.environ.setdefault("LLM_OFFLINE", "1")
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.graphs.conversation_graph import build_conversation_graph  # noqa: E402

out = Path(__file__).resolve().parents[1] / "docs" / "images"
out.mkdir(parents=True, exist_ok=True)
for name, g in (("bid_graph", build_bid_graph()), ("conversation_graph", build_conversation_graph())):
    (out / f"{name}.mmd").write_text(g.get_graph().draw_mermaid(), encoding="utf-8")
    print(name, "mermaid written")
