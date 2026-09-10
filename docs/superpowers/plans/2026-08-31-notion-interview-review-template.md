# Notion Interview Review Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize the two private Notion interview reviews into one seven-section format and make the same format reusable for future reviews without committing private interview data.

**Architecture:** A pure transformation module converts synthetic or live Notion blocks into a normalized seven-section block list while preserving text-bearing block semantics. A guarded migration CLI reads private pages at runtime, appends and validates replacements before archiving legacy blocks or pages, and refuses duplicate execution when the standard section sequence already exists.

**Tech Stack:** Python 3.13, standard-library `urllib`, Notion REST API 2022-06-28, pytest

---

## File Structure

- Create `scripts/notion_interview_template.py`: pure block sanitization, legacy-section extraction, standard template assembly, and validation.
- Create `scripts/standardize_notion_interviews.py`: private runtime discovery, dry-run, guarded Notion writes, verification, and legacy archival.
- Create `tests/test_notion_interview_template.py`: synthetic transformation and preservation tests without private data or network calls.
- Create `tests/test_standardize_notion_interviews.py`: fake-API orchestration tests for append-before-archive and idempotency.

### Task 1: Build the Standard Block Contract

**Files:**
- Create: `scripts/notion_interview_template.py`
- Create: `tests/test_notion_interview_template.py`

- [ ] **Step 1: Write the failing standard-section and block-cloning tests**

```python
from scripts.notion_interview_template import (
    STANDARD_SECTIONS,
    clone_block,
    heading,
)


def rich_text(value: str) -> list[dict[str, object]]:
    return [{"type": "text", "text": {"content": value}, "plain_text": value}]


def source(block_type: str, value: str, **extra: object) -> dict[str, object]:
    body = {"rich_text": rich_text(value), **extra}
    return {"id": f"id-{value}", "type": block_type, block_type: body}


def test_standard_sections_are_fixed_and_ordered() -> None:
    assert STANDARD_SECTIONS == (
        "基本信息",
        "面试主线与整体评价",
        "核心问题复盘",
        "项目与回答亮点",
        "主要短板",
        "改进与准备建议",
        "后续动作",
    )


def test_clone_block_preserves_supported_semantics_without_read_only_fields() -> None:
    assert clone_block(source("code", "SELECT 1;", language="sql")) == {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": "SELECT 1;"}}],
            "language": "sql",
        },
    }
    assert clone_block(source("to_do", "复习 RRF", checked=True))["to_do"][
        "checked"
    ] is True
    assert heading(2, "基本信息")["heading_2"]["rich_text"][0]["text"][
        "content"
    ] == "基本信息"
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

Run:

```powershell
rtk proxy python -X utf8 -m pytest tests/test_notion_interview_template.py -q
```

Expected: collection fails because `scripts.notion_interview_template` does not exist.

- [ ] **Step 3: Implement the block contract**

Implement these public definitions:

```python
STANDARD_SECTIONS = (
    "基本信息",
    "面试主线与整体评价",
    "核心问题复盘",
    "项目与回答亮点",
    "主要短板",
    "改进与准备建议",
    "后续动作",
)

SUPPORTED_TYPES = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "quote",
    "divider",
    "code",
    "to_do",
}
```

`clone_block` must:

- reject unsupported block types with `ValueError`;
- copy visible rich text through `type`, `text`/`equation`, and annotations only;
- omit source IDs, timestamps, `plain_text`, and `href`;
- preserve `code.language`, `code.caption`, `to_do.checked`, and block color when present;
- allow `type_override="heading_3"` for demoting legacy module headings.

- [ ] **Step 4: Run the focused tests**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_notion_interview_template.py -q
```

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit the block contract**

```powershell
rtk git add scripts/notion_interview_template.py tests/test_notion_interview_template.py
rtk git commit -m "feat: add standard Notion interview block contract"
```

### Task 2: Transform Both Legacy Layouts Into Seven Sections

