import ergon_tracker.index.router as router
from ergon_tracker.index.backend import SqliteIndexBackend
from ergon_tracker.index.build import build_index
from ergon_tracker.models import JobLevel, JobPosting, SearchQuery


def test_router_uses_index_for_broad_query(tmp_path, monkeypatch):
    p = tmp_path / "i.sqlite"
    build_index(
        [JobPosting.create(source="greenhouse", source_job_id="1", company="Co",
                           title="Senior Backend Engineer", level=JobLevel.SENIOR)],
        p,
        build_id="b1",
    )
    monkeypatch.setattr(router, "_load_backend", lambda: SqliteIndexBackend(p))
    out = router.try_index(SearchQuery(keywords="backend", limit=5))
    assert out is not None and out[0].title == "Senior Backend Engineer"


def test_router_returns_none_for_targeted_query():
    assert router.try_index(SearchQuery(keywords="x", companies=["stripe.com"])) is None


def test_router_returns_none_when_index_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(router, "_load_backend", lambda: SqliteIndexBackend(tmp_path / "none.sqlite"))
    assert router.try_index(SearchQuery(keywords="x")) is None


def test_env_off_disables_index(monkeypatch):
    monkeypatch.setenv("ERGON_INDEX", "off")
    assert router.try_index(SearchQuery(keywords="x")) is None
