"""The single marketplace interface (R1).  Both adapters implement it; config picks one."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MarketplaceError(Exception):
    code = "marketplace_error"


class MarketplaceUnavailable(MarketplaceError):
    code = "marketplace_unavailable"


class RateLimited(MarketplaceError):
    code = "rate_limited"


class NotFound(MarketplaceError):
    code = "not_found"


class PolicyRejected(MarketplaceError):
    code = "policy_rejected"


class InsufficientConnects(MarketplaceError):
    code = "insufficient_connects"


class MarketplaceAdapter(ABC):
    """All methods take normalised arguments and return normalised dicts (see schemas.py)."""

    name: str

    # reads
    @abstractmethod
    async def search_jobs(self, query: str, category: str | None, skills: list[str], min_budget: float,
                          posted_within_minutes: float | None, limit: int) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_connects_balance(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_market_stats(self, category: str, skills: list[str]) -> dict[str, Any]: ...

    @abstractmethod
    async def list_threads(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_thread(self, thread_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def list_proposals(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def list_events(self, since_id: int) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_policy(self) -> dict[str, Any]: ...

    # writes (always called with an idempotency key; dry_run returns a preview without side effects)
    @abstractmethod
    async def create_proposal_draft(self, job_id: str, cover_letter: str, screening_answers: list[str],
                                    bid_amount: float, bid_type: str, idempotency_key: str) -> dict[str, Any]: ...

    @abstractmethod
    async def submit_proposal(self, proposal_id: str, idempotency_key: str, dry_run: bool) -> dict[str, Any]: ...

    @abstractmethod
    async def send_message(self, thread_id: str, text: str, idempotency_key: str, dry_run: bool) -> dict[str, Any]: ...

    async def aclose(self):  # pragma: no cover
        return None
