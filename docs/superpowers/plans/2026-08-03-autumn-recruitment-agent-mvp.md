# Autumn Recruitment Agent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, testable Python MCP service for recording applications, updating stages, saving interview notes, analyzing interviews with a DeepSeek-compatible adapter, and producing follow-up/review summaries while keeping real job-search data private.

**Architecture:** Keep private data in Notion through a repository boundary, and run all core behavior against an in-memory repository in tests. The MCP layer stays thin: it validates tool inputs, calls services, and returns receipts. DeepSeek is isolated behind an analyzer protocol so tests never call a real model.

**Tech Stack:** Python 3.12, FastMCP, Pydantic v2, httpx, pytest, Ruff, Notion API over httpx, DeepSeek OpenAI-compatible chat completions.

---

## File Structure

- `pyproject.toml` - package metadata, runtime dependencies, pytest and Ruff settings.
- `.gitignore` - local env, caches, build artifacts, and private exports.
- `.env.example` - documented environment variable names with empty values only.
- `README.md` - public project explanation, privacy boundary, local usage commands.
- `src/job_hunt_agent/__init__.py` - package version export.
- `src/job_hunt_agent/config.py` - environment parsing with no secrets logged.
- `src/job_hunt_agent/domain/models.py` - Pydantic records, drafts, receipts, and interview analysis schema.
- `src/job_hunt_agent/domain/statuses.py` - stage, outcome, event, sync, and confirmation enums.
- `src/job_hunt_agent/matching.py` - deterministic normalization, application keying, and disambiguation helpers.
- `src/job_hunt_agent/privacy.py` - secret and private-data leak scanner for text/files.
- `src/job_hunt_agent/repositories.py` - repository protocol, in-memory implementation, and Notion client skeleton.
- `src/job_hunt_agent/services/applications.py` - application creation, dedupe, stage update, idempotency, and receipts.
- `src/job_hunt_agent/services/interviews.py` - interview note persistence, analysis persistence, and review task creation.
- `src/job_hunt_agent/services/reporting.py` - follow-up listing plus daily and weekly review generation.
- `src/job_hunt_agent/ai/deepseek.py` - DeepSeek-compatible analyzer adapter with Pydantic response validation.
- `src/job_hunt_agent/prompts/interview_analysis.md` - model contract for interview analysis.
- `src/job_hunt_agent/mcp_server.py` - FastMCP server construction and tool registration.
- `scripts/privacy_scan.py` - local leak scan entrypoint for CI and pre-push checks.
- `examples/synthetic_inputs.jsonl` - public synthetic examples only.
- `docs/notion-setup.md` - Notion integration and database field setup.
- `docs/privacy.md` - privacy rules for public GitHub usage.
- `tests/` - focused pytest suite for each boundary.

## Execution Notes

- All shell commands in this workspace must be prefixed with `rtk`.
- Real Notion and DeepSeek credentials are read only from environment variables.
- Unit and contract tests use in-memory fakes and synthetic data.
- The public repo must never include real company records, interview notes, Notion URLs, or API keys.

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/job_hunt_agent/__init__.py`
- Create: `tests/test_project_scaffold.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_project_scaffold.py`:

```python
from job_hunt_agent import __version__


def test_package_exports_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the scaffold test to verify it fails**

Run:

```bash
rtk python -m pytest tests/test_project_scaffold.py -q
```

Expected: FAIL because `job_hunt_agent` does not exist yet.

- [ ] **Step 3: Create package metadata and public project files**

Create `pyproject.toml`:

```toml
[project]
name = "job-hunt-agent"
version = "0.1.0"
description = "Private Notion-backed autumn recruitment tracker exposed as a Python MCP server."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "fastmcp>=2.0.0",
  "httpx>=0.27.0",
  "pydantic>=2.7.0",
  "python-dotenv>=1.0.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2.0",
  "ruff>=0.5.0",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
build/
dist/
*.egg-info/
private_exports/
notion_cache.json
```

Create `.env.example`:

```dotenv
NOTION_TOKEN=
NOTION_APPLICATIONS_DB_ID=
NOTION_ACTIVITY_DB_ID=
NOTION_INTERVIEWS_DB_ID=
NOTION_REVIEW_TASKS_DB_ID=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEFAULT_RECRUITING_SEASON=2026-autumn
```

Create `README.md`:

```markdown
# Job Hunt Agent

A private Notion-backed autumn recruitment tracker exposed as a Python MCP server.

The project is designed for AI Agent and LLM application engineer recruiting. Public code,
schemas, prompts, tests, and synthetic examples live in GitHub. Real applications,
interview notes, contacts, Notion page URLs, and API keys stay outside the repository.

## Local Usage

```bash
rtk python -m pytest -q
```

Configure credentials through environment variables. Never commit `.env`.

## Privacy Boundary

- Notion is the source of truth for real job-search data.
- GitHub contains code and synthetic examples only.
- DeepSeek and Notion secrets are read from environment variables only.
```

Create `src/job_hunt_agent/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Run the scaffold test to verify it passes**

Run:

```bash
rtk python -m pytest tests/test_project_scaffold.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit scaffold**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add pyproject.toml .gitignore .env.example README.md src tests
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "chore: scaffold job hunt agent"
```

Expected: commit succeeds.

---

### Task 2: Domain Models and Status Rules

**Files:**
- Create: `src/job_hunt_agent/domain/__init__.py`
- Create: `src/job_hunt_agent/domain/statuses.py`
- Create: `src/job_hunt_agent/domain/models.py`
- Create: `tests/test_domain_models.py`

- [ ] **Step 1: Write failing tests for core schemas**

Create `tests/test_domain_models.py`:

```python
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from job_hunt_agent.domain.models import (
    ActivityEvent,
    ApplicationDraft,
    ApplicationRecord,
    InterviewAnalysis,
    ReviewTaskCandidate,
)
from job_hunt_agent.domain.statuses import EventType, RecruitingStage, SyncStatus


