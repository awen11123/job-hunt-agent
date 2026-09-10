from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from job_hunt_agent.actions import ActionDraftService
from job_hunt_agent.ai import ChatMessage
from job_hunt_agent.ai.action_planner import (
    ActionPlan,
    InvalidActionPlanError,
    LLMActionPlanner,
    UnsupportedActionError,
)


class RecordingExcelRepository:
    def __init__(self) -> None:
        self.created: list[object] = []

    def create_application(self, draft):
        self.created.append(draft)
        return SimpleNamespace(id="created-application")

    def update_application(self, application_id, patch):
        return SimpleNamespace(id=application_id)


class RecordingInterviewStore:
    def save(self, draft, operation_id):
        return SimpleNamespace(id="created-interview")


class StubProvider:
    provider_name = "deepseek"
    model_name = "deepseek-chat"

    def __init__(self, plan: ActionPlan) -> None:
        self.plan = plan
        self.messages: list[ChatMessage] = []

    def complete_structured(self, messages, response_model):
        assert response_model is ActionPlan
        self.messages = messages
        return self.plan


def build_planner(
    plan: ActionPlan | None,
    *,
    read_handlers: dict[str, Any] | None = None,
) -> tuple[LLMActionPlanner, ActionDraftService, RecordingExcelRepository]:
    repository = RecordingExcelRepository()
    drafts = ActionDraftService(
        repository,
        RecordingInterviewStore(),
        token_factory=lambda: "confirmation-secret",
    )
    provider = StubProvider(plan) if plan is not None else None
    return (
        LLMActionPlanner(provider, drafts, read_handlers=read_handlers),
        drafts,
        repository,
    )


def test_planner_returns_pending_draft_and_never_executes_write() -> None:
    planner, _, repository = build_planner(
        ActionPlan(
            action="create_application",
            arguments={"company": "示例科技", "role": "Agent 工程师"},
        )
    )

    result = planner.propose("记录一个示例科技 Agent 工程师投递")

    assert result.status == "pending"
    assert result.payload["company"] == "示例科技"
    assert repository.created == []


def test_unknown_tool_is_rejected_before_draft_creation() -> None:
    unsafe_plan = ActionPlan.model_construct(
        action="run_shell",
        arguments={"command": "dir"},
        disclosure=[],
    )
    planner, _, repository = build_planner(unsafe_plan)

    with pytest.raises(UnsupportedActionError):
        planner.propose("查看目录")

    assert repository.created == []


def test_missing_required_fields_are_rejected_before_draft_creation() -> None:
    planner, _, repository = build_planner(
        ActionPlan(action="create_application", arguments={"company": "示例科技"})
    )

    with pytest.raises(InvalidActionPlanError):
        planner.propose("记录投递")

    assert repository.created == []


def test_read_only_query_uses_only_its_registered_handler() -> None:
    calls: list[dict[str, object]] = []

    def query(arguments: dict[str, object]) -> dict[str, object]:
        calls.append(arguments)
        return {"count": 2}

    planner, _, repository = build_planner(
        ActionPlan(action="query_applications", arguments={"status": "已投递"}),
        read_handlers={"query_applications": query},
    )

    result = planner.propose("有多少条已投递记录")

    assert result == {"count": 2}
    assert calls == [{"status": "已投递"}]
    assert repository.created == []


def test_remote_disclosure_metadata_is_preserved_on_write_draft() -> None:
    planner, _, _ = build_planner(
        ActionPlan(
            action="save_interview",
            arguments={
                "application_id": "app-1",
                "company": "示例科技",
                "round_name": "技术一面",
                "raw_notes": "讨论了 RAG 评测。",
            },
            disclosure=["interview_notes"],
        )
    )

    result = planner.propose("保存这段面经")

    assert result.status == "pending"
    assert result.disclosure == ["interview_notes"]


def test_no_model_falls_back_to_the_deterministic_application_parser() -> None:
    planner, _, repository = build_planner(None)

    result = planner.propose("今天投了示例科技的 Agent 工程师，北京")

    assert result.action == "create_application"
    assert result.payload["location"] == "北京"
    assert result.disclosure == []
    assert repository.created == []


def test_unregistered_read_handler_is_rejected() -> None:
    planner, _, _ = build_planner(
        ActionPlan(action="generate_review", arguments={"period": "weekly"})
    )

    with pytest.raises(UnsupportedActionError):
        planner.propose("生成本周复盘")
