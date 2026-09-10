# Windows Local Web MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a developer-runnable local web application that manages an Excel application tracker and local Markdown interview notes without requiring an LLM or Notion.

**Architecture:** A FastAPI process binds to `127.0.0.1` and serves a React/TypeScript application. New package-level Excel and local-interview repositories provide durable storage, while an action-draft service separates parsing from confirmed writes.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, openpyxl, React 19, TypeScript, Vite, Vitest, pytest

---

### Task 1: Add Local Application Configuration

**Files:**
- Create: `src/job_hunt_agent/local_app/__init__.py`
- Create: `src/job_hunt_agent/local_app/paths.py`
- Create: `src/job_hunt_agent/local_app/config.py`
- Create: `tests/test_local_app_config.py`

- [x] **Step 1: Write the failing configuration tests**

```python
from pathlib import Path

from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore


def test_local_config_round_trip_excludes_secrets(tmp_path: Path) -> None:
    store = LocalConfigStore(tmp_path / "config.json")
    config = LocalAppConfig(
        excel_path=tmp_path / "applications.xlsx",
        backup_dir=tmp_path / "backups",
        interview_dir=tmp_path / "interviews",
    )

    store.save(config)

    assert store.load() == config
    assert "token" not in store.path.read_text(encoding="utf-8").lower()


def test_default_paths_are_below_supplied_app_data_root(tmp_path: Path) -> None:
    config = LocalAppConfig.defaults(tmp_path)

    assert config.backup_dir == tmp_path / "backups"
    assert config.interview_dir == tmp_path / "interviews"
```

- [x] **Step 2: Run the tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_local_app_config.py`

Expected: FAIL with `ModuleNotFoundError: job_hunt_agent.local_app`.

- [x] **Step 3: Implement the configuration model and atomic JSON store**

```python
class LocalAppConfig(BaseModel):
    excel_path: Path | None = None
    backup_dir: Path
    interview_dir: Path
    notion_enabled: bool = False
    model_enabled: bool = False

    @classmethod
    def defaults(cls, app_data_root: Path) -> "LocalAppConfig":
        return cls(
            backup_dir=app_data_root / "backups",
            interview_dir=app_data_root / "interviews",
        )


class LocalConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> LocalAppConfig:
        return LocalAppConfig.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, config: LocalAppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)
```

`paths.py` must expose `app_data_root()` using `%APPDATA%/JobHuntAgent` on Windows and `~/.local/share/job-hunt-agent` elsewhere.

- [x] **Step 4: Run the tests and verify GREEN**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_local_app_config.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/local_app tests/test_local_app_config.py
rtk proxy git commit -m "feat: add local app configuration"
```

### Task 2: Add the Excel Application Repository

**Files:**
- Create: `src/job_hunt_agent/excel/__init__.py`
- Create: `src/job_hunt_agent/excel/models.py`
- Create: `src/job_hunt_agent/excel/repository.py`
- Create: `tests/test_excel_application_repository.py`

- [x] **Step 1: Write failing repository tests with a synthetic workbook**

```python
def test_repository_lists_rows_and_preserves_links(tmp_path: Path) -> None:
    workbook_path = build_synthetic_tracker(tmp_path / "tracker.xlsx")
    repository = ExcelApplicationRepository(workbook_path, tmp_path / "backups")

    records = repository.list_applications()

    assert records[0].company == "示例科技"
    assert str(records[0].job_url) == "https://example.com/job"


def test_confirmed_create_makes_backup_and_preserves_existing_styles(tmp_path: Path) -> None:
    workbook_path = build_synthetic_tracker(tmp_path / "tracker.xlsx")
    repository = ExcelApplicationRepository(workbook_path, tmp_path / "backups")
    before = load_workbook(workbook_path)

    created = repository.create_application(
        TrackerApplicationDraft(company="示例旅行", role="Agent 工程师")
    )

    after = load_workbook(workbook_path)
    assert created.id.startswith("app_")
    assert len(list((tmp_path / "backups").glob("*.xlsx"))) == 1
    assert after["投递总览"]["A3"]._style == before["投递总览"]["A2"]._style
```

Add tests for duplicate company-role rejection, stage updates, WPS file-lock errors, merged cells, the gray closed-process divider, and atomic replacement failure.

- [x] **Step 2: Run the tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_excel_application_repository.py`

Expected: FAIL because `job_hunt_agent.excel` does not exist.

- [x] **Step 3: Implement exact Excel row models**

```python
class TrackerApplication(BaseModel):
    id: str
    company: str
    role: str
    applied_date: date | None = None
    location: str | None = None
    status: str
    next_step: str | None = None
    next_time: date | None = None
    job_url: HttpUrl | None = None
    notes: str | None = None


