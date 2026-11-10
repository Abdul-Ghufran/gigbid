import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="gigbid-test-")
os.environ.setdefault("LLM_OFFLINE", "1")
os.environ.setdefault("GIGSIM_INPROCESS", "1")
os.environ.setdefault("MCP_TRANSPORT", "memory")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_STATE_PATH", os.path.join(_tmp, "gigsim.json"))
os.environ.setdefault("GIGBID_STATE_DIR", _tmp)
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(_tmp, "t.sqlite").replace("\\", "/"))
os.environ.setdefault("GIGSIM_RATE_LIMIT_PER_MIN", "100000")
