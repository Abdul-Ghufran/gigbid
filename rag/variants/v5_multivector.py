"""V5 - multi-vector items: case-study summary, README and code chunks are indexed separately and the
best match of any vector lifts the whole project, which is then returned as one unit (case, README, code)."""
from collections import defaultdict

from rag.query import decompose
from rag.types import Hit
from rag.variants.base import RetrievalResult, Variant, merge_round_robin

ORDER = {"case_study": 0, "readme": 1, "code": 2}


class V5MultiVector(Variant):
    name = "v5_multivector"

    def _project_rank(self, q, mask, k, requirement=None):
        idx, chunks = self.c.dense("structured", multivector=True)
        by_chunk = {c.id: c for c in chunks}
        proj_score: dict[str, float] = defaultdict(lambda: -1e9)
        loose: dict[str, float] = {}
        for cid, s in idx.search(q, 60, mask):
            it = self.c.by_id[by_chunk[cid].item_id]
            if it.project:
                proj_score[it.project] = max(proj_score[it.project], s)
            else:
                loose[it.id] = max(loose.get(it.id, -1e9), s)
        hits: list[Hit] = []
        for proj, s in sorted(proj_score.items(), key=lambda x: -x[1]):
            members = sorted([i for i in self.c.evidence if i.project == proj and i.type in ORDER], key=lambda i: ORDER[i.type])
            for j, it in enumerate(members):
                hits.append(Hit(item_id=it.id, score=s - 0.001 * j, requirement=requirement, snippet=it.text[:300]))
        hits += [Hit(item_id=i, score=s, requirement=requirement, snippet=self.c.by_id[i].text[:300]) for i, s in loose.items()]
        return sorted(hits, key=lambda h: -h.score)[:k]

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        _, chunks = self.c.dense("structured", multivector=True)
        mask = self.c.mask(chunks, filters)
        reqs = decompose(job, requirements)
        per = {r: self._project_rank(r, mask, k, r) for r in reqs}
        return RetrievalResult(hits=merge_round_robin(per, k)[:k], by_requirement=per, requirements=reqs)
