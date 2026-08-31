from __future__ import annotations

import re
from dataclasses import dataclass
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


def block_text(block: dict[str, object]) -> str:
    block_type = block.get("type")
    body = block.get(block_type) if isinstance(block_type, str) else None
    if not isinstance(body, dict):
        return ""
    items = body.get("rich_text")
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("plain_text"), str):
            parts.append(item["plain_text"])
            continue
        item_type = item.get("type")
        value = item.get(item_type) if isinstance(item_type, str) else None
        if item_type == "text" and isinstance(value, dict):
            parts.append(str(value.get("content", "")))
        elif item_type == "equation" and isinstance(value, dict):
            parts.append(str(value.get("expression", "")))
    return "".join(parts)


def _text_block(block_type: str, value: str) -> dict[str, object]:
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


def _property_value(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    property_type = value.get("type")
    raw = value.get(property_type) if isinstance(property_type, str) else None
    if property_type == "date" and isinstance(raw, dict):
        return str(raw.get("start", ""))
    if property_type == "select" and isinstance(raw, dict):
        return str(raw.get("name", ""))
    if property_type == "number" and raw is not None:
        return str(raw)
    if property_type in {"rich_text", "title"} and isinstance(raw, list):
        return block_text(
            {
                "type": "paragraph",
                "paragraph": {"rich_text": raw},
            }
        )
    return ""


def basic_information_blocks(
    properties: dict[str, object],
) -> list[dict[str, object]]:
    labels = ("时间", "结果", "形式", "面试轮次", "自评分")
    result: list[dict[str, object]] = []
    for label in labels:
        value = _property_value(properties.get(label))
        if value:
            result.append(_text_block("bulleted_list_item", f"{label}：{value}"))
    return result


def _find_heading(
    blocks: list[dict[str, object]],
    patterns: tuple[str, ...],
    *,
    start: int = 0,
) -> int:
    for index in range(start, len(blocks)):
        if blocks[index].get("type") != "heading_2":
            continue
        value = block_text(blocks[index])
        if any(pattern in value for pattern in patterns):
            return index
    raise ValueError(f"missing legacy heading matching: {patterns}")


def _clone_content(
    blocks: list[dict[str, object]],
    *,
    demote_heading_2: bool = True,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading_1":
            continue
        if block_type == "paragraph" and not block_text(block).strip():
            continue
        override = "heading_3" if demote_heading_2 and block_type == "heading_2" else None
        result.append(clone_block(block, type_override=override))
    return result


def _section(
    name: str, content: list[dict[str, object]]
) -> list[dict[str, object]]:
    return [heading(2, name), *content]


def standardize_structured_review(
    blocks: list[dict[str, object]], properties: dict[str, object]
) -> list[dict[str, object]]:
    main = _find_heading(blocks, ("这场面试到底在考什么",))
    background = _find_heading(blocks, ("候选人底子速览",), start=main + 1)
    core = _find_heading(blocks, ("核心面试题复盘",), start=background + 1)
    shortcomings = _find_heading(blocks, ("暴露的", "短板"), start=core + 1)
    matching = _find_heading(
        blocks, ("公司人才画像", "匹配度"), start=shortcomings + 1
    )
    improvements = _find_heading(blocks, ("面经建议",), start=matching + 1)
    next_actions = _find_heading(
        blocks, ("后续待确认", "后续动作"), start=improvements + 1
    )

    basic = basic_information_blocks(properties)
    basic.extend(_clone_content(blocks[:main]))
    main_content = _clone_content(blocks[main + 1 : background])
    main_content.extend(_clone_content(blocks[matching:improvements]))
    core_content = _clone_content(blocks[core + 1 : shortcomings])
    highlights = _clone_content(blocks[background + 1 : core])
    shortcoming_content = _clone_content(blocks[shortcomings + 1 : matching])
    improvement_content = _clone_content(blocks[improvements + 1 : next_actions])
    next_content = _clone_content(blocks[next_actions + 1 :])

    return [
        *_section(STANDARD_SECTIONS[0], basic),
        *_section(STANDARD_SECTIONS[1], main_content),
        *_section(STANDARD_SECTIONS[2], core_content),
        *_section(STANDARD_SECTIONS[3], highlights),
        *_section(STANDARD_SECTIONS[4], shortcoming_content),
        *_section(STANDARD_SECTIONS[5], improvement_content),
        *_section(STANDARD_SECTIONS[6], next_content),
    ]


_NUMBERED_CHINESE_HEADING = re.compile(r"^[一二三四五六七八九十]+、")
_NEXT_ACTION_WORDS = ("核实", "确认", "联系", "关注", "待补充")


def standardize_detailed_child_review(
    blocks: list[dict[str, object]], properties: dict[str, object]
) -> list[dict[str, object]]:
    basic_heading = _find_heading(blocks, ("基本信息",))
    core_headings = [
        index
        for index, block in enumerate(blocks)
        if index > basic_heading
        and block.get("type") == "heading_2"
        and _NUMBERED_CHINESE_HEADING.match(block_text(block))
    ]
    if not core_headings:
        raise ValueError("detailed review has no numbered technical sections")
    core = core_headings[0]
    highlights = _find_heading(blocks, ("亮点",), start=core + 1)
    shortcomings = _find_heading(
        blocks, ("风险", "短板"), start=highlights + 1
    )
    actions = _find_heading(
        blocks, ("行动清单", "后续动作"), start=shortcomings + 1
    )

    basic = basic_information_blocks(properties)
    basic.extend(_clone_content(blocks[basic_heading + 1 : core]))
    main_content = _clone_content(blocks[:basic_heading])
    core_content = _clone_content(blocks[core:highlights])
    highlight_content = _clone_content(blocks[highlights + 1 : shortcomings])
    shortcoming_content = _clone_content(blocks[shortcomings + 1 : actions])

    improvement_content: list[dict[str, object]] = []
    next_content: list[dict[str, object]] = []
    for block in blocks[actions + 1 :]:
        if block.get("type") == "paragraph" and not block_text(block).strip():
            continue
        clone = clone_block(block)
        if any(word in block_text(block) for word in _NEXT_ACTION_WORDS):
            next_content.append(clone)
        else:
            improvement_content.append(clone)

    return [
        *_section(STANDARD_SECTIONS[0], basic),
        *_section(STANDARD_SECTIONS[1], main_content),
        *_section(STANDARD_SECTIONS[2], core_content),
        *_section(STANDARD_SECTIONS[3], highlight_content),
        *_section(STANDARD_SECTIONS[4], shortcoming_content),
        *_section(STANDARD_SECTIONS[5], improvement_content),
        *_section(STANDARD_SECTIONS[6], next_content),
    ]


@dataclass(frozen=True)
class ReviewValidation:
    section_names: tuple[str, ...]
    question_count: int
    code_count: int
    action_count: int
    next_action_count: int


def validate_standard_review(
    blocks: list[dict[str, object]],
) -> ReviewValidation:
    sections = tuple(
        block_text(block)
        for block in blocks
        if block.get("type") == "heading_2"
    )
    if sections != STANDARD_SECTIONS:
        raise ValueError("review must contain the seven standard sections in order")

    current_section = ""
    next_action_count = 0
    for block in blocks:
        if block.get("type") == "heading_2":
            current_section = block_text(block)
        elif block.get("type") == "to_do" and current_section == "后续动作":
            next_action_count += 1

    return ReviewValidation(
        section_names=sections,
        question_count=sum(
            bool(re.match(r"^Q\d+[：:]", block_text(block).strip(), re.IGNORECASE))
            for block in blocks
        ),
        code_count=sum(block.get("type") == "code" for block in blocks),
        action_count=sum(block.get("type") == "to_do" for block in blocks),
        next_action_count=next_action_count,
    )
