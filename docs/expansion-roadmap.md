# Expansion Roadmap — going "super extensive" by borrowing from every competitor

> **Goal (2026-06-20):** drop the original self-imposed constraints (free-only / ATS-API-direct /
> no-browser) where they hold us back, and make `ergon_tracker` the most extensive job-discovery
> system — in *coverage*, *capabilities*, and *distribution* — by taking the best idea from each
> competitor, direct or indirect.
>
> **Companion docs:** competitive landscape + code-level reads in
> [`landscape-job-fetching-tools.md`](./landscape-job-fetching-tools.md); v2 index design in
> [`superpowers/specs/2026-06-19-v2-tiered-index-design.md`](./superpowers/specs/2026-06-19-v2-tiered-index-design.md).

## Where we stand right now (measured 2026-06-20)

- **Us:** **49,051 verified-live boards**, ~1.07M live jobs, 45 providers, daily tiered index
  (full / sector-shards / slim / row-deltas / multi-build chaining), SDK + CLI + **working MCP**,
  deterministic enrichment (level/comp/yoe/sector/geo), cross-source provenance merge, H-1B/visa.
- **jobhive** (our one real data competitor): **63,390 *listed* tenants** (counted across its 26
  CSVs today; the "~88k" figure floating in older notes is inflated — use 63,390). We're at **~77%**
  of its size on the stricter *verified-live* denominator.
- The lane the research identified — *a free, unified, maintained, enriched ATS-direct SDK + index +
  MCP* — **we already occupy it.** This roadmap is about widening the moat, not finding it.

---

## Priority 1 — Direct competitors (ATS-direct fetchers)

### 1A. In-philosophy, do-now (free, no new rules)
- **Re-ingest jobhive's *grown* CSVs** through our live verify gate for the ATSes where we trail
  their current list: **join (−3.7k), bamboohr (−2.9k), workable (−2.4k), personio (−1k)**. Same
  path that just added +2,170 jazzhr. Expected: several thousand more verified-live boards.
  - Tooling exists: `scripts/ingest_jobhive_csvs.py` → `scripts/build_registry.py` (verify+merge).
  - Source: **jobhive / `kalil0321/ats-scrapers`** (MIT) — <https://github.com/kalil0321/ats-scrapers>
- **Broaden brute-force token discovery** — feed more company-name sources (YC, Crunchbase/Wikidata,
  GitHub orgs) into `scripts/harvest_tokens.py`, probe GH/Lever/Ashby/SmartRecruiters concurrently.
  - Inspired by **`Babak-hasani/company-career-scraper`** (`generate_token_variations()`) —
    <https://github.com/Babak-hasani/company-career-scraper>

