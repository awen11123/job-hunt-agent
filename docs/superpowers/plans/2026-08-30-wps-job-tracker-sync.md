# WPS Job Tracker Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a fixed-link WPS job tracker, migrate the existing private applications into it, and reduce Notion to a concise interview archive.

**Architecture:** A small Python workbook module renders normalized application records into one stable `.xlsx` path under the logged-in WPS cloud directory. A separate Notion exporter converts private database rows into the normalized JSON contract, while a guarded Notion cleanup script archives only the generated text-overview block range after WPS synchronization is verified. Real application data, WPS paths, share links, and Notion identifiers remain outside Git.

**Tech Stack:** Python 3.13, openpyxl 3.1.5, urllib from the standard library, pytest, WPS desktop cloud sync, Notion REST API

---

## File Map

- Create: `scripts/__init__.py` - marks the scripts directory as an importable package.
- Create: `scripts/wps_job_tracker.py` - validates normalized records, renders the workbook, atomically replaces the stable file, and creates sync probes.
- Create: `scripts/export_notion_applications.py` - reads the private Notion applications database and emits normalized private JSON.
- Create: `scripts/simplify_notion_overview.py` - dry-runs and applies the marker-bounded Notion overview cleanup.
- Create: `tests/test_wps_job_tracker.py` - workbook layout, sorting, colors, hyperlinks, and stable-path replacement tests.
- Create: `tests/test_export_notion_applications.py` - Notion property normalization tests without network calls.
- Create: `tests/test_simplify_notion_overview.py` - marker selection and idempotent replacement tests.
- Private runtime artifact: `%TEMP%\job-hunt-applications-private.json` - never add to Git.
- Private WPS artifacts: the logged-in account directory below `%USERPROFILE%\WPS Cloud Files` - never add to Git.

### Task 1: Build the stable WPS workbook renderer

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/wps_job_tracker.py`
- Test: `tests/test_wps_job_tracker.py`

- [ ] **Step 1: Write the failing workbook contract test**

```python
from pathlib import Path

from openpyxl import load_workbook

from scripts.wps_job_tracker import HEADERS, build_workbook


def test_build_workbook_layout_sorting_and_links(tmp_path: Path) -> None:
    output = tmp_path / "tracker.xlsx"
    records = [
        {
            "company": "较早企业",
            "role": "AI 工程师",
            "applied_date": "2026-08-01",
            "location": "北京",
            "status": "已投递",
            "next_step": "等待通知",
            "next_time": "",
            "link": "https://example.com/old",
            "notes": "",
        },
        {
            "company": "最新企业",
            "role": "Agent 工程师",
            "applied_date": "2026-08-30",
            "location": "杭州",
            "status": "面试安排中",
            "next_step": "确认时间",
            "next_time": "2026-09-01 10:00",
            "link": "https://example.com/new",
            "notes": "重点跟进",
        },
    ]

    build_workbook(records, output)

    workbook = load_workbook(output)
    sheet = workbook["投递总览"]
    assert [cell.value for cell in sheet[1]] == list(HEADERS)
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:I3"
    assert sheet["A2"].value == "最新企业"
    assert sheet["A3"].value == "较早企业"
    assert sheet["H2"].hyperlink.target == "https://example.com/new"
    assert sheet["E2"].fill.fgColor.rgb != sheet["E3"].fill.fgColor.rgb
```

- [ ] **Step 2: Run the test and verify the missing module failure**

Run:

```powershell
rtk pytest tests/test_wps_job_tracker.py -q
```

Expected: FAIL because `scripts.wps_job_tracker` does not exist.

- [ ] **Step 3: Implement the minimal renderer and atomic replacement**

Implement these public elements in `scripts/wps_job_tracker.py`:

```python
HEADERS = (
    "企业",
    "投递岗位",
    "投递日期",
    "所在地",
    "当前状态",
    "下一节点",
    "节点时间",
    "岗位链接",
    "备注",
)


def build_workbook(records: list[dict[str, str]], output: Path) -> Path:
    """Render records newest-first and atomically replace output."""