def test_application_draft_tracks_noncritical_missing_fields() -> None:
    draft = ApplicationDraft(company="DeepSeek", role="LLM Application Engineer")

    assert draft.season is None
    assert draft.missing_noncritical_fields() == [
        "season",
        "direction",
        "location",
        "channel",
        "resume_version",
        "applied_date",
    ]


def test_application_record_requires_company_role_and_season() -> None:
    record = ApplicationRecord(
        id="app_1",
        company="MiniMax",
        role="AI Agent Engineer",
        season="2026-autumn",
        current_stage=RecruitingStage.APPLIED,
        created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    assert record.current_stage is RecruitingStage.APPLIED


def test_activity_event_uses_operation_id_for_idempotency() -> None:
    event = ActivityEvent(
        id="evt_1",
        application_id="app_1",
        operation_id="op_abc",
        event_type=EventType.STAGE_UPDATED,
        occurred_at=datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc),
        from_stage=RecruitingStage.APPLIED,
        to_stage=RecruitingStage.INTERVIEW,
        sync_status=SyncStatus.COMPLETED,
    )

    assert event.operation_id == "op_abc"


def test_interview_analysis_rejects_fabricated_answer_summary() -> None:
    with pytest.raises(ValidationError):
        InterviewAnalysis(
            overview="One technical interview.",
            technical_questions=["How does RAG chunking work?"],
            project_questions=[],
            behavioral_questions=[],
            reverse_questions=[],
            answer_summary="The candidate answered perfectly.",
            answer_summary_source_present=False,
            evidence_based_performance=[],
            better_answer_ideas=[],
            weaknesses=[],
            review_tasks=[],
            inference_notes=[],
        )


def test_review_task_candidate_defaults_to_pending_confirmation() -> None:
    task = ReviewTaskCandidate(
        category="RAG",
        topic="Hybrid search evaluation",
        action="Build a small BM25 plus vector search comparison on synthetic data.",
    )

    assert task.confirmation_status == "pending"
    assert task.occurrences == 1
```

- [ ] **Step 2: Run the domain tests to verify they fail**

Run:

```bash
rtk python -m pytest tests/test_domain_models.py -q
```

Expected: FAIL because domain modules do not exist.

- [ ] **Step 3: Define enums**

Create `src/job_hunt_agent/domain/statuses.py`:

```python
from enum import StrEnum


class RecruitingStage(StrEnum):
    TO_APPLY = "to_apply"
    APPLIED = "applied"
    WRITTEN_TEST = "written_test"
    INTERVIEW = "interview"
    INTENTION = "intention"
    OFFER = "offer"


class FinalOutcome(StrEnum):
    ONGOING = "ongoing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventType(StrEnum):
    APPLICATION_CREATED = "application_created"
    STAGE_UPDATED = "stage_updated"
    INTERVIEW_RECORDED = "interview_recorded"
    INTERVIEW_ANALYZED = "interview_analyzed"


class SyncStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class InterviewAnalysisStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
```

- [ ] **Step 4: Define Pydantic models**

Create `src/job_hunt_agent/domain/__init__.py`:

```python
from job_hunt_agent.domain.models import (
    ActivityEvent,
    ApplicationDraft,
    ApplicationRecord,
    InterviewAnalysis,
    InterviewDraft,
    InterviewRecord,
    ReviewTaskCandidate,
    ReviewTaskRecord,
    ToolReceipt,
)
from job_hunt_agent.domain.statuses import RecruitingStage

__all__ = [
    "ActivityEvent",
    "ApplicationDraft",
    "ApplicationRecord",
    "InterviewAnalysis",
    "InterviewDraft",
    "InterviewRecord",
    "RecruitingStage",
    "ReviewTaskCandidate",
    "ReviewTaskRecord",
    "ToolReceipt",
]
```

Create `src/job_hunt_agent/domain/models.py`:

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from job_hunt_agent.domain.statuses import (
    FinalOutcome,
    InterviewAnalysisStatus,
    Priority,
    RecruitingStage,
    SyncStatus,
    EventType,
)


class ApplicationDraft(BaseModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    season: str | None = None
    direction: str | None = None
    location: str | None = None
    channel: str | None = None
    jd_url: HttpUrl | None = None
    resume_version: str | None = None
    applied_date: date | None = None
    current_stage: RecruitingStage = RecruitingStage.APPLIED
    priority: Priority = Priority.MEDIUM
    deadline: date | None = None
    next_step: str | None = None

    def missing_noncritical_fields(self) -> list[str]:
        fields = ["season", "direction", "location", "channel", "resume_version", "applied_date"]
        return [name for name in fields if getattr(self, name) is None]


class ApplicationRecord(ApplicationDraft):
    id: str
    season: str
    final_outcome: FinalOutcome = FinalOutcome.ONGOING
    end_reason: str | None = None
    needs_supplement: bool = False
    archived: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(validate_assignment=True)


class ActivityEvent(BaseModel):
    id: str
    application_id: str
    operation_id: str
    event_type: EventType
    occurred_at: datetime
    from_stage: RecruitingStage | None = None
    to_stage: RecruitingStage | None = None
    note: str | None = None
    sync_status: SyncStatus = SyncStatus.PENDING


class InterviewDraft(BaseModel):
    application_id: str
    round_name: str = Field(min_length=1)
    scheduled_at: datetime | None = None
    format: str | None = None
    result: str | None = None
    raw_notes: str = Field(min_length=1)
    self_score: int | None = Field(default=None, ge=1, le=10)


class ReviewTaskCandidate(BaseModel):
    category: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    action: str = Field(min_length=10)
    mastery: str | None = None
    due_date: date | None = None
    occurrences: int = Field(default=1, ge=1)
    confirmation_status: Literal["pending", "confirmed", "dismissed"] = "pending"


class InterviewAnalysis(BaseModel):
    overview: str
    technical_questions: list[str] = Field(default_factory=list)
    project_questions: list[str] = Field(default_factory=list)
    behavioral_questions: list[str] = Field(default_factory=list)
    reverse_questions: list[str] = Field(default_factory=list)
    answer_summary: str | None = None
    answer_summary_source_present: bool = False
    evidence_based_performance: list[str] = Field(default_factory=list)
    better_answer_ideas: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    review_tasks: list[ReviewTaskCandidate] = Field(default_factory=list)
    inference_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def answer_summary_must_have_source(self) -> "InterviewAnalysis":
        if self.answer_summary and not self.answer_summary_source_present:
            raise ValueError("answer_summary requires answer_summary_source_present=true")
        return self


class InterviewRecord(InterviewDraft):
    id: str
    structured_analysis: InterviewAnalysis | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    analysis_status: InterviewAnalysisStatus = InterviewAnalysisStatus.PENDING
    created_at: datetime
    updated_at: datetime


class ReviewTaskRecord(ReviewTaskCandidate):
    id: str
    source_interview_ids: list[str] = Field(default_factory=list)
    completed: bool = False
    created_at: datetime
    updated_at: datetime


class ToolReceipt(BaseModel):
    status: Literal["created", "updated", "unchanged", "needs_disambiguation", "partial", "failed"]
    message: str
    record_id: str | None = None
    operation_id: str | None = None
    pending_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Run the domain tests to verify they pass**

Run:

```bash
rtk python -m pytest tests/test_domain_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit domain models**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add src/job_hunt_agent/domain tests/test_domain_models.py
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "feat: add job hunt domain models"
```

Expected: commit succeeds.

---

### Task 3: Matching, Privacy Scan, and Configuration

**Files:**
- Create: `src/job_hunt_agent/config.py`
- Create: `src/job_hunt_agent/matching.py`
- Create: `src/job_hunt_agent/privacy.py`
- Create: `tests/test_matching_privacy_config.py`

- [ ] **Step 1: Write failing tests for matching, leak scanning, and env parsing**

Create `tests/test_matching_privacy_config.py`:

```python
from job_hunt_agent.config import Settings
from job_hunt_agent.matching import application_key, normalize_text
from job_hunt_agent.privacy import scan_text_for_private_leaks


