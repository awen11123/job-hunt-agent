from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from job_hunt_agent.domain.models import (
    ActivityEvent,
    ApplicationDraft,
    InterviewAnalysis,
    InterviewDraft,
    ReviewTaskRecord,
)
from job_hunt_agent.domain.statuses import EventType, RecruitingStage, SyncStatus
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


def test_daily_review_counts_utc_event_on_local_calendar_day() -> None:
    repo = InMemoryJobHuntRepository()
    repo.save_activity_event(
        ActivityEvent(
            id="evt_local_midnight",
            application_id="app_demo",
            operation_id="op_local_midnight",
            event_type=EventType.STAGE_UPDATED,
            occurred_at=datetime(2026, 9, 10, 16, 30, tzinfo=timezone.utc),
            sync_status=SyncStatus.COMPLETED,
        )
    )
    reporting = ReportingService(repo, report_timezone=ZoneInfo("Asia/Shanghai"))

    review = reporting.generate_daily_review(day=date(2026, 9, 11))

    assert "Stage changes: 1" in review


def test_daily_review_keeps_explicit_application_date_as_business_date() -> None:
    repo = InMemoryJobHuntRepository()
    ApplicationService(repo, default_season="2026-autumn").record_application(
        ApplicationDraft(
            company="Example AI",
            role="Agent Engineer",
            applied_date=date(2026, 9, 11),
        ),
        operation_id="op_business_date",
    )
    reporting = ReportingService(repo, report_timezone=ZoneInfo("America/Los_Angeles"))

    review = reporting.generate_daily_review(day=date(2026, 9, 11))

    assert "Applications created: 1" in review


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


def test_generate_text_overview_prioritizes_readable_current_state() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    app_service.record_application(
        ApplicationDraft(
            company="示例科技",
            role="智能 Agent 系统开发工程师",
            direction="AI Agent / LLM 应用",
            location="远程面试",
            channel="示例科技校招官网",
            resume_version="resume-v3.pdf",
            applied_date=date(2026, 8, 13),
            next_step="准备 Agent 架构、Planning、Memory 和 Tool Use。",
        ),
        operation_id="op-example-tech",
    )
    app_service.record_application(
        ApplicationDraft(
            company="示例旅行",
            role="AI全栈工程师（上海）",
            direction="AI Agent / LLM 应用 / AI 全栈",
            location="上海",
            channel="校招正式技术类",
            applied_date=date(2026, 8, 13),
            next_step="补充简历版本并准备低成本实验评测。",
        ),
        operation_id="op-example-travel",
    )
    reporting = ReportingService(repo)

    overview = reporting.generate_text_overview(today=date(2026, 8, 13))

    assert "# 秋招总览｜2026-08-13" in overview
    assert "## 当前投递" in overview
    assert "- 示例科技｜智能 Agent 系统开发工程师｜已投递｜中优先级｜准备 Agent 架构、Planning、Memory 和 Tool Use。" in overview
    assert "- 示例旅行｜AI全栈工程师（上海）｜已投递｜中优先级｜补充简历版本并准备低成本实验评测。" in overview
    assert "## 待补充" in overview
    assert "- 示例旅行｜AI全栈工程师（上海）：简历版本" in overview
    assert "## 最近流程" in overview
    assert "新增投递：示例旅行 - AI全栈工程师（上海）" in overview


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
