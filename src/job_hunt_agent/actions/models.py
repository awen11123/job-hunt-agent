from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from job_hunt_agent.excel import TrackerApplicationDraft, TrackerApplicationPatch
from job_hunt_agent.interviews import LocalInterviewDraft


ActionName = Literal["create_application", "update_application", "save_interview"]
ActionStatus = Literal["pending", "confirmed", "cancelled", "expired"]
ReceiptStatus = Literal["created", "updated", "unchanged", "failed"]


class _ActionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )


class _UpdateApplicationPayload(_ActionModel):
    application_id: str = Field(min_length=1)
    patch: TrackerApplicationPatch


class ActionDraft(_ActionModel):
    id: str = Field(min_length=1)
    action: ActionName
    payload: dict[str, Any]
    before: dict[str, Any] | None = None
    status: ActionStatus = "pending"
    confirmation_token: str = Field(min_length=1, repr=False)
    operation_id: str = Field(min_length=1)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_payload_for_action(self) -> ActionDraft:
        if self.action == "create_application":
            validated = TrackerApplicationDraft.model_validate(self.payload)
            self.payload = validated.model_dump(mode="python")
        elif self.action == "update_application":
            validated_update = _UpdateApplicationPayload.model_validate(self.payload)
            self.payload = {
                "application_id": validated_update.application_id,
                "patch": validated_update.patch.model_dump(
                    mode="python",
                    exclude_unset=True,
                ),
            }
        else:
            validated_interview = LocalInterviewDraft.model_validate(self.payload)
            self.payload = validated_interview.model_dump(mode="python")
        return self


class ActionReceipt(_ActionModel):
    status: ReceiptStatus
    record_id: str | None = None
    message: str


class ActionExecution(_ActionModel):
    draft: ActionDraft
    receipt: ActionReceipt
    executed_at: datetime

    @field_validator("executed_at")
    @classmethod
    def execution_time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("executed_at must be timezone-aware")
        return value
