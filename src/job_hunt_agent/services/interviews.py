from datetime import datetime, timezone

from job_hunt_agent.ai.deepseek import InterviewAnalyzer
from job_hunt_agent.domain.models import (
    ActivityEvent,
    InterviewDraft,
    InterviewRecord,
    ReviewTaskRecord,
    ToolReceipt,
)
from job_hunt_agent.domain.statuses import EventType, InterviewAnalysisStatus, SyncStatus
from job_hunt_agent.repositories import JobHuntRepository


class InterviewService:
    def __init__(self, repository: JobHuntRepository, analyzer: InterviewAnalyzer) -> None:
        self.repository = repository
        self.analyzer = analyzer

    def record_interview(self, draft: InterviewDraft, operation_id: str) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=existing_event.note,
                operation_id=operation_id,
            )

        try:
            self.repository.get_application(draft.application_id)
        except KeyError as exc:
            return ToolReceipt(
                status="failed",
                message="Application not found.",
                record_id=draft.application_id,
                operation_id=operation_id,
                warnings=[type(exc).__name__],
            )
        now = datetime.now(timezone.utc)
        interview = InterviewRecord(
            **draft.model_dump(),
            id=self.repository.next_id("int"),
            created_at=now,
            updated_at=now,
        )
        interview = self.repository.save_interview(interview)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=draft.application_id,
            operation_id=operation_id,
            event_type=EventType.INTERVIEW_RECORDED,
            occurred_at=now,
            note=interview.id,
            sync_status=SyncStatus.COMPLETED,
        )
        event = self.repository.save_activity_event(event)
        return ToolReceipt(
            status="created",
            message=f"Recorded interview round {interview.round_name}.",
            record_id=interview.id,
            operation_id=operation_id,
        )

    def analyze_interview(self, interview_id: str, operation_id: str) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=interview_id,
                operation_id=operation_id,
            )

        try:
            interview = self.repository.get_interview(interview_id)
        except KeyError as exc:
            return ToolReceipt(
                status="failed",
                message="Interview not found.",
                record_id=interview_id,
                operation_id=operation_id,
                warnings=[type(exc).__name__],
            )

        now = datetime.now(timezone.utc)
        try:
            analysis = self.analyzer.analyze(interview.raw_notes)
            self._validate_source_excerpts(analysis.source_excerpts, interview.raw_notes)
        except Exception as exc:
            failed = interview.model_copy(
                update={
                    "analysis_status": InterviewAnalysisStatus.FAILED,
                    "updated_at": now,
                }
            )
            failed = self.repository.save_interview(failed)
            event = ActivityEvent(
                id=self.repository.next_id("evt"),
                application_id=interview.application_id,
                operation_id=operation_id,
                event_type=EventType.INTERVIEW_ANALYZED,
                occurred_at=now,
                note=interview.id,
                sync_status=SyncStatus.FAILED,
            )
            event = self.repository.save_activity_event(event)
            return ToolReceipt(
                status="failed",
                message="Interview analysis failed.",
                record_id=interview.id,
                operation_id=operation_id,
                warnings=[type(exc).__name__],
            )

        updated = interview.model_copy(
            update={
                "structured_analysis": analysis,
                "model_version": self.analyzer.model_version,
                "prompt_version": self.analyzer.prompt_version,
                "analysis_status": InterviewAnalysisStatus.COMPLETED,
                "updated_at": now,
            }
        )
        updated = self.repository.save_interview(updated)
        for candidate in analysis.review_tasks:
            existing = self.repository.find_review_task_by_topic(candidate.category, candidate.topic)
            if existing is not None:
                source_ids = list(existing.source_interview_ids)
                if interview.id not in source_ids:
                    source_ids.append(interview.id)
                task = existing.model_copy(
                    update={
                        "occurrences": existing.occurrences + candidate.occurrences,
                        "source_interview_ids": source_ids,
                        "updated_at": now,
                    }
                )
                task = self.repository.save_review_task(task)
            else:
                task = ReviewTaskRecord(
                    **candidate.model_dump(),
                    id=self.repository.next_id("rev"),
                    source_interview_ids=[interview.id],
                    created_at=now,
                    updated_at=now,
                )
                task = self.repository.save_review_task(task)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=interview.application_id,
            operation_id=operation_id,
            event_type=EventType.INTERVIEW_ANALYZED,
            occurred_at=now,
            note=interview.id,
            sync_status=SyncStatus.COMPLETED,
        )
        event = self.repository.save_activity_event(event)
        return ToolReceipt(
            status="updated",
            message="Interview analysis saved with pending review tasks.",
            record_id=interview.id,
            operation_id=operation_id,
        )

    def _validate_source_excerpts(self, source_excerpts: list[str], raw_notes: str) -> None:
        missing = [excerpt for excerpt in source_excerpts if excerpt not in raw_notes]
        if missing:
            raise ValueError("source excerpt missing from raw notes")
