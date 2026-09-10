from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from job_hunt_agent.interviews.local_store import LocalInterviewRecord


STANDARD_SECTIONS = (
    "基本信息",
    "面试主线与整体评价",
    "核心问题复盘",
    "项目与回答亮点",
    "主要短板",
    "改进与准备建议",
    "后续动作",
)
_RICH_TEXT_LIMIT = 1_800
_CHILD_BATCH_SIZE = 100


class NotionInterviewClient(Protocol):
    def create_page(self, database_id: str, properties: dict[str, Any]) -> dict: ...

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict: ...

    def append_block_children(
        self,
        page_id: str,
        children: list[dict[str, Any]],
    ) -> dict: ...


def _rich_text(value: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": value}}]


def _text_block(block_type: str, value: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _rich_text(value)},
    }


def _chunks(value: str) -> Iterable[str]:
    for start in range(0, len(value), _RICH_TEXT_LIMIT):
        yield value[start : start + _RICH_TEXT_LIMIT]


def _body(record: LocalInterviewRecord) -> list[dict[str, Any]]:
    basic = [
        f"面试轮次：{record.round_name}",
        *([f"时间：{record.scheduled_at.isoformat()}"] if record.scheduled_at else []),
        *([f"形式：{record.format}"] if record.format else []),
        *([f"结果：{record.result}"] if record.result else []),
        *([f"自评分：{record.self_score}"] if record.self_score else []),
    ]
    paragraphs: list[dict[str, Any]] = []
    for paragraph in record.raw_notes.split("\n\n"):
        for chunk in _chunks(paragraph):
            paragraphs.append(_text_block("paragraph", chunk))

    blocks: list[dict[str, Any]] = []
    for section in STANDARD_SECTIONS:
        blocks.append(_text_block("heading_2", section))
        if section == "基本信息":
            blocks.extend(_text_block("bulleted_list_item", value) for value in basic)
        elif section == "核心问题复盘":
            blocks.extend(paragraphs)
    return blocks


def _properties(record: LocalInterviewRecord) -> dict[str, Any]:
    title = f"{record.company} | {record.round_name}"
    return {
        "面试": {"title": _rich_text(title[:_RICH_TEXT_LIMIT])},
        "时间": {
            "date": {"start": record.scheduled_at.isoformat()}
            if record.scheduled_at
            else None
        },
        "结果": {"select": {"name": record.result} if record.result else None},
        "面试轮次": {"rich_text": _rich_text(record.round_name)},
        "分析状态": {"select": {"name": "待整理"}},
    }


class NotionInterviewTarget:
    def __init__(
        self,
        client: NotionInterviewClient,
        interviews_database_id: str,
    ) -> None:
        self.client = client
        self.interviews_database_id = interviews_database_id

    def upsert(self, record: LocalInterviewRecord, operation_id: str) -> str:
        del operation_id
        properties = _properties(record)
        if record.notion_page_id:
            self.client.update_page(record.notion_page_id, properties)
            return record.notion_page_id

        page = self.client.create_page(self.interviews_database_id, properties)
        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id.strip():
            raise RuntimeError("Notion did not return a page identifier")

        blocks = _body(record)
        for start in range(0, len(blocks), _CHILD_BATCH_SIZE):
            self.client.append_block_children(
                page_id,
                blocks[start : start + _CHILD_BATCH_SIZE],
            )
        return page_id

