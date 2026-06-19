"""M1 build entry: crawl a bounded slice of the registry -> build index -> publish artifacts.

Usage:
  .venv/bin/python scripts/build_index.py --limit-companies 300 --out dist/
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ergon_tracker.index.build import build_index  # noqa: E402


def _gzip_file(src: Path, dst: Path) -> tuple[str, int]:
    """Stream-gzip ``src`` to ``dst`` in chunks; return (sha256 of RAW bytes, raw byte count).

    Avoids loading the whole (~1GB) file into memory — gzip.compress(read_bytes()) would spike
    ~2GB RAM at publish time. mtime=0 keeps the gz byte-stable for unchanged input.
    """
    h = hashlib.sha256()
    total = 0
    with (
        open(src, "rb") as f_in,
        open(dst, "wb") as raw_out,
        gzip.GzipFile(fileobj=raw_out, mode="wb", mtime=0) as f_out,
    ):
        while True:
            chunk = f_in.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            f_out.write(chunk)
    return h.hexdigest(), total


def publish_artifacts(db_path: Path, out_dir: Path, *, build_id: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sha, nbytes = _gzip_file(db_path, out_dir / "index.sqlite.gz")
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {"build_id": build_id, "schema_version": 1, "sha256": sha, "bytes": nbytes}
        )
    )


async def _crawl(limit_companies: int) -> list:
    """Bounded registry crawl: fetch N boards directly by their stored (ats, token).

    Bypasses resolve() (which is for arbitrary user domains/URLs) and reuses the providers +
    enrich + dedup, crash-isolated per board so one dead board never sinks the run.
    """
    import anyio

    from ergon_tracker.dedup import deduplicate
    from ergon_tracker.enrich import enrich_in_place
    from ergon_tracker.http import AsyncFetcher
    from ergon_tracker.models import SearchQuery
    from ergon_tracker.providers.base import get_provider, load_builtins
    from ergon_tracker.registry.store import SeedRegistry

    load_builtins()
    items = [
        (k, e)
        for k, e in list(SeedRegistry().all().items())[:limit_companies]
        if e.get("ats") and e.get("token")
    ]
    jobs: list = []

    async def grab(key: str, entry: dict, fetcher: AsyncFetcher) -> None:
        provider = get_provider(entry["ats"])
        if provider is None:
            return
        try:
            raws = await provider.fetch(entry["token"], SearchQuery(), fetcher)
        except Exception:  # noqa: BLE001 - dead/blocked board, skip
            return
        for raw in raws:
            try:
                job = provider.normalize(raw)
            except Exception:  # noqa: BLE001
                continue
            if entry.get("domain") and not job.company_domain:
                job.company_domain = entry["domain"]
            enrich_in_place(job, company_key=key)
            jobs.append(job)

    async with AsyncFetcher() as fetcher, anyio.create_task_group() as tg:
        for key, entry in items:
            tg.start_soon(grab, key, entry, fetcher)
    return deduplicate(jobs)


def _today() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()


def build_and_publish_shards(jobs: list, out: Path, *, build_id: str) -> int:
    """Build per-sector shards from jobs and gzip each for release upload. Returns shard count."""
    from ergon_tracker.index.build import build_sharded_index

    manifest = build_sharded_index(jobs, out, build_id=build_id)
    for info in manifest["shards"].values():
        _gzip_file(out / info["file"], out / (info["file"] + ".gz"))
    return len(manifest["shards"])


def build_and_publish_shards_from_db(db_path: Path, out: Path, *, build_id: str) -> int:
    """Memory-bounded shard publish: partition the built index by sector via SQL, gzip each."""
    from ergon_tracker.index.build import build_sharded_index_from_db

    manifest = build_sharded_index_from_db(db_path, out, build_id=build_id)
    for info in manifest["shards"].values():
        _gzip_file(out / info["file"], out / (info["file"] + ".gz"))
    return len(manifest["shards"])


def _count_jobs(db_path: Path) -> int:
    """Row count of an index DB (cheap; avoids loading jobs into memory)."""
    from ergon_tracker.index.db import connect

    con = connect(db_path, read_only=True)
    try:
        return con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    finally:
        con.close()


def publish_coverage(db_path: Path, out_dir: Path, *, build_id: str) -> dict:
    """Write coverage.json + INDEX_STATUS.md so users/forkers can see index coverage."""
    from ergon_tracker.index.coverage import compute_coverage, render_status_md
    from ergon_tracker.index.db import connect

    con = connect(db_path, read_only=True)
    try:
        cov = compute_coverage(con)
    finally:
        con.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    md = render_status_md(cov, build_id=build_id)
    (out_dir / "coverage.json").write_text(json.dumps(cov, indent=2))
    (out_dir / "INDEX_STATUS.md").write_text(md)  # release asset
    (ROOT / "INDEX_STATUS.md").write_text(md)  # browsable in repo root
    return cov


def append_history(history_path: Path, row: dict) -> None:
    """Append one build-summary row to the history JSONL time series (for drift detection)."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _gated_publish(
    tmp_db: Path, final_db: Path, out: Path, *, build_id: str, prev_row_count: int | None = None
) -> bool:
    """Good-or-nothing publish: gate the temp build, promote+publish only if it passes.

    Writes gates.json always. On failure the previous snapshot (final_db) is left untouched.
    """
    from ergon_tracker.index.gates import evaluate_gates

    rep = evaluate_gates(tmp_db, prev_row_count=prev_row_count)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gates.json").write_text(json.dumps(rep.to_dict(), indent=2))
    if not rep.passed:
        print(f"GATES FAILED — keeping previous snapshot. {rep.summary()}")
        tmp_db.unlink(missing_ok=True)
        return False
    tmp_db.replace(final_db)  # atomic promote
    publish_artifacts(final_db, out, build_id=build_id)
    cov = publish_coverage(final_db, out, build_id=build_id)
    print(f"gates passed: {rep.summary()} | coverage: {cov['total_jobs']} jobs, "
          f"{len(cov['by_source'])} providers, {len(cov['by_sector'])} sectors")
    return True