```

Implementation requirements:

- Validate every record contains exactly the nine normalized keys.
- Sort by `applied_date` descending while preserving input order for equal dates.
- Create one sheet named `投递总览`.
- Freeze only the header row with `A2`; do not freeze any left column.
- Add an autofilter across all populated rows.
- Use restrained header formatting and three status fills:
  - green for active states such as `已投递` and `进行中`;
  - amber for attention states containing `测评`, `笔试`, `面试`, or `待处理`;
  - red for closed states containing `未通过`, `结束`, `放弃`, or `拒绝`.
- Write valid links as hyperlinks in column H.
- Set practical fixed widths so the nine columns remain readable.
- Save to `output.with_name(f".{output.name}.tmp.xlsx")` in the same directory, then call `os.replace` so the public path remains stable.
- Convert `PermissionError` into a clear message telling the user to close the workbook before retrying.

- [ ] **Step 4: Add the stable-path replacement test**

```python
def test_build_workbook_replaces_same_path_without_temp_file(tmp_path: Path) -> None:
    output = tmp_path / "tracker.xlsx"
    first = [sample_record(company="第一版", applied_date="2026-08-29")]
    second = [sample_record(company="第二版", applied_date="2026-08-30")]

    build_workbook(first, output)
    build_workbook(second, output)

    workbook = load_workbook(output)
    assert workbook["投递总览"]["A2"].value == "第二版"
    assert not (tmp_path / ".tracker.xlsx.tmp.xlsx").exists()
```

- [ ] **Step 5: Run the focused tests**

Run:

```powershell
rtk pytest tests/test_wps_job_tracker.py -q
```

Expected: all workbook tests PASS.

- [ ] **Step 6: Commit the renderer**

```powershell
rtk git add scripts/__init__.py scripts/wps_job_tracker.py tests/test_wps_job_tracker.py
rtk git commit -m "feat: add stable WPS job tracker renderer"
```

### Task 2: Add WPS cloud discovery and sync probe commands

**Files:**
- Modify: `scripts/wps_job_tracker.py`
- Modify: `tests/test_wps_job_tracker.py`

- [ ] **Step 1: Write failing cloud-directory discovery tests**

```python
def test_discover_wps_account_directory_ignores_cache_directories(tmp_path: Path) -> None:
    (tmp_path / ".metadata").mkdir()
    (tmp_path / "hyperionlocalcache").mkdir()
    account = tmp_path / "account-directory"
    account.mkdir()

    assert discover_wps_account_directory(tmp_path) == account


def test_discover_wps_account_directory_rejects_ambiguity(tmp_path: Path) -> None:
    (tmp_path / "account-one").mkdir()
    (tmp_path / "account-two").mkdir()

    with pytest.raises(RuntimeError, match="multiple WPS account directories"):
        discover_wps_account_directory(tmp_path)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
rtk pytest tests/test_wps_job_tracker.py -q
```

Expected: FAIL because `discover_wps_account_directory` is missing.

- [ ] **Step 3: Implement discovery and CLI subcommands**

Add:

```python
def discover_wps_account_directory(root: Path | None = None) -> Path:
    root = root or Path.home() / "WPS Cloud Files"
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name.lower() != "hyperionlocalcache"
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "expected one WPS account directory; found "
            f"{len(candidates)}"
        )
    return candidates[0]
```

Add `argparse` subcommands:

- `probe --marker TEXT [--open]`: write `WPS同步测试.xlsx` into the discovered account directory using one fake row only; on Windows, `--open` calls `os.startfile(output)` after a successful save.
- `build --input JSON [--output XLSX]`: render normalized JSON; default output is `秋招投递总览.xlsx` in the discovered account directory.

- [ ] **Step 4: Run tests and create the first private probe**

```powershell
rtk pytest tests/test_wps_job_tracker.py -q
rtk proxy python -X utf8 scripts/wps_job_tracker.py probe --marker "同步测试-第一版"
```

Expected: tests PASS and the command prints the full path to `WPS同步测试.xlsx`.

- [ ] **Step 5: Open the probe through the Windows file association**

```powershell
rtk proxy python -X utf8 scripts/wps_job_tracker.py probe --marker "同步测试-第一版" --open
```

Opening a GUI requires user approval. The user confirms the workbook appears in WPS cloud documents and creates a view-only link.

- [ ] **Step 6: Update the same file and verify the fixed link**

```powershell
rtk proxy python -X utf8 scripts/wps_job_tracker.py probe --marker "同步测试-第二版"
```

Expected: the same file path is replaced. The user refreshes the original view-only link and sees `同步测试-第二版` without receiving a new URL.

- [ ] **Step 7: Commit cloud discovery and probe support**

```powershell
rtk git add scripts/wps_job_tracker.py tests/test_wps_job_tracker.py
rtk git commit -m "feat: add WPS cloud sync probe"
```

### Task 3: Export private Notion applications to the normalized contract

**Files:**
- Create: `scripts/export_notion_applications.py`
- Test: `tests/test_export_notion_applications.py`

- [ ] **Step 1: Write the failing Notion normalization test**

```python
from scripts.export_notion_applications import normalize_application


