"""Census the H-1B gap for SuccessFactors career sites -> verified candidates.json.

The SuccessFactors provider exists, so any uncovered H-1B sponsor on SuccessFactors is
recoverable now with zero new code — we just need to find each sponsor's career host +
siteid. Unlike Eightfold, SF sites are server-rendered HTML on the company's OWN domain
(careers.{co}.com/{siteid}/...), so detection is browser-free:

  1. Tavily-search ``{sponsor} careers`` (aggregators excluded) for the company's pages.
  2. Detect SF two ways: (a) a result URL is already an SF job/search URL
     (SuccessFactorsProvider.matches), or (b) the top career host's landing HTML carries
     an SF signature (successfactors / jobs2web / sitemal.xml / rmkcdn) and a
     ``/{siteid}/(search|job)/`` link to mine the siteid from.
  3. Provenance + verify gate: require a significant sponsor word in the host/siteid
     (the careers domain is the company's own), then fetch live (limit=1) through the
     provider. Only boards returning >=1 job and not already seeded are emitted.

Usage::

    .venv/bin/python scripts/census_successfactors.py [--out scripts/candidates_sf.json] [--cap N]
    .venv/bin/python scripts/build_registry.py scripts/candidates_sf.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_commoncrawl import load_seed_keys  # noqa: E402
from harvest_tavily import load_key  # noqa: E402

from ergon_tracker.http import AsyncFetcher  # noqa: E402
from ergon_tracker.models import SearchQuery  # noqa: E402
from ergon_tracker.providers.successfactors import SuccessFactorsProvider  # noqa: E402

DEFAULT_OUT = ROOT / "scripts" / "candidates_sf.json"
GAP = ROOT / "runs" / "h1b_coverage_gap.json"
MIDTIER = ROOT / "runs" / "h1b_gap_midtier.json"
_API = "https://api.tavily.com/search"
EXCLUDE = [
    "linkedin.com",
    "indeed.com",
    "ziprecruiter.com",
    "glassdoor.com",
    "wikipedia.org",
    "levels.fyi",
    "builtin.com",
    "simplyhired.com",
    "monster.com",
    "dice.com",
    "myvisajobs.com",
    "h1bdata.info",
    "trackitt.com",
    "salary.com",
    "google.com",
]
_SIG = ("successfactors", "jobs2web", "sitemal.xml", "rmkcdn", "/services/rss/job")
_SITEID_RE = re.compile(r'href="/([a-z0-9][a-z0-9-]*)/(?:search|job)/', re.IGNORECASE)
_SF = SuccessFactorsProvider()


def _collapse(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _name_ok(sponsor: str, token: str) -> bool:
    """Provenance: a significant sponsor word appears in the host or siteid (collapsed)."""
    blob = _collapse(token)
    words = [
        _collapse(w)
        for w in re.sub(r"[^a-z0-9 ]", " ", sponsor.lower()).split()
        if len(w) >= 4
        and w
        not in (
            "services",
            "group",
            "technologies",
            "company",
            "corp",
            "inc",
            "international",
            "global",
            "solutions",
            "systems",
            "consulting",
        )
    ]
    return any(w in blob for w in words) or _collapse(sponsor)[:10] in blob


def _hosts(urls: list[str]) -> list[str]:
    out: list[str] = []
    for u in urls:
        m = re.match(r"https?://([^/]+)", u or "")
        if m:
            h = m.group(1).lower()
            if h not in out and not any(x in h for x in EXCLUDE):
                out.append(h)
    return out


async def tavily(sponsor: str, key: str, fetcher: AsyncFetcher) -> list[str]:
    body = {"query": f"{sponsor} careers jobs", "exclude_domains": EXCLUDE, "max_results": 5}
    try:
        data = await fetcher.post_json(_API, json=body, headers={"Authorization": f"Bearer {key}"})
    except Exception:  # noqa: BLE001
        return []
    return [r.get("url", "") for r in (data.get("results", []) if isinstance(data, dict) else [])]


async def detect(sponsor: str, urls: list[str], fetcher: AsyncFetcher) -> str | None:
    """Return an SF ``"{host}|{siteid}"`` token for the sponsor, else None."""
    # (a) a result URL is already an SF job/search URL
    for u in urls:
        tok = _SF.matches(u)
        if tok and _name_ok(sponsor, tok):
            return tok
    # (b) probe the top career hosts for an SF signature + a siteid link
    for host in _hosts(urls)[:3]:
        try:
            html = await fetcher.get_text(f"https://{host}/")
        except Exception:  # noqa: BLE001
            continue
        if not any(s in html.lower() for s in _SIG):
            continue
        m = _SITEID_RE.search(html)
        if m:
            tok = f"{host}|{m.group(1).lower()}"
            if _name_ok(sponsor, tok):
                return tok
    return None


async def main() -> None:
    args = sys.argv[1:]
    out_path = DEFAULT_OUT
    cap = 2500
    i = 0
    while i < len(args):
        if args[i] == "--out":
            out_path = Path(args[i + 1])
            i += 2
        elif args[i] == "--cap":
            cap = int(args[i + 1])
            i += 2
        else:
            print(f"unknown flag: {args[i]}")
            return

    key = load_key()
    if not key:
        print("TAVILY_API_KEY not set.")
        return

    # Merge the top-1000 and mid-tier gap lists, dedup by name, highest filings first.
    sponsors: dict[str, dict] = {}
    for f in (GAP, MIDTIER):
        if f.exists():
            for s in json.loads(f.read_text()).get("uncovered_top", []):
                cur = sponsors.get(s["name"])
                if cur is None or s.get("filings", 0) > cur.get("filings", 0):
                    sponsors[s["name"]] = s
    todo = sorted(sponsors.values(), key=lambda s: -s.get("filings", 0))[:cap]
    seed_keys = load_seed_keys()
    print(f"SF census over {len(todo)} uncovered sponsors ...", flush=True)

    # Phase 1: Tavily + detect (concurrent).
    tokens: dict[int, str] = {}
    done = [0]

    async def find(idx: int, sponsor: dict, fetcher: AsyncFetcher) -> None:
        urls = await tavily(sponsor["name"], key, fetcher)
        tok = await detect(sponsor["name"], urls, fetcher)
        if tok:
            tokens[idx] = tok
        done[0] += 1
        if done[0] % 200 == 0:
            print(f"  scanned {done[0]}/{len(todo)} (SF hits so far: {len(tokens)})", flush=True)

    async with (
        AsyncFetcher(concurrency=16, per_host_rate=6, timeout=20.0) as fetcher,
        anyio.create_task_group() as tg,
    ):
        for idx, s in enumerate(todo):
            tg.start_soon(find, idx, s, fetcher)

    print(f"detected {len(tokens)} SF candidates; verifying live ...", flush=True)

    # Phase 2: verify each token live (limit=1) through the provider; keep live + unseeded.
    candidates: list[dict] = []
    taken: set[str] = set()

    async def verify(idx: int, token: str, fetcher: AsyncFetcher) -> None:
        siteid = token.split("|", 1)[1]
        if siteid in seed_keys or siteid in taken:
            return
        try:
            raws = await _SF.fetch(token, SearchQuery(limit=1), fetcher)
        except Exception:  # noqa: BLE001
            raws = []
        if raws:
            taken.add(siteid)
            candidates.append(
                {
                    "company": siteid,
                    "ats": "successfactors",
                    "token": token,
                    "domain": None,
                    "_sponsor": todo[idx]["name"],
                    "_filings": todo[idx].get("filings"),
                }
            )

    async with (
        AsyncFetcher(concurrency=10, per_host_rate=6, timeout=25.0) as fetcher,
        anyio.create_task_group() as tg,
    ):
        for idx, token in tokens.items():
            tg.start_soon(verify, idx, token, fetcher)

    candidates.sort(key=lambda c: -(c.get("_filings") or 0))
    for c in candidates:
        print(f"  + {c['_sponsor'][:32]:32} ({c.get('_filings') or 0:>5} filings) -> {c['token']}")
    out = [{k: v for k, v in c.items() if not k.startswith("_")} for c in candidates]
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    try:
        shown = out_path.relative_to(ROOT)
    except ValueError:
        shown = out_path
    print(f"\nwrote {len(out)} SF candidates -> {shown}")
    print(f"next: .venv/bin/python scripts/build_registry.py {shown}")


if __name__ == "__main__":
    anyio.run(main)
