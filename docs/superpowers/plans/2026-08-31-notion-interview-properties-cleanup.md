# Notion Interview Properties Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the two non-empty legacy summaries in standardized interview bodies, reduce the interview database to five useful properties, and replace the English analysis status with `已整理`.

**Architecture:** A dedicated cleanup module reads the live database through a protocol-backed API, produces Notion blocks from non-empty legacy summary properties, inserts them inside the existing “面试主线与整体评价” section, and re-fetches the bodies before any schema deletion. A production HTTP adapter performs page and database PATCH requests, while synthetic fake-API tests verify ordering, refusal, idempotency, and preservation without storing private content.

**Tech Stack:** Python 3.13, standard-library `urllib`, Notion REST API 2022-06-28, pytest

---

## File Structure

- Create `scripts/cleanup_notion_interview_properties.py`: property extraction, body insertion planning, guarded orchestration, Notion HTTP adapter, and CLI.
- Create `tests/test_cleanup_notion_interview_properties.py`: synthetic page/schema fixtures and fake-API safety tests.
- Reuse `scripts/notion_interview_template.py`: standard-section validation and block text extraction.
- Reuse `scripts/standardize_notion_interviews.py`: existing HTTP API client for database queries and child-block reads.

### Task 1: Define Property Cleanup and Content-Preservation Rules

**Files:**
- Create: `scripts/cleanup_notion_interview_properties.py`
- Create: `tests/test_cleanup_notion_interview_properties.py`

- [ ] **Step 1: Write failing tests for fixed schema rules and summary blocks**

Create fictional fixtures only. The tests must assert the exact five kept properties, exact eight deleted properties, and mapping of the two preservable fields:

```python
from scripts.cleanup_notion_interview_properties import (
    DROP_PROPERTIES,
    KEEP_PROPERTIES,
    build_summary_blocks,
    property_text,
)
from scripts.notion_interview_template import block_text


def rich_property(value: str) -> dict[str, object]:
    return {
        "type": "rich_text",
        "rich_text": [
            {"type": "text", "text": {"content": value}, "plain_text": value}
        ],
    }


def test_property_contract_is_small_and_fixed() -> None:
    assert KEEP_PROPERTIES == (
        "面试",
        "时间",
        "结果",
        "面试轮次",
        "分析状态",
    )
    assert DROP_PROPERTIES == (
        "Prompt 版本",
        "关联投递",
        "原始笔记",
        "形式",
        "总体复盘",
        "模型版本",
        "结构化面经",
        "自评分",
    )


def test_summary_blocks_preserve_only_nonempty_unique_text() -> None:
    properties = {
        "总体复盘": rich_property("示例总体判断"),
        "结构化面经": rich_property("示例考察主线"),
        "原始笔记": rich_property("正文已经保存"),
    }

    blocks = build_summary_blocks(properties, existing_body_text="")

    assert [block_text(block) for block in blocks] == [
        "总体复盘",
        "示例总体判断",
        "考察主线",
        "示例考察主线",
    ]
    assert property_text(properties["原始笔记"]) not in {
        block_text(block) for block in blocks
    }


def test_summary_blocks_skip_text_already_in_body() -> None:
    properties = {"总体复盘": rich_property("示例总体判断")}

    assert build_summary_blocks(
        properties, existing_body_text="正文已有：示例总体判断"
    ) == []
```

- [ ] **Step 2: Run the focused tests and verify the import failure**

Run:

```powershell
rtk proxy python -X utf8 -m pytest tests/test_cleanup_notion_interview_properties.py -q
```

Expected: collection fails because `scripts.cleanup_notion_interview_properties` does not exist.

- [ ] **Step 3: Implement the fixed rules and pure block builder**

Implement:

```python
KEEP_PROPERTIES = ("面试", "时间", "结果", "面试轮次", "分析状态")
DROP_PROPERTIES = (
    "Prompt 版本",
    "关联投递",
    "原始笔记",
    "形式",
    "总体复盘",
    "模型版本",
    "结构化面经",
    "自评分",
)
SUMMARY_FIELDS = (
    ("总体复盘", "总体复盘"),
    ("结构化面经", "考察主线"),
)


def property_text(prop: object) -> str:
    """Return visible title/rich-text content without exposing read-only fields."""


def build_summary_blocks(
    properties: dict[str, object], existing_body_text: str
) -> list[dict[str, object]]:
    """Return heading_3/paragraph pairs only for non-empty text absent from body."""
```

