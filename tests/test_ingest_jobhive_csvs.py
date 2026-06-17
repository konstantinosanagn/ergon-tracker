"""Tests for the jobhive-CSV ingest's pure row->candidate mapping (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_jobhive_csvs import (  # noqa: E402
    company_key,
    parse_jobhive_csv,
    row_to_candidate,
)


def test_company_key_slugifies() -> None:
    assert company_key("Modern Treasury") == "modern-treasury"
    assert company_key("  1Password!! ") == "1password"
    assert company_key("dbt Labs") == "dbt-labs"


def test_row_to_candidate_simple_uses_slug() -> None:
    c = row_to_candidate("greenhouse", {"name": "Stripe", "slug": "stripe", "url": ""})
    assert c == {"company": "stripe", "ats": "greenhouse", "token": "stripe", "domain": None}


def test_row_to_candidate_falls_back_to_url_extraction() -> None:
    # No slug column -> recover the token from the url via the provider's matches().
    c = row_to_candidate(
        "greenhouse", {"name": "Acme", "url": "https://boards.greenhouse.io/acme"}
    )
    assert c is not None and c["token"] == "acme"


def test_row_to_candidate_workday_parses_url_into_triple() -> None:
    c = row_to_candidate(
        "workday",
        {"name": "NVIDIA",
         "url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"},
    )
    assert c == {
        "company": "nvidia", "ats": "workday",
        "tenant": "nvidia", "wd": "wd5", "site": "NVIDIAExternalCareerSite", "domain": None,
    }


def test_row_to_candidate_workday_unparseable_url_dropped() -> None:
    assert row_to_candidate("workday", {"name": "X", "url": "https://example.com/careers"}) is None


def test_row_to_candidate_empty_dropped() -> None:
    assert row_to_candidate("greenhouse", {"name": "", "slug": "", "url": ""}) is None


def test_parse_jobhive_csv_dedupes_and_counts_unmappable() -> None:
    text = (
        "name,slug,url\n"
        "Stripe,stripe,https://boards.greenhouse.io/stripe\n"
        "Stripe,stripe,https://boards.greenhouse.io/stripe\n"  # dup key
        "Bad,,\n"  # unmappable (no slug, no url)
        "Airbnb,airbnb,\n"
    )
    cands, skipped = parse_jobhive_csv(text, "greenhouse")
    keys = {c["company"] for c in cands}
    assert keys == {"stripe", "airbnb"}
    assert skipped == 1
