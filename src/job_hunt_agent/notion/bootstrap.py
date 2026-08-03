from dataclasses import dataclass
import os

from job_hunt_agent.notion.client import NotionClient


@dataclass(frozen=True)
class BootstrappedDatabases:
    applications: str
    activity: str
    interviews: str
    review_tasks: str


@dataclass(frozen=True)
class DatabaseTitle:
    current: str
    legacy: tuple[str, ...] = ()


DATABASE_TITLES = {
    "applications": DatabaseTitle("投递记录", ("Applications",)),
    "activity": DatabaseTitle("流程日志", ("Activity Log",)),
    "interviews": DatabaseTitle("面试记录", ("Interviews",)),
    "review_tasks": DatabaseTitle("复习任务", ("Review Tasks",)),
}


class NotionBootstrapper:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    def bootstrap(self, parent_page_id: str) -> BootstrappedDatabases:
        applications = self._get_or_create_database(
            parent_page_id,
            DATABASE_TITLES["applications"],
            application_properties(),
        )
        activity = self._get_or_create_database(
            parent_page_id,
            DATABASE_TITLES["activity"],
            activity_properties(applications),
        )
        interviews = self._get_or_create_database(
            parent_page_id,
            DATABASE_TITLES["interviews"],
            interview_properties(applications),
        )
        review_tasks = self._get_or_create_database(
            parent_page_id,
            DATABASE_TITLES["review_tasks"],
            review_task_properties(interviews),
        )
        return BootstrappedDatabases(applications, activity, interviews, review_tasks)

    def rename_configured_databases(self, database_ids: BootstrappedDatabases) -> None:
        for data_source_id, title in [
            (database_ids.applications, DATABASE_TITLES["applications"].current),
            (database_ids.activity, DATABASE_TITLES["activity"].current),
            (database_ids.interviews, DATABASE_TITLES["interviews"].current),
            (database_ids.review_tasks, DATABASE_TITLES["review_tasks"].current),
        ]:
            data_source = self.client.retrieve_data_source(data_source_id)
            self._rename_data_source(data_source, title)

    def _get_or_create_database(
        self,
        parent_page_id: str,
        title: DatabaseTitle,
        properties: dict,
    ) -> str:
        existing = self.client.find_database_by_title(title.current, parent_page_id=parent_page_id)
        if existing is not None:
            return existing["id"]
        for legacy_title in title.legacy:
            existing = self.client.find_database_by_title(legacy_title, parent_page_id=parent_page_id)
            if existing is not None:
                self._rename_data_source(existing, title.current)
                return existing["id"]
        return first_data_source_id(
            self.client.create_database(parent_page_id, title.current, properties)
        )

    def _rename_data_source(self, data_source: dict, title: str) -> None:
        data_source_id = data_source["id"]
        self.client.update_data_source_title(data_source_id, title)
        database_id = parent_database_id(data_source)
        if database_id:
            self.client.update_database_title(database_id, title)


def first_data_source_id(database: dict) -> str:
    data_sources = database.get("data_sources") or []
    if data_sources:
        return data_sources[0]["id"]
    return database["id"]


def parent_database_id(data_source: dict) -> str | None:
    parent = data_source.get("parent", {})
    if parent.get("type") == "database_id":
        return parent.get("database_id")
    return None


def application_properties() -> dict:
    return {
        "公司": {"title": {}},
        "岗位": {"rich_text": {}},
        "秋招批次": {"select": {}},
        "方向": {"select": {}},
        "地点": {"rich_text": {}},
        "投递渠道": {"select": {}},
        "JD 链接": {"url": {}},
        "简历版本": {"rich_text": {}},
        "投递日期": {"date": {}},
        "当前阶段": {"select": {}},
        "优先级": {"select": {}},
        "截止日期": {"date": {}},
        "下一步": {"rich_text": {}},
        "最终结果": {"select": {}},
        "结束原因": {"rich_text": {}},
        "是否待补充": {"checkbox": {}},
        "归档状态": {"checkbox": {}},
    }


def activity_properties(applications_database_id: str) -> dict:
    return {
        "事件": {"title": {}},
        "事件时间": {"date": {}},
        "关联投递": {
            "relation": {
                "data_source_id": applications_database_id,
                "single_property": {},
            }
        },
        "操作唯一 ID": {"rich_text": {}},
        "事件类型": {"select": {}},
        "原状态": {"select": {}},
        "新状态": {"select": {}},
        "备注": {"rich_text": {}},
        "同步状态": {"select": {}},
    }


def interview_properties(applications_database_id: str) -> dict:
    return {
        "面试": {"title": {}},
        "关联投递": {
            "relation": {
                "data_source_id": applications_database_id,
                "single_property": {},
            }
        },
        "面试轮次": {"rich_text": {}},
        "时间": {"date": {}},
        "形式": {"select": {}},
        "结果": {"select": {}},
        "原始笔记": {"rich_text": {}},
        "结构化面经": {"rich_text": {}},
        "自评分": {"number": {"format": "number"}},
        "总体复盘": {"rich_text": {}},
        "模型版本": {"rich_text": {}},
        "Prompt 版本": {"rich_text": {}},
        "分析状态": {"select": {}},
    }


def review_task_properties(interviews_database_id: str) -> dict:
    return {
        "任务": {"title": {}},
        "分类": {"select": {}},
        "知识点或问题": {"rich_text": {}},
        "来源面试": {
            "relation": {
                "data_source_id": interviews_database_id,
                "single_property": {},
            }
        },
        "掌握程度": {"select": {}},
        "出现次数": {"number": {"format": "number"}},
        "复习行动": {"rich_text": {}},
        "截止日期": {"date": {}},
        "完成状态": {"checkbox": {}},
        "确认状态": {"select": {}},
    }


def set_user_environment_value(name: str, value: str) -> None:
    os.environ[name] = value
    if os.name != "nt":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