def test_application_key_normalizes_company_role_and_season() -> None:
    assert application_key(" DeepSeek ", "LLM Application Engineer", "2026 Autumn") == (
        "deepseek",
        "llm application engineer",
        "2026 autumn",
    )


def test_normalize_text_collapses_internal_whitespace() -> None:
    assert normalize_text("AI   Agent\tEngineer") == "ai agent engineer"


def test_privacy_scan_detects_notion_urls_and_api_keys() -> None:
    text = (
        "Notion: https://www.notion" + ".so/private-page "
        "and key " + "sk-" + "abc123456789SECRET"
    )

    findings = scan_text_for_private_leaks(text)

    assert {finding.kind for finding in findings} == {"notion_url", "api_key"}


def test_settings_reads_env_without_requiring_real_secrets(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_RECRUITING_SEASON", "2026-autumn")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")

    settings = Settings.from_env()

    assert settings.default_recruiting_season == "2026-autumn"
    assert settings.deepseek_model == "deepseek-chat"
    assert settings.notion_token is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk python -m pytest tests/test_matching_privacy_config.py -q
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement config, matching, and privacy modules**

Create `src/job_hunt_agent/config.py`:

```python
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    notion_token: str | None
    notion_applications_db_id: str | None
    notion_activity_db_id: str | None
    notion_interviews_db_id: str | None
    notion_review_tasks_db_id: str | None
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str
    default_recruiting_season: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            notion_token=os.getenv("NOTION_TOKEN") or None,
            notion_applications_db_id=os.getenv("NOTION_APPLICATIONS_DB_ID") or None,
            notion_activity_db_id=os.getenv("NOTION_ACTIVITY_DB_ID") or None,
            notion_interviews_db_id=os.getenv("NOTION_INTERVIEWS_DB_ID") or None,
            notion_review_tasks_db_id=os.getenv("NOTION_REVIEW_TASKS_DB_ID") or None,
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            default_recruiting_season=os.getenv("DEFAULT_RECRUITING_SEASON") or None,
        )
```

Create `src/job_hunt_agent/matching.py`:

```python
import re


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def application_key(company: str, role: str, season: str) -> tuple[str, str, str]:
    return normalize_text(company), normalize_text(role), normalize_text(season)
```

Create `src/job_hunt_agent/privacy.py`:

```python
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PrivacyFinding:
    kind: str
    value: str


NOTION_URL_RE = re.compile(r"https://(?:www\.)?notion\.so/[^\s)>\"]+", re.IGNORECASE)
API_KEY_RE = re.compile(r"\b(?:sk|ntn|secret)[-_][A-Za-z0-9_-]{12,}\b")
ENV_SECRET_RE = re.compile(r"\b(?:NOTION_TOKEN|DEEPSEEK_API_KEY|GITHUB_TOKEN)\s*=\s*\S+")


def scan_text_for_private_leaks(text: str) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    findings.extend(PrivacyFinding("notion_url", match.group(0)) for match in NOTION_URL_RE.finditer(text))
    findings.extend(PrivacyFinding("api_key", match.group(0)) for match in API_KEY_RE.finditer(text))
    findings.extend(PrivacyFinding("env_secret", match.group(0)) for match in ENV_SECRET_RE.finditer(text))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk python -m pytest tests/test_matching_privacy_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit matching, privacy, and config**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add src/job_hunt_agent/config.py src/job_hunt_agent/matching.py src/job_hunt_agent/privacy.py tests/test_matching_privacy_config.py
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "feat: add config matching and privacy scan"
```

Expected: commit succeeds.

---

### Task 4: Repository Boundary and Application Service

