"""Portfolio tools: search_evidence, get_case_study, list_skills (+ have_i_done for skill-graph questions)."""
import os
from collections import Counter
from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers._shared import audited, current_user_id

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class Evidence(BaseModel):
    id: str = Field(description="Evidence item id; load the full item with resource portfolio://item/{id}")
    type: str = Field(description="case_study | readme | code | review | cv | upload")
    title: str
    source: str
    date: str | None = None
    outcome: str | None = Field(default=None, description="won | replied | ignored (past proposals only)")
    project: str | None = None
    client_industry: str | None = None
    skills: list[str] = Field(default_factory=list)
    score: float
    snippet: str = Field(description="Most relevant passage")


class EvidenceResult(BaseModel):
    requirement: str
    variant: str
    items: list[Evidence]
    supported: bool = Field(description="False when no evidence passed the grader: do not claim this requirement.")


class CaseStudy(BaseModel):
    id: str
    title: str
    project: str | None
    date: str | None
    client_industry: str | None
    text: str
    related_items: list[str] = Field(default_factory=list, description="README / code / review ids for the same project")


class SkillCount(BaseModel):
    skill: str
    items: int
    projects: int


class SkillList(BaseModel):
    persona: str
    skills: list[SkillCount]


class ProjectsAnswer(BaseModel):
    skill: str
    industry: str | None
    projects: list[str]
    answer: str


def corpus():
    """Corpus for the caller: PORTFOLIO_DIR (standalone), the persona env, or the GigBid user's persona + uploads."""
    from rag.corpus import get_corpus, get_corpus_for_dir

    if os.getenv("PORTFOLIO_DIR"):
        return get_corpus_for_dir(os.environ["PORTFOLIO_DIR"])
    uid = current_user_id()
    persona = os.getenv("PORTFOLIO_PERSONA", "")
    if uid.startswith("persona-"):
        persona = uid.split("-")[1]
    elif uid != "local":
        try:
            from common.db import User, session

            with session() as s:
                u = s.get(User, uid)
                persona = (u.persona_key if u else None) or persona
        except Exception:
            pass
    return get_corpus(persona or "ai", None if uid == "local" else uid)


def register(mcp):
    @mcp.tool(annotations=READ, title="Search portfolio evidence")
    @audited("portfolio", log_reads=True)
    async def search_evidence(
        requirement: Annotated[str, Field(min_length=2, max_length=500, description="One job requirement, e.g. 'background jobs with Celery'")],
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        filters: Annotated[dict | None, Field(description="Optional: {types: [case_study, readme, code, review, cv], since: 'YYYY-MM', industry: str}")] = None,
        trace_id: Annotated[str, Field(max_length=64)] = "",
    ) -> EvidenceResult:
        """Find portfolio evidence (case studies, repos, code, reviews, CV) that proves one requirement.
        Uses GigBid's shipped retrieval pipeline (chosen by evaluation). If `supported` is false, do not claim it."""
        from agent.config import config
        from rag.retriever import VARIANTS

        c = corpus()
        name = config()["rag"]["shipped_variant"]
        opts = config()["rag"]["corrective"] if name == "v8_corrective" else {}
        v = VARIANTS[name](c, **opts)
        res = await v.retrieve({"title": "", "description": requirement}, k=k, requirements=[requirement], filters=filters)
        hits = res.by_requirement.get(requirement) or res.hits
        items = []
        for h in hits[:k]:
            it = c.by_id[h.item_id]
            items.append(Evidence(**{**it.card(), "score": round(h.score, 4), "snippet": h.snippet or it.text[:300]}))
        return EvidenceResult(requirement=requirement, variant=name, items=items,
                              supported=requirement not in res.unsupported and bool(items))

    @mcp.tool(annotations=READ, title="Get case study")
    @audited("portfolio")
    async def get_case_study(id: Annotated[str, Field(min_length=1, max_length=80)], trace_id: str = "") -> CaseStudy:
        """Full text of one case study plus the ids of the same project's README, code and reviews."""
        c = corpus()
        it = c.by_id.get(id)
        if not it or it.type not in ("case_study", "upload"):
            raise ToolError(f"not_found: no case study {id}")
        related = [x.id for x in c.items if x.project and x.project == it.project and x.id != id]
        return CaseStudy(id=it.id, title=it.title, project=it.project, date=it.date, client_industry=it.client_industry,
                         text=it.text, related_items=related)

    @mcp.tool(annotations=READ, title="List skills")
    @audited("portfolio")
    async def list_skills(trace_id: str = "") -> SkillList:
        """Every skill the portfolio demonstrates, with how many items and projects prove it."""
        c = corpus()
        items, projects = Counter(), {}
        for it in c.evidence:
            for sk in it.skills:
                items[sk] += 1
                if it.project:
                    projects.setdefault(sk, set()).add(it.project)
        return SkillList(persona=c.persona, skills=[SkillCount(skill=s, items=n, projects=len(projects.get(s, ())))
                                                    for s, n in items.most_common()])

    @mcp.tool(annotations=READ, title="Have I done X (for an industry)?")
    @audited("portfolio")
    async def have_i_done(skill: Annotated[str, Field(min_length=1, max_length=80)],
                          industry: Annotated[str | None, Field(max_length=60)] = None, trace_id: str = "") -> ProjectsAnswer:
        """Skill-graph lookup: projects that used a skill, optionally for a client in a given industry."""
        from rag.ingest.skills import canonical
        from rag.variants.v9_skill_graph import V9SkillGraph

        g = V9SkillGraph(corpus())
        sk = canonical(skill) or skill
        projs = g.have_i_done(sk, industry)
        ans = (f"Yes: {', '.join(projs)}." if projs else "No matching project in the portfolio.")
        return ProjectsAnswer(skill=sk, industry=industry, projects=projs, answer=ans)
