from datetime import date
from uuid import uuid4

from job_hunt_agent.domain.models import ApplicationDraft, InterviewDraft
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.interviews import InterviewService
from job_hunt_agent.services.reporting import ReportingService


TOOL_NAMES = [
    "record_application",
    "update_application_stage",
    "record_interview",
    "analyze_interview",
    "list_follow_ups",
    "generate_review",
]


def new_operation_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def build_mcp_server(
    application_service: ApplicationService,
    interview_service: InterviewService,
    reporting_service: ReportingService,
):
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install the project dependencies to run the MCP server.") from exc

    mcp = FastMCP("job-hunt-agent")

    @mcp.tool
    def record_application(payload: dict) -> dict:
        draft = ApplicationDraft.model_validate(payload)
        receipt = application_service.record_application(draft, new_operation_id("record-application"))
        return receipt.model_dump(mode="json")

    @mcp.tool
    def update_application_stage(application_id: str, to_stage: str, note: str | None = None) -> dict:
        receipt = application_service.update_application_stage(
            application_id=application_id,
            to_stage=RecruitingStage(to_stage),
            operation_id=new_operation_id("update-stage"),
            note=note,
        )
        return receipt.model_dump(mode="json")

    @mcp.tool
    def record_interview(payload: dict) -> dict:
        draft = InterviewDraft.model_validate(payload)
        receipt = interview_service.record_interview(draft, new_operation_id("record-interview"))
        return receipt.model_dump(mode="json")

    @mcp.tool
    def analyze_interview(interview_id: str) -> dict:
        receipt = interview_service.analyze_interview(interview_id, new_operation_id("analyze-interview"))
        return receipt.model_dump(mode="json")

    @mcp.tool
    def list_follow_ups(days: int = 7) -> list[dict[str, str]]:
        return reporting_service.list_follow_ups(today=date.today(), days=days)

    @mcp.tool
    def generate_review(kind: str = "daily") -> str:
        if kind != "daily":
            return "Weekly review generation will use the same event data in the next milestone."
        return reporting_service.generate_daily_review(day=date.today())

    return mcp
