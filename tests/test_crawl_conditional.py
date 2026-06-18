"""Crawler conditional pre-check: a 304 carries forward without calling provider.fetch."""

from __future__ import annotations

import sys
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_index as bi  # noqa: E402

from ergon_tracker.http import ConditionalResult  # noqa: E402
from ergon_tracker.index.scheduler import BoardState  # noqa: E402


class _FakeReg:
    def all(self):
        return {"co": {"ats": "greenhouse", "token": "stripe", "domain": "stripe.com"}}


class _Provider304:
    name = "greenhouse"

    def conditional_url(self, token):
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

    async def fetch(self, *a):  # must NOT run when the board is unchanged
        raise AssertionError("provider.fetch called despite 304")

    def normalize(self, raw):  # pragma: no cover - not reached on 304
        raise AssertionError


class _Fetcher304:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def conditional_get(self, url, *, etag=None, last_modified=None):
        return ConditionalResult(
            not_modified=True, status_code=304, etag=etag, last_modified=last_modified
        )


def test_crawl_due_304_carries_forward(monkeypatch):
    import ergon_tracker.http as http_mod
    import ergon_tracker.providers.base as base_mod
    import ergon_tracker.registry.store as store_mod

    monkeypatch.setattr(store_mod, "SeedRegistry", _FakeReg)
    monkeypatch.setattr(base_mod, "get_provider", lambda n: _Provider304())
    monkeypatch.setattr(base_mod, "load_builtins", lambda: None)
    monkeypatch.setattr(http_mod, "AsyncFetcher", _Fetcher304)

    # Pre-seed state with a stored validator + a past due date so the board is crawled.
    bs = BoardState(provider="greenhouse", token="stripe", etag='W/"abc"', next_due="2000-01-01")
    states = {bs.key: bs}

    fresh, outcome = anyio.run(bi._crawl_due, 10, states)

    assert fresh == []  # nothing re-downloaded
    assert outcome[bs.key]["not_modified"] is True
    assert outcome[bs.key]["companies"] == set()  # empty -> prev jobs carry forward in merge
