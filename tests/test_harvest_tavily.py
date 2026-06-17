"""Tests for the Tavily harvester's pure result->token extraction (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_commoncrawl import CONFIGS  # noqa: E402
from harvest_tavily import tokens_from_results  # noqa: E402


def test_tokens_from_results_greenhouse() -> None:
    results = [
        {"url": "https://boards.greenhouse.io/figma", "title": "Figma"},
        {"url": "https://boards.greenhouse.io/figma/jobs/123"},  # dup token
        {"url": "https://boards.greenhouse.io/discord"},
        {"url": "https://boards.greenhouse.io/embed/job_board"},  # junk
        {"title": "no url key"},
    ]
    assert tokens_from_results(CONFIGS["greenhouse"], results) == ["figma", "discord"]


def test_tokens_from_results_subdomain_and_lever() -> None:
    assert tokens_from_results(
        CONFIGS["lever"], [{"url": "https://jobs.lever.co/netflix/abc"}]
    ) == ["netflix"]
    assert tokens_from_results(
        CONFIGS["rippling"], [{"url": "https://ats.rippling.com/acme/jobs"}]
    ) == ["acme"]
    # a non-matching host yields nothing for that ATS
    assert tokens_from_results(CONFIGS["lever"], [{"url": "https://example.com/x"}]) == []
