# Notion Overview Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create or reuse one private Notion overview page that displays all four recruiting databases as linked table views.

**Architecture:** Keep existing databases as the source of truth. Add Notion API helpers for child pages and linked database views, then teach the bootstrapper to create/reuse an overview page and ensure four linked views exist on it.

**Tech Stack:** Python, Notion API `2026-03-11`, pytest.

---

### Task 1: Notion Overview Page

**Files:**
- Modify: `src/job_hunt_agent/notion/client.py`
- Modify: `src/job_hunt_agent/notion/bootstrap.py`
- Modify: `scripts/notion_bootstrap.py`
- Modify: `tests/test_notion_integration.py`
- Modify: `tests/test_notion_bootstrap_script.py`

- [ ] **Step 1: Write failing tests**

Add tests that prove the bootstrapper creates or reuses a page named `秋招总览`, then creates linked table views for `投递记录`, `流程日志`, `面试记录`, and `复习任务`.

- [ ] **Step 2: Verify red**

Run:

```bash
rtk python -m pytest tests/test_notion_integration.py::test_bootstrap_creates_overview_page_with_four_linked_database_views -q
```

Expected: FAIL because the bootstrapper has no overview-page method.

- [ ] **Step 3: Implement client and bootstrap support**

Add focused methods for creating child pages, finding child pages by title, listing views by data source, and creating linked database views with `create_database`.

- [ ] **Step 4: Verify green**

Run:

```bash
rtk python -m pytest tests/test_notion_integration.py tests/test_notion_bootstrap_script.py -q
```

Expected: PASS.

- [ ] **Step 5: Full verification**

Run:

```bash
rtk python -m pytest -q
rtk python scripts/privacy_scan.py README.md docs examples src tests
rtk python -m compileall -q src scripts tests
```

Expected: all pass.
