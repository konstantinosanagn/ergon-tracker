# jobspine — Unified Job-Fetching SDK (v1 Design Spec)

**Date:** 2026-06-15
**Status:** Approved — building
**Working package name:** `jobspine`

## 1. Purpose & positioning

A unified, typed Python SDK that **combines and canonicalizes** job postings from many
free sources behind a single search interface. It is reliable-first (public ATS JSON feeds
are the default path), ergonomic (one `search()` call; sync + async), and ships a CLI.

### The market gap we fill (from prior-art research)
The OSS landscape splits into two camps and nothing bridges them:
- **Aggregator scrapers** (JobSpy, 3.7k★; JobFunnel, archived/dead) — broad coverage but
  *unreliable*: anti-bot 429s, ~1000-result caps, silent breakage, proxy-dependent,
  ToS-risky.
- **ATS-feed readers** (jobhive/ats-scrapers, OpenPostings, Levergreen) — reliable public
  JSON but fragmented, shipped as apps/pipelines not SDKs, **no real dedup**, no maintained
  company→token registry.

**No library is reliable + ergonomic + unified (ATS *and* aggregator) + job-aware dedup +
maintained registry + observability.** That combination is our wedge.

### What we borrow / what we beat
- Borrow: one-call ergonomics + optional DataFrame (JobSpy/jobhive); direct public ATS JSON
  as the reliability backbone (jobhive); seen-job/dedup memory + review workflow (JobFunnel);
  silent-failure detection via count sanity-checks (Levergreen); standard fields + raw
  passthrough.
- Beat: structured per-source observability (no silent empties); a real **job-aware dedup
  engine** (unfilled niche); a clean unified ATS abstraction with **auto-discovery**; a
  maintained **company→ATS registry**; honest documented limits; clear license separation
  between public-feed adapters (default) and scraping adapters (opt-in).

## 2. Constraints
- **Free only.** No paid APIs/tools in v1. Paid providers are documented and parked.
- **Python 3.10+.** Type-checked, fully typed (`py.typed`).
- User-friendly (casual: `jobspine.search(...)`) **and** dev-friendly (async core, pluggable
  providers, typed schema).

## 3. Tech stack (all OSS)
| Concern | Choice |
|---|---|
| HTTP | `httpx[http2]` — async core + sync facade |
| Concurrency | `anyio` (structured concurrency + `CapacityLimiter`) |
| Per-host rate limit | `aiolimiter` (token bucket) |
| Retries | `stamina` (wraps tenacity; honors `Retry-After`) |
| HTTP caching | `hishel` (RFC 9111, 304s, sqlite/file backend) |
| Schema | `pydantic` v2 |
| HTML/JSON-LD fallback | `selectolax` |
| Fuzzy match (dedup) | `rapidfuzz` |
| CLI | `typer` + `rich` |
| State (poll-and-diff seam) | stdlib `sqlite3` |
| Plugins | `importlib.metadata` entry points (`jobspine.providers`) |
| Packaging | `uv` + `hatchling`, src-layout |
| Quality | `ruff`, `mypy --strict`, `pytest` + `respx` + `vcrpy`, `mkdocs-material` |

DataFrame export (`pandas`/`polars`) is an **optional extra**, never a hard dependency.

## 4. Architecture (Approach A — layered pipeline)

```
search(query)
  → Resolver/Registry select target companies + sources
  → orchestrator fans out concurrently (bounded by CapacityLimiter)
      → Provider.fetch (cached, retried, rate-limited) → RawJob[]
  → Provider.normalize: RawJob → canonical JobPosting
  → dedup/merge across sources (provenance preserved, richest record wins)
  → SearchResult: jobs[] + per-source health[]
  → output: objects / dicts / optional DataFrame / CLI table|json
```

Reliable public ATS feeds are the default. Scraping adapters are opt-in and isolated behind
versioned adapters so one breakage cannot sink the library. `state.py` is the seam for a
future streaming/scheduler platform (parked Approach C).

