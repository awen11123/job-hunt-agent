from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from job_hunt_agent.interviews import (
    InterviewSyncService,
    LocalInterviewDraft,
    LocalInterviewRecord,
    NotionInterviewTarget,
)


NOW = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)


def draft() -> LocalInterviewDraft:
    return LocalInterviewDraft(
        application_id="app-1",
        company="示例科技",
        round_name="技术一面",
        scheduled_at=NOW,
        format="远程",
        result="待反馈",
        self_score=7,
        raw_notes="重点追问了 Agent 状态编排。\n\n还讨论了 RAG 评测。",
    )


class RecordingLocalStore:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.records: dict[str, LocalInterviewRecord] = {}

    def save(self, value: LocalInterviewDraft, operation_id: str) -> LocalInterviewRecord:
        self.events.append("saved")
        existing = next(
            (record for record in self.records.values() if record.operation_id == operation_id),
            None,
        )
        if existing is not None:
            return existing
        record = LocalInterviewRecord(
            **value.model_dump(mode="python"),
            id="interview-1",
            markdown_path=Path("C:/private/interview.md"),
            operation_id=operation_id,
            created_at=NOW,
            updated_at=NOW,
        )
        self.records[record.id] = record
        return record

    def get(self, interview_id: str) -> LocalInterviewRecord:
        return self.records[interview_id]

    def mark_sync(
        self,
        interview_id: str,
        status: str,
        notion_page_id: str | None = None,
    ) -> LocalInterviewRecord:
        self.events.append(f"marked:{status}")
        record = self.records[interview_id]
        updates: dict[str, object] = {"sync_status": status, "updated_at": NOW}
        if notion_page_id is not None:
            updates["notion_page_id"] = notion_page_id
        updated = record.model_copy(update=updates)
        self.records[interview_id] = updated
        return updated


class RecordingNotionTarget:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.events: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.failure = failure

    def upsert(self, record: LocalInterviewRecord, operation_id: str) -> str:
        self.events.append("created")
        self.calls.append((record.id, operation_id))
        if self.failure is not None:
            raise self.failure
        return record.notion_page_id or "notion-page-1"


def test_sync_writes_local_record_before_notion() -> None:
    local = RecordingLocalStore()
    notion = RecordingNotionTarget()
    service = InterviewSyncService(local, notion)

    result = service.save_and_sync(draft(), operation_id="interview-operation-1")

    assert local.events == ["saved", "marked:pending", "marked:synced"]
    assert notion.events == ["created"]
    assert result.sync_status == "synced"
    assert result.notion_page_id == "notion-page-1"


def test_notion_failure_keeps_retryable_local_record(caplog: pytest.LogCaptureFixture) -> None:
    private_failure = "private-notion-credential"
    local = RecordingLocalStore()
    service = InterviewSyncService(
        local,
        RecordingNotionTarget(failure=RuntimeError(private_failure)),
    )

    result = service.save_and_sync(draft(), operation_id="interview-operation-2")

    assert result.sync_status == "failed"
    assert local.get(result.id).raw_notes == draft().raw_notes
    assert private_failure not in caplog.text


def test_disabled_notion_keeps_record_local() -> None:
    local = RecordingLocalStore()
    service = InterviewSyncService(local, None)

    result = service.save_and_sync(draft(), operation_id="interview-operation-3")

    assert result.sync_status == "local"
    assert local.events == ["saved"]


def test_retry_is_idempotent_after_success() -> None:
    local = RecordingLocalStore()
    notion = RecordingNotionTarget()
    service = InterviewSyncService(local, notion)
    first = service.save_and_sync(draft(), operation_id="interview-operation-4")

    second = service.retry(first.id)

    assert second == first
    assert notion.calls == [(first.id, "interview-operation-4")]


def test_failed_sync_can_retry_the_same_local_record() -> None:
    local = RecordingLocalStore()
    notion = RecordingNotionTarget(failure=RuntimeError("temporary failure"))
    service = InterviewSyncService(local, notion)
    failed = service.save_and_sync(draft(), operation_id="interview-operation-5")
    notion.failure = None

    synced = service.retry(failed.id)

    assert synced.id == failed.id
    assert synced.raw_notes == failed.raw_notes
    assert synced.sync_status == "synced"
    assert notion.calls == [
        (failed.id, "interview-operation-5"),
        (failed.id, f"retry-{failed.id}"),
    ]


class RecordingNotionClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, object]]] = []
        self.updated: list[tuple[str, dict[str, object]]] = []
        self.appended: list[tuple[str, list[dict[str, object]]]] = []

    def create_page(self, database_id: str, properties: dict[str, object]) -> dict:
        self.created.append((database_id, properties))
        return {"id": "created-page"}

    def update_page(self, page_id: str, properties: dict[str, object]) -> dict:
        self.updated.append((page_id, properties))
        return {"id": page_id}

    def append_block_children(
        self,
        page_id: str,
        children: list[dict[str, object]],
    ) -> dict:
        self.appended.append((page_id, children))
        return {"results": children}


def local_record(*, notion_page_id: str | None = None) -> LocalInterviewRecord:
    return LocalInterviewRecord(
        **draft().model_dump(mode="python"),
        id="interview-1",
        markdown_path=Path("C:/private/interview.md"),
        sync_status="synced" if notion_page_id else "pending",
        notion_page_id=notion_page_id,
        operation_id="interview-operation",
        created_at=NOW,
        updated_at=NOW,
    )


def heading_text(block: dict[str, object]) -> str:
    block_type = str(block["type"])
    body = block[block_type]
    assert isinstance(body, dict)
    rich_text = body["rich_text"]
    assert isinstance(rich_text, list)
    return rich_text[0]["text"]["content"]


def test_notion_target_creates_five_property_page_and_standard_body() -> None:
    client = RecordingNotionClient()
    target = NotionInterviewTarget(client, "interviews-database")

    page_id = target.upsert(local_record(), "interview-operation")

    assert page_id == "created-page"
    database_id, properties = client.created[0]
    assert database_id == "interviews-database"
    assert set(properties) == {"面试", "时间", "结果", "面试轮次", "分析状态"}
    appended_page, blocks = client.appended[0]
    assert appended_page == "created-page"
    assert [heading_text(block) for block in blocks if block["type"] == "heading_2"] == [
        "基本信息",
        "面试主线与整体评价",
        "核心问题复盘",
        "项目与回答亮点",
        "主要短板",
        "改进与准备建议",
        "后续动作",
    ]
    assert draft().raw_notes.split("\n\n") == [
        heading_text(block) for block in blocks if block["type"] == "paragraph"
    ]


def test_notion_target_updates_existing_page_without_duplicate_body() -> None:
    client = RecordingNotionClient()
    target = NotionInterviewTarget(client, "interviews-database")

    page_id = target.upsert(
        local_record(notion_page_id="existing-page"),
        "interview-operation",
    )

    assert page_id == "existing-page"
    assert client.created == []
    assert client.updated[0][0] == "existing-page"
    assert client.appended == []