def _registry_window(cursor: int, limit: int) -> tuple[list, int]:
    """Return (window, next_cursor): a rotating slice of crawlable registry boards.

    Instead of always crawling registry[:limit] (which never reaches the tail and, on a cold
    start, makes ALL ~46.8k boards due at once -> a build that can't fit one CI run), each run
    takes `limit` boards starting at `cursor` (wrapping), then advances the cursor. Over
    ceil(total/limit) runs the whole registry is covered + seeded into board_state; tiering then
    keeps steady-state crawls small.
    """
    from ergon_tracker.registry.store import SeedRegistry

    items = [
        (k, e)
        for k, e in SeedRegistry().all().items()
        if e.get("ats") and e.get("token")
    ]
    total = len(items)
    if total == 0:
        return [], 0
    if limit >= total:
        return items, 0
    start = cursor % total
    window = [items[(start + i) % total] for i in range(limit)]
    return window, (start + limit) % total


async def _crawl_due(
    limit_companies: int, states: dict, fresh_db_path, build_id: str, cursor: int = 0
) -> tuple[dict, int]:
    """Crawl the due boards in this run's rotating window, streaming jobs into ``fresh_db_path``.

    Returns (per-board outcome, next_cursor). Jobs are written to the fresh DB as boards complete
    (memory O(in-flight boards), not O(all jobs)). The window bounds each run so it finishes within
    the CI timeout and durably seeds board_state; crash-isolated per board.
    """
    import anyio

    from ergon_tracker.dedup import deduplicate, normalize_company
    from ergon_tracker.enrich import enrich_in_place
    from ergon_tracker.exceptions import RateLimitError
    from ergon_tracker.http import AsyncFetcher
    from ergon_tracker.index.build import append_jobs
    from ergon_tracker.index.db import connect, fresh_db
    from ergon_tracker.index.scheduler import BoardState, due_boards
    from ergon_tracker.models import SearchQuery
    from ergon_tracker.providers.base import get_provider, load_builtins

    load_builtins()
    window, next_cursor = _registry_window(cursor, limit_companies)
    boards = {}
    for key, e in window:
        bs = BoardState(provider=e["ats"], token=e["token"])
        boards[bs.key] = (key, e)
        states.setdefault(bs.key, bs)
    due = set(due_boards(list(states.values()), _today())) & set(boards)

    outcome: dict[str, dict] = {
        b: {"error": False, "http_429": 0, "companies": set(), "not_modified": False} for b in due
    }
    fresh_db(fresh_db_path)
    con = connect(fresh_db_path)
    con.execute("PRAGMA foreign_keys = OFF")  # companies aggregated later (build_index_from_fresh_db)
    write_lock = anyio.Lock()
    pending = {"rows": 0}  # uncommitted row count; mutated only while holding write_lock

    async def grab(bkey: str, fetcher: AsyncFetcher) -> None:
        regkey, e = boards[bkey]
        provider = get_provider(e["ats"])
        state = states[bkey]
        # Cross-build conditional request: if this provider exposes a whole-board validator URL,
        # present the stored ETag/Last-Modified. A 304 means unchanged -> carry forward without
        # re-downloading (the big throttle/bandwidth win). A 200 refreshes the validator and we
        # parse that same body (no refetch) via raws_from_body.
        curl = provider.conditional_url(e["token"])
        try:
            if curl:
                res = await fetcher.conditional_get(
                    curl, etag=state.etag, last_modified=state.last_modified
                )
                if res.not_modified:
                    outcome[bkey]["not_modified"] = True
                    return  # unchanged -> prev jobs carry forward (company set stays empty)
                state.etag, state.last_modified = res.etag, res.last_modified
                # Reuse the body we just downloaded (200) instead of refetching the same board.
                raws = provider.raws_from_body(e["token"], res.body) if res.body else None
                if raws is None:
                    raws = await provider.fetch(e["token"], SearchQuery(), fetcher)
            else:
                raws = await provider.fetch(e["token"], SearchQuery(), fetcher)
        except RateLimitError:
            outcome[bkey].update(error=True, http_429=1)
            return
        except Exception:  # noqa: BLE001
            outcome[bkey]["error"] = True
            return
        # Crash isolation: normalize/enrich/dedup/insert for ONE board must never propagate to
        # the task group (that would cancel every other in-flight board and lose the whole crawl).
        try:
            board_jobs: list = []
            for raw in raws:
                try:
                    job = provider.normalize(raw)
                except Exception:  # noqa: BLE001
                    continue
                if e.get("domain") and not job.company_domain:
                    job.company_domain = e["domain"]
                enrich_in_place(job, company_key=regkey)
                board_jobs.append(job)
                outcome[bkey]["companies"].add(normalize_company(job.company))
            if board_jobs:
                # Per-board fuzzy dedup (cheap, memory-safe) recovers most of the old in-memory
                # deduplicate() quality; cross-board exact-id dedup is handled by append_jobs' UNIQUE.
                board_jobs = deduplicate(board_jobs)
                # one shared connection; the lock serializes the (sync, fast) batch insert and
                # the commit-batching counter. Periodic commit bounds the open transaction so a
                # crash/timeout doesn't roll back the entire crawl.
                async with write_lock:
                    append_jobs(con, board_jobs, build_id=build_id)
                    pending["rows"] += len(board_jobs)
                    if pending["rows"] >= 20000:
                        con.commit()
                        pending["rows"] = 0
        except Exception:  # noqa: BLE001 - one bad board never sinks the crawl
            outcome[bkey]["error"] = True
            outcome[bkey]["companies"].clear()  # not "crawled" -> prev jobs carry forward

    try:
        # Crawl-tuned fetcher: fail fast on dead/slow boards (a big fraction of a 46k-board cold
        # crawl). Defaults (25s timeout, 3 retries + backoff) can burn ~88s per dead board; 12s +
        # 1 retry caps that at ~24s. Per-host rate limiting + circuit breaker still apply, and
        # transiently-missed boards stay 'hot' and are retried next build (tiering).
        async with (
            AsyncFetcher(timeout=12.0, retries=2) as fetcher,
            anyio.create_task_group() as tg,
        ):
            for bkey in due:
                tg.start_soon(grab, bkey, fetcher)
        con.commit()
    finally:
        con.close()
    return outcome, next_cursor


