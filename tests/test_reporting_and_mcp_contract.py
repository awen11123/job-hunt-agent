from datetime import date

from job_hunt_agent.domain.models import ApplicationDraft
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.mcp_server import TOOL_NAMES
from job_hunt_agent.repositories import InMemoryJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.reporting import ReportingService


def test_list_follow_ups_includes_deadlines_and_next_steps() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    app_service.record_application(
        ApplicationDraft(
            company="Moonshot AI",
            role="AI Agent Engineer",
            deadline=date(2026, 8, 10),
            next_step="Submit referral resume.",
        ),
        operation_id="op-create",
    )
    reporting = ReportingService(repo)

    follow_ups = reporting.list_follow_ups(today=date(2026, 8, 3), days=10)

    assert follow_ups[0]["company"] == "Moonshot AI"
    assert follow_ups[0]["next_step"] == "Submit referral resume."


def test_generate_daily_review_counts_applications_and_stage_changes() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    created = app_service.record_application(
        ApplicationDraft(company="Zhipu AI", role="LLM Application Engineer"),
        operation_id="op-create",
    )
    assert created.record_id is not None
    app_service.update_application_stage(
        created.record_id,
        RecruitingStage.INTERVIEW,
        operation_id="op-stage",
        note="Written test passed.",
    )
    reporting = ReportingService(repo)

    review = reporting.generate_daily_review(day=date.today())

    assert "Applications created: 1" in review
    assert "Stage changes: 1" in review


def test_mcp_tool_names_match_design() -> None:
    assert TOOL_NAMES == [
        "record_application",
        "update_application_stage",
        "record_interview",
        "analyze_interview",
        "list_follow_ups",
        "generate_review",
    ]
