"""Unit tests for the DirectEmployers/dejobs provider (respx-mocked, offline)."""

from __future__ import annotations

import httpx
import pytest
import respx

from ergon_tracker.http import AsyncFetcher
from ergon_tracker.models import RemoteType, SearchQuery, make_job_id
from ergon_tracker.providers.dejobs import DEJobsProvider

pytestmark = pytest.mark.anyio

API = "https://prod-search-api.jobsyn.org/api/v1/solr/search"


def _job(guid: str, title: str, loc: str) -> dict:
    return {
        "guid": guid,
        "title_exact": title,
        "company_exact": "American Airlines",
        "location_exact": loc,
        "title_slug": title.lower().replace(" ", "-"),
        "date_added": "2026-06-01T00:00:00Z",
        "description": f"<p>{title}</p>",
    }


def _mock(respx_mock: respx.MockRouter) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        _job("G1", "Staff Assistant", "Los Angeles, CA"),
                        _job("G2", "Flight Attendant (Remote)", "Remote, US"),
                    ],
                    "pagination": {"total": 2, "page": 1, "page_size": 15, "has_more_pages": False},
                },
            )
        return httpx.Response(200, json={"jobs": [], "pagination": {"has_more_pages": False}})

    respx_mock.get(url__startswith=API).mock(side_effect=handler)


def test_matches_is_seed_only() -> None:
    # Aggregator: never auto-claims a host.
    assert DEJobsProvider.matches("https://dejobs.org/x") is None


async def test_fetch_and_normalize() -> None:
    with respx.mock as respx_mock:
        _mock(respx_mock)
        async with AsyncFetcher(per_host_rate=100) as f:
            raws = await DEJobsProvider().fetch("american-airlines", SearchQuery(), f)

    assert len(raws) == 2
    assert {r.company for r in raws} == {"American Airlines"}
    j0 = DEJobsProvider().normalize(raws[0])
    assert j0.id == make_job_id("dejobs", "G1")
    assert j0.title == "Staff Assistant"
    assert j0.locations[0].raw == "Los Angeles, CA"
    assert "G1" in j0.apply_url
    assert j0.posted_at is not None

    remote = DEJobsProvider().normalize(raws[1])
    assert remote.remote is RemoteType.REMOTE


async def test_fetch_respects_limit() -> None:
    with respx.mock as respx_mock:
        _mock(respx_mock)
        async with AsyncFetcher(per_host_rate=100) as f:
            raws = await DEJobsProvider().fetch("american-airlines", SearchQuery(limit=1), f)
    assert len(raws) == 1


async def test_fetch_degrades_on_error() -> None:
    with respx.mock as respx_mock:
        respx_mock.get(url__startswith=API).mock(return_value=httpx.Response(403))
        async with AsyncFetcher(per_host_rate=100) as f:
            raws = await DEJobsProvider().fetch("american-airlines", SearchQuery(), f)
    assert raws == []
