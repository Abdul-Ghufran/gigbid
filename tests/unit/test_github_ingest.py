"""GitHub MCP ingestion against a fake MCP client (same tool names as the official GitHub MCP server)."""
import json

from rag.ingest.github_mcp import ingest_github_user


class FakeTool:
    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    async def ainvoke(self, args):
        return self.fn(args)


class FakeClient:
    async def get_tools(self):
        def search(a):
            return json.dumps({"items": [{"name": "queue-svc", "owner": {"login": "dev"}, "pushed_at": "2025-04-01"}]})

        def get_file(a):
            if a["path"] == "README.md":
                return "# queue-svc\nBackground jobs for an online store."
            if a["path"] == "":
                return json.dumps([{"type": "file", "path": "worker.py"}, {"type": "file", "path": "logo.png"}])
            return "from celery import Celery\napp = Celery('q')\n"

        return [FakeTool("search_repositories", search), FakeTool("get_file_contents", get_file)]


async def test_ingests_readme_and_code_with_implied_skills():
    items = await ingest_github_user("dev", client=FakeClient())
    kinds = {i.type for i in items}
    assert kinds == {"readme", "code"}
    code = next(i for i in items if i.type == "code")
    assert "Celery" in code.skills and "logo.png" not in code.text
    assert all(i.source == "github:dev/queue-svc" for i in items)