**Files:**
- Create: `src/job_hunt_agent/repositories.py`
- Create: `src/job_hunt_agent/services/__init__.py`
- Create: `src/job_hunt_agent/services/applications.py`
- Create: `tests/test_application_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_application_service.py`:

```python
from job_hunt_agent.domain.models import ApplicationDraft
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.repositories import InMemoryJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService


def test_record_application_creates_record_and_activity_event() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")

    receipt = service.record_application(
        ApplicationDraft(company="DeepSeek", role="LLM Application Engineer"),
        operation_id="op-create-1",
    )

    assert receipt.status == "created"
    assert receipt.pending_fields == ["direction", "location", "channel", "resume_version", "applied_date"]
    assert repo.get_application(receipt.record_id).season == "2026-autumn"
    assert repo.activity_events[0].operation_id == "op-create-1"
    assert repo.activity_events[0].sync_status == "completed"


def test_record_application_is_idempotent_by_operation_id() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")
    draft = ApplicationDraft(company="DeepSeek", role="LLM Application Engineer")

    first = service.record_application(draft, operation_id="op-create-1")
    second = service.record_application(draft, operation_id="op-create-1")

    assert second.status == "unchanged"
    assert second.record_id == first.record_id
    assert len(repo.applications) == 1
    assert len(repo.activity_events) == 1


def test_record_application_deduplicates_company_role_and_season() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")

    service.record_application(
        ApplicationDraft(company=" DeepSeek ", role="LLM Application Engineer"),
        operation_id="op-create-1",
    )
    receipt = service.record_application(
        ApplicationDraft(company="deepseek", role="LLM   Application Engineer"),
        operation_id="op-create-2",
    )

    assert receipt.status == "unchanged"
    assert len(repo.applications) == 1


def test_update_application_stage_writes_pending_then_completed_event() -> None:
    repo = InMemoryJobHuntRepository()
    service = ApplicationService(repo, default_season="2026-autumn")
    created = service.record_application(
        ApplicationDraft(company="MiniMax", role="AI Agent Engineer"),
        operation_id="op-create-1",
    )

    receipt = service.update_application_stage(
        application_id=created.record_id,
        to_stage=RecruitingStage.INTERVIEW,
        operation_id="op-stage-1",
        note="Passed written test.",
    )

    assert receipt.status == "updated"
    assert repo.get_application(created.record_id).current_stage is RecruitingStage.INTERVIEW
    assert repo.activity_events[-1].sync_status == "completed"
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```bash
rtk python -m pytest tests/test_application_service.py -q
```

Expected: FAIL because repository and service modules do not exist.

- [ ] **Step 3: Implement the repository boundary**

Create `src/job_hunt_agent/repositories.py`:

```python
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from job_hunt_agent.domain.models import (
    ActivityEvent,
    ApplicationRecord,
    InterviewRecord,
    ReviewTaskRecord,
)
from job_hunt_agent.domain.statuses import SyncStatus
from job_hunt_agent.matching import application_key


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobHuntRepository(Protocol):
    def save_application(self, record: ApplicationRecord) -> ApplicationRecord: ...
    def get_application(self, application_id: str | None) -> ApplicationRecord: ...
    def find_application_by_key(self, company: str, role: str, season: str) -> ApplicationRecord | None: ...
    def save_activity_event(self, event: ActivityEvent) -> ActivityEvent: ...
    def find_activity_by_operation_id(self, operation_id: str) -> ActivityEvent | None: ...
    def save_interview(self, record: InterviewRecord) -> InterviewRecord: ...
    def get_interview(self, interview_id: str) -> InterviewRecord: ...
    def save_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord: ...


class InMemoryJobHuntRepository:
    def __init__(self) -> None:
        self.applications: dict[str, ApplicationRecord] = {}
        self.activity_events: list[ActivityEvent] = []
        self.interviews: dict[str, InterviewRecord] = {}
        self.review_tasks: dict[str, ReviewTaskRecord] = {}

    def next_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    def save_application(self, record: ApplicationRecord) -> ApplicationRecord:
        self.applications[record.id] = record
        return record

    def get_application(self, application_id: str | None) -> ApplicationRecord:
        if application_id is None or application_id not in self.applications:
            raise KeyError(f"application not found: {application_id}")
        return self.applications[application_id]

    def find_application_by_key(self, company: str, role: str, season: str) -> ApplicationRecord | None:
        expected = application_key(company, role, season)
        for record in self.applications.values():
            if application_key(record.company, record.role, record.season) == expected:
                return record
        return None

    def save_activity_event(self, event: ActivityEvent) -> ActivityEvent:
        for index, existing in enumerate(self.activity_events):
            if existing.id == event.id:
                self.activity_events[index] = event
                return event
        self.activity_events.append(event)
        return event

    def find_activity_by_operation_id(self, operation_id: str) -> ActivityEvent | None:
        for event in self.activity_events:
            if event.operation_id == operation_id:
                return event
        return None

    def save_interview(self, record: InterviewRecord) -> InterviewRecord:
        self.interviews[record.id] = record
        return record

    def get_interview(self, interview_id: str) -> InterviewRecord:
        return self.interviews[interview_id]

    def save_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord:
        self.review_tasks[record.id] = record
        return record


class NotionJobHuntRepository:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Notion repository requires database setup before real writes are enabled")
```

- [ ] **Step 4: Implement application service**

Create `src/job_hunt_agent/services/__init__.py`:

```python
__all__: list[str] = []
```

Create `src/job_hunt_agent/services/applications.py`:

```python
from datetime import datetime, timezone

from job_hunt_agent.domain.models import ActivityEvent, ApplicationDraft, ApplicationRecord, ToolReceipt
from job_hunt_agent.domain.statuses import EventType, RecruitingStage, SyncStatus
from job_hunt_agent.repositories import JobHuntRepository


