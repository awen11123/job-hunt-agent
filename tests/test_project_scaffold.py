import tomllib
from pathlib import Path

from job_hunt_agent import __version__

PROJECT_METADATA = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_package_exports_version() -> None:
    assert __version__ == PROJECT_METADATA["version"]


def test_runtime_dependencies_include_windows_timezone_database() -> None:
    dependencies = PROJECT_METADATA["dependencies"]

    assert any(dependency.split(">=", maxsplit=1)[0] == "tzdata" for dependency in dependencies)