## 5. Repo layout
```
src/jobspine/
  __init__.py        # public API: search(), JobSpine, AsyncJobSpine, JobPosting, SearchQuery
  models.py          # FROZEN CONTRACT: JobPosting, SearchQuery, Salary, Location, RawJob,
                     #   Provenance, SourceHealth, SearchResult, enums
  exceptions.py      # FROZEN CONTRACT: error hierarchy
  http.py            # AsyncFetcher: rate-limit + retry/Retry-After + circuit-break + cache
  client.py          # AsyncJobSpine async core (holds fetcher + registry; .search())
  sync.py            # JobSpine sync facade
  providers/
    base.py          # FROZEN CONTRACT: Provider Protocol, RawJob flow, @register, registry
    greenhouse.py lever.py ashby.py workday.py remoteok.py
  registry/
    resolver.py      # ATS auto-discovery: url/host → (ats, token)
    store.py         # seed registry loader + user overrides
    data/seed.json   # curated company→ATS→token seed (bootstrapped free)
  search.py          # unified search orchestrator
  dedup.py           # job-aware dedup/merge engine
  observability.py   # SourceHealth aggregation, count sanity checks
  state.py           # sqlite poll-and-diff seam (minimal in v1)
  cli.py             # typer + rich
  py.typed
tests/               # respx unit + vcrpy cassettes + stress suite
```

## 6. Frozen contract: canonical schema (`models.py`)

Enums: `RemoteType{ONSITE,HYBRID,REMOTE,UNKNOWN}`,
`EmploymentType{FULL_TIME,PART_TIME,CONTRACT,INTERNSHIP,TEMPORARY,OTHER,UNKNOWN}`,
`SalaryInterval{YEAR,MONTH,WEEK,DAY,HOUR}`.

- `Location`: `city|None, region|None, country|None, raw|None, is_remote: bool`
- `Salary`: `min_amount|None, max_amount|None, currency|None, interval|None`
- `RawJob` (pre-normalization container): `source: str, source_job_id: str, company: str,
  token: str|None, url: str|None, payload: dict, fetched_at: datetime`
- `Provenance`: `source: str, source_job_id: str, apply_url: str|None, fetched_at: datetime`
- `JobPosting` (canonical): `id: str` (stable, derived), `source: str`, `source_job_id: str`,
  `company: str`, `company_domain: str|None`, `title: str`, `description_text: str|None`,
  `description_html: str|None`, `locations: list[Location]`, `remote: RemoteType`,
  `employment_type: EmploymentType`, `department: str|None`, `salary: Salary|None`,
  `apply_url: str|None`, `posted_at: datetime|None`, `updated_at: datetime|None`,
  `provenance: list[Provenance]`, `raw: dict`. Missing fields are `None` — never invented.
  - `id` = stable hash of `(source, source_job_id)`; merged records keep the
    highest-priority source as primary and list all in `provenance`.
- `SearchQuery`: `keywords: str|None, location: str|None, remote: bool|None,
  employment_type: EmploymentType|None, posted_after: datetime|None, limit: int|None,
  companies: list[str]|None, sources: list[str]|None`. Includes a `matches(JobPosting)->bool`
  client-side filter used for ATS feeds (which have no server-side keyword search except Lever).
- `SourceHealth`: `source: str, ok: bool, count: int, error: str|None, elapsed_ms: int,
  truncated: bool`
- `SearchResult`: `jobs: list[JobPosting], health: list[SourceHealth]`; methods
  `to_dicts()`, `to_pandas()`, `to_polars()` (extras), `__iter__`/`__len__`.

## 7. Frozen contract: provider model (`providers/base.py`)
```python
@runtime_checkable
class Provider(Protocol):
    name: str
    @classmethod
    def matches(cls, url_or_host: str) -> str | None: ...     # token if this ATS else None
    async def fetch(self, token: str, query: SearchQuery, fetcher: AsyncFetcher) -> list[RawJob]: ...
    def normalize(self, raw: RawJob) -> JobPosting: ...
```
- Registry: module-level dict; `@register("greenhouse")` decorator; `get_provider(name)`,
  `iter_providers()`. Third-party plugins discovered via entry-point group `jobspine.providers`.
- Optional `BaseProvider` ABC with shared helpers (token-from-host regex, JSON-LD parse).