Use `heading(3, label)` from the existing template module and construct a plain paragraph block. Do not migrate `原始笔记`, because the approved design classifies it as redundant metadata rather than interview content.

- [ ] **Step 4: Run focused and full tests**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_cleanup_notion_interview_properties.py -q
rtk proxy python -X utf8 -m pytest -q
```

Expected: all new tests pass and the existing 41 tests remain green.

- [ ] **Step 5: Commit the pure cleanup contract**

```powershell
rtk git add scripts/cleanup_notion_interview_properties.py tests/test_cleanup_notion_interview_properties.py
rtk git commit -m "feat: define Notion interview property cleanup"
```

### Task 2: Add Guarded Cleanup Orchestration

**Files:**
- Modify: `scripts/cleanup_notion_interview_properties.py`
- Modify: `tests/test_cleanup_notion_interview_properties.py`

- [ ] **Step 1: Write failing fake-API orchestration tests**

Define a `FakeCleanupApi` with two standardized synthetic pages, a 13-property database schema, one page containing both legacy summaries, and an operation log. Add these tests:

```python
def test_dry_run_never_mutates() -> None:
    api = legacy_cleanup_api()

    report = cleanup_interview_properties(api, apply=False)

    assert api.operations == []
    assert report.pages == 2
    assert report.summary_values_to_preserve == 2
    assert report.properties_to_delete == 8


def test_apply_inserts_and_validates_before_schema_deletion() -> None:
    api = legacy_cleanup_api()

    report = cleanup_interview_properties(api, apply=True)

    assert api.operations[0].startswith("insert:")
    assert api.operations[-1] == "delete-properties"
    assert report.preserved_summary_values == 2
    assert report.updated_statuses == 2
    assert report.deleted_properties == 8
    assert set(api.schema) == set(KEEP_PROPERTIES)
    assert all(page_status(page) == "已整理" for page in api.pages)


def test_insert_failure_keeps_schema_and_statuses() -> None:
    api = legacy_cleanup_api(fail_on="insert")
    original_schema = set(api.schema)

    with pytest.raises(RuntimeError, match="insert"):
        cleanup_interview_properties(api, apply=True)

    assert set(api.schema) == original_schema
    assert not any(operation.startswith("status:") for operation in api.operations)
    assert "delete-properties" not in api.operations


def test_failed_body_verification_never_deletes_properties() -> None:
    api = legacy_cleanup_api(drop_inserted_text=True)

    with pytest.raises(RuntimeError, match="preservation"):
        cleanup_interview_properties(api, apply=True)

    assert "delete-properties" not in api.operations


def test_retry_skips_summaries_already_preserved() -> None:
    api = partially_preserved_cleanup_api()

    cleanup_interview_properties(api, apply=True)

    assert not any(operation.startswith("insert:") for operation in api.operations)
    assert api.operations[-1] == "delete-properties"


def test_already_clean_database_refuses_duplicate_execution() -> None:
    api = completed_cleanup_api()

    with pytest.raises(RuntimeError, match="already cleaned"):
        cleanup_interview_properties(api, apply=True)

    assert api.operations == []
```

- [ ] **Step 2: Run orchestration tests and verify missing symbols fail**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_cleanup_notion_interview_properties.py -q
```

Expected: tests fail because `CleanupApi`, `CleanupReport`, and `cleanup_interview_properties` are not defined.

- [ ] **Step 3: Implement the API protocol and preflight**

Define:

