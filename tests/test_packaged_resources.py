from __future__ import annotations

import sys
from pathlib import Path

from job_hunt_agent.web.resources import resource_root


def test_resource_root_uses_package_directory_when_not_frozen(
    monkeypatch,
) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    root = resource_root()

    assert root.name == "web_static"
    assert root.parent.name == "job_hunt_agent"


def test_resource_root_uses_pyinstaller_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_root() == tmp_path / "web_static"
