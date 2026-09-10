from __future__ import annotations

import json
from pathlib import Path

from job_hunt_agent.ai.presets import provider_presets
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.local_app.secrets import SecretStore


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_secret_store_round_trip_uses_injected_keyring_backend() -> None:
    backend = FakeKeyring()
    store = SecretStore(backend=backend, service_name="JobHuntAgent")

    store.set("deepseek:default", "secret-value")

    assert store.get("deepseek:default") == "secret-value"
    assert backend.values == {("JobHuntAgent", "deepseek:default"): "secret-value"}


def test_secret_store_delete_removes_only_the_named_credential() -> None:
    backend = FakeKeyring()
    store = SecretStore(backend=backend)
    store.set("deepseek:default", "first-value")
    store.set("notion:default", "second-value")

    store.delete("deepseek:default")

    assert store.get("deepseek:default") is None
    assert store.get("notion:default") == "second-value"


def test_presets_are_openai_compatible_and_do_not_embed_keys() -> None:
    presets = provider_presets()

    assert set(presets) == {
        "deepseek",
        "qwen",
        "moonshot",
        "openai-compatible",
        "ollama",
    }
    assert str(presets["deepseek"].base_url).rstrip("/") == "https://api.deepseek.com"
    assert presets["qwen"].base_url.host == "dashscope.aliyuncs.com"
    assert presets["ollama"].requires_api_key is False
    assert all(preset.api_key is None for preset in presets.values())


def test_local_config_serializes_only_a_credential_reference(tmp_path: Path) -> None:
    store = LocalConfigStore(tmp_path / "config.json")
    config = LocalAppConfig.defaults(tmp_path).model_copy(
        update={
            "model_enabled": True,
            "model_provider": "deepseek",
            "model_name": "deepseek-chat",
            "model_credential_ref": "deepseek:default",
        }
    )

    store.save(config)

    serialized = store.path.read_text(encoding="utf-8")
    payload = json.loads(serialized)
    assert payload["model_credential_ref"] == "deepseek:default"
    assert "secret-value" not in serialized
    assert "api_key" not in serialized.lower()
