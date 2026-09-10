from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from job_hunt_agent.ai import ActionPlan, LLMProviderError
from job_hunt_agent.interviews import LocalInterviewDraft, LocalInterviewStore
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.web import create_app


SESSION_TOKEN = "test-session"


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, reference: str, value: str) -> None:
        self.values[reference] = value

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class SuccessfulProvider:
    provider_name = "deepseek"
    model_name = "deepseek-chat"

    def __init__(self, plan: ActionPlan | None = None) -> None:
        self.plan = plan

    def complete_structured(self, messages, response_model):
        if response_model is ActionPlan:
            assert self.plan is not None
            return self.plan
        return response_model(ok=True)


class FailingProvider:
    provider_name = "deepseek"
    model_name = "deepseek-chat"

    def complete_structured(self, messages, response_model):
        raise LLMProviderError("Model request timed out.")


class RecordingProviderFactory:
    def __init__(self, provider=None) -> None:
        self.provider = provider or SuccessfulProvider()
        self.configs = []

    def __call__(self, config):
        self.configs.append(config)
        return self.provider


class RecordingNotionClient:
    def __init__(self) -> None:
        self.probed: list[str] = []
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, dict]] = []
        self.appended: list[tuple[str, list[dict]]] = []

    def retrieve_data_source(self, database_id: str) -> dict:
        self.probed.append(database_id)
        return {"id": database_id}

    def create_page(self, database_id: str, properties: dict) -> dict:
        self.created.append((database_id, properties))
        return {"id": "notion-page"}

    def update_page(self, page_id: str, properties: dict) -> dict:
        self.updated.append((page_id, properties))
        return {"id": page_id}

    def append_block_children(self, page_id: str, children: list[dict]) -> dict:
        self.appended.append((page_id, children))
        return {"results": children}


def make_client(
    tmp_path: Path,
    *,
    provider_factory: RecordingProviderFactory | None = None,
    notion_client: RecordingNotionClient | None = None,
) -> tuple[TestClient, LocalConfigStore, FakeSecretStore, RecordingProviderFactory, RecordingNotionClient]:
    config_store = LocalConfigStore(tmp_path / "config.json")
    config_store.save(LocalAppConfig.defaults(tmp_path / "app-data"))
    secrets = FakeSecretStore()
    models = provider_factory or RecordingProviderFactory()
    notion = notion_client or RecordingNotionClient()
    client = TestClient(
        create_app(
            config_store,
            session_token=SESSION_TOKEN,
            secret_store=secrets,
            provider_factory=models,
            notion_client_factory=lambda _token: notion,
        ),
        base_url="http://localhost",
    )
    return client, config_store, secrets, models, notion


def headers() -> dict[str, str]:
    return {"X-Job-Hunt-Session": SESSION_TOKEN}


def test_settings_response_and_config_never_return_model_secret(tmp_path: Path) -> None:
    client, config_store, secrets, _, _ = make_client(tmp_path)
    private_value = "private-model-value"

    saved = client.put(
        "/api/settings/model",
        headers=headers(),
        json={
            "enabled": True,
            "provider": "deepseek",
            "api_key": private_value,
        },
    )
    response = client.get("/api/settings")

    assert saved.status_code == 200
    assert response.status_code == 200
    assert response.json()["model"]["credential_configured"] is True
    assert "api_key" not in response.json()["model"]
    assert private_value not in response.text
    assert private_value not in config_store.path.read_text(encoding="utf-8")
    assert secrets.values == {"model:deepseek:default": private_value}
    assert "model_credential_ref" not in client.get("/api/config").text


def test_model_test_reports_structured_output_capability(tmp_path: Path) -> None:
    client, _, _, _, _ = make_client(tmp_path)
    client.put(
        "/api/settings/model",
        headers=headers(),
        json={"enabled": True, "provider": "deepseek", "api_key": "private-value"},
    )

    response = client.post("/api/settings/model/test", headers=headers())

    assert response.status_code == 200
    assert response.json() == {"status": "connected", "structured_output": True}


