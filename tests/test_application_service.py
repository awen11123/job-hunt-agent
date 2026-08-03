from job_hunt_agent.domain.models import ApplicationDraft
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.repositories import InMemoryJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService


def test_record_application_creates_record_and_activity_event() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")

    receipt = service.record_application(
        ApplicationDraft(company="DeepSeek", role="LLM Application Engineer"),
        operation_id="op-create-1",
    )

    assert receipt.status == "created"
    assert receipt.pending_fields == [
        "direction",
        "location",
        "channel",
        "resume_version",
        "applied_date",
    ]
    assert repo.get_application(receipt.record_id).season == "2026-autumn"
    assert repo.activity_events[0].operation_id == "op-create-1"
    assert repo.activity_events[0].sync_status == "completed"


def test_record_application_is_idempotent_by_operation_id() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")
    draft = ApplicationDraft(company="DeepSeek", role="LLM Application Engineer")

    first = service.record_application(draft, operation_id="op-create-1")
    second = service.record_application(draft, operation_id="op-create-1")

    assert second.status == "unchanged"
    assert second.record_id == first.record_id
    assert len(repo.applications) == 1
    assert len(repo.activity_events) == 1


def test_record_application_deduplicates_company_role_and_season() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")

    service.record_application(
        ApplicationDraft(company=" DeepSeek ", role="LLM Application Engineer"),
        operation_id="op-create-1",
    )
    receipt = service.record_application(
        ApplicationDraft(company="deepseek", role="LLM   Application Engineer"),
        operation_id="op-create-2",
    )

    assert receipt.status == "unchanged"
    assert len(repo.applications) == 1


def test_update_application_stage_writes_pending_then_completed_event() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")
    created = service.record_application(
        ApplicationDraft(company="MiniMax", role="AI Agent Engineer"),
        operation_id="op-create-1",
    )

    receipt = service.update_application_stage(
        application_id=created.record_id,
        to_stage=RecruitingStage.INTERVIEW,
        operation_id="op-stage-1",
        note="Passed written test.",
    )

    assert receipt.status == "updated"
    assert repo.get_application(created.record_id).current_stage is RecruitingStage.INTERVIEW
    assert repo.activity_events[-1].sync_status == "completed"
