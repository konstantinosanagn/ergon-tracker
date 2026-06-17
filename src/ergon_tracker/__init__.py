"""ergon_tracker — unified, reliable, typed job-fetching SDK."""

from __future__ import annotations

from .client import AsyncErgonTracker
from .exceptions import (
    ErgonTrackerError,
    FetchError,
    ProviderError,
    RateLimitError,
    ResolveError,
)
from .models import (
    EmploymentType,
    JobLevel,
    JobPosting,
    Location,
    Provenance,
    RawJob,
    RemoteType,
    Salary,
    SalaryInterval,
    SearchQuery,
    SearchResult,
    SourceHealth,
)
from .sync import ErgonTracker, search

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # clients
    "search",
    "ErgonTracker",
    "AsyncErgonTracker",
    # models
    "JobPosting",
    "SearchQuery",
    "SearchResult",
    "Salary",
    "SalaryInterval",
    "Location",
    "RawJob",
    "Provenance",
    "SourceHealth",
    "RemoteType",
    "EmploymentType",
    "JobLevel",
    # exceptions
    "ErgonTrackerError",
    "ProviderError",
    "FetchError",
    "RateLimitError",
    "ResolveError",
]
