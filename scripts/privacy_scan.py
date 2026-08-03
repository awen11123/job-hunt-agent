from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_hunt_agent.privacy import PrivacyFinding, scan_text_for_private_leaks  # noqa: E402


SKIPPED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv"}
SKIPPED_SUFFIXES = {".pyc", ".pyo"}


def should_scan(path: Path) -> bool:
    if any(part in SKIPPED_DIR_NAMES for part in path.parts):
        return False
    return path.suffix not in SKIPPED_SUFFIXES


def scan_paths(paths: list[Path]) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    for path in paths:
        if path.is_dir():
            findings.extend(scan_paths([child for child in path.rglob("*") if child.is_file()]))
            continue
        if not should_scan(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(scan_text_for_private_leaks(text))
    return findings


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] if argv else [Path(".")]
    findings = scan_paths(paths)
    for finding in findings:
        print(f"{finding.kind}: {finding.value}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
