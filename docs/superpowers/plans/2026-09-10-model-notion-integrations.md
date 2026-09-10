# Model and Notion Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider-neutral LLM capabilities, secure credential storage, and local-first Notion interview synchronization to the working local Web MVP.

**Architecture:** Business services depend on an `LLMProvider` protocol and an `InterviewSyncTarget` protocol. Model output can create action drafts but cannot execute tools; interview writes always land locally before optional Notion synchronization.

**Tech Stack:** Python 3.12, httpx, Pydantic, keyring, FastAPI, React, TypeScript, pytest, Vitest

---

### Task 1: Introduce the Provider-Neutral LLM Contract

**Files:**
- Create: `src/job_hunt_agent/ai/provider.py`
- Create: `src/job_hunt_agent/ai/openai_compatible.py`
- Modify: `src/job_hunt_agent/ai/deepseek.py`
- Modify: `src/job_hunt_agent/ai/__init__.py`
- Create: `tests/test_llm_provider.py`

- [x] **Step 1: Write failing provider-contract tests**

```python
def test_openai_compatible_provider_validates_structured_output() -> None:
    transport = StubTransport(content='{"action":"query","arguments":{}}')
    provider = OpenAICompatibleProvider(
        config=ProviderConfig(
            name="custom",
            base_url="https://example.com/v1",
            model="example-chat",
            api_key="test-key",
        ),
        transport=transport,
    )

    result = provider.complete_structured([], ActionPlan)

    assert result == ActionPlan(action="query", arguments={})
    assert transport.last_url == "https://example.com/v1/chat/completions"


def test_ollama_provider_omits_authorization_header() -> None:
    provider = OpenAICompatibleProvider(ProviderConfig.ollama("qwen3:8b"), StubTransport())
    provider.complete_structured([], ActionPlan)
    assert "Authorization" not in provider.transport.last_headers
```

Add tests for malformed JSON, HTTP timeout, missing API key for remote providers, and error messages that never contain response bodies or keys.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_llm_provider.py`

Expected: FAIL because the provider-neutral classes do not exist.

- [x] **Step 3: Implement the protocol and generic adapter**

```python
class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def complete_structured(
        self,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
    ) -> ResponseT:
        raise NotImplementedError


class ProviderConfig(BaseModel):
    name: Literal["deepseek", "qwen", "moonshot", "openai-compatible", "ollama"]
    base_url: HttpUrl
    model: str
    api_key: SecretStr | None = None
```

`OpenAICompatibleProvider` must use `httpx.Client`, send `/chat/completions`, request JSON output when supported, and validate the response with the supplied Pydantic model. Refactor `DeepSeekInterviewAnalyzer` to delegate transport and validation to this adapter.

- [x] **Step 4: Run provider and existing interview tests**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_llm_provider.py tests/test_interview_service.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/ai tests/test_llm_provider.py
rtk proxy git commit -m "feat: add provider-neutral LLM interface"
```

### Task 2: Add Provider Presets and Secure Credential Storage

**Files:**
- Modify: `pyproject.toml`
- Create: `src/job_hunt_agent/local_app/secrets.py`
- Create: `src/job_hunt_agent/ai/presets.py`
- Modify: `src/job_hunt_agent/local_app/config.py`
- Create: `tests/test_secret_store_and_presets.py`

- [x] **Step 1: Add `keyring>=25.0.0` to project dependencies**

Store only credential references such as `deepseek:default` in JSON configuration. Never serialize secret values.

- [x] **Step 2: Write failing secret-store and preset tests**

```python
def test_secret_store_round_trip_uses_windows_credential_backend() -> None:
    backend = FakeKeyring()
    store = SecretStore(backend=backend, service_name="JobHuntAgent")

    store.set("deepseek:default", "secret-value")

    assert store.get("deepseek:default") == "secret-value"
    assert backend.values == {("JobHuntAgent", "deepseek:default"): "secret-value"}


def test_presets_are_openai_compatible_and_do_not_embed_keys() -> None:
    presets = provider_presets()
    assert presets["deepseek"].base_url == "https://api.deepseek.com"
    assert presets["qwen"].base_url.host == "dashscope.aliyuncs.com"
    assert all(preset.api_key is None for preset in presets.values())
```

- [x] **Step 3: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_secret_store_and_presets.py`

Expected: FAIL because the secret store and presets do not exist.

- [x] **Step 4: Implement presets and secret storage**

Presets must include DeepSeek, Qwen, Moonshot, a custom OpenAI-compatible endpoint, and Ollama. `SecretStore.delete` must remove only the named credential. Tests use an injected fake backend and never access the real Windows Credential Manager.

- [x] **Step 5: Run tests and privacy scan**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_secret_store_and_presets.py tests/test_local_app_config.py`

