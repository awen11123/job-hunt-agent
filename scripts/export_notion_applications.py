from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def _windows_user_environment(name: str) -> str:
    if os.name != "nt":
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return ""
    return value if isinstance(value, str) else ""


def read_setting(
    name: str, *, registry_reader: Callable[[str], str] | None = None
) -> str:
    value = os.getenv(name)
    if value:
        return value
    value = (registry_reader or _windows_user_environment)(name)
    if value:
        return value
    raise RuntimeError(f"missing required setting: {name}")


def _property(page: dict[str, object], name: str) -> dict[str, Any]:
    properties = page.get("properties")
    if not isinstance(properties, dict):
        return {}
    value = properties.get(name)
    return value if isinstance(value, dict) else {}


def _plain_text(items: object) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(
        str(item.get("plain_text", ""))
        for item in items
        if isinstance(item, dict)
    )


def _title(page: dict[str, object], name: str) -> str:
    return _plain_text(_property(page, name).get("title"))


def _rich_text(page: dict[str, object], name: str) -> str:
    return _plain_text(_property(page, name).get("rich_text"))


def _date(page: dict[str, object], name: str) -> str:
    value = _property(page, name).get("date")
    return str(value.get("start", "")) if isinstance(value, dict) else ""


def _select(page: dict[str, object], name: str) -> str:
    value = _property(page, name).get("select")
    return str(value.get("name", "")) if isinstance(value, dict) else ""


def _url(page: dict[str, object], name: str) -> str:
    value = _property(page, name).get("url")
    return value if isinstance(value, str) else ""


def query_database(
    token: str,
    database_id: str,
    *,
    requester: Callable[[Request], Any] | None = None,
) -> list[dict[str, object]]:
    requester = requester or (lambda request: urlopen(request, timeout=30))
    pages: list[dict[str, object]] = []
    cursor: str | None = None

    while True:
        body: dict[str, object] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        request = Request(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with requester(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Notion response results must be a list")
        pages.extend(page for page in results if isinstance(page, dict))
        if not payload.get("has_more"):
            return pages
        next_cursor = payload.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise ValueError("Notion pagination response is missing next_cursor")
        cursor = next_cursor


def normalize_application(page: dict[str, object]) -> dict[str, str]:
    priority = _select(page, "优先级")
    return {
        "company": _title(page, "公司"),
        "role": _rich_text(page, "岗位"),
        "applied_date": _date(page, "投递日期"),
        "location": _rich_text(page, "地点"),
        "status": _select(page, "当前阶段"),
        "next_step": _rich_text(page, "下一步"),
        "next_time": _date(page, "截止日期"),
        "link": _url(page, "JD 链接"),
        "notes": f"{priority}优先级" if priority else "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export private Notion applications")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    token = read_setting("NOTION_TOKEN")
    database_id = read_setting("NOTION_APPLICATIONS_DB_ID")
    records = [
        normalize_application(page) for page in query_database(token, database_id)
    ]

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    print(f"{output} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
