from datetime import date, timedelta

from job_hunt_agent.domain.statuses import EventType
from job_hunt_agent.repositories import JobHuntRepository


class ReportingService:
    def __init__(self, repository: JobHuntRepository) -> None:
        self.repository = repository

    def list_follow_ups(self, today: date, days: int = 7) -> list[dict[str, str]]:
        end = today + timedelta(days=days)
        items: list[dict[str, str]] = []
        for record in self.repository.applications.values():
            if record.archived:
                continue
            if record.deadline is not None and today <= record.deadline <= end:
                items.append(
                    {
                        "application_id": record.id,
                        "company": record.company,
                        "role": record.role,
                        "deadline": record.deadline.isoformat(),
                        "next_step": record.next_step or "",
                    }
                )
        return sorted(items, key=lambda item: item["deadline"])

    def generate_daily_review(self, day: date) -> str:
        created = 0
        stage_changes = 0
        for event in self.repository.activity_events:
            if event.occurred_at.date() != day:
                continue
            if event.event_type is EventType.APPLICATION_CREATED:
                created += 1
            if event.event_type is EventType.STAGE_UPDATED:
                stage_changes += 1
        return "\n".join(
            [
                f"Daily review for {day.isoformat()}",
                f"Applications created: {created}",
                f"Stage changes: {stage_changes}",
            ]
        )
