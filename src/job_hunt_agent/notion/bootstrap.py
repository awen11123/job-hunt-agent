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


@dataclass(frozen=True)
class ViewSpec:
    name: str
    visible_properties: tuple[str, ...] | None
    reuse_default: bool = False


DATABASE_TITLES = {
    "applications": DatabaseTitle("投递记录", ("Applications",)),
    "activity": DatabaseTitle("流程日志", ("Activity Log",)),
    "interviews": DatabaseTitle("面试记录", ("Interviews",)),
    "review_tasks": DatabaseTitle("复习任务", ("Review Tasks",)),
}


APPLICATION_OVERVIEW_FIELDS = (
    "公司",
    "岗位",
    "当前阶段",
    "优先级",
    "投递日期",
    "截止日期",
    "下一步",
)
ACTIVITY_OVERVIEW_FIELDS = ("事件", "事件时间", "关联投递", "事件类型", "新状态")
INTERVIEW_OVERVIEW_FIELDS = ("面试", "关联投递", "时间", "形式", "结果", "分析状态", "自评分")
REVIEW_TASK_OVERVIEW_FIELDS = ("任务", "分类", "掌握程度", "出现次数", "截止日期", "完成状态")

VIEW_SPECS = {
    "applications": (
        ViewSpec("总览", APPLICATION_OVERVIEW_FIELDS, reuse_default=True),
        ViewSpec("待跟进", APPLICATION_OVERVIEW_FIELDS),
        ViewSpec("完整字段", None),
    ),
    "activity": (
        ViewSpec("总览", ACTIVITY_OVERVIEW_FIELDS, reuse_default=True),
        ViewSpec("完整字段", None),
    ),
    "interviews": (
        ViewSpec("总览", INTERVIEW_OVERVIEW_FIELDS, reuse_default=True),
        ViewSpec("面试安排", INTERVIEW_OVERVIEW_FIELDS),
        ViewSpec("完整字段", None),
    ),
    "review_tasks": (
        ViewSpec("总览", REVIEW_TASK_OVERVIEW_FIELDS, reuse_default=True),
        ViewSpec("复习看板", REVIEW_TASK_OVERVIEW_FIELDS),
        ViewSpec("完整字段", None),
    ),
}


OVERVIEW_PAGE_TITLE = "秋招总览"
TABLE_OVERVIEW_BACKUP_TITLE = "秋招总览（表格备份）"

OVERVIEW_LINKED_VIEWS = (
    ("applications", "投递记录", APPLICATION_OVERVIEW_FIELDS),
    ("activity", "流程日志", ACTIVITY_OVERVIEW_FIELDS),
    ("interviews", "面试记录", INTERVIEW_OVERVIEW_FIELDS),
    ("review_tasks", "复习任务", REVIEW_TASK_OVERVIEW_FIELDS),
)

