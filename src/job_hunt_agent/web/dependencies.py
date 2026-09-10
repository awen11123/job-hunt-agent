from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Header, HTTPException, Request, status

from job_hunt_agent.actions import ActionDraftService
from job_hunt_agent.ai import LLMProvider, OpenAICompatibleProvider, ProviderConfig
from job_hunt_agent.ai.action_planner import LLMActionPlanner
from job_hunt_agent.ai.presets import provider_presets
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
    InterviewSyncService,
    NotionInterviewTarget,
)
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.local_app.secrets import SecretStore
from job_hunt_agent.notion import NotionClient


ProviderFactory = Callable[[ProviderConfig], LLMProvider]
NotionClientFactory = Callable[[str], NotionClient]


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
    secret_store: SecretStore
    provider_factory: ProviderFactory
    notion_client_factory: NotionClientFactory

    def load_config(self) -> LocalAppConfig:
        return self.config_store.load()

    def save_config(self, config: LocalAppConfig) -> LocalAppConfig:
        self.config_store.save(config)
        return self.config_store.load()

    def excel_repository(self) -> ExcelApplicationRepository:
        return _configured_excel_repository(self.load_config())

    def interview_store(self) -> LocalInterviewStore:
        return LocalInterviewStore(self.load_config().interview_dir)

    def model_provider(self) -> LLMProvider:
        config = self.load_config()
        preset = provider_presets()[config.model_provider]
        api_key = None
        if preset.requires_api_key:
            if config.model_credential_ref is None:
                raise LocalResourceError("model_not_configured", "模型密钥尚未配置。")
            api_key = self.secret_store.get(config.model_credential_ref)
            if api_key is None:
                raise LocalResourceError("model_not_configured", "模型密钥尚未配置。")
        provider_config = ProviderConfig(
            name=config.model_provider,
            base_url=config.model_base_url or preset.base_url,
            model=config.model_name or preset.model,
            api_key=api_key,
            supports_json_mode=preset.supports_json_mode,
        )
        return self.provider_factory(provider_config)

    def action_planner(self) -> LLMActionPlanner:
        config = self.load_config()
        provider = self.model_provider() if config.model_enabled else None
        return LLMActionPlanner(
            provider,
            self.action_service,
            read_handlers={
                "query_applications": self._query_applications,
                "generate_review": self._generate_review,
            },
        )

    def notion_client(self) -> tuple[NotionClient, str]:
        config = self.load_config()
        if not config.notion_enabled:
            raise LocalResourceError("notion_not_configured", "Notion 尚未启用。")
        if config.notion_credential_ref is None:
            raise LocalResourceError("notion_not_configured", "Notion 密钥尚未配置。")
        token = self.secret_store.get(config.notion_credential_ref)
        if token is None:
            raise LocalResourceError("notion_not_configured", "Notion 密钥尚未配置。")
        if config.notion_interviews_database_id is None:
            raise LocalResourceError("notion_not_configured", "Notion 面经库尚未配置。")
        return self.notion_client_factory(token), config.notion_interviews_database_id

    def interview_sync_service(self) -> InterviewSyncService:
        client, database_id = self.notion_client()
        return InterviewSyncService(
            self.interview_store(),
            NotionInterviewTarget(client, database_id),
        )

    def _query_applications(self, arguments: dict[str, object]) -> dict[str, object]:
        records = self.excel_repository().list_applications()
        status_filter = arguments.get("status")
        if isinstance(status_filter, str):
            records = [record for record in records if record.status == status_filter]
        return {"message": f"找到 {len(records)} 条投递记录。"}

    def _generate_review(self, arguments: dict[str, object]) -> dict[str, object]:
        del arguments
        records = self.excel_repository().list_applications()
        return {"message": f"当前共记录 {len(records)} 条投递。"}


def build_services(
    config_store: LocalConfigStore,
    *,
    secret_store: SecretStore | None = None,
    provider_factory: ProviderFactory = OpenAICompatibleProvider,
    notion_client_factory: NotionClientFactory = NotionClient,
) -> WebServices:
    action_service = ActionDraftService(
        _DynamicExcelRepository(config_store),
        _DynamicInterviewStore(config_store),
    )
    return WebServices(
        config_store=config_store,
        action_service=action_service,
        secret_store=secret_store or SecretStore(),
        provider_factory=provider_factory,
        notion_client_factory=notion_client_factory,
    )


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