def test_normalize_application_maps_only_tracker_fields() -> None:
    page = synthetic_notion_page(
        company="示例企业",
        role="Agent 工程师",
        applied_date="2026-08-30",
        location="杭州",
        stage="测评完成",
        next_step="等待结果",
        link="https://example.com/job",
        priority="高",
    )

    assert normalize_application(page) == {
        "company": "示例企业",
        "role": "Agent 工程师",
        "applied_date": "2026-08-30",
        "location": "杭州",
        "status": "测评完成",
        "next_step": "等待结果",
        "next_time": "",
        "link": "https://example.com/job",
        "notes": "高优先级",
    }
```

- [ ] **Step 2: Run the test and verify the missing module failure**

```powershell
rtk pytest tests/test_export_notion_applications.py -q
```

Expected: FAIL because the exporter does not exist.

- [ ] **Step 3: Implement the private exporter**

Implement:

```python
def read_setting(name: str) -> str:
    """Read a process environment variable, then HKCU\Environment on Windows."""


def query_database(token: str, database_id: str) -> list[dict[str, object]]:
    """Page through POST /v1/databases/{id}/query with page_size=100."""


def normalize_application(page: dict[str, object]) -> dict[str, str]:
    """Map Notion properties to the exact nine-field workbook contract."""
```

Mapping:

- `公司` title -> `company`
- `岗位` rich text -> `role`
- `投递日期` date start -> `applied_date`
- `地点` rich text -> `location`
- `当前阶段` select -> `status`
- `下一步` rich text -> `next_step`
- `截止日期` date start -> `next_time`
- `JD 链接` URL -> `link`
- `优先级` select -> the selected text followed by `优先级` in `notes`, for example `高优先级`

The CLI writes UTF-8 JSON to `--output`. It must never print the token, database ID, full private records, or Notion page URLs.

- [ ] **Step 4: Run tests and export the real private JSON**

```powershell
rtk pytest tests/test_export_notion_applications.py -q
rtk proxy python -X utf8 scripts/export_notion_applications.py --output "$env:TEMP\job-hunt-applications-private.json"
```

Expected: tests PASS; exporter reports only the record count and output path. Current expected record count is 16.

- [ ] **Step 5: Privacy-check the repository and commit**

```powershell
rtk rg -n "NOTION_TOKEN|notion\.so|<account-id>|job-hunt-applications-private" .
rtk git add scripts/export_notion_applications.py tests/test_export_notion_applications.py
rtk git commit -m "feat: export private applications for WPS rendering"
```

Expected: matches are limited to generic documentation or code identifiers; no token, private URL, account directory, or real record appears.

### Task 4: Build and verify the formal WPS tracker

**Files:**
- Private input: `%TEMP%\job-hunt-applications-private.json`
- Private output: WPS cloud account directory `秋招投递总览.xlsx`

- [ ] **Step 1: Generate the formal workbook at its stable path**

```powershell
rtk proxy python -X utf8 scripts/wps_job_tracker.py build --input "$env:TEMP\job-hunt-applications-private.json"
```

Expected: command prints the private output path and `16 records`; it does not print record contents.

- [ ] **Step 2: Verify workbook structure without displaying private rows**

Run a verification command that loads the workbook and prints only:

- sheet name;
- header list;
- data-row count;
- unique-company count;
- whether dates are descending;
- whether column freeze is exactly `A2`.

Expected for the current snapshot: 16 rows, 15 unique companies, nine headers, descending dates, and `A2` freeze.

- [ ] **Step 3: Open the formal workbook and create a fixed view-only link**

Open the file through Windows default association. In WPS, set link permissions to view-only and copy the share link outside the repository. Confirm from a signed-out/private browser window that the link opens without edit permission.

- [ ] **Step 4: Keep the Notion source untouched until sync is confirmed**

Do not archive or edit the Notion overview during this task. The WPS link must first show the complete formal workbook.

### Task 5: Guard and simplify the Notion overview

**Files:**
- Create: `scripts/simplify_notion_overview.py`
- Test: `tests/test_simplify_notion_overview.py`

- [ ] **Step 1: Write the failing marker-selection test**

```python
from scripts.simplify_notion_overview import select_generated_block_ids