TEXT_OVERVIEW_START = "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"
TEXT_OVERVIEW_END = "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"


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
        database_ids = BootstrappedDatabases(applications, activity, interviews, review_tasks)
        self.configure_readable_views(database_ids)
        self.ensure_overview_page(parent_page_id, database_ids)
        return database_ids

    def rename_configured_databases(self, database_ids: BootstrappedDatabases) -> None:
        for data_source_id, title in [
            (database_ids.applications, DATABASE_TITLES["applications"].current),
            (database_ids.activity, DATABASE_TITLES["activity"].current),
            (database_ids.interviews, DATABASE_TITLES["interviews"].current),
            (database_ids.review_tasks, DATABASE_TITLES["review_tasks"].current),
        ]:
            data_source = self.client.retrieve_data_source(data_source_id)
            self._rename_data_source(data_source, title)

    def configure_readable_views(self, database_ids: BootstrappedDatabases) -> None:
        plans = [
            ("applications", database_ids.applications, tuple(application_properties().keys())),
            ("activity", database_ids.activity, tuple(activity_properties(database_ids.applications).keys())),
            ("interviews", database_ids.interviews, tuple(interview_properties(database_ids.applications).keys())),
            (
                "review_tasks",
                database_ids.review_tasks,
                tuple(review_task_properties(database_ids.interviews).keys()),
            ),
        ]
        for key, data_source_id, properties in plans:
            self._configure_data_source_views(
                data_source_id=data_source_id,
                properties=properties,
                specs=VIEW_SPECS[key],
            )

    def ensure_overview_page(
        self,
        parent_page_id: str,
        database_ids: BootstrappedDatabases,
    ) -> str:
        page = self.client.find_page_by_title(OVERVIEW_PAGE_TITLE, parent_page_id=parent_page_id)
        if page is None:
            page = self.client.create_child_page(parent_page_id, OVERVIEW_PAGE_TITLE)
        page_id = page["id"]
        self._ensure_overview_linked_views(page_id, database_ids)
        return page_id

    def ensure_text_first_overview_page(self, parent_page_id: str) -> str:
        page = self.client.find_page_by_title(OVERVIEW_PAGE_TITLE, parent_page_id=parent_page_id)
        if page is None:
            return self.client.create_child_page(parent_page_id, OVERVIEW_PAGE_TITLE)["id"]
        children = self.client.list_block_children(page["id"])
        if children and children[0].get("type") == "child_database":
            self.client.update_child_page_title(page["id"], TABLE_OVERVIEW_BACKUP_TITLE)
            return self.client.create_child_page(parent_page_id, OVERVIEW_PAGE_TITLE)["id"]
        return page["id"]

    def refresh_text_overview(self, overview_page_id: str, overview_text: str) -> None:
        self._archive_existing_text_overview_blocks(overview_page_id)
        self.client.append_block_children(overview_page_id, text_overview_blocks(overview_text))

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

    def _configure_data_source_views(
        self,
        data_source_id: str,
        properties: tuple[str, ...],
        specs: tuple[ViewSpec, ...],
    ) -> None:
        data_source = self.client.retrieve_data_source(data_source_id)
        database_id = parent_database_id(data_source)
        if database_id is None:
            return
        existing_views = [self.client.retrieve_view(view["id"]) for view in self.client.list_views(database_id)]
        for spec in specs:
            self._ensure_view(database_id, data_source_id, properties, existing_views, spec)

    def _ensure_view(
        self,
        database_id: str,
        data_source_id: str,
        properties: tuple[str, ...],
        existing_views: list[dict],
        spec: ViewSpec,
    ) -> None:
        configuration = table_view_configuration(properties, spec.visible_properties)
        target_view = find_view(existing_views, spec.name)
        if target_view is not None:
            self.client.update_view(target_view["id"], {"name": spec.name, "configuration": configuration})
            return
        if spec.reuse_default:
            default_view = find_view(existing_views, "Default view")
            if default_view is not None:
                self.client.update_view(default_view["id"], {"name": spec.name, "configuration": configuration})
                return
        self.client.create_view(
            {
                "database_id": database_id,
                "name": spec.name,
                "type": "table",
                "data_source_id": data_source_id,
                "configuration": configuration,
            }
        )

    def _ensure_overview_linked_views(
        self,
        overview_page_id: str,
        database_ids: BootstrappedDatabases,
    ) -> None:
        properties_by_key = {
            "applications": tuple(application_properties().keys()),
            "activity": tuple(activity_properties(database_ids.applications).keys()),
            "interviews": tuple(interview_properties(database_ids.applications).keys()),
            "review_tasks": tuple(review_task_properties(database_ids.interviews).keys()),
        }
        data_source_by_key = {
            "applications": database_ids.applications,
            "activity": database_ids.activity,
            "interviews": database_ids.interviews,
            "review_tasks": database_ids.review_tasks,
        }
        for key, view_name, visible_properties in OVERVIEW_LINKED_VIEWS:
            data_source_id = data_source_by_key[key]
            properties = properties_by_key[key]
            configuration = table_view_configuration(properties, visible_properties)
            existing_view = self._find_overview_linked_view(
                data_source_id=data_source_id,
                view_name=view_name,
                overview_page_id=overview_page_id,
            )
            if existing_view is not None:
                self.client.update_view(
                    existing_view["id"],
                    {"name": view_name, "configuration": configuration},
                )
                continue
            self.client.create_linked_database_view(
                parent_page_id=overview_page_id,
                data_source_id=data_source_id,
                name=view_name,
                configuration=configuration,
            )

    def _find_overview_linked_view(
        self,
        data_source_id: str,
        view_name: str,
        overview_page_id: str,
    ) -> dict | None:
        for view_summary in self.client.list_views(data_source_id=data_source_id):
            view = self.client.retrieve_view(view_summary["id"])
            if view.get("name") != view_name:
                continue
            database_id = parent_database_id(view)
            if database_id is None:
                continue
            database = self.client.retrieve_database(database_id)
            parent = database.get("parent", {})
            if parent.get("type") == "page_id" and notion_id_equal(
                parent.get("page_id", ""),
                overview_page_id,
            ):
                return view
        return None

    def _archive_existing_text_overview_blocks(self, overview_page_id: str) -> None:
        in_managed_section = False
        for block in self.client.list_block_children(overview_page_id):
            block_text = plain_block_text(block)
            if block_text == TEXT_OVERVIEW_START:
                in_managed_section = True
            if in_managed_section:
                self.client.archive_block(block["id"])
            if block_text == TEXT_OVERVIEW_END:
                in_managed_section = False


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


def notion_id_equal(left: str, right: str) -> bool:
    return left.replace("-", "") == right.replace("-", "")


def find_view(views: list[dict], name: str) -> dict | None:
    for view in views:
        if view.get("name") == name:
            return view
    return None


def table_view_configuration(
    properties: tuple[str, ...],
    visible_properties: tuple[str, ...] | None,
) -> dict:
    visible = set(visible_properties or properties)
    ordered_properties = list(visible_properties or properties)
    ordered_properties.extend(property_name for property_name in properties if property_name not in visible)
    return {
        "type": "table",
        "properties": [
            {
                "property_id": property_name,
                "visible": property_name in visible,
            }
            for property_name in ordered_properties
        ],
    }


def text_overview_blocks(overview_text: str) -> list[dict]:
    blocks = [paragraph_block(TEXT_OVERVIEW_START)]
    for line in overview_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("# "):
            blocks.append(heading_block("heading_1", line.removeprefix("# ").strip()))
            continue
        if line.startswith("## "):
            blocks.append(heading_block("heading_2", line.removeprefix("## ").strip()))
            continue
        if line.startswith("- "):
            blocks.append(bulleted_list_item_block(line.removeprefix("- ").strip()))
            continue
        blocks.append(paragraph_block(line.strip()))
    blocks.append(paragraph_block(TEXT_OVERVIEW_END))
    return blocks


def paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text_payload(text)},
    }


def heading_block(block_type: str, text: str) -> dict:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": rich_text_payload(text)},
    }


def bulleted_list_item_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text_payload(text)},
    }


def rich_text_payload(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def plain_block_text(block: dict) -> str:
    block_type = block.get("type", "")
    rich_text = block.get(block_type, {}).get("rich_text", [])
    parts = []
    for item in rich_text:
        if "plain_text" in item:
            parts.append(item["plain_text"])
        else:
            parts.append(item.get("text", {}).get("content", ""))
    return "".join(parts)


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
