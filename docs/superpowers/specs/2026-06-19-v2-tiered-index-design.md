# v2 — Tiered Index for Optimized Search (design)

**Status:** design (2026-06-19). v1 is complete: 1,058,597 jobs / 39,949 companies / 32 ATS
providers, full-registry rotating crawl, throttle-proof, CI-green, stress-tested for anonymous
users. v2 optimizes *query-time download cost*.

## Problem
The single-file index is **343 MB gz / 1.47 GB raw**. A filtered query is already cheap (sector
shards are 9–21 MB gz — shipped in v1). The remaining cost is a **broad, no-sector keyword query**:
it must download the whole 343 MB single file once. That's the v2 target.

## Measured reality (don't over-promise)
- `snippet`/description text is only **~43%** of the main text columns (avg 111 chars/row) — it is
  NOT the bulk. The index is big because it has **1M+ rows × ~1.4 KB/row**.
- Therefore a *snippet-stripped* index saves only ~30–40%.
- A **minimal-column** index (keep only what broad search needs to match + display) is
  ~150–200 bytes/row → **~50–80 MB gz (~4–5× smaller)**. This is the real win.

## Design: three tiers behind the existing `IndexBackend` seam
1. **Slim broad tier** *(new — this spec)*: a compact index carrying only
   `id, company, company_key, title, level, sector, city, country, remote, salary_min/max/currency,
   visa_sponsor, sponsorship_offered, apply_url, posted_at, source` + an FTS over **title+company**
   only (no snippet). Published as `index-slim.sqlite.gz`. Broad keyword/filter queries that need
   no description hit this (~60 MB) instead of the 343 MB full file.
2. **Sector shards** *(shipped in v1)*: filtered-by-sector queries pull one 9–21 MB shard.
3. **Full index** *(shipped)*: fetched only when a query needs `snippet`/description or exhaustive
   provenance.

Routing (extend `router.try_index`): sector query → shard; broad query needing no snippet → slim
tier; else → full. All three are the same schema family, so `SqliteIndexBackend`/`search_rows`
work unchanged (slim just has NULL snippet and fewer columns populated).

## Build
`build_slim_index(full_db, slim_path)` (SQL, memory-bounded): create a fresh schema DB, `ATTACH`
the full index, `INSERT ... SELECT <slim cols>` (snippet left NULL), rebuild FTS over title+company,
`finalize` (no VACUUM needed beyond the copy), gzip. Runs in the publish step after the full build;
adds `index-slim.sqlite.gz` + sha to the manifest.

## Tasks (TDD, incremental)
1. `build_slim_index(full_db, out)` — SQL copy of slim columns + title/company FTS; parity test
   (same ids as full for a broad keyword query; file is materially smaller).
2. Publish `index-slim.sqlite.gz` in the build + manifest entry; workflow asset upload.
3. `SlimCache` (download/verify slim) + router preference: broad-no-snippet → slim.
4. Decide "needs snippet" predicate (e.g. keyword present but matched only in description → fall
   to full; default broad keyword matches title/company so slim suffices).
5. Live dogfood: broad query downloads ~60 MB slim, returns same top results as full.

## v2.1 — Row-level deltas (SHIPPED 2026-06-19)
A returning user one build behind downloads only **changed/deleted rows**, not the whole file.
- `build_delta(prev_db, curr_db, out)` emits a compact SQLite of `delta_upserts` (rows new or whose
  content-bearing columns changed — per-build bookkeeping `build_id/fetched_at/last_seen` excluded so
  unchanged postings aren't re-sent every build) + `delta_deletes` (ids gone) + meta
  (`from_build_id`/`to_build_id`). `apply_delta(base_db, delta_db)` mutates the cached base in place
  (refuses unless `base.build_id == delta.from_build_id`), re-aggregates companies, rebuilds FTS,
  advances `build_id`, integrity-checks.
- Build publishes `index-delta.sqlite.gz` + `manifest-delta.json` (diff of the prior published index
  vs the new one). `IndexCache.ensure_fresh` tries the delta first when exactly one build behind,
  falling back to the full download on any miss (no delta / base mismatch / integrity failure).
- **Measured:** for a realistic ~4% daily churn over the real 380K-job index, the delta is **2.9 MB
  gz vs 130 MB full — ~45× smaller**; `apply_delta` reproduces the new index exactly (ids, titles,
  companies, FTS, integrity).

## Deferred (v2.2)
Per-**shard** deltas (currently deltas cover the single-file index; ShardCache still does
shard-level conditional fetch). Multi-build-behind delta chaining (today: one build behind → delta,
else full download).

## Non-goals
A server-side query API (not free/static). The index stays a static GH-Release artifact.
