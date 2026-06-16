"""Canonical data models for jobspine — the FROZEN CONTRACT all providers normalize to.

Every provider produces ``RawJob`` from its source, then maps it into a ``JobPosting``.
Missing fields are ``None`` (or an ``UNKNOWN`` enum) — never invented.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RemoteType",
    "EmploymentType",
    "SalaryInterval",
    "Location",
    "Salary",
    "RawJob",
    "Provenance",
    "JobPosting",
    "SearchQuery",
    "SourceHealth",
    "SearchResult",
    "make_job_id",
]


class RemoteType(str, Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    OTHER = "other"
    UNKNOWN = "unknown"


class SalaryInterval(str, Enum):
    YEAR = "year"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    HOUR = "hour"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_job_id(source: str, source_job_id: str) -> str:
    """Stable, short id derived from (source, source_job_id)."""
    return hashlib.sha1(f"{source}:{source_job_id}".encode()).hexdigest()[:16]


class Location(BaseModel):
    city: str | None = None
    region: str | None = None
    country: str | None = None
    raw: str | None = None
    is_remote: bool = False

    def as_text(self) -> str:
        parts = [p for p in (self.city, self.region, self.country) if p]
        return ", ".join(parts) if parts else (self.raw or "")


class Salary(BaseModel):
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    interval: SalaryInterval | None = None


class RawJob(BaseModel):
    """Pre-normalization container: exactly what a source returned for one posting."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: str
    source_job_id: str
    company: str
    token: str | None = None
    url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=_utcnow)


class Provenance(BaseModel):
    """A record of one source that yielded a (possibly merged) posting."""

    source: str
    source_job_id: str
    apply_url: str | None = None
    fetched_at: datetime = Field(default_factory=_utcnow)


class JobPosting(BaseModel):
    """The canonical, normalized posting returned to users."""

    id: str
    source: str
    source_job_id: str
    company: str
    company_domain: str | None = None
    title: str
    description_text: str | None = None
    description_html: str | None = None
    locations: list[Location] = Field(default_factory=list)
    remote: RemoteType = RemoteType.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    department: str | None = None
    salary: Salary | None = None
    apply_url: str | None = None
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source: str,
        source_job_id: str | int,
        company: str,
        title: str,
        fetched_at: datetime | None = None,
        apply_url: str | None = None,
        **fields: Any,
    ) -> JobPosting:
        """Ergonomic constructor for providers.

        Auto-fills ``id`` and a default single-entry ``provenance`` so normalize() code stays
        short and consistent. Pass any other ``JobPosting`` field via kwargs.
        """
        sid = str(source_job_id)
        fetched = fetched_at or _utcnow()
        provenance = fields.pop("provenance", None) or [
            Provenance(source=source, source_job_id=sid, apply_url=apply_url, fetched_at=fetched)
        ]
        return cls(
            id=make_job_id(source, sid),
            source=source,
            source_job_id=sid,
            company=company,
            title=title,
            apply_url=apply_url,
            provenance=provenance,
            **fields,
        )


class SearchQuery(BaseModel):
    """A unified query. ``matches()`` is the client-side filter applied to sources that have
    no server-side keyword search (i.e. most ATS feeds)."""

    keywords: str | None = None
    location: str | None = None
    remote: bool | None = None
    employment_type: EmploymentType | None = None
    posted_after: datetime | None = None
    limit: int | None = None
    companies: list[str] | None = None
    sources: list[str] | None = None

    def matches(self, job: JobPosting) -> bool:
        if self.keywords:
            haystack = " ".join(
                filter(
                    None,
                    [job.title, job.department, job.company, job.description_text or ""],
                )
            ).lower()
            if not all(tok in haystack for tok in self.keywords.lower().split()):
                return False

        if self.location:
            loc_text = " ".join(loc.as_text() for loc in job.locations).lower()
            if self.location.lower() not in loc_text:
                return False

        if self.remote is True:
            is_remote = job.remote in (RemoteType.REMOTE, RemoteType.HYBRID) or any(
                loc.is_remote for loc in job.locations
            )
            # Keep UNKNOWN-remote jobs only when no location constraint contradicts it.
            if not is_remote and job.remote != RemoteType.UNKNOWN:
                return False

        if self.employment_type and job.employment_type not in (
            self.employment_type,
            EmploymentType.UNKNOWN,
        ):
            return False

        return not (
            self.posted_after is not None
            and job.posted_at is not None
            and job.posted_at < self.posted_after
        )


class SourceHealth(BaseModel):
    """Per-source outcome of a search. Surfaced so callers never see a silent empty result."""

    source: str
    ok: bool
    count: int = 0
    error: str | None = None
    elapsed_ms: int = 0
    truncated: bool = False


class SearchResult(BaseModel):
    jobs: list[JobPosting] = Field(default_factory=list)
    health: list[SourceHealth] = Field(default_factory=list)

    def __iter__(self) -> Iterator[JobPosting]:  # type: ignore[override]
        return iter(self.jobs)

    def __len__(self) -> int:
        return len(self.jobs)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [j.model_dump(mode="json") for j in self.jobs]

    def to_pandas(self) -> Any:  # optional dep, dynamic return type
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ImportError("DataFrame export needs: pip install 'jobspine[pandas]'") from exc
        return pd.DataFrame(self.to_dicts())

    def to_polars(self) -> Any:  # optional dep, dynamic return type
        try:
            import polars as pl
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ImportError("DataFrame export needs: pip install 'jobspine[polars]'") from exc
        return pl.DataFrame(self.to_dicts())

    @property
    def ok_sources(self) -> list[str]:
        return [h.source for h in self.health if h.ok]

    @property
    def failed_sources(self) -> list[SourceHealth]:
        return [h for h in self.health if not h.ok]
