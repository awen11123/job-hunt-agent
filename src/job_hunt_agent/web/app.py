from __future__ import annotations

import html
import secrets
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from job_hunt_agent.actions import (
    ActionDraft,
    ActionExecution,
    ActionExecutionError,
    UnsupportedInputError,
)
from job_hunt_agent.ai import (
    ChatMessage,
    InvalidActionPlanError,
    LLMProviderError,
    UnsupportedActionError,
)
from job_hunt_agent.ai.presets import provider_presets
from job_hunt_agent.excel import TrackerApplication
from job_hunt_agent.interviews import LocalInterviewRecord
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.local_app.secrets import SecretStore
from job_hunt_agent.notion import NotionClient
from job_hunt_agent.web.dependencies import (
    LocalResourceError,
    NotionClientFactory,
    ProviderFactory,
    WebServices,
    build_services,
    require_session,
)
from job_hunt_agent.web.schemas import (
    AssistantMessage,
    ConfirmActionRequest,
    IntegrationSettingsView,
    ModelConnectionResult,
    ModelSettingsRequest,
    ModelSettingsView,
    ModifyActionRequest,
    NotionConnectionResult,
    NotionSettingsRequest,
    NotionSettingsView,
    ProposeActionRequest,
    PublicLocalConfig,
)


SessionRequired = Annotated[None, Depends(require_session)]


class _InvalidFrontendIndex(ValueError):
    pass


class _ModelProbe(BaseModel):
    ok: bool


@dataclass(frozen=True)
class _RootStartTag:
    offset: int
    raw: str
    has_unique_root_id: bool
    has_session_token: bool


class _RootElementParser(HTMLParser):
    def __init__(self, document: str) -> None:
        super().__init__(convert_charrefs=False)
        self._line_offsets = [0]
        for line in document.splitlines(keepends=True):
            self._line_offsets.append(self._line_offsets[-1] + len(line))
        self.roots: list[_RootStartTag] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "div":
            return
        id_values = [value for name, value in attrs if name == "id"]
        if "root" not in id_values:
            return
        raw = self.get_starttag_text()
        if raw is None:
            raise _InvalidFrontendIndex
        line, column = self.getpos()
        self.roots.append(
            _RootStartTag(
                offset=self._line_offsets[line - 1] + column,
                raw=raw,
                has_unique_root_id=id_values == ["root"],
                has_session_token=any(
                    name == "data-session-token" for name, _value in attrs
                ),
            )
        )


def _inject_session_token(index: str, session_token: str) -> str:
    parser = _RootElementParser(index)
    parser.feed(index)
    parser.close()
    if len(parser.roots) != 1:
        raise _InvalidFrontendIndex

    root = parser.roots[0]
    if (
        not root.has_unique_root_id
        or root.has_session_token
        or root.raw.rstrip().endswith("/>")
    ):
        raise _InvalidFrontendIndex
    closing_offset = root.raw.rfind(">")
    if closing_offset < 0:
        raise _InvalidFrontendIndex
    insertion_offset = root.offset + closing_offset
    escaped_token = html.escape(session_token, quote=True)
    return (
        f'{index[:insertion_offset]} data-session-token="{escaped_token}"'
        f"{index[insertion_offset:]}"
    )


def _detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _raise_resource_error(error: LocalResourceError) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_detail(error.code, str(error)),
    ) from None


def _raise_config_unavailable() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_detail("config_unavailable", "本地配置暂时不可用。"),
    ) from None


def _raise_draft_state_error(error: ValueError) -> None:
    message = str(error)
    if message == "Invalid confirmation token":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_detail("invalid_confirmation", "确认凭证无效。"),
        ) from None
    if "cancelled" in message:
        code = "draft_cancelled"
    elif "expired" in message:
        code = "draft_expired"
    elif "confirmed" in message:
        code = "draft_confirmed"
    else:
        code = "draft_conflict"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_detail(code, "操作草稿当前状态不允许此操作。"),
    ) from None


def _credential_is_configured(services: WebServices, reference: str | None) -> bool:
    if reference is None:
        return False
    try:
        return services.secret_store.get(reference) is not None
    except Exception:
        return False


def _model_settings_view(services: WebServices) -> ModelSettingsView:
    config = services.load_config()
    preset = provider_presets()[config.model_provider]
    return ModelSettingsView(
        enabled=config.model_enabled,
        provider=config.model_provider,
        base_url=str(config.model_base_url or preset.base_url).rstrip("/"),
        model=config.model_name or preset.model,
        credential_configured=_credential_is_configured(
            services,
            config.model_credential_ref,
        ),
        requires_api_key=preset.requires_api_key,
    )


def _notion_settings_view(services: WebServices) -> NotionSettingsView:
    config = services.load_config()
    return NotionSettingsView(
        enabled=config.notion_enabled,
        credential_configured=_credential_is_configured(
            services,
            config.notion_credential_ref,
        ),
        database_configured=config.notion_interviews_database_id is not None,
    )


