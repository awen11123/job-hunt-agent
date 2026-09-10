from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


ProviderName = Literal[
    "deepseek",
    "qwen",
    "moonshot",
    "openai-compatible",
    "ollama",
]


class ProviderPreset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ProviderName
    display_name: str
    base_url: HttpUrl
    model: str
    requires_api_key: bool
    supports_json_mode: bool = True
    api_key: None = None


def provider_presets() -> dict[ProviderName, ProviderPreset]:
    presets = (
        ProviderPreset(
            name="deepseek",
            display_name="DeepSeek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            requires_api_key=True,
        ),
        ProviderPreset(
            name="qwen",
            display_name="通义千问",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            requires_api_key=True,
        ),
        ProviderPreset(
            name="moonshot",
            display_name="Moonshot",
            base_url="https://api.moonshot.cn/v1",
            model="moonshot-v1-8k",
            requires_api_key=True,
        ),
        ProviderPreset(
            name="openai-compatible",
            display_name="OpenAI 兼容接口",
            base_url="http://127.0.0.1:8000/v1",
            model="default",
            requires_api_key=True,
        ),
        ProviderPreset(
            name="ollama",
            display_name="Ollama（本地）",
            base_url="http://127.0.0.1:11434/v1",
            model="qwen3:8b",
            requires_api_key=False,
        ),
    )
    return {preset.name: preset for preset in presets}

