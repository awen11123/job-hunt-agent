from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_hunt_agent.privacy import PrivacyFinding, scan_text_for_private_leaks  # noqa: E402


SKIPPED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".venv",
}
SKIPPED_SUFFIXES = {".pyc", ".pyo"}


def scan_file(path: Path) -> list[PrivacyFinding]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return scan_text_for_private_leaks(text)


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _is_skipped_directory(path: Path, scan_root: Path | None = None) -> bool:
    if any(part in SKIPPED_DIR_NAMES for part in path.parts):
        return True

    generated_directories = (
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist",
        PROJECT_ROOT / "frontend" / "dist",
        PROJECT_ROOT / "frontend" / "node_modules",
    )
    if any(_is_within(path, directory) for directory in generated_directories):
        return True
    return bool(
        scan_root is not None
        and scan_root.name == "node_modules"
        and _is_within(path, scan_root)
    )


def should_scan(path: Path, scan_root: Path | None = None) -> bool:
    if _is_skipped_directory(path, scan_root):
        return False
    return path.suffix not in SKIPPED_SUFFIXES


def scan_paths(paths: list[Path]) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    for path in paths:
        if path.is_dir():
            if _is_skipped_directory(path, path):
                continue
            files = [
                child
                for child in path.rglob("*")
                if child.is_file() and should_scan(child, path)
            ]
            findings.extend(scan_paths(files))
            continue
        if not should_scan(path):
            continue
        findings.extend(scan_file(path))
    return findings


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] if argv else [Path(".")]
    findings = scan_paths(paths)
    for finding in findings:
        print(f"{finding.kind}: {finding.redacted_value}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
