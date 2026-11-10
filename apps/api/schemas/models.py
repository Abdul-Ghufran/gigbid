"""Request / response models (the OpenAPI schema generated from these feeds the TypeScript client)."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

EmailStr = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    persona_key: str | None
    onboarded: bool


class AuthOut(BaseModel):
    token: str
    user: UserOut


class SavedSearch(BaseModel):
    id: str = ""
    name: str = ""
    query: str = ""
    category: Literal["ai", "web", "data"] | None = None
    skills: list[str] = Field(default_factory=list)
    min_budget: float = 0
    interval_minutes: int = Field(default=20, ge=5, le=1440)
    limit: int = Field(default=10, ge=1, le=30)
    last_run: str | None = None


class OnboardingIn(BaseModel):
    persona_key: Literal["ai", "web", "data"] | None = Field(None, description="Demo persona, or null for your own profile")
    marketplace: Literal["gigsim", "upwork"] = "gigsim"
    hourly_rate: float = Field(40, gt=0, le=1000)
    min_project: float = Field(300, ge=0, le=100000)
    weekly_connects_budget: int = Field(60, ge=0, le=1000)
    saved_searches: list[SavedSearch] = Field(default_factory=list)


class SettingsOut(BaseModel):
    hourly_rate: float
    min_project: float
    weekly_connects_budget: int
    autonomy: Literal["suggest", "auto_skip_low_fit"]
    saved_searches: list[SavedSearch]
    connected_accounts: list[dict[str, Any]]
    model_profile: str
    marketplace_mode: str


class SettingsIn(BaseModel):
    hourly_rate: float | None = Field(None, gt=0, le=1000)
    min_project: float | None = Field(None, ge=0)
    weekly_connects_budget: int | None = Field(None, ge=0, le=1000)
    autonomy: Literal["suggest", "auto_skip_low_fit"] | None = None
    saved_searches: list[SavedSearch] | None = None


class JobCard(BaseModel):
    job_id: str
    title: str
    category: str | None
    budget: dict[str, Any]
    connects_cost: int | None
    status: str
    pipeline_stage: str | None
    fit: float | None = None
    risk: float | None = None
    scam: bool | None = None
    flags: list[str] = Field(default_factory=list)
    decision: str | None = None
    price: float | None = None
    duplicate_of: str | None = None
    attention: list[str] = Field(default_factory=list)
    updated_at: str


class JobDetail(BaseModel):
    card: JobCard
    job: dict[str, Any]
    analyses: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    price: dict[str, Any] = Field(default_factory=dict)
    draft: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    critiques: list[dict[str, Any]] = Field(default_factory=list)
    compliance: dict[str, Any] | None = None
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    submission: dict[str, Any] | None = None
    pending_approval: dict[str, Any] | None = None
    runs: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    cover_letter: str | None = Field(None, max_length=5000)
    screening_answers: list[str] | None = None
    bid_amount: float | None = Field(None, gt=0)
    reason: str | None = Field(None, max_length=500)


class RunRef(BaseModel):
    run_id: str
    trace_id: str | None = None


class RegenerateIn(BaseModel):
    paragraph_index: int = Field(ge=0, le=20)
    instruction: str = Field("", max_length=300)


class RegenerateOut(BaseModel):
    paragraph: str
    cover_letter: str


class ConversationCard(BaseModel):
    thread_id: str
    job_id: str
    job_title: str
    status: str
    intent: str | None
    last_message: str | None
    updated_at: str


class SystemStatus(BaseModel):
    api: str
    marketplace: Literal["up", "down"]
    marketplace_mode: str
    marketplace_error: str | None = None
    policy_version: str | None = None
    model_profile: str
    llm_offline: bool
    tracing: bool
    worker: str


class MemoryOut(BaseModel):
    style: list[dict[str, Any]]
    outcome: list[dict[str, Any]]
    recent_edits: list[dict[str, Any]]


class PortfolioItemIn(BaseModel):
    kind: Literal["case_study", "repo", "review", "proposal", "cv"]
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=20, max_length=50000)
    project: str | None = None
    date: str | None = None
    client_industry: str | None = None
    outcome: Literal["won", "replied", "ignored"] | None = None


class PortfolioItemOut(BaseModel):
    id: str
    type: str
    title: str
    source: str
    skills: list[str]
    date: str | None = None
    project: str | None = None
    outcome: str | None = None
    uploaded: bool = False
