from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from collections import Counter
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.export_notion_applications import read_setting


START = "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"
END = "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"
NEW_START = "JOB_HUNT_AGENT_INTERVIEW_OVERVIEW_START"
NEW_END = "JOB_HUNT_AGENT_INTERVIEW_OVERVIEW_END"


def _request_json(
    token: str,
    request: Request,
    *,
    requester: Callable[[Request], Any] | None = None,
) -> dict[str, object]:
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Notion-Version", "2022-06-28")
    requester = requester or (lambda value: urlopen(value, timeout=30))
    with requester(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Notion response must be a JSON object")
    return payload


def fetch_database_parent_page_id(
    token: str,
    database_id: str,
    *,
    requester: Callable[[Request], Any] | None = None,
) -> str:
    request = Request(
        f"https://api.notion.com/v1/databases/{database_id}", method="GET"
    )
    payload = _request_json(token, request, requester=requester)
    parent = payload.get("parent")
    if not isinstance(parent, dict) or parent.get("type") != "page_id":
        raise RuntimeError("applications database is not nested under an overview page")
    page_id = parent.get("page_id")
    if not isinstance(page_id, str) or not page_id:
        raise RuntimeError("applications database parent page ID is missing")
    return page_id


def fetch_child_blocks(
    token: str,
    page_id: str,
    *,
    requester: Callable[[Request], Any] | None = None,
) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    cursor: str | None = None
    while True:
        query: dict[str, object] = {"page_size": 100}
        if cursor:
            query["start_cursor"] = cursor
        request = Request(
            f"https://api.notion.com/v1/blocks/{page_id}/children?{urlencode(query)}",
            method="GET",
        )
        payload = _request_json(token, request, requester=requester)
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Notion response results must be a list")
        blocks.extend(item for item in results if isinstance(item, dict))
        if not payload.get("has_more"):
            return blocks
        next_cursor = payload.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise ValueError("Notion pagination response is missing next_cursor")
        cursor = next_cursor


def discover_marker_page(
    token: str,
    root_page_id: str,
    *,
    requester: Callable[[Request], Any] | None = None,
) -> tuple[str, list[dict[str, object]]]:
    root_blocks = fetch_child_blocks(token, root_page_id, requester=requester)
    candidates = [(root_page_id, root_blocks)]
    for block in root_blocks:
        if block.get("type") != "child_page":
            continue
        child_id = block.get("id")
        if isinstance(child_id, str) and child_id:
            candidates.append(
                (
                    child_id,
                    fetch_child_blocks(token, child_id, requester=requester),
                )
            )

    matches: list[tuple[str, list[dict[str, object]]]] = []
    for candidate in candidates:
        texts = [_block_text(block) for block in candidate[1]]
        if texts.count(START) == 1 and texts.count(END) == 1:
            start_index = texts.index(START)
            end_index = texts.index(END)
            if start_index <= end_index:
                matches.append(candidate)
    if len(matches) != 1:
        raise RuntimeError("expected exactly one page with a complete generated marker range")
    return matches[0]


def _text_block(block_type: str, content: str) -> dict[str, object]:
    rich_text: dict[str, object] = {
        "type": "text",
        "text": {"content": content},
    }
    if content in {NEW_START, NEW_END}:
        rich_text["annotations"] = {"color": "gray"}
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": [rich_text]},
    }


def build_replacement_blocks(interviews_database_id: str) -> list[dict[str, object]]:
    return [
        _text_block("paragraph", NEW_START),
        _text_block("heading_1", "面试复盘"),
        _text_block(
            "paragraph", "投递记录已迁移到 WPS 云文档；这里仅保留面试复盘。"
        ),
        {
            "object": "block",
            "type": "link_to_page",
            "link_to_page": {"database_id": interviews_database_id},
        },
        _text_block("paragraph", NEW_END),
    ]


def _patch_json(
    token: str,
    url: str,
    payload: dict[str, object],
    *,
    requester: Callable[[Request], Any] | None = None,
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    return _request_json(token, request, requester=requester)


def _ensure_replacement_absent(blocks: list[dict[str, object]]) -> None:
    if any(_block_text(block) in {NEW_START, NEW_END} for block in blocks):
        raise RuntimeError("interview overview replacement already exists")


def apply_cleanup(
    token: str,
    page_id: str,
    interviews_database_id: str,
    blocks: list[dict[str, object]],
    *,
    requester: Callable[[Request], Any] | None = None,
) -> int:
    _ensure_replacement_absent(blocks)
    block_ids = select_generated_block_ids(blocks)
    for block_id in block_ids:
        _patch_json(
            token,
            f"https://api.notion.com/v1/blocks/{block_id}",
            {"archived": True},
            requester=requester,
        )

    _patch_json(
        token,
        f"https://api.notion.com/v1/pages/{page_id}",
        {
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": "面试复盘"},
                        }
                    ]
                }
            }
        },
        requester=requester,
    )
    _patch_json(
        token,
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        {"children": build_replacement_blocks(interviews_database_id)},
        requester=requester,
    )
    return len(block_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simplify the private Notion overview")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    token = read_setting("NOTION_TOKEN")
    try:
        page_id = read_setting("JOB_HUNT_OVERVIEW_PAGE_ID")
        blocks = fetch_child_blocks(token, page_id)
    except RuntimeError:
        applications_database_id = read_setting("NOTION_APPLICATIONS_DB_ID")
        root_page_id = fetch_database_parent_page_id(token, applications_database_id)
        page_id, blocks = discover_marker_page(token, root_page_id)
    interviews_database_id = read_setting("NOTION_INTERVIEWS_DB_ID")
    _ensure_replacement_absent(blocks)
    block_ids = select_generated_block_ids(blocks)
    selected = [block for block in blocks if block.get("id") in set(block_ids)]
    counts = Counter(str(block.get("type", "unknown")) for block in selected)
    detail = ", ".join(f"{name}={counts[name]}" for name in sorted(counts))

    if args.dry_run:
        print(f"dry-run: would archive {len(block_ids)} blocks ({detail})")
        return 0

    changed = apply_cleanup(
        token,
        page_id,
        interviews_database_id,
        blocks,
    )
    print(f"applied: archived {changed} generated blocks and added interview overview")
    return 0


def _block_text(block: dict[str, object]) -> str:
    block_type = block.get("type")
    value = block.get(block_type) if isinstance(block_type, str) else None
    if not isinstance(value, dict):
        return ""
    rich_text = value.get("rich_text")
    if not isinstance(rich_text, list):
        return ""
    return "".join(
        str(item.get("plain_text", ""))
        for item in rich_text
        if isinstance(item, dict)
    )


def select_generated_block_ids(blocks: list[dict[str, object]]) -> list[str]:
    starts = [index for index, block in enumerate(blocks) if _block_text(block) == START]
    ends = [index for index, block in enumerate(blocks) if _block_text(block) == END]
    if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
        raise RuntimeError("expected exactly one complete generated marker range")

    selected = blocks[starts[0] : ends[0] + 1]
    ids = [block.get("id") for block in selected]
    if not all(isinstance(block_id, str) and block_id for block_id in ids):
        raise RuntimeError("generated marker range contains a block without an ID")
    return [str(block_id) for block_id in ids]


if __name__ == "__main__":
    raise SystemExit(main())
