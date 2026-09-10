from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from job_hunt_agent.ai.presets import ProviderName
from job_hunt_agent.local_app.config import LocalAppConfig


class _ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProposeActionRequest(_ApiRequest):
    text: str = Field(min_length=1)


class ConfirmActionRequest(_ApiRequest):
    confirmation_token: str = Field(min_length=1)


class ModifyActionRequest(_ApiRequest):
    payload: dict[str, Any]


class PublicLocalConfig(_ApiRequest):
    excel_path: Path | None = None
    backup_dir: Path
    interview_dir: Path
    notion_enabled: bool = False
    model_enabled: bool = False

    @classmethod
    def from_config(cls, config: LocalAppConfig) -> "PublicLocalConfig":
        return cls(**config.model_dump(include=set(cls.model_fields)))


class ModelSettingsRequest(_ApiRequest):
    enabled: bool
    provider: ProviderName
    base_url: HttpUrl | None = None
    model: str | None = Field(default=None, min_length=1)
    api_key: str | None = Field(default=None, min_length=1, repr=False)


class NotionSettingsRequest(_ApiRequest):
    enabled: bool
    token: str | None = Field(default=None, min_length=1, repr=False)
    interviews_database_id: str | None = Field(default=None, min_length=1, repr=False)


class ModelSettingsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: ProviderName
    base_url: str
    model: str
    credential_configured: bool
    requires_api_key: bool


class NotionSettingsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    credential_configured: bool
    database_configured: bool


class IntegrationSettingsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ModelSettingsView
    notion: NotionSettingsView


class ModelConnectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["connected"]
    structured_output: bool


class NotionConnectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["connected"]


class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["message"] = "message"
    message: str
