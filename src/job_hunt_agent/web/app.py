from __future__ import annotations

import html
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

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
from job_hunt_agent.web.schemas import (
    ConfirmActionRequest,
    ModifyActionRequest,
    ProposeActionRequest,
)


SessionRequired = Annotated[None, Depends(require_session)]
_ROOT_ELEMENT = re.compile(
    r"(<div\b(?=[^>]*\bid=(?P<quote>['\"])root(?P=quote))[^>]*)(>)",
    re.IGNORECASE,
)
_SESSION_ATTRIBUTE = re.compile(
    r'''\s+data-session-token\b(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?''',
    re.IGNORECASE,
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


def build_api_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/config", response_model=LocalAppConfig)
    def get_config() -> LocalAppConfig:
        try:
            return services.load_config()
        except (OSError, ValueError):
            _raise_config_unavailable()

    @router.put("/config", response_model=LocalAppConfig)
    def put_config(config: LocalAppConfig, _session: SessionRequired) -> LocalAppConfig:
        try:
            return services.save_config(config)
        except (OSError, ValueError):
            _raise_config_unavailable()

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
    if len(list(_ROOT_ELEMENT.finditer(index))) != 1:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_detail("frontend_unavailable", "前端资源暂时不可用。"),
        )
    escaped_token = html.escape(session_token, quote=True)
    rendered, _count = _ROOT_ELEMENT.subn(
        lambda match: (
            f'{_SESSION_ATTRIBUTE.sub("", match.group(1))} '
            f'data-session-token="{escaped_token}"{match.group(3)}'
        ),
        index,
        count=1,
    )
    return HTMLResponse(rendered, headers={"Cache-Control": "no-store"})


def create_app(
    config_store: LocalConfigStore,
    session_token: str | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Job Hunt Agent", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost"],
    )
    app.state.session_token = session_token or secrets.token_urlsafe(32)
    app.state.services = build_services(config_store)

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
        except OSError:
            raise RuntimeError("The frontend build is unavailable.") from None
        if len(list(_ROOT_ELEMENT.finditer(index))) != 1:
            raise RuntimeError("The frontend build is unavailable.")

        @app.get("/", include_in_schema=False, response_model=None)
        def serve_frontend_root() -> Response:
            return _frontend_response(static_root, "", app.state.session_token)

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        def serve_frontend_path(full_path: str) -> Response:
            return _frontend_response(static_root, full_path, app.state.session_token)

    return app
