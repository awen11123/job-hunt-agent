from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from job_hunt_agent.interviews import LocalInterviewDraft, LocalInterviewStore
from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.web import create_app


SESSION_TOKEN = "test-session-token"
HEADERS = (
    "企业",
    "投递岗位",
    "投递日期",
    "所在地",
    "当前状态",
    "下一节点",
    "节点时间",
    "岗位链接",
    "备注",
)


def build_tracker(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "投递总览"
    sheet.append(HEADERS)
    sheet.append(
        [
            "示例科技",
            "Agent 工程师",
            datetime.now(UTC).date(),
            "杭州",
            "已投递",
            "等待筛选",
            None,
            "查看岗位",
            "已有记录",
        ]
    )
    sheet["H2"].hyperlink = "https://example.com/job"
    workbook.save(path)
    workbook.close()
    return path


def build_config_store(tmp_path: Path, *, configured: bool = True) -> LocalConfigStore:
    store = LocalConfigStore(tmp_path / "config.json")
    config = LocalAppConfig.defaults(tmp_path / "app-data")
    if configured:
        config.excel_path = build_tracker(tmp_path / "tracker.xlsx")
    store.save(config)
    return store


@pytest.fixture
def configured_store(tmp_path: Path) -> LocalConfigStore:
    return build_config_store(tmp_path)


@pytest.fixture
def client(configured_store: LocalConfigStore) -> TestClient:
    return TestClient(create_app(configured_store, session_token=SESSION_TOKEN))


def session_headers(token: str = SESSION_TOKEN) -> dict[str, str]:
    return {"X-Job-Hunt-Session": token}


def test_health_application_list_and_docs_are_private(client: TestClient) -> None:
    health = client.get("/api/health")
    applications = client.get("/api/applications")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert applications.status_code == 200
    assert applications.json()[0]["company"] == "示例科技"
    assert applications.json()[0]["job_url"] == "https://example.com/job"
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_app_starts_without_excel_and_lists_return_safe_conflict(tmp_path: Path) -> None:
    client = TestClient(
        create_app(build_config_store(tmp_path, configured=False), session_token=SESSION_TOKEN)
    )

    response = client.get("/api/applications")

    assert client.get("/api/health").status_code == 200
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "excel_not_configured"
    assert "test-session-token" not in response.text


def test_unavailable_excel_returns_safe_conflict(tmp_path: Path) -> None:
    store = build_config_store(tmp_path, configured=False)
    config = store.load()
    config.excel_path = tmp_path / "missing-private-name.xlsx"
    store.save(config)
    client = TestClient(create_app(store, session_token=SESSION_TOKEN))

    response = client.get("/api/applications")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "excel_unavailable"
    assert "missing-private-name" not in response.text


def test_config_is_whitelisted_persisted_and_refreshes_services(tmp_path: Path) -> None:
    store = build_config_store(tmp_path, configured=False)
    client = TestClient(create_app(store, session_token=SESSION_TOKEN))
    workbook_path = build_tracker(tmp_path / "later.xlsx")
    saved = store.load().model_copy(update={"excel_path": workbook_path})

    get_response = client.get("/api/config")
    missing = client.put("/api/config", json=saved.model_dump(mode="json"))
    wrong = client.put(
        "/api/config",
        headers=session_headers("wrong-session-token"),
        json=saved.model_dump(mode="json"),
    )
    updated = client.put(
        "/api/config",
        headers=session_headers(),
        json=saved.model_dump(mode="json"),
    )

    assert set(get_response.json()) == {
        "excel_path",
        "backup_dir",
        "interview_dir",
        "notion_enabled",
        "model_enabled",
    }
    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert "wrong-session-token" not in wrong.text
    assert updated.status_code == 200
    assert store.load() == saved
    assert client.get("/api/applications").status_code == 200


def test_propose_is_preview_only_and_confirmation_writes_once(client: TestClient) -> None:
    before = client.get("/api/applications").json()

    proposed = client.post(
        "/api/actions/propose",
        json={"text": "今天投了新增科技的 AI Agent 工程师，杭州"},
    )

    assert proposed.status_code == 200
    preview = proposed.json()
    assert preview["status"] == "pending"
    assert preview["action"] == "create_application"
    assert client.get("/api/applications").json() == before

    missing_session = client.post(
        f"/api/actions/{preview['id']}/confirm",
        json={"confirmation_token": preview["confirmation_token"]},
    )
    wrong_session = client.post(
        f"/api/actions/{preview['id']}/confirm",
        headers=session_headers("wrong-session-token"),
        json={"confirmation_token": preview["confirmation_token"]},
    )
    wrong_confirmation = client.post(
        f"/api/actions/{preview['id']}/confirm",
        headers=session_headers(),
        json={"confirmation_token": "wrong-confirmation-token"},
    )
    first = client.post(
        f"/api/actions/{preview['id']}/confirm",
        headers=session_headers(),
        json={"confirmation_token": preview["confirmation_token"]},
    )
    second = client.post(
        f"/api/actions/{preview['id']}/confirm",
        headers=session_headers(),
        json={"confirmation_token": preview["confirmation_token"]},
    )

    assert missing_session.status_code == 401
    assert wrong_session.status_code == 403
    assert "wrong-session-token" not in wrong_session.text
    assert wrong_confirmation.status_code == 403
    assert "wrong-confirmation-token" not in wrong_confirmation.text
    assert first.status_code == 200
    assert first.json()["receipt"]["status"] == "created"
    assert second.json() == first.json()
    after = client.get("/api/applications").json()
    assert len(after) == len(before) + 1
    assert sum(record["company"] == "新增科技" for record in after) == 1


def test_cancel_requires_session_and_cancelled_draft_cannot_execute(
    client: TestClient,
) -> None:
    preview = client.post(
        "/api/actions/propose",
        json={"text": "今天投了取消科技的 AI Agent 工程师，上海"},
    ).json()

    missing = client.post(f"/api/actions/{preview['id']}/cancel")
    cancelled = client.post(
        f"/api/actions/{preview['id']}/cancel",
        headers=session_headers(),
    )
    confirmed = client.post(
        f"/api/actions/{preview['id']}/confirm",
        headers=session_headers(),
        json={"confirmation_token": preview["confirmation_token"]},
    )

    assert missing.status_code == 401
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert confirmed.status_code == 409
    assert confirmed.json()["detail"]["code"] == "draft_cancelled"
    assert all(
        application["company"] != "取消科技"
        for application in client.get("/api/applications").json()
    )


def test_unknown_draft_and_invalid_requests_have_stable_statuses(client: TestClient) -> None:
    assert client.get("/api/actions/missing").status_code == 404
    assert client.post("/api/actions/propose", json={}).status_code == 422
    unsupported = client.post("/api/actions/propose", json={"text": "本周投了多少家"})
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["code"] == "unsupported_input"


def test_execution_failure_is_safe_and_keeps_draft_pending(client: TestClient) -> None:
    preview = client.post(
        "/api/actions/propose",
        json={"text": "今天投了示例科技的 Agent 工程师，杭州"},
    ).json()

    response = client.post(
        f"/api/actions/{preview['id']}/confirm",
        headers=session_headers(),
        json={"confirmation_token": preview["confirmation_token"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "create_application_failed",
        "message": "Application creation failed.",
    }
    assert "示例科技" not in response.text
    assert client.get(f"/api/actions/{preview['id']}").json()["status"] == "pending"


def test_interviews_list_and_optional_application_filter(
    configured_store: LocalConfigStore,
) -> None:
    config = configured_store.load()
    interview_store = LocalInterviewStore(config.interview_dir)
    first = interview_store.save(
        LocalInterviewDraft(
            application_id="app-first",
            company="甲公司",
            round_name="技术一面",
            raw_notes="甲公司的面试记录。",
        ),
        operation_id="first-interview",
    )
    interview_store.save(
        LocalInterviewDraft(
            application_id="app-second",
            company="乙公司",
            round_name="技术二面",
            raw_notes="乙公司的面试记录。",
        ),
        operation_id="second-interview",
    )
    client = TestClient(create_app(configured_store, session_token=SESSION_TOKEN))

    all_records = client.get("/api/interviews")
    filtered = client.get("/api/interviews", params={"application_id": "app-first"})

    assert all_records.status_code == 200
    assert len(all_records.json()) == 2
    assert filtered.status_code == 200
    assert [record["id"] for record in filtered.json()] == [first.id]
    assert filtered.json()[0]["raw_notes"] == "甲公司的面试记录。"