### Verified provider endpoints (live-tested in research)
| Provider | Endpoint | Auth | Notes |
|---|---|---|---|
| Greenhouse | `GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none | full board; filter client-side |
| Lever | `GET api.lever.co/v0/postings/{token}?mode=json` | none | server-side filters: team, location, commitment |
| Ashby | `GET api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` | none | richest comp data |
| Workday | `POST {tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` body `{appliedFacets,limit,offset,searchText}` | none | hardest: per-tenant, paginate, 10k cap |
| RemoteOK | `GET remoteok.com/api` | none | first element is legal/metadata — skip it |

## 8. Registry + auto-discovery (`registry/`)
- `seed.json`: curated `{company: {ats, token, domain}}`; bootstrapped free from Simplify
  `listings.json`, public ATS company lists, careers-URL parsing.
- `resolver.py`: given a domain/careers URL, run each provider's `matches()` → `(ats, token)`;
  handle Workday's `wdN`/tenant/site triple; unknown sites fall through to JSON-LD scraping.
- Unified keyword search = (registry ATS feeds, fetched then `SearchQuery.matches`-filtered)
  ∪ (keyword-searchable sources) → merged.

## 9. Dedup/merge engine (`dedup.py`) — differentiator
- Blocking key from normalized title + company alias + location.
- `rapidfuzz` similarity within block → merge near-duplicates (same role on ATS + aggregator).
- Merge keeps richest/most-authoritative record (ATS > scraped), unions `provenance`.

## 10. Public API + CLI
```python
import jobspine
jobs = jobspine.search("backend engineer", location="Berlin", remote=True)   # sync
async with jobspine.AsyncJobSpine() as js:
    result = await js.search(SearchQuery(keywords="ml", remote=True))         # async
```
CLI: `jobspine search "ml engineer" --remote --json`; `jobspine resolve acme.com`;
`jobspine sources` (health). `rich` tables by default, `--json` for piping.

## 11. Error handling / observability
- Never silently return empty. `SearchResult.health` reports per-source
  `{ok,count,error,elapsed_ms,truncated}`.
- Count-sanity warnings (a source that normally returns N suddenly returns 0 → flagged).
- Exception hierarchy in `exceptions.py`: `JobSpineError` → `ProviderError`, `FetchError`,
  `ResolveError`, `RateLimitError`. Orchestrator degrades gracefully: one dead source ≠
  failed search.

## 12. Testing & stress strategy
- **Unit** (`respx`): per-provider URL/token construction + full field normalization.
- **Recorded integration** (`vcrpy`): cassettes from real responses (captured in research);
  sanitized, committed.
- **Stress:** concurrency soak (hundreds of simulated companies); 429/`Retry-After`
  handling; malformed/empty payloads; partial-failure; dedup correctness on known-duplicate
  fixtures; pagination past caps (Workday).
- CI gate: `ruff check` + `ruff format --check` + `mypy --strict` + `pytest` on 3.10–3.13.

## 13. v1 scope boundary
**In:** providers {Greenhouse, Lever, Ashby, Workday, RemoteOK}; canonical schema; resolver +
seed registry; unified search; dedup; sync + async API; CLI; full test suite + CI.

**Parked (documented, not built):**
- Paid providers: JSearch, SerpApi Google Jobs, Coresignal, Bright Data/Oxylabs, TheirStack.
- Keyed free-tier search: Adzuna, USAJOBS (pluggable via optional API key) — fast follow.
- H-1B enrichment: DOL OFLC LCA + USCIS Employer Data Hub CSVs (sponsorship + salary join).
- Simplify GitHub `listings.json` curated feed.
- Streaming/scheduler platform (Approach C) — `state.py` seam left in place.

## 14. Build plan (parallel agents)
- **Phase 0 (sequential, owner = lead):** scaffold + freeze contracts (`models.py`,
  `providers/base.py`, `http.py`, `client.py` skeleton, `exceptions.py`, `pyproject.toml`, CI,
  `tests/conftest.py`).
- **Phase 1 (parallel, file-isolated):**
  - Agent A: `providers/greenhouse.py` + `providers/lever.py` + tests
  - Agent B: `providers/ashby.py` + `providers/remoteok.py` + tests
  - Agent C: `providers/workday.py` + tests + cassette
  - Agent D: `registry/resolver.py` + `store.py` + `seed.json` + tests
  - Agent E: `dedup.py` + `observability.py` + tests
- **Phase 2 (sequential, owner = lead):** `search.py` orchestrator + `sync.py` + `cli.py` +
  end-to-end stress suite; full CI green.
