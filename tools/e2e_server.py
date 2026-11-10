"""Start an isolated GigBid API for Playwright: fresh SQLite DB + checkpoints, in-process GigSim, offline LLM
fallbacks (deterministic, no API quota).  `--degraded` points the marketplace at a dead GigSim to test the banner."""
import os
import sys
import tempfile
from pathlib import Path

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
degraded = "--degraded" in sys.argv
tmp = Path(tempfile.mkdtemp(prefix="gigbid-e2e-"))
os.environ.update(
    LLM_OFFLINE="1", MCP_TRANSPORT="memory", GIGSIM_ERROR_RATE="0", REDIS_URL="", LANGFUSE_PUBLIC_KEY="",
    DATABASE_URL="sqlite:///" + str(tmp / "e2e.sqlite").replace("\\", "/"), GIGSIM_STATE_PATH=str(tmp / "gigsim.json"),
    REVIEWER_PASSWORD="", INPROCESS_SCHEDULER="0", GIGBID_STATE_DIR=str(tmp),
)
if degraded:
    os.environ.update(GIGSIM_INPROCESS="0", GIGSIM_BASE_URL="http://127.0.0.1:9")
else:
    os.environ["GIGSIM_INPROCESS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn  # noqa: E402

uvicorn.run("apps.api.main:app", host="127.0.0.1", port=port, log_level="warning")
