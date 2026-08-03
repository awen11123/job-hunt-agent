from pathlib import Path
import subprocess
import sys

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


def test_privacy_scan_script_runs_as_file() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/privacy_scan.py", "README.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_scan_paths_skips_python_cache_directories(tmp_path: Path) -> None:
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    cached = cache_dir / "compiled.pyc"
    cached.write_bytes(
        b"https://www.notion" + b".so/private " + b"sk-" + b"abc123456789SECRET"
    )

    assert scan_paths([tmp_path]) == []
