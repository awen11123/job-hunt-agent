# Windows Installer and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the verified local web application as a Windows installer that runs without Python, Node, or Codex and publish privacy-scanned artifacts through GitHub Releases.

**Architecture:** A launcher owns the single local server process, loopback session token, health check, and browser opening. Vite assets are embedded in a PyInstaller directory build, and Inno Setup creates the final installer executable.

**Tech Stack:** Python 3.12, Uvicorn, PyInstaller, React/Vite, Inno Setup, PowerShell, GitHub Actions

---

### Task 1: Harden the Windows Launcher

**Files:**
- Modify: `src/job_hunt_agent/web/launcher.py`
- Create: `src/job_hunt_agent/__main__.py`
- Create: `tests/test_windows_launcher.py`

- [x] **Step 1: Write failing launcher lifecycle tests**

```python
def test_second_launcher_reuses_healthy_instance() -> None:
    state = FakeInstanceState(port=43127, healthy=True)
    launcher = WindowsLauncher(instance_state=state, browser=FakeBrowser())

    result = launcher.start()

    assert result.started_server is False
    assert result.url == "http://127.0.0.1:43127/"


def test_launcher_opens_browser_only_after_health_check() -> None:
    events: list[str] = []
    launcher = WindowsLauncher(server=FakeServer(events), browser=FakeBrowser(events))
    launcher.start()
    assert events == ["server-start", "health-ok", "browser-open"]
```

Add tests for stale instance files, port collisions, graceful shutdown, and loopback-only binding.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_windows_launcher.py`

Expected: FAIL because the hardened launcher does not exist.

- [x] **Step 3: Implement the launcher**

`WindowsLauncher.start()` must acquire a per-user lock, reuse a healthy process, choose an available port, generate a session token, start Uvicorn on `127.0.0.1`, poll `/api/health`, and open the browser only after the health check succeeds. Register normal process and signal cleanup without killing a reused instance.

- [x] **Step 4: Run tests and verify GREEN**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_windows_launcher.py tests/test_web_launcher.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
rtk proxy git add src/job_hunt_agent/web/launcher.py src/job_hunt_agent/__main__.py tests/test_windows_launcher.py
rtk proxy git commit -m "feat: harden Windows local launcher"
```

### Task 2: Build Frontend Resources and the PyInstaller Application

**Files:**
- Modify: `pyproject.toml`
- Create: `src/job_hunt_agent/web/resources.py`
- Create: `scripts/build_frontend.py`
- Create: `packaging/job_hunt_agent.spec`
- Create: `tests/test_packaged_resources.py`

- [x] **Step 1: Add release tooling**

Add a `release` optional dependency group containing `pyinstaller>=6.10.0`. Keep Inno Setup outside Python dependencies.

- [x] **Step 2: Write failing resource-location tests**

```python
def test_resource_root_uses_package_directory_when_not_frozen(monkeypatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert resource_root().name == "web_static"


def test_resource_root_uses_pyinstaller_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_root() == tmp_path / "web_static"
```

- [x] **Step 3: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_packaged_resources.py`

Expected: FAIL because `resource_root` does not exist.

- [x] **Step 4: Implement frontend build copying and the spec file**

`scripts/build_frontend.py` must run `npm ci`, `npm run typecheck`, `npm test -- --run`, and `npm run build` in `frontend`, then copy `frontend/dist` to `src/job_hunt_agent/web_static`. `job_hunt_agent.spec` must include `web_static` as data and use `job_hunt_agent.__main__` as the entry point.

- [x] **Step 5: Build and inspect the application directory**

Run: `rtk proxy python -X utf8 scripts/build_frontend.py`

Run: `rtk proxy python -X utf8 -m PyInstaller --clean packaging/job_hunt_agent.spec`

Expected: `dist/JobHuntAgent/JobHuntAgent.exe` exists and `dist/JobHuntAgent/_internal/web_static/index.html` is packaged.

- [x] **Step 6: Run tests and commit**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_packaged_resources.py`

```bash
rtk proxy git add pyproject.toml src/job_hunt_agent/web/resources.py scripts/build_frontend.py packaging/job_hunt_agent.spec tests/test_packaged_resources.py
rtk proxy git commit -m "build: package local web application"
```

### Task 3: Create the Windows Installer

**Files:**
- Create: `packaging/installer.iss`
- Create: `scripts/build_windows_installer.ps1`
- Create: `tests/test_installer_manifest.py`

- [x] **Step 1: Write failing installer-manifest tests**

```python
def test_installer_creates_shortcut_and_keeps_data_on_uninstall() -> None:
    script = Path("packaging/installer.iss").read_text(encoding="utf-8")
    assert "{autodesktop}" in script
    assert "JobHuntAgent.exe" in script
    assert "%APPDATA%" not in script
    assert "UninstallDelete" not in script
```

Add tests for per-user installation, semantic version injection, installer output naming, and absence of private paths.