class ApplicationService:
    def __init__(self, repository: JobHuntRepository, default_season: str | None = None) -> None:
        self.repository = repository
        self.default_season = default_season

    def record_application(self, draft: ApplicationDraft, operation_id: str) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=existing_event.application_id,
                operation_id=operation_id,
            )

        season = draft.season or self.default_season
        if season is None:
            return ToolReceipt(
                status="failed",
                message="Recruiting season is required.",
                operation_id=operation_id,
                pending_fields=["season"],
            )

        existing = self.repository.find_application_by_key(draft.company, draft.role, season)
        if existing is not None:
            return ToolReceipt(
                status="unchanged",
                message="Matching application already exists.",
                record_id=existing.id,
                operation_id=operation_id,
            )

        now = datetime.now(timezone.utc)
        record = ApplicationRecord(
            **draft.model_dump(exclude={"season"}),
            id=self.repository.next_id("app"),
            season=season,
            needs_supplement=bool(
                [field for field in draft.missing_noncritical_fields() if field != "season"]
            ),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_application(record)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=record.id,
            operation_id=operation_id,
            event_type=EventType.APPLICATION_CREATED,
            occurred_at=now,
            to_stage=record.current_stage,
            sync_status=SyncStatus.COMPLETED,
        )
        self.repository.save_activity_event(event)
        pending_fields = [field for field in draft.missing_noncritical_fields() if field != "season"]
        return ToolReceipt(
            status="created",
            message=f"Created application for {record.company} - {record.role}.",
            record_id=record.id,
            operation_id=operation_id,
            pending_fields=pending_fields,
        )

    def update_application_stage(
        self,
        application_id: str,
        to_stage: RecruitingStage,
        operation_id: str,
        note: str | None = None,
    ) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=existing_event.application_id,
                operation_id=operation_id,
            )

        record = self.repository.get_application(application_id)
        now = datetime.now(timezone.utc)
        pending_event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=record.id,
            operation_id=operation_id,
            event_type=EventType.STAGE_UPDATED,
            occurred_at=now,
            from_stage=record.current_stage,
            to_stage=to_stage,
            note=note,
            sync_status=SyncStatus.PENDING,
        )
        self.repository.save_activity_event(pending_event)
        record.current_stage = to_stage
        record.updated_at = now
        self.repository.save_application(record)
        completed_event = pending_event.model_copy(update={"sync_status": SyncStatus.COMPLETED})
        self.repository.save_activity_event(completed_event)
        return ToolReceipt(
            status="updated",
            message=f"Updated application stage to {to_stage.value}.",
            record_id=record.id,
            operation_id=operation_id,
        )
```

- [ ] **Step 5: Run service tests to verify they pass**

Run:

```bash
rtk python -m pytest tests/test_application_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit repository and application service**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add src/job_hunt_agent/repositories.py src/job_hunt_agent/services tests/test_application_service.py
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "feat: add application tracking service"
```

Expected: commit succeeds.

---

### Task 5: Interview Recording and DeepSeek-Compatible Analysis

**Files:**
- Create: `src/job_hunt_agent/ai/__init__.py`
- Create: `src/job_hunt_agent/ai/deepseek.py`
- Create: `src/job_hunt_agent/prompts/interview_analysis.md`
- Create: `src/job_hunt_agent/services/interviews.py`
- Create: `tests/test_interview_service.py`

- [ ] **Step 1: Write failing interview service tests**

Create `tests/test_interview_service.py`:

```python
from job_hunt_agent.domain.models import ApplicationDraft, InterviewAnalysis, InterviewDraft, ReviewTaskCandidate
from job_hunt_agent.domain.statuses import InterviewAnalysisStatus
from job_hunt_agent.repositories import InMemoryJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.interviews import InterviewService


class FakeAnalyzer:
    model_version = "fake-deepseek"
    prompt_version = "interview-analysis-v1"

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        assert "Hybrid Search" in raw_notes
        return InterviewAnalysis(
            overview="One technical interview focused on retrieval systems.",
            technical_questions=["How would you evaluate Hybrid Search?"],
            project_questions=[],
            behavioral_questions=[],
            reverse_questions=[],
            answer_summary=None,
            answer_summary_source_present=False,
            evidence_based_performance=["The notes only mention that the topic was asked."],
            better_answer_ideas=["Compare BM25-only, vector-only, and hybrid retrieval on the same queries."],
            weaknesses=["Hybrid Search evaluation depth"],
            review_tasks=[
                ReviewTaskCandidate(
                    category="RAG",
                    topic="Hybrid Search evaluation",
                    action="Build a BM25 versus vector versus hybrid retrieval comparison on synthetic data.",
                )
            ],
            inference_notes=["Performance quality cannot be inferred without an answer transcript."],
        )


def make_application(repo: InMemoryJobHuntRepository) -> str:
    service = ApplicationService(repo, default_season="2026-autumn")
    receipt = service.record_application(
        ApplicationDraft(company="DeepSeek", role="LLM Application Engineer"),
        operation_id="op-app",
    )
    return receipt.record_id


def test_record_interview_preserves_raw_notes() -> None:
    repo = InMemoryJobHuntRepository()
    application_id = make_application(repo)
    service = InterviewService(repo, analyzer=FakeAnalyzer())

    receipt = service.record_interview(
        InterviewDraft(
            application_id=application_id,
            round_name="first round",
            raw_notes="Asked about Hybrid Search. I did not record my answer.",
        ),
        operation_id="op-interview",
    )

    interview = repo.get_interview(receipt.record_id)
    assert receipt.status == "created"
    assert interview.raw_notes == "Asked about Hybrid Search. I did not record my answer."
    assert interview.analysis_status is InterviewAnalysisStatus.PENDING