**Files:**
- Modify: `scripts/notion_interview_template.py`
- Modify: `tests/test_notion_interview_template.py`

- [ ] **Step 1: Write failing synthetic legacy-layout tests**

Add tests with fictional content only:

```python
from scripts.notion_interview_template import (
    block_text,
    standardize_detailed_child_review,
    standardize_structured_review,
    validate_standard_review,
)


def section_names(blocks: list[dict[str, object]]) -> list[str]:
    return [
        block_text(block)
        for block in blocks
        if block.get("type") == "heading_2"
    ]


def test_structured_review_preserves_questions_and_uses_standard_sections() -> None:
    legacy = synthetic_structured_review(question_count=17)
    result = standardize_structured_review(legacy, synthetic_properties())

    assert section_names(result) == list(STANDARD_SECTIONS)
    assert sum("Q" in block_text(block) for block in result) == 17
    assert validate_standard_review(result).question_count == 17


def test_detailed_child_review_preserves_code_and_splits_actions() -> None:
    legacy = synthetic_detailed_review(code_count=2, action_count=9)
    result = standardize_detailed_child_review(legacy, synthetic_properties())
    report = validate_standard_review(result)

    assert section_names(result) == list(STANDARD_SECTIONS)
    assert report.code_count == 2
    assert report.action_count == 9
    assert report.next_action_count >= 1
```

The fixtures must use names such as `示例公司` and synthetic questions. They must not contain real company, role, interview, or date data.

- [ ] **Step 2: Run the focused tests and verify missing-function failures**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_notion_interview_template.py -q
```

Expected: tests fail because the transformation functions are undefined.

- [ ] **Step 3: Implement property-derived basic information**

Add:

```python
def basic_information_blocks(properties: dict[str, object]) -> list[dict[str, object]]:
    """Return non-empty 时间/结果/形式/面试轮次/自评分 bullets."""
```

The function must preserve only non-empty values and must never fabricate missing values. Missing fields remain absent instead of being filled with guesses.

- [ ] **Step 4: Implement semantic legacy boundaries**

`standardize_structured_review` must locate boundaries by semantic heading patterns rather than page IDs, company names, fixed indexes, or block counts:

```python
STRUCTURED_BOUNDARIES = {
    "main": ("这场面试到底在考什么",),
    "background": ("候选人底子速览",),
    "core": ("核心面试题复盘",),
    "shortcomings": ("暴露的", "短板"),
    "matching": ("公司人才画像", "匹配度"),
    "improvements": ("面经建议",),
    "next": ("后续待确认", "后续动作"),
}
```

`standardize_detailed_child_review` must locate:

- `基本信息`;
- numbered Chinese technical headings from `一、` through `十、`;
- highlight headings containing `亮点`;
- shortcoming headings containing `风险` or `短板`;
- action headings containing `行动清单` or `后续动作`.

Technical `heading_2` blocks inside the core section become `heading_3`. Action items containing `核实`, `确认`, `联系`, `关注`, or `待补充` go to “后续动作”; other action items go to “改进与准备建议”.

- [ ] **Step 5: Implement validation**

Add an immutable report:

```python
@dataclass(frozen=True)
class ReviewValidation:
    section_names: tuple[str, ...]
    question_count: int
    code_count: int
    action_count: int
    next_action_count: int
```

`validate_standard_review` must raise `ValueError` unless the seven `heading_2` values exactly equal `STANDARD_SECTIONS` in order. Counts are derived from block types and visible text; they are not supplied by callers.

- [ ] **Step 6: Run all transformation tests**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_notion_interview_template.py -q
```

Expected: all transformation tests pass, including 17 questions, two code blocks, and nine action items.

- [ ] **Step 7: Commit legacy transformation support**

```powershell
rtk git add scripts/notion_interview_template.py tests/test_notion_interview_template.py
rtk git commit -m "feat: normalize legacy interview review layouts"
```

