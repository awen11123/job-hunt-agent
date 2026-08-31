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
