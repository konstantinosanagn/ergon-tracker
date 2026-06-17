# Oracle Taleo (Enterprise) — Public Job-Fetch Spec

**Status:** build-ready, live-verified on 2 tenants (drhorton=621 jobs, hyatt=3,184). Modern faceted-search Taleo exposes a public no-auth JSON endpoint. **The only non-obvious requirement is a `tz` request header** (no cookie/CSRF/JSESSIONID handshake needed).

## Identification
Host `{tenant}.taleo.net` (slug ≈ company, sometimes prefixed `tas-{co}`). Career section: `/careersection/{cs}/jobsearch.ftl?lang=en`. Signatures: `*.taleo.net` + `/careersection/`, version token `2026PRD.x`, `fs/FacetedSearchPage` requirejs, `Set-Cookie: locale=...; path=/careersection/`, `P3P: CP="CAO PSA OUR"`, error body "An Error Occurred in TEE". **Tenants churn — resolve host (NXDOMAIN-handle) before trusting.**

## Two required ids
- `{cs}` = career section CODE (not portal). Numeric (`drhorton`→`2`, `hyatt`→`1`) or alpha (`ex`, `external`, `cb_external`). Probe `[1,2,5,ex,external,cb_external]`; a real one returns a large (~46-50KB) HTML page.
- `{portal}` = 9-digit number embedded in that page. Extract `portal=(\d+)`. Required for the REST call. (`drhorton`→101430233, `hyatt`→460210089.)

## Fetch endpoint (public JSON)
```
POST https://{tenant}.taleo.net/careersection/rest/jobboard/searchjobs?lang=en&portal={portal}
Content-Type: application/json
tz: GMT-05:00            <-- REQUIRED (no tz -> HTTP 500)
Body: {"fieldData":{"fields":{},"valid":true},
       "filterSelectionParam":{"searchFilterSelections":[]},
       "sortingSelection":{"sortBySelectionParam":"3","ascendingSortingOrder":"false"},
       "advancedSearchFiltersSelectionParam":{"searchFilterSelections":[]},
       "pageNo":1}
```
Empty selections = all jobs. `fieldData` must be an OBJECT (not array) or 400.

### Response
```
{"requisitionList":[{"jobId":"264858","contestNo":"2602892",
    "column":["Junior Sales Rep","[\"TX-Richmond\"]","Jun 17, 2026"],
    "linkedColumn":0,"locationsColumns":[1], ...}],   // 25/page
 "pagingData":{"currentPageNo":1,"pageSize":25,"totalCount":621},
 "careerSectionUnAvailable":false}
```
- **`column` is tenant-configured + self-describing:** `linkedColumn`=title index; `locationsColumns`=location index(es) (JSON-encoded string array like `["US-TX-Dallas"]`); remaining (last) = posting date. Stable ids: `jobId` (→ `jobdetail.ftl?job=`), `contestNo` (public req number).
- Paginate `pageNo` 1..ceil(totalCount/pageSize). `requisitionList:null` (139B) = bad portal.
- Detail: `…/careersection/{cs}/jobdetail.ftl?job={jobId}&lang=en` → HTML (~103KB), description in JS string blocks, **no JSON-LD**.

## Variants
- **Enterprise faceted-search** (`fs/FacetedSearchPage`, `2026PRD.x`) → has REST endpoint. **Target this.**
- **Older Enterprise (pre-faceted):** `jobsearch.ftl`/`moresearch.ftl` HTML form, may lack REST → scrape HTML table.
- **Taleo Business Edition (`*.tbe.taleo.net`):** different product, REST is fully auth-gated → out of scope.
- Legacy RSS `…/ats/servlet/Rss?org=...` is admin-gated (default OFF) + 10-job cap → last resort only.

## Pitfalls (live-tested)
- **`tz` header mandatory** — matrix: (tz,no-cookie)→200; (no-tz,*)→500. Cookies NOT needed.
- No CSRF needed for search (only apply/save-search).
- `fieldData` object not array (else 400).
- `lang` consistent between page + REST call.
- `Cache-Control: no-store` (every page is a real query) — throttle; 3k jobs ≈ 128 requests.

## Strategy
1. Resolve `{tenant}.taleo.net` (skip NXDOMAIN).
2. Discover `(cs, portal)`: GET jobsearch.ftl probing cs codes; regex `portal=(\d+)`. Cache per tenant.
3. POST searchjobs with `tz` header + empty-selection body; page `pageNo` to totalCount.
4. Map: `id=jobId, req=contestNo, title=column[linkedColumn], location=json.loads(column[locationsColumns[0]]), posted=last column, url=jobdetail.ftl?job={jobId}`.
5. Fallbacks: older-Enterprise HTML scrape; TBE out of scope.

Token shape for our provider: `"{tenant}.taleo.net|{cs}|{portal}"` (or discover cs+portal at fetch time from the host).
