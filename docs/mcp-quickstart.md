# MCP quickstart — use ergon-tracker from Claude (and other agents)

ergon-tracker ships an [MCP](https://modelcontextprotocol.io) server so an LLM can search jobs,
resolve a company's ATS, and list sources — as native tools.

## Tools exposed

| Tool | What it does |
|---|---|
| `search_jobs` | Unified, deduped, relevance-ranked search across all 22 sources. Accepts `keywords`, `location`, `remote`, `companies`, `sources`, `level`, `sector`, `country`, `city`, `salary_min/max`, `semantic`, `limit`. Returns compact jobs each with a relevance `score`, plus per-source `health`. |
| `resolve_company` | Detect which ATS a domain/careers URL uses and its board token. |
| `list_sources` | List registered providers + the bundled registry size. |

## Install

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
