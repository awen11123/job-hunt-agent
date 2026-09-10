from __future__ import annotations

from typing import Protocol

from job_hunt_agent.interviews.local_store import (
    LocalInterviewDraft,
    LocalInterviewRecord,
    SyncStatus,
)


class LocalInterviewSyncStore(Protocol):
    def save(
        self,
        draft: LocalInterviewDraft,
        operation_id: str,
    ) -> LocalInterviewRecord: ...

    def get(self, interview_id: str) -> LocalInterviewRecord: ...

    def mark_sync(
        self,
        interview_id: str,
        status: SyncStatus,
        notion_page_id: str | None = None,
    ) -> LocalInterviewRecord: ...


class InterviewSyncTarget(Protocol):
    def upsert(self, record: LocalInterviewRecord, operation_id: str) -> str: ...


class InterviewSyncService:
    def __init__(
        self,
        local_store: LocalInterviewSyncStore,
        target: InterviewSyncTarget | None,
    ) -> None:
        self.local_store = local_store
        self.target = target

    def save_and_sync(
        self,
        draft: LocalInterviewDraft,
        operation_id: str,
    ) -> LocalInterviewRecord:
        local_record = self.local_store.save(draft, operation_id)
        return self._sync(local_record, operation_id)

    def retry(self, interview_id: str) -> LocalInterviewRecord:
        local_record = self.local_store.get(interview_id)
        if local_record.sync_status == "synced":
            return local_record
        return self._sync(local_record, f"retry-{interview_id}")

    def _sync(
        self,
        local_record: LocalInterviewRecord,
        operation_id: str,
    ) -> LocalInterviewRecord:
        if self.target is None or local_record.sync_status == "synced":
            return local_record

        pending = self.local_store.mark_sync(local_record.id, "pending")
        try:
            page_id = self.target.upsert(pending, operation_id)
        except Exception:
            return self.local_store.mark_sync(local_record.id, "failed")
        return self.local_store.mark_sync(local_record.id, "synced", page_id)

