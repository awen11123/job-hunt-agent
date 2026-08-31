from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from scripts.notion_interview_template import (
    block_text,
    heading,
    validate_standard_review,
)


KEEP_PROPERTIES: Final = (
    "面试",
    "时间",
    "结果",
    "面试轮次",
    "分析状态",
)

DROP_PROPERTIES: Final = (
    "Prompt 版本",
    "关联投递",
    "原始笔记",
    "形式",
    "总体复盘",
    "模型版本",
    "结构化面经",
    "自评分",
)

SUMMARY_FIELDS: Final = (
    ("总体复盘", "总体复盘"),
    ("结构化面经", "考察主线"),
)


def property_text(prop: object) -> str:
    if not isinstance(prop, dict):
        return ""
    property_type = prop.get("type")
    if property_type not in {"rich_text", "title"}:
        return ""
    items = prop.get(property_type)
    if not isinstance(items, list):
        return ""

    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        plain_text = item.get("plain_text")
        if isinstance(plain_text, str):
            parts.append(plain_text)
            continue
        item_type = item.get("type")
        value = item.get(item_type) if isinstance(item_type, str) else None
        if item_type == "text" and isinstance(value, dict):
            parts.append(str(value.get("content", "")))
        elif item_type == "equation" and isinstance(value, dict):
            parts.append(str(value.get("expression", "")))
    return "".join(parts)


def _paragraph(value: str) -> dict[str, object]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": value},
                }
            ]
        },
    }


def build_summary_blocks(
    properties: dict[str, object], existing_body_text: str
) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for property_name, heading_name in SUMMARY_FIELDS:
        value = property_text(properties.get(property_name))
        if not value or value in existing_body_text:
            continue
        blocks.extend((heading(3, heading_name), _paragraph(value)))
    return blocks


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


def _require_id(value: dict[str, object], kind: str) -> str:
    item_id = value.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise RuntimeError(f"{kind} is missing an ID")
    return item_id


def _properties(page: dict[str, object]) -> dict[str, object]:
    value = page.get("properties")
    if not isinstance(value, dict):
        raise RuntimeError("interview page properties are missing")
    return value


def _status(page: dict[str, object]) -> str:
    value = _properties(page).get("分析状态")
    if not isinstance(value, dict) or value.get("type") != "select":
        return ""
    selected = value.get("select")
    return str(selected.get("name", "")) if isinstance(selected, dict) else ""


def _body_text(blocks: list[dict[str, object]]) -> str:
    return "\n".join(block_text(block) for block in blocks)


def _main_heading_id(blocks: list[dict[str, object]]) -> str:
    matches = [
        block
        for block in blocks
        if block.get("type") == "heading_2"
        and block_text(block) == "面试主线与整体评价"
    ]
    if len(matches) != 1:
        raise RuntimeError("expected exactly one main interview review heading")
    return _require_id(matches[0], "main interview review heading")


def cleanup_interview_properties(
    api: CleanupApi,
    *,
    apply: bool,
    database_id: str | None = None,
) -> CleanupReport:
    database_id = database_id or api.database_id
    pages = api.query_database(database_id)
    if len(pages) != 2:
        raise RuntimeError("expected exactly two interview database pages")

    schema_names = set(api.database_properties(database_id))
    keep_names = set(KEEP_PROPERTIES)
    full_names = keep_names | set(DROP_PROPERTIES)
    if schema_names == keep_names:
        if all(_status(page) == "已整理" for page in pages):
            raise RuntimeError("interview database properties are already cleaned")
        raise RuntimeError("interview database has a partial cleanup state")
    if schema_names != full_names:
        raise RuntimeError("interview database property schema is unexpected")

    plans: list[
        tuple[
            str,
            str,
            list[dict[str, object]],
            tuple[str, ...],
        ]
    ] = []
    summary_count = 0
    for page in pages:
        page_id = _require_id(page, "interview database page")
        blocks = api.child_blocks(page_id)
        validate_standard_review(blocks)
        main_heading_id = _main_heading_id(blocks)
        properties = _properties(page)
        summary_values = tuple(
            value
            for property_name, _ in SUMMARY_FIELDS
            if (value := property_text(properties.get(property_name)))
        )
        summary_count += len(summary_values)
        additions = build_summary_blocks(properties, _body_text(blocks))
        plans.append((page_id, main_heading_id, additions, summary_values))

    if not apply:
        return CleanupReport(
            pages=len(pages),
            summary_values_to_preserve=summary_count,
            properties_to_delete=len(DROP_PROPERTIES),
            preserved_summary_values=0,
            updated_statuses=0,
            deleted_properties=0,
        )

    for page_id, main_heading_id, additions, _ in plans:
        if additions:
            api.insert_children_after(page_id, main_heading_id, additions)

    for page_id, _, _, summary_values in plans:
        blocks = api.child_blocks(page_id)
        validate_standard_review(blocks)
        body = _body_text(blocks)
        if any(value not in body for value in summary_values):
            raise RuntimeError("interview summary preservation validation failed")

    status_update = {"分析状态": {"select": {"name": "已整理"}}}
    for page_id, _, _, _ in plans:
        api.update_page_properties(page_id, status_update)

    refreshed_pages = api.query_database(database_id)
    if len(refreshed_pages) != 2 or any(
        _status(page) != "已整理" for page in refreshed_pages
    ):
        raise RuntimeError("interview analysis status validation failed")

    api.delete_database_properties(database_id, DROP_PROPERTIES)
    if set(api.database_properties(database_id)) != keep_names:
        raise RuntimeError("interview database schema cleanup validation failed")

    for page_id, _, _, _ in plans:
        validate_standard_review(api.child_blocks(page_id))

    return CleanupReport(
        pages=len(pages),
        summary_values_to_preserve=summary_count,
        properties_to_delete=len(DROP_PROPERTIES),
        preserved_summary_values=summary_count,
        updated_statuses=len(pages),
        deleted_properties=len(DROP_PROPERTIES),
    )
