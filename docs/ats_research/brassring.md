# BrassRing (IBM / Infinite Kenexa "Infinite BrassRing") — public fetch contract

**Verdict: FEASIBLE, no-auth / no-browser.** Job RECORDS (title, id, location, description
HTML, date, apply URL) come back as JSON from a public AJAX endpoint. There is **no token
login**, but the endpoint is CSRF-protected: you must first `GET` the career-site home page
(plain HTTP GET) to obtain (a) the session cookies and (b) a per-page anti-forgery token, then
echo that token back on the POST. All of this is doable with `httpx` alone — no browser.

Live-verified 2026-06-18 against **ADM** (286 jobs) and **Fairfax County Public Schools**
(603 jobs).

---

## 1. Host / URL pattern & how a tenant is keyed

A BrassRing career site is identified by two query params: **`partnerid`** (the client) +
**`siteid`** (one career-site flavor of that client — language/brand/req-pool). Host is almost
always `sjobs.brassring.com`; some tenants use a vanity/region host (`krb-sjobs.brassring.com`,
`{company}.brassring.com`).

```
https://sjobs.brassring.com/TGnewUI/Search/Home/Home?partnerid={pid}&siteid={sid}
https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid={pid}&siteid={sid}&PageType=JobDetails&jobid={reqid}
```

The new UI is an **AngularJS 1.8 SPA** ("TGnewUI" / "TgNewUI", served by ASP.NET MVC). The home
page is ~1 MB of HTML; jobs are **not** embedded — the SPA loads them via an AJAX POST.

**Finding a tenant's pid/sid:** the company careers page links to the BrassRing search.
`www.adm.com/careers` → `sjobs.brassring.com/.../Home?partnerid=25416&siteid=5429`. A web search
for `site:sjobs.brassring.com {company}` reveals the params. Confirmed tenants:

| Tenant | host | partnerid | siteid | live jobs |
|---|---|---|---|---|
| Archer Daniels Midland (ADM) | sjobs.brassring.com | 25416 | 5429 | 286 |
| Fairfax County Public Schools | sjobs.brassring.com | 25103 | 5019 | 603 |
| Lockheed Martin (site-events site) | sjobs.brassring.com | 25037 | 5066 | 0 (niche) |
| IBM | krb-sjobs.brassring.com | 26059 | 5016 | (host 500s on this flow) |

**"This is BrassRing" signatures:** host `*.brassring.com`; `partnerid=` + `siteid=` query
params; paths `/TGnewUI/Search/...` (`Home`, `HomeWithPreLoad`); cookies `tg_session`,
`tg_rft`, `tg_rft_mvc`, `tg_session_{pid}_{sid}`; Kenexa markers (`media.brassring.com`,
`KenexaCandidateExport`, "Infinite Talent Acquisition").

---

## 2. The job-fetch mechanism (the one we use)

### Step A — bootstrap (GET, no auth)
```
GET https://sjobs.brassring.com/TGnewUI/Search/Home/Home?partnerid=25416&siteid=5429
```
Sets cookies (`tg_session`, `tg_rft`, `tg_rft_mvc`, `tg_session_25416_5429`) and, in the HTML,
the two values we need:

* `<input name="__RequestVerificationToken" value="…">` — the anti-forgery token (sent back as
  the **`RFT`** request header).
* `<input id="CookieValue" value="^…">` — the encrypted session value (= the `tg_session`
  cookie), echoed back in the POST body as `encryptedsessionvalue` / `encryptedSessionValue`.

It also carries the per-tenant **field map** (`JobFieldsToDisplay`) and the company name
(`PartnerName`) — see §4.

### Step B — list jobs (POST JSON, paginated)
```
POST https://sjobs.brassring.com/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs
Content-Type: application/json; charset=utf-8
RFT: {__RequestVerificationToken from step A}
(cookies from step A sent automatically)

{ "partnerId":"25416", "siteId":"5429", "keyword":"", "location":"",
  "keywordCustomSolrFields":"", "locationCustomSolrFields":"", "linkId":"",
  "Latitude":0, "Longitude":0,
  "facetfilterfields":{"Facet":[]}, "powersearchoptions":{"PowerSearchOption":[]},
  "SortType":"LastUpdated", "pageNumber":1, "encryptedSessionValue":"^…" }
```
Returns `200 application/json`. **50 jobs per page**, fixed. Increment `pageNumber` (1-indexed)
to page; total is `JobsCount`. Live-verified page 1 + page 2 for ADM with **no priming call** —
this single endpoint serves page 1 too.

> The SPA actually fires `POST /TgNewUI/Search/Ajax/MatchedJobs` (same body in PascalCase, same
> `RFT` header, no `pageNumber`) for the *first* page and `ProcessSortAndShowMoreJobs` for
> "show more". Both return the identical record shape. We use **only**
> `ProcessSortAndShowMoreJobs` because it serves every page (1..N) uniformly with a consistent
> `LastUpdated` sort. `keywordCustomSolrFields` is **optional** (verified: ADM returns all 286
> with it empty).

### Response shape
```json
{ "Jobs": { "Job": [ { "Questions": [ {"QuestionName":"reqid","Value":"3374337"}, … ],
                       "Link": "https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=25416&siteid=5429&PageType=JobDetails&jobid=3374337",
                       "lastupdated": … } ] },
  "JobsCount": 286, "Facets": …, "SortFields": [{"Name":"LastUpdated"},{"Name":"JobTitle"}] }
```
Each job's real fields live in a flat **`Questions[]` array of `{QuestionName, Value}` pairs**
(flatten to a dict). `JobsCount` is the true total. `TotalJobsCount`/`PageSize` are `0` here —
do not use them; page off `JobsCount`.

