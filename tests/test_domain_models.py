from datetime import datetime, timezone

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
