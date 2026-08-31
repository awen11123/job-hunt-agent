from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.notion_interview_template import (
    STANDARD_SECTIONS,
    heading,
    standardize_detailed_child_review,
    standardize_structured_review,
)
from scripts.standardize_notion_interviews import migrate_reviews
from tests.test_notion_interview_template import (
    synthetic_detailed_review,
    synthetic_properties,
    synthetic_structured_review,
)


class FakeNotionApi:
    database_id = "synthetic-database"

    def __init__(
        self,
        *,
        structured_body: list[dict[str, object]],
        detailed_target_body: list[dict[str, object]],
        standalone_body: list[dict[str, object]] | None,
        fail_on: str | None = None,
    ) -> None:
        self.pages = [
            {
                "id": "structured",
                "properties": synthetic_properties(),
            },
            {
                "id": "detailed",
                "properties": synthetic_properties(),
            },
        ]
        self.blocks = {
            "structured": self._with_ids("structured", structured_body),
            "detailed": self._with_ids("detailed", detailed_target_body),
            "root": [
                {
                    "id": "reviews-container",
                    "type": "child_page",
                    "child_page": {"title": "面试复盘"},
                }
            ],
            "reviews-container": [],
        }
        if standalone_body is not None:
            self.blocks["reviews-container"] = [
                {
                    "id": "standalone",
                    "type": "child_page",
                    "child_page": {"title": "示例面经"},
                }
            ]
            self.blocks["standalone"] = self._with_ids(
                "standalone", standalone_body
            )
        self.archived_pages: set[str] = set()
        self.operations: list[str] = []
        self.fail_on = fail_on

    @staticmethod
    def _with_ids(
        prefix: str, blocks: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        result = deepcopy(blocks)
        for index, block in enumerate(result):
            block["id"] = f"{prefix}-{index}"
        return result

    def query_database(self, database_id: str) -> list[dict[str, object]]:
        assert database_id == self.database_id
        return deepcopy(self.pages)

    def database_parent_page_id(self, database_id: str) -> str:
        assert database_id == self.database_id
        return "root"

    def child_blocks(self, block_id: str) -> list[dict[str, object]]:
        return deepcopy(self.blocks.get(block_id, []))

    def append_children(
        self, block_id: str, children: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        operation = f"append:{block_id}"
        self.operations.append(operation)
        if self.fail_on == operation:
            raise RuntimeError(operation)
        created = self._with_ids(
            f"{block_id}-new-{len(self.blocks[block_id])}", children
        )
        self.blocks[block_id].extend(created)
        return deepcopy(created)

    def archive_block(self, block_id: str) -> None:
        self.operations.append("archive:legacy-blocks")
        for page_blocks in self.blocks.values():
            page_blocks[:] = [block for block in page_blocks if block.get("id") != block_id]

    def archive_page(self, page_id: str) -> None:
        self.operations.append("archive:standalone-page")
        self.archived_pages.add(page_id)
        for page_blocks in self.blocks.values():
            page_blocks[:] = [block for block in page_blocks if block.get("id") != page_id]


def legacy_api(*, fail_on: str | None = None) -> FakeNotionApi:
    return FakeNotionApi(
        structured_body=synthetic_structured_review(question_count=17),
        detailed_target_body=[],
        standalone_body=synthetic_detailed_review(code_count=2, action_count=9),
        fail_on=fail_on,
    )


def standard_blocks(kind: str) -> list[dict[str, object]]:
    properties = synthetic_properties()
    if kind == "structured":
        return standardize_structured_review(
            synthetic_structured_review(question_count=17), properties
        )
    return standardize_detailed_child_review(
        synthetic_detailed_review(code_count=2, action_count=9), properties
    )


def test_migration_appends_and_validates_before_archiving() -> None:
    api = legacy_api()

    report = migrate_reviews(api, apply=True)

    assert api.operations[:2] == ["append:detailed", "append:structured"]
    assert "archive:legacy-blocks" in api.operations[2:]
    assert api.operations[-1] == "archive:standalone-page"
    assert report.created_reviews == 2
    assert report.archived_standalone_pages == 1


def test_migration_dry_run_never_mutates() -> None:
    api = legacy_api()

    report = migrate_reviews(api, apply=False)

    assert api.operations == []
    assert report.created_reviews == 0
    assert report.planned_reviews == 2
    assert report.legacy_blocks == len(
        synthetic_structured_review(question_count=17)
    ) + len(synthetic_detailed_review(code_count=2, action_count=9))


def test_migration_refuses_duplicate_standard_sections() -> None:
    api = FakeNotionApi(
        structured_body=standard_blocks("structured"),
        detailed_target_body=standard_blocks("detailed"),
        standalone_body=None,
    )

    with pytest.raises(RuntimeError, match="already standardized"):
        migrate_reviews(api, apply=True)

    assert api.operations == []


def test_failed_append_preserves_every_legacy_source() -> None:
    api = legacy_api(fail_on="append:structured")
    structured_ids = [block["id"] for block in api.blocks["structured"]]

    with pytest.raises(RuntimeError, match="append:structured"):
        migrate_reviews(api, apply=True)

    assert [block["id"] for block in api.blocks["structured"]] == structured_ids
    assert "standalone" not in api.archived_pages
    assert "archive:legacy-blocks" not in api.operations
    assert "archive:standalone-page" not in api.operations


def test_migration_resumes_partial_append_without_duplicate_sections() -> None:
    api = FakeNotionApi(
        structured_body=synthetic_structured_review(question_count=17),
        detailed_target_body=standard_blocks("detailed"),
        standalone_body=synthetic_detailed_review(code_count=2, action_count=9),
    )

    migrate_reviews(api, apply=True)

    assert "append:detailed" not in api.operations
    assert api.operations.count("append:structured") == 1
    assert api.operations[-1] == "archive:standalone-page"
    detailed_sections = [
        block
        for block in api.blocks["detailed"]
        if block.get("type") == "heading_2"
    ]
    assert len(detailed_sections) == len(STANDARD_SECTIONS)


def test_migration_resumes_archival_after_both_reviews_were_appended() -> None:
    api = FakeNotionApi(
        structured_body=[
            *synthetic_structured_review(question_count=17),
            *standard_blocks("structured"),
        ],
        detailed_target_body=standard_blocks("detailed"),
        standalone_body=synthetic_detailed_review(code_count=2, action_count=9),
    )

    report = migrate_reviews(api, apply=True)

    assert not any(operation.startswith("append:") for operation in api.operations)
    assert api.operations[-1] == "archive:standalone-page"
    assert report.archived_legacy_blocks == len(
        synthetic_structured_review(question_count=17)
    )


def test_migration_rejects_wrong_database_size_without_mutation() -> None:
    api = legacy_api()
    api.pages.pop()

    with pytest.raises(RuntimeError, match="exactly two"):
        migrate_reviews(api, apply=True)

    assert api.operations == []


def test_migration_does_not_accept_seven_unrelated_headings() -> None:
    api = FakeNotionApi(
        structured_body=[heading(2, f"无关章节 {index}") for index in range(7)],
        detailed_target_body=[],
        standalone_body=synthetic_detailed_review(code_count=2, action_count=9),
    )

    with pytest.raises(RuntimeError, match="classify"):
        migrate_reviews(api, apply=False)

    assert api.operations == []
