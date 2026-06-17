# ergon-tracker

**A unified, free, reliable job-search engine in one Python package.** It fetches live
postings across **22 sources** (company ATS feeds + aggregators), canonicalizes them into one
schema, **deduplicates the same job posted on many sites**, enriches each posting (level,
location, salary, years-of-experience, sector), and **ranks results by relevance** — with an
SDK, a CLI, and an **MCP server** so humans *and* AI agents can use it.

> Package name note: the project / repo / install name is **`ergon-tracker`**; the Python
> import is **`ergon_tracker`**; the commands are **`ergon-tracker`** and **`ergon-tracker-mcp`**.

---

## Why it exists

Every free job source speaks a different dialect, and the same role shows up on four sites. No
free OSS tool was *reliable + unified + deduped + ergonomic* at once. ergon-tracker is that tool:

- ✅ **Dedup is real.** The same posting from Greenhouse + RemoteOK + Adzuna collapses to **one**
  record — fuzzy title/company matching, location compatibility, the most authoritative source
  (employer ATS) wins, and every source that listed it is kept under `provenance`.
- ✅ **Live jobs are real.** Postings are fetched on demand, directly from source APIs.
- ✅ **Filters are real and strong.** Level, location (country/city), salary range, years of
  experience, sector, remote, employment type, posting recency — all typed and tested.
- ✅ **Companies are easy to find & search.** Point at a domain (`stripe.com`) and it auto-detects
  the ATS and pulls that company's roles. A **41,988-company** registry ships in the box.
- ✅ **Search by natural language.** Lexical **BM25** ranking by default (zero deps); optional
  **semantic** (embeddings) ranking for meaning/synonyms.
- ✅ **Agent-ready.** An MCP server exposes search/resolve/list as tools, with relevance `score`s
  and structured fields, so an LLM can query it the way it expects.

Everything here is **free** — no paid APIs required. Two optional sources (Adzuna, USAJOBS) use
free API keys you provide.

---

## Install

Not on PyPI yet — install from the repo:

```bash
git clone https://github.com/konstantinosanagn/ergon-tracker
cd ergon-tracker

# with uv (recommended)
uv venv && uv pip install -e ".[mcp]"

# or with pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[mcp]"
```

Optional extras: `[mcp]` (agent server), `[semantic]` (NL embedding search),
`[pandas]` / `[polars]` (DataFrame export).

---

## Quickstart

### SDK (Python)

```python
from ergon_tracker import search

# Search a specific company's roles (auto-detects its ATS):
res = search("engineer", companies=["stripe.com"], limit=10)
for job in res.jobs:
    loc = job.locations[0].as_text() if job.locations else "—"
    print(f"{job.score:5.1f}  {job.title}  [{loc}]  ({job.source})")

# Strong filters, all combinable:
res = search(
    "backend",
    country="Germany",
    level="senior",
    salary_min=80000,
    remote=True,
    limit=20,
)

# Natural-language / semantic ranking (needs: pip install -e ".[semantic]"):
res = search("AI and deep learning roles at fintechs", semantic=True, limit=10)
```

`search()` returns a `SearchResult` with `.jobs` (ranked, each carrying a relevance `.score`),
`.health` (per-source status), and `.to_dicts()` / `.to_pandas()` / `.to_polars()`.

Async is first-class too:

```python
from ergon_tracker import AsyncErgonTracker, SearchQuery

async with AsyncErgonTracker() as et:
    res = await et.search(SearchQuery(keywords="data scientist", remote=True, limit=25))
```

### CLI

```bash
ergon-tracker search "engineer" --country Germany --level senior --remote --limit 20
ergon-tracker search "deep learning" --semantic            # embedding-ranked
ergon-tracker resolve stripe.com                            # -> {ats: greenhouse, token: stripe}
ergon-tracker sources                                       # list all 22 providers
ergon-tracker search "backend" --json | jq                 # machine-readable output
```

### MCP (for Claude / AI agents)

```bash
ergon-tracker-mcp        # stdio MCP server exposing search_jobs / resolve_company / list_sources
```

See **[docs/mcp-quickstart.md](docs/mcp-quickstart.md)** for the Claude Desktop / Claude Code
config block.

---

## Optional API keys (Adzuna & USAJOBS)

Two of the 22 sources are free keyed search APIs. Add your keys to a `.env` file in the repo
root (gitignored — never committed). Copy `.env.example` to get started:

```bash
cp .env.example .env
# then fill in your keys
```

```bash
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
USAJOBS_API_KEY=...
USAJOBS_EMAIL=...        # the email you registered with (sent as the required User-Agent)
```

If a key is missing, that source is **silently skipped** — it never breaks a search. Get free
keys at [developer.adzuna.com](https://developer.adzuna.com/) and
[developer.usajobs.gov](https://developer.usajobs.gov/).

---

## Sources (22)

**Company ATS feeds (14):** Greenhouse · Lever · Ashby · Workday · SmartRecruiters · Workable ·
Recruitee · Personio · BambooHR · Breezy · Teamtailor · join.com · Rippling · Pinpoint

**Aggregators (8):** RemoteOK · Remotive · Arbeitnow · Jobicy · Himalayas · TheMuse ·
**Adzuna** (keyed) · **USAJOBS** (keyed)

ATS feeds are the authoritative source during dedup; aggregators broaden coverage.

---

## How ranking works

1. **Filter** — each posting must pass your structured filters (and, in lexical mode, the
   keyword gate). Recall first: nothing relevant is dropped.
2. **Dedup** — cross-source duplicates merge into one record.
3. **Rank** — **field-weighted BM25** (title ≫ department/company ≫ description), so a search
   for "engineer" ranks *Engineer* roles above a sales role that merely mentions engineering.
   Every job gets a `.score`; ranking happens *before* the limit, so you keep the best matches.
4. **Semantic (opt-in)** — with `semantic=True`, embeddings rerank the top candidates by
   meaning (handles synonyms / NL intent). Runs locally on CPU via fastembed (~67 MB,
   already-quantized model); no API, no GPU. Tune with `ERGON_SEMANTIC_MODEL` /
   `ERGON_SEMANTIC_THREADS`.

A pluggable reranker seam means a stronger cross-encoder (e.g. ZeroEntropy `zerank`) can drop in
later as an extra — without touching the core.

---

## Development

```bash
uv pip install -e ".[dev,mcp,semantic]"
pytest          # full test suite
ruff check src tests && ruff format src tests
```

## License

MIT — see [LICENSE](LICENSE).
