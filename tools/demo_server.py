"""Demo / recording server: fresh DB, in-process GigSim + MCP, reviewer account seeded with demo searches.
  python tools/demo_server.py 8030 [--live]     (--live uses the configured Groq models instead of offline fallbacks)"""
import os
import sys
import tempfile
from pathlib import Path

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8030
tmp = Path(tempfile.mkdtemp(prefix="gigbid-demo-"))
os.environ.update(MCP_TRANSPORT="memory", GIGSIM_INPROCESS="1", GIGSIM_ERROR_RATE="0", REDIS_URL="", INPROCESS_SCHEDULER="0",
                  DATABASE_URL="sqlite:///" + str(tmp / "demo.sqlite").replace("\\", "/"), GIGSIM_STATE_PATH=str(tmp / "gigsim.json"),
                  GIGBID_STATE_DIR=str(tmp), REVIEWER_EMAIL="reviewer@gigbid.app", REVIEWER_PASSWORD="demo-reviewer-pass",
                  GIGSIM_POLICY_VERSION="2026-11-02")
if "--live" not in sys.argv:
    os.environ["LLM_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn  # noqa: E402

uvicorn.run("apps.api.main:app", host="127.0.0.1", port=port, log_level="warning")
