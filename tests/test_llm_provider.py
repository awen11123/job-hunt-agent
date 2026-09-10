from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from job_hunt_agent.ai import (
    ChatMessage,
    LLMProviderError,
    OpenAICompatibleProvider,
    ProviderConfig,
)


class StructuredReply(BaseModel):
    action: str
    arguments: dict[str, object]


class StubResponse:
    def __init__(
        self,
        content: str = '{"action":"query","arguments":{}}',
        *,
        status_code: int = 200,
        response_body: str = "",
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.response_body = response_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.com/v1/chat/completions")
            response = httpx.Response(
                self.status_code,
                request=request,
                text=self.response_body,
            )
            raise httpx.HTTPStatusError("remote failure", request=request, response=response)

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": self.content}}]}


class StubTransport:
    def __init__(
        self,
        content: str = '{"action":"query","arguments":{}}',
        *,
        status_code: int = 200,
        response_body: str = "",
        failure: Exception | None = None,
    ) -> None:
        self.response = StubResponse(
            content,
            status_code=status_code,
            response_body=response_body,
        )
        self.failure = failure
        self.last_url: str | None = None
        self.last_headers: dict[str, str] = {}
        self.last_json: dict[str, Any] | None = None
        self.last_timeout: float | None = None

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> StubResponse:
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        self.last_timeout = timeout
        if self.failure is not None:
            raise self.failure
        return self.response


def remote_config(*, api_key: str = "test-key") -> ProviderConfig:
    return ProviderConfig(
        name="openai-compatible",
        base_url="https://example.com/v1",
        model="example-chat",
        api_key=api_key,
    )


def test_openai_compatible_provider_validates_structured_output() -> None:
    transport = StubTransport()
    provider = OpenAICompatibleProvider(config=remote_config(), transport=transport)

    result = provider.complete_structured(
        [ChatMessage(role="user", content="plan this")],
        StructuredReply,
    )

    assert result == StructuredReply(action="query", arguments={})
    assert transport.last_url == "https://example.com/v1/chat/completions"
    assert transport.last_headers["Authorization"] == "Bearer test-key"
    assert transport.last_json == {
        "model": "example-chat",
        "messages": [{"role": "user", "content": "plan this"}],
        "response_format": {"type": "json_object"},
    }


def test_ollama_provider_omits_authorization_header() -> None:
    transport = StubTransport()
    provider = OpenAICompatibleProvider(
        ProviderConfig.ollama("qwen3:8b"),
        transport=transport,
    )

    provider.complete_structured([], StructuredReply)

    assert "Authorization" not in transport.last_headers
    assert transport.last_url == "http://127.0.0.1:11434/v1/chat/completions"


def test_remote_provider_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="API key"):
        ProviderConfig(
            name="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )


def test_malformed_json_raises_a_stable_error_without_content() -> None:
    private_body = "private-model-output"
    provider = OpenAICompatibleProvider(
        config=remote_config(),
        transport=StubTransport(private_body),
    )

    with pytest.raises(LLMProviderError, match="invalid structured output") as caught:
        provider.complete_structured([], StructuredReply)

    assert private_body not in str(caught.value)
    assert "test-key" not in str(caught.value)


def test_timeout_raises_a_stable_error_without_key() -> None:
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    provider = OpenAICompatibleProvider(
        config=remote_config(api_key="private-timeout-key"),
        transport=StubTransport(failure=httpx.ReadTimeout("private timeout", request=request)),
    )

    with pytest.raises(LLMProviderError, match="timed out") as caught:
        provider.complete_structured([], StructuredReply)

    assert "private-timeout-key" not in str(caught.value)
    assert "private timeout" not in str(caught.value)


def test_http_error_never_exposes_response_body_or_key() -> None:
    provider = OpenAICompatibleProvider(
        config=remote_config(api_key="private-http-key"),
        transport=StubTransport(status_code=429, response_body="private provider response"),
    )

    with pytest.raises(LLMProviderError, match="HTTP 429") as caught:
        provider.complete_structured([], StructuredReply)

    message = str(caught.value)
    assert "private provider response" not in message
    assert "private-http-key" not in message


def test_missing_choice_content_is_reported_as_invalid_response() -> None:
    class MissingContentResponse(StubResponse):
        def json(self) -> dict[str, Any]:
            return {"choices": []}

    transport = StubTransport()
    transport.response = MissingContentResponse()
    provider = OpenAICompatibleProvider(config=remote_config(), transport=transport)

    with pytest.raises(LLMProviderError, match="invalid response"):
        provider.complete_structured([], StructuredReply)