def test_analyze_interview_stores_validated_analysis_and_pending_tasks() -> None:
    repo = InMemoryJobHuntRepository()
    application_id = make_application(repo)
    service = InterviewService(repo, analyzer=FakeAnalyzer())
    created = service.record_interview(
        InterviewDraft(
            application_id=application_id,
            round_name="first round",
            raw_notes="Asked about Hybrid Search. I did not record my answer.",
        ),
        operation_id="op-interview",
    )

    receipt = service.analyze_interview(created.record_id, operation_id="op-analysis")

    interview = repo.get_interview(created.record_id)
    assert receipt.status == "updated"
    assert interview.analysis_status is InterviewAnalysisStatus.COMPLETED
    assert interview.structured_analysis.answer_summary is None
    assert len(repo.review_tasks) == 1
    task = next(iter(repo.review_tasks.values()))
    assert task.confirmation_status == "pending"
    assert task.source_interview_ids == [created.record_id]
```

- [ ] **Step 2: Run interview tests to verify they fail**

Run:

```bash
rtk python -m pytest tests/test_interview_service.py -q
```

Expected: FAIL because interview service and AI modules do not exist.

- [ ] **Step 3: Add the model prompt contract**

Create `src/job_hunt_agent/prompts/interview_analysis.md`:

```markdown
# Interview Analysis Prompt v1

You analyze Chinese campus recruiting interview notes for AI Agent and LLM application
engineer roles.

Return JSON matching the InterviewAnalysis schema. Preserve uncertainty:

- Do not invent candidate answers.
- Set `answer_summary` to null when the notes do not contain the candidate answer.
- Use `inference_notes` for uncertain judgments.
- Make review task actions concrete and executable.
- Keep generated review tasks pending user confirmation.
```

- [ ] **Step 4: Implement DeepSeek adapter and interview service**

Create `src/job_hunt_agent/ai/__init__.py`:

```python
from job_hunt_agent.ai.deepseek import DeepSeekInterviewAnalyzer, InterviewAnalyzer

__all__ = ["DeepSeekInterviewAnalyzer", "InterviewAnalyzer"]
```

Create `src/job_hunt_agent/ai/deepseek.py`:

```python
from typing import Protocol

import httpx

from job_hunt_agent.domain.models import InterviewAnalysis


class InterviewAnalyzer(Protocol):
    model_version: str
    prompt_version: str

    def analyze(self, raw_notes: str) -> InterviewAnalysis: ...


class DeepSeekInterviewAnalyzer:
    prompt_version = "interview-analysis-v1"

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_version = model

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
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
```

Create `src/job_hunt_agent/services/interviews.py`:

```python
from datetime import datetime, timezone

from job_hunt_agent.ai.deepseek import InterviewAnalyzer
from job_hunt_agent.domain.models import (
    ActivityEvent,
    InterviewDraft,
    InterviewRecord,
    ReviewTaskRecord,
    ToolReceipt,
)
from job_hunt_agent.domain.statuses import EventType, InterviewAnalysisStatus, SyncStatus
from job_hunt_agent.repositories import JobHuntRepository


class InterviewService:
    def __init__(self, repository: JobHuntRepository, analyzer: InterviewAnalyzer) -> None:
        self.repository = repository
        self.analyzer = analyzer

    def record_interview(self, draft: InterviewDraft, operation_id: str) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=existing_event.note,
                operation_id=operation_id,
            )

        self.repository.get_application(draft.application_id)
        now = datetime.now(timezone.utc)
        interview = InterviewRecord(
            **draft.model_dump(),
            id=self.repository.next_id("int"),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_interview(interview)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=draft.application_id,
            operation_id=operation_id,
            event_type=EventType.INTERVIEW_RECORDED,
            occurred_at=now,
            note=interview.id,
            sync_status=SyncStatus.COMPLETED,
        )
        self.repository.save_activity_event(event)
        return ToolReceipt(
            status="created",
            message=f"Recorded interview round {interview.round_name}.",
            record_id=interview.id,
            operation_id=operation_id,
        )

    def analyze_interview(self, interview_id: str, operation_id: str) -> ToolReceipt:
        existing_event = self.repository.find_activity_by_operation_id(operation_id)
        if existing_event is not None:
            return ToolReceipt(
                status="unchanged",
                message="Operation already recorded.",
                record_id=interview_id,
                operation_id=operation_id,
            )

        interview = self.repository.get_interview(interview_id)
        analysis = self.analyzer.analyze(interview.raw_notes)
        now = datetime.now(timezone.utc)
        updated = interview.model_copy(
            update={
                "structured_analysis": analysis,
                "model_version": self.analyzer.model_version,
                "prompt_version": self.analyzer.prompt_version,
                "analysis_status": InterviewAnalysisStatus.COMPLETED,
                "updated_at": now,
            }
        )
        self.repository.save_interview(updated)
        for candidate in analysis.review_tasks:
            task = ReviewTaskRecord(
                **candidate.model_dump(),
                id=self.repository.next_id("rev"),
                source_interview_ids=[interview.id],
                created_at=now,
                updated_at=now,
            )
            self.repository.save_review_task(task)
        event = ActivityEvent(
            id=self.repository.next_id("evt"),
            application_id=interview.application_id,
            operation_id=operation_id,
            event_type=EventType.INTERVIEW_ANALYZED,
            occurred_at=now,
            note=interview.id,
            sync_status=SyncStatus.COMPLETED,
        )
        self.repository.save_activity_event(event)
        return ToolReceipt(
            status="updated",
            message="Interview analysis saved with pending review tasks.",
            record_id=interview.id,
            operation_id=operation_id,
        )
```

- [ ] **Step 5: Run interview tests to verify they pass**

Run:

```bash
rtk python -m pytest tests/test_interview_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit interview analysis**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add src/job_hunt_agent/ai src/job_hunt_agent/prompts src/job_hunt_agent/services/interviews.py tests/test_interview_service.py
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "feat: add interview recording and analysis"
```

Expected: commit succeeds.

---

### Task 6: Reporting and MCP Tool Contracts

**Files:**
- Create: `src/job_hunt_agent/services/reporting.py`
- Create: `src/job_hunt_agent/mcp_server.py`
- Create: `tests/test_reporting_and_mcp_contract.py`

- [ ] **Step 1: Write failing tests for reporting and MCP tool registration**

Create `tests/test_reporting_and_mcp_contract.py`:

```python
from datetime import date, datetime, timezone

