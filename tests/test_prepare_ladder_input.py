"""Tests for the ladder-input preparer's pure non-operating filter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prepare_ladder_input import filter_operating, is_nonoperating  # noqa: E402


def test_is_nonoperating_flags_shells() -> None:
    for name in (
        "M3-Brigade Acquisition V Corp.",
        "Some SPAC Inc",
        "Pioneer Municipal High Income Trust",
        "iShares Core S&P 500 ETF",
        "Nuveen Credit Income Fund",
    ):
        assert is_nonoperating(name), name


def test_is_nonoperating_passes_real_companies() -> None:
    for name in (
        "Magic Software Enterprises Ltd",
        "Fastenal Company",
        "Sempra",
        "Micron Technology, Inc.",
    ):
        assert not is_nonoperating(name), name


def test_filter_operating_drops_shells_and_blanks() -> None:
    names = ["Fastenal", "Acme Acquisition Corp", "  ", "Micron Technology"]
    assert filter_operating(names) == ["Fastenal", "Micron Technology"]
