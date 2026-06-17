"""H-1B visa-sponsor: ETL parsing, enrichment, and filter."""

from __future__ import annotations

import sys
from pathlib import Path

from ergon_tracker.enrich import enrich_in_place
from ergon_tracker.extract import visa
from ergon_tracker.extract.visa import SponsorIndex
from ergon_tracker.models import JobPosting, SearchQuery

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_h1b_sponsors import sponsors_from_rows  # noqa: E402


def _job(company: str) -> JobPosting:
    return JobPosting.create(source="greenhouse", source_job_id="1", company=company, title="Eng")


# --- ETL parsing (pure, no workbook needed) ---------------------------------
def test_sponsors_from_rows_keeps_certified_and_normalizes() -> None:
    rows = [
        {"EMPLOYER_NAME": "Stripe, Inc.", "CASE_STATUS": "Certified"},
        {"EMPLOYER_NAME": "STRIPE INC", "CASE_STATUS": "Certified - Withdrawn"},  # same -> "stripe"
        {"EMPLOYER_NAME": "Denied Co", "CASE_STATUS": "Denied"},  # dropped
        {"EMPLOYER_NAME": "Acme GmbH", "CASE_STATUS": "CERTIFIED"},  # case-insensitive status
        {"EMPLOYER_NAME": "", "CASE_STATUS": "Certified"},  # blank employer dropped
    ]
    out = sponsors_from_rows(rows)
    assert out.get("stripe") == 2  # both certified Stripe rows collapse + count
    assert out.get("acme") == 1
    assert "denied co" not in out


def test_sponsors_from_rows_handles_alt_header() -> None:
    rows = [{"EMPLOYER_LEGAL_BUSINESS_NAME": "Globex LLC", "case_status": "Certified"}]
    assert sponsors_from_rows(rows).get("globex") == 1


# --- enrichment -------------------------------------------------------------
def test_enrich_sets_visa_sponsor_true_when_matched(monkeypatch) -> None:
    monkeypatch.setattr(visa, "load_sponsor_index", lambda: SponsorIndex({"stripe"}))
    # is_h1b_sponsor is imported into enrich's namespace -> patch there too.
    monkeypatch.setattr("ergon_tracker.enrich.is_h1b_sponsor", lambda c: visa.is_h1b_sponsor(c))

    job = _job("Stripe, Inc.")
    enrich_in_place(job)
    assert job.visa_sponsor is True

    other = _job("Nobody Co")
    enrich_in_place(other)
    assert other.visa_sponsor is None  # positive evidence only — never False


def test_index_missing_file_is_graceful() -> None:
    # Empty index -> nobody flagged, no crash (feature no-ops without the data file).
    idx = SponsorIndex(set())
    assert idx.is_sponsor("Stripe") is False
    assert len(idx) == 0


# --- filter -----------------------------------------------------------------
def test_visa_sponsor_filter() -> None:
    sponsor = _job("Stripe")
    sponsor.visa_sponsor = True
    unknown = _job("Nobody Co")  # visa_sponsor stays None

    q = SearchQuery(visa_sponsor=True)
    assert q.matches(sponsor) is True
    assert q.matches(unknown) is False

    assert SearchQuery().matches(unknown) is True  # no filter -> kept


def test_sponsor_index_normalizes_lookup() -> None:
    idx = SponsorIndex({"stripe"})
    assert idx.is_sponsor("Stripe, Inc.") is True
    assert idx.is_sponsor("STRIPE") is True
    assert idx.is_sponsor("Unrelated") is False
    assert idx.is_sponsor(None) is False
