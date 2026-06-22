"""Unit tests for the ATS-exhaustion sweep's pure decision logic (the entity-correctness guard)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ats_exhaustion_sweep import _adjudicate  # noqa: E402


def _raw(company: str):
    return SimpleNamespace(company=company)


def test_adjudicate_accepts_matching_entity() -> None:
    assert _adjudicate("HCA Healthcare", [_raw("HCA Healthcare")], provider=None)          # exact
    assert _adjudicate("Targa Resources", [_raw("Targa Resources Corp")], provider=None)   # suffix-stripped
    assert _adjudicate("Saama Technologies", [_raw("noise"), _raw("Saama")], provider=None) # any of sample


def test_adjudicate_rejects_namesake() -> None:
    assert not _adjudicate("Vici Properties", [_raw("Vici Collection")], provider=None)
    assert not _adjudicate("PPL Corporation", [_raw("Providence Public Library")], provider=None)


def test_adjudicate_empty_is_miss() -> None:
    assert not _adjudicate("Anyone", [], provider=None)


def test_adjudicate_trust_skips_entity_check_for_clean_federations() -> None:
    assert _adjudicate("Whatever", [_raw("Anything At All")], provider=None, trust=True)
    assert not _adjudicate("Whatever", [], provider=None, trust=True)  # still needs >=1 job
