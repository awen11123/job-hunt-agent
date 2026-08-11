from datetime import date, timedelta

from job_hunt_agent.domain.statuses import EventType, SyncStatus
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
                        "kind": "application",
                        "title": f"{record.company} - {record.role}",
                        "date": record.deadline.isoformat(),
                        "company": record.company,
                        "role": record.role,
                        "deadline": record.deadline.isoformat(),
                        "next_step": record.next_step or "",
                    }
                )
        for interview in self.repository.interviews.values():
            if interview.scheduled_at is None:
                continue
            scheduled_day = interview.scheduled_at.date()
            if today <= scheduled_day <= end:
                application = self.repository.get_application(interview.application_id)
                items.append(
                    {
                        "kind": "interview",
                        "title": f"{application.company} - {interview.round_name}",
                        "date": scheduled_day.isoformat(),
                        "application_id": interview.application_id,
                        "interview_id": interview.id,
                        "company": application.company,
                        "role": application.role,
                    }
                )
        for task in self.repository.review_tasks.values():
            if task.completed or task.due_date is None:
                continue
            if today <= task.due_date <= end:
                items.append(
                    {
                        "kind": "review_task",
                        "title": task.topic,
                        "date": task.due_date.isoformat(),
                        "review_task_id": task.id,
                        "category": task.category,
                        "action": task.action,
                    }
                )
        return sorted(items, key=lambda item: item["date"])

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

    def generate_weekly_review(self, start_day: date, days: int = 7) -> str:
        end_day = start_day + timedelta(days=days - 1)
        created = 0
        stage_changes = 0
        interviews_recorded = 0
        analyses_completed = 0
        analyses_failed = 0
        for event in self.repository.activity_events:
            if not start_day <= event.occurred_at.date() <= end_day:
                continue
            if event.event_type is EventType.APPLICATION_CREATED:
                created += 1
            if event.event_type is EventType.STAGE_UPDATED:
                stage_changes += 1
            if event.event_type is EventType.INTERVIEW_RECORDED:
                interviews_recorded += 1
            if event.event_type is EventType.INTERVIEW_ANALYZED:
                if event.sync_status is SyncStatus.COMPLETED:
                    analyses_completed += 1
                if event.sync_status is SyncStatus.FAILED:
                    analyses_failed += 1
        open_review_tasks = sum(1 for task in self.repository.review_tasks.values() if not task.completed)
        upcoming_follow_ups = len(self.list_follow_ups(today=end_day + timedelta(days=1), days=7))
        return "\n".join(
            [
                f"Weekly review for {start_day.isoformat()} to {end_day.isoformat()}",
                f"Applications created: {created}",
                f"Stage changes: {stage_changes}",
                f"Interviews recorded: {interviews_recorded}",
                f"Analyses completed: {analyses_completed}",
                f"Analyses failed: {analyses_failed}",
                f"Open review tasks: {open_review_tasks}",
                f"Upcoming follow-ups next 7 days: {upcoming_follow_ups}",
            ]
        )
