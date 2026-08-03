from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from job_hunt_agent.domain.statuses import (
    EventType,
    FinalOutcome,
    InterviewAnalysisStatus,
    Priority,
    RecruitingStage,
    SyncStatus,
)


class ApplicationDraft(BaseModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    season: str | None = None
    direction: str | None = None
    location: str | None = None
    channel: str | None = None
    jd_url: HttpUrl | None = None
    resume_version: str | None = None
    applied_date: date | None = None
    current_stage: RecruitingStage = RecruitingStage.APPLIED
    priority: Priority = Priority.MEDIUM
    deadline: date | None = None
    next_step: str | None = None

    def missing_noncritical_fields(self) -> list[str]:
        fields = ["season", "direction", "location", "channel", "resume_version", "applied_date"]
        return [name for name in fields if getattr(self, name) is None]


class ApplicationRecord(ApplicationDraft):
    id: str
    season: str
    final_outcome: FinalOutcome = FinalOutcome.ONGOING
    end_reason: str | None = None
    needs_supplement: bool = False
    archived: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(validate_assignment=True)


class ActivityEvent(BaseModel):
    id: str
    application_id: str
    operation_id: str
    event_type: EventType
    occurred_at: datetime
    from_stage: RecruitingStage | None = None
    to_stage: RecruitingStage | None = None
    note: str | None = None
    sync_status: SyncStatus = SyncStatus.PENDING


class InterviewDraft(BaseModel):
    application_id: str
    round_name: str = Field(min_length=1)
    scheduled_at: datetime | None = None
    format: str | None = None
    result: str | None = None
    raw_notes: str = Field(min_length=1)
    self_score: int | None = Field(default=None, ge=1, le=10)


class ReviewTaskCandidate(BaseModel):
    category: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    action: str = Field(min_length=10)
    mastery: str | None = None
    due_date: date | None = None
    occurrences: int = Field(default=1, ge=1)
    confirmation_status: Literal["pending", "confirmed", "dismissed"] = "pending"


class InterviewAnalysis(BaseModel):
    overview: str
    technical_questions: list[str] = Field(default_factory=list)
    project_questions: list[str] = Field(default_factory=list)
    behavioral_questions: list[str] = Field(default_factory=list)
    reverse_questions: list[str] = Field(default_factory=list)
    answer_summary: str | None = None
    answer_summary_source_present: bool = False
    evidence_based_performance: list[str] = Field(default_factory=list)
    better_answer_ideas: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    review_tasks: list[ReviewTaskCandidate] = Field(default_factory=list)
    inference_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def answer_summary_must_have_source(self) -> "InterviewAnalysis":
        if self.answer_summary and not self.answer_summary_source_present:
            raise ValueError("answer_summary requires answer_summary_source_present=true")
        return self


class InterviewRecord(InterviewDraft):
    id: str
    structured_analysis: InterviewAnalysis | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    analysis_status: InterviewAnalysisStatus = InterviewAnalysisStatus.PENDING
    created_at: datetime
    updated_at: datetime


class ReviewTaskRecord(ReviewTaskCandidate):
    id: str
    source_interview_ids: list[str] = Field(default_factory=list)
    completed: bool = False
    created_at: datetime
    updated_at: datetime


class ToolReceipt(BaseModel):
    status: Literal["created", "updated", "unchanged", "needs_disambiguation", "partial", "failed"]
    message: str
    record_id: str | None = None
    operation_id: str | None = None
    pending_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