```python
class CleanupApi(Protocol):
    database_id: str

    def query_database(self, database_id: str) -> list[dict[str, object]]: ...
    def database_properties(self, database_id: str) -> dict[str, object]: ...
    def child_blocks(self, page_id: str) -> list[dict[str, object]]: ...
    def insert_children_after(
        self,
        page_id: str,
        after_block_id: str,
        children: list[dict[str, object]],
    ) -> list[dict[str, object]]: ...
    def update_page_properties(
        self, page_id: str, properties: dict[str, object]
    ) -> None: ...
    def delete_database_properties(
        self, database_id: str, property_names: tuple[str, ...]
    ) -> None: ...


@dataclass(frozen=True)
class CleanupReport:
    pages: int
    summary_values_to_preserve: int
    properties_to_delete: int
    preserved_summary_values: int
    updated_statuses: int
    deleted_properties: int
```

Preflight must:

- require exactly two database pages;
- validate each body with `validate_standard_review`;
- require all five kept property names;
- accept either the full eight-property legacy schema or the completed five-property schema;
- classify the five-property schema with both statuses already `已整理` as `already cleaned`;
- find exactly one `heading_2` block named `面试主线与整体评价` in each page body and require its block ID before insertion;
- count non-empty `总体复盘` and `结构化面经` values without printing values, titles, or IDs.

- [ ] **Step 4: Implement append-before-delete orchestration**

For `apply=True`:

1. Build all missing summary block pairs in memory.
2. Insert each page's pairs immediately after its `面试主线与整体评价` heading.
3. Re-fetch all pages and verify every original non-empty summary value appears exactly in its page body.
4. Validate both bodies still have the seven standard `heading_2` sections.
5. Update both page statuses using:

```python
{"分析状态": {"select": {"name": "已整理"}}}
```

6. Re-query and verify both statuses are `已整理`.
7. Delete the eight legacy schema properties in one database PATCH.
8. Re-fetch the database schema and require its property-name set to equal `KEEP_PROPERTIES`.
9. Re-fetch both bodies and validate the seven standard sections again.

If insertion or preservation validation fails, do not update statuses or delete properties. If status verification fails, do not delete properties. Retrying after a successful insertion must detect the exact text and avoid inserting it twice.

- [ ] **Step 5: Run orchestration and full tests**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_cleanup_notion_interview_properties.py -q
rtk proxy python -X utf8 -m pytest -q
```

Expected: all orchestration tests pass without network access or private fixtures.

- [ ] **Step 6: Commit guarded cleanup orchestration**

```powershell
rtk git add scripts/cleanup_notion_interview_properties.py tests/test_cleanup_notion_interview_properties.py
rtk git commit -m "feat: add guarded Notion property cleanup"
```

### Task 3: Add the Production Notion Adapter and CLI

**Files:**
- Modify: `scripts/cleanup_notion_interview_properties.py`
- Modify: `tests/test_cleanup_notion_interview_properties.py`

- [ ] **Step 1: Write failing HTTP payload and CLI-format tests**

Use a fake `urlopen` requester to assert:

```python
def test_delete_database_properties_uses_null_schema_values() -> None:
    api = CleanupHttpApi("synthetic-token", "synthetic-database", requester)

    api.delete_database_properties("synthetic-database", ("旧字段一", "旧字段二"))

    assert captured_json() == {
        "properties": {"旧字段一": None, "旧字段二": None}
    }


def test_insert_children_after_sends_after_block_id() -> None:
    api = CleanupHttpApi("synthetic-token", "synthetic-database", requester)

    api.insert_children_after("page", "heading", [paragraph("示例摘要")])

    assert captured_json()["after"] == "heading"
