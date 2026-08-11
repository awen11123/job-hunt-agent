from datetime import datetime, timezone
from dataclasses import dataclass
import json
from typing import Protocol
from uuid import uuid4

from job_hunt_agent.domain.models import (
    ActivityEvent,
    ApplicationRecord,
    InterviewRecord,
    ReviewTaskRecord,
)
from job_hunt_agent.domain.statuses import (
    EventType,
    FinalOutcome,
    InterviewAnalysisStatus,
    Priority,
    RecruitingStage,
    SyncStatus,
)
from job_hunt_agent.matching import application_key, normalize_text
from job_hunt_agent.notion.client import NotionClient


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


@dataclass(frozen=True)
class NotionDatabaseIds:
    applications: str
    activity: str
    interviews: str
    review_tasks: str


class NotionJobHuntRepository:
    def __init__(
        self,
        token: str,
        database_ids: NotionDatabaseIds,
        client: NotionClient | None = None,
    ) -> None:
        self.client = client or NotionClient(token)
        self.database_ids = database_ids
        self.applications: dict[str, ApplicationRecord] = {}
        self.activity_events: list[ActivityEvent] = []
        self.interviews: dict[str, InterviewRecord] = {}
        self.review_tasks: dict[str, ReviewTaskRecord] = {}

    def next_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    def save_application(self, record: ApplicationRecord) -> ApplicationRecord:
        properties = application_to_properties(record)
        if is_temporary_id(record.id):
            page = self.client.create_page(self.database_ids.applications, properties)
        else:
            page = self.client.update_page(record.id, properties)
        saved = record.model_copy(update={"id": page["id"]})
        self.applications[saved.id] = saved
        return saved

    def get_application(self, application_id: str | None) -> ApplicationRecord:
        if application_id is None:
            raise KeyError("application not found: None")
        if application_id in self.applications:
            return self.applications[application_id]
        page = self.client.retrieve_page(application_id)
        record = application_from_page(page)
        self.applications[record.id] = record
        return record

    def find_application_by_key(self, company: str, role: str, season: str) -> ApplicationRecord | None:
        expected = application_key(company, role, season)
        for page in self.client.query_database(self.database_ids.applications):
            record = application_from_page(page)
            self.applications[record.id] = record
            if application_key(record.company, record.role, record.season) == expected:
                return record
        return None

    def save_activity_event(self, event: ActivityEvent) -> ActivityEvent:
        properties = activity_to_properties(event)
        if is_temporary_id(event.id):
            page = self.client.create_page(self.database_ids.activity, properties)
        else:
            page = self.client.update_page(event.id, properties)
        saved = event.model_copy(update={"id": page["id"]})
        self.activity_events = [item for item in self.activity_events if item.id != saved.id]
        self.activity_events.append(saved)
        return saved

    def find_activity_by_operation_id(self, operation_id: str) -> ActivityEvent | None:
        for event in self.activity_events:
            if event.operation_id == operation_id:
                return event
        filter_payload = {"property": "操作唯一 ID", "rich_text": {"equals": operation_id}}
        for page in self.client.query_database(self.database_ids.activity, filter_payload):
            event = activity_from_page(page)
            self.activity_events.append(event)
            return event
        return None

    def save_interview(self, record: InterviewRecord) -> InterviewRecord:
        properties = interview_to_properties(record)
        if is_temporary_id(record.id):
            page = self.client.create_page(self.database_ids.interviews, properties)
        else:
            page = self.client.update_page(record.id, properties)
        saved = record.model_copy(update={"id": page["id"]})
        self.interviews[saved.id] = saved
        return saved

    def get_interview(self, interview_id: str) -> InterviewRecord:
        if interview_id in self.interviews:
            return self.interviews[interview_id]
        page = self.client.retrieve_page(interview_id)
        record = interview_from_page(page)
        self.interviews[record.id] = record
        return record

    def save_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord:
        properties = review_task_to_properties(record)
        if is_temporary_id(record.id):
            page = self.client.create_page(self.database_ids.review_tasks, properties)
        else:
            page = self.client.update_page(record.id, properties)
        saved = record.model_copy(update={"id": page["id"]})
        self.review_tasks[saved.id] = saved
        return saved

    def find_review_task_by_topic(self, category: str, topic: str) -> ReviewTaskRecord | None:
        expected = (normalize_text(category), normalize_text(topic))
        for task in self.review_tasks.values():
            if (normalize_text(task.category), normalize_text(task.topic)) == expected:
                return task
        for page in self.client.query_database(self.database_ids.review_tasks):
            task = review_task_from_page(page)
            self.review_tasks[task.id] = task
            if (normalize_text(task.category), normalize_text(task.topic)) == expected:
                return task
        return None


