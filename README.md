# Job Hunt Agent

A private Notion-backed autumn recruitment tracker exposed as a Python MCP server.

The project is designed for AI Agent and LLM application engineer recruiting. Public code,
schemas, prompts, tests, and synthetic examples live in GitHub. Real applications,
interview notes, contacts, Notion page URLs, and API keys stay outside the repository.

Core tools record applications, update stages, save interview notes, analyze interviews,
list follow-ups across applications/interviews/review tasks, and generate daily or weekly
reviews.

## Local Usage

```bash
rtk python -m pytest -q
```

Configure credentials through environment variables. Never commit `.env`.

After sharing a private Notion parent page with your integration, bootstrap the Notion
tables locally:

```bash
rtk python scripts/notion_bootstrap.py
```

## Privacy Boundary

- Notion is the source of truth for real job-search data.
- GitHub contains code and synthetic examples only.
- DeepSeek and Notion secrets are read from environment variables only.

## Notion Setup

See `docs/notion-setup.md`. The bootstrap script creates the private Notion data sources
and stores their IDs in local user environment variables. Real Notion writes are enabled
only after the token and generated IDs are configured locally.

## Verification

```bash
rtk python -m pytest -q
rtk python scripts/privacy_scan.py README.md docs examples src tests
```
