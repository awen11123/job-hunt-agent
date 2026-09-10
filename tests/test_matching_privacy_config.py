from job_hunt_agent.config import Settings
import job_hunt_agent.config as config_module
from job_hunt_agent.matching import application_key, normalize_text
from job_hunt_agent.privacy import scan_text_for_private_leaks


def test_application_key_normalizes_company_role_and_season() -> None:
    assert application_key(" DeepSeek ", "LLM Application Engineer", "2026 Autumn") == (
        "deepseek",
        "llm application engineer",
        "2026 autumn",
    )


def test_normalize_text_collapses_internal_whitespace() -> None:
    assert normalize_text("AI   Agent\tEngineer") == "ai agent engineer"


def test_privacy_scan_detects_notion_urls_and_api_keys() -> None:
    text = (
        "Notion: https://www.notion" + ".so/private-page "
        "and key " + "sk-" + "abc123456789SECRET"
    )

    findings = scan_text_for_private_leaks(text)

    assert {finding.kind for finding in findings} == {"notion_url", "api_key"}


def test_privacy_scan_does_not_treat_empty_env_example_as_secret() -> None:
    text = "\n".join(
        [
            "NOTION_TOKEN" + "=",
            "NOTION_APPLICATIONS_DB_ID=",
            "DEEPSEEK_API_KEY" + "=",
            "DEEPSEEK_BASE_URL=https://api.deepseek.com",
        ]
    )

    assert scan_text_for_private_leaks(text) == []


def test_settings_reads_env_without_requiring_real_secrets(monkeypatch) -> None:
    for name in [
        "NOTION_TOKEN",
        "NOTION_PARENT_PAGE_ID",
        "NOTION_APPLICATIONS_DB_ID",
        "NOTION_ACTIVITY_DB_ID",
        "NOTION_INTERVIEWS_DB_ID",
        "NOTION_REVIEW_TASKS_DB_ID",
        "DEEPSEEK_API_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEFAULT_RECRUITING_SEASON", "2026-autumn")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setattr(config_module, "winreg_user_environment_value", lambda name: None)
    monkeypatch.setattr(config_module, "powershell_user_environment_value", lambda name: None)

    settings = Settings.from_env()

    assert settings.default_recruiting_season == "2026-autumn"
    assert settings.deepseek_model == "deepseek-chat"
    assert settings.notion_token is None


def test_env_value_falls_back_to_powershell_user_environment(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_TEST_NOTION_TOKEN", raising=False)
    monkeypatch.setattr(config_module.os, "name", "nt")
    monkeypatch.setattr(config_module, "winreg_user_environment_value", lambda name: None)
    monkeypatch.setattr(
        config_module,
        "powershell_user_environment_value",
        lambda name: "from-user-target" if name == "CODEX_TEST_NOTION_TOKEN" else None,
    )

    assert config_module.env_value("CODEX_TEST_NOTION_TOKEN") == "from-user-target"
