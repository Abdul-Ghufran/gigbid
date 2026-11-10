from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Item:
    """One portfolio evidence item (a case study, README, code file, review, past proposal or CV)."""
    id: str
    persona: str
    type: str  # case_study | readme | code | review | past_proposal | cv | upload
    title: str
    text: str
    project: str | None = None
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None  # won | replied | ignored (past proposals only)
    source: str = ""
    skills: list[str] = field(default_factory=list)  # extracted by the normaliser at ingest time
    meta: dict[str, Any] = field(default_factory=dict)

    def card(self) -> dict:
        return {"id": self.id, "type": self.type, "title": self.title, "project": self.project, "date": self.date,
                "client_industry": self.client_industry, "outcome": self.outcome, "source": self.source,
                "skills": self.skills}


@dataclass
class Chunk:
    id: str
    item_id: str
    text: str  # text that is embedded / indexed (may carry a prepended context line)
    raw: str  # original chunk text shown to writers
    kind: str = "body"  # body | summary | readme | code (multi-vector)


@dataclass
class Hit:
    item_id: str
    score: float
    chunk_id: str | None = None
    snippet: str = ""
    requirement: str | None = None
    signals: dict[str, float] = field(default_factory=dict)
