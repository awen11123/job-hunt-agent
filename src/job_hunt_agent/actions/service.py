from __future__ import annotations

import copy
import re
import secrets
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from job_hunt_agent.actions.models import (
    ActionDraft,
    ActionExecution,
    ActionName,
    ActionReceipt,
)
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.excel import TrackerApplicationDraft, TrackerApplicationPatch
from job_hunt_agent.interviews import LocalInterviewDraft
from job_hunt_agent.nlu.application_text import parse_application_text


_WRITE_REQUEST_PATTERN = re.compile(
    r"^(?:今天|昨天|明天)?\s*(?:我)?\s*(?:已)?\s*"
    r"(?:投了|投递了|投递|申请了|申请|待投|准备投)"
)
_QUESTION_PATTERN = re.compile(
    r"(?:哪个|哪些|什么|吗|是否|多少|怎么|如何|为何|为什么|[?？])"
)
_STAGE_STATUS = {
    RecruitingStage.TO_APPLY: "待投递",
    RecruitingStage.APPLIED: "已投递",
    RecruitingStage.WRITTEN_TEST: "笔试",
    RecruitingStage.INTERVIEW: "面试",
    RecruitingStage.INTENTION: "意向",
    RecruitingStage.OFFER: "Offer",
}


class UnsupportedInputError(ValueError):
    """Raised when free-form text cannot safely become a write draft."""


