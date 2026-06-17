"""Relevance ranking for search results (deterministic, dependency-free).

After fetch + filter + dedup, results arrive in *source order* — which has nothing to do
with how well a posting matches the user's query. Without ranking, a search for ``"engineer"``
can surface an "Account Executive" role just because its *description* happens to mention
engineering. This module fixes precision while preserving recall: every candidate that passed
the filter is kept, but they are ordered by how well they actually match.

Design (deterministic-first, no ML, runs anywhere):

* **Field-weighted BM25.** Standard Okapi BM25 (the workhorse lexical ranker) over each job's
  searchable text, with the title weighted far above department/company, and description
  lowest. Field weighting is achieved by repeating field tokens ``w`` times before scoring, so
  a title hit dominates a description-only hit naturally. BM25 brings term-frequency saturation
  (k1) and length normalization (b), so keyword-stuffed descriptions don't win.
* **Stable.** Ties keep their prior order (authority/recency from dedup), so ranking only ever
  *improves* ordering, never scrambles equally-relevant results.

A pluggable :data:`Reranker` seam lets a stronger model (e.g. a cross-encoder such as ZeroEntropy
``zerank``) reorder the top-K later, installed as an optional extra — without touching the core.
By default no reranker is registered and ranking is pure lexical BM25.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .models import JobPosting

__all__ = ["rank", "score_text", "Reranker", "register_reranker"]

# BM25 hyperparameters (standard defaults).
_K1 = 1.5
_B = 0.75

# Field weights: how many times each field's tokens are counted. Title dominates.
_W_TITLE = 5
_W_DEPARTMENT = 2
_W_COMPANY = 2
_W_DESCRIPTION = 1

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _doc_tokens(job: JobPosting) -> list[str]:
    """Weighted bag of tokens for a posting: title tokens count most, description least."""
    out: list[str] = []
    out += _tokenize(job.title) * _W_TITLE
    if job.department:
        out += _tokenize(job.department) * _W_DEPARTMENT
    if job.company:
        out += _tokenize(job.company) * _W_COMPANY
    if job.description_text:
        out += _tokenize(job.description_text) * _W_DESCRIPTION
    return out


# --------------------------------------------------------------------------------------------
# Pluggable reranker seam (e.g. a cross-encoder like ZeroEntropy zerank). Optional; off by
# default. A backend implements `rerank(query, jobs) -> list[float]` returning a score per job.
# --------------------------------------------------------------------------------------------
@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, jobs: list[JobPosting]) -> list[float]:
        """Return a relevance score per job (same order/length as ``jobs``)."""
        ...


_RERANKER: Reranker | None = None


def register_reranker(reranker: Reranker | None) -> None:
    """Install (or clear, with ``None``) a stronger reranker used after lexical BM25.

    Optional extras (e.g. a zerank backend) call this to plug in a cross-encoder. The core
    never imports a model; this keeps the default install light and fully deterministic.
    """
    global _RERANKER
    _RERANKER = reranker


def score_text(query: str, jobs: list[JobPosting]) -> list[float]:
    """Compute field-weighted BM25 scores for ``jobs`` against ``query`` (one score per job).

    Pure function over the candidate set; no network, no model. Empty query -> all zeros.
    """
    q_terms = _tokenize(query)
    n = len(jobs)
    if not q_terms or n == 0:
        return [0.0] * n

    docs = [_doc_tokens(j) for j in jobs]
    doc_len = [len(d) for d in docs]
    avgdl = (sum(doc_len) / n) or 1.0
    tfs = [Counter(d) for d in docs]

    # IDF per query term (BM25 form), over this candidate set.
    q_unique = set(q_terms)
    df = {t: sum(1 for tf in tfs if t in tf) for t in q_unique}
    idf = {
        t: math.log(1.0 + (n - df_t + 0.5) / (df_t + 0.5))
        for t, df_t in df.items()
    }

    scores: list[float] = []
    for i in range(n):
        tf = tfs[i]
        dl = doc_len[i] or 1
        s = 0.0
        for t in q_unique:
            f = tf.get(t, 0)
            if not f:
                continue
            denom = f + _K1 * (1.0 - _B + _B * dl / avgdl)
            s += idf[t] * (f * (_K1 + 1.0)) / denom
        scores.append(s)
    return scores


def rank(jobs: list[JobPosting], query: str | None) -> list[JobPosting]:
    """Return ``jobs`` ordered by relevance to ``query`` (descending), setting ``job.score``.

    Stable: equally-scored jobs keep their incoming order (authority/recency from dedup). With
    no query (or no jobs) the list is returned unchanged and scores are left as-is. If a
    reranker is registered, it reorders the lexical top-K for a final precision pass.
    """
    if not query or len(jobs) <= 1:
        return jobs

    scores = score_text(query, jobs)
    for job, sc in zip(jobs, scores):
        job.score = sc

    # Optional stronger reranker over the lexical top-K (kept small for cost).
    if _RERANKER is not None:
        top_k = min(len(jobs), 100)
        order = sorted(range(len(jobs)), key=lambda i: scores[i], reverse=True)
        head_idx = order[:top_k]
        head_jobs = [jobs[i] for i in head_idx]
        try:
            re_scores = _RERANKER.rerank(query, head_jobs)
            for job, sc in zip(head_jobs, re_scores):
                job.score = sc
        except Exception:  # noqa: BLE001 - a reranker failure must not break search
            pass

    # Stable sort by score desc (Python sort is stable, so ties keep prior order).
    return sorted(jobs, key=lambda j: (j.score if j.score is not None else 0.0), reverse=True)
