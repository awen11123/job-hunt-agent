from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from job_hunt_agent.actions import (
    ActionDraft,
    ActionDraftService,
    UnsupportedInputError,
)
from job_hunt_agent.excel import TrackerApplicationDraft, TrackerApplicationPatch
from job_hunt_agent.interviews import LocalInterviewDraft


NOW = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class RecordingExcelRepository:
    def __init__(self) -> None:
        self.created: list[TrackerApplicationDraft] = []
        self.updated: list[tuple[str, TrackerApplicationPatch]] = []
        self.failure: Exception | None = None
        self.delay = 0.0
        self._lock = threading.Lock()

    def create_application(self, draft: TrackerApplicationDraft):
        with self._lock:
            self.created.append(draft)
        if self.delay:
            time.sleep(self.delay)
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure
        return SimpleNamespace(id="app-created")

    def update_application(self, application_id: str, patch: TrackerApplicationPatch):
        with self._lock:
            self.updated.append((application_id, patch))
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure
        return SimpleNamespace(id=application_id)


class RecordingInterviewStore:
    def __init__(self) -> None:
        self.saved: list[tuple[LocalInterviewDraft, str]] = []

    def save(self, draft: LocalInterviewDraft, operation_id: str):
        self.saved.append((draft, operation_id))
        return SimpleNamespace(id="interview-created")


def configured_service(
    *,
    clock: MutableClock | None = None,
    tokens: tuple[str, ...] = ("first-secret-token", "second-secret-token"),
) -> tuple[ActionDraftService, RecordingExcelRepository, RecordingInterviewStore]:
    repository = RecordingExcelRepository()
    interview_store = RecordingInterviewStore()
    token_values = iter(tokens)
    service = ActionDraftService(
        repository,
        interview_store,
        clock=clock or MutableClock(),
        token_factory=lambda: next(token_values),
    )
    return service, repository, interview_store


def application_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company": "Example Technology",
        "role": "Agent Engineer",
        "applied_date": "2026-09-10",
    }
    payload.update(overrides)
    return payload


def interview_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "application_id": "app-1",
        "company": "Example Technology",
        "round_name": "first round",
        "raw_notes": "Discussed system design.",
    }
    payload.update(overrides)
    return payload


def test_action_draft_model_forbids_extra_fields_and_naive_expiry() -> None:
    fields = {
        "id": "draft-1",
        "action": "create_application",
        "payload": application_payload(),
        "confirmation_token": "secret",
        "operation_id": "operation-1",
        "expires_at": NOW + timedelta(minutes=10),
    }

    with pytest.raises(ValidationError):
        ActionDraft(**fields, unexpected=True)
    with pytest.raises(ValidationError, match="timezone-aware"):
        ActionDraft(**{**fields, "expires_at": datetime(2026, 9, 10, 8, 10)})


@pytest.mark.parametrize(
    ("action", "payload"),
    [
        ("create_application", {"company": "Missing Role"}),
        ("create_application", {**application_payload(), "extra": "forbidden"}),
        ("update_application", {"application_id": "app-1", "patch": {}}),
        ("update_application", {"patch": {"status": "interview"}}),
        ("update_application", {"application_id": "app-1", "patch": {"bad": 1}}),
        ("save_interview", {"application_id": "app-1"}),
        ("save_interview", {**interview_payload(), "extra": "forbidden"}),
    ],
)
def test_payload_is_validated_for_its_action(action: str, payload: dict[str, object]) -> None:
    service, _, _ = configured_service()

    with pytest.raises(ValidationError):
        service.propose(action, payload)


def test_propose_application_creates_preview_without_writing() -> None:
    service, repository, interview_store = configured_service()

    draft = service.propose_application("今天投了示例科技的 Agent 工程师，北京")

    assert draft.status == "pending"
    assert draft.action == "create_application"
    assert draft.payload["company"] == "示例科技"
    assert draft.payload["role"] == "Agent 工程师"
    assert draft.payload["location"] == "北京"
    assert draft.payload["applied_date"].isoformat() == "2026-09-10"
    assert draft.expires_at == NOW + timedelta(minutes=10)
    assert repository.created == []
    assert repository.updated == []
    assert interview_store.saved == []


@pytest.mark.parametrize(
    "text",
    [
        "无法解析的输入",
        "本周投了多少家",
        "今天投了 的 ",
    ],
)
def test_propose_application_rejects_unparseable_or_read_only_text(text: str) -> None:
    service, repository, _ = configured_service()

    with pytest.raises(UnsupportedInputError) as caught:
        service.propose_application(text)

    assert text not in str(caught.value)
    assert repository.created == []


def test_propose_is_idempotent_by_operation_id() -> None:
    service, _, _ = configured_service(tokens=("only-token",))

    first = service.propose(
        "create_application",
        application_payload(),
        operation_id="same-operation",
    )
    second = service.propose(
        "save_interview",
        interview_payload(),
        operation_id="same-operation",
    )

    assert second == first
    assert second.action == "create_application"


def test_modify_revalidates_payload_and_refreshes_only_token() -> None:
    service, _, _ = configured_service()
    original = service.propose(
        "create_application",
        application_payload(),
        operation_id="modify-operation",
    )

    modified = service.modify(
        original.id,
        application_payload(role="Platform Engineer"),
    )

    assert modified.payload["role"] == "Platform Engineer"
    assert modified.confirmation_token == "second-secret-token"
    assert modified.confirmation_token != original.confirmation_token
    assert modified.operation_id == original.operation_id
    assert modified.expires_at == original.expires_at
    with pytest.raises(ValidationError):
        service.modify(modified.id, {"company": "Missing Role"})