def is_temporary_id(value: str) -> bool:
    return value.startswith(("app_", "evt_", "int_", "rev_"))


def title_property(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def text_property(value: str | None) -> dict:
    if not value:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}


def select_property(value: str | None) -> dict:
    return {"select": {"name": value}} if value else {"select": None}


def date_property(value: object | None) -> dict:
    return {"date": {"start": value.isoformat()}} if value else {"date": None}


def relation_property(page_ids: list[str]) -> dict:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def number_property(value: int | None) -> dict:
    return {"number": value}


def checkbox_property(value: bool) -> dict:
    return {"checkbox": value}


def title_text(properties: dict, name: str) -> str:
    items = properties.get(name, {}).get("title", [])
    return "".join(item.get("plain_text", "") for item in items)


def rich_text(properties: dict, name: str) -> str | None:
    items = properties.get(name, {}).get("rich_text", [])
    text = "".join(item.get("plain_text", "") for item in items)
    return text or None


def select_text(properties: dict, name: str) -> str | None:
    value = properties.get(name, {}).get("select")
    return value.get("name") if value else None


def checkbox_value(properties: dict, name: str) -> bool:
    return bool(properties.get(name, {}).get("checkbox", False))


def application_to_properties(record: ApplicationRecord) -> dict:
    return {
        "公司": title_property(record.company),
        "岗位": text_property(record.role),
        "秋招批次": select_property(record.season),
        "方向": select_property(record.direction),
        "地点": text_property(record.location),
        "投递渠道": select_property(record.channel),
        "JD 链接": {"url": str(record.jd_url) if record.jd_url else None},
        "简历版本": text_property(record.resume_version),
        "投递日期": date_property(record.applied_date),
        "当前阶段": select_property(record.current_stage.value),
        "优先级": select_property(record.priority.value),
        "截止日期": date_property(record.deadline),
        "下一步": text_property(record.next_step),
        "最终结果": select_property(record.final_outcome.value),
        "结束原因": text_property(record.end_reason),
        "是否待补充": checkbox_property(record.needs_supplement),
        "归档状态": checkbox_property(record.archived),
    }


def application_from_page(page: dict) -> ApplicationRecord:
    properties = page.get("properties", {})
    now = utc_now()
    return ApplicationRecord(
        id=page["id"],
        company=title_text(properties, "公司") or "Unknown",
        role=rich_text(properties, "岗位") or "Unknown",
        season=select_text(properties, "秋招批次") or "unknown",
        direction=select_text(properties, "方向"),
        location=rich_text(properties, "地点"),
        channel=select_text(properties, "投递渠道"),
        current_stage=RecruitingStage(select_text(properties, "当前阶段") or RecruitingStage.APPLIED),
        priority=Priority(select_text(properties, "优先级") or Priority.MEDIUM),
        final_outcome=FinalOutcome(select_text(properties, "最终结果") or FinalOutcome.ONGOING),
        end_reason=rich_text(properties, "结束原因"),
        needs_supplement=checkbox_value(properties, "是否待补充"),
        archived=checkbox_value(properties, "归档状态"),
        created_at=now,
        updated_at=now,
    )


