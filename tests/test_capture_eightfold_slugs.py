"""Tests for the pure slug-extraction helper (no network/browser)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_eightfold_slugs import slug_from_urls  # noqa: E402


def test_extracts_first_real_slug() -> None:
    urls = [
        "https://www.eightfold.ai/some-marketing",  # generic front -> skipped
        "https://careers.amd.com/",  # not eightfold
        "https://amd-careers.eightfold.ai/api/pcsx/search?domain=amd.com",
    ]
    assert slug_from_urls(urls) == "amd-careers"


def test_skips_generic_subdomains() -> None:
    assert slug_from_urls(["https://app.eightfold.ai/careers"]) is None
    assert slug_from_urls(["https://cdn.eightfold.ai/x.js"]) is None


def test_handles_bare_host_and_empty() -> None:
    assert slug_from_urls(["deere-prod.eightfold.ai/careers"]) == "deere-prod"
    assert slug_from_urls(["", "https://example.com"]) is None
    assert slug_from_urls([]) is None
