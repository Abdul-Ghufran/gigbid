"""Process-wide settings.  Secrets only ever come from environment variables (never from files in git)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "dev-only-insecure-key-change-me"
    database_url: str = ""  # empty -> local sqlite file (tests / laptop without docker)
    redis_url: str = ""
    public_web_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"

    marketplace_mode: str = "gigsim"  # gigsim | upwork_live
    gigsim_base_url: str = "http://localhost:8081"
    gigsim_admin_token: str = "gigsim-admin"
    upwork_mcp_url: str = "https://mcp.upwork.com/mcp"
    upwork_client_id: str = ""
    upwork_client_secret: str = ""

    mcp_transport: str = "stdio"  # stdio (spawn servers locally) | http (docker / deployed services)
    mcp_marketplace_url: str = "http://localhost:8091/mcp"
    mcp_portfolio_url: str = "http://localhost:8092/mcp"
    mcp_workspace_url: str = "http://localhost:8093/mcp"
    mcp_shared_secret: str = "dev-mcp-shared-secret"
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"
    github_token: str = ""

    model_profile: str = "open"
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    llm_offline: bool = False  # deterministic stub LLM for CI / tests without keys

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    reviewer_email: str = "reviewer@gigbid.app"
    reviewer_password: str = ""

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url.replace("postgres://", "postgresql+psycopg://").replace(
                "postgresql://", "postgresql+psycopg://")
        return f"sqlite:///{ROOT / 'data' / 'processed' / 'gigbid.sqlite'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
