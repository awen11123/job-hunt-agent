from datetime import datetime, timezone

from job_hunt_agent.domain.models import ActivityEvent, ApplicationDraft, ApplicationRecord, ToolReceipt
from job_hunt_agent.domain.statuses import EventType, RecruitingStage, SyncStatus
from job_hunt_agent.repositories import JobHuntRepository


class ApplicationService:
    def __init__(self, repository: JobHuntRepository, default_season: str | None = None) -> None:
        self.repository = repository
        self.default_season = default_season

    def record_application(self, draft: ApplicationDraft, operation_id: str) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=existing_event.application_id,
                operation_id=operation_id,
            )

        season = draft.season or self.default_season
        if season is None:
            return ToolReceipt(
                status="failed",
                message="Recruiting season is required.",
                operation_id=operation_id,
                pending_fields=["season"],
            )

        existing = self.repository.find_application_by_key(draft.company, draft.role, season)
        if existing is not None:
            return ToolReceipt(
                status="unchanged",
                message="Matching application already exists.",
                record_id=existing.id,
                operation_id=operation_id,
            )

        now = datetime.now(timezone.utc)
        pending_fields = [field for field in draft.missing_noncritical_fields() if field != "season"]
        record = ApplicationRecord(
            **draft.model_dump(exclude={"season"}),
            id=self.repository.next_id("app"),
            season=season,
            needs_supplement=bool(pending_fields),
            created_at=now,
            updated_at=now,
        )
        record = self.repository.save_application(record)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=record.id,
            operation_id=operation_id,
            event_type=EventType.APPLICATION_CREATED,
            occurred_at=now,
            to_stage=record.current_stage,
            sync_status=SyncStatus.COMPLETED,
        )
        event = self.repository.save_activity_event(event)
        return ToolReceipt(
            status="created",
            message=f"Created application for {record.company} - {record.role}.",
            record_id=record.id,
            operation_id=operation_id,
            pending_fields=pending_fields,
        )

    def update_application_stage(
        self,
        application_id: str,
        to_stage: RecruitingStage,
        operation_id: str,
        note: str | None = None,
    ) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=existing_event.application_id,
                operation_id=operation_id,
            )

        try:
            record = self.repository.get_application(application_id)
        except KeyError as exc:
            return ToolReceipt(
                status="failed",
                message="Application not found.",
                record_id=application_id,
                operation_id=operation_id,
                warnings=[type(exc).__name__],
            )
        now = datetime.now(timezone.utc)
        pending_event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=record.id,
            operation_id=operation_id,
            event_type=EventType.STAGE_UPDATED,
            occurred_at=now,
            from_stage=record.current_stage,
            to_stage=to_stage,
            note=note,
            sync_status=SyncStatus.PENDING,
        )
        pending_event = self.repository.save_activity_event(pending_event)
        record.current_stage = to_stage
        record.updated_at = now
        record = self.repository.save_application(record)
        completed_event = pending_event.model_copy(update={"sync_status": SyncStatus.COMPLETED})
        completed_event = self.repository.save_activity_event(completed_event)
        return ToolReceipt(
            status="updated",
            message=f"Updated application stage to {to_stage.value}.",
            record_id=record.id,
            operation_id=operation_id,
        )
