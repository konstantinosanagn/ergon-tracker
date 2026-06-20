import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_index import publish_artifacts  # noqa: E402

from ergon_tracker.index.build import build_index  # noqa: E402
from ergon_tracker.models import JobPosting  # noqa: E402


def test_publish_writes_gz_and_manifest(tmp_path):
    src = tmp_path / "i.sqlite"
    build_index(
        [JobPosting.create(source="greenhouse", source_job_id="1", company="Co", title="Eng")],
        src,
        build_id="b1",
    )
    out = tmp_path / "dist"
    publish_artifacts(src, out, build_id="b1")
    man = json.loads((out / "manifest.json").read_text())
    assert man["build_id"] == "b1" and man["schema_version"] == 1
    raw = gzip.decompress((out / "index.sqlite.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == man["sha256"]


def test_append_history_accumulates(tmp_path):
    from build_index import append_history

    h = tmp_path / "runs" / "history.jsonl"
    append_history(h, {"build_id": "b1", "total_jobs": 10})
    append_history(h, {"build_id": "b2", "total_jobs": 12})
    import json

    rows = [json.loads(line) for line in h.read_text().splitlines()]
    assert [r["build_id"] for r in rows] == ["b1", "b2"]


def test_build_and_publish_shards_gzips(tmp_path):
    from build_index import build_and_publish_shards

    from ergon_tracker.models import JobPosting

    jobs = [
        JobPosting.create(
            source="greenhouse",
            source_job_id=str(i),
            company=f"Co{i}",
            title="Engineer",
            sector=("Fintech" if i % 2 else None),
        )
        for i in range(4)
    ]
    n = build_and_publish_shards(jobs, tmp_path, build_id="b1")
    assert n == 2  # fintech + unknown
    assert (tmp_path / "shards.json").exists()
    gzs = {f.name for f in tmp_path.glob("shard-*.sqlite.gz")}
    assert gzs == {"shard-fintech.sqlite.gz", "shard-unknown.sqlite.gz"}


def test_new_boards_selects_unseen_and_caps():
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "_bi", pathlib.Path(__file__).parent.parent / "scripts" / "build_index.py"
    )
    bi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bi)
    from ergon_tracker.index.scheduler import BoardState

    items = [
        ("a", {"ats": "greenhouse", "token": "acme"}),
        ("b", {"ats": "lever", "token": "beta"}),
        ("c", {"ats": "ashby", "token": "gamma"}),
        ("d", {"ats": None, "token": None}),  # not crawlable -> ignored
    ]
    # 'a' already has state -> only b,c are new
    seen = {BoardState(provider="greenhouse", token="acme").key: object()}
    new = bi._new_boards(items, seen)
    tokens = {e["token"] for _, e in new}
    assert tokens == {"beta", "gamma"}
    # cap is respected
    assert len(bi._new_boards(items, {}, cap=1)) == 1


def test_deltas_window_accumulates_contiguous_chain_across_builds(tmp_path):
    import importlib.util
    import json
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "_bi2", pathlib.Path(__file__).parent.parent / "scripts" / "build_index.py"
    )
    bi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bi)
    from ergon_tracker.index.build import build_index
    from ergon_tracker.models import JobPosting

    def _job(sid, title):
        return JobPosting.create(source="greenhouse", source_job_id=sid, company="Co", title=title)

    out = tmp_path / "dist"
    out.mkdir()
    b1, b2, b3 = (tmp_path / f"b{i}.sqlite" for i in (1, 2, 3))
    build_index([_job("1", "Backend Engineer")], b1, build_id="build-1")
    build_index(
        [_job("1", "Backend Engineer"), _job("2", "Frontend Engineer")], b2, build_id="build-2"
    )
    build_index(
        [_job("1", "Backend Engineer"), _job("2", "Frontend Engineer"), _job("3", "ML Engineer")],
        b3,
        build_id="build-3",
    )

    bi.build_and_publish_delta(b1, b2, out, build_id="build-2")
    bi.build_and_publish_delta(b2, b3, out, build_id="build-3")

    window = json.loads((out / "deltas.json").read_text())["deltas"]
    # two entries forming a contiguous build-1 -> build-2 -> build-3 chain
    assert [(d["from_build_id"], d["to_build_id"]) for d in window] == [
        ("build-1", "build-2"),
        ("build-2", "build-3"),
    ]
    # each entry's per-build chain file was actually written
    for d in window:
        assert (out / d["file"]).exists()
    # the generic 1-behind delta points at the latest step
    assert json.loads((out / "manifest-delta.json").read_text())["to_build_id"] == "build-3"
