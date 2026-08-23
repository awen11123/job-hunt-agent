from datetime import datetime, timezone

from job_hunt_agent.domain.models import ActivityEvent, ApplicationDraft, ApplicationRecord
from job_hunt_agent.domain.statuses import EventType, RecruitingStage, SyncStatus
from job_hunt_agent.notion.bootstrap import NotionBootstrapper
from job_hunt_agent.notion.client import NotionClient
from job_hunt_agent.repositories import (
    NotionDatabaseIds,
    NotionJobHuntRepository,
    activity_from_page,
)
from job_hunt_agent.services.applications import ApplicationService


class FakeNotionClient:
    def __init__(self) -> None:
        self.created_databases: list[dict] = []
        self.created_pages: list[dict] = []
        self.queried_pages: list[dict] = []
        self.queried_pages_by_database: dict[str, list[dict]] = {}
        self.updated_pages: list[tuple[str, dict]] = []
        self.updated_data_source_titles: list[tuple[str, str]] = []
        self.updated_database_titles: list[tuple[str, str]] = []
        self.updated_views: list[tuple[str, dict]] = []
        self.created_views: list[dict] = []
        self.queried_databases: list[tuple[str, dict | None]] = []
        self.created_child_pages: list[dict] = []
        self.updated_child_page_titles: list[tuple[str, str]] = []
        self.children_by_block: dict[str, list[dict]] = {}
        self.appended_children: list[tuple[str, list[dict]]] = []
        self.archived_blocks: list[str] = []
        self.search_results: dict[str, dict] = {}
        self.search_page_results: dict[str, dict] = {}
        self.views_by_database: dict[str, list[dict]] = {}
        self.views_by_data_source: dict[str, list[dict]] = {}
        self.databases_by_id: dict[str, dict] = {}

    def create_database(self, parent_page_id: str, title: str, properties: dict) -> dict:
        sequence = len(self.created_databases) + 1
        database_id = f"db_{sequence}"
        data_source_id = f"ds_{sequence}"
        self.created_databases.append(
            {"parent_page_id": parent_page_id, "title": title, "properties": properties}
        )
        return {"id": database_id, "data_sources": [{"id": data_source_id}]}

    def create_page(self, parent_data_source_id: str, properties: dict) -> dict:
        page_id = f"page_{len(self.created_pages) + 1}"
        self.created_pages.append(
            {"parent_data_source_id": parent_data_source_id, "properties": properties}
        )
        return {"id": page_id, "properties": properties}

    def update_page(self, page_id: str, properties: dict) -> dict:
        self.updated_pages.append((page_id, properties))
        return {"id": page_id, "properties": properties}

    def update_child_page_title(self, page_id: str, title: str) -> dict:
        self.updated_child_page_titles.append((page_id, title))
        return {"id": page_id}

    def query_database(self, database_id: str, filter_payload: dict | None = None) -> list[dict]:
        self.queried_databases.append((database_id, filter_payload))
        if database_id in self.queried_pages_by_database:
            return self.queried_pages_by_database[database_id]
        return self.queried_pages

    def create_child_page(self, parent_page_id: str, title: str) -> dict:
        page_id = f"child_page_{len(self.created_child_pages) + 1}"
        page = {"id": page_id, "parent_page_id": parent_page_id, "title": title}
        self.created_child_pages.append(page)
        return page

    def find_page_by_title(self, title: str, parent_page_id: str | None = None) -> dict | None:
        page = self.search_page_results.get(title)
        if page is None:
            return None
        if parent_page_id is None or page.get("parent_page_id") == parent_page_id:
            return page
        return None

    def retrieve_page(self, page_id: str) -> dict:
        return {"id": page_id, "properties": {}}

    def retrieve_data_source(self, data_source_id: str) -> dict:
        return {
            "id": data_source_id,
            "parent": {"type": "database_id", "database_id": f"{data_source_id}_database"},
        }

    def find_database_by_title(self, title: str, parent_page_id: str | None = None) -> dict | None:
        return self.search_results.get(title)

    def update_data_source_title(self, data_source_id: str, title: str) -> dict:
        self.updated_data_source_titles.append((data_source_id, title))
        return {"id": data_source_id}

    def update_database_title(self, database_id: str, title: str) -> dict:
        self.updated_database_titles.append((database_id, title))
        return {"id": database_id}

    def retrieve_database(self, database_id: str) -> dict:
        return self.databases_by_id.get(
            database_id,
            {"id": database_id, "parent": {"type": "page_id", "page_id": "parent_1"}},
        )

    def list_views(
        self,
        database_id: str | None = None,
        data_source_id: str | None = None,
    ) -> list[dict]:
        if data_source_id is not None:
            return self.views_by_data_source.get(data_source_id, [])
        return self.views_by_database.get(database_id or "", [])

    def retrieve_view(self, view_id: str) -> dict:
        for views in [*self.views_by_database.values(), *self.views_by_data_source.values()]:
            for view in views:
                if view["id"] == view_id:
                    return view
        return {"id": view_id, "name": "Default view", "type": "table"}

    def update_view(self, view_id: str, payload: dict) -> dict:
        self.updated_views.append((view_id, payload))
        return {"id": view_id, **payload}

    def create_view(self, payload: dict) -> dict:
        view = {"id": f"view_{len(self.created_views) + 1}", **payload}
        self.created_views.append(view)
        return view

    def create_linked_database_view(
        self,
        parent_page_id: str,
        data_source_id: str,
        name: str,
        configuration: dict,
    ) -> dict:
        return self.create_view(
            {
                "create_database": {
                    "parent": {"type": "page_id", "page_id": parent_page_id},
                },
                "data_source_id": data_source_id,
                "name": name,
                "type": "table",
                "configuration": configuration,
            }
        )

    def list_block_children(self, block_id: str) -> list[dict]:
        return self.children_by_block.get(block_id, [])

    def append_block_children(self, block_id: str, children: list[dict]) -> dict:
        self.appended_children.append((block_id, children))
        self.children_by_block.setdefault(block_id, []).extend(children)
        return {"results": children}

    def archive_block(self, block_id: str) -> dict:
        self.archived_blocks.append(block_id)
        return {"id": block_id, "archived": True}


