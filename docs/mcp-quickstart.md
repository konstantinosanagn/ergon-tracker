# MCP quickstart — use ergon-tracker from Claude (and other agents)

ergon-tracker ships an [MCP](https://modelcontextprotocol.io) server so an LLM can search jobs,
resolve a company's ATS, and list sources — as native tools.

## Tools exposed

| Tool | What it does |
|---|---|
| `search_jobs` | Unified, deduped, relevance-ranked search across 30+ sources. Accepts `keywords`, `location`, `remote`, `companies`, `sources`, `level`, `sector`, `country`, `city`, `salary_min/max`, `visa_sponsor`, `sponsorship_offered`, `semantic`, `limit`. Returns compact jobs each with a relevance `score`, `visa_sponsor`/`visa_last_filed`, and `sponsorship_offered`, plus per-source `health`. |
| `list_h1b_sponsors` | Browse employers known to sponsor H-1B visas (US DoL LCA data), ranked by filing volume, with the most-recent filing date. Covers far more employers than we can fetch jobs for. |
| `resolve_company` | Detect which ATS a domain/careers URL uses and its board token. |
| `list_sources` | List registered providers + the bundled registry size. |

## Install

### Option A — from PyPI (one line, recommended)

Once published (see [Publishing](#publishing-maintainers)), no clone or venv is needed:

```bash
uv tool install ergon-tracker          # or: pipx install ergon-tracker
# adds `ergon-tracker` + `ergon-tracker-mcp` to your PATH; the registry (57k+ boards) is bundled
```

Or run the MCP server with **zero install** via `uvx` (auto-fetches + runs) — see the config below.

### Option B — from source (today / contributors)

```bash
git clone https://github.com/konstantinosanagn/ergon-tracker
cd ergon-tracker
uv venv && uv pip install -e ".[mcp]"
# optional: add ".[semantic]" to enable semantic=true (embedding) ranking
```

Confirm it runs:

```bash
ergon-tracker-mcp        # starts the stdio server (Ctrl-C to stop)
```

## Claude Desktop

Edit the config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ergon-tracker": {
      "command": "ergon-tracker-mcp"
    }
  }
}
```

If `ergon-tracker-mcp` isn't on Claude Desktop's PATH, use the absolute path to the console
script inside your venv (e.g. `/path/to/ergon-tracker/.venv/bin/ergon-tracker-mcp`), or run via
your environment manager:

```json
{
  "mcpServers": {
    "ergon-tracker": {
      "command": "uv",
      "args": ["run", "--project", "/abs/path/to/ergon-tracker", "ergon-tracker-mcp"]
    }
  }
}
```

To enable the keyed sources (Adzuna/USAJOBS) and/or semantic tuning, pass env vars:

```json
{
  "mcpServers": {
    "ergon-tracker": {
      "command": "ergon-tracker-mcp",
      "env": {
        "ADZUNA_APP_ID": "...",
        "ADZUNA_APP_KEY": "...",
        "USAJOBS_API_KEY": "...",
        "USAJOBS_EMAIL": "you@example.com"
      }
    }
  }
}
```

(The server also reads a `.env` in the repo root, so setting `env` here is optional if you've
created that file.)

Restart Claude Desktop. You should see `ergon-tracker` listed under the tools/🔌 menu.

## Claude Code

```bash
claude mcp add ergon-tracker -- ergon-tracker-mcp
```

Then in a session: *"use ergon-tracker to find senior backend roles in Germany over €80k."* The
model translates that into a `search_jobs` call (`keywords`, `country`, `level`, `salary_min`),
and gets back deduped, relevance-ranked postings with scores.

## Example tool call

```jsonc
// search_jobs
{
  "keywords": "machine learning",
  "country": "United States",
  "level": "senior",
  "remote": true,
  "semantic": true,
  "limit": 15
}
```

Returns:

```jsonc
{
  "count": 15,
  "jobs": [
    {
      "company": "...", "title": "Senior ML Engineer", "location": "Remote, US",
      "level": "senior", "salary": { "min": 180000, "max": 240000, "currency": "USD" },
      "apply_url": "https://...", "source": "greenhouse",
      "found_on": ["greenhouse", "remoteok"], "score": 12.34
    }
  ],
  "health": [ { "source": "greenhouse", "ok": true, "count": 41 } ]
}
```

## Example prompts (what to ask your agent)

These phrasings lead the agent to efficient, rate-limit-safe `search_jobs` calls. An *unscoped*
search (no company, no source) automatically uses only the fast single-call aggregator/keyed
APIs — so you can't accidentally trigger the slow ~42k-company ATS crawl.

**🎯 Company-specific (fastest, most precise)**
- "Show me open engineering roles at Stripe and Ramp."
- "What ATS does notion.so use, then list their product roles." *(resolve_company → search_jobs)*
- "Find data roles at datadog.com and mongodb.com, senior and up."

**🔍 Broad keyword search (auto-routes to the fast APIs)**
- "Find remote senior backend engineer jobs, top 15."
- "Show me 20 remote data-science jobs in the US paying over $150k."
- "Entry-level software jobs in Berlin — and keep ones that don't state a level too."
  *(sets `include_unknown_level`)*

**🧠 Natural-language / semantic** *(needs the `[semantic]` extra)*
- "Find roles about LLMs and applied AI, even if they don't use those exact words." *(`semantic=true`)*
- "Jobs that sound like 'building developer tools at an early-stage startup'."

**🏛️ Federal (USAJOBS)**
- "Find senior data scientist federal jobs in Washington DC."

**🛂 Visa sponsorship (for international applicants)**
- "Find software roles at companies that sponsor H-1B and hide postings that say no sponsorship."
  *(`visa_sponsor=true` + `sponsorship_offered=true`)*
- "Which of Stripe, Ramp, and Databricks sponsor H-1B, and when did they last file?"
  *(`list_h1b_sponsors` / `visa_last_filed`)*
- "Show the biggest H-1B sponsors in fintech." *(`list_h1b_sponsors`)*

**📄 From a résumé**
- "Here's my résumé: [paste]. Find relevant roles that sponsor H-1B, ranked by fit."
  The agent extracts your skills/level/location, calls `search_jobs` (with `semantic=true`,
  `visa_sponsor=true`), then ranks the results against your résumé. (The MCP doesn't read files —
  paste the text into the chat; the agent does the matching.)

**🎛️ Power filters (combine anything)**
- "Senior fintech backend roles over $160k — keep ones that don't list a level or sector too."
  *(`sector`, `level`, `salary_min`, `include_unknown_level`, `include_unknown_sector`)*
- "Find senior developer jobs, and infer seniority from required years when the title omits it."
  *(`infer_level_from_experience=true`)*
- "Search only Greenhouse, Lever and Ashby for Rust roles." *(explicit `sources=[…]`)*
- "Remote ML jobs at H-1B sponsors that recently filed, over $150k, ranked by meaning."
  *(`visa_sponsor` + `semantic` + `salary_min` + read `visa_last_filed`)*

### Tips so the agent stays fast and answers cleanly

1. **Imply a count** ("top 10/20") — keeps the tool response small and the answer quick.
2. **Name companies** when you care about specific employers — the precise, fastest route.
3. **Don't ask to "search every company / the whole registry."** That's the one slow path; the
   server guards against it by default, but explicitly demanding it is still a long crawl.
4. **Widen strict filters when needed** — add "include roles that don't list a level/salary" so
   level/sector filters narrow instead of hard-dropping unlabeled postings.

## Zero-install (uvx) — recommended once published

No clone, no venv, no PATH juggling — `uvx` fetches and runs the published package on demand:

```json
{
  "mcpServers": {
    "ergon-tracker": {
      "command": "uvx",
      "args": ["--from", "ergon-tracker[mcp]", "ergon-tracker-mcp"]
    }
  }
}
```

Add `"env": {"ADZUNA_APP_ID": "...", ...}` exactly as in the sections above to enable keyed sources.

## Publishing (maintainers)

The package is PyPI-ready (`pyproject.toml` carries full metadata; the registry + `schema.sql` ship
inside the wheel). Build and publish with:

```bash
uv pip install --python .venv/bin/python build twine
.venv/bin/python -m build --no-isolation        # -> dist/*.whl + *.tar.gz
.venv/bin/twine check dist/*                     # validates PyPI metadata (must PASS)
.venv/bin/twine upload dist/*                    # needs a PyPI token; tag the release first
```

Verified: clean-venv `pip install ergon-tracker[mcp]` imports, registers all providers, and loads the
bundled `seed.json` (57k+ boards); both `ergon-tracker` and `ergon-tracker-mcp` console scripts work.
