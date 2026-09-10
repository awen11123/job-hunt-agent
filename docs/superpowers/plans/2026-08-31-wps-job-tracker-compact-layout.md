# WPS Job Tracker Compact Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the existing private WPS job tracker into a compact process overview without losing manual content, merged cells, or hyperlink targets.

**Architecture:** Add a focused one-shot compactor separate from the existing stage-sorting script. It performs only approved value and layout changes, validates protected cells and workbook structure, saves through a temporary workbook, and creates a recoverable backup before replacing the cloud-synced file.

**Tech Stack:** Python 3, openpyxl, pytest, pathlib, shutil, atomic `os.replace`

---

### Task 1: Compact values and layout with preservation checks

**Files:**
- Create: `scripts/compact_wps_job_tracker.py`
- Create: `tests/test_compact_wps_job_tracker.py`

- [ ] **Step 1: Write failing tests using only synthetic data**

Create a synthetic nine-column workbook with submitted, AI-interview, written-test, abnormal, and closed rows; include a two-row merged company, a raw URL with a real hyperlink, a meaningful link label with a real hyperlink, a `。。。` placeholder without a hyperlink, a comment, custom cell style, and long next-step text.

The tests call the wished-for API and assert exact behavior:

```python
result = compact_workbook(source, output)

assert result.rows == 7
assert result.normalized_statuses == 2
assert result.shortened_next_steps == 6
assert result.relabelled_links == 2
assert result.cleared_placeholders == 1
assert sheet["E2"].value == "已投递"
assert sheet["F2"].value == "等待流程通知"
assert sheet["F3"].value == "等待面试结果"
assert sheet["F4"].value == "等待笔试结果"
assert sheet["F5"].value == "等待补发链接"
assert sheet["F7"].value == "结束"
assert sheet["H2"].value == "查看岗位"
assert sheet["H2"].hyperlink.target == "https://example.com/job"
assert sheet["H5"].value is None
assert max(sheet.row_dimensions[row].height for row in range(2, 9)) <= 42
```

Also assert that columns A:D, G, and I are byte-for-byte equivalent at the cell-value level, comments and hyperlink targets are unchanged, meaningful non-link labels are retained, merged ranges stay identical, row order is unchanged, `freeze_panes` remains `A2`, and the auto-filter remains `A1:I8`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -X utf8 -m pytest tests/test_compact_wps_job_tracker.py -q
```

Expected: test collection fails with `ModuleNotFoundError: No module named 'scripts.compact_wps_job_tracker'`.

- [ ] **Step 3: Implement the short-node mapping**

Create these public interfaces:

```python
from dataclasses import dataclass
from pathlib import Path


ALLOWED_NEXT_STEPS = frozenset(
    {
        "等待筛选",
        "等待流程通知",
        "等待笔试结果",
        "等待面试结果",
        "等待补发链接",
        "结束",
    }
)


@dataclass(frozen=True)
class CompactResult:
    rows: int
    normalized_statuses: int
    shortened_next_steps: int
    relabelled_links: int
    cleared_placeholders: int


def short_next_step(status: object, current: object) -> str:
    normalized = str(status or "").strip()
    if any(marker in normalized for marker in ("未通过", "结束", "拒绝", "放弃", "终止", "淘汰")):
        return "结束"
    if "AI面试完成" in normalized or "面试完成" in normalized:
        return "等待面试结果"
    if "笔试完成" in normalized:
        return "等待笔试结果"
    if any(marker in normalized for marker in ("异常", "补发")):
        return "等待补发链接"
    if str(current or "").strip() == "等待筛选":
        return "等待筛选"
    return "等待流程通知"
