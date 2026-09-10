from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/windows-release.yml")
SMOKE_SCRIPT_PATH = Path("scripts/smoke_windows_install.ps1")


def load_workflow() -> dict:
    return yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def workflow_commands(workflow: dict) -> str:
    steps = workflow["jobs"]["build"]["steps"]
    return "\n".join(step.get("run", "") for step in steps)


def test_release_workflow_runs_all_quality_gates() -> None:
    workflow = load_workflow()
    commands = workflow_commands(workflow)

    assert "pytest" in commands
    assert "scripts/build_frontend.py" in commands
    assert "privacy_scan.py" in commands
    assert "verify_release_artifact.py" in commands
    assert "build_windows_installer.ps1" in commands
    assert "smoke_windows_install.ps1" in commands


def test_release_workflow_is_windows_tag_only_and_publishes_checksums() -> None:
    workflow = load_workflow()
    build = workflow["jobs"]["build"]
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert workflow["on"]["push"]["tags"] == ["v*"]
    assert build["runs-on"] == "windows-latest"
    assert "Get-FileHash" in text
    assert "softprops/action-gh-release" in text
    assert "JobHuntAgent-Setup-*.exe.sha256" in text


def test_smoke_script_uses_isolated_data_and_checks_install_lifecycle() -> None:
    script = SMOKE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "$env:APPDATA" in script
    assert "JOB_HUNT_AGENT_SKIP_BROWSER" in script
    assert "instance.json" in script
    assert "/api/health" in script
    assert "unins000.exe" in script
    assert "keep-after-uninstall.txt" in script
    assert "StartupTimeoutSeconds = 60" in script
    assert "InstanceState=" in script
    assert "KeepTemporaryFilesOnFailure" in script
    assert "StartsWith" in script
    assert "C:\\Users\\" not in script