def build_api_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/config", response_model=PublicLocalConfig)
    def get_config() -> PublicLocalConfig:
        try:
            return PublicLocalConfig.from_config(services.load_config())
        except (OSError, ValueError):
            _raise_config_unavailable()

    @router.put("/config", response_model=PublicLocalConfig)
    def put_config(
        config: PublicLocalConfig,
        _session: SessionRequired,
    ) -> PublicLocalConfig:
        try:
            current = services.load_config()
            merged = LocalAppConfig.model_validate(
                {**current.model_dump(mode="python"), **config.model_dump(mode="python")}
            )
            return PublicLocalConfig.from_config(services.save_config(merged))
        except (OSError, ValueError):
            _raise_config_unavailable()

    @router.get("/settings", response_model=IntegrationSettingsView)
    def get_settings() -> IntegrationSettingsView:
        try:
            return IntegrationSettingsView(
                model=_model_settings_view(services),
                notion=_notion_settings_view(services),
            )
        except (OSError, ValueError):
            _raise_config_unavailable()

    @router.put("/settings/model", response_model=ModelSettingsView)
    def put_model_settings(
        request: ModelSettingsRequest,
        _session: SessionRequired,
    ) -> ModelSettingsView:
        try:
            current = services.load_config()
            preset = provider_presets()[request.provider]
            credential_ref = (
                None
                if not preset.requires_api_key
                else f"model:{request.provider}:default"
            )
            if request.api_key is not None and credential_ref is not None:
                services.secret_store.set(credential_ref, request.api_key)
            updated = LocalAppConfig.model_validate(
                {
                    **current.model_dump(mode="python"),
                    "model_enabled": request.enabled,
                    "model_provider": request.provider,
                    "model_base_url": str(request.base_url or preset.base_url).rstrip("/"),
                    "model_name": request.model or preset.model,
                    "model_credential_ref": credential_ref,
                }
            )
            services.save_config(updated)
            return _model_settings_view(services)
        except (OSError, RuntimeError, ValueError):
            _raise_config_unavailable()

    @router.post("/settings/model/test", response_model=ModelConnectionResult)
    def test_model_settings(_session: SessionRequired) -> ModelConnectionResult:
        try:
            result = services.model_provider().complete_structured(
                [
                    ChatMessage(
                        role="system",
                        content='Return exactly {"ok": true} as JSON.',
                    )
                ],
                _ModelProbe,
            )
            if not result.ok:
                raise LLMProviderError("Model capability probe failed")
            return ModelConnectionResult(status="connected", structured_output=True)
        except (LLMProviderError, LocalResourceError, OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail("model_unavailable", "模型服务暂时不可用。"),
            ) from None

    @router.put("/settings/notion", response_model=NotionSettingsView)
    def put_notion_settings(
        request: NotionSettingsRequest,
        _session: SessionRequired,
    ) -> NotionSettingsView:
        try:
            current = services.load_config()
            credential_ref = current.notion_credential_ref
            if request.token is not None:
                credential_ref = "notion:default"
                services.secret_store.set(credential_ref, request.token)
            database_id = (
                request.interviews_database_id
                if request.interviews_database_id is not None
                else current.notion_interviews_database_id
            )
            updated = LocalAppConfig.model_validate(
                {
                    **current.model_dump(mode="python"),
                    "notion_enabled": request.enabled,
                    "notion_credential_ref": credential_ref,
                    "notion_interviews_database_id": database_id,
                }
            )
            services.save_config(updated)
            return _notion_settings_view(services)
        except (OSError, RuntimeError, ValueError):
            _raise_config_unavailable()

    @router.post("/settings/notion/test", response_model=NotionConnectionResult)
    def test_notion_settings(_session: SessionRequired) -> NotionConnectionResult:
        try:
            client, database_id = services.notion_client()
            client.retrieve_data_source(database_id)
            return NotionConnectionResult(status="connected")
        except (LocalResourceError, OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail("notion_unavailable", "Notion 暂时不可用。"),
            ) from None

    @router.get("/applications", response_model=list[TrackerApplication])
    def list_applications() -> list[TrackerApplication]:
        try:
            return services.excel_repository().list_applications()
        except LocalResourceError as error:
            _raise_resource_error(error)
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail("excel_unavailable", "Excel 投递表暂时不可用。"),
            ) from None

    @router.get("/interviews", response_model=list[LocalInterviewRecord])
    def list_interviews(
        application_id: Annotated[str | None, Query()] = None,
    ) -> list[LocalInterviewRecord]:
        try:
            return services.interview_store().list(application_id=application_id)
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail("interviews_unavailable", "本地面经暂时不可用。"),
            ) from None

    @router.post("/interviews/{interview_id}/sync", response_model=LocalInterviewRecord)
    def sync_interview(
        interview_id: str,
        _session: SessionRequired,
    ) -> LocalInterviewRecord:
        try:
            return services.interview_sync_service().retry(interview_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_detail("interview_not_found", "未找到面经记录。"),
            ) from None
        except LocalResourceError as error:
            _raise_resource_error(error)
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail("interview_sync_failed", "面经同步暂时失败。"),
            ) from None

    @router.post("/actions/propose", response_model=ActionDraft | AssistantMessage)
    def propose_action(request: ProposeActionRequest) -> ActionDraft | AssistantMessage:
        try:
            result = services.action_planner().propose(request.text)
            if isinstance(result, ActionDraft):
                return result
            if isinstance(result, dict) and isinstance(result.get("message"), str):
                return AssistantMessage(message=result["message"])
            raise UnsupportedActionError("Planner returned an unsupported result")
        except UnsupportedInputError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_detail("unsupported_input", "暂时无法安全生成写入预览。"),
            ) from None
        except (InvalidActionPlanError, UnsupportedActionError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_detail("unsupported_action", "模型未能生成可安全执行的操作。"),
            ) from None
        except LLMProviderError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail("model_unavailable", "模型服务暂时不可用。"),
            ) from None
        except LocalResourceError as error:
            _raise_resource_error(error)

    @router.get("/actions/{draft_id}", response_model=ActionDraft)
    def get_action(draft_id: str) -> ActionDraft:
        try:
            return services.action_service.get(draft_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_detail("draft_not_found", "未找到操作草稿。"),
            ) from None

    @router.patch("/actions/{draft_id}", response_model=ActionDraft)
    def modify_action(
        draft_id: str,
        request: ModifyActionRequest,
        _session: SessionRequired,
    ) -> ActionDraft:
        try:
            return services.action_service.modify(draft_id, request.payload)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_detail("draft_not_found", "未找到操作草稿。"),
            ) from None
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_detail(
                    "invalid_action_payload",
                    "变更内容无效，请检查必填字段和字段格式。",
                ),
            ) from None
        except ValueError as error:
            _raise_draft_state_error(error)

    @router.post("/actions/{draft_id}/confirm", response_model=ActionExecution)
    def confirm_action(
        draft_id: str,
        request: ConfirmActionRequest,
        _session: SessionRequired,
    ) -> ActionExecution:
        try:
            return services.action_service.confirm(draft_id, request.confirmation_token)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_detail("draft_not_found", "未找到操作草稿。"),
            ) from None
        except ActionExecutionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_detail(error.code, str(error)),
            ) from None
        except ValueError as error:
            _raise_draft_state_error(error)

    @router.post("/actions/{draft_id}/cancel", response_model=ActionDraft)
    def cancel_action(draft_id: str, _session: SessionRequired) -> ActionDraft:
        try:
            return services.action_service.cancel(draft_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_detail("draft_not_found", "未找到操作草稿。"),
            ) from None
        except ValueError as error:
            _raise_draft_state_error(error)

    return router


