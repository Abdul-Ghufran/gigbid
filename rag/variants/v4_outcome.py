"""V4 - outcome-aware ranking: projects that appear in proposals which won or got replies are boosted;
the writer also receives the most similar *winning* past proposals as phrasing examples."""
from collections import defaultdict

from rag.variants.base import Variant
from rag.variants.v3_rerank import V3Rerank

OUTCOME_W = {"won": 1.0, "replied": 0.5, "ignored": 0.0}


class V4Outcome(Variant):
    name = "v4_outcome"

    def __init__(self, corpus, **opts):
        super().__init__(corpus, **opts)
        self.base = V3Rerank(corpus, **opts)
        stats = defaultdict(lambda: [0.0, 0])
        for p in corpus.proposals:
            if p.project:
                stats[p.project][0] += OUTCOME_W.get(p.outcome or "ignored", 0)
                stats[p.project][1] += 1
        mean = sum(s for s, _ in stats.values()) / max(1, sum(n for _, n in stats.values()))
        # Laplace-smoothed success rate relative to the persona mean
        self.boost = {proj: ((s + mean * 2) / (n + 2)) - mean for proj, (s, n) in stats.items()}
        self.beta = opts.get("beta", 2.0)

    async def retrieve(self, job, k=10, requirements=None, filters=None):
        r = await self.base.retrieve(job, k=k * 2, requirements=requirements, filters=filters)
        for h in r.hits:
            proj = self.c.by_id[h.item_id].project
            b = self.boost.get(proj, 0.0)
            h.signals["outcome_boost"] = round(b, 3)
            h.score = h.signals.get("rr_score", 0.5) + self.beta * b
        r.hits = sorted(r.hits, key=lambda h: -h.score)[:k]
        return r

    def winning_examples(self, job: dict, n: int = 2) -> list[dict]:
        idx = self.c.proposal_index()
        good = {p.id for p in self.c.proposals if p.outcome in ("won", "replied")}
        hits = [(pid, s) for pid, s in idx.search(job.get("title", "") + " " + job.get("description", "")[:500], 20) if pid in good]
        return [{"id": pid, "outcome": self.c.by_id[pid].outcome, "text": self.c.by_id[pid].text} for pid, _ in hits[:n]]
