import json
from urllib.request import Request

import pytest

from scripts.simplify_notion_overview import (
    apply_cleanup,
    build_replacement_blocks,
    discover_marker_page,
    fetch_database_parent_page_id,
    fetch_child_blocks,
    main,
    select_generated_block_ids,
)


def block(block_id: str, block_type: str, text: str = "") -> dict[str, object]:
    value: dict[str, object] = {}
    if block_type in {"paragraph", "heading_1"}:
        value["rich_text"] = [{"plain_text": text}]
    return {"id": block_id, "type": block_type, block_type: value}


def test_select_generated_block_ids_only_returns_marker_range() -> None:
    blocks = [
        block("keep-before", "child_page"),
        block("start", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"),
        block("generated", "heading_1", "秋招总览"),
        block("end", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"),
        block("keep-after", "paragraph", "人工内容"),
    ]

    assert select_generated_block_ids(blocks) == ["start", "generated", "end"]


def test_select_generated_block_ids_rejects_missing_or_duplicate_ranges() -> None:
    missing_end = [
        block("start", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_START")
    ]
    duplicate_start = [
        block("start-1", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"),
        block("start-2", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"),
        block("end", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"),
    ]

    for blocks in (missing_end, duplicate_start):
        try:
            select_generated_block_ids(blocks)
        except RuntimeError as exc:
            assert "exactly one complete" in str(exc)
        else:
            raise AssertionError("unsafe marker layout should be rejected")


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_fetch_child_blocks_follows_pagination_without_exposing_ids() -> None:
    responses = iter(
        [
            {"results": [{"id": "first"}], "has_more": True, "next_cursor": "next"},
            {"results": [{"id": "second"}], "has_more": False},
        ]
    )
    requests: list[Request] = []

    def requester(request: Request) -> FakeResponse:
        requests.append(request)
        return FakeResponse(next(responses))

    blocks = fetch_child_blocks("secret", "private-page", requester=requester)

    assert [item["id"] for item in blocks] == ["first", "second"]
    assert requests[0].method == "GET"
    assert "start_cursor" not in requests[0].full_url
    assert "start_cursor=next" in requests[1].full_url


def test_fetch_database_parent_page_id_uses_notion_metadata() -> None:
    def requester(request: Request) -> FakeResponse:
        assert request.method == "GET"
        assert request.full_url.endswith("/v1/databases/applications-database")
        return FakeResponse(
            {"parent": {"type": "page_id", "page_id": "overview-page"}}
        )

    assert (
        fetch_database_parent_page_id(
            "secret", "applications-database", requester=requester
        )
        == "overview-page"
    )


def test_discover_marker_page_checks_direct_child_pages() -> None:
    payloads = {
        "root": {
            "results": [block("overview-child", "child_page")],
            "has_more": False,
        },
        "overview-child": {
            "results": generated_overview_blocks(),
            "has_more": False,
        },
    }

    def requester(request: Request) -> FakeResponse:
        page_id = request.full_url.split("/blocks/", 1)[1].split("/children", 1)[0]
        return FakeResponse(payloads[page_id])

    page_id, blocks = discover_marker_page("secret", "root", requester=requester)

    assert page_id == "overview-child"
    assert select_generated_block_ids(blocks) == ["start", "generated", "end"]


def test_build_replacement_blocks_links_only_the_interview_database() -> None:
    blocks = build_replacement_blocks("interviews-database")

    assert len(blocks) == 5
    assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == (
        "JOB_HUNT_AGENT_INTERVIEW_OVERVIEW_START"
    )
    assert blocks[2]["paragraph"]["rich_text"][0]["text"]["content"] == (
        "投递记录已迁移到 WPS 云文档；这里仅保留面试复盘。"
    )
    assert blocks[3]["link_to_page"] == {"database_id": "interviews-database"}


def generated_overview_blocks() -> list[dict[str, object]]:
    return [
        block("keep-before", "child_page"),
        block("start", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"),
        block("generated", "heading_1", "秋招总览"),
        block("end", "paragraph", "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"),
        block("keep-after", "paragraph", "人工内容"),
    ]


def test_main_dry_run_reports_only_counts_and_types(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "private-token")
    monkeypatch.setenv("JOB_HUNT_OVERVIEW_PAGE_ID", "private-overview")
    monkeypatch.setenv("NOTION_INTERVIEWS_DB_ID", "private-interviews")
    monkeypatch.setattr(
        "scripts.simplify_notion_overview.fetch_child_blocks",
        lambda *_args, **_kwargs: generated_overview_blocks(),
    )

    def forbidden_apply(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("dry-run must not mutate Notion")

    monkeypatch.setattr(
        "scripts.simplify_notion_overview.apply_cleanup", forbidden_apply
    )

    assert main(["--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "3 blocks" in output
    assert "heading_1=1" in output
    assert "paragraph=2" in output
    assert "private-" not in output
    assert "start" not in output


def test_apply_cleanup_archives_only_range_then_renames_and_appends() -> None:
    requests: list[Request] = []

    def requester(request: Request) -> FakeResponse:
        requests.append(request)
        return FakeResponse({})

    changed = apply_cleanup(
        "secret",
        "overview-page",
        "interviews-database",
        generated_overview_blocks(),
        requester=requester,
    )

    assert changed == 3
    archived_urls = [request.full_url for request in requests[:3]]
    assert archived_urls == [
        "https://api.notion.com/v1/blocks/start",
        "https://api.notion.com/v1/blocks/generated",
        "https://api.notion.com/v1/blocks/end",
    ]
    assert all(json.loads(request.data or b"{}") == {"archived": True} for request in requests[:3])
    assert requests[3].full_url.endswith("/v1/pages/overview-page")
    assert requests[4].full_url.endswith("/v1/blocks/overview-page/children")
    assert len(json.loads(requests[4].data or b"{}")["children"]) == 5
