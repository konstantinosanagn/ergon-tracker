"""Semantic reranking (Layer 2) — optional, embeddings-based.

Lexical BM25 (the default :mod:`ergon_tracker.ranking`) matches *tokens*. It can't tell that
"ML engineer" and "Machine Learning" mean the same thing, or rank a role for the *meaning* of
"fintech using Rust, remote-friendly". This module adds that, using small CPU embedding models
via `fastembed` (ONNX) — no GPU, no API, fully local. It is an **opt-in extra**::

    pip install 'ergon-tracker[semantic]'

and is engaged per search with ``semantic=True``. It implements the
:class:`ergon_tracker.ranking.Reranker` protocol, so it plugs into the existing ranking seam:
lexical BM25 narrows to a top-K candidate set, then embeddings reorder it by cosine similarity.

The model (~130 MB) downloads once on first use and is cached by `fastembed`. The model is
loaded lazily and memoized, so importing this module never downloads anything.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import JobPosting

__all__ = ["SemanticReranker", "get_semantic_reranker", "DEFAULT_MODEL"]

# Small, fast, good-quality English embedding model (CPU/ONNX). Override via get_semantic_reranker.
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

# How much of each posting to embed. Title carries the most signal; we prepend it and add a
# bounded slice of the description so long postings don't dominate or slow things down.
_DESC_CHARS = 600


def _job_text(job: JobPosting) -> str:
    parts = [job.title or ""]
    if job.department:
        parts.append(job.department)
    if job.description_text:
        parts.append(job.description_text[:_DESC_CHARS])
    return " — ".join(p for p in parts if p)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SemanticReranker:
    """Embeddings reranker: scores jobs by cosine similarity to the query.

    Implements the ``Reranker`` protocol (``rerank(query, jobs) -> list[float]``). The embedding
    model is created lazily on first ``rerank`` call so constructing this object is cheap.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "Semantic search needs the optional extra: pip install 'ergon-tracker[semantic]'"
            ) from exc
        self._model = TextEmbedding(model_name=self.model_name)

    def rerank(self, query: str, jobs: list[JobPosting]) -> list[float]:
        if not jobs:
            return []
        self._ensure_model()
        assert self._model is not None
        texts = [_job_text(j) for j in jobs]
        # fastembed returns numpy arrays; tolist() keeps this dependency-light (no numpy import).
        query_vec = next(iter(self._model.embed([query]))).tolist()
        doc_vecs = [v.tolist() for v in self._model.embed(texts)]
        return [_cosine(query_vec, dv) for dv in doc_vecs]


@lru_cache(maxsize=4)
def get_semantic_reranker(model_name: str = DEFAULT_MODEL) -> SemanticReranker:
    """Return a memoized :class:`SemanticReranker` (one model load per process, per model name).

    Raises ``ImportError`` with install guidance the first time it embeds if the ``semantic``
    extra is not installed.
    """
    return SemanticReranker(model_name)
