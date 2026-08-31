from scripts.notion_interview_template import (
    STANDARD_SECTIONS,
    clone_block,
    heading,
)


def rich_text(value: str) -> list[dict[str, object]]:
    return [
        {
            "type": "text",
            "text": {"content": value},
            "annotations": {"bold": True},
            "plain_text": value,
            "href": None,
        }
    ]


def source(block_type: str, value: str, **extra: object) -> dict[str, object]:
    body = {"rich_text": rich_text(value), **extra}
    return {
        "id": f"id-{value}",
        "created_time": "2026-08-31T00:00:00.000Z",
        "type": block_type,
        block_type: body,
    }


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


def test_clone_code_preserves_language_without_read_only_fields() -> None:
    assert clone_block(source("code", "SELECT 1;", language="sql")) == {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "SELECT 1;"},
                    "annotations": {"bold": True},
                }
            ],
            "language": "sql",
        },
    }


def test_clone_todo_preserves_checked_state() -> None:
    clone = clone_block(source("to_do", "复习 RRF", checked=True))

    assert clone["to_do"]["checked"] is True
    assert "id" not in clone
    assert "created_time" not in clone


def test_heading_builds_requested_level() -> None:
    block = heading(2, "基本信息")

    assert block["type"] == "heading_2"
    assert block["heading_2"]["rich_text"][0]["text"]["content"] == "基本信息"
