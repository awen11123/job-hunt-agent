from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from job_hunt_agent.actions import ActionDraftService
from job_hunt_agent.excel import (
    ExcelApplicationRepository,
    TrackerApplication,
    TrackerApplicationDraft,
    TrackerApplicationPatch,
)
from job_hunt_agent.interviews import (
    LocalInterviewDraft,
    LocalInterviewRecord,
    LocalInterviewStore,
)
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore


class LocalResourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _configured_excel_repository(config: LocalAppConfig) -> ExcelApplicationRepository:
    if config.excel_path is None:
        raise LocalResourceError("excel_not_configured", "尚未配置 Excel 投递表。")
    if not config.excel_path.is_file():
        raise LocalResourceError("excel_unavailable", "Excel 投递表暂时不可用。")
    return ExcelApplicationRepository(config.excel_path, config.backup_dir)


class _DynamicExcelRepository:
    def __init__(self, config_store: LocalConfigStore) -> None:
        self._config_store = config_store

    def create_application(self, draft: TrackerApplicationDraft) -> TrackerApplication:
        repository = _configured_excel_repository(self._config_store.load())
        return repository.create_application(draft)

    def update_application(
        self,
        application_id: str,
        patch: TrackerApplicationPatch,
    ) -> TrackerApplication:
        repository = _configured_excel_repository(self._config_store.load())
        return repository.update_application(application_id, patch)


class _DynamicInterviewStore:
    def __init__(self, config_store: LocalConfigStore) -> None:
        self._config_store = config_store

    def save(
        self,
        draft: LocalInterviewDraft,
        operation_id: str,
    ) -> LocalInterviewRecord:
        config = self._config_store.load()
        return LocalInterviewStore(config.interview_dir).save(draft, operation_id)


@dataclass(frozen=True)
class WebServices:
    config_store: LocalConfigStore
    action_service: ActionDraftService

    def load_config(self) -> LocalAppConfig:
        return self.config_store.load()

    def save_config(self, config: LocalAppConfig) -> LocalAppConfig:
        self.config_store.save(config)
        return self.config_store.load()

    def excel_repository(self) -> ExcelApplicationRepository:
        return _configured_excel_repository(self.load_config())

    def interview_store(self) -> LocalInterviewStore:
        return LocalInterviewStore(self.load_config().interview_dir)


def build_services(config_store: LocalConfigStore) -> WebServices:
    action_service = ActionDraftService(
        _DynamicExcelRepository(config_store),
        _DynamicInterviewStore(config_store),
    )
    return WebServices(config_store=config_store, action_service=action_service)


def require_session(
    request: Request,
    supplied_token: Annotated[
        str | None,
        Header(alias="X-Job-Hunt-Session"),
    ] = None,
) -> None:
    if supplied_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "session_required", "message": "缺少本机会话凭证。"},
        )
    expected_token = request.app.state.session_token
    try:
        matches = secrets.compare_digest(expected_token, supplied_token)
    except TypeError:
        matches = False
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "invalid_session", "message": "本机会话凭证无效。"},
        )