class ActionExecutionError(RuntimeError):
    """Safe public error raised when a confirmed action cannot be executed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_EXECUTION_ERRORS: dict[ActionName, tuple[str, str]] = {
    "create_application": (
        "create_application_failed",
        "Application creation failed.",
    ),
    "update_application": (
        "update_application_failed",
        "Application update failed.",
    ),
    "save_interview": (
        "save_interview_failed",
        "Interview save failed.",
    ),
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ActionDraftService:
    def __init__(
        self,
        excel_repository: Any,
        interview_store: Any = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
        ttl: timedelta = timedelta(minutes=10),
        token_factory: Callable[[], str] = secrets.token_urlsafe,
    ) -> None:
        self._excel_repository = excel_repository
        self._interview_store = interview_store
        self._clock = clock
        self._ttl = ttl
        self._token_factory = token_factory
        self._drafts: dict[str, ActionDraft] = {}
        self._draft_ids_by_operation: dict[str, str] = {}
        self._executions: dict[str, ActionExecution] = {}
        self._lock = threading.RLock()

    def propose_application(self, text: str) -> ActionDraft:
        if _QUESTION_PATTERN.search(text) or not _WRITE_REQUEST_PATTERN.search(text.strip()):
            raise UnsupportedInputError("Input is not an unambiguous application write request")

        today = self._now().date()
        try:
            parsed = parse_application_text(text, today, default_season="local")
            payload: dict[str, Any] = {
                "company": parsed.company,
                "role": parsed.role,
                "applied_date": parsed.applied_date or today,
                "location": parsed.location,
                "status": _STAGE_STATUS[parsed.current_stage],
            }
            if parsed.next_step is not None:
                payload["next_step"] = parsed.next_step
            if parsed.jd_url is not None:
                payload["job_url"] = parsed.jd_url
            return self.propose("create_application", payload)
        except (KeyError, ValueError) as exc:
            raise UnsupportedInputError(
                "Input is not an unambiguous application write request"
            ) from exc

    def propose(
        self,
        action: ActionName,
        payload: Mapping[str, Any],
        before: Mapping[str, Any] | None = None,
        operation_id: str | None = None,
    ) -> ActionDraft:
        if operation_id is None:
            requested_operation_id = str(uuid.uuid4())
        else:
            requested_operation_id = operation_id.strip()
            if not requested_operation_id:
                raise ValueError("operation_id must not be blank")
        with self._lock:
            existing_id = self._draft_ids_by_operation.get(requested_operation_id)
            if existing_id is not None:
                return self._copy_draft(self._expire_if_needed(self._drafts[existing_id]))

            now = self._now()
            draft = ActionDraft(
                id=str(uuid.uuid4()),
                action=action,
                payload=dict(payload),
                before=copy.deepcopy(dict(before)) if before is not None else None,
                confirmation_token=self._token_factory(),
                operation_id=requested_operation_id,
                expires_at=now + self._ttl,
            )
            self._drafts[draft.id] = draft
            self._draft_ids_by_operation[draft.operation_id] = draft.id
            return self._copy_draft(draft)

    def modify(self, draft_id: str, payload: Mapping[str, Any]) -> ActionDraft:
        with self._lock:
            draft = self._require_draft(draft_id)
            draft = self._expire_if_needed(draft)
            self._require_pending(draft)
            validated = ActionDraft(
                id=draft.id,
                action=draft.action,
                payload=dict(payload),
                before=copy.deepcopy(draft.before),
                status="pending",
                confirmation_token=draft.confirmation_token,
                operation_id=draft.operation_id,
                expires_at=draft.expires_at,
            )
            modified = ActionDraft(
                **validated.model_dump(mode="python", exclude={"confirmation_token"}),
                confirmation_token=self._token_factory(),
            )
            self._drafts[draft_id] = modified
            return self._copy_draft(modified)

    def cancel(self, draft_id: str) -> ActionDraft:
        with self._lock:
            draft = self._require_draft(draft_id)
            draft = self._expire_if_needed(draft)
            if draft.status == "cancelled":
                return self._copy_draft(draft)
            self._require_pending(draft)
            cancelled = draft.model_copy(update={"status": "cancelled"}, deep=True)
            self._drafts[draft_id] = cancelled
            return self._copy_draft(cancelled)

    def get(self, draft_id: str) -> ActionDraft:
        with self._lock:
            draft = self._expire_if_needed(self._require_draft(draft_id))
            return self._copy_draft(draft)

    def confirm(self, draft_id: str, confirmation_token: str) -> ActionExecution:
        with self._lock:
            draft = self._expire_if_needed(self._require_draft(draft_id))
            if draft.status == "confirmed":
                self._require_matching_token(draft, confirmation_token)
                return self._copy_execution(self._executions[draft_id])
            self._require_pending(draft)
            self._require_matching_token(draft, confirmation_token)

            executed_at = self._now()
            try:
                receipt = self._execute(draft)
            except Exception:
                code, message = _EXECUTION_ERRORS[draft.action]
                raise ActionExecutionError(code, message) from None
            confirmed = draft.model_copy(update={"status": "confirmed"}, deep=True)
            execution = ActionExecution(
                draft=confirmed,
                receipt=receipt,
                executed_at=executed_at,
            )
            self._drafts[draft_id] = confirmed
            self._executions[draft_id] = execution
            return self._copy_execution(execution)

    def _execute(self, draft: ActionDraft) -> ActionReceipt:
        if draft.action == "create_application":
            record = self._excel_repository.create_application(
                TrackerApplicationDraft.model_validate(draft.payload)
            )
            return ActionReceipt(
                status="created",
                record_id=self._record_id(record),
                message="Application created.",
            )
        if draft.action == "update_application":
            application_id = draft.payload["application_id"]
            record = self._excel_repository.update_application(
                application_id,
                TrackerApplicationPatch.model_validate(draft.payload["patch"]),
            )
            return ActionReceipt(
                status="updated",
                record_id=self._record_id(record) or application_id,
                message="Application updated.",
            )
        if self._interview_store is None:
            raise RuntimeError("Interview storage is not configured")
        record = self._interview_store.save(
            LocalInterviewDraft.model_validate(draft.payload),
            draft.operation_id,
        )
        return ActionReceipt(
            status="created",
            record_id=self._record_id(record),
            message="Interview saved.",
        )

    def _expire_if_needed(self, draft: ActionDraft) -> ActionDraft:
        if draft.status == "pending" and self._now() >= draft.expires_at:
            draft = draft.model_copy(update={"status": "expired"}, deep=True)
            self._drafts[draft.id] = draft
        return draft

    def _require_draft(self, draft_id: str) -> ActionDraft:
        try:
            return self._drafts[draft_id]
        except KeyError:
            raise KeyError(draft_id) from None

    @staticmethod
    def _require_pending(draft: ActionDraft) -> None:
        if draft.status != "pending":
            raise ValueError(f"Action draft is {draft.status}")

    @staticmethod
    def _require_matching_token(draft: ActionDraft, supplied_token: str) -> None:
        try:
            matches = secrets.compare_digest(draft.confirmation_token, supplied_token)
        except TypeError:
            matches = False
        if not matches:
            raise ValueError("Invalid confirmation token")

    def _now(self) -> datetime:
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now

    @staticmethod
    def _record_id(record: Any) -> str | None:
        if isinstance(record, Mapping):
            value = record.get("id")
        else:
            value = getattr(record, "id", None)
        return value if isinstance(value, str) else None

    @staticmethod
    def _copy_draft(draft: ActionDraft) -> ActionDraft:
        return draft.model_copy(deep=True)

    @staticmethod
    def _copy_execution(execution: ActionExecution) -> ActionExecution:
        return execution.model_copy(deep=True)
