from __future__ import annotations

from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, HttpUrl, SecretStr, model_validator


ResponseT = TypeVar("ResponseT", bound=BaseModel)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal[
        "deepseek",
        "qwen",
        "moonshot",
        "openai-compatible",
        "ollama",
    ]
    base_url: HttpUrl
    model: str
    api_key: SecretStr | None = None
    supports_json_mode: bool = True

    @model_validator(mode="after")
    def require_remote_api_key(self) -> "ProviderConfig":
        if self.name != "ollama" and (
            self.api_key is None or not self.api_key.get_secret_value().strip()
        ):
            raise ValueError("Remote model providers require an API key")
        if not self.model.strip():
            raise ValueError("Model name must not be blank")
        return self

    @classmethod
    def ollama(
        cls,
        model: str,
        base_url: str = "http://127.0.0.1:11434/v1",
    ) -> "ProviderConfig":
        return cls(name="ollama", base_url=base_url, model=model)


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def complete_structured(
        self,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
    ) -> ResponseT: ...


class LLMProviderError(RuntimeError):
    """A stable provider error that never includes model output or credentials."""

