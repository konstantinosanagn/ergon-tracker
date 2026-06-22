# Plan: ATS-Exhaustion Ladder — the mandatory predecessor to ANY browser work

> **Status:** authoritative gate (2026-06-21). This plan is a **hard prerequisite** for
> [`2026-06-21-browser-discovery-design.md`](../specs/2026-06-21-browser-discovery-design.md).
> Build/run this FIRST. The browser subsystem must not touch a company until this ladder has run
> for it and recorded a complete, failed exhaustion log.

---

## THE NON-NEGOTIABLE PRINCIPLE

**Never assume a company needs a browser. The browser is the LAST resort, fired only after every
ATS lever we already own has been excruciatingly tried against that exact company and logged as
failed.** A board is "browser-eligible" *only* when it carries a complete `exhaustion_log` proving
every rung below was attempted and returned 0 entity-correct jobs.

Rationale (why this is serious):
1. **Cost & ops.** Headless browsers are ~1000× the cost/latency/fragility of an HTTP replay. Firing
   one for a board that was actually a 2-field Workday token away is pure waste and a production risk.
2. **Correctness.** Most "walls" this session turned out to be the wrong host / a namesake / an
   undiscovered tenant — not a real wall (EOG `.asp`, Targa Taleo behind a SelectMinds front, CRH via
   themuse, HCA/CBRE via dejobs, Ralph Lauren's `{page}Data/`). Reaching for a browser early would have
   captured *nothing better* and often a wrong entity.
3. **Trust.** A registry where every browser entry is provably "ATS-exhausted first" is auditable and
   defensible. One where we guessed "needs a browser" is neither.

---

## The standardized ladder (ordered; each rung = a method we ALREADY have)

Run rungs **in order**, cheapest/most-reliable first. Stop at the first rung that yields ≥1
**entity-correct** job (verified through our own provider stack). Record every rung's outcome.

| # | Rung | How (existing asset) | Covers |
|---|---|---|---|
| 0 | **Registry hit** | already in `seed.json`? fetch live; confirm healthy real count, right entity | already-captured |
| 1 | **Correct-tenant discovery** | curl_cffi the company's REAL careers page; grep for ANY supported ATS host/tenant (`*.myworkdayjobs.com`, `*.oraclecloud.com`/`CX_n`, `*.icims.com`, `successfactors`, `*.taleo.net`, `phenom`/`recruiting.com`, `radancy`/`/search-jobs`, `dayforcehcm`, `adp`, `ultipro`, `paylocity`, `pageup`, `peoplesoft`, `avature`, `jobvite`, `brassring`, `jazzhr`, …) → try the matched provider with the right token | namesake/wrong-token; most enterprise |
| 2 | **Brute-force token discovery** | `scripts/harvest_tokens.py` — slug variants (case/hyphen/suffix-strip/CamelCase) probed against path-based ATSes (greenhouse, lever, ashby, smartrecruiters, jazzhr, workable, recruitee, breezy, teamtailor, join, pinpoint) | path-based ATSes crt.sh can't see |
| 3 | **WebSearch the apply URL** | search `"{company} careers apply"` → read the real careers/job-search host → back to rung 1 with the discovered host (beware namesakes: verify entity) | sites whose ATS host isn't on the marketing page |
| 4 | **Provider-specific modes** | exhaust EACH provider's variants before declaring it dead: SuccessFactors (CSB-path `host\|siteid` / CSB-root `host\|*\|Company` / RSS `host\|company`); Taleo (modern REST **and** legacy `.ftl` `!\|!` stream); iCIMS (new `/api/jobs` vs classic `/jobs/search`); Avature (HTML anchors → `{page}Data/` JSON → RSS); Workday (`tenant\|wdN\|site`, try sites); Oracle (`host\|CX_n`, try site numbers) | "provider returns 0" that is really a token/mode mismatch |
| 5 | **Federation / aggregator (entity-clean)** | `dejobs` (DirectEmployers — hyphenated full name, e.g. `hca-healthcare`); `themuse` (brand name). Both keep `company_exact`, so entity-safe | WAF-walled US giants reachable via the federation (HCA, CBRE, EchoStar, Tractor Supply, PPL, Smurfit) |
| 6 | **apicapture, no-browser** | own-domain JSON/GraphQL replay; `html_table` (incl. non-`<table>` div rows, e.g. EOG); `embed_script` (`__NEXT_DATA__`/`__NUXT__`); `json_text_recover`; `rss`; `tls_impersonate` (curl_cffi) | bespoke sites with a reachable JSON/HTML grid no-browser |
| 7 | **schema.org** | job sitemap / JSON-LD JobPosting (`schemaorg` provider, curl_cffi TLS fallback) | sites exposing a JSON-LD/sitemap surface |
| — | **GATE → browser-eligible** | only if rungs 0–7 ALL logged failed → mark `ats_exhausted=true` with the full log → enqueue for browser discovery (Tier-1/2 of the browser design) | the genuine residual |

**Hard rule:** a company may enter the browser queue **iff** `ats_exhausted == true` AND the log
contains an attempt+result for **every** rung above. No shortcuts, no assumptions.

---

## Data model — the exhaustion record (per company)

Persist one record per company (e.g. `runs/exhaustion/{key}.json`), append-only:

```json
{
  "company": "fastenal",
  "checked_at": "2026-06-21T23:00:00Z",
  "rungs": [
    {"rung": 1, "method": "correct-tenant-discovery", "result": "no supported ATS host on careers page"},
    {"rung": 2, "method": "harvest_tokens", "result": "0 across gh/lever/ashby/smartrecruiters/jazzhr"},
    {"rung": 3, "method": "websearch", "result": "jobs.fastenal.com (custom FCA CMS)"},
    {"rung": 4, "method": "provider-modes", "result": "n/a (no provider host)"},
    {"rung": 5, "method": "dejobs/themuse", "result": "not in federation"},
    {"rung": 6, "method": "apicapture", "result": "POST /load-jobs is Akamai-403 to curl_cffi"},
    {"rung": 7, "method": "schemaorg", "result": "WordPress sitemap, no job sitemap/JSON-LD"}
  ],
  "ats_exhausted": true,
  "browser_tier_hint": 2,
  "notes": "Akamai sensor cookie; Tier-2 token-mint candidate"
}
```

This log is the **audit trail** that justifies every browser entry, and the input the browser
subsystem consumes (it reads `browser_tier_hint`, never guesses).

---

## Batch sweep over the existing registry

`scripts/ats_exhaustion_sweep.py` (to build): for the target company set (gaps first, then a
periodic full re-sweep), run the ladder concurrently via the existing `AsyncFetcher`, write
`exhaustion/{key}.json`, and emit:
- **captured** → `candidates.json` (→ `build_registry.py` live-verify gate → `seed.json`),
- **ats_exhausted** → `browser_queue.json` (the ONLY input to the browser subsystem).

Reuse, do not reinvent: the **propose → live-verify → merge** seam (`build_registry.py`) and the
ATS-priority survivor logic already exist. Every rung's "success" still passes the ≥1-entity-correct
verify-gate before it counts.

---

## Why this must live in memory + the design doc

- It prevents the single most expensive mistake: **defaulting to a browser**. Every future cron run,
  agent, and contributor must see this gate before any browser code path.
- It makes the browser subsystem's scope *small and earned* — only the proven-residual flows through it.
- Recorded as memory: `jobspine-ats-exhaustion-first`. Referenced as the hard prerequisite at the top
  of the browser-discovery design doc.

## Status / next steps
- [ ] Build `scripts/ats_exhaustion_sweep.py` (the ladder runner + exhaustion log).
- [ ] Run it over current S&P gaps + a full-registry periodic re-sweep.
- [ ] Only the `browser_queue.json` it emits feeds the browser design (next doc).