def test_bootstrap_creates_databases_with_relations() -> None:
    client = FakeNotionClient()
    bootstrapper = NotionBootstrapper(client)

    ids = bootstrapper.bootstrap(parent_page_id="parent_1")

    assert ids.applications == "ds_1"
    assert ids.activity == "ds_2"
    assert ids.interviews == "ds_3"
    assert ids.review_tasks == "ds_4"
    assert [item["title"] for item in client.created_databases] == [
        "投递记录",
        "流程日志",
        "面试记录",
        "复习任务",
    ]
    activity_relation = client.created_databases[1]["properties"]["关联投递"]["relation"]
    review_relation = client.created_databases[3]["properties"]["来源面试"]["relation"]
    assert activity_relation["data_source_id"] == "ds_1"
    assert activity_relation["single_property"] == {}
    assert review_relation["data_source_id"] == "ds_3"
    assert review_relation["single_property"] == {}


def test_bootstrap_reuses_existing_database_by_title_before_creating() -> None:
    client = FakeNotionClient()
    client.search_results["投递记录"] = {"id": "existing_apps_ds"}
    bootstrapper = NotionBootstrapper(client)

    ids = bootstrapper.bootstrap(parent_page_id="parent_1")

    assert ids.applications == "existing_apps_ds"
    assert [item["title"] for item in client.created_databases] == [
        "流程日志",
        "面试记录",
        "复习任务",
    ]
    activity_relation = client.created_databases[0]["properties"]["关联投递"]["relation"]
    assert activity_relation["data_source_id"] == "existing_apps_ds"
    assert activity_relation["single_property"] == {}


def test_bootstrap_renames_legacy_english_database_titles() -> None:
    client = FakeNotionClient()
    client.search_results["Applications"] = {
        "id": "existing_apps_ds",
        "parent": {"type": "database_id", "database_id": "existing_apps_db"},
    }
    bootstrapper = NotionBootstrapper(client)

    ids = bootstrapper.bootstrap(parent_page_id="parent_1")

    assert ids.applications == "existing_apps_ds"
    assert client.updated_data_source_titles[0] == ("existing_apps_ds", "投递记录")
    assert client.updated_database_titles[0] == ("existing_apps_db", "投递记录")


