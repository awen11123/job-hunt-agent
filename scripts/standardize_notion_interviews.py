from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen

from scripts.export_notion_applications import query_database, read_setting
from scripts.notion_interview_template import (
    STANDARD_SECTIONS,
    ReviewValidation,
    block_text,
    standardize_detailed_child_review,
    standardize_structured_review,
    validate_standard_review,
)
from scripts.simplify_notion_overview import (
    fetch_child_blocks,
    fetch_database_parent_page_id,
)


class NotionApi(Protocol):
    database_id: str

    def query_database(self, database_id: str) -> list[dict[str, object]]: ...

    def database_parent_page_id(self, database_id: str) -> str: ...

    def child_blocks(self, block_id: str) -> list[dict[str, object]]: ...

    def append_children(
        self, block_id: str, children: list[dict[str, object]]
    ) -> list[dict[str, object]]: ...

    def archive_block(self, block_id: str) -> None: ...

    def archive_page(self, page_id: str) -> None: ...


@dataclass(frozen=True)
class MigrationReport:
    planned_reviews: int
    created_reviews: int
    legacy_blocks: int
    archived_legacy_blocks: int
    archived_standalone_pages: int


@dataclass(frozen=True)
class _StandaloneReview:
    page_id: str
    blocks: list[dict[str, object]]


def _require_id(value: dict[str, object], kind: str) -> str:
    item_id = value.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise RuntimeError(f"{kind} is missing an ID")
    return item_id


def _properties(page: dict[str, object]) -> dict[str, object]:
    value = page.get("properties")
    return value if isinstance(value, dict) else {}


def _child_page_title(block: dict[str, object]) -> str:
    child = block.get("child_page")
    if block.get("type") != "child_page" or not isinstance(child, dict):
        return ""
    title = child.get("title")
    return title if isinstance(title, str) else ""


def _standard_suffix_index(blocks: list[dict[str, object]]) -> int | None:
    heading_positions = [
        index
        for index, block in enumerate(blocks)
        if block.get("type") == "heading_2"
    ]
    if len(heading_positions) < len(STANDARD_SECTIONS):
        return None
    positions = heading_positions[-len(STANDARD_SECTIONS) :]
    names = tuple(block_text(blocks[index]) for index in positions)
    if names != STANDARD_SECTIONS:
        return None
    start = positions[0]
    try:
        validate_standard_review(blocks[start:])
    except ValueError:
        return None
    return start


def _is_structured_legacy(blocks: list[dict[str, object]]) -> bool:
    try:
        standardize_structured_review(blocks, {})
    except (ValueError, TypeError):
        return False
    return True


def _is_detailed_legacy(blocks: list[dict[str, object]]) -> bool:
    try:
        standardize_detailed_child_review(blocks, {})
    except (ValueError, TypeError):
        return False
    return True


def _discover_standalone_review(
    api: NotionApi, database_id: str
) -> _StandaloneReview | None:
    parent_id = api.database_parent_page_id(database_id)
    containers = [
        block
        for block in api.child_blocks(parent_id)
        if _child_page_title(block) == "面试复盘"
    ]
    if len(containers) != 1:
        raise RuntimeError("expected exactly one interview review container")

    container_id = _require_id(containers[0], "interview review container")
    matches: list[_StandaloneReview] = []
    for child in api.child_blocks(container_id):
        if child.get("type") != "child_page":
            continue
        page_id = _require_id(child, "standalone interview review page")
        blocks = api.child_blocks(page_id)
        if blocks and _is_detailed_legacy(blocks):
            matches.append(_StandaloneReview(page_id, blocks))
    if len(matches) > 1:
        raise RuntimeError("expected at most one standalone legacy interview review")
    return matches[0] if matches else None