def test_cancel_is_idempotent_and_cancelled_token_never_executes() -> None:
    service, repository, _ = configured_service()
    proposed = service.propose("create_application", application_payload())

    first = service.cancel(proposed.id)
    second = service.cancel(proposed.id)

    assert first.status == "cancelled"
    assert second == first
    with pytest.raises(ValueError, match="cancelled"):
        service.confirm(proposed.id, proposed.confirmation_token)
    assert repository.created == []


def test_expired_access_marks_draft_expired_and_token_never_executes() -> None:
    clock = MutableClock()
    service, repository, _ = configured_service(clock=clock)
    proposed = service.propose("create_application", application_payload())

    clock.now = proposed.expires_at

    assert service.get(proposed.id).status == "expired"
    with pytest.raises(ValueError, match="expired"):
        service.confirm(proposed.id, proposed.confirmation_token)
    with pytest.raises(ValueError, match="expired"):
        service.modify(proposed.id, application_payload(role="New Role"))
    assert repository.created == []


def test_wrong_token_does_not_write_or_leak_sensitive_values() -> None:
    service, repository, _ = configured_service()
    secret_payload = application_payload(notes="private candidate notes")
    proposed = service.propose("create_application", secret_payload)

    with pytest.raises(ValueError) as caught:
        service.confirm(proposed.id, "wrong-secret-token")

    error_text = str(caught.value)
    assert "wrong-secret-token" not in error_text
    assert "first-secret-token" not in error_text
    assert "private candidate notes" not in error_text
    assert service.get(proposed.id).status == "pending"
    assert repository.created == []


def test_repository_failure_keeps_draft_pending_and_allows_same_token_retry() -> None:
    service, repository, _ = configured_service()
    repository.failure = OSError("workbook is busy")
    proposed = service.propose("create_application", application_payload())

    with pytest.raises(OSError, match="workbook is busy"):
        service.confirm(proposed.id, proposed.confirmation_token)

    assert service.get(proposed.id).status == "pending"
    execution = service.confirm(proposed.id, proposed.confirmation_token)
    assert execution.receipt.status == "created"
    assert len(repository.created) == 2


def test_confirmation_executes_once_and_returns_same_execution() -> None:
    service, repository, _ = configured_service()
    proposed = service.propose("create_application", application_payload())

    first = service.confirm(proposed.id, proposed.confirmation_token)
    second = service.confirm(proposed.id, proposed.confirmation_token)

    assert first == second
    assert first.draft.status == "confirmed"
    assert first.receipt.status == "created"
    assert first.receipt.record_id == "app-created"
    assert proposed.confirmation_token not in first.receipt.message
    assert proposed.confirmation_token not in repr(first.receipt)
    assert len(repository.created) == 1


def test_concurrent_confirmation_executes_once() -> None:
    service, repository, _ = configured_service()
    repository.delay = 0.05
    proposed = service.propose("create_application", application_payload())
    barrier = threading.Barrier(8)

    def confirm_once():
        barrier.wait()
        return service.confirm(proposed.id, proposed.confirmation_token)

    with ThreadPoolExecutor(max_workers=8) as executor:
        executions = list(executor.map(lambda _: confirm_once(), range(8)))

    assert all(execution == executions[0] for execution in executions)
    assert len(repository.created) == 1


def test_update_confirmation_preserves_before_and_passes_validated_patch() -> None:
    service, repository, _ = configured_service()
    before = {"id": "app-1", "status": "已投递"}
    proposed = service.propose(
        "update_application",
        {"application_id": " app-1 ", "patch": {"status": "面试"}},
        before=before,
        operation_id="update-operation",
    )

    before["status"] = "mutated outside"
    execution = service.confirm(proposed.id, proposed.confirmation_token)

    assert proposed.before == {"id": "app-1", "status": "已投递"}
    assert execution.receipt.status == "updated"
    assert execution.receipt.record_id == "app-1"
    assert len(repository.updated) == 1
    application_id, patch = repository.updated[0]
    assert application_id == "app-1"
    assert isinstance(patch, TrackerApplicationPatch)
    assert patch.model_dump(exclude_unset=True) == {"status": "面试"}


def test_save_interview_confirmation_uses_operation_id() -> None:
    service, _, interview_store = configured_service()
    proposed = service.propose(
        "save_interview",
        interview_payload(),
        operation_id="interview-operation",
    )

    execution = service.confirm(proposed.id, proposed.confirmation_token)

    assert execution.receipt.status == "created"
    assert execution.receipt.record_id == "interview-created"
    assert len(interview_store.saved) == 1
    saved_draft, operation_id = interview_store.saved[0]
    assert isinstance(saved_draft, LocalInterviewDraft)
    assert operation_id == "interview-operation"


def test_confirmed_draft_cannot_be_cancelled_or_modified() -> None:
    service, _, _ = configured_service()
    proposed = service.propose("create_application", application_payload())
    service.confirm(proposed.id, proposed.confirmation_token)

    with pytest.raises(ValueError, match="confirmed"):
        service.cancel(proposed.id)
    with pytest.raises(ValueError, match="confirmed"):
        service.modify(proposed.id, application_payload(role="Too Late"))


@pytest.mark.parametrize("method", ["get", "cancel", "modify", "confirm"])
def test_unknown_draft_raises_key_error(method: str) -> None:
    service, _, _ = configured_service()

    with pytest.raises(KeyError, match="missing"):
        if method == "get":
            service.get("missing")
        elif method == "cancel":
            service.cancel("missing")
        elif method == "modify":
            service.modify("missing", application_payload())
        else:
            service.confirm("missing", "unknown-token")