Run: `rtk proxy python -X utf8 scripts/privacy_scan.py src tests`

Expected: PASS with no privacy findings.

- [x] **Step 6: Commit**

```bash
rtk proxy git add pyproject.toml src/job_hunt_agent/local_app src/job_hunt_agent/ai/presets.py tests/test_secret_store_and_presets.py
rtk proxy git commit -m "feat: secure model provider settings"
```

### Task 3: Add the LLM Action Planner

**Files:**
- Create: `src/job_hunt_agent/ai/action_planner.py`
- Modify: `src/job_hunt_agent/actions/service.py`
- Create: `tests/test_llm_action_planner.py`

- [x] **Step 1: Write failing planner tests**

```python
def test_planner_returns_draft_and_never_calls_executor() -> None:
    provider = StubProvider(
        ActionPlan(
            action="create_application",
            arguments={"company": "示例科技", "role": "Agent 工程师"},
        )
    )
    executor = RecordingExecutor()
    planner = LLMActionPlanner(provider, executor=executor)

    draft = planner.propose("记录一个示例科技 Agent 工程师投递")

    assert draft.status == "pending"
    assert executor.calls == []


def test_unknown_tool_is_rejected_before_draft_creation() -> None:
    provider = StubProvider(ActionPlan(action="run_shell", arguments={"command": "dir"}))
    with pytest.raises(UnsupportedActionError):
        LLMActionPlanner(provider).propose("查看目录")
```

Add tests for missing required fields, read-only queries, remote-data disclosure metadata, and no-model fallback to the deterministic parser.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_llm_action_planner.py`

Expected: FAIL because `LLMActionPlanner` does not exist.

- [x] **Step 3: Implement allow-listed planning**

```python
class ActionPlan(BaseModel):
    action: Literal[
        "query_applications",
        "create_application",
        "update_application",
        "save_interview",
        "generate_review",
    ]
    arguments: dict[str, object]
    disclosure: list[Literal["application_metadata", "interview_notes"]] = []
```

The planner must validate action-specific payload models, convert writes to `ActionDraftService` drafts, and execute only read-only query handlers directly.

- [x] **Step 4: Run tests and verify GREEN**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_llm_action_planner.py tests/test_action_draft_service.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/ai/action_planner.py src/job_hunt_agent/actions/service.py tests/test_llm_action_planner.py
rtk proxy git commit -m "feat: plan confirmed actions with LLMs"
```

### Task 4: Add Local-First Notion Interview Sync

**Files:**
- Create: `src/job_hunt_agent/interviews/sync.py`
- Create: `src/job_hunt_agent/interviews/notion_target.py`
- Modify: `src/job_hunt_agent/interviews/local_store.py`
- Create: `tests/test_interview_sync.py`

- [x] **Step 1: Write failing sync tests**

```python
def test_sync_writes_local_record_before_notion() -> None:
    local = RecordingLocalStore()
    notion = RecordingNotionTarget()
    service = InterviewSyncService(local, notion)

    result = service.save_and_sync(draft(), operation_id="interview-1")

    assert local.events[0] == "saved"
    assert notion.events[0] == "created"
    assert result.sync_status == "synced"


def test_notion_failure_keeps_retryable_local_record() -> None:
    local = RecordingLocalStore()
    service = InterviewSyncService(local, FailingNotionTarget())

    result = service.save_and_sync(draft(), operation_id="interview-2")

    assert result.sync_status == "failed"
    assert local.get(result.id).raw_notes == draft().raw_notes
```

Add tests for retry idempotency, update of an existing Notion page, disabled Notion, and token-free logs.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_interview_sync.py`

Expected: FAIL because the sync service does not exist.

- [x] **Step 3: Implement the sync protocol and Notion target**

```python
class InterviewSyncTarget(Protocol):
    def upsert(self, record: LocalInterviewRecord, operation_id: str) -> str:
        raise NotImplementedError


class InterviewSyncService:
    def save_and_sync(self, draft: LocalInterviewDraft, operation_id: str) -> LocalInterviewRecord:
        local_record = self.local_store.save(draft, operation_id)
        return self._sync(local_record, operation_id)

    def retry(self, interview_id: str) -> LocalInterviewRecord:
        local_record = self.local_store.get(interview_id)
        return self._sync(local_record, f"retry-{interview_id}")
```

The Notion target must use the existing `NotionClient`, write the standard interview body contract, and return only the page ID. Local state is updated after a successful response.

- [x] **Step 4: Run sync and existing Notion tests**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_interview_sync.py tests/test_notion_integration.py tests/test_notion_interview_template.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/interviews tests/test_interview_sync.py
rtk proxy git commit -m "feat: sync local interviews to Notion"
```

### Task 5: Expose Model and Notion Settings in the Web API

