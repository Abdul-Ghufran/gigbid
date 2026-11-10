"""Structured hand-offs between agents (C3).  Anything a later step decides on is one of these objects."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    summary: str = Field(default="", description="One neutral sentence: what the client wants.")
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list, description="Atomic requirements, one capability each.")
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="Needs implied but not stated.")
    client_industry: str | None = None


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1, description="0 = safe, 1 = certainly a scam / do not engage")
    scam: bool = False
    injection_detected: bool = False
    flags: list[str] = Field(default_factory=list)  # free_work, off_platform_contact, off_platform_payment, ...
    client_quality: float = Field(default=0.5, ge=0, le=1)
    client_summary: str = ""
    explanation: str = ""
    injected_text: list[str] = Field(default_factory=list, description="Quoted suspicious instructions (never followed).")


class EvidenceRef(BaseModel):
    item_id: str
    title: str
    type: str
    snippet: str
    score: float
    source: str = ""


class RequirementMatch(BaseModel):
    requirement: str
    supported: bool
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    retrieval_variant: str = ""

    @property
    def evidence_ids(self) -> list[str]:
        return list(dict.fromkeys(e.item_id for m in self.matrix for e in m.evidence))


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str]
    auto: bool = Field(default=False, description="True when the user's autonomy setting applied it without review.")


class PriceQuote(BaseModel):
    amount: float
    bid_type: Literal["fixed", "hourly"]
    currency: str = "USD"
    market_p25: float | None = None
    market_p50: float | None = None
    market_p75: float | None = None
    floor: float
    connects_cost: int | None = None
    connects_usd: float | None = None
    est_reply_probability: float
    expected_value_usd: float
    worth_connects: bool
    rationale: list[str]


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str = Field(description="Plain text. Cite evidence inline as [item-id] after each factual claim.")
    screening_answers: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    version: int = 1
    strategy: str = "default"


class ClaimCheck(BaseModel):
    claim: str
    location: str = "cover_letter"  # cover_letter | answer:N
    label: Literal["supported", "partly_supported", "unsupported", "no_claim"]
    evidence_ids: list[str] = Field(default_factory=list)
    best_evidence: str | None = None
    score: float = 0.0
    reason: str = ""


class VerificationReport(BaseModel):
    checks: list[ClaimCheck]
    unsupported_before: int
    claims_before: int
    unsupported_after: int
    removed: list[str] = Field(default_factory=list)
    rewritten: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    score: float = Field(ge=0, le=10)
    passed: bool
    issues: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list, description="Concrete revision instructions for the writer.")
    revision: int = 0


class ComplianceVerdict(BaseModel):
    status: Literal["pass", "fixed", "block"]
    reasons: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)
    policy_version: str = ""


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    cover_letter: str | None = None
    screening_answers: list[str] | None = None
    bid_amount: float | None = None
    reason: str | None = None
    user_id: str | None = None


class ClientIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "acceptance", "other"]
    confidence: float = Field(ge=0, le=1, default=0.7)
    injection_detected: bool = False
    summary: str = ""
    counter_offer: float | None = None


class ReplyDraft(BaseModel):
    text: str
    proposed_slots: list[dict] = Field(default_factory=list)
    counter_price: float | None = None
    rationale: str = ""