def _preservation_check(
    source_blocks: list[dict[str, object]],
    standardized_blocks: list[dict[str, object]],
    *,
    kind: str,
) -> ReviewValidation:
    report = validate_standard_review(standardized_blocks)
    if kind == "structured":
        def question_labels(
            blocks: list[dict[str, object]],
        ) -> Counter[str]:
            labels: Counter[str] = Counter()
            for block in blocks:
                match = re.match(
                    r"^(Q\d+)(?!\d)", block_text(block).strip(), re.IGNORECASE
                )
                if match:
                    labels[match.group(1).upper()] += 1
            return labels

        if question_labels(source_blocks) != question_labels(standardized_blocks):
            raise RuntimeError("structured review question labels were not preserved")
    elif kind == "detailed":
        source_code = sum(block.get("type") == "code" for block in source_blocks)
        source_actions = sum(block.get("type") == "to_do" for block in source_blocks)
        if report.code_count != source_code or report.action_count != source_actions:
            raise RuntimeError("detailed review code or action count was not preserved")
    else:
        raise ValueError(f"unknown review kind: {kind}")
    return report


def _validate_appended(
    created: list[dict[str, object]], expected: ReviewValidation
) -> None:
    actual = validate_standard_review(created)
    if actual != expected:
        raise RuntimeError("Notion append response failed preservation validation")


def migrate_reviews(
    api: NotionApi,
    *,
    apply: bool,
    database_id: str | None = None,
) -> MigrationReport:
    database_id = database_id or api.database_id
    pages = api.query_database(database_id)
    if len(pages) != 2:
        raise RuntimeError("expected exactly two interview database pages")

    page_blocks = {
        _require_id(page, "interview database page"): api.child_blocks(
            _require_id(page, "interview database page")
        )
        for page in pages
    }
    page_by_id = {_require_id(page, "interview database page"): page for page in pages}
    standard_ids = {
        page_id
        for page_id, blocks in page_blocks.items()
        if _standard_suffix_index(blocks) is not None
    }
    standalone = _discover_standalone_review(api, database_id)

    if len(standard_ids) == 2 and standalone is None:
        raise RuntimeError("interview reviews are already standardized")

    structured_candidates = [
        page_id
        for page_id, blocks in page_blocks.items()
        if _is_structured_legacy(blocks)
    ]
    empty_ids = [page_id for page_id, blocks in page_blocks.items() if not blocks]

    structured_id: str | None = None
    detailed_id: str | None = None
    if len(standard_ids) == 0:
        if len(structured_candidates) != 1 or len(empty_ids) != 1:
            raise RuntimeError("could not classify the two legacy interview reviews")
        structured_id = structured_candidates[0]
        detailed_id = empty_ids[0]
    elif len(standard_ids) == 1:
        remaining = set(page_blocks) - standard_ids
        if len(remaining) != 1:
            raise RuntimeError("could not classify the partial interview migration")
        candidate = remaining.pop()
        if not _is_structured_legacy(page_blocks[candidate]):
            raise RuntimeError("could not classify the remaining legacy interview review")
        structured_id = candidate
        detailed_id = next(iter(standard_ids))
    elif len(standard_ids) == 2:
        pass
    else:
        raise RuntimeError("could not classify interview review state")

    if len(standard_ids) < 2 and standalone is None:
        raise RuntimeError("standalone legacy interview review is missing")

    legacy_blocks = sum(
        len(blocks)
        for page_id, blocks in page_blocks.items()
        if page_id not in standard_ids
    )
    if standalone is not None:
        legacy_blocks += len(standalone.blocks)

    detailed_standard: list[dict[str, object]] | None = None
    detailed_validation: ReviewValidation | None = None
    if detailed_id is not None and detailed_id not in standard_ids:
        if standalone is None:
            raise RuntimeError("standalone legacy interview review is missing")
        detailed_standard = standardize_detailed_child_review(
            standalone.blocks, _properties(page_by_id[detailed_id])
        )
        detailed_validation = _preservation_check(
            standalone.blocks, detailed_standard, kind="detailed"
        )

    structured_standard: list[dict[str, object]] | None = None
    structured_validation: ReviewValidation | None = None
    if structured_id is not None and structured_id not in standard_ids:
        structured_standard = standardize_structured_review(
            page_blocks[structured_id], _properties(page_by_id[structured_id])
        )
        structured_validation = _preservation_check(
            page_blocks[structured_id], structured_standard, kind="structured"
        )

    if not apply:
        return MigrationReport(
            planned_reviews=2,
            created_reviews=0,
            legacy_blocks=legacy_blocks,
            archived_legacy_blocks=0,
            archived_standalone_pages=0,
        )

    created_reviews = 0
    if detailed_standard is not None and detailed_validation is not None:
        created = api.append_children(detailed_id, detailed_standard)
        _validate_appended(created, detailed_validation)
        created_reviews += 1
    if structured_standard is not None and structured_validation is not None:
        created = api.append_children(structured_id, structured_standard)
        _validate_appended(created, structured_validation)
        created_reviews += 1

    refreshed = {
        page_id: api.child_blocks(page_id)
        for page_id in page_blocks
    }
    suffixes: dict[str, int] = {}
    for page_id, blocks in refreshed.items():
        suffix = _standard_suffix_index(blocks)
        if suffix is None:
            raise RuntimeError("appended interview review could not be validated")
        suffixes[page_id] = suffix

    archived_blocks = 0
    for page_id, blocks in refreshed.items():
        for block in blocks[: suffixes[page_id]]:
            api.archive_block(_require_id(block, "legacy interview block"))
            archived_blocks += 1

    archived_pages = 0
    if standalone is not None:
        api.archive_page(standalone.page_id)
        archived_pages = 1

    for page_id in page_blocks:
        final_blocks = api.child_blocks(page_id)
        if _standard_suffix_index(final_blocks) != 0:
            raise RuntimeError("final interview review body failed validation")
        validate_standard_review(final_blocks)

    return MigrationReport(
        planned_reviews=2,
        created_reviews=created_reviews,
        legacy_blocks=legacy_blocks,
        archived_legacy_blocks=archived_blocks,
        archived_standalone_pages=archived_pages,
    )