- [x] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_installer_manifest.py`

Expected: FAIL because `installer.iss` does not exist.

- [x] **Step 3: Implement the installer and build script**

The Inno Setup script must install below `{localappdata}/Programs/JobHuntAgent`, create Start Menu and optional desktop shortcuts, and leave `%APPDATA%/JobHuntAgent` untouched during uninstall. `build_windows_installer.ps1` must validate the PyInstaller directory, pass the version to `ISCC.exe`, and write `dist/installer/JobHuntAgent-Setup-<version>.exe`.

- [x] **Step 4: Build and verify**

Run: `rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows_installer.ps1 -Version 0.2.0`

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_installer_manifest.py`

Expected: installer exists and tests pass.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add packaging/installer.iss scripts/build_windows_installer.ps1 tests/test_installer_manifest.py
rtk proxy git commit -m "build: add Windows installer"
```

### Task 4: Add Release Artifact Verification

**Files:**
- Create: `scripts/verify_release_artifact.py`
- Create: `tests/test_release_artifact.py`
- Modify: `scripts/privacy_scan.py`

- [ ] **Step 1: Write failing artifact tests**

```python
def test_artifact_rejects_private_markers(tmp_path: Path) -> None:
    artifact = build_release_directory(tmp_path, {"config.json": '{"token":"secret-value"}'})
    result = verify_artifact(artifact)
    assert result.ok is False
    assert "config.json" in result.failed_files


def test_artifact_requires_application_and_frontend(tmp_path: Path) -> None:
    artifact = build_release_directory(tmp_path, {"JobHuntAgent.exe": b"binary"})
    result = verify_artifact(artifact)
    assert result.missing == {"web_static/index.html"}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_release_artifact.py`

Expected: FAIL because the artifact verifier does not exist.

- [ ] **Step 3: Implement archive inspection**

The verifier must recursively inspect the PyInstaller release directory, reuse privacy patterns, reject `.env`, config files with secret values, private data directories, Notion URLs, WPS account paths, and missing required application resources. It must print only finding categories and paths, never matched values. The verified directory is the sole input to the Inno Setup build.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_release_artifact.py tests/test_privacy_scan_script.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add scripts/verify_release_artifact.py scripts/privacy_scan.py tests/test_release_artifact.py
rtk proxy git commit -m "test: verify release artifact privacy"
```

### Task 5: Add Windows CI and GitHub Release Workflow

**Files:**
- Create: `.github/workflows/windows-release.yml`
- Create: `scripts/smoke_windows_install.ps1`
- Create: `tests/test_release_workflow.py`

- [ ] **Step 1: Write failing workflow tests**

```python
def test_release_workflow_runs_all_quality_gates() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/windows-release.yml").read_text())
    commands = "\n".join(step.get("run", "") for step in workflow["jobs"]["build"]["steps"])
    assert "pytest" in commands
    assert "privacy_scan.py" in commands
    assert "npm test" in commands
    assert "verify_release_artifact.py" in commands
    assert "smoke_windows_install.ps1" in commands
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_release_workflow.py`

Expected: FAIL because the workflow does not exist.

- [ ] **Step 3: Implement the release workflow**

Trigger on tags matching `v*`. Use a Windows runner to install Python and Node, run Python and frontend tests, build frontend assets, build PyInstaller output, scan the complete PyInstaller directory, compile the installer only from that verified directory, install it silently, start the application, wait for the local health endpoint, stop it, uninstall it, generate SHA-256, and publish the installer and checksum to GitHub Releases.

- [ ] **Step 4: Run workflow tests and local smoke script**

Run: `rtk proxy python -X utf8 -m pytest -q tests/test_release_workflow.py`

Run: `rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_windows_install.ps1 -Installer dist/installer/JobHuntAgent-Setup-0.2.0.exe`

Expected: PASS and the smoke script confirms health on a loopback URL.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add .github/workflows/windows-release.yml scripts/smoke_windows_install.ps1 tests/test_release_workflow.py
rtk proxy git commit -m "ci: publish verified Windows releases"
```

### Task 6: Document Installation and Perform Final Verification

**Files:**
- Create: `docs/windows-install.md`
- Modify: `README.md`
- Modify: `docs/privacy.md`

- [ ] **Step 1: Document the ordinary-user workflow**

Document installation, first-run Excel selection, optional model and Notion setup, backup recovery, upgrade behavior, and uninstall behavior. Do not require command-line steps in the primary path.

- [ ] **Step 2: Run all verification commands**

Run: `rtk proxy python -X utf8 -m pytest -q`

Run: `rtk proxy npm test -- --run` in `frontend`.

Run: `rtk proxy npm run typecheck` in `frontend`.

Run: `rtk proxy npm run build` in `frontend`.

Run: `rtk proxy python -X utf8 scripts/privacy_scan.py README.md docs examples frontend packaging scripts src tests`

Run: `rtk proxy python -X utf8 scripts/verify_release_artifact.py dist/JobHuntAgent`

Expected: every command passes and no privacy findings are printed.

- [ ] **Step 3: Commit**

```bash
rtk proxy git add README.md docs/windows-install.md docs/privacy.md
rtk proxy git commit -m "docs: add Windows installation guide"
```
