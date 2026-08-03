# Job Hunt Agent

A private Notion-backed autumn recruitment tracker exposed as a Python MCP server.

The project is designed for AI Agent and LLM application engineer recruiting. Public code,
schemas, prompts, tests, and synthetic examples live in GitHub. Real applications,
interview notes, contacts, Notion page URLs, and API keys stay outside the repository.

## Local Usage

```bash
rtk python -m pytest -q
```

Configure credentials through environment variables. Never commit `.env`.

## Privacy Boundary

- Notion is the source of truth for real job-search data.
- GitHub contains code and synthetic examples only.
- DeepSeek and Notion secrets are read from environment variables only.

## Notion Setup

See `docs/notion-setup.md`. The first local milestone can run entirely on the in-memory
repository used by tests. Real Notion writes are enabled only after private database IDs
and token are configured locally.

## Verification

```bash
rtk python -m pytest -q
rtk python scripts/privacy_scan.py README.md docs examples src tests
```
