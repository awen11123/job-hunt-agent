from copy import deepcopy

import pytest

from scripts.cleanup_notion_interview_properties import (
    CleanupReport,
    DROP_PROPERTIES,
    KEEP_PROPERTIES,
    build_summary_blocks,
    cleanup_interview_properties,
    property_text,
)
from scripts.notion_interview_template import STANDARD_SECTIONS, block_text, heading


def rich_property(value: str) -> dict[str, object]:
    return {
        "type": "rich_text",
        "rich_text": [
            {
                "type": "text",
                "text": {"content": value},
                "plain_text": value,
            }
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


def test_property_text_reads_visible_rich_text() -> None:
    assert property_text(rich_property("示例摘要")) == "示例摘要"
    assert property_text({"type": "rich_text", "rich_text": []}) == ""
    assert property_text(None) == ""


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


def test_summary_blocks_skip_empty_and_existing_text() -> None:
    properties = {
        "总体复盘": rich_property("示例总体判断"),
        "结构化面经": rich_property(""),
    }

    assert build_summary_blocks(
        properties, existing_body_text="正文已有：示例总体判断"
    ) == []


def select_property(value: str) -> dict[str, object]:
    return {"type": "select", "select": {"name": value}}


def synthetic_schema() -> dict[str, object]:
    return {name: {"type": "synthetic"} for name in (*KEEP_PROPERTIES, *DROP_PROPERTIES)}


def synthetic_page_properties(*, with_summaries: bool) -> dict[str, object]:
    properties: dict[str, object] = {
        "面试": {"type": "title", "title": []},
        "时间": {"type": "date", "date": {"start": "2026-08-01"}},
        "结果": select_property("待沟通"),
        "面试轮次": rich_property("技术面试"),
        "分析状态": select_property("completed"),
        "Prompt 版本": rich_property(""),
        "关联投递": {"type": "relation", "relation": []},
        "原始笔记": rich_property("正文已经保存" if with_summaries else ""),
        "形式": {"type": "select", "select": None},
        "总体复盘": rich_property("示例总体判断" if with_summaries else ""),
        "模型版本": rich_property(""),
        "结构化面经": rich_property("示例考察主线" if with_summaries else ""),
        "自评分": {"type": "number", "number": None},
    }
    return properties


def standard_body(prefix: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for index, section in enumerate(STANDARD_SECTIONS):
        section_heading = heading(2, section)
        section_heading["id"] = f"{prefix}-heading-{index}"
        blocks.append(section_heading)
        blocks.append(
            {
                "id": f"{prefix}-paragraph-{index}",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": f"示例正文 {index}"},
                            "plain_text": f"示例正文 {index}",
                        }
                    ]
                },
            }
        )
    return blocks


def page_status(page: dict[str, object]) -> str:
    properties = page.get("properties", {})
    status = properties.get("分析状态", {}) if isinstance(properties, dict) else {}
    selected = status.get("select") if isinstance(status, dict) else None
    return str(selected.get("name", "")) if isinstance(selected, dict) else ""


