# Oracle Recruiting Cloud (ORC / Fusion HCM) — Public Job-Fetch Spec

**Status:** build-ready, live-confirmed across 4 tenants / 3 FA pods (2026-06-17).
**Bottom line:** fully public, unauthenticated REST API (`recruitingCEJobRequisitions`) —
no token, no cookie, no browser. This is the fetch path; do NOT scrape the JS career SPA.

## Host / identification
Career URL: `https://{host}/hcmUI/CandidateExperience/{locale}/sites/{SiteName}/requisitions`
- `{host}` is `*.fa.*.oraclecloud.com` (pods: us2, ap1, em2, em3, ocs; also `fa-{x}-saasfaprod1.fa.ocs.oraclecloud.com`). Pod = routing only.
- `{SiteName}` == the `siteNumber` the API needs: `CX_1` (most common default), `CX_1001`, `CX_1002`, `CX_2001`, `CX_6001`, bare `CX`, …
- Signature: host `*.fa.*.oraclecloud.com` + `/hcmUI/CandidateExperience/.../sites/CX...`, and the REST base returns JSON. (Distinct from Taleo's `*.taleo.net`.)

## List endpoint
```
GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    ?onlyData=true&expand=requisitionList&totalResults=true
    &finder=findReqs;siteNumber={CX_xxxx},limit={n},offset={m}
```
- **Jobs live in `items[0].requisitionList[]`** (NOT `items[]`). Requires `expand=requisitionList` or you get facets only.
- **Total = `items[0].TotalJobsCount`.** Top-level `totalResults` is always 1 (a trap).
- Finder: `findReqs;siteNumber=CX_1,limit=25,offset=0`. `siteNumber` required. Other vars: `keyword, location, sortBy=POSTING_DATES_DESC, selected*Facet, latitude/longitude/radius`.
- **Per-request cap ~50–70** regardless of high `limit` → page with `limit=25` + walk `offset` to TotalJobsCount.

### List record fields (reliably present)
`Id, Title, PostedDate (YYYY-MM-DD), PostingEndDate, PrimaryLocation, PrimaryLocationCountry,
ShortDescriptionStr, WorkplaceType/WorkplaceTypeCode (ORA_ON_SITE…), JobFamily, JobSchedule,
Department, HotJobFlag, Relevancy`. Often null: JobFunction, WorkerType, LegalEmployer.

## Detail endpoint (optional, full HTML description)
```
GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
    ?expand=all&onlyData=true&finder=ById;Id="{Id}",siteNumber={CX_xxxx}
```
Returns `ExternalDescriptionStr, ExternalQualificationsStr, ExternalResponsibilitiesStr,
NumberOfOpenings, workLocation/secondaryLocations` (structured), etc. (`Id` quoted in finder.)

## Apply/view URL (construct — not in JSON)
`https://{host}/hcmUI/CandidateExperience/{locale}/sites/{CX_xxxx}/job/{Id}` (+ `/apply`).

## Versioning
Use `latest` (== `11.13.18.05`, byte-identical live). Fall back to `11.13.18.05` on 404.
Don't hardcode older numeric versions — some pods reject unknown segments.

## Pitfalls
- `siteNumber` mandatory + tenant-specific (the `CX_xxxx` from the career URL; default-probe `CX_1`).
- `expand=requisitionList` mandatory or zero jobs.
- `totalResults` always 1 → use `TotalJobsCount`.
- Per-request cap → offset paging.
- hCaptcha only on apply submit, NOT the read API. No auth header needed. Be polite (sequential offset, modest concurrency).

## Fetch strategy
1. Resolve `{host}` + `siteNumber` from career URL (default `CX_1`).
2. `limit=1&totalResults=true&expand=requisitionList` → read `items[0].TotalJobsCount`.
3. Page `offset=0,25,…` `limit=25` `expand=requisitionList` `sortBy=POSTING_DATES_DESC` until offset ≥ total.
4. (Optional) enrich via `recruitingCEJobRequisitionDetails`.
5. `version=latest`, fallback `11.13.18.05`. No auth.

Token shape for our provider: `"{host}|{siteNumber}"` (e.g. `eeho.fa.us2.oraclecloud.com|CX_1`).
