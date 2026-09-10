from pathlib import Path
import subprocess
import sys

from scripts.verify_release_artifact import verify_artifact


REPO_ROOT = Path(__file__).resolve().parents[1]


def build_release_directory(
    tmp_path: Path,
    files: dict[str, str | bytes] | None = None,
    *,
    complete: bool = True,
) -> Path:
    artifact = tmp_path / "JobHuntAgent"
    artifact.mkdir()
    if complete:
        (artifact / "JobHuntAgent.exe").write_bytes(b"binary")
        frontend = artifact / "_internal" / "web_static" / "index.html"
        frontend.parent.mkdir(parents=True)
        frontend.write_text("<main>Job Hunt Agent</main>", encoding="utf-8")
    for relative_path, content in (files or {}).items():
        target = artifact / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return artifact


def test_artifact_accepts_complete_public_release(tmp_path: Path) -> None:
    artifact = build_release_directory(tmp_path)

    result = verify_artifact(artifact)

    assert result.ok is True
    assert result.failed_files == set()
    assert result.missing == set()


def test_artifact_rejects_configured_secrets_without_exposing_values(tmp_path: Path) -> None:
    secret = "private-release-value"
    artifact = build_release_directory(
        tmp_path,
        {"config.json": '{"token":"' + secret + '"}'},
    )

    result = verify_artifact(artifact)

    assert result.ok is False
    assert result.failed_files == {"config.json"}
    assert secret not in result.summary()


def test_artifact_rejects_dotenv_and_private_data_directories(tmp_path: Path) -> None:
    artifact = build_release_directory(
        tmp_path,
        {
            ".env": "MODEL_KEY=not-public",
            "interviews/company.md": "private interview notes",
            "backups/tracker.xlsx": b"private workbook",
        },
    )

    result = verify_artifact(artifact)

    assert result.failed_files == {
        ".env",
        "backups/tracker.xlsx",
        "interviews/company.md",
    }


def test_artifact_rejects_notion_and_wps_account_paths(tmp_path: Path) -> None:
    artifact = build_release_directory(
        tmp_path,
        {
            "notes.txt": (
                "https://www.notion" + ".so/private "
                + "C:/Users/Example/WPS Cloud Files/12345678/tracker.xlsx"
            )
        },
    )

    result = verify_artifact(artifact)

    assert result.failed_files == {"notes.txt"}
    assert {finding.category for finding in result.findings} >= {
        "notion_url",
        "windows_user_path",
        "wps_account_path",
    }


def test_artifact_does_not_treat_compiled_dependency_strings_as_user_data(
    tmp_path: Path,
) -> None:
    artifact = build_release_directory(
        tmp_path,
        {
            "_internal/dependency.pyd": (
                b"compiler metadata C:/Users/runneradmin/source "
                b"and arbitrary sk-abc123456789SECRET bytes"
            )
        },
    )

    result = verify_artifact(artifact)

    assert result.ok is True


def test_artifact_requires_application_and_frontend(tmp_path: Path) -> None:
    artifact = build_release_directory(
        tmp_path,
        {"JobHuntAgent.exe": b"binary"},
        complete=False,
    )

    result = verify_artifact(artifact)

    assert result.missing == {"_internal/web_static/index.html"}


def test_cli_prints_only_categories_and_paths(tmp_path: Path) -> None:
    secret = "sk-abc123456789SECRET"
    artifact = build_release_directory(tmp_path, {"leaked.txt": secret})

    result = subprocess.run(
        [sys.executable, "scripts/verify_release_artifact.py", str(artifact)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "api_key: leaked.txt" in result.stdout
    assert secret not in result.stdout