def test_ollama_model_test_does_not_require_a_key(tmp_path: Path) -> None:
    client, _, _, models, _ = make_client(tmp_path)
    saved = client.put(
        "/api/settings/model",
        headers=headers(),
        json={"enabled": True, "provider": "ollama", "model": "qwen3:8b"},
    )

    response = client.post("/api/settings/model/test", headers=headers())

    assert saved.status_code == 200
    assert response.status_code == 200
    assert models.configs[-1].api_key is None


def test_model_timeout_returns_stable_error(tmp_path: Path) -> None:
    factory = RecordingProviderFactory(FailingProvider())
    client, _, _, _, _ = make_client(tmp_path, provider_factory=factory)
    client.put(
        "/api/settings/model",
        headers=headers(),
        json={"enabled": True, "provider": "deepseek", "api_key": "private-value"},
    )

    response = client.post("/api/settings/model/test", headers=headers())

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "model_unavailable",
        "message": "模型服务暂时不可用。",
    }
    assert "timed out" not in response.text


def test_enabled_model_can_only_return_a_pending_action_draft(tmp_path: Path) -> None:
    provider = SuccessfulProvider(
        ActionPlan(
            action="create_application",
            arguments={"company": "示例科技", "role": "Agent 工程师"},
            disclosure=["application_metadata"],
        )
    )
    client, _, _, _, _ = make_client(
        tmp_path,
        provider_factory=RecordingProviderFactory(provider),
    )
    client.put(
        "/api/settings/model",
        headers=headers(),
        json={"enabled": True, "provider": "deepseek", "api_key": "private-value"},
    )

    response = client.post("/api/actions/propose", json={"text": "记录这条投递"})

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["action"] == "create_application"
    assert response.json()["disclosure"] == ["application_metadata"]


def test_notion_settings_test_exposes_only_connection_state(tmp_path: Path) -> None:
    client, config_store, secrets, _, notion = make_client(tmp_path)
    private_token = "private-notion-value"
    saved = client.put(
        "/api/settings/notion",
        headers=headers(),
        json={
            "enabled": True,
            "token": private_token,
            "interviews_database_id": "interviews-database",
        },
    )

    tested = client.post("/api/settings/notion/test", headers=headers())
    settings = client.get("/api/settings")

    assert saved.status_code == 200
    assert tested.json() == {"status": "connected"}
    assert notion.probed == ["interviews-database"]
    assert settings.json()["notion"] == {
        "enabled": True,
        "credential_configured": True,
        "database_configured": True,
    }
    assert private_token not in settings.text
    assert private_token not in config_store.path.read_text(encoding="utf-8")
    assert secrets.values["notion:default"] == private_token


def test_interview_sync_endpoint_is_guarded_and_retry_is_idempotent(tmp_path: Path) -> None:
    client, config_store, _, _, notion = make_client(tmp_path)
    client.put(
        "/api/settings/notion",
        headers=headers(),
        json={
            "enabled": True,
            "token": "private-notion-value",
            "interviews_database_id": "interviews-database",
        },
    )
    config = config_store.load()
    record = LocalInterviewStore(config.interview_dir).save(
        LocalInterviewDraft(
            application_id="app-1",
            company="示例科技",
            round_name="技术一面",
            raw_notes="讨论了 Agent 评测。",
            scheduled_at=datetime(2026, 9, 11, tzinfo=UTC),
        ),
        operation_id="interview-operation",
    )

    assert client.post(f"/api/interviews/{record.id}/sync").status_code == 401
    first = client.post(f"/api/interviews/{record.id}/sync", headers=headers())
    second = client.post(f"/api/interviews/{record.id}/sync", headers=headers())

    assert first.status_code == 200
    assert first.json()["sync_status"] == "synced"
    assert second.status_code == 200
    assert len(notion.created) == 1
