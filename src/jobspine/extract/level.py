"""Job level / seniority extraction (deterministic rules baseline).

The classifier is a strictly ordered set of dictionary/regex rules. The strongest
signal must come first, because the first match wins. Key design points:

* Explicit seniority words (senior/staff/principal/lead/junior/intern) beat IC
  "manager" head-nouns and numeric ladder tokens, e.g. "Senior Project Manager"
  resolves to SENIOR rather than MANAGER.
* "<function> Manager" titles where the function is an individual-contributor
  function (product, account, project, ...) are NOT people-management roles, so
  they are intentionally left to fall through (typically UNKNOWN).
* "Head of X" and "(Assistant) Vice President"/AVP are director-level, while
  EXECUTIVE is reserved for Chief/C?O/President/VP/SVP/EVP.
"""

from __future__ import annotations

import re

from ..models import JobLevel
from .base import ExtractInput, register_extractor

__all__ = ["infer_level", "LevelExtractor"]

# --- Individual-contributor "Manager" functions -----------------------------
# "<function> Manager/Mgr" is an IC role title, not a people-management level.
# Matched only when the function word sits immediately before manager/mgr.
_IC_MANAGER = re.compile(
    r"\b(?:"
    r"product marketing|customer success|"
    r"product|account|project|program|marketing|community|"
    r"channel|category|brand|growth|partner|sales"
    r")\s+(?:managers?|mgr)\b",
    re.I,
)

# True people-management signal (manager/supervisor/people lead).
_PEOPLE_MANAGER = re.compile(r"\b(?:managers?|mgr|supervisors?|people lead)\b", re.I)

_INTERN = re.compile(r"\b(?:intern|internship|co-?op|apprentice|werk?student)\b", re.I)

# Director runs BEFORE executive so "Head of X" and "(Assistant) Vice President"
# / AVP resolve to director rather than executive.
_DIRECTOR = re.compile(
    r"\b(?:director|head of|avp|assistant vice president)\b",
    re.I,
)

_EXECUTIVE = re.compile(
    r"\b(?:chief|c[etfoi]o|cxo|cmo|cpo|svp|evp|vp|vice president|president)\b",
    re.I,
)

_PRINCIPAL = re.compile(r"\b(?:principal|distinguished|fellow)\b", re.I)
# "Member of Technical Staff" / MTS is an IC ladder, NOT staff-level. Handle before _STAFF so
# "Technical Staff" doesn't trip the plain staff rule.
_MTS = re.compile(r"\bmember of technical staff\b|\bmts\b", re.I)
_STAFF = re.compile(r"\bstaff\b", re.I)
_LEAD = re.compile(r"\b(?:lead|tech lead|team lead)\b", re.I)
# "Mid / Senior" combos resolve to mid (lower bound), handled before SENIOR.
_MID_SENIOR = re.compile(r"\bmid\s*/\s*senior\b", re.I)
_SENIOR = re.compile(r"\b(?:senior|sr\.?|snr)\b", re.I)
_JUNIOR = re.compile(r"\b(?:junior|jr\.?|jnr)\b", re.I)

# Explicit entry-level signals, including narrow sales-development titles.
# "Business/Partner Development Representative" are their own sales functions and
# are deliberately excluded (negative lookbehind) so they stay UNKNOWN.
_ENTRY = re.compile(
    r"\b(?:entry[- ]level|new ?grad|graduate|associate|trainee|early[- ]career)\b"
    r"|(?<!business )(?<!partner )\bdevelopment representative\b"
    r"|\bsales development\b"
    r"|\bsdr\b",
    re.I,
)

# --- Numeric / explicit-level tokens ----------------------------------------
_TOK_EARLY = re.compile(r"\(\s*early\b|\bearly[- ]career\b", re.I)
_TOK_MID = re.compile(r"\(\s*mid\b|\bmid[- ]level\b", re.I)
# Ladder codes like L5 / E4 / P3 / IC6 (case-sensitive to avoid false hits).
_LADDER = re.compile(r"\b(?:IC|[LEP])-?([1-9])\b")
# Roman/arabic suffix levels (word boundaries; roman is case-sensitive so "II"
# is never matched inside lowercase words).
_ROMAN_SENIOR = re.compile(r"\b(?:III|IV)\b")
_ROMAN_MID = re.compile(r"\bII\b")
_ROMAN_ENTRY = re.compile(r"\bI\b")
_ARABIC = re.compile(r"\b([1-4])\b")

_LADDER_MAP: dict[int, JobLevel] = {
    1: JobLevel.ENTRY,
    2: JobLevel.ENTRY,
    3: JobLevel.MID,
    4: JobLevel.MID,
    5: JobLevel.SENIOR,
    6: JobLevel.STAFF,
    7: JobLevel.PRINCIPAL,
    8: JobLevel.PRINCIPAL,
    9: JobLevel.PRINCIPAL,
}

_ARABIC_MAP: dict[int, JobLevel] = {
    1: JobLevel.ENTRY,
    2: JobLevel.MID,
    3: JobLevel.SENIOR,
    4: JobLevel.SENIOR,
}


def _parse_level_token(title: str) -> JobLevel | None:
    """Parse an explicit/numeric level token (returns None when absent)."""
    if _TOK_EARLY.search(title):
        return JobLevel.ENTRY
    if _TOK_MID.search(title):
        return JobLevel.MID
    m = _LADDER.search(title)
    if m:
        return _LADDER_MAP[int(m.group(1))]
    if _ROMAN_SENIOR.search(title):
        return JobLevel.SENIOR
    if _ROMAN_MID.search(title):
        return JobLevel.MID
    if _ROMAN_ENTRY.search(title):
        return JobLevel.ENTRY
    m = _ARABIC.search(title)
    if m:
        return _ARABIC_MAP[int(m.group(1))]
    return None


def infer_level(title: str) -> JobLevel:
    """Infer seniority from a job title. Returns UNKNOWN when no signal is present."""
    t = title or ""

    if _INTERN.search(t):
        return JobLevel.INTERN
    if _DIRECTOR.search(t):
        return JobLevel.DIRECTOR
    if _EXECUTIVE.search(t):
        return JobLevel.EXECUTIVE
    # People-management manager wins over seniority words ("Senior Manager" ->
    # manager) but IC "<function> Manager" titles are excluded here.
    if _PEOPLE_MANAGER.search(t) and not _IC_MANAGER.search(t):
        return JobLevel.MANAGER
    if _PRINCIPAL.search(t):
        return JobLevel.PRINCIPAL
    if _MTS.search(t):
        # IC level: default mid, but honor an explicit senior qualifier.
        return JobLevel.SENIOR if _SENIOR.search(t) else JobLevel.MID
    if _STAFF.search(t):
        return JobLevel.STAFF
    if _LEAD.search(t):
        return JobLevel.LEAD
    if _MID_SENIOR.search(t):
        return JobLevel.MID
    if _SENIOR.search(t):
        return JobLevel.SENIOR
    if _JUNIOR.search(t):
        return JobLevel.JUNIOR
    if _ENTRY.search(t):
        return JobLevel.ENTRY

    token = _parse_level_token(t)
    if token is not None:
        return token
    return JobLevel.UNKNOWN


class LevelExtractor:
    name = "level"

    def extract(self, inp: ExtractInput) -> JobLevel:
        return infer_level(inp.title)


register_extractor(LevelExtractor())
