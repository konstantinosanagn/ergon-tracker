# Avature — Public Job-Fetch Spec

**Status:** live-tested (2026-06). Feasible as ONE generic parser, **parameterized per tenant** (not one fixed URL). Server-rendered HTML is the backbone.

## Identification
Host: `{tenant}.avature.net` (one slug = one company; some on vanity CNAMEs).
Path: `https://{host}/{locale}/{portalPath}/{page}` — `{portalPath}` is per-tenant (`main`, `careers`, `careersmarketplace`, custom); `{page}` is stable Avature names (`SearchJobs`, `JobDetail`).
Signatures: `avature.portal.*` `<meta>` tags, `/portal/{id}/` + `/portalpacks/web/assets/` asset paths, `ScustomPortal-*` cookies, `recruiting.analytics.avature.net/matomo.php`, `robots.txt` with `Sitemap: .../{portalPath}/sitemap_index.xml` + `Disallow: /*/{portalPath}/*qtvc=`.

## Fetch mechanism — server-rendered HTML (primary)
```
GET https://{host}/{portalPath}/SearchJobs?jobRecordsPerPage={N}&jobOffset={K}   # follow 302 locale redirect
```
- Job cards in raw HTML (no JS). Paginate by incrementing `jobOffset` (proven distinct pages) until no new `JobDetail` ids.
- Job detail: `…/{portalPath}/JobDetail/{slug}/{numericId}` or `?jobId={id}`.
- **Anchor parsing on the stable `JobDetail/.../{id}` href + title text, NOT tenant CSS** (themes vary).

## RSS feed (freshness only — NOT full list)
`…/{portalPath}/SearchJobs/feed/?jobRecordsPerPage=20` → clean `<item>` (title, `"{location} - {ref}"`, link/guid w/ id, pubDate). **Hard-capped at 20, `jobOffset` ignored.** Latest ≤20 only.

## What does NOT work
- **No public JSON/REST search endpoint** (the "JSON Jobs API" is a contracted per-customer feed). `qtvc=` URLs are server-side cache state — don't construct.
- **No JSON-LD** on stock JobDetail.
- **Sitemap lists page TYPES, not jobs** — useless for enumeration.

## Pitfalls / anti-bot
- Must follow 302 locale redirects (else empty body).
- **Some tenants block non-browser clients: 202 + 0-byte body (koch), or mandatory-login portals (maximus).** Treat empty/202/login-titled as "not fetchable," skip.
- RSS 20-cap + no offset.
- Use browser UA + cookie jar across paged requests.
- Per-tenant config needed: `{host}`, `{portalPath}` (from robots.txt `Sitemap:` lines; default `careers` then `main`), locale handling.

## Recommended strategy
1. Discover `{portalPath}` from `{host}/robots.txt` (default `careers`→`main`).
2. GET `…/{portalPath}/SearchJobs?jobRecordsPerPage=100&jobOffset=0`, follow redirects, browser UA + cookie jar.
3. Parse `JobDetail/{slug}/{id}` hrefs + titles/locations; paginate `jobOffset` until no new ids.
4. (Optional) per-job detail page for description/ref.
5. Freshness probe: `SearchJobs/feed/?jobRecordsPerPage=20`.
6. Detect blocked/login-only (empty/202) → skip.

**Feasibility:** one parser works (stable page grammar), but expect a per-tenant success rate well below 100% (blocked/login buckets) and theme variation. Token shape: `"{host}|{portalPath}"`.
