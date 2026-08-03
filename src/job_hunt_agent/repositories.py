from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from job_hunt_agent.domain.models import (
    ActivityEvent,
    ApplicationRecord,
    InterviewRecord,
    ReviewTaskRecord,
)
from job_hunt_agent.matching import application_key, normalize_text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobHuntRepository(Protocol):
    applications: dict[str, ApplicationRecord]
    activity_events: list[ActivityEvent]
    interviews: dict[str, InterviewRecord]
    review_tasks: dict[str, ReviewTaskRecord]

    def next_id(self, prefix: str) -> str:
        ...

    def save_application(self, record: ApplicationRecord) -> ApplicationRecord:
        ...

    def get_application(self, application_id: str | None) -> ApplicationRecord:
        ...

    def find_application_by_key(self, company: str, role: str, season: str) -> ApplicationRecord | None:
        ...

    def save_activity_event(self, event: ActivityEvent) -> ActivityEvent:
        ...

    def find_activity_by_operation_id(self, operation_id: str) -> ActivityEvent | None:
        ...

    def save_interview(self, record: InterviewRecord) -> InterviewRecord:
        ...

    def get_interview(self, interview_id: str) -> InterviewRecord:
        ...

    def save_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord:
        ...

    def find_review_task_by_topic(self, category: str, topic: str) -> ReviewTaskRecord | None:
        ...


class InMemoryJobHuntRepository:
    def __init__(self) -> None:
        self.applications: dict[str, ApplicationRecord] = {}
        self.activity_events: list[ActivityEvent] = []
        self.interviews: dict[str, InterviewRecord] = {}
        self.review_tasks: dict[str, ReviewTaskRecord] = {}

    def next_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    def save_application(self, record: ApplicationRecord) -> ApplicationRecord:
        self.applications[record.id] = record
        return record

    def get_application(self, application_id: str | None) -> ApplicationRecord:
        if application_id is None or application_id not in self.applications:
            raise KeyError(f"application not found: {application_id}")
        return self.applications[application_id]

    def find_application_by_key(self, company: str, role: str, season: str) -> ApplicationRecord | None:
        expected = application_key(company, role, season)
        for record in self.applications.values():
            if application_key(record.company, record.role, record.season) == expected:
                return record
        return None

    def save_activity_event(self, event: ActivityEvent) -> ActivityEvent:
        for index, existing in enumerate(self.activity_events):
            if existing.id == event.id:
                self.activity_events[index] = event
                return event
        self.activity_events.append(event)
        return event

    def find_activity_by_operation_id(self, operation_id: str) -> ActivityEvent | None:
        for event in self.activity_events:
            if event.operation_id == operation_id:
                return event
        return None

    def save_interview(self, record: InterviewRecord) -> InterviewRecord:
        self.interviews[record.id] = record
        return record

    def get_interview(self, interview_id: str) -> InterviewRecord:
        return self.interviews[interview_id]

    def save_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord:
        self.review_tasks[record.id] = record
        return record

    def find_review_task_by_topic(self, category: str, topic: str) -> ReviewTaskRecord | None:
        expected = (normalize_text(category), normalize_text(topic))
        for record in self.review_tasks.values():
            if (normalize_text(record.category), normalize_text(record.topic)) == expected:
                return record
        return None


class NotionJobHuntRepository:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Notion repository requires database setup before real writes are enabled")
