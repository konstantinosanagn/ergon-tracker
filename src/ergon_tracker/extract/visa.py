"""H-1B visa-sponsor signal — table-backed, from US DoL OFLC LCA disclosure data.

The Department of Labor publishes (free, official) quarterly disclosure files of every Labor
Condition Application — the petition an employer must file to hire an H-1B worker. An employer
appearing there with a *certified* LCA is a demonstrated visa sponsor. We distill that bulk data
offline (see ``scripts/build_h1b_sponsors.py``) into a compact set of normalized employer names
shipped as ``registry/data/h1b_sponsors.json``, and tag matching postings with ``visa_sponsor``.

Honesty note: this gives **positive** evidence only. A company *in* the set has sponsored H-1B
visas; a company *not* in it is ``unknown`` (the data is historical and name-matching is fuzzy),
never asserted as a non-sponsor. So we only ever set ``visa_sponsor = True``.

Matching is by normalized company name (``dedup.normalize_company``), since LCA employer names
("STRIPE, INC.") and posting company names ("Stripe") both collapse to the same key ("stripe").
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

from ..dedup import normalize_company

__all__ = ["SponsorIndex", "load_sponsor_index", "is_h1b_sponsor"]


class SponsorIndex:
    """Set of normalized employer names known to have certified H-1B LCAs."""

    def __init__(self, names: set[str]) -> None:
        self._names = names

    def is_sponsor(self, company: str | None) -> bool:
        if not company:
            return False
        return normalize_company(company) in self._names

    def __len__(self) -> int:
        return len(self._names)


@lru_cache(maxsize=1)
def load_sponsor_index() -> SponsorIndex:
    """Load the bundled H-1B sponsor set. Tolerant of a missing/empty file (feature no-ops)."""
    names: set[str] = set()
    try:
        text = (files("ergon_tracker.registry.data") / "h1b_sponsors.json").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return SponsorIndex(names)
    data = json.loads(text)
    # Accept either {"sponsors": ["name", ...]} or {"sponsors": {"name": count}}.
    sponsors = data.get("sponsors", [])
    names = set(sponsors.keys()) if isinstance(sponsors, dict) else set(sponsors)
    return SponsorIndex(names)


def is_h1b_sponsor(company: str | None) -> bool:
    """True iff ``company`` matches a known H-1B sponsor in the bundled index."""
    return load_sponsor_index().is_sponsor(company)
