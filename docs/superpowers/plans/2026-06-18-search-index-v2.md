# Search Index — v2 (Approach B: sector-sharded index) Implementation Plan

> Builds on v1 (M1–M3). Spec: `docs/superpowers/specs/2026-06-18-search-index-design.md` (Approach B).
> Implement task-by-task (TDD). Same `IndexBackend` interface → callers unchanged.

**Goal:** Optimize search + downloads by splitting the single index into **per-sector shards**
(plus an `unknown` shard) behind a shard manifest, and a `ShardedIndexBackend` that routes a
sector-scoped query to just that shard — so a "fintech" search downloads/opens one small shard
instead of the whole ~100 MB index. Cross-sector queries fan out across shards and merge.

**Architecture:** Build writes `shard-<sector>.sqlite` files + `shards.json` manifest. The SDK's
shard cache downloads the manifest, then only the shard(s) a query needs. `ShardedIndexBackend`
implements the existing `IndexBackend` Protocol (drop-in for `SqliteIndexBackend`); routing in
`run_search` is unchanged. Daily deltas are a later sub-phase (v2.1).

**Why now (honest):** the single-file v1 index already works (one ~100 MB cached download, 2 ms
queries). Sharding earns its keep when (a) the full index grows large and (b) queries are
sector-scoped — then a user pulls one shard, not all. We keep v1's single-file path as the
fallback when no shards are published.

---

### Task 1: Sector-sharded build
- Add `build_sharded_index(jobs, out_dir, *, build_id)` to `index/build.py`: group jobs by
  `sector` (None → `"unknown"`), build one `shard-<slug>.sqlite` per sector via `build_index`,
  write `shards.json` = `{build_id, schema_version, shards: {sector: {file, rows, sha256}}}`.
- Test: jobs in 2 sectors + unknown → 3 shard files + manifest; each shard queryable; row counts
  sum to total; sha256 present.

### Task 2: `ShardedIndexBackend`
- Add to `index/backend.py`: `ShardedIndexBackend(shard_dir)` implementing `IndexBackend`.
  `search(q)`: if `q.sector` → open that one shard, `search_rows`; else → open every shard, union
  results, re-sort (bm25 not comparable across shards → re-rank with `ranking.rank` on the merged
  set when keywords present, else posted_at), apply `q.limit`. `available()`/`metadata()` read
  `shards.json`.
- Test: sector query touches one shard; cross-sector query merges + limits; parity of results vs
  a single-file index built from the same jobs (same ids returned).

### Task 3: Shard-aware cache
- `ShardCache` (or extend `IndexCache`): download `shards.json` (TTL-gated, sha-verified per
  shard), and a `shard_for(sector)` that lazily downloads just that shard; cross-sector pulls all.
  Reuse token/anonymous logic. Atomic per-shard writes; schema gate.
- Test (file:// remote): downloads only the requested shard; verifies sha; cross-sector pulls all;
  corrupt shard rejected.

### Task 4: Routing prefers shards, falls back to single-file then live
- `index/router.py`: prefer `ShardedIndexBackend` if a shard manifest is available, else the v1
  single-file `SqliteIndexBackend`, else live. No public-API change.
- Test: shards present → sharded path; only single-file present → single path; neither → live None.

### Task 5: Build script + Action publish shards
- `build_index.py --sharded`: build shards + manifest; publish all `shard-*.sqlite.gz` + `shards.json`
  to the release (alongside the single-file for back-comat during transition).
- Action: upload shard assets. (Keep single-file until shard path is proven in the wild.)

### Task 6: Live dogfood (mandatory)
- Build sharded from a real crawl; confirm a sector query downloads/opens one shard; cross-sector
  merges; sizes per shard sane. Log to `INDEX_RUNS.md`.

### (v2.1, later) Daily deltas
- Per-shard row-level delta artifacts (added/removed ids + changed rows since build_id N), applied
  client-side so the daily refresh downloads diffs, not full shards. Separate plan.

---
**Self-review:** Task 1 build + Task 2 backend are pure/offline-testable (the core). Same
`IndexBackend` interface keeps routing/callers unchanged. Single-file fallback preserves v1.
Deltas deferred. Sector slug normalization reuses a simple slugify; `unknown` shard for null
sector.
