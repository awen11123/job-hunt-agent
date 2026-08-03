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

        self.repository.get_application(draft.application_id)
        now = datetime.now(timezone.utc)
        interview = InterviewRecord(
            **draft.model_dump(),
            id=self.repository.next_id("int"),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_interview(interview)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=draft.application_id,
            operation_id=operation_id,
            event_type=EventType.INTERVIEW_RECORDED,
            occurred_at=now,
            note=interview.id,
            sync_status=SyncStatus.COMPLETED,
        )
        self.repository.save_activity_event(event)
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

        interview = self.repository.get_interview(interview_id)
        analysis = self.analyzer.analyze(interview.raw_notes)
        now = datetime.now(timezone.utc)
        updated = interview.model_copy(
            update={
                "structured_analysis": analysis,
                "model_version": self.analyzer.model_version,
                "prompt_version": self.analyzer.prompt_version,
                "analysis_status": InterviewAnalysisStatus.COMPLETED,
                "updated_at": now,
            }
        )
        self.repository.save_interview(updated)
        for candidate in analysis.review_tasks:
            task = ReviewTaskRecord(
                **candidate.model_dump(),
                id=self.repository.next_id("rev"),
                source_interview_ids=[interview.id],
                created_at=now,
                updated_at=now,
            )
            self.repository.save_review_task(task)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=interview.application_id,
            operation_id=operation_id,
            event_type=EventType.INTERVIEW_ANALYZED,
            occurred_at=now,
            note=interview.id,
            sync_status=SyncStatus.COMPLETED,
        )
        self.repository.save_activity_event(event)
        return ToolReceipt(
            status="updated",
            message="Interview analysis saved with pending review tasks.",
            record_id=interview.id,
            operation_id=operation_id,
        )
