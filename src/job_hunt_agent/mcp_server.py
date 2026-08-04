from datetime import date, timedelta
from uuid import uuid4

from job_hunt_agent.domain.models import ApplicationDraft, InterviewDraft, ToolReceipt
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.nlu.application_text import parse_application_text
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.interviews import InterviewService
from job_hunt_agent.services.reporting import ReportingService


TOOL_NAMES = [
    "record_application",
    "record_application_text",
    "update_application_stage",
    "record_interview",
    "analyze_interview",
    "list_follow_ups",
    "generate_review",
]


def new_operation_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class JobHuntToolHandlers:
    def __init__(
        self,
        application_service: ApplicationService,
        interview_service: InterviewService,
        reporting_service: ReportingService,
        today_provider=date.today,
    ) -> None:
        self.application_service = application_service
        self.interview_service = interview_service
        self.reporting_service = reporting_service
        self.today_provider = today_provider

    def operation_id(self, provided: str | None, prefix: str) -> str:
        return provided or new_operation_id(prefix)

    def record_application(self, payload: dict, operation_id: str | None = None) -> dict:
        draft = ApplicationDraft.model_validate(payload)
        receipt = self.application_service.record_application(
            draft,
            self.operation_id(operation_id, "record-application"),
        )
        return receipt.model_dump(mode="json")

    def record_application_text(self, text: str, operation_id: str | None = None) -> dict:
        operation = self.operation_id(operation_id, "record-application-text")
        try:
            draft = parse_application_text(
                text,
                today=self.today_provider(),
                default_season=self.application_service.default_season,
            )
        except ValueError as exc:
            return ToolReceipt(
                status="failed",
                message="Could not parse application text.",
                operation_id=operation,
                pending_fields=["company", "role"],
                warnings=[str(exc)],
            ).model_dump(mode="json")
        receipt = self.application_service.record_application(draft, operation)
        return receipt.model_dump(mode="json")

    def update_application_stage(
        self,
        application_id: str,
        to_stage: str,
        operation_id: str | None = None,
        note: str | None = None,
    ) -> dict:
        receipt = self.application_service.update_application_stage(
            application_id=application_id,
            to_stage=RecruitingStage(to_stage),
            operation_id=self.operation_id(operation_id, "update-stage"),
            note=note,
        )
        return receipt.model_dump(mode="json")

    def record_interview(self, payload: dict, operation_id: str | None = None) -> dict:
        draft = InterviewDraft.model_validate(payload)
        receipt = self.interview_service.record_interview(
            draft,
            self.operation_id(operation_id, "record-interview"),
        )
        return receipt.model_dump(mode="json")

    def analyze_interview(self, interview_id: str, operation_id: str | None = None) -> dict:
        receipt = self.interview_service.analyze_interview(
            interview_id,
            self.operation_id(operation_id, "analyze-interview"),
        )
        return receipt.model_dump(mode="json")

    def list_follow_ups(self, days: int = 7) -> list[dict[str, str]]:
        return self.reporting_service.list_follow_ups(today=date.today(), days=days)

    def generate_review(self, kind: str = "daily") -> str:
        if kind == "weekly":
            return self.reporting_service.generate_weekly_review(
                start_day=date.today() - timedelta(days=6)
            )
        if kind != "daily":
            return "Unsupported review kind. Use daily or weekly."
        return self.reporting_service.generate_daily_review(day=date.today())


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
    handlers = JobHuntToolHandlers(application_service, interview_service, reporting_service)

    @mcp.tool
    def record_application(payload: dict, operation_id: str | None = None) -> dict:
        return handlers.record_application(payload, operation_id)

    @mcp.tool
    def record_application_text(text: str, operation_id: str | None = None) -> dict:
        return handlers.record_application_text(text, operation_id)

    @mcp.tool
    def update_application_stage(
        application_id: str,
        to_stage: str,
        operation_id: str | None = None,
        note: str | None = None,
    ) -> dict:
        return handlers.update_application_stage(application_id, to_stage, operation_id, note)

    @mcp.tool
    def record_interview(payload: dict, operation_id: str | None = None) -> dict:
        return handlers.record_interview(payload, operation_id)

    @mcp.tool
    def analyze_interview(interview_id: str, operation_id: str | None = None) -> dict:
        return handlers.analyze_interview(interview_id, operation_id)

    @mcp.tool
    def list_follow_ups(days: int = 7) -> list[dict[str, str]]:
        return handlers.list_follow_ups(days)

    @mcp.tool
    def generate_review(kind: str = "daily") -> str:
        return handlers.generate_review(kind)

    return mcp
