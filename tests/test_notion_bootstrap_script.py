from scripts import notion_bootstrap
from scripts.notion_bootstrap import bootstrap_and_store


class FakeBootstrapper:
    def bootstrap(self, parent_page_id: str):
        assert parent_page_id == "parent_1"
        return {
            "NOTION_APPLICATIONS_DB_ID": "apps_db",
            "NOTION_ACTIVITY_DB_ID": "activity_db",
            "NOTION_INTERVIEWS_DB_ID": "interviews_db",
            "NOTION_REVIEW_TASKS_DB_ID": "review_tasks_db",
        }


def test_bootstrap_and_store_writes_database_ids_without_exposing_token() -> None:
    written: dict[str, str] = {}

    result = bootstrap_and_store(
        parent_page_id="parent_1",
        bootstrapper=FakeBootstrapper(),
        set_env=written.__setitem__,
    )

    assert result == [
        "NOTION_APPLICATIONS_DB_ID",
        "NOTION_ACTIVITY_DB_ID",
        "NOTION_INTERVIEWS_DB_ID",
        "NOTION_REVIEW_TASKS_DB_ID",
    ]
    assert written["NOTION_APPLICATIONS_DB_ID"] == "apps_db"


class FullyConfiguredSettings:
    notion_token = None
    notion_parent_page_id = None
    notion_applications_db_id = "apps_db"
    notion_activity_db_id = "activity_db"
    notion_interviews_db_id = "interviews_db"
    notion_review_tasks_db_id = "review_tasks_db"


def test_main_reports_already_configured_before_requiring_token(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        notion_bootstrap.Settings,
        "from_env",
        staticmethod(lambda: FullyConfiguredSettings()),
    )

    assert notion_bootstrap.main() == 0
    assert capsys.readouterr().out.strip() == "notion_databases=already_configured"


class FullyConfiguredSettingsWithToken(FullyConfiguredSettings):
    notion_token = "fake-token"


class RecordingBootstrapper:
    renamed_ids = None
    configured_view_ids = None
    overview_args = None
    text_overview_page_args = None
    refreshed_text_args = None

    def __init__(self, client) -> None:
        self.client = client

    def rename_configured_databases(self, database_ids) -> None:
        RecordingBootstrapper.renamed_ids = database_ids

    def configure_readable_views(self, database_ids) -> None:
        RecordingBootstrapper.configured_view_ids = database_ids

    def ensure_overview_page(self, parent_page_id, database_ids) -> str:
        RecordingBootstrapper.overview_args = (parent_page_id, database_ids)
        return "overview_page"

    def ensure_text_first_overview_page(self, parent_page_id) -> str:
        RecordingBootstrapper.text_overview_page_args = parent_page_id
        return "text_overview_page"

    def refresh_text_overview(self, overview_page_id, overview_text) -> None:
        RecordingBootstrapper.refreshed_text_args = (overview_page_id, overview_text)


class RecordingRepository:
    loaded = False

    def __init__(self, token, database_ids, client) -> None:
        self.token = token
        self.database_ids = database_ids
        self.client = client

    def load_all(self) -> None:
        RecordingRepository.loaded = True


class RecordingReportingService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def generate_text_overview(self, today) -> str:
        return f"# 秋招总览｜{today.isoformat()}"


def test_main_localizes_configured_database_titles_when_token_is_available(
    monkeypatch,
    capsys,
) -> None:
    RecordingBootstrapper.renamed_ids = None
    RecordingBootstrapper.configured_view_ids = None
    RecordingBootstrapper.overview_args = None
    RecordingBootstrapper.text_overview_page_args = None
    RecordingBootstrapper.refreshed_text_args = None
    monkeypatch.setattr(
        notion_bootstrap.Settings,
        "from_env",
        staticmethod(lambda: FullyConfiguredSettingsWithToken()),
    )
    monkeypatch.setattr(notion_bootstrap, "NotionClient", lambda token: object())
    monkeypatch.setattr(notion_bootstrap, "NotionBootstrapper", RecordingBootstrapper)

    assert notion_bootstrap.main() == 0

    assert RecordingBootstrapper.renamed_ids.applications == "apps_db"
    assert RecordingBootstrapper.configured_view_ids.applications == "apps_db"
    assert RecordingBootstrapper.overview_args is None
    assert capsys.readouterr().out.strip().splitlines() == [
        "notion_database_titles=localized",
        "notion_views=configured",
        "notion_databases=already_configured",
    ]


class FullyConfiguredSettingsWithTokenAndParent(FullyConfiguredSettingsWithToken):
    notion_parent_page_id = "parent_1"


def test_main_configures_overview_page_when_parent_page_is_available(
    monkeypatch,
    capsys,
) -> None:
    RecordingBootstrapper.renamed_ids = None
    RecordingBootstrapper.configured_view_ids = None
    RecordingBootstrapper.overview_args = None
    RecordingBootstrapper.text_overview_page_args = None
    RecordingBootstrapper.refreshed_text_args = None
    RecordingRepository.loaded = False
    monkeypatch.setattr(
        notion_bootstrap.Settings,
        "from_env",
        staticmethod(lambda: FullyConfiguredSettingsWithTokenAndParent()),
    )
    monkeypatch.setattr(notion_bootstrap, "NotionClient", lambda token: object())
    monkeypatch.setattr(notion_bootstrap, "NotionBootstrapper", RecordingBootstrapper)
    monkeypatch.setattr(notion_bootstrap, "NotionJobHuntRepository", RecordingRepository)
    monkeypatch.setattr(notion_bootstrap, "ReportingService", RecordingReportingService)

    assert notion_bootstrap.main() == 0

    assert RecordingBootstrapper.overview_args is None
    assert RecordingBootstrapper.text_overview_page_args == "parent_1"
    overview_page_id, overview_text = RecordingBootstrapper.refreshed_text_args
    assert overview_page_id == "text_overview_page"
    assert overview_text.startswith("# 秋招总览")
    assert RecordingRepository.loaded is True
    assert capsys.readouterr().out.strip().splitlines() == [
        "notion_database_titles=localized",
        "notion_views=configured",
        "notion_text_overview=configured",
        "notion_databases=already_configured",
    ]
