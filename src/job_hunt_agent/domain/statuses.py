from enum import StrEnum


class RecruitingStage(StrEnum):
    TO_APPLY = "to_apply"
    APPLIED = "applied"
    WRITTEN_TEST = "written_test"
    INTERVIEW = "interview"
    INTENTION = "intention"
    OFFER = "offer"


class FinalOutcome(StrEnum):
    ONGOING = "ongoing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventType(StrEnum):
    APPLICATION_CREATED = "application_created"
    STAGE_UPDATED = "stage_updated"
    INTERVIEW_RECORDED = "interview_recorded"
    INTERVIEW_ANALYZED = "interview_analyzed"


class SyncStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class InterviewAnalysisStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
