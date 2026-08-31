from scripts.notion_interview_template import (
    STANDARD_SECTIONS,
    block_text,
    clone_block,
    heading,
    standardize_detailed_child_review,
    standardize_structured_review,
    validate_standard_review,
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


def synthetic_properties() -> dict[str, object]:
    return {
        "时间": {"type": "date", "date": {"start": "2026-08-01"}},
        "结果": {"type": "select", "select": {"name": "待沟通"}},
        "形式": {"type": "select", "select": None},
        "面试轮次": {"type": "rich_text", "rich_text": rich_text("技术面试")},
        "自评分": {"type": "number", "number": None},
    }


def synthetic_structured_review(question_count: int) -> list[dict[str, object]]:
    blocks = [
        source("paragraph", "面试结果说明"),
        source("heading_2", "整理说明"),
        source("paragraph", "转写已按语义归位"),
        source("heading_2", "一、这场面试到底在考什么"),
        source("paragraph", "重点考察工程落地"),
        source("heading_2", "二、候选人底子速览"),
        source("bulleted_list_item", "示例项目已上线"),
        source("heading_2", "三、核心面试题复盘"),
        source("heading_3", "模块 1：示例模块"),
    ]
    blocks.extend(
        source("numbered_list_item", f"Q{index}：示例问题 {index}")
        for index in range(1, question_count + 1)
    )
    blocks.extend(
        [
            source("heading_2", "四、暴露的主要短板"),
            source("bulleted_list_item", "底层原理需要加强"),
            source("heading_2", "五、公司人才画像与匹配度"),
            source("paragraph", "岗位与项目方向匹配"),
            source("heading_2", "六、面经建议"),
            source("numbered_list_item", "补齐性能工程知识"),
            source("heading_2", "七、后续待确认"),
            source("bulleted_list_item", "确认后续安排"),
        ]
    )
    return blocks


def synthetic_detailed_review(
    code_count: int, action_count: int
) -> list[dict[str, object]]:
    blocks = [
        source("heading_1", "详细面经"),
        source("paragraph", "人工整理版"),
        source("paragraph", "面试连续追问系统可靠性"),
        source("heading_2", "基本信息"),
        source("paragraph", "公司：示例公司"),
        source("heading_2", "一、多智能体架构"),
        source("paragraph", "面试官问题：为什么使用多智能体？"),
        source("heading_2", "二、SQL 现场题"),
    ]
    blocks.extend(
        source("code", f"SELECT {index};", language="sql")
        for index in range(1, code_count + 1)
    )
    blocks.extend(
        [
            source("heading_2", "本次面试的亮点"),
            source("bulleted_list_item", "能够讲清架构取舍"),
            source("heading_2", "本次暴露的主要风险"),
            source("bulleted_list_item", "底层细节不足"),
            source("heading_2", "复习与行动清单"),
        ]
    )
    for index in range(1, action_count + 1):
        value = f"练习技术问题 {index}"
        if index == action_count - 1:
            value = "核实转写中的技术名称"
        elif index == action_count:
            value = "联系招聘方确认后续流程"
        blocks.append(source("to_do", value, checked=False))
    return blocks


def section_names(blocks: list[dict[str, object]]) -> list[str]:
    return [
        block_text(block)
        for block in blocks
        if block.get("type") == "heading_2"
    ]


def test_structured_review_preserves_questions_and_uses_standard_sections() -> None:
    result = standardize_structured_review(
        synthetic_structured_review(question_count=17), synthetic_properties()
    )

    assert section_names(result) == list(STANDARD_SECTIONS)
    report = validate_standard_review(result)
    assert report.question_count == 17
    assert any(
        block.get("type") == "heading_3" and block_text(block) == "模块 1：示例模块"
        for block in result
    )


def test_detailed_review_preserves_code_and_splits_actions() -> None:
    result = standardize_detailed_child_review(
        synthetic_detailed_review(code_count=2, action_count=9),
        synthetic_properties(),
    )

    assert section_names(result) == list(STANDARD_SECTIONS)
    report = validate_standard_review(result)
    assert report.code_count == 2
    assert report.action_count == 9
    assert report.next_action_count == 2
    assert [
        block_text(block)
        for block in result
        if block.get("type") == "heading_3"
    ] == ["一、多智能体架构", "二、SQL 现场题"]


def test_validation_rejects_wrong_section_order() -> None:
    blocks = [heading(2, value) for value in reversed(STANDARD_SECTIONS)]

    try:
        validate_standard_review(blocks)
    except ValueError as exc:
        assert "seven standard sections" in str(exc)
    else:
        raise AssertionError("wrong section order should fail validation")