```

Add pure aggregate formatters and assert they contain counts only, never IDs or page titles.

- [ ] **Step 2: Run focused tests and verify missing adapter failure**

```powershell
rtk proxy python -X utf8 -m pytest tests/test_cleanup_notion_interview_properties.py -q
```

Expected: tests fail because `CleanupHttpApi` and aggregate formatters are undefined.

- [ ] **Step 3: Implement `CleanupHttpApi`**

Subclass the existing `NotionHttpApi` and add an injectable requester. Implement:

- `GET /v1/databases/{database_id}` for schema properties;
- `PATCH /v1/blocks/{page_id}/children` with `after` and at most 100 children;
- `PATCH /v1/pages/{page_id}` for page properties;
- `PATCH /v1/databases/{database_id}` with `None` values for deleted properties.

Every request must use `Authorization: Bearer ...`, `Notion-Version: 2022-06-28`, JSON content type, and a 30-second timeout. Responses must be validated as JSON objects. Never log request headers, tokens, IDs, titles, or body text.

- [ ] **Step 4: Implement aggregate-only CLI modes**

Support:

```powershell
rtk proxy python -X utf8 -m scripts.cleanup_notion_interview_properties --dry-run
rtk proxy python -X utf8 -m scripts.cleanup_notion_interview_properties --apply
```

Read `NOTION_TOKEN` and `NOTION_INTERVIEWS_DB_ID` through `read_setting`. Output only:

```text
dry-run: pages=2, summaries_to_preserve=2, properties_to_delete=8
applied: pages=2, preserved_summaries=2, updated_statuses=2, deleted_properties=8
```

- [ ] **Step 5: Run syntax and full tests**

```powershell
rtk proxy python -X utf8 -m py_compile scripts/cleanup_notion_interview_properties.py
rtk proxy python -X utf8 -m pytest -q
```

Expected: compilation succeeds and the full suite passes.

- [ ] **Step 6: Commit the production adapter and CLI**

```powershell
rtk git add scripts/cleanup_notion_interview_properties.py tests/test_cleanup_notion_interview_properties.py
rtk git commit -m "feat: add Notion property cleanup CLI"
```

### Task 4: Execute and Verify the Private Cleanup

**Files:**
- Execute: `scripts/cleanup_notion_interview_properties.py`
- Verify: private interview database and unchanged 180-question page

- [ ] **Step 1: Run the aggregate-only dry-run**

```powershell
rtk proxy python -X utf8 -m scripts.cleanup_notion_interview_properties --dry-run
```

Expected:

```text
dry-run: pages=2, summaries_to_preserve=2, properties_to_delete=8
```

No Notion mutation occurs.

- [ ] **Step 2: Apply the cleanup**

```powershell
rtk proxy python -X utf8 -m scripts.cleanup_notion_interview_properties --apply
```

Expected:

```text
applied: pages=2, preserved_summaries=2, updated_statuses=2, deleted_properties=8
```

- [ ] **Step 3: Verify live invariants without private text**

Run a read-only verifier and require:

```text
pages=2
database_properties=5
property_names_match=true
statuses_ready=2
standard_reviews=2
sections_per_review=[7, 7]
preserved_summary_values=2
answer_page_blocks=455
```

- [ ] **Step 4: Verify duplicate execution refusal**

```powershell
rtk proxy python -X utf8 -m scripts.cleanup_notion_interview_properties --dry-run
```

Expected: a clear `already cleaned` refusal with no mutation.

### Task 5: Final Privacy, Tests, and Branch Completion

**Files:**
- Verify: all files changed from the design commit through the feature branch head

- [ ] **Step 1: Run fresh verification**

```powershell
rtk proxy python -X utf8 -m py_compile scripts/cleanup_notion_interview_properties.py
rtk proxy python -X utf8 -m pytest -q
rtk git diff --check master...HEAD
```

Expected: compilation succeeds, all tests pass, and the diff check is empty.

- [ ] **Step 2: Scan changed files for private values**

Search the changed script, tests, and plan for runtime company names, candidate names, Notion/WPS URLs, UUID values, recommendation codes, and common token prefixes. Require zero matches. Synthetic names such as `示例公司` and synthetic IDs are allowed.

- [ ] **Step 3: Merge locally and re-test**

Because branch handling was delegated by the user, use the local-merge option from `superpowers:finishing-a-development-branch`:

```powershell
rtk git merge --ff-only feature/notion-interview-properties-cleanup
rtk proxy python -X utf8 -m pytest -q
```

Do not push GitHub. Preserve the two unrelated untracked Markdown files in the main workspace.

- [ ] **Step 4: Clean Git metadata safely**

After the merged test passes, remove the feature worktree through `git worktree remove` and delete the fully merged feature branch. Do not touch the unrelated `autumn-recruitment-agent-mvp` worktree or any inaccessible residual cache directory from earlier work.
