from datetime import date, datetime, timezone

from job_hunt_agent.domain.models import (
    ApplicationDraft,
    InterviewAnalysis,
    InterviewDraft,
    ReviewTaskRecord,
)
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.mcp_server import TOOL_NAMES, JobHuntToolHandlers
from job_hunt_agent.repositories import InMemoryJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.interviews import InterviewService
from job_hunt_agent.services.reporting import ReportingService


class NoopAnalyzer:
    model_version = "noop"
    prompt_version = "noop"

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        return InterviewAnalysis(overview=raw_notes)


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


def test_list_follow_ups_includes_interviews_and_review_tasks() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    created = app_service.record_application(
        ApplicationDraft(company="MiniMax", role="LLM 应用工程师"),
        operation_id="op-create-followup",
    )
    assert created.record_id is not None
    interview_service = InterviewService(repo, analyzer=NoopAnalyzer())
    interview_service.record_interview(
        InterviewDraft(
            application_id=created.record_id,
            round_name="一面",
            scheduled_at=datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc),
            raw_notes="还没面，先占位。",
        ),
        operation_id="op-interview-followup",
    )
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    repo.save_review_task(
        ReviewTaskRecord(
            id="rev_followup",
            category="LLM",
            topic="RAG 评估",
            action="整理 RAG 评估指标并写一版标准答案。",
            due_date=date(2026, 8, 6),
            created_at=now,
            updated_at=now,
        )
    )
    reporting = ReportingService(repo)

    follow_ups = reporting.list_follow_ups(today=date(2026, 8, 3), days=7)

    kinds = {item["kind"] for item in follow_ups}
    assert {"interview", "review_task"}.issubset(kinds)
    interview = next(item for item in follow_ups if item["kind"] == "interview")
    task = next(item for item in follow_ups if item["kind"] == "review_task")
    assert interview["title"] == "MiniMax - 一面"
    assert task["title"] == "RAG 评估"


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


def test_generate_weekly_review_summarizes_pipeline_and_review_tasks() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    created = app_service.record_application(
        ApplicationDraft(company="Zhipu AI", role="LLM Application Engineer"),
        operation_id="op-weekly-create",
    )
    assert created.record_id is not None
    app_service.update_application_stage(
        created.record_id,
        RecruitingStage.INTERVIEW,
        operation_id="op-weekly-stage",
        note="Written test passed.",
    )
    InterviewService(repo, analyzer=NoopAnalyzer()).record_interview(
        InterviewDraft(
            application_id=created.record_id,
            round_name="技术一面",
            raw_notes="面试官问了 RAG 评估。",
        ),
        operation_id="op-weekly-interview",
    )
    now = datetime.now(timezone.utc)
    repo.save_review_task(
        ReviewTaskRecord(
            id="rev_weekly",
            category="LLM",
            topic="RAG 评估",
            action="复盘 RAG 评估常用指标和线上排障思路。",
            created_at=now,
            updated_at=now,
        )
    )
    reporting = ReportingService(repo)

    review = reporting.generate_weekly_review(start_day=date.today())

    assert "Weekly review" in review
    assert "Applications created: 1" in review
    assert "Stage changes: 1" in review
    assert "Interviews recorded: 1" in review
    assert "Open review tasks: 1" in review


def test_mcp_tool_names_match_design() -> None:
    assert TOOL_NAMES == [
        "record_application",
        "record_application_text",
        "update_application_stage",
        "record_interview",
        "analyze_interview",
        "list_follow_ups",
        "generate_review",
    ]


def test_mcp_record_application_accepts_client_operation_id_for_retries() -> None:
    repo = InMemoryJobHuntRepository()
    handlers = JobHuntToolHandlers(
        application_service=ApplicationService(repo, default_season="2026-autumn"),
        interview_service=InterviewService(repo, analyzer=NoopAnalyzer()),
        reporting_service=ReportingService(repo),
    )
    payload = {"company": "DeepSeek", "role": "LLM Application Engineer"}

    first = handlers.record_application(payload, operation_id="client-op-1")
    second = handlers.record_application(payload, operation_id="client-op-1")

    assert first["status"] == "created"
    assert second["status"] == "unchanged"
    assert len(repo.applications) == 1
    assert len(repo.activity_events) == 1


def test_mcp_generate_review_supports_weekly_summary() -> None:
    repo = InMemoryJobHuntRepository()
    handlers = JobHuntToolHandlers(
        application_service=ApplicationService(repo, default_season="2026-autumn"),
        interview_service=InterviewService(repo, analyzer=NoopAnalyzer()),
        reporting_service=ReportingService(repo),
    )

    review = handlers.generate_review(kind="weekly")

    assert "Weekly review" in review
    assert "next milestone" not in review
