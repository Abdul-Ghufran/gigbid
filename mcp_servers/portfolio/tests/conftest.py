import os
import tempfile

os.environ.setdefault("GIGSIM_INPROCESS", "1")
os.environ.setdefault("GIGSIM_TOKEN", "gigsim-dev-token-ai")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_STATE_PATH", os.path.join(tempfile.mkdtemp(), "state.json"))
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.sqlite").replace("\\", "/"))
os.environ.setdefault("PORTFOLIO_PERSONA", "web")
