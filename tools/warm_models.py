"""Download the open embedding + reranker models and pre-compute corpus embeddings at image build time, so the
container starts fast and never downloads at request time."""
import os

os.environ.setdefault("LLM_OFFLINE", "1")
from rag.corpus import get_corpus  # noqa: E402
from rag.index.core import embeddings  # noqa: E402

for p in ("ai", "web", "data"):
    c = get_corpus(p)
    c.dense("structured")
    c.dense("structured", multivector=True)
    c.proposal_index()
embeddings().save()
# reranker is not loaded in production (verification uses the bi-encoder; see agent/config.yaml)
print("models and corpus embeddings ready")
