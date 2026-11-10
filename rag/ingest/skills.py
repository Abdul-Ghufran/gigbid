"""Skill normaliser: canonical skill names from free text and code (synonyms + code signals)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache
def taxonomy() -> dict:
    return yaml.safe_load((Path(__file__).parent / "skills.yaml").read_text(encoding="utf-8"))


def _term_re(term: str) -> re.Pattern:
    t = re.escape(term.lower())
    return re.compile(rf"(?<![a-z0-9]){t}(?![a-z0-9])")


@lru_cache
def _patterns() -> list[tuple[str, list[re.Pattern], list[str]]]:
    out = []
    for skill, v in taxonomy().items():
        terms = [skill] + list(v.get("synonyms", []))
        out.append((skill, [_term_re(t) for t in terms if len(t) > 1], [c.lower() for c in v.get("code_signals", [])]))
    return out


DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", " ": " "})


def normalise(text: str) -> str:
    """LLMs emit non-breaking hyphens / spaces ("scikit‑learn"); map them to ASCII before matching."""
    return text.translate(DASHES)


def extract_skills(text: str, code: bool = False) -> list[str]:
    low = normalise(text).lower()
    found = []
    for skill, pats, signals in _patterns():
        if any(p.search(low) for p in pats) or (code and any(s and s in low for s in signals)):
            found.append(skill)
    return sorted(set(found))


def expand(skill: str) -> list[str]:
    """Canonical name plus known synonyms (used for query expansion)."""
    v = taxonomy().get(skill, {})
    return [skill, *v.get("synonyms", [])]


def canonical(name: str) -> str | None:
    low = name.lower().strip()
    for skill, v in taxonomy().items():
        if low == skill.lower() or low in [s.lower() for s in v.get("synonyms", [])]:
            return skill
    return None