def test_bootstrap_configures_slim_default_views_and_full_field_views() -> None:
    client = FakeNotionClient()
    client.views_by_database["apps_ds_database"] = [
        {"id": "apps_default_view", "name": "Default view", "type": "table"}
    ]
    bootstrapper = NotionBootstrapper(client)

    bootstrapper.configure_readable_views(
        database_ids=type(
            "Ids",
            (),
            {
                "applications": "apps_ds",
                "activity": "activity_ds",
                "interviews": "interviews_ds",
                "review_tasks": "review_ds",
            },
        )()
    )

    updated_view_id, updated_payload = client.updated_views[0]
    assert updated_view_id == "apps_default_view"
    assert updated_payload["name"] == "总览"
    visible_properties = visible_property_names(updated_payload["configuration"])
    assert visible_properties == [
        "公司",
        "岗位",
        "当前阶段",
        "优先级",
        "投递日期",
        "截止日期",
        "下一步",
    ]
    created_names = [view["name"] for view in client.created_views]
    assert "完整字段" in created_names
    assert "待跟进" in created_names
    assert "面试安排" in created_names
    assert "复习看板" in created_names
    created_full_view = next(view for view in client.created_views if view["name"] == "完整字段")
    assert created_full_view["database_id"] == "apps_ds_database"
    assert "parent" not in created_full_view


def test_bootstrap_creates_overview_page_with_four_linked_database_views() -> None:
    client = FakeNotionClient()
    bootstrapper = NotionBootstrapper(client)
    database_ids = type(
        "Ids",
        (),
        {
            "applications": "apps_ds",
            "activity": "activity_ds",
            "interviews": "interviews_ds",
            "review_tasks": "review_ds",
        },
    )()

    overview_page_id = bootstrapper.ensure_overview_page("parent_1", database_ids)

    assert overview_page_id == "child_page_1"
    assert client.created_child_pages == [
        {"id": "child_page_1", "parent_page_id": "parent_1", "title": "秋招总览"}
    ]
    assert [view["name"] for view in client.created_views] == [
        "投递记录",
        "流程日志",
        "面试记录",
        "复习任务",
    ]
    assert [view["data_source_id"] for view in client.created_views] == [
        "apps_ds",
        "activity_ds",
        "interviews_ds",
        "review_ds",
    ]
    assert all(
        view["create_database"]["parent"] == {"type": "page_id", "page_id": "child_page_1"}
        for view in client.created_views
    )
    apps_configuration = client.created_views[0]["configuration"]
    assert visible_property_names(apps_configuration) == [
        "公司",
        "岗位",
        "当前阶段",
        "优先级",
        "投递日期",
        "截止日期",
        "下一步",
    ]


def test_bootstrap_reuses_existing_overview_page_and_linked_view() -> None:
    client = FakeNotionClient()
    client.search_page_results["秋招总览"] = {
        "id": "overview_page",
        "parent_page_id": "parent_1",
        "title": "秋招总览",
    }
    client.views_by_data_source["apps_ds"] = [
        {
            "id": "existing_apps_view",
            "name": "投递记录",
            "parent": {"type": "database_id", "database_id": "linked_apps_db"},
            "data_source_id": "apps_ds",
            "type": "table",
        }
    ]
    client.databases_by_id["linked_apps_db"] = {
        "id": "linked_apps_db",
        "parent": {"type": "page_id", "page_id": "overview_page"},
    }
    bootstrapper = NotionBootstrapper(client)
    database_ids = type(
        "Ids",
        (),
        {
            "applications": "apps_ds",
            "activity": "activity_ds",
            "interviews": "interviews_ds",
            "review_tasks": "review_ds",
        },
    )()

    overview_page_id = bootstrapper.ensure_overview_page("parent_1", database_ids)

    assert overview_page_id == "overview_page"
    assert client.created_child_pages == []
    assert client.updated_views[0][0] == "existing_apps_view"
    assert [view["name"] for view in client.created_views] == [
        "流程日志",
        "面试记录",
        "复习任务",
    ]


