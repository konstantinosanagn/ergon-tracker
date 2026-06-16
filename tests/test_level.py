"""Tests for deterministic job-level extraction."""

from __future__ import annotations

import pytest

from jobspine.extract.level import infer_level
from jobspine.models import JobLevel


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # --- IC "<function> Manager" titles are NOT people-management -------
        ("Product Manager", JobLevel.UNKNOWN),
        ("Product Manager, Platform", JobLevel.UNKNOWN),
        ("Product Marketing Manager", JobLevel.UNKNOWN),
        ("Technical Customer Success Manager, NA (remote)", JobLevel.UNKNOWN),
        ("Territory Account Manager (Nashville)", JobLevel.UNKNOWN),
        ("Logistics Product Manager, MENA", JobLevel.UNKNOWN),
        # --- True people-management managers -------------------------------
        ("Engineering Manager", JobLevel.MANAGER),
        ("Manager, Engineering", JobLevel.MANAGER),
        ("Engineering Manager, Payments", JobLevel.MANAGER),
        ("People Manager", JobLevel.MANAGER),
        ("Events Manager", JobLevel.MANAGER),
        ("Senior Manager", JobLevel.MANAGER),
        ("Senior Manager, Event Technology", JobLevel.MANAGER),
        # --- Explicit seniority beats IC manager / numeric tokens ----------
        ("Senior Project Manager", JobLevel.SENIOR),
        ("Senior Project Manager - Freelance", JobLevel.SENIOR),
        ("Senior Product Marketing Manager", JobLevel.SENIOR),
        # --- Numeric / explicit level tokens -------------------------------
        ("Data Scientist II", JobLevel.MID),
        ("Data Scientist II - Platform Mission", JobLevel.MID),
        ("SDE II", JobLevel.MID),
        ("Engineer III", JobLevel.SENIOR),
        ("Spacecraft RF Engineer (Mid)", JobLevel.MID),
        ("Thermal Engineer (Mid)", JobLevel.MID),
        ("Spacecraft Mechanical Engineer (Early)", JobLevel.ENTRY),
        ("Mid / Senior Software Engineer", JobLevel.MID),
        ("Software Engineer L5", JobLevel.SENIOR),
        # "Mid-Market" must NOT be read as mid-level.
        ("Mid-Market Account Exec", JobLevel.UNKNOWN),
        # --- Head of / AVP -> director; VP/Chief -> executive --------------
        ("Head of Growth", JobLevel.DIRECTOR),
        ("Head of Growth Marketing", JobLevel.DIRECTOR),
        ("Head of Development", JobLevel.DIRECTOR),
        ("AVP", JobLevel.DIRECTOR),
        ("Assistant Vice President - Development Marketing", JobLevel.DIRECTOR),
        ("Director of Engineering", JobLevel.DIRECTOR),
        ("VP", JobLevel.EXECUTIVE),
        ("VP Product, Core Products", JobLevel.EXECUTIVE),
        ("Chief Technology Officer", JobLevel.EXECUTIVE),
        # --- Sales-development roles -> entry ------------------------------
        ("SDR", JobLevel.ENTRY),
        ("Sales Development Representative", JobLevel.ENTRY),
        ("Bilingual Hybrid Development Representative (Thai)", JobLevel.ENTRY),
        ("Sales Development - Brazil", JobLevel.ENTRY),
        # ...but Business/Partner Development Representative stay unknown.
        ("Business Development Representative", JobLevel.UNKNOWN),
        ("Partner Development Representative | Financial Institutions", JobLevel.UNKNOWN),
        # --- Other anchors that must not regress ---------------------------
        ("Staff Engineer", JobLevel.STAFF),
        ("Senior Data Engineer", JobLevel.SENIOR),
        ("Junior Engineer", JobLevel.JUNIOR),
        ("Principal HPC Architect", JobLevel.PRINCIPAL),
        ("Lead Software Engineer", JobLevel.LEAD),
        ("Project Manager Intern", JobLevel.INTERN),
        ("Software Engineer", JobLevel.UNKNOWN),
    ],
)
def test_infer_level(title: str, expected: JobLevel) -> None:
    assert infer_level(title) == expected


def test_empty_title_is_unknown() -> None:
    assert infer_level("") == JobLevel.UNKNOWN
