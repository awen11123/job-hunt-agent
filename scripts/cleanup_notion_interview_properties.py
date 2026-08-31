from __future__ import annotations

from typing import Final

from scripts.notion_interview_template import heading


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
