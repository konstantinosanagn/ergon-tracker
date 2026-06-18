"""Streaming/SQL-merge build: memory-bounded, parity with the in-memory build_index."""

from __future__ import annotations

from ergon_tracker.index.build import (
    append_jobs,
    build_index,
    build_index_incremental,
    build_index_streaming,
)
from ergon_tracker.index.db import connect
from ergon_tracker.models import JobLevel, JobPosting, Location, RemoteType


def _job(sid, company, title, **kw):
    return JobPosting.create(
        source=kw.pop("source", "greenhouse"), source_job_id=sid, company=company, title=title,
        locations=[Location(raw="Remote", is_remote=True)], remote=RemoteType.REMOTE, **kw,
    )


def _rows(path):
    con = connect(path, read_only=True)
    try:
        ids = {r[0] for r in con.execute("SELECT id FROM jobs")}
        companies = {r[0]: r[1] for r in con.execute("SELECT company_key, open_roles FROM companies")}
        n = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        return ids, companies, n
    finally:
        con.close()


def test_streaming_parity_with_build_index(tmp_path):
    jobs = [
        _job("1", "Stripe", "Backend Engineer", level=JobLevel.SENIOR, sector="Fintech"),
        _job("2", "Stripe", "Frontend Engineer", sector="Fintech"),
        _job("3", "OpenAI", "ML Engineer", sector="AI/ML"),
    ]
    a = tmp_path / "mem.sqlite"
    b = tmp_path / "stream.sqlite"
    build_index(jobs, a, build_id="b1")
    build_index_streaming([jobs[:2], jobs[2:]], b, build_id="b1")  # two batches

    ids_a, comp_a, n_a = _rows(a)
    ids_b, comp_b, n_b = _rows(b)
    assert ids_a == ids_b
    assert n_a == n_b == 3
    assert comp_a == comp_b  # company_key -> open_roles identical


def test_streaming_fts_queryable(tmp_path):
    p = tmp_path / "s.sqlite"
    build_index_streaming([[_job("1", "Stripe", "Senior Backend Engineer")]], p, build_id="b1")
    con = connect(p, read_only=True)
    try:
        hit = con.execute(
            "SELECT j.title FROM jobs j JOIN jobs_fts f ON j.rowid=f.rowid "
            "WHERE jobs_fts MATCH 'backend'"
        ).fetchone()
        assert hit and hit[0] == "Senior Backend Engineer"
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def test_append_jobs_exact_id_dedup(tmp_path):
    from ergon_tracker.index.db import fresh_db

    p = tmp_path / "d.sqlite"
    fresh_db(p)
    con = connect(p)
    con.execute("PRAGMA foreign_keys = OFF")  # companies aggregated later; see build_index_streaming
    try:
        j = _job("1", "Stripe", "Backend Engineer")
        assert append_jobs(con, [j], build_id="b1") == 1
        assert append_jobs(con, [j], build_id="b1") == 0  # same id ignored
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    finally:
        con.close()


def test_streaming_carry_forward_matches_incremental(tmp_path):
    # prev index has companies Stripe + Ramp; this run re-crawled only Stripe (crawled_keys).
    prev = tmp_path / "prev.sqlite"
    build_index(
        [_job("1", "Stripe", "Old Stripe Role"), _job("2", "Ramp", "Ramp Role")],
        prev, build_id="b0",
    )
    fresh = [_job("3", "Stripe", "New Stripe Role")]  # Stripe's board changed
    crawled = {"stripe"}

    # streaming path
    s = tmp_path / "stream.sqlite"
    build_index_streaming([fresh], s, build_id="b1", prev_db=prev, crawled_keys=crawled)
    # in-memory incremental path (the oracle)
    m = tmp_path / "mem.sqlite"
    build_index_incremental(prev, fresh, crawled, m, build_id="b1")

    ids_s, _, _ = _rows(s)
    ids_m, _, _ = _rows(m)
    # both: Ramp carried forward, Stripe replaced with the fresh role, old Stripe role dropped
    assert ids_s == ids_m
    companies_s = {r[0] for r in connect(s, read_only=True).execute("SELECT DISTINCT company FROM jobs")}
    assert companies_s == {"Stripe", "Ramp"}
    titles_s = {r[0] for r in connect(s, read_only=True).execute("SELECT title FROM jobs")}
    assert titles_s == {"New Stripe Role", "Ramp Role"}  # old Stripe role gone