```

Expose `compact_workbook(source: Path, output: Path) -> CompactResult` and `compact_file_in_place(target: Path, backup_dir: Path) -> tuple[Path, CompactResult]` as the file-level public API. In `compact_workbook`, validate the exact headers, snapshot protected values in A:D/G/I plus hyperlink targets, comments, merges, row order, freeze panes, and filter range. Normalize `applied` to `已投递`, call `short_next_step`, relabel cells with real hyperlinks to `查看岗位`, clear only `。。。` cells without hyperlinks, set H width to 12 and F width to 18, center and disable wrapping in linked H cells, and cap data-row heights at 32 or 42 based on company/role text length; closed rows use 28.

- [ ] **Step 4: Add post-save validation**

Reload the output and enforce:

```python
assert protected_values_after == protected_values_before
assert hyperlink_targets_after == hyperlink_targets_before
assert comments_after == comments_before
assert merged_ranges_after == merged_ranges_before
assert row_order_after == row_order_before
assert output_sheet.freeze_panes == original_freeze_panes
assert output_sheet.auto_filter.ref == original_filter_ref
assert all(step in ALLOWED_NEXT_STEPS for step in next_steps_after)
assert all(height <= 42 for height in row_heights_after)
```

Raise `RuntimeError` before replacing the private file if any invariant fails.

- [ ] **Step 5: Implement recoverable in-place replacement and CLI**

`compact_file_in_place` copies the target to `<backup_dir>/<stem>-compact-<timestamp>.xlsx`, writes to a hidden temporary file beside the target, reloads and validates it, then calls `os.replace`. Add CLI arguments:

```text
--target <xlsx path>
--backup-dir <directory>
--dry-run
```

Dry-run prints only row counts and planned change counts; it must not print private link targets.

- [ ] **Step 6: Run focused and full regression tests**

Run:

```powershell
python -X utf8 -m pytest tests/test_compact_wps_job_tracker.py -q
python -X utf8 -m pytest -q
python -X utf8 -m py_compile scripts/compact_wps_job_tracker.py tests/test_compact_wps_job_tracker.py
```

Expected: all focused tests pass, all repository tests pass, and compilation exits with code 0.

- [ ] **Step 7: Commit the implementation**

```powershell
git add scripts/compact_wps_job_tracker.py tests/test_compact_wps_job_tracker.py
git commit -m "feat: compact WPS tracker layout"
```

### Task 2: Apply the compactor to the private WPS workbook

**Files:**
- Modify outside Git: `C:/Users/<username>/WPS Cloud Files/<account-id>/秋招投递总览.xlsx`
- Create outside Git: `C:/Users/<username>/Desktop/job-hunt/backups/秋招投递总览-compact-<timestamp>.xlsx`

- [ ] **Step 1: Run read-only dry-run against the latest workbook**

```powershell
python -X utf8 scripts/compact_wps_job_tracker.py `
  --target "C:\Users\<username>\WPS Cloud Files\<account-id>\秋招投递总览.xlsx" `
  --dry-run
```

Expected report: 18 records, 9 `applied` statuses to normalize, all 18 next steps evaluated, 13 real hyperlink labels to normalize, and two invalid `。。。` placeholders to clear.

- [ ] **Step 2: Back up and atomically compact the workbook**

```powershell
python -X utf8 scripts/compact_wps_job_tracker.py `
  --target "C:\Users\<username>\WPS Cloud Files\<account-id>\秋招投递总览.xlsx" `
  --backup-dir "C:\Users\<username>\Desktop\job-hunt\backups"
```

Expected: one timestamped backup is created and the target is atomically replaced only after successful reload and invariant validation.

- [ ] **Step 3: Independently verify the private output**

Reload the target and backup in a separate verification command. Assert 18 records remain; active/closed counts remain 15/3; closed rows remain 17–19; no `applied` or `。。。` remains; every next step belongs to the six approved phrases; all real link cells display `查看岗位`; hyperlink-target multisets, merges, comments, protected values, row order, freeze panes, and filter range match the backup; maximum data-row height is 42.

- [ ] **Step 4: Merge locally and report**

After fresh full-suite verification, fast-forward the feature branch into `master`, rerun the full test suite on the merged result, remove the isolated worktree and local feature branch, and report the target path, backup path, exact counts, commit hash, and any cleanup residue.
