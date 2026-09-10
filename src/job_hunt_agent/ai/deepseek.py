from typing import Protocol

from job_hunt_agent.ai.openai_compatible import OpenAICompatibleProvider
from job_hunt_agent.ai.provider import ChatMessage, ProviderConfig
from job_hunt_agent.domain.models import InterviewAnalysis


class InterviewAnalyzer(Protocol):
    model_version: str
    prompt_version: str

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        ...


class DeepSeekInterviewAnalyzer:
    prompt_version = "interview-analysis-v1"

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model_version = model
        self._provider = OpenAICompatibleProvider(
            ProviderConfig(
                name="deepseek",
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
        )

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        return self._provider.complete_structured(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Return strict JSON for the InterviewAnalysis schema. "
                        "Do not invent missing candidate answers."
                    ),
                ),
                ChatMessage(role="user", content=raw_notes),
            ],
            InterviewAnalysis,
        )
