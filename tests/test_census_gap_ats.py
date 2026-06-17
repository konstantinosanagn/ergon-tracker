"""Tests for the gap-ATS census's pure detection/adjudication logic (no network/browser)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from census_gap_ats import detect_ats, name_in_url  # noqa: E402


def test_detect_ats_supported_and_unsupported() -> None:
    assert detect_ats("https://acme.wd5.myworkdayjobs.com/x") == ("workday", True)
    assert detect_ats("https://boards.greenhouse.io/acme") == ("greenhouse", True)
    assert detect_ats("careers-acme.icims.com/jobs") == ("icims", False)
    assert detect_ats("https://acme.eightfold.ai/careers") == ("eightfold", False)
    assert detect_ats("https://acme.com/about") is None


def test_detect_ats_prefers_supported_on_ties() -> None:
    # supported signatures are listed first, so they win when both full signatures appear
    assert detect_ats("boards.greenhouse.io and icims.com both here")[0] == "greenhouse"


def test_name_in_url_matches_significant_word() -> None:
    assert name_in_url("wal mart associates", "https://walmart.wd5.myworkdayjobs.com") is True
    assert name_in_url("qualcomm technologies", "https://qualcomm.wd12.myworkdayjobs.com") is True
    # a different company's board must NOT match
    assert name_in_url("cognizant", "https://collaborative.wd1.myworkdayjobs.com") is False
    # short stopword-only overlaps don't match (no significant word present)
    assert name_in_url("ibm", "https://crownholdings.wd5.myworkdayjobs.com") is False