def activity_to_properties(event: ActivityEvent) -> dict:
    return {
        "事件": title_property(f"{event.event_type.value} {event.operation_id}"),
        "事件时间": date_property(event.occurred_at),
        "关联投递": relation_property([event.application_id]),
        "操作唯一 ID": text_property(event.operation_id),
        "事件类型": select_property(event.event_type.value),
        "原状态": select_property(event.from_stage.value if event.from_stage else None),
        "新状态": select_property(event.to_stage.value if event.to_stage else None),
        "备注": text_property(event.note),
        "同步状态": select_property(event.sync_status.value),
    }


def activity_from_page(page: dict) -> ActivityEvent:
    properties = page.get("properties", {})
    relation = properties.get("关联投递", {}).get("relation", [])
    application_id = relation[0]["id"] if relation else ""
    return ActivityEvent(
        id=page["id"],
        application_id=application_id,
        operation_id=rich_text(properties, "操作唯一 ID") or "",
        event_type=EventType(select_text(properties, "事件类型") or EventType.APPLICATION_CREATED),
        occurred_at=utc_now(),
        sync_status=SyncStatus(select_text(properties, "同步状态") or SyncStatus.COMPLETED),
    )


def interview_to_properties(record: InterviewRecord) -> dict:
    analysis_json = (
        json.dumps(record.structured_analysis.model_dump(mode="json"), ensure_ascii=False)
        if record.structured_analysis
        else None
    )
    return {
        "面试": title_property(record.round_name),
        "关联投递": relation_property([record.application_id]),
        "面试轮次": text_property(record.round_name),
        "时间": date_property(record.scheduled_at),
        "形式": select_property(record.format),
        "结果": select_property(record.result),
        "原始笔记": text_property(record.raw_notes),
        "结构化面经": text_property(analysis_json),
        "自评分": number_property(record.self_score),
        "总体复盘": text_property(record.structured_analysis.overview if record.structured_analysis else None),
        "模型版本": text_property(record.model_version),
        "Prompt 版本": text_property(record.prompt_version),
        "分析状态": select_property(record.analysis_status.value),
    }


def interview_from_page(page: dict) -> InterviewRecord:
    properties = page.get("properties", {})
    now = utc_now()
    relation = properties.get("关联投递", {}).get("relation", [])
    return InterviewRecord(
        id=page["id"],
        application_id=relation[0]["id"] if relation else "",
        round_name=rich_text(properties, "面试轮次") or title_text(properties, "面试") or "unknown",
        raw_notes=rich_text(properties, "原始笔记") or "No raw notes found.",
        analysis_status=InterviewAnalysisStatus(select_text(properties, "分析状态") or "pending"),
        created_at=now,
        updated_at=now,
    )


def review_task_to_properties(record: ReviewTaskRecord) -> dict:
    return {
        "任务": title_property(record.topic),
        "分类": select_property(record.category),
        "知识点或问题": text_property(record.topic),
        "来源面试": relation_property(record.source_interview_ids),
        "掌握程度": select_property(record.mastery),
        "出现次数": number_property(record.occurrences),
        "复习行动": text_property(record.action),
        "截止日期": date_property(record.due_date),
        "完成状态": checkbox_property(record.completed),
        "确认状态": select_property(record.confirmation_status),
    }


def review_task_from_page(page: dict) -> ReviewTaskRecord:
    properties = page.get("properties", {})
    now = utc_now()
    relation = properties.get("来源面试", {}).get("relation", [])
    return ReviewTaskRecord(
        id=page["id"],
        category=select_text(properties, "分类") or "uncategorized",
        topic=rich_text(properties, "知识点或问题") or title_text(properties, "任务") or "unknown",
        action=rich_text(properties, "复习行动") or "Review the related interview notes and write a corrected answer.",
        mastery=select_text(properties, "掌握程度"),
        occurrences=int(properties.get("出现次数", {}).get("number") or 1),
        source_interview_ids=[item["id"] for item in relation],
        completed=checkbox_value(properties, "完成状态"),
        confirmation_status=select_text(properties, "确认状态") or "pending",
        created_at=now,
        updated_at=now,
    )