### Task 3: Add Guarded Notion Migration Orchestration

**Files:**
- Create: `scripts/standardize_notion_interviews.py`
- Create: `tests/test_standardize_notion_interviews.py`

- [ ] **Step 1: Write failing fake-API orchestration tests**

```python
from scripts.standardize_notion_interviews import migrate_reviews


def test_migration_appends_and_validates_before_archiving() -> None:
    api = FakeNotionApi(two_legacy_reviews())

    report = migrate_reviews(api, apply=True)

    assert api.operations[:2] == ["append:detailed", "append:structured"]
    assert "archive:legacy-blocks" in api.operations[2:]
    assert api.operations[-1] == "archive:standalone-page"
    assert report.created_reviews == 2
    assert report.archived_standalone_pages == 1


def test_migration_dry_run_never_mutates() -> None:
    api = FakeNotionApi(two_legacy_reviews())

    report = migrate_reviews(api, apply=False)

    assert api.operations == []
    assert report.created_reviews == 0
    assert report.planned_reviews == 2


def test_migration_refuses_duplicate_standard_sections() -> None:
    api = FakeNotionApi(two_completed_standard_reviews())

    with pytest.raises(RuntimeError, match="already standardized"):
        migrate_reviews(api, apply=True)

    assert api.operations == []


def test_failed_append_preserves_every_legacy_source() -> None:
    api = FakeNotionApi(two_legacy_reviews(), fail_on="append:structured")

    with pytest.raises(RuntimeError, match="append:structured"):
        migrate_reviews(api, apply=True)

    assert "archive:legacy-blocks" not in api.operations
    assert "archive:standalone-page" not in api.operations


def test_migration_resumes_partial_append_without_duplicating_sections() -> None:
    api = FakeNotionApi(detailed_review_already_appended())

    migrate_reviews(api, apply=True)

    assert "append:detailed" not in api.operations
    assert api.operations.count("append:structured") == 1
    assert api.operations[-1] == "archive:standalone-page"
```

