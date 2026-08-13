# Text-First Notion Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the private Notion `秋招总览` page prioritize a readable text dashboard while preserving databases as backend detail views.

**Architecture:** Render a deterministic text summary from repository records, then use Notion block APIs to append a managed generated section on the overview page. The existing four linked database views remain below the generated text.

**Tech Stack:** Python, Notion API `2026-03-11`, pytest.

---

### Task 1: Text Summary Renderer

**Files:**
- Modify: `src/job_hunt_agent/services/reporting.py`
- Test: `tests/test_reporting_and_mcp_contract.py`

- [ ] **Step 1: Write a failing test**

Add a test proving `ReportingService.generate_text_overview(today)` returns Chinese sections for current applications, recent activity, and pending items.

- [ ] **Step 2: Verify red**

Run:

```bash
rtk python -m pytest tests/test_reporting_and_mcp_contract.py::test_generate_text_overview_prioritizes_readable_current_state -q
```

Expected: FAIL because `generate_text_overview` does not exist.

- [ ] **Step 3: Implement minimal renderer**

Use in-memory repository data. Show company, role, stage, priority, next step, and missing resume-version hints.

- [ ] **Step 4: Verify green**

Run the focused reporting test and ensure it passes.

### Task 2: Notion Managed Text Blocks

**Files:**
- Modify: `src/job_hunt_agent/notion/client.py`
- Modify: `src/job_hunt_agent/notion/bootstrap.py`
- Test: `tests/test_notion_integration.py`

- [ ] **Step 1: Write failing tests**

Add tests for appending generated text blocks to `秋招总览`, plus replacing a previous generated section without touching linked database views.

- [ ] **Step 2: Verify red**

Run:

```bash
rtk python -m pytest tests/test_notion_integration.py::test_bootstrap_refreshes_text_first_overview_blocks -q
```

Expected: FAIL because block methods do not exist.

- [ ] **Step 3: Implement block methods and bootstrap refresh**

Add `append_block_children`, `list_block_children`, and `archive_block`. Add a managed marker paragraph so future refreshes can remove only generated blocks.

- [ ] **Step 4: Verify green**

Run Notion integration tests.

### Task 3: Verification and Real Sync

- [ ] **Step 1: Run full verification**

```bash
rtk python -m pytest -q
rtk python scripts/privacy_scan.py README.md docs examples src tests
rtk python -m compileall -q src scripts tests
```

- [ ] **Step 2: Sync real Notion**

Run a local script against Notion API to refresh `秋招总览` with the current private data.

- [ ] **Step 3: Commit and push**

Commit message:

```bash
feat: add text-first notion overview
```
