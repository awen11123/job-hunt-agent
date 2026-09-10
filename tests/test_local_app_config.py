import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from job_hunt_agent.local_app import config as config_module
from job_hunt_agent.local_app import paths as paths_module
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore


def test_local_config_round_trip_only_serializes_settings(tmp_path: Path) -> None:
    store = LocalConfigStore(tmp_path / "config.json")
    config = LocalAppConfig(
        excel_path=tmp_path / "applications.xlsx",
        backup_dir=tmp_path / "backups",
        interview_dir=tmp_path / "interviews",
        notion_enabled=True,
        model_enabled=True,
    )

    store.save(config)

    serialized = store.path.read_text(encoding="utf-8")
    assert store.load() == config
    assert set(json.loads(serialized)) == {
        "excel_path",
        "backup_dir",
        "interview_dir",
        "notion_enabled",
        "model_enabled",
    }
    assert all(term not in serialized.lower() for term in ("token", "api_key", "secret"))


def test_save_excludes_sensitive_fields_declared_by_config_subclass(tmp_path: Path) -> None:
    class SensitiveLocalAppConfig(LocalAppConfig):
        token: str
        api_key: str
        secret: str

    store = LocalConfigStore(tmp_path / "config.json")
    config = SensitiveLocalAppConfig(
        backup_dir=tmp_path / "backups",
        interview_dir=tmp_path / "interviews",
        token="not-a-real-token",
        api_key="not-a-real-api-key",
        secret="not-a-real-secret",
    )

    store.save(config)

    serialized = store.path.read_text(encoding="utf-8")
    assert set(json.loads(serialized)) == set(LocalAppConfig.model_fields)
    assert all(term not in serialized.lower() for term in ("token", "api_key", "secret"))


def test_local_config_rejects_extra_fields(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        LocalAppConfig(
            backup_dir=tmp_path / "backups",
            interview_dir=tmp_path / "interviews",
            token="not-a-real-token",
        )


def test_defaults_are_below_supplied_app_data_root(tmp_path: Path) -> None:
    config = LocalAppConfig.defaults(tmp_path)

    assert config.excel_path is None
    assert config.backup_dir == tmp_path / "backups"
    assert config.interview_dir == tmp_path / "interviews"
    assert config.notion_enabled is False
    assert config.model_enabled is False


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    store = LocalConfigStore(tmp_path / "nested" / "config.json")

    store.save(LocalAppConfig.defaults(tmp_path))

    assert store.path.is_file()


def test_load_missing_file_returns_defaults_next_to_config(tmp_path: Path) -> None:
    store = LocalConfigStore(tmp_path / "settings" / "config.json")

    assert store.load() == LocalAppConfig.defaults(store.path.parent)


def test_app_data_root_prefers_appdata_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appdata = tmp_path / "roaming"
    monkeypatch.setattr(paths_module.sys, "platform", "win32")

    result = paths_module.app_data_root(
        env={"APPDATA": str(appdata)},
        home=tmp_path / "home",
    )

    assert result == appdata / "JobHuntAgent"


def test_app_data_root_uses_supplied_home_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(paths_module.sys, "platform", "linux")

    result = paths_module.app_data_root(
        env={"APPDATA": str(tmp_path / "ignored")},
        home=home,
    )

    assert result == home / ".local" / "share" / "job-hunt-agent"


def test_failed_atomic_replace_keeps_original_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalConfigStore(tmp_path / "config.json")
    original = LocalAppConfig.defaults(tmp_path / "original")
    replacement = LocalAppConfig.defaults(tmp_path / "replacement")
    store.save(original)
    replacement_sources: list[Path] = []

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        replacement_sources.append(Path(source))
        assert Path(destination) == store.path
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(config_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replacement failure"):
        store.save(replacement)

    assert store.load() == original
    assert len(replacement_sources) == 1
    assert replacement_sources[0].parent == store.path.parent
    assert not replacement_sources[0].exists()
    assert list(tmp_path.iterdir()) == [store.path]


def test_validation_failure_keeps_original_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalConfigStore(tmp_path / "config.json")
    original = LocalAppConfig.defaults(tmp_path / "original")
    replacement = LocalAppConfig.defaults(tmp_path / "replacement")
    store.save(original)
    original_json = store.path.read_text(encoding="utf-8")

    def reject_serialized_data(cls: type[LocalAppConfig], data: str) -> LocalAppConfig:
        raise ValueError("simulated validation failure")

    monkeypatch.setattr(
        LocalAppConfig,
        "model_validate_json",
        classmethod(reject_serialized_data),
    )

    with pytest.raises(ValueError, match="simulated validation failure"):
        store.save(replacement)

    assert store.path.read_text(encoding="utf-8") == original_json
    assert list(tmp_path.iterdir()) == [store.path]
