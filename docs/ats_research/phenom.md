# Phenom (Phenom People career sites) — public fetch contract

Phenom ("Phenom People") powers large enterprise career sites. The sites are Vue SPAs that
fetch jobs from a **public, no-auth POST endpoint on the tenant's own host** (`{host}/widgets`).
No API key, cookie, CSRF token, or browser is required for the job-search call.

Live-confirmed 2026-06-17 against three tenants:

| Tenant host                     | totalHits |
| ------------------------------- | --------- |
| `careers.activisionblizzard.com`| 53        |
| `careers.phenom.com`            | 47        |
| `careers.gehealthcare.com`      | 1037      |

## Identifying a Phenom tenant

Career sites run on **vanity domains** (e.g. `careers.activisionblizzard.com`), not on
`*.phenompeople.com`, so the host alone is not a reliable signal. The HTML/asset signatures are:

- Page HTML contains `phApp.ddo`, `"refNum":"<TENANT>"` (e.g. `ACCOUS`), and
  `phApp = phApp || {"widgetApiEndpoint":"https://{host}/widgets",...}`.
- Static assets are served from `https://cdn.phenompeople.com/CareerConnectResources/...`
  and there are `phenomTrackURL` / `phenompeople.com` references throughout.
- Search-results page lives at `/{country}/{lang}/search-results` (e.g. `/us/en/search-results`).
- Job detail page: `https://{host}/job/{jobSeqNo}` (200/303 → slugged URL).

`refNum` is the tenant key embedded in `jobSeqNo` (e.g. `ACCOUS` → `ACCOUSR023566EXTERNAL`).

## Job-fetch mechanism (the actual XHR)

The SPA's `phw-common` bundle posts to `widgetApiEndpoint` (`{host}/widgets`) with a JSON body
`{...params, ddoKey}` — **not** a raw GraphQL string (raw GraphQL → `{"status":"failure"}`).
The job-search DDO key is `refineSearch`. Pagination is `from`/`size` (NOT pageNumber/pageSize).

```
POST https://{host}/widgets
Content-Type: application/json
Body: {"ddoKey":"refineSearch","jobs":true,"from":0,"size":100}
```

`jobs:true` is required for the `data.jobs` array to be populated; `from`/`size` drive paging.
No auth headers needed. Live:

```
$ curl -s -X POST https://careers.activisionblizzard.com/widgets \
    -H 'Content-Type: application/json' \
    -d '{"ddoKey":"refineSearch","jobs":true,"from":0,"size":100}'
# -> {"refineSearch":{"status":200,"hits":53,"totalHits":53,"data":{"jobs":[ ... 53 ... ]}}}
```

### Response shape

```jsonc
{
  "refineSearch": {
    "status": 200,
    "hits": 53,            // count returned in THIS page
    "totalHits": 53,       // total matching jobs (the real count to page to)
    "data": {
      "jobs": [ { ...record... } ],
      "counts": {...}, "suggestions": {...}
    },
    "eid": {...}
  }
}
```

`size=100` returns up to 100 records; `from=50` returns records 50+ (clean offset paging).
`totalHits` is the count to page to; `from += size` until `from >= totalHits`.

### Record fields (live, Activision `R023566`)

```jsonc
{
  "jobSeqNo": "ACCOUSR023566EXTERNAL",          // STABLE unique id (tenant+req+visibility)
  "jobId": "R023566", "reqId": "R023566",
  "title": "Senior Staff Software Engineer (Data) | Xbox Advertising",
  "category": "Data Analytics",                  // -> department
  "multi_category": ["Data Analytics"],
  "city": "San Francisco", "state": "California",
  "country": "United States of America",
  "cityState": "San Francisco, California",
  "cityStateCountry": "San Francisco, California, United States of America",
  "location": "San Francisco, California, United States of America",
  "postedDate": "2026-03-13T00:00:00.000+0000",  // ISO-8601, +0000 offset (no colon)
  "dateCreated": "2024-11-14T18:30:53.827+0000",
  "type": "Regular",                             // employment taxonomy (tenant-specific, see below)
  "checkRemote": "On-site",                      // "On-site"/"Remote"/"Hybrid" or null
  "descriptionTeaser": "Your Role Within the Kingdom...",  // plain-text summary (truncated)
  "applyUrl": "https://xboxgaming.wd1.myworkdayjobs.com/.../apply",  // external ATS apply link
  "externalApply": false,
  "ml_skills": [...], "ml_job_parser": {...}     // ML enrichment (ignored)
}
```

- **Canonical posting URL:** `https://{host}/job/{jobSeqNo}` (live 200/303).
- **`applyUrl`** is the *real* apply destination (often an external ATS such as Workday).
- **`type`** is tenant-defined taxonomy, NOT a clean employment type — Activision uses
  `"Regular"`; GE Healthcare uses `"Mid-Career"`, `"Early Career"`, `"Co-op/Intern"`,
  `"Senior Level"`, `"Fixed Term Contract (Fixed Term)"`, `"Apprentice"`, `"Non-Salaried"`.
  Only substring-matchable values (intern/contract/part-time/full-time/temporary) are mapped;
  everything else → `UNKNOWN`.
- **`checkRemote`** is often `null` (e.g. all 100 GE records) — degrade to location-based remote
  detection / `UNKNOWN`.
- `descriptionTeaser` is a plain-text teaser (no HTML) → `description_text`. The full description
  is only on the detail page (not fetched in bulk).

## Versioning / variants / telling tenants apart

- The API is **per-tenant-hosted** at `{tenant_host}/widgets` — there is no shared Phenom host
  for search. Each tenant's `/widgets` returns only that tenant's jobs.
- `refNum` (prefix of `jobSeqNo`) distinguishes tenants in the data.
- The `ddoKey`/`from`/`size`/`jobs:true` contract was identical across all three tenants.

## Pitfalls

- **Not GraphQL at the wire** — raw `query{...}` bodies are rejected (`{"status":"failure"}`).
  It is the Phenom "DDO widget" API: `{ddoKey, ...params}`.
- `jobs:true` is mandatory; without it `data.jobs` is absent/empty even though `totalHits` is set.
- `from`/`size` only — `pageNumber`/`pageSize` are silently ignored (returns 0 jobs).
- Vanity domains mean host-suffix matching is impossible; match `*.phenompeople.com` plus
  career-site path shapes (`/search-results`, `/job/{SEQNO}`).
- `checkRemote` and `type` are frequently null/tenant-specific — never invent; map only known
  values, else `UNKNOWN`.
- Some non-Phenom career hosts return HTML/non-JSON for `/widgets`; the provider degrades to `[]`.
- No auth key observed for search; bot-walls/rate-limits not hit at modest volume, but the shared
  per-host limiter + circuit breaker in `AsyncFetcher` apply.

## Token shape

`"{host}"` — e.g. `"careers.activisionblizzard.com"`. The `/widgets` endpoint and `/job/...`
detail pages are all on that host.
