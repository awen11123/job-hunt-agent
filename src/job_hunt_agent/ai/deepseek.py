from typing import Protocol

from job_hunt_agent.domain.models import InterviewAnalysis


class InterviewAnalyzer(Protocol):
    model_version: str
    prompt_version: str

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        ...


class DeepSeekInterviewAnalyzer:
    prompt_version = "interview-analysis-v1"

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_version = model

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        import httpx

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model_version,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return strict JSON for the InterviewAnalysis schema. "
                            "Do not invent missing candidate answers."
                        ),
                    },
                    {"role": "user", "content": raw_notes},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return InterviewAnalysis.model_validate_json(content)
