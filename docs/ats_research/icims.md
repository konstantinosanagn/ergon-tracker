# iCIMS — Public Job-Fetch Spec

**Status:** build-ready, live-verified (2026-06). **Two generations with DIFFERENT contracts — detect + branch.**

## Identification
Hosts: classic `careers-{co}.icims.com`, `uscareers-{co}.icims.com`, `{co}.icims.com`; new "Career Sites" (Jibe) often on a vanity domain (`careers.amd.com`). AMD runs BOTH.
Signatures: `cdn02/cdn13.icims.com` assets, `images.icims.com/.../platform_183`, cookies (`JSESSIONID` classic vs `jasession`/`jrasession` new), `iCIMS_*` CSS (classic), `app.jibecdn.com` (new), CloudFront headers, `cdn13.icims.com/icims-branding` on error pages.

## A. New "Career Sites" (Jibe) → PUBLIC JSON API (use this)
```
GET https://{host}/api/jobs?page={N}&limit=100      # 1-indexed page; limit honored (size/per_page ignored)
```
- `200 application/json`. Live: `careers.amd.com` totalCount=1046; `careers.icims.com`=25. No auth/cookies.
- Top keys: `jobs, locations, totalCount, count, ...`. Each = `{"data": {...}}`.
- Per-job fields: `req_id, slug, title, description (full HTML), apply_url, posted_date, update_date,
  location_name/city/state/country/postal_code, employment_type, categories/department,
  salary_min_value/salary_max_value, hiring_organization, client_code`.
- Pages = ceil(totalCount/limit). One request/page = fully structured records incl. body.

## B. Classic → HTML only (fallback)
```
GET https://{host}/jobs/search?ss=1&in_iframe=1        # listing, 20/page, server-rendered
GET https://{host}/jobs/search?pr={P}&in_iframe=1      # page P, 0-indexed
GET https://{host}/jobs/{id}/{slug}/job?in_iframe=1    # detail (has JSON-LD JobPosting)
```
- `/api/jobs` returns HTML on classic (not JSON) — that's the detection signal.
- Listing: parse `/jobs/(\d+)/[a-z0-9-]+/job` hrefs; total via literal "Page X of Y".
- Detail pages DO carry `application/ld+json` `@type:JobPosting` (title, datePosted, validThrough, employmentType, hiringOrganization, jobLocation, description HTML). Needs `JSESSIONID` cookie jar across pages.

## C. Out of scope (auth-gated): Platform API `api.icims.com/customers/{id}/...` (Basic auth); Standard XML Feed (OAuth, approved vendors only).

## Detection algorithm
`GET {host}/api/jobs?page=1` → JSON with `jobs`/`totalCount` ⇒ new (use API); else ⇒ classic (HTML+JSON-LD). Hybrid Jibe-skinned classic hosts (careers-amd.icims.com) still answer `/api/jobs` with HTML → routed to classic correctly.

## Pitfalls
- **`sitemap.xml` is IP-allowlisted (403)** — do NOT use. Many guides wrongly push it.
- Vanity-domain iframe hides the real data host — resolve it first.
- CloudFront edge caching + occasional bot challenge at high rate (~1 req/2-3s/host).
- Classic needs cookie jar (first `/jobs/search` issues JSESSIONID); new API needs none.
- Desktop UA; multi-language tenants return per-language counts (filter `language:"en-us"`).
- Some big sponsors (Intel/PwC/T-Mobile) front iCIMS behind custom layers and redirect `/api/jobs` — verify per host.

## Recommended strategy
1. Detect via `/api/jobs?page=1`.
2. New: loop `/api/jobs?page=N&limit=100` to ceil(totalCount/100); map `jobs[].data`. Done, no detail fetch.
3. Classic: paginate `/jobs/search?in_iframe=1&pr=P` (cookie jar) to "Page X of Y"; fetch each detail; parse JSON-LD.
4. Never depend on sitemap/Platform API/XML feed.

Token shape for our provider: `"{host}"` (detect generation at fetch time) or `"{host}|new"`/`"{host}|classic"` if we want to pin.
