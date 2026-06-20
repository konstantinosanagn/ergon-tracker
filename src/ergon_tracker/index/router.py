"""Decide whether a query should be served from the index, and do it safely (never raise)."""

from __future__ import annotations

import logging
import os

from ..models import JobPosting, SearchQuery
from .backend import ShardedIndexBackend, SqliteIndexBackend
from .cache import IndexCache, ShardCache, SlimCache

log = logging.getLogger("ergon_tracker.index")


def _load_sharded(query: SearchQuery) -> ShardedIndexBackend | None:
    """v2 path: download only the shard(s) this query needs, return a sharded backend."""
    shard_dir = ShardCache().ensure(query)
    return ShardedIndexBackend(shard_dir) if shard_dir else None


def _slim_serves(query: SearchQuery) -> bool:
    """True when the slim tier returns IDENTICAL results to the full index for this query.

    The slim tier nulls snippet/description (so keyword matches in the description would be lost)
    and years (so year filters can't apply) and skips semantic embeddings. It is therefore exactly
    equivalent to the full index only for broad STRUCTURED-FILTER queries: no keywords, no year
    filter, no semantic rerank. Those download ~half the bytes with zero recall loss.
    """
    return (
        not query.keywords
        and not query.semantic
        and query.min_years is None
        and query.max_years is None
    )


def _load_slim() -> SqliteIndexBackend | None:
    """v2 path: the compact slim broad-query tier (~half the full-file download)."""
    path = SlimCache().ensure_fresh()
    return SqliteIndexBackend(path) if path else None


def _load_backend() -> SqliteIndexBackend | None:
    """v1 path: the single-file index."""
    path = IndexCache().ensure_fresh()
    return SqliteIndexBackend(path) if path else None


def try_index(query: SearchQuery) -> list[JobPosting] | None:
    """Return index results for a broad query, or None to signal 'fall back to live'.

    Preference order: sector-sharded index (v2, sector queries only) -> single-file index (v1)
    -> live (None).
    """
    if os.environ.get("ERGON_INDEX", "").lower() == "off":
        return None
    if query.companies or query.sources:  # targeted => live (fresher, already fast)
        return None
    try:
        # The sharded path only wins for SECTOR-scoped queries (download one small shard). A
        # broad/cross-sector query would have to pull every shard — slower than the single-file
        # index's one download + single global FTS rank — so skip straight to single-file.
        if query.sector:
            sharded = _load_sharded(query)
            if sharded is not None and sharded.available():
                return sharded.search(query)
        # Broad structured-filter query (no keywords/years/semantic): the slim tier is an exact,
        # smaller-download equivalent of the full index — prefer it, fall through to full if absent.
        if _slim_serves(query):
            slim = _load_slim()
            if slim is not None and slim.available():
                return slim.search(query)
        backend = _load_backend()
        if backend is None or not backend.available():
            return None
        return backend.search(query)
    except Exception as exc:  # noqa: BLE001 - index is a fast path, never a hard dependency
        log.warning("index query failed (%s); live fallback", exc)
        return None


def try_index_ranked(query: SearchQuery) -> list[JobPosting] | None:
    """try_index + semantic rerank when query.semantic — the full index serving path.

    Shared by BOTH the live engine and the MCP server so a broad ``semantic=True`` query is
    embedding-reranked no matter which surface issues it (the index itself only ranks lexically via
    BM25). On any rerank failure (e.g. the optional fastembed extra is absent) it degrades to the
    index's lexical order. Returns None to signal 'fall back to live' exactly like try_index.
    """
    indexed = try_index(query)
    if indexed is None:
        return None
    if query.semantic and query.keywords and len(indexed) > 1:
        # Rerank a WIDER candidate pool from the index by embedding similarity, then truncate.
        try:
            from ..ranking import rank
            from ..semantic import get_semantic_reranker

            want = query.limit or 20
            pool = try_index(query.model_copy(update={"limit": max(want * 10, 200)})) or indexed
            indexed = rank(pool, query.keywords, reranker=get_semantic_reranker())[:want]
        except Exception as exc:  # noqa: BLE001 - reranker optional; lexical order is fine
            log.warning("semantic rerank on index unavailable (%s); lexical order", exc)
    return indexed