def test_select_generated_block_ids_only_returns_marker_range() -> None:
    blocks = [
        block("keep-before", "child_page", "历史面经"),
        block("start", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"),
        block("generated", "heading_1", "秋招总览"),
        block("end", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"),
        block("keep-after", "paragraph", "人工内容"),
    ]

    assert select_generated_block_ids(blocks) == ["start", "generated", "end"]
```

- [ ] **Step 2: Run the test and verify failure**

```powershell
rtk pytest tests/test_simplify_notion_overview.py -q
```

Expected: FAIL because the cleanup module does not exist.

- [ ] **Step 3: Implement dry-run-first cleanup**

Implement these safeguards:

```python
START = "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"
END = "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"
NEW_START = "JOB_HUNT_AGENT_INTERVIEW_OVERVIEW_START"
NEW_END = "JOB_HUNT_AGENT_INTERVIEW_OVERVIEW_END"
```

- Fetch all top-level blocks from `JOB_HUNT_OVERVIEW_PAGE_ID`.
- Refuse to mutate unless exactly one complete `START`/`END` range exists.
- `--dry-run` prints only the number and types of blocks to archive.
- `--apply` archives only the selected IDs, renames the page to `面试复盘`, and appends:
  - hidden start marker paragraph;
  - `面试复盘` heading;
  - one sentence explaining that applications moved to WPS;
  - a `link_to_page` block targeting `NOTION_INTERVIEWS_DB_ID`;
  - hidden end marker paragraph.
- If `NEW_START` already exists, refuse to append another replacement section.
- Never archive interview database pages or database objects.

- [ ] **Step 4: Run tests and dry-run against Notion**

```powershell
rtk pytest tests/test_simplify_notion_overview.py -q
rtk proxy python -X utf8 scripts/simplify_notion_overview.py --dry-run
```

Expected: tests PASS; dry-run reports the generated overview block count and preserves the historical child page.

- [ ] **Step 5: Apply cleanup only after WPS link verification**

```powershell
rtk proxy python -X utf8 scripts/simplify_notion_overview.py --apply
```

Expected: overview title becomes `面试复盘`; the long application list, stale reminders, and duplicated process history disappear; the interview database remains reachable.

- [ ] **Step 6: Commit the guarded cleanup script**

```powershell
rtk git add scripts/simplify_notion_overview.py tests/test_simplify_notion_overview.py
rtk git commit -m "feat: simplify Notion interview overview"
```

### Task 6: Final verification and private-artifact cleanup

**Files:**
- Verify: private WPS workbook
- Verify: private Notion interview database and overview
- Remove: private temporary JSON

- [ ] **Step 1: Run the complete test suite**

```powershell
rtk pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Verify cross-system counts and invariants**

Verify without printing private content:

- WPS formal workbook has 16 application rows and nine columns.
- Notion interview database still has two entries.
- The newest detailed interview still contains all 17 numbered questions.
- Notion overview contains exactly one new interview-overview marker range.
- The old generated text-overview marker range is archived.
- The original WPS view-only link displays the newest workbook version.

- [ ] **Step 3: Delete the temporary private JSON**

Resolve `%TEMP%\job-hunt-applications-private.json`, verify it is inside the current user temporary directory, then remove only that file. Report that the file was deleted and is not recoverable from Git because it was never committed.

- [ ] **Step 4: Run privacy and Git checks**

```powershell
rtk rg -n "<account-id>|https://www\.notion\.so/|secret_[A-Za-z0-9]|job-hunt-applications-private\.json" .
rtk git status --short
rtk git log -5 --oneline
```

Expected: no private WPS account ID, Notion URL, secret, temporary JSON, or real application data is tracked. Existing unrelated local interview notes remain untouched.