class NotionHttpApi:
    def __init__(self, token: str, database_id: str) -> None:
        self.token = token
        self.database_id = database_id

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        request = Request(
            url,
            data=(json.dumps(body).encode("utf-8") if body is not None else None),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Notion returned a non-object response")
        return payload

    def query_database(self, database_id: str) -> list[dict[str, object]]:
        return query_database(self.token, database_id)

    def database_parent_page_id(self, database_id: str) -> str:
        return fetch_database_parent_page_id(self.token, database_id)

    def child_blocks(self, block_id: str) -> list[dict[str, object]]:
        return fetch_child_blocks(self.token, block_id)

    def append_children(
        self, block_id: str, children: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        created: list[dict[str, object]] = []
        for offset in range(0, len(children), 100):
            payload = self._request_json(
                f"https://api.notion.com/v1/blocks/{block_id}/children",
                method="PATCH",
                body={"children": children[offset : offset + 100]},
            )
            results = payload.get("results")
            if not isinstance(results, list):
                raise RuntimeError("Notion append response is missing results")
            created.extend(item for item in results if isinstance(item, dict))
        return created

    def archive_block(self, block_id: str) -> None:
        self._request_json(
            f"https://api.notion.com/v1/blocks/{block_id}",
            method="PATCH",
            body={"archived": True},
        )

    def archive_page(self, page_id: str) -> None:
        self._request_json(
            f"https://api.notion.com/v1/pages/{page_id}",
            method="PATCH",
            body={"archived": True},
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Standardize private Notion interview reviews"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    token = read_setting("NOTION_TOKEN")
    database_id = read_setting("NOTION_INTERVIEWS_DB_ID")
    report = migrate_reviews(
        NotionHttpApi(token, database_id),
        apply=args.apply,
        database_id=database_id,
    )
    if args.dry_run:
        print(
            "dry-run: "
            f"reviews={report.planned_reviews}, "
            f"standard_sections={len(STANDARD_SECTIONS)}, "
            f"legacy_blocks={report.legacy_blocks}, "
            f"standalone_pages={int(report.legacy_blocks > 0)}"
        )
    else:
        print(
            "applied: "
            f"reviews={report.planned_reviews}, "
            f"archived_legacy_blocks={report.archived_legacy_blocks}, "
            "archived_standalone_pages="
            f"{report.archived_standalone_pages}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