- [ ] **Step 2: Run orchestration tests and verify the expected import failure**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_standardize_notion_interviews.py -q
```

Expected: collection fails because `scripts.standardize_notion_interviews` does not exist.

- [ ] **Step 3: Implement the API boundary**

Define a protocol so orchestration tests never use the network:

```python
class NotionApi(Protocol):
    def query_database(self, database_id: str) -> list[dict[str, object]]:
        raise NotImplementedError

    def child_blocks(self, block_id: str) -> list[dict[str, object]]:
        raise NotImplementedError

    def append_children(
        self, block_id: str, children: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        raise NotImplementedError

    def archive_block(self, block_id: str) -> None:
        raise NotImplementedError

    def archive_page(self, page_id: str) -> None:
        raise NotImplementedError
```

The production implementation reads `NOTION_TOKEN` and `NOTION_INTERVIEWS_DB_ID` through the existing `read_setting` helper. It must not print tokens, IDs, titles, or private body text.

- [ ] **Step 4: Implement runtime discovery without private identifiers**

The CLI must:

- query the interview database;
- identify the populated legacy database page by a non-empty body matching structured semantic boundaries;
- identify the empty database page by an empty body;
- discover the `面试复盘` container from the kept database parent page;
- find exactly one legacy standalone child page with a non-empty body;
- refuse to continue unless there are exactly two interview database pages and all required legacy or standardized boundaries can be classified;
- treat a complete seven-section suffix as an already appended replacement, so an interrupted migration can resume without duplicating sections;
- report `already standardized` only when both database pages are fully standardized and the standalone legacy page is already archived.

- [ ] **Step 5: Implement append-before-archive orchestration**

For `--apply`:

1. Build both standardized block lists in memory.
2. Validate section order and preservation counts before network writes.
3. Append the detailed standalone-page transformation to the empty database page, unless that target already has a complete seven-section body.
4. Validate the detailed append response.
5. Append the structured transformation to the populated database page, unless a complete seven-section suffix already exists.
6. Validate the structured append response.
7. Re-fetch both pages and locate the complete standard body or suffix.
8. Archive only blocks before the structured page's standard suffix; on retry, archive whichever legacy prefix blocks remain.
9. Archive the standalone legacy page only after both database pages validate.
10. Re-fetch both database pages and validate the final seven-section bodies.

If either append or validation fails, do not archive legacy sources. If archival is interrupted, a rerun locates the validated standard suffix and continues removing only the remaining legacy prefix. Archive operations are reversible through the Notion trash.

- [ ] **Step 6: Implement the CLI modes**

```powershell
rtk proxy python -X utf8 -m scripts.standardize_notion_interviews --dry-run
rtk proxy python -X utf8 -m scripts.standardize_notion_interviews --apply
```

`--dry-run` prints only aggregate counts:

```text
dry-run: reviews=2, standard_sections=7, legacy_blocks=155, standalone_pages=1
```

`--apply` prints only aggregate results:

```text
applied: reviews=2, archived_legacy_blocks=61, archived_standalone_pages=1
```

- [ ] **Step 7: Run orchestration and full tests**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_standardize_notion_interviews.py -q
rtk proxy python -X utf8 -m pytest -q
```

Expected: all tests pass without network calls or private fixtures.

- [ ] **Step 8: Commit guarded migration orchestration**

```powershell
rtk git add scripts/standardize_notion_interviews.py tests/test_standardize_notion_interviews.py
rtk git commit -m "feat: add guarded Notion interview migration"
```

### Task 4: Dry-Run and Apply the Private Migration

**Files:**
- Execute: `scripts/standardize_notion_interviews.py`
- Verify: private Notion interview database and review container

- [ ] **Step 1: Run the private dry-run**

```powershell
rtk proxy python -X utf8 -m scripts.standardize_notion_interviews --dry-run
```

Expected:

- exactly two database reviews;
- one standalone legacy page;
- seven planned standard sections per review;
- no mutation.

- [ ] **Step 2: Apply the migration**

```powershell
rtk proxy python -X utf8 -m scripts.standardize_notion_interviews --apply
```

Expected: two standardized database pages are written and verified before the old populated blocks and standalone page are archived.

- [ ] **Step 3: Verify live invariants without printing private text**

Run a read-only verifier that reports only counts:

```text
interviews=2
standard_reviews=2
sections_per_review=[7, 7]
question_count_preserved=true
code_count_preserved=true
standalone_legacy_pages=0
answer_page_blocks=455
```

- [ ] **Step 4: Re-run dry-run to verify idempotency refusal**

```powershell
rtk proxy python -X utf8 -m scripts.standardize_notion_interviews --dry-run
```

Expected: a clear `already standardized` refusal and no mutation.

### Task 5: Final Privacy and Repository Verification

**Files:**
- Verify: all created scripts, tests, and docs

- [ ] **Step 1: Run syntax and full test verification**

```powershell
rtk proxy python -X utf8 -m py_compile scripts/notion_interview_template.py scripts/standardize_notion_interviews.py
rtk proxy python -X utf8 -m pytest -q
```

Expected: compilation succeeds and all tests pass.

- [ ] **Step 2: Scan tracked content for private identifiers and real interview data**

Use runtime-only values as search terms without adding them to tracked files. Confirm no company title, role title, Notion URL, Notion ID, WPS share ID, recommendation code, or token is present in the repository changes.

- [ ] **Step 3: Confirm the worktree is clean**

```powershell
rtk git status --short
rtk git log -5 --oneline
```

Expected: no uncommitted files in the feature worktree.

- [ ] **Step 4: Hand off through branch completion workflow**

Use `superpowers:finishing-a-development-branch`, re-run tests, and offer local merge, PR, keep, or discard. Do not push private data.
