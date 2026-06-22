"""Tests for scripts/build_registry.py verification helpers.

The crux: a candidate that merely throttled (429 / timeout / circuit-open / exhausted retries)
must be classified TRANSIENT so it is re-verified, never silently merged into the permanent
"dead" set. Genuinely-empty (200 + no jobs) and gone (404/410) boards must classify as final.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "_build_registry", pathlib.Path(__file__).parent.parent / "scripts" / "build_registry.py"
)
br = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(br)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "err,expected",
    [
        (None, "empty"),
        ("HTTPStatusError: 404 Not Found", "gone"),
        ("HTTPStatusError: 410 Gone", "gone"),
        ("HTTPStatusError: 403 Forbidden", "walled"),
        ("RateLimitError: 429 Too Many Requests from boards.greenhouse.io", "rate_limited"),
        ("FetchError: circuit open for workable.com (cooling down)", "circuit_open"),
        ("FetchError: exhausted retries for https://x", "exhausted"),
        ("ReadTimeout: timed out", "timeout"),
        ("ConnectError: connection refused", "transport"),
        ("JSONDecodeError: Expecting value", "parse_error"),
    ],
)
def test_classify_dead(err, expected):
    assert br.classify_dead(err) == expected


@pytest.mark.parametrize(
    "err",
    [
        "RateLimitError: 429 Too Many Requests",
        "FetchError: circuit open for workable.com (cooling down)",
        "FetchError: exhausted retries for https://x",
        "ReadTimeout: timed out",
        "ConnectError: connection refused",
        "TransientHTTPError: 503 from x",
    ],
)
def test_is_transient_true_for_throttle_and_network(err):
    assert br.is_transient(err) is True


@pytest.mark.parametrize(
    "err",
    [
        None,  # clean empty board
        "HTTPStatusError: 404 Not Found",
        "HTTPStatusError: 410 Gone",
        "HTTPStatusError: 403 Forbidden",
        "JSONDecodeError: Expecting value",
        "no provider for foo",
    ],
)
def test_is_transient_false_for_permanent(err):
    assert br.is_transient(err) is False


def test_dedupe_best_prefers_more_jobs_then_ats_priority():
    # Same company on two ATSes: more jobs wins.
    gh = {"company": "acme", "ats": "greenhouse"}
    lv = {"company": "acme", "ats": "lever"}
    best = br.dedupe_best([(gh, 3, "acme"), (lv, 9, "acme")])
    assert best["acme"][0]["ats"] == "lever"  # 9 > 3 jobs

    # Tie on job count: lower ATS_PRIORITY number wins (greenhouse 0 < lever 1).
    best2 = br.dedupe_best([(lv, 5, "acme"), (gh, 5, "acme")])
    assert best2["acme"][0]["ats"] == "greenhouse"


def test_trusted_empties_only_json_providers_and_clean_empty():
    # dead = (entry, token, err). Only err=None (clean empty) on a trusted JSON ATS onboards.
    dead = [
        ({"company": "a", "ats": "greenhouse"}, "a", None),  # trusted + empty -> yes
        ({"company": "b", "ats": "lever"}, "b", None),  # trusted + empty -> yes
        ({"company": "c", "ats": "join"}, "c", None),  # untrusted (HTML) -> no
        ({"company": "d", "ats": "personio"}, "d", None),  # untrusted (feed) -> no
        ({"company": "e", "ats": "greenhouse"}, "e", "HTTPStatusError: 404"),  # gone -> no
        ({"company": "f", "ats": "ashby"}, "f", "ReadTimeout"),  # transient -> no
    ]
    out = br.trusted_empties(dead, br.TRUSTED_EMPTY_PROVIDERS)
    assert sorted(e["company"] for e, _t in out) == ["a", "b"]


def test_trusted_provider_allowlist_excludes_html_scrapers():
    assert {"greenhouse", "lever", "ashby", "workable"} <= br.TRUSTED_EMPTY_PROVIDERS
    assert br.TRUSTED_EMPTY_PROVIDERS.isdisjoint({"join", "personio", "jazzhr"})


def test_dedupe_best_prefers_live_over_empty_same_company():
    gh_empty = {"company": "acme", "ats": "greenhouse"}
    lv_live = {"company": "acme", "ats": "lever"}
    best = br.dedupe_best([(gh_empty, 0, "acme"), (lv_live, 2, "acme")])
    assert best["acme"][0]["ats"] == "lever"  # live (2 jobs) beats empty (0)
    assert best["acme"][1] == 2


def test_partition_splits_live_from_dead_carrying_err():
    results = {
        0: ({"company": "a", "ats": "lever"}, 4, "a", None),
        1: ({"company": "b", "ats": "lever"}, 0, "b", "ReadTimeout: timed out"),
        2: ({"company": "c", "ats": "lever"}, 0, "c", None),
    }
    verified, dead = br.partition(results)
    assert [v[0]["company"] for v in verified] == ["a"]
    assert {d[0]["company"]: d[2] for d in dead} == {
        "b": "ReadTimeout: timed out",
        "c": None,
    }


# --- candidate validation: a malformed row must never crash the batch -------------------------
@pytest.mark.parametrize(
    "entry",
    [
        {"company": "acme", "ats": "greenhouse", "token": "acme"},
        {"company": "acme", "ats": "workday", "tenant": "acme", "wd": "wd1", "site": "Careers"},
        {"company": "acme", "ats": "greenhouse", "token": "acme", "domain": "acme.com"},
    ],
)
def test_validate_candidate_accepts_well_formed(entry):
    assert br.validate_candidate(entry) is None


@pytest.mark.parametrize(
    "entry",
    [
        {"company": "acme", "token": "acme"},  # missing ats
        {"company": "acme", "ats": "", "token": "acme"},  # blank ats
        {"ats": "greenhouse", "token": "acme"},  # missing company
        {"company": "acme", "ats": "greenhouse"},  # non-workday missing token
        {"company": "acme", "ats": "greenhouse", "token": ""},  # blank token
        {"company": "acme", "ats": "workday", "wd": "wd1", "site": "Careers"},  # wd missing tenant
        {"company": "acme", "ats": "workday", "tenant": "acme", "site": "Careers"},  # missing wd
        {"company": "acme", "ats": "workday", "tenant": "acme", "wd": "wd1"},  # missing site
        "not-a-dict",
    ],
)
def test_validate_candidate_rejects_malformed(entry):
    assert br.validate_candidate(entry) is not None


def test_verify_one_returns_dead_not_raises_on_malformed(anyio_backend="asyncio"):
    # The critical regression: token_for used to be called outside the try/except, so a Workday
    # row missing `tenant` raised KeyError straight out of the task group, aborting the whole run.
    import anyio as _anyio

    bad = {"company": "acme", "ats": "workday", "wd": "wd1", "site": "Careers"}  # no tenant

    async def _run():
        # fetcher is never reached for an invalid candidate, so None is safe here.
        return await br.verify_one(bad, None, br.SearchQuery(limit=1))

    entry, count, token, err = _anyio.run(_run)
    assert count == 0
    assert err and "invalid-candidate" in err


# --- merge: add-only, dedup by slug AND by (ats, token) physical board ------------------------
def test_merge_candidates_adds_new_board():
    companies: dict = {}
    best = {"acme": ({"company": "acme", "ats": "greenhouse", "domain": "acme.com"}, 5, "acme")}
    stats = br.merge_candidates(companies, best)
    assert companies["acme"] == {"ats": "greenhouse", "token": "acme", "domain": "acme.com"}
    assert stats["added"] == 1


def test_merge_candidates_skips_existing_slug():
    companies = {"acme": {"ats": "lever", "token": "acme-old", "domain": None}}
    best = {"acme": ({"company": "acme", "ats": "greenhouse"}, 5, "acme")}
    stats = br.merge_candidates(companies, best)
    assert companies["acme"]["ats"] == "lever"  # unchanged (add-only)
    assert stats["added"] == 0 and stats["dup_slug"] == 1


def test_merge_candidates_skips_same_physical_board_under_different_slug():
    # The (ats, token) dedup: same greenhouse board already present as 'acme-inc' must not be
    # re-added under a different name slug 'acme-incorporated'.
    companies = {"acme-inc": {"ats": "greenhouse", "token": "acme", "domain": None}}
    best = {"acme-incorporated": ({"company": "acme-incorporated", "ats": "greenhouse"}, 5, "acme")}
    stats = br.merge_candidates(companies, best)
    assert "acme-incorporated" not in companies
    assert stats["added"] == 0 and stats["dup_board"] == 1


def test_merge_candidates_dedups_same_board_within_batch():
    companies = {}
    best = {
        "acme-inc": ({"company": "acme-inc", "ats": "greenhouse"}, 5, "acme"),
        "acme-corp": ({"company": "acme-corp", "ats": "greenhouse"}, 5, "acme"),
    }
    stats = br.merge_candidates(companies, best)
    assert stats["added"] == 1 and stats["dup_board"] == 1
    assert len(companies) == 1


def test_merge_candidates_rejects_demo_board():
    companies = {}
    best = {"demo": ({"company": "demo", "ats": "lever"}, 3, "leverdemo")}
    stats = br.merge_candidates(companies, best)
    assert companies == {} and stats["demo"] == 1


def test_bump_meta_sets_version_and_today():
    import datetime as _dt

    meta = {"version": 1, "updated": "2020-01-01"}
    br.bump_meta(meta)
    assert meta["version"] == 2
    assert meta["updated"] == _dt.date.today().isoformat()