from job_hunt_agent.domain.models import ApplicationDraft
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.mcp_server import TOOL_NAMES
from job_hunt_agent.repositories import InMemoryJobHuntRepository
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.reporting import ReportingService


def test_list_follow_ups_includes_deadlines_and_next_steps() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    app_service.record_application(
        ApplicationDraft(
            company="Moonshot AI",
            role="AI Agent Engineer",
            deadline=date(2026, 8, 10),
            next_step="Submit referral resume.",
        ),
        operation_id="op-create",
    )
    reporting = ReportingService(repo)

    follow_ups = reporting.list_follow_ups(today=date(2026, 8, 3), days=10)

    assert follow_ups[0]["company"] == "Moonshot AI"
    assert follow_ups[0]["next_step"] == "Submit referral resume."


def test_generate_daily_review_counts_applications_and_stage_changes() -> None:
    repo = InMemoryJobHuntRepository()
    app_service = ApplicationService(repo, default_season="2026-autumn")
    created = app_service.record_application(
        ApplicationDraft(company="Zhipu AI", role="LLM Application Engineer"),
        operation_id="op-create",
    )
    app_service.update_application_stage(
        created.record_id,
        RecruitingStage.INTERVIEW,
        operation_id="op-stage",
        note="Written test passed.",
    )
    reporting = ReportingService(repo)

    review = reporting.generate_daily_review(day=date.today())

    assert "Applications created: 1" in review
    assert "Stage changes: 1" in review


def test_mcp_tool_names_match_design() -> None:
    assert TOOL_NAMES == [
        "record_application",
        "update_application_stage",
        "record_interview",
        "analyze_interview",
        "list_follow_ups",
        "generate_review",
    ]
```

- [ ] **Step 2: Run reporting and MCP contract tests to verify they fail**

Run:

```bash
rtk python -m pytest tests/test_reporting_and_mcp_contract.py -q
```

Expected: FAIL because reporting and MCP modules do not exist.

- [ ] **Step 3: Implement reporting service**

Create `src/job_hunt_agent/services/reporting.py`:

```python
from datetime import date, timedelta

from job_hunt_agent.domain.statuses import EventType
from job_hunt_agent.repositories import JobHuntRepository


class ReportingService:
    def __init__(self, repository: JobHuntRepository) -> None:
        self.repository = repository

    def list_follow_ups(self, today: date, days: int = 7) -> list[dict[str, str]]:
        end = today + timedelta(days=days)
        items: list[dict[str, str]] = []
        for record in self.repository.applications.values():
            if record.archived:
                continue
            if record.deadline is not None and today <= record.deadline <= end:
                items.append(
                    {
                        "application_id": record.id,
                        "company": record.company,
                        "role": record.role,
                        "deadline": record.deadline.isoformat(),
                        "next_step": record.next_step or "",
                    }
                )
        return sorted(items, key=lambda item: item["deadline"])

    def generate_daily_review(self, day: date) -> str:
        created = 0
        stage_changes = 0
        for event in self.repository.activity_events:
            if event.occurred_at.date() != day:
                continue
            if event.event_type is EventType.APPLICATION_CREATED:
                created += 1
            if event.event_type is EventType.STAGE_UPDATED:
                stage_changes += 1
        return "\n".join(
            [
                f"Daily review for {day.isoformat()}",
                f"Applications created: {created}",
                f"Stage changes: {stage_changes}",
            ]
        )
```

- [ ] **Step 4: Implement MCP server construction**

Create `src/job_hunt_agent/mcp_server.py`:

```python
from datetime import date
from uuid import uuid4

from job_hunt_agent.domain.models import ApplicationDraft, InterviewDraft
from job_hunt_agent.domain.statuses import RecruitingStage
from job_hunt_agent.services.applications import ApplicationService
from job_hunt_agent.services.interviews import InterviewService
from job_hunt_agent.services.reporting import ReportingService


TOOL_NAMES = [
    "record_application",
    "update_application_stage",
    "record_interview",
    "analyze_interview",
    "list_follow_ups",
    "generate_review",
]


def new_operation_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def build_mcp_server(
    application_service: ApplicationService,
    interview_service: InterviewService,
    reporting_service: ReportingService,
):
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install the project dependencies to run the MCP server.") from exc

    mcp = FastMCP("job-hunt-agent")

    @mcp.tool
    def record_application(payload: dict) -> dict:
        draft = ApplicationDraft.model_validate(payload)
        receipt = application_service.record_application(draft, new_operation_id("record-application"))
        return receipt.model_dump(mode="json")

    @mcp.tool
    def update_application_stage(application_id: str, to_stage: str, note: str | None = None) -> dict:
        receipt = application_service.update_application_stage(
            application_id=application_id,
            to_stage=RecruitingStage(to_stage),
            operation_id=new_operation_id("update-stage"),
            note=note,
        )
        return receipt.model_dump(mode="json")

    @mcp.tool
    def record_interview(payload: dict) -> dict:
        draft = InterviewDraft.model_validate(payload)
        receipt = interview_service.record_interview(draft, new_operation_id("record-interview"))
        return receipt.model_dump(mode="json")

    @mcp.tool
    def analyze_interview(interview_id: str) -> dict:
        receipt = interview_service.analyze_interview(interview_id, new_operation_id("analyze-interview"))
        return receipt.model_dump(mode="json")

    @mcp.tool
    def list_follow_ups(days: int = 7) -> list[dict[str, str]]:
        return reporting_service.list_follow_ups(today=date.today(), days=days)

    @mcp.tool
    def generate_review(kind: str = "daily") -> str:
        if kind != "daily":
            return "Weekly review generation will use the same event data in the next milestone."
        return reporting_service.generate_daily_review(day=date.today())

    return mcp
