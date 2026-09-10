from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
FRONTEND_DIST = FRONTEND_ROOT / "dist"
PACKAGE_STATIC = PROJECT_ROOT / "src" / "job_hunt_agent" / "web_static"


def _npm_executable() -> str:
    executable = shutil.which("npm")
    if executable is None:
        raise RuntimeError("npm is required to build the frontend.")
    return executable


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=FRONTEND_ROOT, check=True)  # noqa: S603


def copy_frontend_dist() -> None:
    index_path = FRONTEND_DIST / "index.html"
    if not index_path.is_file():
        raise RuntimeError("Frontend build did not produce dist/index.html.")
    if PACKAGE_STATIC.exists():
        shutil.rmtree(PACKAGE_STATIC)
    shutil.copytree(FRONTEND_DIST, PACKAGE_STATIC)


def main() -> int:
    npm = _npm_executable()
    for arguments in (
        ["ci", "--no-audit", "--no-fund"],
        ["run", "typecheck"],
        ["test", "--", "--run"],
        ["run", "build"],
    ):
        _run([npm, *arguments])
    copy_frontend_dist()
    print(f"Frontend resources copied to {PACKAGE_STATIC.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
