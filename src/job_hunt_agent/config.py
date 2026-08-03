from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    notion_token: str | None
    notion_applications_db_id: str | None
    notion_activity_db_id: str | None
    notion_interviews_db_id: str | None
    notion_review_tasks_db_id: str | None
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str
    default_recruiting_season: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            notion_token=os.getenv("NOTION_TOKEN") or None,
            notion_applications_db_id=os.getenv("NOTION_APPLICATIONS_DB_ID") or None,
            notion_activity_db_id=os.getenv("NOTION_ACTIVITY_DB_ID") or None,
            notion_interviews_db_id=os.getenv("NOTION_INTERVIEWS_DB_ID") or None,
            notion_review_tasks_db_id=os.getenv("NOTION_REVIEW_TASKS_DB_ID") or None,
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            default_recruiting_season=os.getenv("DEFAULT_RECRUITING_SEASON") or None,
        )
