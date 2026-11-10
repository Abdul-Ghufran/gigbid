"""V9 - skill graph (GraphRAG-lite): skills, projects, client industries and outcomes as a networkx graph.
Requirements are mapped to canonical skills; projects are ranked by how many required skills they connect
to (plus industry match and winning-proposal edges); requirements with no recognised skill fall back to
dense retrieval.  Also answers "have I done X for a client in industry Y?"."""
from collections import defaultdict

import networkx as nx

from rag.ingest.skills import extract_skills
from rag.query import decompose
from rag.types import Hit
from rag.variants.base import RetrievalResult, Variant, merge_round_robin, to_items

ORDER = {"case_study": 0, "readme": 1, "code": 2, "review": 3}


def mask_types_only_dense(opts) -> bool:
    return opts.get("graph", True) is False


class V9SkillGraph(Variant):
    name = "v9_skill_graph"

    def __init__(self, corpus, **opts):
        super().__init__(corpus, **opts)
        g = nx.Graph()
        for it in corpus.items:
            g.add_node(("item", it.id))
            if it.project:
                g.add_edge(("project", it.project), ("item", it.id))
            for sk in it.skills:
                g.add_edge(("skill", sk), ("item", it.id))
                if it.project:
                    g.add_edge(("skill", sk), ("project", it.project))
            if it.client_industry and it.project:
                g.add_edge(("industry", it.client_industry), ("project", it.project))
            if it.type == "past_proposal" and it.outcome in ("won", "replied") and it.project:
                g.add_edge(("outcome", it.outcome), ("project", it.project))
        self.g = g

    def projects_for(self, skills: list[str], industry: str | None = None) -> list[tuple[str, float]]:
        score = defaultdict(float)
        for sk in skills:
            node = ("skill", sk)
            if node in self.g:
                for nb in self.g.neighbors(node):
                    if nb[0] == "project":
                        score[nb[1]] += 1.0
        for proj in list(score):
            if not self.opts.get("boosts", True):
                continue
            if industry and self.g.has_edge(("industry", industry), ("project", proj)):
                score[proj] += 0.5
            if self.g.has_edge(("outcome", "won"), ("project", proj)):
                score[proj] += 0.1
        return sorted(score.items(), key=lambda x: -x[1])

    def have_i_done(self, skill: str, industry: str | None = None) -> list[str]:
        return [p for p, s in self.projects_for([skill], industry) if s >= (1.5 if industry else 1.0)]

    def _items_of(self, proj: str) -> list[str]:
        return sorted([n[1] for n in self.g.neighbors(("project", proj)) if n[0] == "item"
                       and self.c.by_id[n[1]].type in ORDER], key=lambda i: ORDER[self.c.by_id[i].type])

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        reqs = decompose(job, requirements) if self.opts.get("decompose", True) else [f"{job.get('title', '')} {job.get('description', '')}"]
        idx, chunks = self.c.dense("structured")
        mask = self.c.mask(chunks, filters)
        per = {}
        for r in reqs:
            sks = extract_skills(r)
            if sks and (not mask_types_only_dense(self.opts)):
                hits = []
                for proj, s in self.projects_for(sks)[:k]:
                    for j, iid in enumerate(self._items_of(proj)):
                        hits.append(Hit(item_id=iid, score=s - 0.01 * j, requirement=r, snippet=self.c.by_id[iid].text[:900],
                                        signals={"graph": s}))
                if hits or not self.opts.get("dense_fallback", True):
                    per[r] = hits[:k]
                    continue
            hits = to_items(idx.search(r, 20, mask), chunks, r)[:k]
            for h in hits:
                h.signals["cos"] = h.score
            per[r] = hits
        return RetrievalResult(hits=merge_round_robin(per, k)[:k], by_requirement=per, requirements=reqs)
