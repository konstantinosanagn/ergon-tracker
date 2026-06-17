# JazzHR — public fetch contract

JazzHR (formerly "The Resumator") hosts each customer's career site at
`{subdomain}.applytojob.com`. The product was historically branded `jazz.co`, so the
internal API host is `app.jazz.co`.

## Identifying a JazzHR tenant (signatures)

- Career-site host `*.applytojob.com` (the subdomain == the JazzHR account key).
- Apply/detail URLs of the shape `{sub}.applytojob.com/apply/{10-char-code}/{slug}`.
- Listing pages reference `app.jazz.co` widgets (`//app.jazz.co/widgets/buttons/create/{sub}/{code}`).
- The feed `publisher` element is `JazzHR`, `publisherurl` `http://app.jazz.co`.

## The fetch mechanism — public XML jobs feed (no auth, no cookies, no JS)

The build-ready, fully public endpoint is the global syndication feed:

```
GET https://app.jazz.co/feeds/export/jobs/{subdomain}
```

- No auth, no params, no pagination — returns **one XML document with every syndicated
  open job** for the tenant. Cached ~24h server-side.
- `Content-Type: application/rss+xml`-ish XML; values are wrapped in `<![CDATA[...]]>`.

### Record shape (`<jobs><job>...`)

| element        | meaning                                   | maps to |
|----------------|-------------------------------------------|---------|
| `id`           | `job_YYYYMMDDHHMMSS_<RANDOM>`             | `source_job_id` + **posted_at** (timestamp prefix) |
| `title`        | job title                                 | `title` |
| `department`   | department                                | `department` |
| `url`          | `http://{sub}.applytojob.com/apply/{code}/{slug}` | `apply_url` |
| `city`/`state`/`country`/`postalcode` | location parts (often blank) | `Location` |
| `description`  | full job description **HTML** (in CDATA)  | `description_html` |
| `type`         | `Full Time` / `Part Time` / `Contractor` / `Temporary` / `Internship` / `Freelance` | `employment_type` |
| `experience`   | `Experienced` / `Entry Level` / ...       | (left to enrichment) |
| `status`       | `Open` (we keep only Open)                | filter |
| `internalcode` | internal category                         | unused |
| `buttons`      | embed `<script>` for apply button         | unused |

**Posted date is derivable deterministically from `id`** — the 14-digit prefix is the
post timestamp. Live-verified: feed id `job_20260605135030_MBOOVQKBADWHJJKE` ⇔ the
detail page's JSON-LD `datePosted: 2026-06-05`. No per-job detail fetch needed.

### Live confirmation

```
$ curl -s https://app.jazz.co/feeds/export/jobs/talentwwinc
<?xml version="1.0" encoding="utf-8"?>
<jobs>
  <publisher><![CDATA[JazzHR]]></publisher>
  <publisherurl>http://app.jazz.co</publisherurl>
  <company><![CDATA[Career.io]]></company>
  <job>
    <id><![CDATA[job_20260605135030_MBOOVQKBADWHJJKE]]></id>
    <status><![CDATA[Open]]></status>
    <title><![CDATA[Product Engineer]]></title>
    <department><![CDATA[Tech]]></department>
    <url><![CDATA[http://talentwwinc.applytojob.com/apply/uw2WjsGMur/Product-Engineer]]></url>
    <country><![CDATA[United States]]></country>
    <description><![CDATA[<p><strong>THE COMPANY</strong> ...]]></description>
    <type><![CDATA[Full Time]]></type>
    <experience><![CDATA[Experienced]]></experience>
  </job>
  ...
</jobs>
```

Tenant job counts (live, 2026-06-17): `firstadvantage` 44, `nurdsoft` 9, `labelmaster`
2, `talentwwinc` 2. The feed count matched the `*.applytojob.com/apply` careers page
exactly for talentwwinc (2 jobs).

## Other endpoints considered (and why the feed wins)

- **Careers page** `{sub}.applytojob.com/apply` — server-rendered HTML, but its only
  `application/ld+json` block is the `Organization` (no per-job `JobPosting` list); jobs
  are plain `<a href="/apply/{code}/{slug}">` cards. Usable but less structured than the
  feed, and no description.
- **Detail page** `/apply/{code}/{slug}` — has full `JobPosting` JSON-LD incl.
  `datePosted`, `validThrough`, `employmentType`. Rich, but one request per job — only
  needed if the feed timestamp trick were unavailable (it isn't).
- **JSON / widget variants** (`?format=json`, `app.jazz.co/api/...`,
  `{sub}.applytojob.com/api/jobs`) — all return HTML/SPA shells, not JSON. No public JSON
  API for listing.
- **Authenticated REST API** `https://api.resumatorapi.com/v1/jobs?apikey=...` — requires
  a per-account API key (`success.jazzhr.com`). Out of scope (no-auth SDK).

## Pitfalls

- The feed only lists jobs the customer **chose to syndicate**; some tenants return an
  empty `<jobs/>` (e.g. `kalkomey` → 0) even with live careers-page jobs. Degrade to `[]`.
- `url` is `http://` (not https). Locations are frequently blank (`<city/>` etc.).
- No pagination / no server-side keyword filter — the whole board is one document;
  `SearchQuery.matches()` does the client-side filtering.
- `description` CDATA contains raw HTML (entities like `&#160;`).

## Token shape

`"{subdomain}"` (e.g. `"firstadvantage"`). `matches()` derives it from a
`*.applytojob.com` host/URL or an `app.jazz.co/feeds/export/jobs/{sub}` URL.

Cited live URLs:
- https://app.jazz.co/feeds/export/jobs/talentwwinc
- https://app.jazz.co/feeds/export/jobs/firstadvantage
- https://firstadvantage.applytojob.com/apply/hWkxLe59Yk/...
- https://success.jazzhr.com/hc/en-us/articles/360003617534 (Advanced career-page integration)
