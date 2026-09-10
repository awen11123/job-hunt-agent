from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from job_hunt_agent.actions import ActionDraft, ActionDraftService
from job_hunt_agent.actions.models import DisclosureCategory
from job_hunt_agent.ai.provider import ChatMessage, LLMProvider
from job_hunt_agent.excel import TrackerApplicationDraft, TrackerApplicationPatch
from job_hunt_agent.interviews import LocalInterviewDraft


PlannerAction = Literal[
    "query_applications",
    "create_application",
    "update_application",
    "save_interview",
    "generate_review",
]
ReadHandler = Callable[[dict[str, object]], object]


class ActionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    action: PlannerAction
    arguments: dict[str, object]
    disclosure: list[DisclosureCategory] = Field(default_factory=list)


class _UpdateApplicationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    application_id: str = Field(min_length=1)
    patch: TrackerApplicationPatch


class UnsupportedActionError(ValueError):
    pass


class InvalidActionPlanError(ValueError):
    pass


class LLMActionPlanner:
    _WRITE_ACTIONS = {
        "create_application",
        "update_application",
        "save_interview",
    }
    _READ_ACTIONS = {"query_applications", "generate_review"}

    def __init__(
        self,
        provider: LLMProvider | None,
        draft_service: ActionDraftService,
        *,
        read_handlers: Mapping[str, ReadHandler] | None = None,
    ) -> None:
        self._provider = provider
        self._draft_service = draft_service
        self._read_handlers = dict(read_handlers or {})

    def propose(self, text: str) -> ActionDraft | object:
        if self._provider is None:
            return self._draft_service.propose_application(text)

        plan = self._provider.complete_structured(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Return one JSON action plan. Allowed actions: "
                        "query_applications, create_application, update_application, "
                        "save_interview, generate_review. Never request code, shell, files, "
                        "credentials, network access, or direct execution. Schema: "
                        f"{json.dumps(ActionPlan.model_json_schema(), ensure_ascii=False)}"
                    ),
                ),
                ChatMessage(role="user", content=text),
            ],
            ActionPlan,
        )
        return self._apply_plan(plan)

    def _apply_plan(self, plan: ActionPlan) -> ActionDraft | object:
        if plan.action in self._READ_ACTIONS:
            handler = self._read_handlers.get(plan.action)
            if handler is None:
                raise UnsupportedActionError("Read-only action is not available")
            return handler(dict(plan.arguments))

        if plan.action not in self._WRITE_ACTIONS:
            raise UnsupportedActionError("Model requested an unsupported action")

        try:
            if plan.action == "create_application":
                payload = TrackerApplicationDraft.model_validate(
                    plan.arguments
                ).model_dump(mode="python")
            elif plan.action == "update_application":
                update = _UpdateApplicationPlan.model_validate(plan.arguments)
                payload = {
                    "application_id": update.application_id,
                    "patch": update.patch.model_dump(mode="python", exclude_unset=True),
                }
            else:
                payload = LocalInterviewDraft.model_validate(plan.arguments).model_dump(
                    mode="python"
                )
        except ValidationError:
            raise InvalidActionPlanError("Model action payload is invalid") from None

        return self._draft_service.propose(
            plan.action,
            payload,
            disclosure=plan.disclosure,
        )
