# Design: Browser-Assisted Discovery (gated, offline-only)

> **PREREQUISITE GATE — READ FIRST:** This subsystem is forbidden from touching any company that has
> not passed the [ATS-Exhaustion Ladder](../plans/2026-06-21-ats-exhaustion-ladder.md). Its **only**
> input is the `browser_queue.json` that the ladder emits (`ats_exhausted == true`). **Never assume a
> board needs a browser.** If you find yourself reaching for Playwright without an exhaustion log for
> that exact company, stop — run the ladder.

> **Status:** design (2026-06-21). Builds on the existing `apicapture` provider + one-time Playwright
> discovery (Tesla, EOG, CRH) + `build_registry.py` verify-gate.

---

## The one principle that makes this safe

**Move the rule from "no browser anywhere" → "no browser in the *request path*."** A browser never
runs during a user `search()`. It runs **only in offline jobs** (the daily index-build cron + a
discovery cron) and produces one of two cheap artifacts that the existing headless paths replay:

1. a **replay spec** (URL + method + body + response field-map) — captured once, replayed forever via curl_cffi;
2. a **short-lived session token/cookie** — minted on a schedule, cached with a TTL, replayed until expiry.

This is the industry-validated "discover-once, replay-cheap" pattern (careerscout; 2026 best-practice
literature: API endpoints are stable + structured, while browser-per-request is "unscalable due to
browser overhead").

## What it means for live-fetch vs. the index (the four-tier model)

| Tier | Sites | Capture | Browser? | Live-fetch | Index |
|---|---|---|---|---|---|
| **0** | most of our 57k (GH/Lever/Workday/Oracle/Taleo/SF/iCIMS/…) | public JSON / curl_cffi | never | direct replay | direct replay |
| **1** | SPA/own-API (Tesla, EOG, Avature-SPA, SelectMinds, recruiting.com) | **browser discovers the XHR once** → apicapture spec | discovery + when spec breaks | replay cached spec, browser-free | replay spec in crawl |
| **2** | JS-minted token (Akamai-sensor Fastenal/Darden, ADP-RM Sempra, Dayforce, Paylocity) | **cron browser mints token** → cached w/ TTL | only on the cron; never at query | replay w/ cached token; if stale → **serve from index** | cron refreshes token, then replays |
| **3** | Turnstile/hCaptcha + behavioral ML | (rare for ATSes) | — | aggregator fallback | skip/aggregator |

**Reconciliation:** the **index build (daily cron) is the home for ALL browser work** — discovery
sweeps, Tier-1 spec capture, Tier-2 token refresh — then the index is built from *headless replay*.
The index doesn't care how a board was reached. **Live fetch stays browser-free always**: Tier-0/1
replay specs; Tier-2 uses a cached token or falls back to the index. The user never waits on Chromium.
This preserves the production guarantee ("no browser in the request path") while letting us populate
aggressively offline. (jobhive already works this way — stealth-browser data lands in their published
*dataset*, the analog of our index.)

## Anti-bot landscape → ruthless ROI tiering

- **Sensor-cookie** (Akamai 512KB-obfuscated-JS `sensor_data`; DataDome 35+ behavioral signals;
  PerimeterX) = Fastenal/Darden. Cannot forge headlessly without running their JS. Free SOTA =
  **patched browsers**: Patchright (maintained patched-Playwright, drop-in), nodriver (undetected-chromedriver
  successor), Camoufox (Firefox C-level fingerprint spoof; beta), SeleniumBase UC, Byparr/FlareSolverr
  (Cloudflare). Winning principle: **believable, internally-consistent fingerprint** > any single trick.
- **Encrypted session token** (ADP-RM `myjobstoken`, Dayforce/Paylocity JWT). Don't fight the crypto —
  let a real browser mint it on the cron; cache w/ TTL. Cleanest Tier-2 win.
- **CAPTCHA** (Turnstile/hCaptcha): not auto-solvable free. Out of scope; aggregator fallback only.

## Production architecture (built for trust)

Reuses the existing **propose → live-verify → merge** seam (`candidates.json` → `build_registry.py`):

1. **`browser_discovery` module** — pooled, containerized Patchright/Camoufox worker; given a careers
   URL (from `browser_queue.json`), captures the job-list XHR (request+response shape) and
   **auto-proposes an apicapture spec** via a response-shape classifier (job-list vs single vs
   paginated + ATS-vocabulary field match). **Connect-don't-launch** to a CDP pool; per-domain
   concurrency + jittered pacing; consistent UA/locale/timezone/viewport.
2. **Token store** — Tier-2 tokens `{value, minted_at, ttl, refresh_on:[401,403]}`; **single-flight**
   refresh (no stampede); TTL-driven cron re-mint.
3. **Spec health + self-healing** — every spec carries `last_verified` + `success_rate`; *N consecutive
   0/403 → mark stale → auto-re-discover*. Nothing silently rots.
4. **Hard verify-gate (existing)** — a browser-discovered spec must return ≥1 **entity-correct** job
   through our own provider stack before it touches `seed.json`. Discovery is fallible; verification is not.
5. **Blast-radius control (existing)** — "good-or-nothing" index publish + data-quality gates: a flaky
   browser job can never corrupt the live index.
6. **Stack (free-only honored)** — Patchright primary; curl_cffi stays the replay layer; nodriver/Camoufox
   as escalation. No paid bypass APIs, no CAPTCHA services.
7. **Ethics/ToS** — public ATS job boards only (public data); respect robots; rate-limit; never
   auth-walled/PII. Materially more defensible than LinkedIn/Indeed board-scraping (which stays a later,
   isolated, opt-in step).

## Rollout (patient, intentional)

1. **Phase 1 — generalize Tier-1** (discover-once, replay-forever). We already have apicapture +
   one-time Playwright discovery. Build the reusable `browser_discovery` + auto-spec + response-shape
   classifier; wire the dormant `aresolve()` into a registry-enrichment cron. Highest ROI, lowest risk.
2. **Phase 2 — Tier-2 token subsystem.** Token store + cron mint + replay-with-refresh. Start where the
   API is already cracked (ADP-RM/Sempra, Dayforce), then sensor-cookie (Fastenal/Darden) via Patchright/nodriver.
3. **Phase 3 — web-scale discovery at volume** (Common Crawl pagination, GitHub code search, passive DNS)
   → same verify-gate → aggressively grow the registry.
4. **Phase 4 — distribute** (PyPI + one-line MCP) once Tier-1/2 are production-solid.
5. **Phase 5 — JobSpy board-scraping** (LinkedIn/Indeed/Glassdoor), isolated/opt-in/off-by-default.

## References
- Predecessor gate: [`2026-06-21-ats-exhaustion-ladder.md`](../plans/2026-06-21-ats-exhaustion-ladder.md)
- Landscape: [`docs/landscape-job-fetching-tools.md`](../../landscape-job-fetching-tools.md)
- Roadmap: [`docs/expansion-roadmap.md`](../../expansion-roadmap.md)
- Lever notes: `runs/flagship_targets.md`; memory `jobspine-sf-rmk-dwr-lever`, `jobspine-flagship-capture`.
