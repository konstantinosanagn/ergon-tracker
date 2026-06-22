"""ATS-Exhaustion Sweep — the standardized ladder runner (predecessor to ANY browser work).

For each company, walk the ATS-exhaustion ladder **in order**, stop at the first rung that yields an
**entity-correct** hit (adjudicated through our own provider stack), and record every rung's outcome.
A company becomes "browser-eligible" ONLY after every autonomous rung is logged as failed.

    THE GATE: never assume a board needs a browser. The browser subsystem consumes ONLY the
    `browser_queue.json` this script emits (`ats_exhausted == true`). See
    docs/superpowers/plans/2026-06-21-ats-exhaustion-ladder.md.

Ladder rungs this runner executes autonomously (no WebSearch / no manual / no browser):
  0  registry hit            — already in seed.json? (skip; already captured)
  1  correct-tenant discovery — curl_cffi the careers page; extract ATS URLs; provider.matches() -> fetch
  2  brute-force token disc.  — harvest_tokens.probe_company (path-based + icims/taleo host guesses)
  5  federation/aggregator    — dejobs (hyphenated slug) + themuse (brand name), entity-clean
  7  schema.org               — JSON-LD / job sitemap via the schemaorg provider

Rungs 3 (WebSearch the apply URL) and 6 (bespoke apicapture spec) are NOT autonomously scriptable;
they are logged as `deferred: needs agent/manual` so a human/agent pass can complete them before a
board is declared browser-eligible. Rung 4 (per-provider mode variants) is folded into rung 1 (every
ATS URL found is run through that provider, whose own token-form logic covers its modes).

Propose, don't dispose: emits `candidates.json` (compatible with build_registry.py, which live-verifies
again before merging) + `browser_queue.json` (the genuine residual) + one append-only log per company.

Usage::
    .venv/bin/python scripts/ats_exhaustion_sweep.py scripts/companies_to_probe.txt --limit 100
    .venv/bin/python scripts/ats_exhaustion_sweep.py --gaps        # sweep current S&P 500 gaps
    .venv/bin/python scripts/build_registry.py scripts/cand_exhaustion.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ergon_tracker.http import AsyncFetcher  # noqa: E402
from ergon_tracker.models import SearchQuery  # noqa: E402
from ergon_tracker.providers.base import (  # noqa: E402
    get_provider,
    iter_providers,
    load_builtins,
)

# Reuse the proven brute-force + entity-adjudication logic (do not reinvent).
from harvest_tokens import (  # noqa: E402
    company_key,
    load_existing,
    name_match,
    parse_companies,
    probe_company,
)

LOG_DIR = ROOT / "runs" / "exhaustion"
OUT_CANDIDATES = ROOT / "scripts" / "cand_exhaustion.json"
OUT_BROWSER_QUEUE = ROOT / "scripts" / "browser_queue.json"
PROBE = SearchQuery(limit=8)  # small live probe; enough to adjudicate entity

# ATS host/URL signatures to pull out of a careers page (rung 1). Each captured URL is handed to
# every provider's matches() — the provider's own logic maps it to a token (and thus its modes).
_ATS_URL_RE = re.compile(
    r"https?://[^\s\"'<>]*?(?:"
    r"myworkdayjobs\.com|oraclecloud\.com|\.icims\.com|successfactors\.(?:com|eu)|\.taleo\.net|"
    r"phenompeople\.com|\.recruiting\.com|avature\.net|dayforcehcm\.com|ultipro\.com|"
    r"pageuppeople\.com|jobvite\.com|brassring\.com|applytojob\.com|jazz\.co|jazzhr|"
    r"radancy|talentbrew|/search-jobs|smartrecruiters\.com|boards\.greenhouse\.io|"
    r"jobs\.lever\.co|jobs\.ashbyhq\.com|paylocity\.com|recruiting\.adp\.com|workforcenow\.adp\.com"
    r")[^\s\"'<>]*",
    re.IGNORECASE,
)
# Careers-page URL candidates derived from a bare domain (cheapest first).
_CAREERS_PATHS = ("https://{d}/careers", "https://careers.{d}", "https://jobs.{d}",
                  "https://www.{d}/careers", "https://{d}/jobs")


def _adjudicate(company: str, raws: list, provider, trust: bool = False) -> bool:
    """True if the provider returned >=1 job that plausibly IS this company.

    `trust=True` for entity-clean federations (dejobs/themuse expose company_exact). Otherwise we
    guard slug collisions with name_match against the board's reported company + a title sample.
    """
    if not raws:
        return False
    if trust:
        return True
    boards = {str(getattr(r, "company", "") or "") for r in raws[:5]}
    return any(name_match(company, b) for b in boards if b)


async def _careers_html(domain: str | None, fetcher: AsyncFetcher) -> str:
    """Fetch the company's careers page (curl_cffi TLS — careers pages are often WAF'd)."""
    if not domain:
        return ""
    from curl_cffi.requests import AsyncSession

    # Tight per-URL timeout: some careers hosts (Akamai/WAF) tarpit non-browser clients, so a long
    # timeout × several URL candidates can hang a worker. Fail fast and let later rungs/queue handle it.
    async with AsyncSession(impersonate="chrome124", verify=False, timeout=8) as s:
        for tmpl in _CAREERS_PATHS:
            url = tmpl.format(d=domain)
            try:
                r = await s.get(url, allow_redirects=True)
            except Exception:
                continue
            if r.status_code == 200 and len(r.text) > 1500:
                return r.text
    return ""


async def _rung1_tenant_discovery(
    name: str, domain: str | None, fetcher: AsyncFetcher
) -> tuple[dict | None, str]:
    """Grep the careers page for ATS URLs; map each via provider.matches(); fetch + adjudicate."""
    html = await _careers_html(domain, fetcher)
    if not html:
        return None, "no careers page resolved from domain" if domain else "no domain given"
    urls = list(dict.fromkeys(_ATS_URL_RE.findall(html)))[:25]
    if not urls:
        return None, "careers page has no recognizable ATS host"
    providers = list(iter_providers())
    tried: list[str] = []
    for url in urls:
        for prov in providers:
            try:
                token = prov.matches(url)
            except Exception:
                token = None
            if not token:
                continue
            tag = f"{prov.name}|{token}"
            if tag in tried:
                continue
            tried.append(tag)
            try:
                raws = await prov.fetch(token, PROBE, fetcher)
            except Exception:
                continue
            if _adjudicate(name, raws, prov):
                return {"company": company_key(name), "ats": prov.name, "token": token,
                        "domain": domain}, f"HIT via {tag}"
    return None, f"{len(tried)} (provider,token) candidates from careers page, none entity-correct"


async def _rung5_federation(name: str, domain: str | None, fetcher: AsyncFetcher) -> tuple[dict | None, str]:
    """DirectEmployers (dejobs) + The Muse — entity-clean fallbacks for WAF-walled giants."""
    slug = company_key(name)  # hyphenated, e.g. "hca-healthcare"
    pd = get_provider("dejobs")
    for tok in (slug, slug.replace("-", "")):
        try:
            raws = await pd.fetch(tok, PROBE, fetcher)
        except Exception:
            raws = []
        if _adjudicate(name, raws, pd, trust=True) and raws:
            return {"company": slug, "ats": "dejobs", "token": tok, "domain": domain}, f"HIT dejobs|{tok}"
    pm = get_provider("themuse")
    brand = re.sub(r"\b(inc|corp|corporation|co|company|plc|ltd|group|holdings)\b\.?", "",
                   name, flags=re.I).strip()
    try:
        raws = await pm.fetch(brand, PROBE, fetcher)
    except Exception:
        raws = []
    if raws and _adjudicate(name, raws, pm, trust=True):
        return {"company": slug, "ats": "themuse", "token": brand, "domain": domain}, f"HIT themuse|{brand}"
    return None, "not in dejobs/themuse federation"


async def _rung7_schemaorg(name: str, domain: str | None, fetcher: AsyncFetcher) -> tuple[dict | None, str]:
    """JSON-LD / job-sitemap via the schemaorg provider (lowest-priority generic surface)."""
    if not domain:
        return None, "no domain for schema.org"
    p = get_provider("schemaorg")
    for tok in (f"https://{domain}/careers", f"careers.{domain}", domain):
        try:
            raws = await p.fetch(tok, PROBE, fetcher)
        except Exception:
            raws = []
        if raws and _adjudicate(name, raws, p):
            return {"company": company_key(name), "ats": "schemaorg", "token": tok, "domain": domain}, \
                f"HIT schemaorg|{tok}"
    return None, "no JSON-LD/sitemap jobs"


async def exhaust_one(
    name: str, domain: str | None, fetcher: AsyncFetcher, existing_keys: set[str]
) -> dict[str, Any]:
    """Walk the ladder for one company; short-circuit on first entity-correct hit; log every rung."""
    key = company_key(name)
    log: list[dict[str, str]] = []
    record: dict[str, Any] = {"company": key, "name": name, "domain": domain, "rungs": log}

    # Rung 0 — already captured?
    if key in existing_keys:
        record.update(status="already-in-registry", ats_exhausted=False)
        log.append({"rung": "0", "method": "registry", "result": "already in seed.json"})
        return record

    # Rungs 1, 2, 5, 7 in order — stop at first hit.
    rungs = [
        ("1", "correct-tenant-discovery", lambda: _rung1_tenant_discovery(name, domain, fetcher)),
        ("2", "harvest_tokens", lambda: _probe_rung2(name, domain, fetcher)),
        ("5", "dejobs/themuse", lambda: _rung5_federation(name, domain, fetcher)),
        ("7", "schemaorg", lambda: _rung7_schemaorg(name, domain, fetcher)),
    ]
    for num, method, run in rungs:
        try:
            cand, note = await run()
        except Exception as exc:  # noqa: BLE001 — record, never crash the sweep
            cand, note = None, f"error: {type(exc).__name__}: {exc}"[:100]
        log.append({"rung": num, "method": method, "result": note})
        if cand:
            record.update(status="captured", candidate=cand, ats_exhausted=False)
            return record

    # Rungs 3 & 6 are not autonomously scriptable — flag for an agent/manual pass before browser.
    log.append({"rung": "3", "method": "websearch-apply-url", "result": "deferred: needs agent/manual"})
    log.append({"rung": "6", "method": "apicapture-bespoke", "result": "deferred: needs agent/manual"})
    record.update(status="ats-exhausted", ats_exhausted=True,
                  browser_tier_hint=None)  # tier hint set by the agent/manual pass
    return record


async def _probe_rung2(name: str, domain: str | None, fetcher: AsyncFetcher) -> tuple[dict | None, str]:
    """Rung 2 wrapper around harvest_tokens.probe_company (path-based + icims/taleo host guesses)."""
    cand = await probe_company(name, domain, fetcher)
    if cand:
        return cand, f"HIT {cand.get('ats')}|{cand.get('token')}"
    return None, "no path-based/icims/taleo token matched"


async def run_sweep(companies: list[tuple[str, str | None]], concurrency: int) -> dict[str, Any]:
    load_builtins()
    existing_keys, _ = load_existing()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    sem = anyio.Semaphore(concurrency)

    async def worker(name: str, domain: str | None) -> None:
        async with sem:
            rec: dict[str, Any] = {"company": company_key(name), "name": name, "domain": domain,
                                   "rungs": [], "status": "timeout", "ats_exhausted": False}
            # Hard per-company deadline: a tarpitting host can never stall the whole sweep. A
            # timed-out company is NOT sent to the browser queue (it wasn't proven exhausted) — re-run it.
            with anyio.move_on_after(90):
                async with AsyncFetcher(retries=1, timeout=12, per_host_rate=4) as f:
                    rec = await exhaust_one(name, domain, f, existing_keys)
            (LOG_DIR / f"{rec['company']}.json").write_text(json.dumps(rec, indent=1))
            results.append(rec)

    async with anyio.create_task_group() as tg:
        for nm, dom in companies:
            tg.start_soon(worker, nm, dom)

    candidates = [r["candidate"] for r in results if r.get("status") == "captured"]
    browser_queue = [
        {"company": r["company"], "name": r["name"], "domain": r["domain"],
         "exhaustion_log": r["rungs"]}
        for r in results if r.get("ats_exhausted")
    ]
    OUT_CANDIDATES.write_text(json.dumps(candidates, indent=1))
    OUT_BROWSER_QUEUE.write_text(json.dumps(browser_queue, indent=1))
    return {
        "total": len(results),
        "already": sum(1 for r in results if r.get("status") == "already-in-registry"),
        "captured": len(candidates),
        "browser_eligible": len(browser_queue),
    }


def _load_gap_companies() -> list[tuple[str, str | None]]:
    """The current S&P 500 gaps (from the crosswalk) — a ready-made target set for --gaps."""
    import subprocess

    out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "sp500_crosswalk.py")]).decode()
    return [(line.split("] ", 1)[1].strip(), None)
            for line in out.splitlines() if re.match(r"\s*\[", line) and "] " in line]


def main() -> None:
    ap = argparse.ArgumentParser(description="ATS-exhaustion ladder sweep (predecessor to browser work)")
    ap.add_argument("input", nargs="?", help="companies file: 'Name[,domain]' per line")
    ap.add_argument("--gaps", action="store_true", help="sweep the current S&P 500 crosswalk gaps")
    ap.add_argument("--limit", type=int, default=0, help="cap number of companies (0 = all)")
    ap.add_argument("--concurrency", type=int, default=12)
    args = ap.parse_args()

    if args.gaps:
        companies = _load_gap_companies()
    elif args.input:
        companies = parse_companies(Path(args.input).read_text())
    else:
        ap.error("provide a companies file or --gaps")
    if args.limit:
        companies = companies[: args.limit]

    summary = anyio.run(run_sweep, companies, args.concurrency)
    print(f"swept {summary['total']} | already={summary['already']} | "
          f"captured={summary['captured']} -> {OUT_CANDIDATES.name} | "
          f"browser-eligible={summary['browser_eligible']} -> {OUT_BROWSER_QUEUE.name}")
    print(f"per-company logs: {LOG_DIR.relative_to(ROOT)}/")
    if summary["captured"]:
        print(f"NEXT: .venv/bin/python scripts/build_registry.py {OUT_CANDIDATES.relative_to(ROOT)} --dry-run")


if __name__ == "__main__":
    main()
