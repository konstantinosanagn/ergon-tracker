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
            {"build_id": "b1", "sha256": hashlib.sha256(raw).hexdigest(),
             "bytes": len(raw), "schema_version": 1}
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