---

## 3. Record fields (after flattening `Questions`)

Field **names vary per tenant** (they're the tenant's Solr field codes). Universal vs.
configured:

| our field | ADM | Fairfax | how to resolve |
|---|---|---|---|
| job id | `reqid`=3374337 | `reqid`=1484331 | **`reqid`** (universal; = `jobid` in `Link`) |
| req number | — | `autoreq`=27896BR | `autoreq` (fallback id) |
| title | `jobtitle` | `jobtitle` / `formtext6` | `JobFieldsToDisplay.JobTitle` → fallback `jobtitle` |
| department | `department` | — | question `department` |
| description (HTML) | `formtext3` | `jobdescription` | `JobFieldsToDisplay.Summary` field |
| location | `formtext8`,`formtext10` | `location` | `JobFieldsToDisplay.Position3` minus dept/title/id (+ any `location/city/state/country` question) |
| last updated | `lastupdated`=`18-Jun-2026` | same | parse `%d-%b-%Y` |
| apply/detail URL | `Link` | `Link` | use `Link` verbatim |

`latitude`/`longitude` present but usually `0`. No salary/employment-type fields exposed → `None`
/ `UNKNOWN` (never invented).

### Per-tenant `JobFieldsToDisplay` (from home HTML, entity-encoded JSON)
```
ADM:     {"Position1":null,    "JobTitle":"jobtitle","Position3":["formtext8","formtext10","department"],"Summary":"formtext3"}
Fairfax: {"Position1":"autoreq","JobTitle":"formtext6","Position3":["location"],                          "Summary":"jobdescription"}
```
This is the deterministic source of truth for the description/location/title field codes — parse
it from the bootstrap HTML rather than hard-coding `formtextN`.

---

## 4. Pitfalls (all handled)

* **CSRF / session-heavy.** The POST 500s without (a) the bootstrap cookies and (b) the matching
  `RFT` header. With both (from the same `GET`) it 200s. `httpx.AsyncClient` keeps the cookie jar
  across the GET→POST on the shared fetcher, so no manual cookie plumbing is needed.
* **`encryptedSessionValue` body field** must echo the `#CookieValue` hidden input (= the
  `tg_session` cookie). The server keys results off the body value, so even if domain-wide
  cookies interleave across concurrent tenants the right session is used.
* **Empty/aggregator siteids** (MSCCN 16030/6106, Lockheed 25037/5066) legitimately return
  `JobsCount:0` — not an error.
* **Vanity hosts** (`krb-sjobs.brassring.com` for IBM) can 500 on this exact flow; the default
  `sjobs.brassring.com` host works.
* **Field-name drift**: never hard-code only `formtext3` etc.; resolve via `JobFieldsToDisplay`
  with sane fallbacks.
* `lastupdated` is an *update* date, not a post date → map to `updated_at`, leave `posted_at`
  `None` (honest; not invented).

---

## 5. Live evidence (2026-06-18)

```
$ curl -s -c c.txt "https://sjobs.brassring.com/TGnewUI/Search/Home/Home?partnerid=25416&siteid=5429" -o home.html
  # home.html: 1,039,922 bytes; sets tg_session/tg_rft/tg_rft_mvc; contains
  #   <input name="__RequestVerificationToken" value="T3pblPKjmlyRfLe2jDMjPFO9O…">
  #   <input id="CookieValue" value="^8tnKrFkcq512gqXDgPJJmM1C…">

$ curl -s -X POST ".../TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs" -b c.txt \
       -H "Content-Type: application/json" -H "RFT: <token>" --data-binary @body.json
  page1 HTTP 200  JobsCount 286  n 50  first reqid 3374337  ("Manager Credit EMEA")
  page2 HTTP 200  JobsCount 286  n 50  first reqid 3371653  ("Regulatory Affairs Executive")

  Fairfax (25103/5019): HTTP 200  JobsCount 603  n 50  first "26 ESOL Teacher, HS"
```
Without the `RFT` header the same POST returns `{"Jobs":null,"JobsCount":0,…}` or HTTP 500 — the
header is the gate.

---

## 6. Provider mapping (as built)

* **Token:** `"{host}|{partnerid}|{siteid}"`. A 2-part `"{partnerid}|{siteid}"` defaults host to
  `sjobs.brassring.com`.
* `matches()` recognizes `*.brassring.com` URLs and pulls `partnerid` + `siteid` from the query.
* `fetch()`: bootstrap GET → loop `pageNumber` 1..ceil(JobsCount/50) (cap `MAX_PAGES`) →
  `ProcessSortAndShowMoreJobs`; flatten `Questions`; dedupe by `reqid`; honor `query.limit`;
  degrade to `[]` on any error. (Keyword filtering is left client-side via `query.matches()`,
  per the SearchQuery contract — the body's `keyword` field is sent empty.)
* `normalize()`: id=`reqid` (fallback `autoreq`); title via `JobFieldsToDisplay.JobTitle`;
  description_html via `Summary` field; locations via `Position3`; department=`department`;
  `updated_at`=`lastupdated`; apply_url=`Link`; company=`PartnerName`.
</content>
