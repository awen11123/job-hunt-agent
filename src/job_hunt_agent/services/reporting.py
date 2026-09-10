from datetime import date, datetime, timedelta, timezone, tzinfo

from job_hunt_agent.domain.models import ActivityEvent
from job_hunt_agent.domain.statuses import EventType, SyncStatus
from job_hunt_agent.repositories import JobHuntRepository


class ReportingService:
    def __init__(
        self,
        repository: JobHuntRepository,
        report_timezone: tzinfo | None = None,
    ) -> None:
        self.repository = repository
        self.report_timezone = (
            report_timezone or datetime.now().astimezone().tzinfo or timezone.utc
        )

    def _event_day(self, event: ActivityEvent) -> date:
        if event.event_type is EventType.APPLICATION_CREATED:
            try:
                application = self.repository.get_application(event.application_id)
            except KeyError:
                pass
            else:
                if application.applied_date is not None:
                    return application.applied_date

        if event.occurred_at.utcoffset() is None:
            return event.occurred_at.date()
        return event.occurred_at.astimezone(self.report_timezone).date()

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
            if self._event_day(event) != day:
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
            if not start_day <= self._event_day(event) <= end_day:
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

    def generate_text_overview(self, today: date) -> str:
        active_applications = [
            record for record in self.repository.applications.values() if not record.archived
        ]
        active_applications.sort(key=lambda record: (record.applied_date or date.min, record.company))
        missing_items = []
        for record in active_applications:
            pending_fields = record.missing_noncritical_fields()
            if pending_fields:
                missing_items.append(
                    f"- {record.company}｜{record.role}：{', '.join(chinese_field_name(field) for field in pending_fields)}"
                )

        recent_events = sorted(
            self.repository.activity_events,
            key=lambda event: event.occurred_at,
            reverse=True,
        )[:8]

        lines = [
            f"# 秋招总览｜{today.isoformat()}",
            "",
            "## 当前投递",
        ]
        if active_applications:
            lines.extend(application_line(record) for record in active_applications)
        else:
            lines.append("- 暂无投递记录。")

        lines.extend(["", "## 待补充"])
        if missing_items:
            lines.extend(missing_items)
        else:
            lines.append("- 暂无待补充字段。")

        lines.extend(["", "## 最近流程"])
        if recent_events:
            lines.extend(event_line(event, self.repository) for event in recent_events)
        else:
            lines.append("- 暂无流程变化。")

        follow_ups = self.list_follow_ups(today=today, days=7)
        lines.extend(["", "## 未来 7 天提醒"])
        if follow_ups:
            lines.extend(f"- {item['date']}｜{item['title']}" for item in follow_ups)
        else:
            lines.append("- 暂无临近截止、面试或复习任务。")

        return "\n".join(lines)


def application_line(record) -> str:
    next_step = record.next_step or "等待后续通知。"
    return (
        f"- {record.company}｜{record.role}｜"
        f"{chinese_stage(record.current_stage.value)}｜{chinese_priority(record.priority.value)}｜"
        f"{next_step}"
    )


def event_line(event, repository: JobHuntRepository) -> str:
    try:
        application = repository.get_application(event.application_id)
        title = f"{application.company} - {application.role}"
    except KeyError:
        title = event.application_id
    if event.event_type is EventType.APPLICATION_CREATED:
        action = f"新增投递：{title}"
    elif event.event_type is EventType.STAGE_UPDATED:
        action = f"阶段更新：{title} → {chinese_stage(event.to_stage.value if event.to_stage else '')}"
    else:
        action = f"{event.event_type.value}：{title}"
    return f"- {event.occurred_at.date().isoformat()} {action}"


def chinese_stage(value: str) -> str:
    return {
        "to_apply": "待投递",
        "applied": "已投递",
        "written_test": "笔试",
        "interview": "面试",
        "intention": "意向",
        "offer": "Offer",
    }.get(value, value)


def chinese_priority(value: str) -> str:
    return {
        "low": "低优先级",
        "medium": "中优先级",
        "high": "高优先级",
    }.get(value, value)


def chinese_field_name(value: str) -> str:
    return {
        "season": "秋招批次",
        "direction": "方向",
        "location": "地点",
        "channel": "投递渠道",
        "resume_version": "简历版本",
        "applied_date": "投递日期",
    }.get(value, value)
