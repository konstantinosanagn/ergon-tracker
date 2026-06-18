import json

from ergon_tracker.index.build import build_sharded_index, sector_slug
from ergon_tracker.index.db import connect
from ergon_tracker.models import JobPosting, Location, RemoteType


def _job(sid, company, title, sector=None):
    return JobPosting.create(
        source="greenhouse", source_job_id=sid, company=company, title=title, sector=sector,
        locations=[Location(raw="Remote", is_remote=True)], remote=RemoteType.REMOTE,
    )


def test_sector_slug():
    assert sector_slug("AI/ML") == "ai-ml"
    assert sector_slug("Fintech") == "fintech"
    assert sector_slug(None) == "unknown"
    assert sector_slug("") == "unknown"


def test_build_sharded_writes_one_shard_per_sector(tmp_path):
    jobs = [
        _job("1", "Stripe", "Backend Engineer", sector="Fintech"),
        _job("2", "Ramp", "Frontend Engineer", sector="Fintech"),
        _job("3", "Hugging Face", "ML Engineer", sector="AI/ML"),
        _job("4", "Acme", "Generalist", sector=None),
    ]
    manifest = build_sharded_index(jobs, tmp_path, build_id="b1")
    shards = manifest["shards"]
    assert set(shards) == {"fintech", "ai-ml", "unknown"}
    assert shards["fintech"]["rows"] == 2
    assert shards["ai-ml"]["rows"] == 1 and shards["unknown"]["rows"] == 1
    # rows sum to total
    assert sum(s["rows"] for s in shards.values()) == 4
    # manifest persisted + each shard file is a valid queryable index
    assert json.loads((tmp_path / "shards.json").read_text())["shards"].keys() == shards.keys()
    con = connect(tmp_path / "shard-fintech.sqlite", read_only=True)
    titles = {r[0] for r in con.execute("SELECT title FROM jobs")}
    assert titles == {"Backend Engineer", "Frontend Engineer"}
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert all("sha256" in s for s in shards.values())
