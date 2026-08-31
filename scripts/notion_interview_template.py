from __future__ import annotations

from typing import Final


STANDARD_SECTIONS: Final = (
    "基本信息",
    "面试主线与整体评价",
    "核心问题复盘",
    "项目与回答亮点",
    "主要短板",
    "改进与准备建议",
    "后续动作",
)

SUPPORTED_TYPES: Final = {
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


def _clone_rich_text(items: object) -> list[dict[str, object]]:
    if not isinstance(items, list):
        return []
    cloned: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        value = item.get(item_type) if isinstance(item_type, str) else None
        if item_type == "text" and isinstance(value, dict):
            output: dict[str, object] = {
                "type": "text",
                "text": {"content": str(value.get("content", ""))},
            }
        elif item_type == "equation" and isinstance(value, dict):
            output = {
                "type": "equation",
                "equation": {"expression": str(value.get("expression", ""))},
            }
        else:
            raise ValueError(f"unsupported rich text type: {item_type}")
        annotations = item.get("annotations")
        if isinstance(annotations, dict):
            output["annotations"] = dict(annotations)
        cloned.append(output)
    return cloned


def clone_block(
    block: dict[str, object], *, type_override: str | None = None
) -> dict[str, object]:
    source_type = block.get("type")
    if not isinstance(source_type, str) or source_type not in SUPPORTED_TYPES:
        raise ValueError(f"unsupported block type: {source_type}")
    output_type = type_override or source_type
    if output_type not in SUPPORTED_TYPES:
        raise ValueError(f"unsupported output block type: {output_type}")

    source_body = block.get(source_type)
    source_body = source_body if isinstance(source_body, dict) else {}
    output_body: dict[str, object] = {}
    if output_type != "divider":
        output_body["rich_text"] = _clone_rich_text(source_body.get("rich_text"))
    if isinstance(source_body.get("color"), str):
        output_body["color"] = source_body["color"]
    if output_type == "code":
        output_body["language"] = str(source_body.get("language", "plain text"))
        caption = _clone_rich_text(source_body.get("caption"))
        if caption:
            output_body["caption"] = caption
    if output_type == "to_do":
        output_body["checked"] = bool(source_body.get("checked", False))

    return {
        "object": "block",
        "type": output_type,
        output_type: output_body,
    }


def heading(level: int, value: str) -> dict[str, object]:
    if level not in {1, 2, 3}:
        raise ValueError("heading level must be 1, 2, or 3")
    block_type = f"heading_{level}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": value},
                }
            ]
        },
    }
