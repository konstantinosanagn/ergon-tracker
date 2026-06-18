"""Decide whether a query should be served from the index, and do it safely (never raise)."""

from __future__ import annotations

import logging
import os

from ..models import JobPosting, SearchQuery
from .backend import SqliteIndexBackend
from .cache import IndexCache

log = logging.getLogger("ergon_tracker.index")


def _load_backend() -> SqliteIndexBackend | None:
    path = IndexCache().ensure_fresh()
    return SqliteIndexBackend(path) if path else None


def try_index(query: SearchQuery) -> list[JobPosting] | None:
    """Return index results for a broad query, or None to signal 'fall back to live'."""
    if os.environ.get("ERGON_INDEX", "").lower() == "off":
        return None
    if query.companies or query.sources:  # targeted => live (fresher, already fast)
        return None
    try:
        backend = _load_backend()
        if backend is None or not backend.available():
            return None
        return backend.search(query)
    except Exception as exc:  # noqa: BLE001 - index is a fast path, never a hard dependency
        log.warning("index query failed (%s); live fallback", exc)
        return None
