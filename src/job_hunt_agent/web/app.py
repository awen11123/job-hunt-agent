from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from job_hunt_agent.actions import (
    ActionDraft,
    ActionExecution,
    ActionExecutionError,
    UnsupportedInputError,
)
from job_hunt_agent.excel import TrackerApplication
from job_hunt_agent.interviews import LocalInterviewRecord
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.web.dependencies import (
    LocalResourceError,
    WebServices,
    build_services,
    require_session,
)
from job_hunt_agent.web.schemas import ConfirmActionRequest, ProposeActionRequest


SessionRequired = Annotated[None, Depends(require_session)]


def _detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _raise_resource_error(error: LocalResourceError) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_detail(error.code, str(error)),
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


def build_api_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/config", response_model=LocalAppConfig)
    def get_config() -> LocalAppConfig:
        return services.load_config()

    @router.put("/config", response_model=LocalAppConfig)
    def put_config(config: LocalAppConfig, _session: SessionRequired) -> LocalAppConfig:
        return services.save_config(config)

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

    @router.post("/actions/propose", response_model=ActionDraft)
    def propose_action(request: ProposeActionRequest) -> ActionDraft:
        try:
            return services.action_service.propose_application(request.text)
        except UnsupportedInputError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_detail("unsupported_input", "暂时无法安全生成写入预览。"),
            ) from None

    @router.get("/actions/{draft_id}", response_model=ActionDraft)
    def get_action(draft_id: str) -> ActionDraft:
        try:
            return services.action_service.get(draft_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_detail("draft_not_found", "未找到操作草稿。"),
            ) from None

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


def create_app(
    config_store: LocalConfigStore,
    session_token: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Job Hunt Agent", docs_url=None, redoc_url=None)
    app.state.session_token = session_token or secrets.token_urlsafe(32)
    app.state.services = build_services(config_store)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request, _error) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": _detail("validation_error", "请求参数无效。")},
        )

    app.include_router(build_api_router(app.state.services))
    return app
