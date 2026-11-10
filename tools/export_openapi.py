"""Write the FastAPI OpenAPI schema to apps/web/openapi.json (input for the generated TypeScript client)."""
import json
import os
from pathlib import Path

os.environ.setdefault("LLM_OFFLINE", "1")
from apps.api.main import app  # noqa: E402

out = Path(__file__).resolve().parents[1] / "apps" / "web" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")
print(f"wrote {out} ({len(app.openapi()['paths'])} paths)")