def test_bootstrap_refreshes_text_first_overview_blocks() -> None:
    client = FakeNotionClient()
    client.children_by_block["overview_page"] = [
        {
            "id": "old_marker",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"plain_text": "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"}],
            },
        },
        {
            "id": "old_content",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": "旧内容"}]},
        },
        {
            "id": "old_end",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"plain_text": "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"}],
            },
        },
        {
            "id": "database_block",
            "type": "child_database",
            "child_database": {"title": "Untitled"},
        },
    ]
    bootstrapper = NotionBootstrapper(client)

    bootstrapper.refresh_text_overview(
        overview_page_id="overview_page",
        overview_text="# 秋招总览｜2026-08-13\n\n## 当前投递\n- 示例科技｜智能 Agent 系统开发工程师",
    )

    assert client.archived_blocks == ["old_marker", "old_content", "old_end"]
    block_id, children = client.appended_children[0]
    assert block_id == "overview_page"
    assert children[0]["paragraph"]["rich_text"][0]["text"]["content"] == (
        "JOB_HUNT_AGENT_TEXT_OVERVIEW_START"
    )
    assert children[1]["type"] == "heading_1"
    assert children[1]["heading_1"]["rich_text"][0]["text"]["content"] == "秋招总览｜2026-08-13"
    assert children[3]["type"] == "bulleted_list_item"
    assert "示例科技" in children[3]["bulleted_list_item"]["rich_text"][0]["text"]["content"]
    assert children[-1]["paragraph"]["rich_text"][0]["text"]["content"] == (
        "JOB_HUNT_AGENT_TEXT_OVERVIEW_END"
    )
    assert "database_block" not in client.archived_blocks


def test_bootstrap_can_replace_table_first_overview_with_text_first_page() -> None:
    client = FakeNotionClient()
    client.search_page_results["秋招总览"] = {
        "id": "old_table_overview",
        "parent_page_id": "parent_1",
        "title": "秋招总览",
    }
    client.children_by_block["old_table_overview"] = [
        {
            "id": "database_block",
            "type": "child_database",
            "child_database": {"title": "Untitled"},
        }
    ]
    bootstrapper = NotionBootstrapper(client)

    page_id = bootstrapper.ensure_text_first_overview_page("parent_1")

    assert client.updated_child_page_titles == [
        ("old_table_overview", "秋招总览（表格备份）")
    ]
    assert page_id == "child_page_1"
    assert client.created_child_pages == [
        {"id": "child_page_1", "parent_page_id": "parent_1", "title": "秋招总览"}
    ]


def visible_property_names(configuration: dict) -> list[str]:
    return [
        item["property_id"]
        for item in configuration["properties"]
        if item.get("visible")
    ]