```

- [ ] **Step 5: Run reporting and MCP tests to verify they pass**

Run:

```bash
rtk python -m pytest tests/test_reporting_and_mcp_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit reporting and MCP contract**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add src/job_hunt_agent/services/reporting.py src/job_hunt_agent/mcp_server.py tests/test_reporting_and_mcp_contract.py
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "feat: expose mcp tool contract"
```

Expected: commit succeeds.

---

### Task 7: Docs, Synthetic Examples, and Verification Script

**Files:**
- Create: `docs/notion-setup.md`
- Create: `docs/privacy.md`
- Create: `examples/synthetic_inputs.jsonl`
- Create: `scripts/privacy_scan.py`
- Create: `tests/test_privacy_scan_script.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing script test**

Create `tests/test_privacy_scan_script.py`:

```python
from pathlib import Path

from scripts.privacy_scan import scan_paths


def test_scan_paths_reports_private_patterns(tmp_path: Path) -> None:
    leaked = tmp_path / "leaked.md"
    leaked.write_text(
        "https://www.notion" + ".so/private and " + "sk-" + "abc123456789SECRET",
        encoding="utf-8",
    )

    findings = scan_paths([leaked])

    assert len(findings) == 2
    assert {finding.kind for finding in findings} == {"notion_url", "api_key"}
```

- [ ] **Step 2: Run script test to verify it fails**

Run:

```bash
rtk python -m pytest tests/test_privacy_scan_script.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Add privacy scan script**

Create `scripts/privacy_scan.py`:

```python
from pathlib import Path
import sys

from job_hunt_agent.privacy import PrivacyFinding, scan_text_for_private_leaks


def scan_paths(paths: list[Path]) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    for path in paths:
        if path.is_dir():
            findings.extend(scan_paths([child for child in path.rglob("*") if child.is_file()]))
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(scan_text_for_private_leaks(text))
    return findings


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] if argv else [Path(".")]
    findings = scan_paths(paths)
    for finding in findings:
        print(f"{finding.kind}: {finding.value}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Add public docs and synthetic examples**

Create `docs/notion-setup.md`:

```markdown
# Notion Setup

Create four private Notion databases before enabling real writes:

- Applications
- Activity Log
- Interviews
- Review Tasks

Create a Notion integration, share only these databases with that integration, and put
the database IDs plus token in local environment variables. Do not paste the token into
chat logs or commit it to GitHub.
```

Create `docs/privacy.md`:

```markdown
# Privacy Rules

This repository is public-safe by design.

- Keep `.env` out of Git.
- Use synthetic examples in `examples/`.
- Do not commit real company pipelines, interview notes, contacts, Notion URLs, or keys.
- Run `rtk python scripts/privacy_scan.py README.md docs examples src tests` before publishing.
```

Create `examples/synthetic_inputs.jsonl`:

```jsonl
{"intent":"record_application","text":"I applied to ExampleAI for LLM Application Engineer through campus portal.","expected_tool":"record_application"}
{"intent":"record_interview","text":"ExampleAI first round asked about RAG chunking and Hybrid Search. I did not record my answer.","expected_tool":"record_interview"}
```

Append this section to `README.md`:

```markdown

## Notion Setup

See `docs/notion-setup.md`. The first local milestone can run entirely on the in-memory
repository used by tests. Real Notion writes are enabled only after private database IDs
and token are configured locally.

## Verification

```bash
rtk python -m pytest -q
rtk python scripts/privacy_scan.py README.md docs examples src tests
```
```

- [ ] **Step 5: Run script test and full unit suite**

Run:

```bash
rtk python -m pytest tests/test_privacy_scan_script.py -q
rtk python -m pytest -q
```

Expected: both commands PASS.

- [ ] **Step 6: Run privacy scan**

Run:

```bash
rtk python scripts/privacy_scan.py README.md docs examples src tests
```

Expected: exit code 0 and no findings.

- [ ] **Step 7: Commit docs and verification script**

Run:

```bash
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 add README.md docs/notion-setup.md docs/privacy.md examples scripts tests/test_privacy_scan_script.py
rtk git -c safe.directory=C:/Users/<username>/Desktop/秋招 commit -m "docs: add setup privacy and synthetic examples"
```

Expected: commit succeeds.

---

## Self-Review

### Spec Coverage

- Natural-language entry through Codex maps to MCP tool contracts in Task 6.
- Notion as private source of truth is protected by the repository boundary in Task 4 and setup docs in Task 7.
- Public code with private real data is covered by `.gitignore`, `.env.example`, privacy scanner, docs, and synthetic examples in Tasks 1, 3, and 7.
- Applications, Activity Log, Interviews, and Review Tasks are represented by domain models in Task 2.
- Application creation, dedupe, idempotency, and stage updates are covered in Task 4.
- Interview raw notes, DeepSeek-compatible analysis, non-fabrication validation, and pending review tasks are covered in Task 5.
- Follow-ups and daily review are covered in Task 6. Weekly review remains a second milestone item documented by the `generate_review` tool response.
- Real Notion writes are intentionally gated behind setup because credentials and database IDs must stay private.

### Placeholder Scan

The plan avoids empty markers and includes exact file paths, code snippets, commands, and expected outcomes for each task.

### Type Consistency

- `ApplicationDraft`, `ApplicationRecord`, and `ToolReceipt` are defined in Task 2 and used by Tasks 4 and 6.
- `InterviewAnalysis`, `InterviewDraft`, `InterviewRecord`, and `ReviewTaskCandidate` are defined in Task 2 and used by Task 5.
- `InMemoryJobHuntRepository` is defined in Task 4 and used by service/reporting tests.
- `TOOL_NAMES` is defined in Task 6 and checked against the design tool list.

## Execution Choice

Default execution for this workspace is inline execution in the current session because multi-agent work is not enabled unless explicitly requested. Use `executing-plans` before marking checkboxes or changing code.