class FakeCleanupApi:
    database_id = "synthetic-database"

    def __init__(
        self,
        *,
        schema: dict[str, object] | None = None,
        summaries_already_in_body: bool = False,
        fail_on: str | None = None,
        drop_inserted_text: bool = False,
    ) -> None:
        self.schema = deepcopy(schema or synthetic_schema())
        self.pages = [
            {
                "id": "page-a",
                "properties": synthetic_page_properties(with_summaries=True),
            },
            {
                "id": "page-b",
                "properties": synthetic_page_properties(with_summaries=False),
            },
        ]
        self.blocks = {
            "page-a": standard_body("a"),
            "page-b": standard_body("b"),
        }
        if summaries_already_in_body:
            self.blocks["page-a"][3:3] = self._created(
                "existing",
                build_summary_blocks(
                    self.pages[0]["properties"], existing_body_text=""
                ),
            )
        self.operations: list[str] = []
        self.fail_on = fail_on
        self.drop_inserted_text = drop_inserted_text

    @staticmethod
    def _created(
        prefix: str, blocks: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        created = deepcopy(blocks)
        for index, block in enumerate(created):
            block["id"] = f"{prefix}-{index}"
        return created

    def query_database(self, database_id: str) -> list[dict[str, object]]:
        assert database_id == self.database_id
        return deepcopy(self.pages)

    def database_properties(self, database_id: str) -> dict[str, object]:
        assert database_id == self.database_id
        return deepcopy(self.schema)

    def child_blocks(self, page_id: str) -> list[dict[str, object]]:
        return deepcopy(self.blocks[page_id])

    def insert_children_after(
        self,
        page_id: str,
        after_block_id: str,
        children: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        self.operations.append(f"insert:{page_id}")
        if self.fail_on == "insert":
            raise RuntimeError("insert")
        created = self._created(f"inserted-{page_id}", children)
        if self.drop_inserted_text:
            created = [block for block in created if block.get("type") == "heading_3"]
        index = next(
            index
            for index, block in enumerate(self.blocks[page_id])
            if block.get("id") == after_block_id
        )
        self.blocks[page_id][index + 1 : index + 1] = created
        return deepcopy(created)

    def update_page_properties(
        self, page_id: str, properties: dict[str, object]
    ) -> None:
        self.operations.append(f"status:{page_id}")
        page = next(page for page in self.pages if page.get("id") == page_id)
        page_properties = page["properties"]
        assert isinstance(page_properties, dict)
        for property_name, value in properties.items():
            current = page_properties.get(property_name)
            property_type = current.get("type") if isinstance(current, dict) else None
            assert isinstance(value, dict)
            page_properties[property_name] = {
                "type": property_type,
                **deepcopy(value),
            }

    def delete_database_properties(
        self, database_id: str, property_names: tuple[str, ...]
    ) -> None:
        assert database_id == self.database_id
        self.operations.append("delete-properties")
        for property_name in property_names:
            self.schema.pop(property_name, None)
        for page in self.pages:
            properties = page.get("properties")
            assert isinstance(properties, dict)
            for property_name in property_names:
                properties.pop(property_name, None)


def legacy_cleanup_api(**kwargs: object) -> FakeCleanupApi:
    return FakeCleanupApi(**kwargs)


def test_dry_run_never_mutates() -> None:
    api = legacy_cleanup_api()

    report = cleanup_interview_properties(api, apply=False)

    assert api.operations == []
    assert report == CleanupReport(
        pages=2,
        summary_values_to_preserve=2,
        properties_to_delete=8,
        preserved_summary_values=0,
        updated_statuses=0,
        deleted_properties=0,
    )


def test_apply_inserts_and_validates_before_schema_deletion() -> None:
    api = legacy_cleanup_api()

    report = cleanup_interview_properties(api, apply=True)

    assert api.operations[0] == "insert:page-a"
    assert api.operations[-1] == "delete-properties"
    assert report.preserved_summary_values == 2
    assert report.updated_statuses == 2
    assert report.deleted_properties == 8
    assert set(api.schema) == set(KEEP_PROPERTIES)
    assert all(page_status(page) == "已整理" for page in api.pages)
    main_heading_index = next(
        index
        for index, block in enumerate(api.blocks["page-a"])
        if block_text(block) == "面试主线与整体评价"
    )
    assert block_text(api.blocks["page-a"][main_heading_index + 1]) == "总体复盘"


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

    assert not any(operation.startswith("status:") for operation in api.operations)
    assert "delete-properties" not in api.operations


def test_retry_skips_summaries_already_preserved() -> None:
    api = legacy_cleanup_api(summaries_already_in_body=True)

    cleanup_interview_properties(api, apply=True)

    assert not any(operation.startswith("insert:") for operation in api.operations)
    assert api.operations[-1] == "delete-properties"


def test_already_clean_database_refuses_duplicate_execution() -> None:
    api = FakeCleanupApi(schema={name: {} for name in KEEP_PROPERTIES})
    for page in api.pages:
        properties = page.get("properties")
        assert isinstance(properties, dict)
        properties["分析状态"] = select_property("已整理")
        for property_name in DROP_PROPERTIES:
            properties.pop(property_name, None)

    with pytest.raises(RuntimeError, match="already cleaned"):
        cleanup_interview_properties(api, apply=True)

    assert api.operations == []
