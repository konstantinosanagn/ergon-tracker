"""Build a SQLite/FTS5 index file from canonical JobPostings (deterministic, integrity-checked)."""

from __future__ import annotations

from pathlib import Path

from ..canonicalize import aggregate_companies
from ..dedup import deduplicate
from ..models import JobPosting
from .db import connect, fresh_db
from .mapping import to_row

_JOB_COLS = (  # noqa: SIM905 - space-delimited string is far more readable than a 40-item list
    "id content_hash company_key source company company_domain title department role_family "
    "location city country remote level employment_type sector salary_min salary_max "
    "salary_currency salary_interval salary_annual years_min years_max visa_sponsor "
    "visa_last_filed sponsorship_offered apply_url listing_url board_token posted_at updated_at "
    "closes_at status first_seen last_seen expired_at expiry_reason fetched_at build_id snippet"
).split()


class IndexBuildError(RuntimeError):
    pass


def build_index(jobs: list[JobPosting], path: Path | str, *, build_id: str) -> int:
    """Dedup -> write companies + jobs + provenance + FTS + meta. Returns row count."""
    deduped = deduplicate(jobs)
    deduped.sort(key=lambda j: j.id)  # deterministic order
    fresh_db(path)
    con = connect(path)
    try:
        companies = aggregate_companies(deduped)
        con.executemany(
            "INSERT INTO companies(company_key,display_name,domain,primary_ats,board_token,"
            "sector,h1b_sponsor,h1b_last_filed,open_roles,first_seen,last_seen) "
            "VALUES(:company_key,:display_name,:domain,:primary_ats,:board_token,:sector,"
            ":h1b_sponsor,:h1b_last_filed,:open_roles,:first_seen,:last_seen)",
            [{**c.model_dump(), "h1b_sponsor": 1 if c.h1b_sponsor else None} for c in companies],
        )
        placeholders = ",".join(":" + c for c in _JOB_COLS)
        con.executemany(
            f"INSERT INTO jobs({','.join(_JOB_COLS)}) VALUES({placeholders})",
            [to_row(j, build_id=build_id) for j in deduped],
        )
        con.executemany(
            "INSERT OR IGNORE INTO job_sources(job_id,source,source_job_id,apply_url,fetched_at) "
            "VALUES(?,?,?,?,?)",
            [
                (j.id, p.source, p.source_job_id, p.apply_url, p.fetched_at.isoformat())
                for j in deduped
                for p in j.provenance
            ],
        )
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('build_id',?)", (build_id,))
        con.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('row_count',?)", (str(len(deduped)),)
        )
        # External-content FTS5 isn't auto-populated by inserts into `jobs`; rebuild from content,
        # then optimize (merge b-trees) for faster/smaller queries.
        con.execute("INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild')")
        con.execute("INSERT INTO jobs_fts(jobs_fts) VALUES('optimize')")
        con.commit()
        con.execute("ANALYZE")
        con.execute("VACUUM")
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise IndexBuildError(f"integrity_check failed: {ok}")
        return len(deduped)
    finally:
        con.close()
