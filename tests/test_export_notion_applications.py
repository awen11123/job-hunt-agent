import json
from pathlib import Path
from urllib.request import Request

import pytest

from scripts.export_notion_applications import (
    main,
    normalize_application,
    query_database,
    read_setting,
)


def rich_text(value: str) -> list[dict[str, str]]:
    return [{"plain_text": value}]


def synthetic_notion_page() -> dict[str, object]:
    return {
        "id": "private-page-id",
        "url": "https://notion.example/private-page",
        "properties": {
            "公司": {"type": "title", "title": rich_text("示例企业")},
            "岗位": {"type": "rich_text", "rich_text": rich_text("Agent 工程师")},
            "投递日期": {"type": "date", "date": {"start": "2026-08-30"}},
            "地点": {"type": "rich_text", "rich_text": rich_text("杭州")},
            "当前阶段": {"type": "select", "select": {"name": "测评完成"}},
            "下一步": {"type": "rich_text", "rich_text": rich_text("等待结果")},
            "截止日期": {"type": "date", "date": None},
            "JD 链接": {"type": "url", "url": "https://example.com/job"},
            "优先级": {"type": "select", "select": {"name": "高"}},
            "结构化面经": {
                "type": "rich_text",
                "rich_text": rich_text("不应导出"),
            },
        },
    }


def test_normalize_application_maps_only_tracker_fields() -> None:
    assert normalize_application(synthetic_notion_page()) == {
        "company": "示例企业",
        "role": "Agent 工程师",
        "applied_date": "2026-08-30",
        "location": "杭州",
        "status": "测评完成",
        "next_step": "等待结果",
        "next_time": "",
        "link": "https://example.com/job",
        "notes": "高优先级",
    }


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_query_database_follows_pagination_cursor() -> None:
    responses = iter(
        [
            {"results": [{"id": "first"}], "has_more": True, "next_cursor": "next"},
            {"results": [{"id": "second"}], "has_more": False, "next_cursor": None},
        ]
    )
    bodies: list[dict[str, object]] = []

    def requester(request: Request) -> FakeResponse:
        bodies.append(json.loads(request.data or b"{}"))
        return FakeResponse(next(responses))

    pages = query_database("secret-token", "database-id", requester=requester)

    assert [page["id"] for page in pages] == ["first", "second"]
    assert bodies == [
        {"page_size": 100},
        {"page_size": 100, "start_cursor": "next"},
    ]


def test_read_setting_prefers_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRACKER_TEST_SETTING", "process-value")

    assert read_setting("TRACKER_TEST_SETTING") == "process-value"


def test_read_setting_falls_back_to_windows_user_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRACKER_TEST_SETTING", raising=False)

    assert (
        read_setting(
            "TRACKER_TEST_SETTING",
            registry_reader=lambda name: "user-value" if name else "",
        )
        == "user-value"
    )


def test_main_exports_normalized_private_json_without_logging_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = "private-token-value"
    database_id = "private-database-id"
    output = tmp_path / "applications.json"
    monkeypatch.setenv("NOTION_TOKEN", token)
    monkeypatch.setenv("NOTION_APPLICATIONS_DB_ID", database_id)

    def fake_query(received_token: str, received_database_id: str) -> list[dict[str, object]]:
        assert received_token == token
        assert received_database_id == database_id
        return [synthetic_notion_page()]

    monkeypatch.setattr(
        "scripts.export_notion_applications.query_database", fake_query
    )

    assert main(["--output", str(output)]) == 0

    assert json.loads(output.read_text(encoding="utf-8")) == [
        normalize_application(synthetic_notion_page())
    ]
    captured = capsys.readouterr()
    assert str(output) in captured.out
    assert "1 records" in captured.out
    assert token not in captured.out + captured.err
    assert database_id not in captured.out + captured.err
    assert "示例企业" not in captured.out + captured.err
