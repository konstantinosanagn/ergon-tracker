import gzip
import hashlib
import json

from ergon_tracker.index.backend import SqliteIndexBackend
from ergon_tracker.index.build import build_index
from ergon_tracker.index.cache import IndexCache
from ergon_tracker.models import JobPosting


def _publish(remote_dir, tmp_path):
    src = tmp_path / "src.sqlite"
    build_index(
        [JobPosting.create(source="greenhouse", source_job_id="1", company="Co", title="Eng")],
        src,
        build_id="b1",
    )
    raw = src.read_bytes()
    (remote_dir / "index.sqlite.gz").write_bytes(gzip.compress(raw))
    (remote_dir / "manifest.json").write_text(
        json.dumps(
            {
                "build_id": "b1",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "schema_version": 1,
            }
        )
    )


def test_cache_downloads_verifies_and_opens(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    _publish(remote, tmp_path)
    cache = IndexCache(base_url=remote.as_uri(), cache_dir=tmp_path / "cache")
    path = cache.ensure_fresh()
    assert path is not None and path.exists()
    assert SqliteIndexBackend(path).available() is True


def test_cache_rejects_corrupt_download(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    _publish(remote, tmp_path)
    (remote / "manifest.json").write_text(
        json.dumps({"build_id": "b1", "sha256": "0" * 64, "bytes": 1, "schema_version": 1})
    )
    cache = IndexCache(base_url=remote.as_uri(), cache_dir=tmp_path / "cache")
    assert cache.ensure_fresh() is None


def test_cache_rejects_future_schema_version(tmp_path):
    # Forward-compat: when a future build bumps SCHEMA_VERSION, an older client must fall back
    # to live (None), never crash on an index it can't read.
    remote = tmp_path / "remote"
    remote.mkdir()
    _publish(remote, tmp_path)
    man = json.loads((remote / "manifest.json").read_text())
    man["schema_version"] = 999  # newer than this client understands
    (remote / "manifest.json").write_text(json.dumps(man))
    cache = IndexCache(base_url=remote.as_uri(), cache_dir=tmp_path / "cache")
    assert cache.ensure_fresh() is None  # graceful live fallback, no exception


def test_shardcache_rejects_future_schema_version(tmp_path):
    import gzip as _gz

    from ergon_tracker.index.build import build_sharded_index
    from ergon_tracker.index.cache import ShardCache
    from ergon_tracker.models import SearchQuery

    src = tmp_path / "build"
    build_sharded_index(
        [
            JobPosting.create(
                source="greenhouse",
                source_job_id="1",
                company="Stripe",
                title="Eng",
                sector="Fintech",
            )
        ],
        src,
        build_id="b1",
    )
    remote = tmp_path / "remote"
    remote.mkdir()
    man = json.loads((src / "shards.json").read_text())
    man["schema_version"] = 999
    (remote / "shards.json").write_text(json.dumps(man))
    for f in src.glob("shard-*.sqlite"):
        (remote / (f.name + ".gz")).write_bytes(_gz.compress(f.read_bytes()))
    cache = ShardCache(base_url=remote.as_uri(), cache_dir=tmp_path / "cache")
    assert cache.ensure(SearchQuery(sector="Fintech")) is None  # graceful fallback


def _job(sid, company, title, **kw):
    from ergon_tracker.models import Location, RemoteType

    return JobPosting.create(
        source="greenhouse",
        source_job_id=sid,
        company=company,
        title=title,
        locations=[Location(raw="Remote", is_remote=True)],
        remote=RemoteType.REMOTE,
        **kw,
    )


def test_cache_applies_delta_instead_of_full_download(tmp_path):
    # Returning user one build behind gets the new state via a small delta, NOT a full re-download.
    from ergon_tracker.index.build import build_delta, build_index

    remote = tmp_path / "remote"
    remote.mkdir()
    cache_dir = tmp_path / "cache"

    # Build b1, publish full, prime the local cache to b1.
    b1 = tmp_path / "b1.sqlite"
    build_index([_job("1", "Stripe", "Backend Engineer")], b1, build_id="b1")
    raw1 = b1.read_bytes()
    (remote / "index.sqlite.gz").write_bytes(gzip.compress(raw1))
    (remote / "manifest.json").write_text(
        json.dumps(
            {
                "build_id": "b1",
                "sha256": hashlib.sha256(raw1).hexdigest(),
                "bytes": len(raw1),
                "schema_version": 1,
            }
        )
    )
    cache = IndexCache(base_url=remote.as_uri(), cache_dir=cache_dir)
    assert cache.ensure_fresh() is not None  # now cached at b1

    # Build b2 (adds a job), publish its manifest + a b1->b2 delta, but make the FULL file
    # un-downloadable so success can ONLY come from the delta path.
    b2 = tmp_path / "b2.sqlite"
    build_index(
        [_job("1", "Stripe", "Backend Engineer"), _job("2", "Ramp", "Founding Engineer")],
        b2,
        build_id="b2",
    )
    raw2 = b2.read_bytes()
    (remote / "manifest.json").write_text(
        json.dumps(
            {
                "build_id": "b2",
                "sha256": hashlib.sha256(raw2).hexdigest(),
                "bytes": len(raw2),
                "schema_version": 1,
            }
        )
    )
    (remote / "index.sqlite.gz").write_bytes(b"corrupt-not-gzip")  # full path must NOT be used
    delta = tmp_path / "delta.sqlite"
    info = build_delta(b1, b2, delta, from_build_id="b1", to_build_id="b2")
    assert info["upserts"] == 1
    draw = delta.read_bytes()
    (remote / "index-delta.sqlite.gz").write_bytes(gzip.compress(draw))
    (remote / "manifest-delta.json").write_text(
        json.dumps(
            {
                "from_build_id": "b1",
                "to_build_id": "b2",
                "sha256": hashlib.sha256(draw).hexdigest(),
                "bytes": len(draw),
                "schema_version": 1,
            }
        )
    )

    path = cache.ensure_fresh()  # must apply the delta (full file is corrupt)
    assert path is not None
    backend = SqliteIndexBackend(path)
    from ergon_tracker.models import SearchQuery

    titles = {j.title for j in backend.search(SearchQuery(keywords="engineer", limit=10))}
    assert "Founding Engineer" in titles  # the b2 row arrived via the delta
    assert json.loads((cache_dir / "manifest.json").read_text())["build_id"] == "b2"


def test_cache_falls_back_to_full_when_delta_base_mismatches(tmp_path):
    # Local is at b1 but the only delta bridges b0->b2: must ignore it and full-download b2.
    from ergon_tracker.index.build import build_delta, build_index

    remote = tmp_path / "remote"
    remote.mkdir()
    cache_dir = tmp_path / "cache"
    b1 = tmp_path / "b1.sqlite"
    build_index([_job("1", "Stripe", "Backend Engineer")], b1, build_id="b1")
    raw1 = b1.read_bytes()
    (remote / "index.sqlite.gz").write_bytes(gzip.compress(raw1))
    (remote / "manifest.json").write_text(
        json.dumps(
            {
                "build_id": "b1",
                "sha256": hashlib.sha256(raw1).hexdigest(),
                "bytes": len(raw1),
                "schema_version": 1,
            }
        )
    )
    cache = IndexCache(base_url=remote.as_uri(), cache_dir=cache_dir)
    assert cache.ensure_fresh() is not None  # cached at b1

    b2 = tmp_path / "b2.sqlite"
    build_index(
        [_job("1", "Stripe", "Backend Engineer"), _job("2", "Ramp", "Founding Engineer")],
        b2,
        build_id="b2",
    )
    raw2 = b2.read_bytes()
    (remote / "index.sqlite.gz").write_bytes(gzip.compress(raw2))  # full IS valid here
    (remote / "manifest.json").write_text(
        json.dumps(
            {
                "build_id": "b2",
                "sha256": hashlib.sha256(raw2).hexdigest(),
                "bytes": len(raw2),
                "schema_version": 1,
            }
        )
    )
    # a delta that does NOT bridge b1 (claims b0->b2)
    b0 = tmp_path / "b0.sqlite"
    build_index([_job("9", "Zzz", "Old Role")], b0, build_id="b0")
    delta = tmp_path / "delta.sqlite"
    build_delta(b0, b2, delta, from_build_id="b0", to_build_id="b2")
    draw = delta.read_bytes()
    (remote / "index-delta.sqlite.gz").write_bytes(gzip.compress(draw))
    (remote / "manifest-delta.json").write_text(
        json.dumps(
            {
                "from_build_id": "b0",
                "to_build_id": "b2",
                "sha256": hashlib.sha256(draw).hexdigest(),
                "bytes": len(draw),
                "schema_version": 1,
            }
        )
    )
    path = cache.ensure_fresh()  # delta base mismatch -> full download of b2
    assert path is not None
    from ergon_tracker.models import SearchQuery

    titles = {
        j.title for j in SqliteIndexBackend(path).search(SearchQuery(keywords="engineer", limit=10))
    }
    assert "Founding Engineer" in titles and "Old Role" not in titles  # got b2, not the b0 delta
