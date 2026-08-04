from datetime import date

from job_hunt_agent.domain.models import InterviewAnalysis
from job_hunt_agent.nlu.application_text import parse_application_text
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


def test_parse_application_text_extracts_common_chinese_fields() -> None:
    draft = parse_application_text(
        "今天投了 DeepSeek 的 LLM 应用工程师，内推，简历 v3，北京，AI Agent方向，截止8月10日",
        today=date(2026, 8, 4),
        default_season="2026-autumn",
    )

    assert draft.company == "DeepSeek"
    assert draft.role == "LLM 应用工程师"
    assert draft.season == "2026-autumn"
    assert draft.channel == "内推"
    assert draft.resume_version == "v3"
    assert draft.location == "北京"
    assert draft.direction == "AI Agent"
    assert draft.applied_date == date(2026, 8, 4)
    assert draft.deadline == date(2026, 8, 10)
    assert draft.current_stage is RecruitingStage.APPLIED


def test_parse_application_text_handles_todo_and_next_step() -> None:
    draft = parse_application_text(
        "待投 MiniMax AI Agent工程师，官网，上海，下一步：找校友内推",
        today=date(2026, 8, 4),
        default_season="2026-autumn",
    )

    assert draft.company == "MiniMax"
    assert draft.role == "AI Agent工程师"
    assert draft.current_stage is RecruitingStage.TO_APPLY
    assert draft.channel == "官网"
    assert draft.location == "上海"
    assert draft.next_step == "找校友内推"


def test_mcp_record_application_text_records_and_deduplicates_by_operation_id() -> None:
    repo = InMemoryJobHuntRepository()
    handlers = JobHuntToolHandlers(
        application_service=ApplicationService(repo, default_season="2026-autumn"),
        interview_service=InterviewService(repo, analyzer=NoopAnalyzer()),
        reporting_service=ReportingService(repo),
        today_provider=lambda: date(2026, 8, 4),
    )

    first = handlers.record_application_text(
        "今天投了 DeepSeek 的 LLM 应用工程师，内推，简历 v3",
        operation_id="text-op-1",
    )
    second = handlers.record_application_text(
        "今天投了 DeepSeek 的 LLM 应用工程师，内推，简历 v3",
        operation_id="text-op-1",
    )

    assert first["status"] == "created"
    assert second["status"] == "unchanged"
    assert len(repo.applications) == 1
    record = next(iter(repo.applications.values()))
    assert record.company == "DeepSeek"
    assert record.role == "LLM 应用工程师"
    assert record.resume_version == "v3"


def test_mcp_tool_names_include_natural_language_application_entry() -> None:
    assert "record_application_text" in TOOL_NAMES