def test_notion_repository_save_application_returns_notion_page_id() -> None:
    client = FakeNotionClient()
    repo = NotionJobHuntRepository(
        token="fake-token",
        database_ids=NotionDatabaseIds(
            applications="apps_db",
            activity="activity_db",
            interviews="interviews_db",
            review_tasks="review_tasks_db",
        ),
        client=client,
    )
    record = ApplicationRecord(
        id="app_temp",
        company="DeepSeek",
        role="LLM Application Engineer",
        season="2026-autumn",
        current_stage=RecruitingStage.APPLIED,
        created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    saved = repo.save_application(record)

    assert saved.id == "page_1"
    assert client.created_pages[0]["parent_data_source_id"] == "apps_db"
    properties = client.created_pages[0]["properties"]
    assert properties["公司"]["title"][0]["text"]["content"] == "DeepSeek"
    assert properties["岗位"]["rich_text"][0]["text"]["content"] == "LLM Application Engineer"


def test_application_from_notion_page_preserves_overview_fields() -> None:
    client = FakeNotionClient()
    client.queried_pages = [
        {
            "id": "page_app",
            "properties": {
                "公司": {"title": [{"plain_text": "示例科技"}]},
                "岗位": {"rich_text": [{"plain_text": "智能 Agent 系统开发工程师"}]},
                "秋招批次": {"select": {"name": "2026-autumn"}},
                "方向": {"select": {"name": "AI Agent / LLM 应用"}},
                "地点": {"rich_text": [{"plain_text": "远程面试"}]},
                "投递渠道": {"select": {"name": "示例科技校招官网"}},
                "简历版本": {"rich_text": [{"plain_text": "resume-v3.pdf"}]},
                "投递日期": {"date": {"start": "2026-08-13"}},
                "当前阶段": {"select": {"name": "applied"}},
                "优先级": {"select": {"name": "high"}},
                "下一步": {"rich_text": [{"plain_text": "准备 Agent 架构。"}]},
                "最终结果": {"select": {"name": "ongoing"}},
                "是否待补充": {"checkbox": False},
                "归档状态": {"checkbox": False},
            },
        }
    ]
    repo = NotionJobHuntRepository(
        token="fake-token",
        database_ids=NotionDatabaseIds(
            applications="apps_db",
            activity="activity_db",
            interviews="interviews_db",
            review_tasks="review_tasks_db",
        ),
        client=client,
    )

    record = repo.find_application_by_key("示例科技", "智能 Agent 系统开发工程师", "2026-autumn")

    assert record is not None
    assert record.resume_version == "resume-v3.pdf"
    assert record.applied_date.isoformat() == "2026-08-13"
    assert record.next_step == "准备 Agent 架构。"


def test_notion_repository_loads_all_overview_data() -> None:
    client = FakeNotionClient()
    client.queried_pages_by_database["apps_db"] = [
        {
            "id": "page_app",
            "properties": {
                "公司": {"title": [{"plain_text": "Example Travel"}]},
                "岗位": {"rich_text": [{"plain_text": "AI Platform Engineer"}]},
                "秋招批次": {"select": {"name": "2026-autumn"}},
                "当前阶段": {"select": {"name": "applied"}},
                "优先级": {"select": {"name": "high"}},
                "下一步": {"rich_text": [{"plain_text": "Prepare the technical interview."}]},
                "最终结果": {"select": {"name": "ongoing"}},
                "是否待补充": {"checkbox": True},
                "归档状态": {"checkbox": False},
            },
        }
    ]
    client.queried_pages_by_database["activity_db"] = [
        {
            "id": "page_event",
            "properties": {
                "关联投递": {"relation": [{"id": "page_app"}]},
                "操作唯一 ID": {"rich_text": [{"plain_text": "op-example"}]},
                "事件类型": {"select": {"name": "application_created"}},
                "事件时间": {"date": {"start": "2026-08-10T09:30:00+08:00"}},
                "同步状态": {"select": {"name": "completed"}},
            },
        }
    ]
    client.queried_pages_by_database["interviews_db"] = []
    client.queried_pages_by_database["review_tasks_db"] = []
    repo = NotionJobHuntRepository(
        token="fake-token",
        database_ids=NotionDatabaseIds(
            applications="apps_db",
            activity="activity_db",
            interviews="interviews_db",
            review_tasks="review_tasks_db",
        ),
        client=client,
    )

    repo.load_all()

    assert list(repo.applications) == ["page_app"]
    assert repo.activity_events[0].operation_id == "op-example"
    assert repo.activity_events[0].occurred_at.isoformat() == "2026-08-10T09:30:00+08:00"
    assert client.queried_databases == [
        ("apps_db", None),
        ("activity_db", None),
        ("interviews_db", None),
        ("review_tasks_db", None),
    ]


def test_activity_from_notion_page_preserves_date_only_event_time() -> None:
    event = activity_from_page(
        {
            "id": "page_event",
            "properties": {
                "事件时间": {"date": {"start": "2026-08-10"}},
                "事件类型": {"select": {"name": "application_created"}},
            },
        }
    )

    assert event.occurred_at == datetime(2026, 8, 10, tzinfo=timezone.utc)


def test_activity_from_notion_page_falls_back_when_event_time_is_missing(
    monkeypatch,
) -> None:
    fallback = datetime(2026, 8, 11, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("job_hunt_agent.repositories.utc_now", lambda: fallback)

    event = activity_from_page(
        {
            "id": "page_event",
            "properties": {
                "事件类型": {"select": {"name": "application_created"}},
            },
        }
    )

    assert event.occurred_at == fallback


def test_application_service_uses_saved_notion_application_id_for_activity_relation() -> None:
    client = FakeNotionClient()
    repo = NotionJobHuntRepository(
        token="fake-token",
        database_ids=NotionDatabaseIds(
            applications="apps_db",
            activity="activity_db",
            interviews="interviews_db",
            review_tasks="review_tasks_db",
        ),
        client=client,
    )
    service = ApplicationService(repo, default_season="2026-autumn")

    receipt = service.record_application(
        ApplicationDraft(company="DeepSeek", role="LLM Application Engineer"),
        operation_id="op-create-1",
    )

    assert receipt.record_id == "page_1"
    activity_properties = client.created_pages[1]["properties"]
    assert activity_properties["关联投递"]["relation"] == [{"id": "page_1"}]


def test_notion_repository_save_activity_update_reuses_created_page_id() -> None:
    client = FakeNotionClient()
    repo = NotionJobHuntRepository(
        token="fake-token",
        database_ids=NotionDatabaseIds(
            applications="apps_db",
            activity="activity_db",
            interviews="interviews_db",
            review_tasks="review_tasks_db",
        ),
        client=client,
    )
    event = ActivityEvent(
        id="evt_temp",
        application_id="app_page",
        operation_id="op-stage-1",
        event_type=EventType.STAGE_UPDATED,
        occurred_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        to_stage=RecruitingStage.INTERVIEW,
        sync_status=SyncStatus.PENDING,
    )

    pending = repo.save_activity_event(event)
    completed = repo.save_activity_event(
        pending.model_copy(update={"sync_status": SyncStatus.COMPLETED})
    )

    assert pending.id == "page_1"
    assert completed.id == "page_1"
    assert len(client.created_pages) == 1
    assert client.updated_pages[0][0] == "page_1"


class FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class RecordingHttpClient:
    def __init__(self, calls: list[dict], responses: list[dict]) -> None:
        self.calls = calls
        self.responses = responses

    def __enter__(self) -> "RecordingHttpClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def request(
        self,
        method: str,
        url: str,
        headers: dict,
        json: dict | None = None,
        params: dict | None = None,
    ):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json, "params": params}
        )
        return FakeHttpResponse(self.responses.pop(0))


