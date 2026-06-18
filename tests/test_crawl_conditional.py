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


def test_crawl_due_304_carries_forward(monkeypatch, tmp_path):
    import ergon_tracker.http as http_mod
    import ergon_tracker.providers.base as base_mod
    import ergon_tracker.registry.store as store_mod
    from ergon_tracker.index.db import connect

    monkeypatch.setattr(store_mod, "SeedRegistry", _FakeReg)
    monkeypatch.setattr(base_mod, "get_provider", lambda n: _Provider304())
    monkeypatch.setattr(base_mod, "load_builtins", lambda: None)
    monkeypatch.setattr(http_mod, "AsyncFetcher", _Fetcher304)

    # Pre-seed state with a stored validator + a past due date so the board is crawled.
    bs = BoardState(provider="greenhouse", token="stripe", etag='W/"abc"', next_due="2000-01-01")
    states = {bs.key: bs}
    fresh_db_path = tmp_path / "fresh.sqlite"

    outcome = anyio.run(bi._crawl_due, 10, states, fresh_db_path, "b1")

    assert connect(fresh_db_path, read_only=True).execute(
        "SELECT COUNT(*) FROM jobs"
    ).fetchone()[0] == 0  # nothing re-downloaded
    assert outcome[bs.key]["not_modified"] is True
    assert outcome[bs.key]["companies"] == set()  # empty -> prev jobs carry forward in merge


class _Provider200:
    """Returns a 200 with a body; the crawler must parse it WITHOUT calling fetch()."""

    name = "greenhouse"

    def conditional_url(self, token):
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

    async def fetch(self, *a):
        raise AssertionError("fetch called despite a reusable 200 body")

    def raws_from_body(self, token, body):
        import json

        from ergon_tracker.models import RawJob
        data = json.loads(body)
        return [
            RawJob(source="greenhouse", source_job_id=str(j["id"]), company=token,
                   token=token, url=None, payload=j)
            for j in data["jobs"]
        ]

    def normalize(self, raw):
        from ergon_tracker.models import JobPosting
        return JobPosting.create(source="greenhouse", source_job_id=raw.source_job_id,
                                 company=raw.company, title=raw.payload["title"])


class _Fetcher200:
    _BODY = b'{"jobs": [{"id": 1, "title": "Engineer"}]}'

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def conditional_get(self, url, *, etag=None, last_modified=None):
        return ConditionalResult(
            not_modified=False, status_code=200, etag='W/"new"', last_modified=None, body=self._BODY
        )


def test_crawl_due_200_reuses_body_without_refetch(monkeypatch, tmp_path):
    import ergon_tracker.http as http_mod
    import ergon_tracker.providers.base as base_mod
    import ergon_tracker.registry.store as store_mod
    from ergon_tracker.index.db import connect

    monkeypatch.setattr(store_mod, "SeedRegistry", _FakeReg)
    monkeypatch.setattr(base_mod, "get_provider", lambda n: _Provider200())
    monkeypatch.setattr(base_mod, "load_builtins", lambda: None)
    monkeypatch.setattr(http_mod, "AsyncFetcher", _Fetcher200)

    bs = BoardState(provider="greenhouse", token="stripe", etag='W/"old"', next_due="2000-01-01")
    states = {bs.key: bs}
    fresh_db_path = tmp_path / "fresh.sqlite"
    outcome = anyio.run(bi._crawl_due, 10, states, fresh_db_path, "b1")

    rows = connect(fresh_db_path, read_only=True).execute("SELECT title FROM jobs").fetchall()
    assert len(rows) == 1 and rows[0][0] == "Engineer"  # parsed from the 200 body, streamed to DB
    assert outcome[bs.key]["not_modified"] is False
    assert states[bs.key].etag == 'W/"new"'  # validator refreshed for next run