def _load_cursor(path: Path) -> int:
    """Read the rotating-crawl cursor (registry offset) from a small JSON file; 0 if absent."""
    try:
        return int(json.loads(Path(path).read_text()).get("cursor", 0))
    except (FileNotFoundError, ValueError, OSError):
        return 0


def _save_cursor(path: Path, cursor: int) -> None:
    Path(path).write_text(json.dumps({"cursor": cursor}))


def main(argv: list[str]) -> None:
    import anyio

    limit = 300
    out = ROOT / "dist"
    incremental = False
    sharded = False
    i = 0
    while i < len(argv):
        if argv[i] == "--limit-companies":
            limit = int(argv[i + 1])
            i += 2
        elif argv[i] == "--out":
            out = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--incremental":
            incremental = True
            i += 1
        elif argv[i] == "--sharded":
            sharded = True
            i += 1
        else:
            print(f"unknown flag: {argv[i]}")
            return
    out.mkdir(parents=True, exist_ok=True)
    db = out / "index.sqlite"
    build_id = f"build-{_today()}"

    if incremental:
        from ergon_tracker.index.build import (
            build_index_from_fresh_db,
            changed_companies_sql,
        )
        from ergon_tracker.index.scheduler import apply_outcome, load_state, save_state

        state_path = out / "board_state.json"
        cursor_path = out / "crawl_cursor.json"
        states = load_state(state_path)
        cursor = _load_cursor(cursor_path)
        prev_db = db if db.exists() else None
        prev_row_count = _count_jobs(db) if prev_db else None
        # Streaming crawl over a rotating window: jobs stream to fresh.sqlite as boards complete.
        fresh_path = out / "fresh.sqlite"
        outcome, next_cursor = anyio.run(_crawl_due, limit, states, fresh_path, build_id, cursor)
        changed = changed_companies_sql(fresh_path, prev_db)  # SQL diff, no jobs in memory
        crawled_keys: set = (
            set().union(*(o["companies"] for o in outcome.values())) if outcome else set()
        )
        # fold each board's outcome back into its state (tiering + throttle back-pressure)
        for bkey, o in outcome.items():
            board_changed = bool(o["companies"] & changed)
            apply_outcome(
                states[bkey],
                today=_today(),
                changed=board_changed and not o["error"],
                error=o["error"],
                http_429=o["http_429"],
                requests=1,
            )
        # Persist crawl progress (tiering + cursor) IMMEDIATELY — durable even if the build/publish
        # below fails or times out, so the next run advances instead of re-crawling this window.
        save_state(states, state_path)
        _save_cursor(cursor_path, next_cursor)
        fresh_jobs_count = _count_jobs(fresh_path)
        db_tmp = out / "index.tmp.sqlite"
        n = build_index_from_fresh_db(
            fresh_path, db_tmp, build_id=build_id, prev_db=prev_db, crawled_keys=crawled_keys
        )
        ok = _gated_publish(db_tmp, db, out, build_id=build_id, prev_row_count=prev_row_count)
        append_history(
            out / "history.jsonl",
            {
                "build_id": build_id, "date": _today(), "due_boards": len(outcome),
                "fresh_jobs": fresh_jobs_count, "total_jobs": n, "changed_companies": len(changed),
                "throttled_boards": sum(1 for o in outcome.values() if o["http_429"]),
                "errored_boards": sum(1 for o in outcome.values() if o["error"]),
                "not_modified_boards": sum(1 for o in outcome.values() if o.get("not_modified")),
                "cursor": cursor, "next_cursor": next_cursor, "window": limit,
                "published": ok,
            },
        )
        fresh_path.unlink(missing_ok=True)  # free disk before the shard VACUUMs
        if ok and sharded:
            ns = build_and_publish_shards_from_db(db, out, build_id=build_id)
            print(f"  + published {ns} sector shards")
        print(
            f"incremental build: crawled {len(outcome)} due boards, {fresh_jobs_count} fresh jobs, "
            f"{n} total{' -> published' if ok else ' (gates FAILED, kept previous)'}"
        )
        if not ok:
            raise SystemExit(1)
        return

    jobs = anyio.run(_crawl, limit)
    db_tmp = out / "index.tmp.sqlite"
    n = build_index(jobs, db_tmp, build_id=build_id)
    if not _gated_publish(db_tmp, db, out, build_id=build_id):
        raise SystemExit(1)
    if sharded:
        ns = build_and_publish_shards(jobs, out, build_id=build_id)
        print(f"  + published {ns} sector shards")
    print(f"built index: {n} jobs -> {out}/index.sqlite.gz (+manifest.json)")


if __name__ == "__main__":
    main(sys.argv[1:])