**Files:**
- Modify: `src/job_hunt_agent/web/app.py`
- Modify: `src/job_hunt_agent/web/dependencies.py`
- Modify: `src/job_hunt_agent/web/schemas.py`
- Create: `tests/test_web_integrations_api.py`

- [x] **Step 1: Write failing API tests**

```python
def test_settings_response_never_returns_secret(client: TestClient) -> None:
    client.put(
        "/api/settings/model",
        headers=session_headers(client),
        json={"provider": "deepseek", "api_key": "secret-value"},
    )

    response = client.get("/api/settings").json()

    assert response["model"]["credential_configured"] is True
    assert "api_key" not in response["model"]
    assert "secret-value" not in str(response)


def test_model_test_endpoint_reports_capability_without_echoing_response(client: TestClient) -> None:
    response = client.post("/api/settings/model/test", headers=session_headers(client))
    assert response.json() == {"status": "connected", "structured_output": True}
```

Add tests for Notion connection status, interview sync retry, Ollama without a key, and model timeout responses.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_web_integrations_api.py`

Expected: FAIL because integration routes do not exist.

- [x] **Step 3: Implement guarded settings and connectivity routes**

Add `/api/settings/model`, `/api/settings/model/test`, `/api/settings/notion`, `/api/settings/notion/test`, and `/api/interviews/{id}/sync`. Mutation routes require the session token. API responses expose only booleans and redacted identifiers.

- [x] **Step 4: Run API tests and privacy scan**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_web_integrations_api.py tests/test_web_api.py`

Run: `rtk proxy python -X utf8 scripts/privacy_scan.py src tests`

Expected: PASS with no privacy findings.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/web tests/test_web_integrations_api.py
rtk proxy git commit -m "feat: expose model and Notion settings"
```

### Task 6: Add Integration Controls to the Frontend

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/AssistantPanel.tsx`
- Modify: `frontend/src/components/ActionPreview.tsx`
- Modify: `frontend/src/views/InterviewsView.tsx`
- Modify: `frontend/src/views/SettingsView.tsx`
- Create: `frontend/src/views/SettingsView.test.tsx`
- Create: `frontend/src/views/InterviewsView.test.tsx`

- [x] **Step 1: Write failing frontend tests**

```tsx
it("saves a provider key without rendering it back", async () => {
  render(<SettingsView api={fakeApi} />);
  await userEvent.selectOptions(screen.getByLabelText("模型供应商"), "deepseek");
  await userEvent.type(screen.getByLabelText("API Key"), "secret-value");
  await userEvent.click(screen.getByRole("button", { name: "保存模型设置" }));

  expect(fakeApi.saveModelSettings).toHaveBeenCalledTimes(1);
  expect(screen.queryByDisplayValue("secret-value")).not.toBeInTheDocument();
});
```

Add tests for Ollama key omission, remote-data disclosure in action previews, Notion connection status, and sync retry.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy npm test -- --run`

Expected: FAIL because the integration controls do not exist.

- [x] **Step 3: Implement settings and sync states**

Render model and Notion settings as compact forms. Display only `未配置`, `已配置`, `连接成功`, or `连接失败`; never render stored secret values. The action preview must require a separate consent checkbox when disclosure includes interview notes.

- [x] **Step 4: Run frontend verification**

Run: `rtk proxy npm test -- --run`

Run: `rtk proxy npm run typecheck`

Run: `rtk proxy npm run build`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add frontend
rtk proxy git commit -m "feat: configure model and Notion integrations"
```

### Task 7: Verify the Integration Release Candidate

**Files:**
- Modify: `README.md`
- Modify: `docs/privacy.md`
- Create: `tests/test_integration_privacy_boundaries.py`

- [x] **Step 1: Add privacy-boundary tests**

Test that logs, API responses, config JSON, local interview indexes, and action receipts do not contain configured API keys or Notion tokens.

- [x] **Step 2: Document supported modes**

README must describe no-model mode, remote provider mode, Ollama mode, local Markdown interviews, and optional Notion sync. `docs/privacy.md` must list exactly which data leaves the computer for each provider mode.

- [x] **Step 3: Run complete verification**

Run: `rtk proxy python -X utf8 -m pytest -q`

Run: `rtk proxy npm test -- --run` in `frontend`.

Run: `rtk proxy npm run typecheck` in `frontend`.

Run: `rtk proxy npm run build` in `frontend`.

Run: `rtk proxy python -X utf8 scripts/privacy_scan.py README.md docs examples frontend scripts src tests`

Expected: all commands pass with no privacy findings.

- [x] **Step 4: Commit**

```bash
rtk proxy git add README.md docs/privacy.md tests/test_integration_privacy_boundaries.py
rtk proxy git commit -m "docs: define local and remote data boundaries"
```
