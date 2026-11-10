"""Load agent/config.yaml (+ env overrides) and the versioned prompt files."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent


@lru_cache
def config() -> dict:
    cfg = yaml.safe_load((AGENT_DIR / "config.yaml").read_text(encoding="utf-8"))
    if os.getenv("MARKETPLACE_MODE"):
        cfg["marketplace"]["mode"] = os.environ["MARKETPLACE_MODE"]
    if os.getenv("RAG_VARIANT"):
        cfg["rag"]["shipped_variant"] = os.environ["RAG_VARIANT"]
    return cfg


def profile_name() -> str:
    return os.getenv("MODEL_PROFILE", "open")


def model_for(node: str, profile: str | None = None) -> dict:
    cfg = config()
    prof = cfg["profiles"][profile or profile_name()]
    alias = prof.get(node) or prof["fallback_small"]
    return {"alias": alias, **cfg["models"][alias]}


@lru_cache
def prompt(node: str) -> dict:
    """agent/prompts/<node>.md -> {version, system, user}.  Sections are '## system' and '## user'."""
    text = (AGENT_DIR / "prompts" / f"{node}.md").read_text(encoding="utf-8")
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    parts = re.split(r"^## (system|user)\s*$", text, flags=re.M)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return {"node": node, "version": version.group(1) if version else "0", **sections}


def render(template: str, **kw) -> str:
    def sub(m):
        v = kw.get(m.group(1), "")
        return v if isinstance(v, str) else yaml.safe_dump(v, sort_keys=False, allow_unicode=True).strip()

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, template)


def policy_pack() -> str:
    return (ROOT / config()["platform_policy"]["policy_pack"]).read_text(encoding="utf-8")
