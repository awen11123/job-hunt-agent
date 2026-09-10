from __future__ import annotations

from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from job_hunt_agent.ai.provider import (
    ChatMessage,
    LLMProviderError,
    ProviderConfig,
    ResponseT,
)


class _Transport(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> Any: ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: _Transport | None = None,
        timeout: float = 60,
    ) -> None:
        self.config = config
        self.provider_name = config.name
        self.model_name = config.model
        self.transport: _Transport = transport or httpx.Client(trust_env=False)
        self.timeout = timeout

    def complete_structured(
        self,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
    ) -> ResponseT:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key is not None:
            headers["Authorization"] = (
                f"Bearer {self.config.api_key.get_secret_value()}"
            )

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [message.model_dump() for message in messages],
        }
        if self.config.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self.transport.post(
                f"{str(self.config.base_url).rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise LLMProviderError("Model request timed out.") from None
        except httpx.HTTPStatusError as error:
            raise LLMProviderError(
                f"Model provider returned HTTP {error.response.status_code}."
            ) from None
        except httpx.RequestError:
            raise LLMProviderError("Model provider is unavailable.") from None

        try:
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMProviderError("Model provider returned an invalid response.") from None

        try:
            return response_model.model_validate_json(content)
        except (ValidationError, ValueError, TypeError):
            raise LLMProviderError("Model returned invalid structured output.") from None

