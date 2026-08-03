from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    notion_token: str | None
    notion_parent_page_id: str | None
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
            notion_token=env_value("NOTION_TOKEN"),
            notion_parent_page_id=env_value("NOTION_PARENT_PAGE_ID"),
            notion_applications_db_id=env_value("NOTION_APPLICATIONS_DB_ID"),
            notion_activity_db_id=env_value("NOTION_ACTIVITY_DB_ID"),
            notion_interviews_db_id=env_value("NOTION_INTERVIEWS_DB_ID"),
            notion_review_tasks_db_id=env_value("NOTION_REVIEW_TASKS_DB_ID"),
            deepseek_api_key=env_value("DEEPSEEK_API_KEY"),
            deepseek_base_url=env_value("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
            deepseek_model=env_value("DEEPSEEK_MODEL") or "deepseek-chat",
            default_recruiting_season=env_value("DEFAULT_RECRUITING_SEASON"),
        )


def env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    if os.name != "nt":
        return None
    return winreg_user_environment_value(name) or powershell_user_environment_value(name)


def winreg_user_environment_value(name: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            registry_value, _ = winreg.QueryValueEx(key, name)
            return registry_value or None
    except OSError:
        return None


def powershell_user_environment_value(name: str) -> str | None:
    try:
        import subprocess

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$name = $args[0]; [Environment]::GetEnvironmentVariable($name, 'User')",
                name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None