def test_notion_client_uses_current_data_source_api(monkeypatch) -> None:
    calls: list[dict] = []
    responses = [
        {"id": "db_1", "data_sources": [{"id": "ds_1"}]},
        {"id": "page_1"},
        {"results": [], "has_more": False},
    ]

    def client_factory(**kwargs):
        assert kwargs == {"trust_env": False, "timeout": 60}
        return RecordingHttpClient(calls, responses)

    import httpx

    monkeypatch.setattr(httpx, "Client", client_factory)
    client = NotionClient("fake-token")

    client.create_database("parent_1", "投递记录", {"公司": {"title": {}}})
    client.create_page("ds_1", {"公司": {"title": []}})
    client.query_database("ds_1")

    assert calls[0]["headers"]["Notion-Version"] == "2026-03-11"
    assert "initial_data_source" in calls[0]["json"]
    assert "properties" not in calls[0]["json"]
    assert calls[1]["json"]["parent"] == {
        "type": "data_source_id",
        "data_source_id": "ds_1",
    }
    assert calls[2]["url"].endswith("/data_sources/ds_1/query")


def test_notion_client_updates_data_source_and_database_titles(monkeypatch) -> None:
    calls: list[dict] = []
    responses = [{"id": "ds_1"}, {"id": "db_1"}]

    def client_factory(**kwargs):
        return RecordingHttpClient(calls, responses)

    import httpx

    monkeypatch.setattr(httpx, "Client", client_factory)
    client = NotionClient("fake-token")

    client.update_data_source_title("ds_1", "投递记录")
    client.update_database_title("db_1", "投递记录")

    assert calls[0]["method"] == "PATCH"
    assert calls[0]["url"].endswith("/data_sources/ds_1")
    assert calls[0]["json"]["title"][0]["text"]["content"] == "投递记录"
    assert calls[1]["method"] == "PATCH"
    assert calls[1]["url"].endswith("/databases/db_1")
    assert calls[1]["json"]["title"][0]["text"]["content"] == "投递记录"


