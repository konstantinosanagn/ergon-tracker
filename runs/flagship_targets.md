# Flagship capture — running status (15-min cron 94d48831)

Updated 2026-06-21. ✅=captured & verified, 🔧=todo, ⛔=blocked (needs paid/browser path).

## Tier 1 — proprietary platforms (apicapture)
- ✅ **amazon** — apicapture `amazon`, amazon.jobs /search.json (10k+ hits)
- ✅ **apple** — apicapture `apple`, jobs.apple.com POST /api/v1/search (tls_impersonate, 6494)
- ✅ **google** — apicapture `google`, careers.google.com html_table+tls_impersonate, **3626** (id=jobs/results/(\d+); ssk rotated away). NOTE: apply_url is relative (apicapture can't prepend host).
- ✅ **meta** — apicapture `meta`, metacareers.com (was smartrecruiters/meta1 namesake)
- ✅ **microsoft** — apicapture `microsoft`, careers.microsoft.com search API (was smartrecruiters namesake)
- ✅ **uber** — apicapture `uber`, POST uber.com/api/loadSearchJobsResults (x-csrf-token:x, tls_impersonate, 923)
- ✅ **netflix** — eightfold `netflix` (verified 510, healthy)
- ⛔ **tesla** — /cua-api/apps/careers/state (6836 listings) behind **Akamai Bot Manager** (`cpr_chlge`). Stress-tested: token STRICTLY requires JS (`_abck` stays unvalidated even with browser cookies); curl_cffi cannot pass. **NEEDS PAID KEY** (JSearch/RapidAPI or SerpAPI Google Jobs).
- ⛔ **ibm** — real board = Avature `careers.ibm.com/.../SearchJobs/` behind **AWS-WAF JS challenge**. The single `aws-waf-token` cookie unlocks the JSON, but it must be JS-minted (curl_cffi can't get it) and EXPIRES in minutes; anonymous offset-walk also caps at 390 of 2982 (rest behind JS facet-POST). No durable no-JS path. **NEEDS PAID KEY** (same).

## Tier 2 — enterprise-ATS correct-tenant
- ✅ **oracle** — oracle `eeho.fa.us2.oraclecloud.com|CX_1` (1713) — fixed smartrecruiters namesake
- ✅ **jpmorgan** — oracle `jpmc.fa.oraclecloud.com|CX_1001` (real JPM, new)
- ✅ **adobe** — workday `adobe|wd5|external_experienced` (1102, already correct)
- ✅ **walmart** — workday `walmart|wd504|WalmartExternal` (2000+, already correct)
- ✅ **goldman sachs** — apicapture `goldmansachs` (api-higher.gs.com, healthy)

## Remaining work
Only **Tesla** + **IBM** left among the named flagships — both hard JS/WAF walls. Next cron runs should try the user-authorized PAID fallback (SerpAPI / JSearch-RapidAPI / an official paid careers API) for these two, key in gitignored .env. Otherwise both need a WAF-token/browser step disallowed at runtime.

## Round 3 — broader flagships (2026-06-21)
✅ Finance: citigroup (workday citi|wd5|2), bankofamerica (ghr|wd1|Lateral-US), wellsfargo (wf|wd1|WellsFargoJobs), americanexpress (oracle egug|CX_1), fidelityinvestments (fmr|wd1|FidelityCareers)
✅ Industrial/health: lockheedmartin (dejobs), raytheon/RTX (workday globalhr|wd5|REC_RTX_Ext_Gateway), johnsonjohnson (jj|wd5|JJ), merck (msd|wd5|SearchJobs), moderna (modernatx|wd1|M_tx), costco (icims careers.costco.com Jibe)
✅ Tech/consulting: dell (oracle iawmqy|CX_1001), doordash (greenhouse doordashusa, 453), ernstyoung (successfactors careers.ey.com|ey), mckinsey (apicapture gateway.mckinsey.com)
⛔ vmware — dedicated Workday board decommissioned post-Broadcom; only over-broad broadcom board has VMware roles → not captured (pollution).
⛔ zoom — careers.zoom.us = ClinchTalent (Phenom sub), AWS-WAF 202; no no-JS path. PAID-FALLBACK candidate.
⛔ kpmg (US) — kpmguscareers.com = Paradox/Olivia (unsupported); only non-US Oracle tenants exist (India/Lower Gulf) → namesake, not captured.

Still blocked awaiting paid key: **IBM, Tesla, Zoom** (all JS/WAF-walled). VMware/KPMG-US = no clean entity-accurate board exists.

## Method note
Namesakes often sit on a higher-priority ATS (smartrecruiters/workable) → force-overwrite in seed (priority gate would skip). For obfuscated SSR boards (Google), prefer a stable id (numeric href id), NOT rotating CSS/attr hooks (ssk/class names rotate).

## Round 4 — major employers wave 2 (2026-06-21) — 28 captured
✅ Energy/retail: chevron(radancy), conocophillips, coca-cola(coke|wd1), proctergamble(phenom pgcareers), kroger(oracle CX_2001), ups(phenom jobs-ups)
✅ Travel/telecom/media: t-mobile(tmobile|wd1), deltaairlines(avature), unitedairlines(phenom), southwestairlines(phenom), marriott(oracle MI_CS_1), hilton(oracle CX_1), booking(icims jobs.booking.com), warnerbrosdiscovery(phenom), sony(sonyglobal|wd1)
✅ Finance/pharma/defense: northropgrumman(ngc|wd1, 2934), generaldynamics(GDIT gdit|wd5), infosys(brassring 25633|5439), wipro(apicapture new-gen SF JSON, 7850), gileadsciences, elililly(lilly|wd115 — wd5 dead), elevancehealth(elevancehealth|wd1|ANT), charlesschwab(icims), synchrony, allyfinancial(avature), progressive(apicapture Talemetry/Cloudflare), statefarm(icims Jibe), emersonelectric(oracle)
⛔ exxonmobil — old TalentBrew HTML (no JSON envelope); needs radancy HTML mode. ⛔ bestbuy — ServiceNow Service Portal (no supported ATS). ⛔ discover — acquired by Capital One (over-broad parent only).

NEW reusable levers this round:
- New-gen SuccessFactors CSB exposes a no-auth POST JSON API `/services/recruiting/v1/jobs` (body {locale,limit,offset}) — capture via apicapture+tls_impersonate when the HTML successfactors provider returns 0 (Wipro).
- Talemetry SPA `/search/jobs.json` behind Cloudflare → apicapture+tls_impersonate (Progressive; cf. Kirkland).
- McKinsey-style API gateways (gateway.mckinsey.com/.../jobs/search) → apicapture GET pagination.

Blocked awaiting PAID KEY: IBM, Tesla, Zoom (JS/WAF). No entity-clean board: VMware (Broadcom), KPMG-US (Paradox), Discover (Cap One), Best Buy (ServiceNow), ExxonMobil (HTML-only, needs provider work).

## Round 5 — major employers wave 3 (2026-06-21) — 40 captured
✅ Finance/health: bnymellon, northerntrust, kkr(gh 165), chubb, prudentialfinancial, aflac, vertexpharmaceuticals, genentech, boozallenhamilton
✅ Retail/food: yumbrands, albertsons(6801), dollargeneral, publix, rossstores, ultabeauty, esteelauder, generalmills, kraftheinz, mondelez, conagra, hershey(~13k), anheuserbusch
✅ Industrial/defense/media: geaerospace, gehealthcare, gevernova, illinoistoolworks, stanleyblackdecker, l3harris, textron, marathonpetroleum, valeroenergy, chartercommunications, foxcorporation, alaskaairlines
✅ Tech/gaming: paloaltonetworks, appliedmaterials, nxpsemiconductors, genpact, take-two, activisionblizzard, hcl

⛔ This round's blocks + WHY (two are fixable no-browser lever gaps):
- **ttcportals TalentBrew** (older Radancy variant) — parkerhannifin(1207, /jobs/search.json), saic(/jobs/{id} JSON-LD), hca(also Cloudflare). FIXABLE: extend radancy or add apicapture GET spec. HIGH VALUE.
- **Avature /jobs/FolderDetail/{id} URL variant** — bain, lululemon. FIXABLE: extend avature _JOB_RE. 
- Acquired/no independent board: splunk(Cisco), juniper(HPE), discover(CapOne), vmware(Broadcom).
- Paradox.ai ATS (unsupported): mcdonalds, kpmg-us. (provider candidate if more appear)
- Bespoke/Ashby-disabled: shopify(Remix+Ashby off), ea(gr8people).

NEXT no-browser levers to build (unlock several flagships each): (1) ttcportals TalentBrew GET-json, (2) Avature FolderDetail URL regex.

## Round 7 — Fortune-500 wave 4 (2026-06-21) — 51 captured
✅ Insurance/finance (13): hartford, principal, massmutual, newyorklife, marshmclennan, aon(icims), willistowerswatson(oracle), arthurjgallagher(icims), troweprice, cme, spglobal, moodys(radancy), globalpayments(tsys)
✅ Data/medtech (9): equifax, transunion, cencora(myhrabc), iqvia, bectondickinson, edwardslifesciences, baxter, intuitivesurgical(SR; aerospace namesake rejected), zimmerbiomet(phenom)
✅ CPG/retail/tech (14): colgatepalmolive, clorox, kenvue, keurigdrpepper, molsoncoors, constellationbrands, kellanova, jmsmucker, campbellsoup, mccormick, hormelfoods, oreillyautomotive, snap(Snap!Mobile namesake rejected), match(lever)
✅ Industrial/energy (15): paccar, johnsoncontrols, carrier, otisworldwide, trane, jacobs(dejobs), caciinternational(eightfold), dominionenergy(dejobs), southerncompany(oracle), exelon(icims), edisoninternational(dejobs), phillips66, occidentalpetroleum, bakerhughes, schlumberger(eightfold)
⛔ sempra — ADP Recruiting (recruiting.adp.com), unsupported provider. NEW recurring blocked ATS (cf. fuyao/hlmando were ADP WorkforceNow which we DO crack; ADP *Recruiting* is different).
⚠ dejobs API flagged an origin-allowlist tightening (schlumberger backend) — watch dejobs tokens (jacobs/dominion/edison) for future breakage.

Recurring unsupported ATSes now seen: Paradox.ai (mcdonalds, kpmg-us), ADP Recruiting (sempra), gr8people (ea), ttcportals+Cloudflare (hca), ServiceNow portal (bestbuy), Coveo (slb native). Candidates if many more appear.

## Round 9 — GROUNDED in S&P 500 (2026-06-21)
Switched from recall to the authoritative S&P 500 constituent list (runs/sp500.json + scripts/sp500_coverage.py).
Was 473/503; captured 19 gap cos -> **492/503 = 98% S&P 500 coverage.**
✅ drhorton(taleo), garmin(icims), mgmresorts(wd5), nvr(taleobe), wynnresorts(wd5), erieindemnity(sf),
   incyte(icims), mettlertoledo(avature), corning(sf), f5(ffive|wd5), paychex(icims), emcor(icims),
   masco(phenom), rollins(icims), corteva(wd5), vertiv(oracle), newmont(phenom), freeport-mcmoran(eightfold fcx), nucor(sf)
Remaining 11 S&P gaps (all known-hard): tesla, ibm, exxonmobil, mcdonalds, sempra (walls/Paradox/ADP/TalentBrew-HTML);
fastenal, transdigm, amphenol (NO central ATS — genuine floors); udr, welltower (UKG Pro/UltiPro — unsupported ATS);
weyerhaeuser (Taleo, JS-injected portal id).
NEW recurring unsupported ATS: **UKG Pro / UltiPro Recruiting** (recruiting.ultipro.com) — UDR, Welltower; provider candidate.
NEXT: run `scripts/sp500_coverage.py` each flagship run for the live gap. To reach 100% S&P: build UKG-Pro provider (+UDR/Welltower), fix ExxonMobil TalentBrew-HTML, Weyerhaeuser Taleo portal; rest need paid/WAF decision or have no board.

## Tesla — cua-api recipe (confirmed working 2026-06-21, build next un-throttled run)
- Endpoint: GET https://www.tesla.com/cua-api/apps/careers/state  (returns ALL jobs in one JSON)
- REQUIRED: prime first — GET https://www.tesla.com/careers/search/ (Accept: text/html) in the SAME
  curl_cffi session to clear the WAF, THEN GET the cua-api with Referer=careers/search + x-requested-with=XMLHttpRequest.
  Without priming -> 403; rapid repeat calls -> 429 (IP-throttled for a window). One paced call/run is fine.
- Response keys: lookup, departments, geo (location TREE), listings (the jobs array).
- CAVEAT: listings are DENORMALIZED — location/department are IDs that must be resolved via the geo/departments
  lookup tables. Plain apicapture dotted-paths won't resolve location; needs a small custom map or a tesla provider
  that joins listing.{l/dp} -> geo/departments. Get one clean 200 (when not throttled), dump listings[0] keys, build the join.
- Status: endpoint cracked + priming solved; remaining work = lookup-join + pacing. NOT a wall.

## Tesla — DONE (provider shipped, commit 0eb4f48): 6,832 jobs / 3,728 US via curl_cffi prime+fetch + lookup-join.

## Gap discovery (2026-06-21, iteration) — platform intel for the hard tail
- Fastenal: jobs.fastenal.com = custom in-house "FCA" CMS (not Phenom/iCIMS API). BLOCKED unless a feed surfaces.
- Darden: dardenrscjobs.recruiting.com / dardenmyjobs.recruiting.com = "recruiting.com" platform; API (/api/jobs),
  sitemap, jobs.json all 403 Access-Denied to curl_cffi (WAF). NOT Phenom (phenom provider -> 0). Needs a one-time
  Playwright network-capture of the job-search XHR, then apicapture replay. DEFERRED.
- EOG / Roper / WEC Energy: careers landing resolves but is a JS-shell (no ATS host in static HTML) -> need Playwright.
- Sempra / Linde / Weyerhaeuser / Tractor Supply: my guessed careers hostnames DNS-failed; need WebSearch for the real
  ATS host before probing. Linde likely SuccessFactors, Sempra likely Workday/SF (utilities) — confirm host first.
- Method note: blind hostname-guessing wastes a run; ALWAYS WebSearch the company's real careers/ATS host first, then
  curl_cffi-grep, then verify. The stalled background discovery agent confirms: do this inline + bounded, not via a
  long-running agent.

## Gap discovery 2026-06-21 (WEC captured; 3 identified-but-deferred)
- WEC Energy: DONE — successfactors careers.wecenergygroup.com|career8 (20 US jobs, commit 6456c31).
- Evergy: Oracle Taleo evergy.taleo.net careersection=evergy_external_career_section (260 jobs at jobsearch.ftl),
  BUT our taleo provider's REST searchjobs endpoint returns 0 for it — token-form/endpoint mismatch. FIX: debug
  taleo provider against evergy (the .ftl page works; the rest/jobboard/searchjobs?portal= may need the portal id).
- Sempra (+SDG&E+SoCalGas): ADP myjobs.adp.com/sempra, tenant 'sempra', client c=2168707. Jobs load via ADP SPA
  backend {myadp}/mycareer/public/staffing/v1/job-requisitions/search-meta/2168707 — host resolved from runtime
  config, not reachable unauth via curl. FIX: the user's adp provider may already handle this token form — test
  adp 'sempra|2168707'.
- EOG Resources: REJECTED eeho.fa.us2.oraclecloud.com (WRONG entity — Austin software/India CS/MI data-centers, NOT
  EOG oil&gas). EOG's real board is careers.eogresources.com (classic .asp). Needs that .asp/legacy site cracked.

## 2026-06-21 hard-tail diagnoses (3 near-misses correctly rejected/deferred — no wrong-entity captures)
- HCA Healthcare: hcahealthcare.wd3.myworkdayjobs.com/hcacareers = HCA UK ONLY (London/Elstree hospitals), NOT the
  US S&P entity (Nashville). REJECTED (not US-inclusive). US board = careers.hcahealthcare.com (WAF 403). Real target.
- Evergy: Taleo evergy.taleo.net careersection serves jobs via server-rendered jobsearch.ftl HTML (260 jobs); the
  REST /careersection/rest/jobboard/searchjobs endpoint returns reqs=0 (older HTML-only Taleo). FIX = extend taleo
  provider to parse the .ftl HTML grid (our provider is REST-only). PROVIDER WORK.
- Sempra: ADP Recruiting Management (myjobs.adp.com/sempra, client 2168707) — DIFFERENT product than our adp provider
  (which handles ADP Workforce Now: workforcenow.adp.com + GUID cid + /careercenter/.../job-requisitions). Sempra's
  myjobs/staffing API (/mycareer/public/staffing/v1/job-requisitions/search-meta/{cid}) is a separate endpoint.
  FIX = add an ADP-RM mode to the adp provider. PROVIDER WORK.

## Evergy — fully diagnosed, DEFERRED (low ROI). Legacy Taleo "jobsearch.ajax" flow:
- NOT modern REST (rest/jobboard/searchjobs returns 0). NOT static HTML rows. NO simple RSS.
- Jobs come from POST /careersection/{cs}/jobsearch.ajax — a `!|!`-pipe-delimited FTL-history stream
  (jobId|title|...|contestNo|location|...|postedDate), needing csrftoken (from the .ftl GET) + a ~100-field
  form body. Only ~29 jobs. A parser would be brittle + Evergy-specific. Verdict: not worth building now.
- If ever needed: GET .ftl (capture csrftoken + cookies), POST jobsearch.ajax with the body, split response on '!|!',
  walk 9-field job records. ~29 jobs.

## STRATEGIC NOTE: remaining ~20 gaps are ALL hard (no cheap tenant-discovery left). Each needs either fragile
## per-site reverse-engineering (legacy-Taleo-ajax=Evergy, recruiting.com-WAF=Darden, ADP-RM=Sempra, custom=HCA/Fastenal/EOG)
## or a PAID keyed aggregator. Highest-ROI finish = one keyed provider (JSearch/RapidAPI or SerpAPI Google Jobs) that
## resolves all remaining gaps by company name in one shot (user has authorized paid APIs; key -> gitignored .env).

## Darden — BLOCKED (confirmed final). recruiting.com board: no job-list XHR (only paradox.ai chatbot + reCAPTCHA);
## jobs are server-rendered but the recruiting.com WAF 403s curl_cffi on every data path (/jobs, /api/jobs, sitemap),
## so the RUNTIME no-browser fetch can't reach them. reCAPTCHA on the board confirms bot-hardening. Not capturable
## without a runtime browser (forbidden). -> needs the paid-aggregator path.

## RUNNING TALLY of remaining-gap verdicts (per-site cracking ~exhausted; walls confirmed):
## WALLS (need paid aggregator): Darden(recruiting.com WAF), HCA-US(WAF), Fastenal(FCA CMS), EOG(.asp legacy),
##   Sempra(ADP-RM SPA), Evergy(legacy Taleo-ajax, 29 jobs), Regency+CBRE(Dayforce, no provider).
## STILL TO PROBE: Linde(gas), Smurfit Westrock, Roper, Tractor Supply, Targa, TransDigm, Texas Pacific Land,
##   Weyerhaeuser, Vici — but most are likely Workday/SF (probe with WebSearch-first next) or small/decentralized.

## 2026-06-21 per-site probes (more walls confirmed — per-site cracking now exhausted):
## - Targa Resources: SelectMinds SPA (targaresources.referrals.selectminds.com) — static HTML has no jobs/feed/JSON-LD;
##   JS-rendered. Needs XHR capture. ~118 jobs.
## - Smurfit Westrock: bespoke AFAS/Serena-CMS careers site — not a supported ATS. Wall.
## CONCLUSION: ~18 of the 20 remaining gaps are confirmed walls or non-standard JS SPAs. Per-site cracking yields
## mostly confirmed-walls now. The efficient finish is the PAID aggregator (JSearch/SerpAPI) — awaiting a key in .env.
## Holding at 483/503 = 96%. Do NOT keep re-probing these walls each run; resume captures when a paid key lands or a
## new lever appears.

## SF-RMK/DWR provider — CONCLUSIVELY NOT BUILDABLE no-browser (verdict final, do not re-attempt)
Re-attempted per explicit request. The DWR POST (careerJobSearchControllerProxy.*.dwr) requires an
x-csrf-token/x-ajax-token that is generated CLIENT-SIDE by SAP's obfuscated uicore JS at runtime.
Proven NOT extractable no-browser via 5 independent vectors: (1) not in careers HTML (no csrf/ajaxToken/
optr_cxt literals), (2) not in any Set-Cookie, (3) not in response headers, (4) SAP "X-CSRF-Token: Fetch"
returns nothing, (5) __System.generateId.dwr 404s. Replaying needs to run SAP's JS = a RUNTIME browser
(forbidden). Building a provider would only ever return 0. NOT SHIPPED by design.
ALTERNATIVE (already in place): CRH — the only known S&P member on SF-RMK/DWR — is captured via themuse
(500 jobs, commit 6b75b52). For any future SF-RMK/DWR-walled flagship, use themuse(brandname) — it's the
working no-browser fallback. See [[jobspine-sf-rmk-dwr-lever]].

## 2026-06-21 Dayforce lever (user's dayforce provider) — 2 captures:
- Regency Centers: DONE — dayforce token 'regency' (23 US REIT jobs). commit bb6144e.
- Packaging Corp of America: DONE — dayforce token 'pca' (362 jobs, Massillon OH etc.). commit 644a599.
- CBRE: NOT Dayforce — careers.cbre.com is an in-house/Oracle-style portal (External Careers Login). Still a gap.
- LEVER NOTE: Dayforce namespace discovery = WebSearch "{company} jobs.dayforcehcm.com candidate portal" -> grab the
  {namespace} from jobs.dayforcehcm.com/en-US/{ns}/CANDIDATEPORTAL, then dayforce provider token = {ns}. Works headless.

## 2026-06-21 dejobs (DirectEmployers) lever — cracks WAF-walled US giants! 3 captures:
- Tractor Supply: dejobs 'tractor-supply-company' (6000, Brentwood TN). commit 1885a77.
- HCA Healthcare: dejobs 'hca-healthcare' (6000/4662 US) — own site WAF-403'd, federation has it! commit 4c8c84e.
- EchoStar: dejobs 'echostar' (559/299 US) — was hardened-Workday-406. commit 4c8c84e.
- KEY LEVER: for any WAF-walled / hardened US employer, TRY dejobs FIRST with slug = hyphenated full name
  (e.g. 'hca-healthcare','tractor-supply-company'). DirectEmployers federates ~900 large US members; entity-clean
  (company_exact). NOT in dejobs: darden, fastenal, sempra, linde, transdigm, roper (tried, 0).

## 2026-06-21 provider-work iteration — 3 captures, crossed 98% (492/503):
- PPL Corporation: DONE — dejobs 'ppl-corporation' (193 US). Its iCIMS host (careers-pplweb, Jibe-skinned)
  is unreachable via our provider; federation had it. commit d16c433.
- Weyerhaeuser + Evergy: DONE — NEW taleo legacy-ftl-stream mode (commit beb36a4, captures ebf46f9).
  LEVER: legacy Taleo sites (jobsearch.ajax, no REST, no server-rendered rows) embed page-1 jobs in the
  jobsearch.ftl HTML as a '!|!'-delimited FTL-history stream. Signature per job: id‖title‖id‖title‖id×5‖
  <tenant-ordered columns>. Classify location/contestNo/date by TYPE (order varies per tenant). taleo
  provider now falls back to this when REST returns 0. PARTIAL (embedded first page ~25); full pagination
  needs the CSRF-gated ajax POST. Token: 'host.taleo.net|cs|'.

## 2026-06-21 EOG captured (493/503=98%):
- EOG Resources: DONE — apicapture spec on careers.eogresources.com (bespoke classic-ASP). 71 jobs.
  LEVER: apicapture html_table works on NON-table div layouts too — set row_css to the job container
  (div.list-group-item) and use regex columns ({"re": ...}) for id/title/location/url. No table needed.
  (The eeho.fa.us2 Oracle host was a WRONG-entity namesake — rejected; EOG's real board is the .asp.)
- Linde CORRECTION: lindecareers.com is custom SITECORE (VisitorIdentification.js, /-/media/), NOT Radancy.
  No job XHR; effectively a wall. The earlier "radancy" string was a red herring.
- Remaining 10 (none in dejobs/themuse): Darden(recruiting.com WAF), Ralph Lauren(Avature JS SPA),
  Fastenal(custom CMS), Targa(SelectMinds SPA), Sempra(ADP-RM), Roper+TransDigm(decentralized),
  Linde(Sitecore wall), Vici, Texas Pacific Land.

## 2026-06-21 iteration — Targa/Vici/TPL all blocked (no capture; 493/503=98% holds):
- Vici Properties: ⚠️ NAMESAKE TRAP — jobs.lever.co/vicicollection is "VICI" the women's CLOTHING brand
  (Associate Copywriter, Key Holder; Walnut Creek CA/Nashville). NOT VICI Properties (gaming REIT). DO NOT capture.
  VICI Properties (small REIT ~40 staff) has no discoverable public board.
- Texas Pacific Land: Paylocity guid 8cb850d5-bd0b-4ad3-a676-06b1a9cf2fac — but the board has the public FEED
  DISABLED (recruiting/v2/api/feed/jobs returns 0; displayName=guid). public-jobs-list returns the SPA shell, no
  job markup. Jobs load via a browser-backed/JWT call. Our paylocity provider only works on feed-enabled boards. WALL.
- Targa Resources: SelectMinds SPA — tile-search-results returns the SPA shell, not job data; the real data XHR
  doesn't fire without deeper interaction. WALL (needs full browser-session reverse-engineering).

## Sempra (ADP Recruiting-Management / myjobs) — API CRACKED except the session token (browser-backed wall)
Full no-browser recipe EXCEPT one gate:
1. GET https://myjobs.adp.com/public/staffing/v1/career-site/sempra  -> {orgoid:"G3AWJ7PAVPW7ZPAD", id, externalId:119707, isiClientId:SEMPRANRG}
2. GET https://my.adp.com/myadp_prefix/mycareer/public/staffing/v1/job-requisitions/apply-custom-filters
   ?$orderby=postingDate desc&$select=reqId,jobTitle,jobDescription,requisitionLocations,postingDate&$top=N&tz=...
   Headers: orgoid:<orgoid>, rolecode:manager, myjobstoken:<AWS-KMS-encrypted session token>
   -> clean JSON {count, jobRequisitions:[{reqId, jobTitle, requisitionLocations[].address.cityName, jobDescription,...}]}
   VERIFIED the response is real Sempra (San Diego; General Audit Associate, Executive Protection Agent, etc.).
BLOCKER: without myjobstoken -> 400 "Missing orgoid"; with orgoid but no token -> 400 "postingChannelId not found"
(the token encodes orgoid+postingChannel). The token is AWS-KMS encrypted (AQICAH...), minted via a browser-backed
session bootstrap (akamai pixel + firebase + SiteMinder login redirects). Legacy srccar (recruiting.adp.com/srccar)
301s into the same myjobs token flow. NEXT: find the no-auth endpoint that mints myjobstoken (dayforce-style curl_cffi
CSRF flow may work), then it's a clean apicapture GET-json. Until then: browser-backed wall.

## 2026-06-21 user-found URLs — 3 captured, Fastenal=Akamai-wall:
- Targa Resources: DONE — Taleo targaresources.taleo.net|ex|101430233 (114 jobs; user's apply URL gave the portal). commit 9853ddb.
- Ralph Lauren: DONE — avature careers.ralphlauren.com|CareersCorporate|SearchJobsCorporate. FULL 160 jobs via the new
  avature {page}Data/ endpoint (was 20 via RSS). LEVER: Avature SPA full board = GET /{portal}/{page}Data/ -> location-grouped JSON.
- Fastenal: WALL (confirmed) — load-jobs POST (DataTables, 596 jobs) is Akamai bot-managed; curl_cffi gets 403/timeout
  while my IP got flagged. Browser passes (JS sensor cookie). Not replayable no-browser. Same as Darden recruiting.com.
- Roper: user's haier.wd3 URL = GE Appliances (Roper CORPORATION namesake), NOT Roper Technologies. Rejected. Decentralized.

## ⚠️ PAYLOCITY PROVIDER IS NON-FUNCTIONAL vs live boards (2026-06-21 finding):
The public feed GET /recruiting/v2/api/feed/jobs/{guid} returns jobs=0 with displayName=<raw-guid>
(never the company name) for EVERY board tested (b181f77f, f40d1a02, c09eff2a, 1c38e30f, ff517f63,
5cc86a46, + TPL 8cb850d5). The careers pages also server-render 0 job-detail links — jobs load via a
JWT-gated SPA API (browser-backed). The documented public feed is effectively deprecated/opt-in-off.
=> The paylocity provider (built against the documented feed + synthetic tests) captures NOTHING live.
Treat Paylocity as a browser-backed WALL. Texas Pacific Land (its only S&P target) is therefore a WALL,
not capturable via this provider. Do NOT add paylocity seed entries expecting jobs.
