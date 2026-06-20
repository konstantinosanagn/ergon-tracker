"""Tests for the aggregator apply-URL mining harvester (pure core, offline)."""

from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "_harvest_apply", ROOT / "scripts" / "harvest_aggregator_apply_urls.py"
)
hv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hv)  # type: ignore[union-attr]

hv.load_builtins()  # register providers so iter_providers()/matches() resolution works


def test_resolve_ats_url_recognizes_boards_and_skips_others():
    assert hv.resolve_ats_url("https://boards.greenhouse.io/acme/jobs/9") == ("greenhouse", "acme")
    assert hv.resolve_ats_url("https://jobs.lever.co/stripe/abc") == ("lever", "stripe")
    # Aggregator / non-ATS URLs never resolve -> no false boards.
    assert hv.resolve_ats_url("https://remoteok.com/remote-jobs/123") is None
    assert hv.resolve_ats_url("https://www.themuse.com/jobs/x") is None
    assert hv.resolve_ats_url("") is None


def test_urls_to_candidates_filters_registry_and_dedups():
    pairs = [
        ("Acme", "https://boards.greenhouse.io/acme/jobs/1"),  # new -> keep
        ("Stripe", "https://jobs.lever.co/stripe/x"),  # new -> keep
        ("Acme", "https://boards.greenhouse.io/acme/jobs/2"),  # dup company in-batch -> skip
        ("Globex", "https://remoteok.com/remote-jobs/9"),  # non-ATS url -> skip
        ("Existing", "https://jobs.ashbyhq.com/existing/y"),  # already in registry -> skip
    ]
    seed_keys = {"existing"}
    cands = hv.urls_to_candidates(pairs, seed_keys)
    by_company = {c["company"]: c for c in cands}
    assert set(by_company) == {"acme", "stripe"}
    assert by_company["acme"]["ats"] == "greenhouse" and by_company["acme"]["token"] == "acme"
    assert by_company["stripe"]["ats"] == "lever"
    # candidate schema matches what build_registry consumes
    assert all(set(c) == {"company", "ats", "token", "domain"} for c in cands)
