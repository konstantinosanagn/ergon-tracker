# Jobvite — Public Job-Fetch Spec

**Status:** build-ready, live-verified (2026-06). No-auth, no-browser. HTML-only path.

## Identification
- Canonical host: **`jobs.jobvite.com/{company}`** (the only reliably-resolvable career host).
  `{company}.jobs.jobvite.com` does **not** resolve (live: connection refused). Custom
  Jobvite-powered domains exist but can't be detected by host — out of scope for `matches()`.
- HTML/asset signatures: `jv-*` CSS classes (`jv-page`, `jv-job-list`, `jv-wrapper`,
  `jv-powered-by`), assets on `d3igejkwe1ucjd.cloudfront.net/__assets__/...` and
  `careers.jobvite.com/.../fonts/jobvite-icons`, recruiter login link to
  `app.jobvite.com/login/login.html`.
- Two career-site generations (auto-handled by redirect, same job-card markup family):
  - **Classic**: `jobs.jobvite.com/{company}/jobs/viewall` serves jobs directly (200).
  - **Newer "Engage"**: `/{company}/jobs/viewall` → **303** → `/careers/{company}/jobs`
    (`Location: /careers/{company}/jobs?error=301`). Following redirects lands on the
    same server-rendered listing. (httpx `follow_redirects=True` handles this transparently.)

## Job-fetch mechanism (the no-auth path we use)
```
GET https://jobs.jobvite.com/{company}/jobs/viewall      # follow 303 → /careers/{company}/jobs
```
- **Server-rendered HTML, the FULL active-req list in ONE document.** No pagination param:
  `?page=2` / `?p=2` return the identical full page. So one request = every open job.
- Each job is a link `href="/{company}/job/{jobId}"` where `jobId` is an 8-char slug
  (e.g. `oD2jAfwi`). Three card layouts seen in the wild — all carry the same signals:
  - Classic list: `<li class="row"><a href="/{c}/job/{id}"><div class="jv-job-list-name">TITLE</div><div class="jv-job-list-location">LOC</div></a></li>`, grouped under `<h3 class="h2">Category</h3>`.
  - Newer table: `<tr><td class="jv-job-list-name"><a href="/{c}/job/{id}">TITLE</a></td><td class="jv-job-list-location">LOC</td></tr>`.
  - Custom-skin featured: `<td class="jv-featured-job-title"><a ...>TITLE</a></td> ... <td class="jv-featured-job-location">LOC</td>`.
- **Record fields available on the list:** title, location string, jobId (= apply slug), apply
  URL. Location may be `"City, State"`, `"City, Country"`, or a placeholder `"2 Locations"`
  when a req spans multiple sites. **No** posted date / department / salary / description on
  the list — those normalize to `None` (never invented).
- Parser strategy (variant-agnostic): iterate `.jv-job-list-name, .jv-featured-job-title`;
  resolve the anchor (descendant **or** ancestor) whose href matches `^/{company}/job/{slug}$`;
  title = that cell's text; location = nearest ancestor's `.jv-job-list-location,
  .jv-featured-job-location`. Dedup by slug.

## Detail page (NOT fetched in bulk — too expensive)
```
GET https://jobs.jobvite.com/{company}/job/{jobId}
```
- Carries **`<script type="application/ld+json">` schema.org `JobPosting`** with
  `datePosted`, `description` (full HTML), `jobLocation`, `hiringOrganization`, `baseSalary`.
  Useful for per-job enrichment but one request per job — not used by the list provider.

## Authenticated feeds (out of scope — need keys)
- **JSON Feed API**: `GET https://api.jobvite.com/v1/jobFeed?companyId={id}&api={key}&sc={secret}&start=1&count=100`
  (start default 1, count default 100, max 1000/call). Requires `api` key + `sc` secret →
  not no-auth.
- **XML feed**: per-customer URL with `?c={companyId}` (the alnum after `c=` in the admin
  career-site URL); link is provisioned by Jobvite support per customer → not generally public.

## Token shape
**`"{company}"`** — the tenant slug from `jobs.jobvite.com/{company}` (e.g. `"buckman"`,
`"internetbrands"`, `"gvwgroup"`). `matches()` extracts it from any `jobs.jobvite.com` URL
(handles both `/{company}/...` and `/careers/{company}/...`).

## Live verification (2026-06)
- `buckman` → 37 jobs (classic list variant). Sample: `Estagiário(a) - Strategic Sourcing` @ `Sumaré, Sao Paulo`.
- `internetbrands` → 78 jobs (newer Engage table; `/jobs/viewall` 303→`/careers/internetbrands/jobs`). Sample: `Account Manager` @ `2 Locations`.
- `gvwgroup` → 4 jobs (custom-skin featured variant). Sample: `Production Operator` @ `Birmingham, Alabama`.

## Pitfalls
- `/jobs/alljobs` 303-redirects (no body); use **`/jobs/viewall`** + follow redirects.
- The bare `jobs.jobvite.com/{company}` landing page is an Angular SPA shell with `jv-*`
  classes but **no inline jobs** — must hit `/jobs/viewall`.
- No pagination knob: viewall is the whole list. Don't fake `?page=N`.
- Custom-skinned tenants (gvwgroup) may render only "featured" jobs on viewall — handled via
  the `jv-featured-*` classes, but such a list can be a subset of the true total.
- Title text in the classic variant lives in the `.jv-job-list-name` child, not the whole
  `<a>` (the anchor also wraps the location) — read the name cell, not anchor text.
