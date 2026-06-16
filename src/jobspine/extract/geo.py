"""Geo normalization (rules baseline): fill city/region/country/remote from a location string.

Geo is handled as a per-``Location`` normalizer rather than a posting-level FieldExtractor,
because it refines existing ``Location`` objects in place.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib.resources import files

from ..models import Location

__all__ = ["normalize_geo"]

# Country aliases -> canonical name (extend freely).
_COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "united kingdom": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "uae": "United Arab Emirates",
}
_COUNTRY_NAMES = {
    "united states",
    "united kingdom",
    "canada",
    "germany",
    "france",
    "spain",
    "italy",
    "netherlands",
    "ireland",
    "india",
    "australia",
    "singapore",
    "japan",
    "china",
    "brazil",
    "mexico",
    "poland",
    "sweden",
    "switzerland",
    "portugal",
    "israel",
    "south korea",
    "new zealand",
    "austria",
    "belgium",
    "denmark",
    "norway",
    "finland",
    "czech republic",
    "romania",
    "ukraine",
    "argentina",
    "chile",
    "colombia",
    "philippines",
    "indonesia",
    "vietnam",
    "thailand",
    "malaysia",
    "south africa",
    "nigeria",
    "egypt",
    "turkey",
    "greece",
    "hungary",
    "united arab emirates",
}
for _name in _COUNTRY_NAMES:
    _COUNTRY_ALIASES.setdefault(_name, _name.title())

_US_STATES = {
    "al",
    "ak",
    "az",
    "ar",
    "ca",
    "co",
    "ct",
    "de",
    "fl",
    "ga",
    "hi",
    "id",
    "il",
    "in",
    "ia",
    "ks",
    "ky",
    "la",
    "me",
    "md",
    "ma",
    "mi",
    "mn",
    "ms",
    "mo",
    "mt",
    "ne",
    "nv",
    "nh",
    "nj",
    "nm",
    "ny",
    "nc",
    "nd",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "vt",
    "va",
    "wa",
    "wv",
    "wi",
    "wy",
    "dc",
}


# Full US state names -> US (note: "georgia"/"washington"/"new york" default to the US state).
_US_STATE_NAMES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
}

# Noise tokens to drop from ATS location strings before matching.
_NOISE_RE = re.compile(
    r"\s*\(.*?\)"
    r"|\b(remote|hybrid|on-?site|locations?|metropolitan area|metro area|greater area"
    r"|bay area|area|region|multiple|various)\b",
    re.IGNORECASE,
)
_LEADING_COUNT_RE = re.compile(r"^\d+\s+")


@lru_cache(maxsize=1)
def _cities() -> dict[str, str]:
    """Lowercased city -> canonical country (bundled gazetteer). Tolerant if missing."""
    try:
        text = (files("jobspine.registry.data") / "cities.json").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return {}
    data = json.loads(text)
    return {k.lower(): v for k, v in data.get("cities", {}).items()}


def _clean(segment: str) -> str:
    s = _LEADING_COUNT_RE.sub("", segment)
    s = _NOISE_RE.sub("", s)
    s = re.sub(r"(?i)^greater\s+", "", s)
    return s.strip(" -,.").strip()


def _has_alpha(s: str) -> bool:
    return any(ch.isalpha() for ch in s)


def normalize_geo(loc: Location) -> Location:
    """Deterministically fill ``city``/``region``/``country`` from ``raw`` (in place).

    All-deterministic: split on separators, strip ATS noise, then resolve country by
    (1) explicit country token, (2) US state name/abbrev, (3) city -> country gazetteer.
    """
    if not loc.raw:
        return loc
    raw = loc.raw.strip()
    if "remote" in raw.lower():
        loc.is_remote = True
    cleaned = re.sub(r"\s+[-–—]\s+", ",", raw)
    segments = [c for c in (_clean(s) for s in re.split(r"[,/|]", cleaned)) if c]
    if not segments:
        return loc

    cities = _cities()

    if loc.country is None:
        for seg in reversed(segments):
            low = seg.lower()
            if low in _COUNTRY_ALIASES:
                loc.country = _COUNTRY_ALIASES[low]
                break
            if low in _US_STATES or low in _US_STATE_NAMES:
                loc.country = "United States"
                if loc.region is None:
                    loc.region = seg if low in _US_STATE_NAMES else seg.upper()
                break
            for tok in re.split(r"[-\s]+", low):
                if tok in _COUNTRY_ALIASES:
                    loc.country = _COUNTRY_ALIASES[tok]
                    break
                if tok in _US_STATES:
                    loc.country = "United States"
                    break
            if loc.country is not None:
                break

    if loc.country is None:
        for seg in segments:
            country = cities.get(seg.lower())
            if country:
                loc.country = country
                if loc.city is None:
                    loc.city = seg
                break

    if loc.city is None:
        for seg in segments:
            low = seg.lower()
            if low in _COUNTRY_ALIASES or low in _US_STATES or low in _US_STATE_NAMES:
                continue
            if not _has_alpha(seg) or "remote" in low:
                continue
            loc.city = seg
            break
    return loc
