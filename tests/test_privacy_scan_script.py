from pathlib import Path
import subprocess
import sys

import pytest

import scripts.privacy_scan as privacy_scan_module
from scripts.privacy_scan import scan_paths


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scan_paths_reports_private_patterns(tmp_path: Path) -> None:
    leaked = tmp_path / "leaked.md"
    leaked.write_text(
        "https://www.notion" + ".so/private and " + "sk-" + "abc123456789SECRET",
        encoding="utf-8",
    )

    findings = scan_paths([leaked])

    assert len(findings) == 2
    assert {finding.kind for finding in findings} == {"notion_url", "api_key"}


def test_scan_paths_reports_local_user_and_wps_account_paths(tmp_path: Path) -> None:
    leaked = tmp_path / "local-path.md"
    leaked.write_text(
        "C:" + "/Users/ExampleUser/" + "WPS Cloud Files/" + "12345678/tracker.xlsx",
        encoding="utf-8",
    )

    findings = scan_paths([leaked])

    assert {finding.kind for finding in findings} == {
        "windows_user_path",
        "wps_account_path",
    }


def test_privacy_scan_script_runs_as_file() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/privacy_scan.py", "README.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_privacy_scan_script_redacts_detected_values(tmp_path: Path) -> None:
    leaked = tmp_path / "leaked.md"
    leaked.write_text("token " + "sk-" + "abc123456789SECRET", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/privacy_scan.py", str(leaked)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "api_key" in result.stdout
    assert "sk-" + "abc123456789SECRET" not in result.stdout
    assert "<redacted>" in result.stdout


def test_scan_paths_skips_python_cache_directories(tmp_path: Path) -> None:
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    cached = cache_dir / "compiled.pyc"
    cached.write_bytes(
        b"https://www.notion" + b".so/private " + b"sk-" + b"abc123456789SECRET"
    )

    assert scan_paths([tmp_path]) == []


def test_scan_paths_skips_only_known_repository_generated_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(privacy_scan_module, "PROJECT_ROOT", tmp_path)
    generated_directories = (
        tmp_path / "build",
        tmp_path / "dist",
        tmp_path / "frontend" / "dist",
        tmp_path / "frontend" / "node_modules",
    )
    for generated_dir in generated_directories:
        generated_dir.mkdir(parents=True, exist_ok=True)
        (generated_dir / "generated.js").write_text(
            "C:" + "/Users/ThirdParty/build-output.js",
            encoding="utf-8",
        )

    assert scan_paths([tmp_path]) == []


def test_scan_paths_skips_an_explicit_node_modules_root(tmp_path: Path) -> None:
    dependency_root = tmp_path / "vendor" / "node_modules"
    dependency_root.mkdir(parents=True)
    (dependency_root / "third-party.js").write_text(
        "C:" + "/Users/ThirdParty/dependency.js",
        encoding="utf-8",
    )

    assert scan_paths([dependency_root]) == []


@pytest.mark.parametrize("directory_name", ["build", "dist"])
def test_scan_paths_does_not_skip_owned_source_named_like_an_output_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    directory_name: str,
) -> None:
    monkeypatch.setattr(privacy_scan_module, "PROJECT_ROOT", tmp_path)
    source_dir = tmp_path / "src" / directory_name
    source_dir.mkdir(parents=True)
    (source_dir / "owned.py").write_text(
        "key = '" + "sk-" + "abc123456789SECRET'",
        encoding="utf-8",
    )

    findings = scan_paths([tmp_path])

    assert [finding.kind for finding in findings] == ["api_key"]
