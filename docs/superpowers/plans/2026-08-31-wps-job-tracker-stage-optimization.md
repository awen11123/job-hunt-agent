# WPS Job Tracker Stage Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely optimize the existing private WPS job tracker in place while preserving manually edited content and hyperlinks.

**Architecture:** Add a focused `optimize_wps_job_tracker.py` module that snapshots logical row groups, stable-partitions active and closed groups, restores merged ranges, applies stage-specific styles, validates preservation, creates a backup, and atomically replaces the target. Unit tests operate only on synthetic workbooks.

**Tech Stack:** Python 3, openpyxl, pytest, pathlib, shutil, tempfile-style atomic replacement

---

### Task 1: Specify preservation, grouping, sorting, and styling

**Files:**
- Create: `tests/test_optimize_wps_job_tracker.py`
- Create: `scripts/optimize_wps_job_tracker.py`

- [ ] **Step 1: Write failing synthetic-workbook tests**

Create tests that build a nine-column workbook containing active rows, three closed rows, a two-row merged-company group, visible hyperlink text, hyperlink targets, and an abnormal assessment row. Assert that `optimize_workbook()`:

```python
result = optimize_workbook(source, output)
assert result.active_rows == 4
assert result.closed_rows == 2
assert sheet["E2"].value == "AI面试完成"
assert active_companies == ["示例出行", "示例平台", "示例联通"]
assert closed_companies == ["示例终止甲", "示例终止乙"]
assert sheet["H2"].value == "岗位页面"
assert sheet["H2"].hyperlink.target == "https://example.com/travel"
assert {str(r) for r in sheet.merged_cells.ranges} == {"A4:A5", "H4:H5"}
assert sheet.freeze_panes == "A2"
```

Also assert that the first closed row has a thick top border, stage fills differ, and all non-authorized values and hyperlink targets are preserved as multisets.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -X utf8 -m pytest tests/test_optimize_wps_job_tracker.py -q`

Expected: FAIL because `scripts.optimize_wps_job_tracker` does not exist.

- [ ] **Step 3: Implement logical row snapshots and stable partitioning**

Implement these focused interfaces:

```python
@dataclass(frozen=True)
class OptimizationResult:
    active_rows: int
    closed_rows: int
    updated_companies: tuple[str, ...]

def optimize_workbook(source: Path, output: Path) -> OptimizationResult:
    ...

def optimize_file_in_place(target: Path, backup_dir: Path) -> tuple[Path, OptimizationResult]:
    ...
```

Build connected row groups from data-region merged ranges, unmerge them, snapshot values/styles/hyperlinks/comments/row dimensions, stable-partition groups with closed markers, write them back, translate and restore merges, then update only the authorized company statuses.

- [ ] **Step 4: Apply selected visual system and preservation validation**

Use strong fills in column E and lighter matching fills in F:G. Apply blue to submitted rows, yellow to written/assessment rows, green to completed AI interviews, orange to abnormal rows, and red plus muted full-row styling to closed rows. Add a thick top border to the first closed row, set `freeze_panes = "A2"`, preserve the auto-filter, and compare normalized before/after row signatures allowing only the two explicit status changes.

- [ ] **Step 5: Run focused and regression tests**

Run: `python -X utf8 -m pytest tests/test_optimize_wps_job_tracker.py -q`

Expected: all focused tests PASS.

Run: `python -X utf8 -m pytest -q`

Expected: all repository tests PASS.

### Task 2: Back up and optimize the private workbook

**Files:**
- Modify outside Git: `C:/Users/<username>/WPS Cloud Files/<account-id>/秋招投递总览.xlsx`
- Create outside Git: `backups/秋招投递总览-<timestamp>.xlsx`

- [ ] **Step 1: Inspect the current workbook immediately before writing**

Run the CLI in dry-run mode to report sheet name, row count, active/closed counts, target companies, and merged ranges without changing the file.

- [ ] **Step 2: Create backup and atomically optimize**

Run:

```powershell
python -X utf8 scripts/optimize_wps_job_tracker.py `
  --target "C:\Users\<username>\WPS Cloud Files\<account-id>\秋招投递总览.xlsx" `
  --backup-dir "C:\Users\<username>\Desktop\秋招\backups"
```

Expected: one timestamped backup is created, the temporary workbook reloads successfully, and the target is atomically replaced.

- [ ] **Step 3: Verify the private output**

Reload the target and assert 18 data rows remain, the two AI interview statuses are green, closed rows are at the bottom, 示例平台 remains active/orange, merged ranges and hyperlink targets are preserved, and the workbook has `freeze_panes = "A2"` with filter range `A1:I19`.

- [ ] **Step 4: Report exact outcome**

Report the target path, backup path, counts, status changes, test results, and any field intentionally left unchanged. Do not print private hyperlink targets.