class TrackerApplicationDraft(BaseModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    applied_date: date = Field(default_factory=date.today)
    location: str | None = None
    status: str = "已投递"
    next_step: str = "等待筛选"
    next_time: date | None = None
    job_url: HttpUrl | None = None
    notes: str | None = None
```

Derive stable IDs from normalized company, role, and application date. Do not add hidden Excel columns.

- [x] **Step 4: Implement guarded workbook reads and writes**

`ExcelApplicationRepository` must expose four exact methods: `list_applications()` returns
newest-first `TrackerApplication` records; `get_application(application_id)` raises `KeyError`
for an unknown stable ID; `create_application(draft)` rejects a normalized company-role-date
duplicate before writing; and `update_application(application_id, changes)` applies a validated
`TrackerApplicationPatch` through the guarded workbook mutation path.

Reuse the existing snapshot, hyperlink, merge, backup, and atomic-replace behavior from `scripts/wps_job_tracker.py`, `scripts/compact_wps_job_tracker.py`, and `scripts/optimize_wps_job_tracker.py`. Package code must not import from `scripts`.

- [x] **Step 5: Run repository tests and the existing WPS tests**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_excel_application_repository.py tests/test_wps_job_tracker.py tests/test_compact_wps_job_tracker.py tests/test_optimize_wps_job_tracker.py`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
rtk proxy git add src/job_hunt_agent/excel tests/test_excel_application_repository.py
rtk proxy git commit -m "feat: add Excel application repository"
```

### Task 3: Add the Local Markdown Interview Store

**Files:**
- Create: `src/job_hunt_agent/interviews/__init__.py`
- Create: `src/job_hunt_agent/interviews/local_store.py`
- Create: `tests/test_local_interview_store.py`

- [x] **Step 1: Write failing local-store tests**

```python
def test_local_store_writes_private_markdown_and_index(tmp_path: Path) -> None:
    store = LocalInterviewStore(tmp_path)
    interview = LocalInterviewDraft(
        application_id="app_demo",
        company="示例科技",
        round_name="技术一面",
        raw_notes="讨论了 Agent 状态管理。",
    )

    saved = store.save(interview, operation_id="save-interview-1")

    assert saved.markdown_path.read_text(encoding="utf-8").startswith("# 示例科技")
    assert store.get(saved.id).raw_notes == interview.raw_notes
    assert store.save(interview, operation_id="save-interview-1").id == saved.id
```

Add tests for filename sanitization, JSON index atomic replacement, missing files, and UTF-8 content.

- [x] **Step 2: Run the tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_local_interview_store.py`

Expected: FAIL because `LocalInterviewStore` does not exist.

- [x] **Step 3: Implement the store**

`LocalInterviewStore` must expose four exact methods: `save(draft, operation_id)` performs an
idempotent write; `get(interview_id)` raises `KeyError` when absent; `list(application_id=None)`
returns newest-first records with optional application filtering; and
`mark_sync(interview_id, status, notion_page_id=None)` accepts only `local`, `pending`, `synced`,
or `failed` and atomically updates the index.

Use `index.json` for metadata and one Markdown file per interview. Write both through temporary files and replace only after validation.

- [x] **Step 4: Run tests and verify GREEN**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_local_interview_store.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/interviews tests/test_local_interview_store.py
rtk proxy git commit -m "feat: add local interview store"
```

### Task 4: Add Action Drafts and Explicit Confirmation

**Files:**
- Create: `src/job_hunt_agent/actions/__init__.py`
- Create: `src/job_hunt_agent/actions/models.py`
- Create: `src/job_hunt_agent/actions/service.py`
- Create: `tests/test_action_draft_service.py`

- [x] **Step 1: Write failing confirmation-flow tests**

```python
def test_write_request_creates_preview_without_mutating_repository() -> None:
    repository = RecordingExcelRepository()
    service = ActionDraftService(repository, clock=fixed_clock)

    draft = service.propose_application("今天投了示例科技的 Agent 工程师")

    assert draft.status == "pending"
    assert draft.action == "create_application"
    assert repository.created == []


def test_confirmation_executes_once() -> None:
    service = configured_service()
    draft = service.propose_application("今天投了示例科技的 Agent 工程师")

    first = service.confirm(draft.id, draft.confirmation_token)
    second = service.confirm(draft.id, draft.confirmation_token)

    assert first.receipt.status == "created"
    assert second.receipt.status == "unchanged"
```

Add tests for cancellation, expired tokens, modified drafts, read-only requests, and unsupported free-form input without a model.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_action_draft_service.py`

Expected: FAIL because the action package does not exist.

- [x] **Step 3: Implement action models and in-memory draft storage**

```python
class ActionDraft(BaseModel):
    id: str
    action: Literal["create_application", "update_application", "save_interview"]
    payload: dict[str, object]
    before: dict[str, object] | None = None
    status: Literal["pending", "confirmed", "cancelled", "expired"] = "pending"
    confirmation_token: str
    operation_id: str
    expires_at: datetime


```

`ActionDraftService` must expose `propose_application(text)`, `modify(draft_id, payload)`,
`cancel(draft_id)`, and `confirm(draft_id, confirmation_token)`. `confirm` validates pending
status, expiry, and token with `secrets.compare_digest`, then stores the execution receipt before
returning so a repeated call returns the same result without another repository write.

Use the existing `parse_application_text` function for no-model parsing. Store drafts only in process memory in the MVP, so an application restart cannot accidentally execute an old draft.

- [x] **Step 4: Run tests and verify GREEN**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_action_draft_service.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/actions tests/test_action_draft_service.py
rtk proxy git commit -m "feat: add confirmed action drafts"
```

### Task 5: Add the FastAPI Application

**Files:**
- Modify: `pyproject.toml`
- Create: `src/job_hunt_agent/web/__init__.py`
- Create: `src/job_hunt_agent/web/app.py`
- Create: `src/job_hunt_agent/web/dependencies.py`
- Create: `src/job_hunt_agent/web/schemas.py`
- Create: `tests/test_web_api.py`

- [x] **Step 1: Add FastAPI and Uvicorn dependencies**

```toml
dependencies = [
  "fastapi>=0.115.0",
  "fastmcp>=2.0.0",
  "httpx>=0.27.0",
  "openpyxl>=3.1.5",
  "pydantic>=2.7.0",
  "python-dotenv>=1.0.1",
  "uvicorn>=0.30.0",
]
```

- [x] **Step 2: Write failing API tests**

```python
def test_health_and_application_list(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/applications").status_code == 200


def test_chat_write_returns_preview_then_requires_confirmation(client: TestClient) -> None:
    proposed = client.post("/api/actions/propose", json={"text": "今天投了示例科技的 Agent 工程师"})
    assert proposed.status_code == 200
    assert proposed.json()["status"] == "pending"

    confirmed = client.post(
        f"/api/actions/{proposed.json()['id']}/confirm",
        headers={"X-Job-Hunt-Session": client.session_token},
        json={"confirmation_token": proposed.json()["confirmation_token"]},
    )
    assert confirmed.json()["receipt"]["status"] == "created"
```

Add tests that write endpoints reject missing session tokens, invalid Excel configuration returns `409`, and cancelled drafts cannot execute.

- [x] **Step 3: Implement the application factory**

```python
def create_app(config_store: LocalConfigStore, session_token: str | None = None) -> FastAPI:
    app = FastAPI(title="Job Hunt Agent", docs_url=None, redoc_url=None)
    app.state.session_token = session_token or secrets.token_urlsafe(32)
    app.include_router(build_api_router(build_services(config_store)))
    return app
```

Expose `/api/health`, `/api/config`, `/api/applications`, `/api/interviews`, `/api/actions/propose`, `/api/actions/{id}`, `/confirm`, and `/cancel`. All mutation routes require `X-Job-Hunt-Session`.

- [x] **Step 4: Run API and full Python tests**

Run: `rtk proxy python -X utf8 -m pytest -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add pyproject.toml src/job_hunt_agent/web tests/test_web_api.py
rtk proxy git commit -m "feat: expose local web API"
```

### Task 6: Scaffold the React and TypeScript Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/App.test.tsx`

- [x] **Step 1: Add the frontend package manifest**

Use React, TypeScript, Vite, Vitest, Testing Library, and `lucide-react`. Add scripts `dev`, `build`, `test`, and `typecheck`.

- [x] **Step 2: Write the failing application-shell test**

```tsx
it("renders the operational navigation", () => {
  render(<App api={fakeApi} />);
  expect(screen.getByRole("tab", { name: "投递看板" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "面经" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "复盘" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "设置" })).toBeInTheDocument();
});
```

- [x] **Step 3: Install dependencies and verify RED**

Run: `rtk proxy npm install`

Run: `rtk proxy npm test -- --run`

Expected: FAIL because the application shell is not implemented.

- [x] **Step 4: Implement the typed API client and shell**

```ts
export interface JobHuntApi {
  listApplications(): Promise<Application[]>;
  proposeAction(text: string): Promise<ActionDraft>;
  confirmAction(id: string, token: string): Promise<ActionExecution>;
  cancelAction(id: string): Promise<ActionDraft>;
}
```

Implement a compact header, tab navigation, main work surface, and collapsible assistant panel. Keep all dimensions stable and use Lucide icons for icon buttons.

- [x] **Step 5: Run frontend tests and type checks**

Run: `rtk proxy npm test -- --run`

Run: `rtk proxy npm run typecheck`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
rtk proxy git add frontend
rtk proxy git commit -m "feat: scaffold local web frontend"
```

### Task 7: Build the Dashboard, Interview View, and Confirmed Chat Flow

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/StatusSummary.tsx`
- Create: `frontend/src/components/ApplicationTable.tsx`
- Create: `frontend/src/components/AssistantPanel.tsx`
- Create: `frontend/src/components/ActionPreview.tsx`
- Create: `frontend/src/views/ApplicationsView.tsx`
- Create: `frontend/src/views/InterviewsView.tsx`
- Create: `frontend/src/views/ReviewView.tsx`
- Create: `frontend/src/views/SettingsView.tsx`
- Create: `frontend/src/components/AppShell.test.tsx`
- Create: `frontend/src/components/AssistantPanel.test.tsx`

- [x] **Step 1: Write failing interaction tests**

```tsx
it("never confirms a write directly from a chat message", async () => {
  render(<AssistantPanel api={fakeApi} />);
  await userEvent.type(screen.getByRole("textbox"), "今天投了示例科技的 Agent 工程师");
  await userEvent.click(screen.getByRole("button", { name: "发送" }));

  expect(fakeApi.proposeAction).toHaveBeenCalledTimes(1);
  expect(fakeApi.confirmAction).not.toHaveBeenCalled();
  expect(screen.getByText("变更预览")).toBeInTheDocument();
});
```

Add tests for search, status filters, closed-process separation, preview edit/cancel/confirm, Excel-lock errors, and empty states.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy npm test -- --run`

Expected: FAIL because the view components do not exist.

- [x] **Step 3: Implement the operational UI**

Use an unframed page layout with a constrained work area. The dashboard must show summary metrics, filters, and a stable table; the assistant panel must render read responses separately from action previews. Do not add tutorial copy or nested cards.

- [x] **Step 4: Run frontend tests, type checks, and production build**

Run: `rtk proxy npm test -- --run`

Run: `rtk proxy npm run typecheck`

Run: `rtk proxy npm run build`

Expected: PASS and `frontend/dist/index.html` exists.

- [x] **Step 5: Commit**

```bash
rtk proxy git add frontend
rtk proxy git commit -m "feat: add job tracking web experience"
```

### Task 8: Serve the Frontend and Add a Developer Launcher

**Files:**
- Modify: `src/job_hunt_agent/web/app.py`
- Create: `src/job_hunt_agent/web/launcher.py`
- Create: `tests/test_web_launcher.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing static-serving and launcher tests**

```python
def test_app_serves_built_frontend(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<main>Job Hunt Agent</main>", encoding="utf-8")

    app = create_app(config_store(), static_dir=frontend)
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Job Hunt Agent" in response.text


def test_launcher_binds_loopback_and_opens_browser_after_health_check() -> None:
    launcher = LocalLauncher(server=fake_server, browser=fake_browser)
    launcher.run()

    assert fake_server.host == "127.0.0.1"
    assert fake_browser.opened_after_health_check is True
```

Add an integration test proving the served page receives the non-empty in-memory session token
expected by `frontend/src/main.tsx`, and that the token can authorize confirm/cancel requests. The
token must not appear in the URL, logs, configuration file, or other persistent storage.

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_web_launcher.py`

Expected: FAIL because the launcher does not exist.

- [ ] **Step 3: Implement static serving and `python -m` launcher**

The launcher must select a free loopback port, start Uvicorn, poll `/api/health`, and only then call
`webbrowser.open`. Static `index.html` responses must inject the current process session token into
the root element's `data-session-token` attribute without modifying the built file on disk. Add
`python -m job_hunt_agent.web.launcher` to the README.

- [ ] **Step 4: Run complete MVP verification**

Run: `rtk proxy python -X utf8 -m pytest -q`

Run: `rtk proxy npm test -- --run` in `frontend`.

Run: `rtk proxy npm run typecheck` in `frontend`.

Run: `rtk proxy npm run build` in `frontend`.

Run: `rtk proxy python -X utf8 scripts/privacy_scan.py README.md docs examples frontend scripts src tests`

Expected: all commands pass with no privacy findings.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add README.md src/job_hunt_agent/web tests/test_web_launcher.py
rtk proxy git commit -m "feat: run the local web MVP"
```