def test_notion_client_manages_views(monkeypatch) -> None:
    calls: list[dict] = []
    responses = [
        {"results": [{"id": "view_1"}], "has_more": False},
        {"id": "view_1", "name": "Default view", "type": "table"},
        {"id": "view_1"},
        {"id": "view_2"},
    ]

    def client_factory(**kwargs):
        return RecordingHttpClient(calls, responses)

    import httpx

    monkeypatch.setattr(httpx, "Client", client_factory)
    client = NotionClient("fake-token")

    listed = client.list_views("db_1")
    view = client.retrieve_view("view_1")
    client.update_view("view_1", {"name": "总览"})
    client.create_view({"name": "完整字段", "database_id": "db_1"})

    assert listed == [{"id": "view_1"}]
    assert view["name"] == "Default view"
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"].endswith("/views")
    assert calls[0]["params"] == {"database_id": "db_1"}
    assert calls[1]["url"].endswith("/views/view_1")
    assert calls[2]["method"] == "PATCH"
    assert calls[2]["json"] == {"name": "总览"}
    assert calls[3]["method"] == "POST"
    assert calls[3]["url"].endswith("/views")


def test_notion_client_creates_child_page_and_linked_database_view(monkeypatch) -> None:
    calls: list[dict] = []
    responses = [
        {"id": "overview_page"},
        {"id": "linked_view"},
        {"results": [], "has_more": False},
    ]

    def client_factory(**kwargs):
        return RecordingHttpClient(calls, responses)

    import httpx

    monkeypatch.setattr(httpx, "Client", client_factory)
    client = NotionClient("fake-token")

    client.create_child_page("parent_1", "秋招总览")
    client.create_linked_database_view(
        parent_page_id="overview_page",
        data_source_id="apps_ds",
        name="投递记录",
        configuration={"type": "table", "properties": []},
    )
    client.list_views(data_source_id="apps_ds")

    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/pages")
    assert calls[0]["json"]["parent"] == {"type": "page_id", "page_id": "parent_1"}
    assert calls[0]["json"]["properties"]["title"][0]["text"]["content"] == "秋招总览"
    assert calls[1]["method"] == "POST"
    assert calls[1]["url"].endswith("/views")
    assert calls[1]["json"]["create_database"]["parent"] == {
        "type": "page_id",
        "page_id": "overview_page",
    }
    assert calls[1]["json"]["data_source_id"] == "apps_ds"
    assert calls[2]["params"] == {"data_source_id": "apps_ds"}


def test_notion_client_manages_block_children(monkeypatch) -> None:
    calls: list[dict] = []
    responses = [
        {"results": [{"id": "block_1"}], "has_more": False},
        {"results": [{"id": "new_block"}]},
        {"id": "block_1", "in_trash": True},
    ]

    def client_factory(**kwargs):
        return RecordingHttpClient(calls, responses)

    import httpx

    monkeypatch.setattr(httpx, "Client", client_factory)
    client = NotionClient("fake-token")

    children = client.list_block_children("page_1")
    client.append_block_children(
        "page_1",
        [{"type": "paragraph", "paragraph": {"rich_text": []}}],
    )
    client.archive_block("block_1")

    assert children == [{"id": "block_1"}]
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"].endswith("/blocks/page_1/children")
    assert calls[1]["method"] == "PATCH"
    assert calls[1]["url"].endswith("/blocks/page_1/children")
    assert calls[1]["json"]["children"][0]["type"] == "paragraph"
    assert calls[2]["method"] == "DELETE"
    assert calls[2]["url"].endswith("/blocks/block_1")
    assert calls[2]["json"] is None


def test_find_database_by_title_filters_matches_to_parent_page(monkeypatch) -> None:
    calls: list[dict] = []
    responses = [
        {
            "results": [
                {
                    "id": "ds_wrong",
                    "title": [{"plain_text": "Applications"}],
                    "parent": {"type": "database_id", "database_id": "db_wrong"},
                },
                {
                    "id": "ds_right",
                    "title": [{"plain_text": "Applications"}],
                    "parent": {"type": "database_id", "database_id": "db_right"},
                },
            ]
        },
        {"parent": {"type": "page_id", "page_id": "other_parent"}},
        {"parent": {"type": "page_id", "page_id": "parent_1"}},
    ]

    def client_factory(**kwargs):
        return RecordingHttpClient(calls, responses)

    import httpx

    monkeypatch.setattr(httpx, "Client", client_factory)
    client = NotionClient("fake-token")

    match = client.find_database_by_title("Applications", parent_page_id="parent_1")

    assert match["id"] == "ds_right"
    assert calls[1]["url"].endswith("/databases/db_wrong")
    assert calls[2]["url"].endswith("/databases/db_right")
