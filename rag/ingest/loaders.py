"""Loaders: PDF CVs, Markdown case studies, repo READMEs + code, reviews, past proposals, UI uploads.

Every item gets metadata: persona, type, project, skills, date, client industry and (proposals) outcome.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from rag.ingest.skills import extract_skills
from rag.types import Item

ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = ROOT / "data" / "personas"
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".yml", ".yaml"}


def _rel(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).as_posix()


def _frontmatter(md: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md.replace("\r\n", "\n"), re.S)
    if not m:
        return {}, md
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def load_cv(path: Path, persona: str) -> Item:
    from pypdf import PdfReader

    text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return Item(id=f"{persona}-cv", persona=persona, type="cv", title="Curriculum vitae", text=text,
                source=_rel(path), skills=extract_skills(text))


def load_case_studies(d: Path, persona: str) -> list[Item]:
    items = []
    for p in sorted(d.glob("*.md")):
        meta, body = _frontmatter(p.read_text(encoding="utf-8"))
        title = next((ln[2:] for ln in body.splitlines() if ln.startswith("# ")), p.stem)
        items.append(Item(id=meta.get("id", f"{persona}-case-{p.stem}"), persona=persona, type="case_study", title=title,
                          text=body.strip(), project=meta.get("project"), date=meta.get("date"),
                          client_industry=meta.get("client_industry"), source=_rel(p),
                          skills=extract_skills(body)))
    return items


def load_repo(repo_dir: Path, persona: str, idx_by_repo: dict[str, str]) -> list[Item]:
    """README + code files of one repository (local checkout or files fetched via the GitHub MCP server)."""
    repo = repo_dir.name
    num = idx_by_repo.get(repo, repo)
    items = []
    readme = repo_dir / "README.md"
    if readme.exists():
        t = readme.read_text(encoding="utf-8")
        items.append(Item(id=f"{persona}-repo-{num}", persona=persona, type="readme", title=f"{repo} README", text=t,
                          project=repo, source=_rel(readme), skills=extract_skills(t)))
    code_files = [p for p in sorted(repo_dir.rglob("*")) if p.suffix in CODE_EXT and p.is_file()]
    if code_files:
        text = "\n\n".join(f"# file: {p.relative_to(repo_dir).as_posix()}\n{p.read_text(encoding='utf-8')}" for p in code_files)
        items.append(Item(id=f"{persona}-code-{num}", persona=persona, type="code", title=f"{repo} source code", text=text,
                          project=repo, source=_rel(repo_dir), skills=extract_skills(text, code=True)))
    return items


def load_jsonl(path: Path, persona: str, typ: str) -> list[Item]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            title = r.get("job_title") or f"Client review ({r.get('rating', '')}★)"
            items.append(Item(id=r["id"], persona=persona, type=typ, title=title, text=r["text"], project=r.get("project"),
                              date=r.get("date"), client_industry=r.get("client_industry"), outcome=r.get("outcome"),
                              source=_rel(path), skills=extract_skills(r["text"]),
                              meta={k: v for k, v in r.items() if k in ("rating", "bid_amount")}))
    return items


def load_persona(persona: str) -> list[Item]:
    return load_dir(PERSONA_DIR / persona, persona)


def load_dir(d: Path, persona: str) -> list[Item]:
    """Load any folder laid out like data/personas/<p>/ (cv.pdf, case_studies/, repos/, *.jsonl)."""
    d = Path(d)
    items: list[Item] = []
    if (d / "cv.pdf").exists():
        items.append(load_cv(d / "cv.pdf", persona))
    cases = load_case_studies(d / "case_studies", persona)
    items += cases
    idx_by_repo = {c.project: c.id.rsplit("-", 1)[-1] for c in cases if c.project}
    for repo_dir in sorted((d / "repos").iterdir()) if (d / "repos").exists() else []:
        items += load_repo(repo_dir, persona, idx_by_repo)
    if (d / "reviews.jsonl").exists():
        items += load_jsonl(d / "reviews.jsonl", persona, "review")
    if (d / "proposals.jsonl").exists():
        items += load_jsonl(d / "proposals.jsonl", persona, "past_proposal")
    return items


def load_uploads(user_id: str, persona: str) -> list[Item]:
    """Work the user added in the UI (incremental re-indexing picks these up)."""
    try:
        from common.db import PortfolioUpload, session

        with session() as s:
            rows = s.query(PortfolioUpload).filter_by(user_id=user_id, deleted=False).all()
            return [Item(id=f"upload-{r.id}", persona=persona, type=r.kind if r.kind != "repo" else "readme", title=r.title,
                         text=r.content, project=r.meta.get("project"), date=r.meta.get("date"),
                         client_industry=r.meta.get("client_industry"), outcome=r.meta.get("outcome"),
                         source="upload", skills=extract_skills(r.content, code=r.kind == "repo"), meta={"upload": True})
                    for r in rows]
    except Exception:
        return []
