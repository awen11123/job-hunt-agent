from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.web import create_app
from job_hunt_agent.web.schemas import ModelSettingsRequest, NotionSettingsRequest

SESSION_TOKEN = "privacy-test-session"
MODEL_CREDENTIAL = "MODEL_CREDENTIAL_SENTINEL_42"
NOTION_CREDENTIAL = "NOTION_CREDENTIAL_SENTINEL_42"


class RecordingSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, reference: str, value: str) -> None:
        self.values[reference] = value

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


def test_integration_request_representations_hide_credentials() -> None:
    model_request = ModelSettingsRequest(
        enabled=True,
        provider="deepseek",
        api_key=MODEL_CREDENTIAL,
    )
    notion_request = NotionSettingsRequest(
        enabled=True,
        token=NOTION_CREDENTIAL,
        interviews_database_id="synthetic-database-id",
    )

    assert MODEL_CREDENTIAL not in repr(model_request)
    assert NOTION_CREDENTIAL not in repr(notion_request)
    assert "synthetic-database-id" not in repr(notion_request)


def test_credentials_stay_out_of_local_artifacts_api_responses_and_logs(
    tmp_path: Path,
    caplog,
) -> None:
    config_store = LocalConfigStore(tmp_path / "config.json")
    config_store.save(LocalAppConfig.defaults(tmp_path / "app-data"))
    secrets = RecordingSecretStore()
    client = TestClient(
        create_app(
            config_store,
            session_token=SESSION_TOKEN,
            secret_store=secrets,
        ),
        base_url="http://localhost",
    )
    headers = {"X-Job-Hunt-Session": SESSION_TOKEN}

    model_response = client.put(
        "/api/settings/model",
        headers=headers,
        json={
            "enabled": True,
            "provider": "deepseek",
            "api_key": MODEL_CREDENTIAL,
        },
    )
    notion_response = client.put(
        "/api/settings/notion",
        headers=headers,
        json={
            "enabled": True,
            "token": NOTION_CREDENTIAL,
            "interviews_database_id": "synthetic-database-id",
        },
    )
    settings_response = client.get("/api/settings")
    config_response = client.get("/api/config")

    draft = client.app.state.services.action_service.propose(
        "save_interview",
        {
            "application_id": "synthetic-application",
            "company": "示例科技",
            "round_name": "技术一面",
            "raw_notes": "讨论了 Agent 状态管理和评测。",
        },
        operation_id="privacy-boundary-interview",
    )
    execution_response = client.post(
        f"/api/actions/{draft.id}/confirm",
        headers=headers,
        json={"confirmation_token": draft.confirmation_token},
    )

    assert model_response.status_code == 200
    assert notion_response.status_code == 200
    assert settings_response.status_code == 200
    assert config_response.status_code == 200
    assert execution_response.status_code == 200
    assert secrets.values == {
        "model:deepseek:default": MODEL_CREDENTIAL,
        "notion:default": NOTION_CREDENTIAL,
    }

    api_output = "\n".join(
        response.text
        for response in (
            model_response,
            notion_response,
            settings_response,
            config_response,
            execution_response,
        )
    )
    config_json = config_store.path.read_text(encoding="utf-8")
    interview_files = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((tmp_path / "app-data" / "interviews").glob("*"))
        if path.is_file()
    )

    for credential in (MODEL_CREDENTIAL, NOTION_CREDENTIAL):
        assert credential not in api_output
        assert credential not in config_json
        assert credential not in interview_files
        assert credential not in caplog.text