### 1B. The big ATS-direct unlock (BREAKS "no browser")
- **Headless-browser / deeper-anti-bot fallback** to crack the enterprise ATSes we currently skip:
  **icims, successfactors, cornerstone, gem, recruiterbox** (~6–7k tenants jobhive captures and we
  don't). We already use `curl_cffi` Chrome-TLS impersonation (schemaorg, peoplesoft); the next rung
  is a Playwright capture-then-replay fallback for the JS/auth-walled boards.
  - This is **jobhive's core edge** (stealth browser + TLS-impersonation) and the largest remaining
    *ATS-direct* coverage gap.
  - Probed 2026-06-20 and confirmed walled keylessly: gem (`jobs.gem.com`, SPA, API 302
    session-gated), recruiterbox/Trakstar (`{slug}.recruiterbox.com`, API 401), cornerstone
    (`{slug}.csod.com`, enterprise anti-bot), mercor (1 site).

### 1C. From careerscout — its two genuinely good ideas (it's an unoperated single-commit repo, not a real competitor)
- **Response-shape classification:** detect jobs on *unknown/unmodeled* ATSes by scoring an
  endpoint by its JSON *shape* (job-list vs single vs paginated) + ATS-vocabulary field matching —
  so discovery isn't limited to the ATSes we've hand-written providers for.
- **Web-scale discovery beyond Common Crawl:** **GitHub code search** (careers URLs embedded in
  repos) + **passive DNS**. (`scripts/harvest_commoncrawl.py` + `harvest_crtsh.py` already exist;
  crt.sh was a measured negative result — wildcard certs hide tenants.)
  - Source: **`Ramcharan747/careerscout`** — <https://github.com/Ramcharan747/careerscout>
- Other ATS-direct personal tools (reference only, not libraries):
  - `YvetteZheng0812/ats-job-scraper` (7 ATS incl. Rippling via `__NEXT_DATA__`; SerpAPI-gated
    discovery) — <https://github.com/YvetteZheng0812/ats-job-scraper>
  - `stevencc92/food-industry-job-scraper` — <https://github.com/stevencc92/food-industry-job-scraper>

---

## Priority 2 — MCP / AI-agent surface (fast-growing)

The MCP ecosystem is the distribution surface; we have the server but it's under-leveraged.

### 2A. Distribution — the real gap (highest-leverage MCP move)
- **Publish to PyPI** + a one-line MCP config so anyone can `pip install ergon-tracker` and drop
  `ergon-tracker-mcp` into Claude/Cursor. Today onboarding is *clone + `uv pip install -e`*, which
  caps adoption to ~zero — directly undercutting the "MCP is the surface" thesis.

### 2B. Agent capabilities competitors' MCPs have (that we can do cleanly)
- **Resume / JD → job matching:** feed a resume, semantically rank our index (we already have the
  embeddings reranker). Inspired by `AZaboobacker/ai_job_scanner` —
  <https://github.com/AZaboobacker/ai_job_scanner>
- **"Track this search / what's new" alerts — our unique advantage:** our daily **row-level deltas**
  already compute new/changed jobs. No competitor MCP has a real diff feed. This is a differentiated,
  demand-proven feature (the JobSpy MCP ecosystem proves the appetite).
- **Apply-assist:** generate tailored application material from a posting (LLM, BYO-key). Inspired by
  `6figr-com/jobgpt-mcp-server`, `MLS-Tech-Inc/shortlistjobs-mcp`, `0xDAEF0F/job-searchoor`.
- **First-class H-1B/visa MCP tool:** we have visa/LCA data *joined to live jobs* — a strict superset
  of `aryaminus/h1b-job-search-mcp` (raw DoL data only) —
  <https://github.com/aryaminus/h1b-job-search-mcp>

### 2C. MCP references worth studying
- JobSpy MCP wrapper: `borgius/jobspy-mcp-server` — <https://github.com/borgius/jobspy-mcp-server>
- Official remote-board MCP: `Himalayas-App/himalayas-mcp` — <https://github.com/Himalayas-App/himalayas-mcp>
- LinkedIn MCP (most active): `stickerdaniel/linkedin-mcp-server` — <https://github.com/stickerdaniel/linkedin-mcp-server>
- Public-data MCPs (international sources to consider adding): `wunderfrucht/jobsuche-mcp-server`
  (German Bundesagentur), `gmen1057/headhunter-mcp-server` (hh.ru).
- Google Jobs via SerpAPI (freemium — fails strict free-only): `ChanMeng666/server-google-jobs`.

---

## Priority 3 — JobSpy (board scraping, the heavyweight / indirect)

The biggest raw-coverage multiplier and the clearest "forget our intentions" move.

- **Wrap JobSpy (MIT) as an opt-in provider** — normalize LinkedIn / Indeed / Glassdoor /
  ZipRecruiter / Bayt / Naukri / BDJobs into our schema + dedup + enrichment + index + MCP. We'd
  gain the board breadth ATS-APIs structurally can't reach, **and present it better than JobSpy**
  (typed, enriched, deduped, provenance-merged, MCP-native).
- **Tradeoff (why we avoided it):** fragile, **proxy-dependent**, ToS-gray. Mitigate by keeping it an
  isolated, opt-in provider (off by default), not part of the core throttle-proof index.
- Source + ecosystem:
  - **`speedyapply/JobSpy`** (`python-jobspy`, MIT, ~3.7k★) — <https://github.com/speedyapply/JobSpy>
  - REST wrapper: `rainmanjam/jobspy-api` — <https://github.com/rainmanjam/jobspy-api>
  - Ports: `alpharomercoma/ts-jobspy`, `Liohtml/RUSTJobSpy`

---

## The three decisions that gate the ambitious moves

| # | Decision | Unlocks | Cost / risk |
|---|---|---|---|
| **D1** | Relax **"no browser"** (add Playwright fallback) | anti-bot ATSes (1B) + robust board scraping | Playwright dep + ops weight; slower, heavier |
| **D2** | Add **board-scraping (JobSpy)** | LinkedIn/Indeed/Glassdoor breadth (millions of jobs) | ToS-gray, proxy-dependent, fragile — biggest philosophy break |
| **D3** | Invest in **distribution** (PyPI + agent features) | actual adoption of the MCP/SDK | build/maintain effort; not "coverage" |

## Recommended sequence

1. **Now — free, fast, zero risk:** re-ingest jobhive's grown CSVs (1A) + broaden token discovery
   → close the verified-coverage gap toward parity with jobhive.
2. **Distribution:** PyPI publish + the **deltas-powered "what's new" MCP tool** + resume-match (2A,
   2B) → turn our unique assets into adopted features.
3. **Big coverage swing (needs D1):** Playwright fallback for anti-bot ATSes (1B), then optionally
   the **JobSpy board-scraping provider** (3, needs D2).

## Status

- [x] jazzhr ingest (+2,170 verified-live boards; registry 46,878 → 49,051) — 2026-06-20
- [x] PeopleSoft provider (cracks Missouri/FSU/NDSU university boards keylessly) — parallel session
- [ ] 1A re-ingest jobhive grown CSVs (join/bamboohr/workable/personio)
- [ ] 1A broaden `harvest_tokens.py` sources
- [ ] D1 decision → 1B Playwright fallback for anti-bot ATSes
- [ ] 2A PyPI publish + one-line MCP config
- [ ] 2B deltas-powered "what's new" MCP tool + resume-match + apply-assist
- [ ] D2 decision → 3 JobSpy board-scraping provider
- [ ] 1C response-shape classifier + GitHub-code-search / passive-DNS discovery
