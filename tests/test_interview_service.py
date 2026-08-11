from job_hunt_agent.domain.models import (
    ApplicationDraft,
    InterviewAnalysis,
    InterviewDraft,
    ReviewTaskCandidate,
)
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
            source_excerpts=["Asked about Hybrid Search"],
            better_answer_ideas=[
                "Compare BM25-only, vector-only, and hybrid retrieval on the same queries."
            ],
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


class FailingAnalyzer:
    model_version = "failing-deepseek"
    prompt_version = "interview-analysis-v1"

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        raise RuntimeError("model unavailable")


class BadEvidenceAnalyzer:
    model_version = "bad-evidence"
    prompt_version = "interview-analysis-v1"

    def analyze(self, raw_notes: str) -> InterviewAnalysis:
        return InterviewAnalysis(
            overview="Analysis with an unsupported quote.",
            evidence_based_performance=["The candidate struggled."],
            source_excerpts=["This sentence is not in the raw notes."],
        )


def make_application(repo: InMemoryJobHuntRepository) -> str:
    service = ApplicationService(repo, default_season="2026-autumn")
    receipt = service.record_application(
        ApplicationDraft(company="DeepSeek", role="LLM Application Engineer"),
        operation_id="op-app",
    )
    assert receipt.record_id is not None
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
    assert created.record_id is not None

    receipt = service.analyze_interview(created.record_id, operation_id="op-analysis")

    interview = repo.get_interview(created.record_id)
    assert receipt.status == "updated"
    assert interview.analysis_status is InterviewAnalysisStatus.COMPLETED
    assert interview.structured_analysis is not None
    assert interview.structured_analysis.answer_summary is None
    assert len(repo.review_tasks) == 1
    task = next(iter(repo.review_tasks.values()))
    assert task.confirmation_status == "pending"
    assert task.source_interview_ids == [created.record_id]


def test_analyze_interview_returns_failed_receipt_when_analyzer_fails() -> None:
    repo = InMemoryJobHuntRepository()
    application_id = make_application(repo)
    service = InterviewService(repo, analyzer=FailingAnalyzer())
    created = service.record_interview(
        InterviewDraft(
            application_id=application_id,
            round_name="first round",
            raw_notes="Asked about Hybrid Search.",
        ),
        operation_id="op-interview",
    )
    assert created.record_id is not None

    receipt = service.analyze_interview(created.record_id, operation_id="op-analysis")

    interview = repo.get_interview(created.record_id)
    assert receipt.status == "failed"
    assert receipt.warnings == ["RuntimeError"]
    assert interview.analysis_status is InterviewAnalysisStatus.FAILED
    assert len(repo.review_tasks) == 0


def test_analyze_interview_rejects_source_excerpts_missing_from_raw_notes() -> None:
    repo = InMemoryJobHuntRepository()
    application_id = make_application(repo)
    service = InterviewService(repo, analyzer=BadEvidenceAnalyzer())
    created = service.record_interview(
        InterviewDraft(
            application_id=application_id,
            round_name="first round",
            raw_notes="Asked about Hybrid Search.",
        ),
        operation_id="op-interview",
    )
    assert created.record_id is not None

    receipt = service.analyze_interview(created.record_id, operation_id="op-analysis")

    assert receipt.status == "failed"
    assert receipt.warnings == ["ValueError"]


def test_record_interview_returns_failed_receipt_for_unknown_application() -> None:
    repo = InMemoryJobHuntRepository()
    service = InterviewService(repo, analyzer=FakeAnalyzer())

    receipt = service.record_interview(
        InterviewDraft(
            application_id="missing",
            round_name="first round",
            raw_notes="Asked about Hybrid Search.",
        ),
        operation_id="op-interview",
    )

    assert receipt.status == "failed"
    assert receipt.record_id == "missing"
    assert receipt.warnings == ["KeyError"]


def test_analyze_interview_merges_repeated_review_tasks() -> None:
    repo = InMemoryJobHuntRepository()
    application_id = make_application(repo)
    service = InterviewService(repo, analyzer=FakeAnalyzer())
    first = service.record_interview(
        InterviewDraft(
            application_id=application_id,
            round_name="first round",
            raw_notes="Asked about Hybrid Search.",
        ),
        operation_id="op-interview-1",
    )
    second = service.record_interview(
        InterviewDraft(
            application_id=application_id,
            round_name="second round",
            raw_notes="Asked about Hybrid Search again.",
        ),
        operation_id="op-interview-2",
    )
    assert first.record_id is not None
    assert second.record_id is not None

    service.analyze_interview(first.record_id, operation_id="op-analysis-1")
    service.analyze_interview(second.record_id, operation_id="op-analysis-2")

    assert len(repo.review_tasks) == 1
    task = next(iter(repo.review_tasks.values()))
    assert task.occurrences == 2
    assert task.source_interview_ids == [first.record_id, second.record_id]
