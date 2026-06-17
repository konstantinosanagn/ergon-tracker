"""Tests for the GitHub code-search harvester's pure extraction (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_github import fragments_from_search, tokens_from_fragments  # noqa: E402


def test_tokens_from_fragments_extracts_and_dedupes() -> None:
    frags = [
        'fetch("https://boards.greenhouse.io/stripe/jobs")',
        "GREENHOUSE_URL = 'https://boards.greenhouse.io/stripe'",  # dup token
        "https://boards.greenhouse.io/airbnb",
        "https://boards.greenhouse.io/embed/job_app",  # junk -> rejected
        "no url here",
    ]
    assert tokens_from_fragments("greenhouse", frags) == ["stripe", "airbnb"]


def test_tokens_from_fragments_per_ats_rules() -> None:
    # subdomain ATS (pinpoint) and path ATS (lever) use their own extractors
    assert tokens_from_fragments(
        "pinpoint", ["url: https://globex.pinpointhq.com/postings.json"]
    ) == ["globex"]
    assert tokens_from_fragments(
        "lever", ["see https://jobs.lever.co/netflix/role-123 for details"]
    ) == ["netflix"]
    # a greenhouse URL yields nothing for the lever extractor
    assert tokens_from_fragments("lever", ["https://boards.greenhouse.io/stripe"]) == []


def test_fragments_from_search_pulls_text_matches() -> None:
    payload = {
        "items": [
            {"text_matches": [{"fragment": "a"}, {"fragment": "b"}]},
            {"text_matches": [{"fragment": "c"}]},
            {"text_matches": None},  # tolerated
            {},  # tolerated
        ]
    }
    assert fragments_from_search(payload) == ["a", "b", "c"]
    assert fragments_from_search({}) == []
    assert fragments_from_search(json.loads("[]")) == []  # non-dict tolerated