def _frontend_response(
    static_root: Path,
    full_path: str,
    session_token: str,
) -> Response:
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    requested = (static_root / full_path).resolve() if full_path else None
    if requested is not None:
        try:
            requested.relative_to(static_root)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        if requested.is_file() and requested.name != "index.html":
            return FileResponse(requested)
        if full_path == "assets" or full_path.startswith("assets/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    index_path = static_root / "index.html"
    try:
        index = index_path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_detail("frontend_unavailable", "前端资源暂时不可用。"),
        ) from None
    try:
        rendered = _inject_session_token(index, session_token)
    except _InvalidFrontendIndex:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_detail("frontend_unavailable", "前端资源暂时不可用。"),
        ) from None
    return HTMLResponse(rendered, headers={"Cache-Control": "no-store"})


def create_app(
    config_store: LocalConfigStore,
    session_token: str | None = None,
    static_dir: Path | None = None,
    *,
    secret_store: SecretStore | None = None,
    provider_factory: ProviderFactory | None = None,
    notion_client_factory: NotionClientFactory | None = None,
) -> FastAPI:
    app = FastAPI(title="Job Hunt Agent", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost"],
    )
    app.state.session_token = session_token or secrets.token_urlsafe(32)
    service_options = {}
    if secret_store is not None:
        service_options["secret_store"] = secret_store
    if provider_factory is not None:
        service_options["provider_factory"] = provider_factory
    if notion_client_factory is not None:
        service_options["notion_client_factory"] = notion_client_factory
    app.state.services = build_services(config_store, **service_options)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request, _error) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": _detail("validation_error", "请求参数无效。")},
        )

    app.include_router(build_api_router(app.state.services))

    if static_dir is not None:
        static_root = static_dir.resolve()
        try:
            index = (static_root / "index.html").read_text(encoding="utf-8")
            _inject_session_token(index, app.state.session_token)
        except (OSError, _InvalidFrontendIndex):
            raise RuntimeError("The frontend build is unavailable.") from None

        @app.get("/", include_in_schema=False, response_model=None)
        def serve_frontend_root() -> Response:
            return _frontend_response(static_root, "", app.state.session_token)

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        def serve_frontend_path(full_path: str) -> Response:
            return _frontend_response(static_root, full_path, app.state.session_token)

    return app
