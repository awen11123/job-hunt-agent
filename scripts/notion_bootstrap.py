from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_hunt_agent.config import Settings  # noqa: E402
from job_hunt_agent.notion.bootstrap import (  # noqa: E402
    BootstrappedDatabases,
    NotionBootstrapper,
    set_user_environment_value,
)
from job_hunt_agent.notion.client import NotionClient  # noqa: E402
from job_hunt_agent.repositories import NotionDatabaseIds, NotionJobHuntRepository  # noqa: E402
from job_hunt_agent.services.reporting import ReportingService  # noqa: E402


DATABASE_ENV_NAMES = [
    "NOTION_APPLICATIONS_DB_ID",
    "NOTION_ACTIVITY_DB_ID",
    "NOTION_INTERVIEWS_DB_ID",
    "NOTION_REVIEW_TASKS_DB_ID",
]


def bootstrap_and_store(parent_page_id: str, bootstrapper, set_env) -> list[str]:
    ids = bootstrapper.bootstrap(parent_page_id)
    values = ids if isinstance(ids, dict) else {
        "NOTION_APPLICATIONS_DB_ID": ids.applications,
        "NOTION_ACTIVITY_DB_ID": ids.activity,
        "NOTION_INTERVIEWS_DB_ID": ids.interviews,
        "NOTION_REVIEW_TASKS_DB_ID": ids.review_tasks,
    }
    for name in DATABASE_ENV_NAMES:
        set_env(name, values[name])
    return DATABASE_ENV_NAMES


def has_database_configuration(settings: Settings) -> bool:
    return all(
        [
            settings.notion_applications_db_id,
            settings.notion_activity_db_id,
            settings.notion_interviews_db_id,
            settings.notion_review_tasks_db_id,
        ]
    )


def configured_database_ids(settings: Settings) -> BootstrappedDatabases:
    return BootstrappedDatabases(
        applications=settings.notion_applications_db_id or "",
        activity=settings.notion_activity_db_id or "",
        interviews=settings.notion_interviews_db_id or "",
        review_tasks=settings.notion_review_tasks_db_id or "",
    )


def configured_repository_ids(settings: Settings) -> NotionDatabaseIds:
    return NotionDatabaseIds(
        applications=settings.notion_applications_db_id or "",
        activity=settings.notion_activity_db_id or "",
        interviews=settings.notion_interviews_db_id or "",
        review_tasks=settings.notion_review_tasks_db_id or "",
    )


def main() -> int:
    settings = Settings.from_env()
    if has_database_configuration(settings):
        if settings.notion_token:
            client = NotionClient(settings.notion_token)
            bootstrapper = NotionBootstrapper(client)
            database_ids = configured_database_ids(settings)
            bootstrapper.rename_configured_databases(database_ids)
            print("notion_database_titles=localized")
            bootstrapper.configure_readable_views(database_ids)
            print("notion_views=configured")
            if settings.notion_parent_page_id:
                repository = NotionJobHuntRepository(
                    token=settings.notion_token,
                    database_ids=configured_repository_ids(settings),
                    client=client,
                )
                repository.load_all()
                reporting = ReportingService(repository)
                overview_page_id = bootstrapper.ensure_text_first_overview_page(
                    settings.notion_parent_page_id
                )
                bootstrapper.refresh_text_overview(
                    overview_page_id,
                    reporting.generate_text_overview(date.today()),
                )
                print("notion_text_overview=configured")
        print("notion_databases=already_configured")
        return 0

    if not settings.notion_token:
        print("NOTION_TOKEN is not configured.")
        return 1
    if not settings.notion_parent_page_id:
        print("NOTION_PARENT_PAGE_ID is not configured.")
        return 1

    client = NotionClient(settings.notion_token)
    bootstrapper = NotionBootstrapper(client)
    written = bootstrap_and_store(
        settings.notion_parent_page_id,
        bootstrapper,
        set_user_environment_value,
    )
    for name in written:
        print(f"{name}=set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
