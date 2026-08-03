from datetime import datetime, timezone

from job_hunt_agent.domain.models import ActivityEvent, ApplicationDraft, ApplicationRecord
from job_hunt_agent.domain.statuses import EventType, RecruitingStage, SyncStatus
from job_hunt_agent.notion.bootstrap import NotionBootstrapper
from job_hunt_agent.notion.client import NotionClient
from job_hunt_agent.repositories import NotionDatabaseIds, NotionJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService


class FakeNotionClient:
    def __init__(self) -> None:
        self.created_databases: list[dict] = []
        self.created_pages: list[dict] = []
        self.updated_pages: list[tuple[str, dict]] = []
        self.updated_data_source_titles: list[tuple[str, str]] = []
        self.updated_database_titles: list[tuple[str, str]] = []
        self.updated_views: list[tuple[str, dict]] = []
        self.created_views: list[dict] = []
        self.queried_databases: list[tuple[str, dict | None]] = []
        self.search_results: dict[str, dict] = {}
        self.views_by_database: dict[str, list[dict]] = {}

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

    def query_database(self, database_id: str, filter_payload: dict | None = None) -> list[dict]:
        self.queried_databases.append((database_id, filter_payload))
        return []

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

    def list_views(self, database_id: str) -> list[dict]:
        return self.views_by_database.get(database_id, [])

    def retrieve_view(self, view_id: str) -> dict:
        for views in self.views_by_database.values():
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
