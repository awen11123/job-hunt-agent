from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.privacy_scan import scan_file  # noqa: E402

REQUIRED_FILES = {
    "JobHuntAgent.exe",
    "_internal/web_static/index.html",
}
PRIVATE_DIRECTORY_NAMES = {
    "backups",
    "interviews",
    "interview_notes",
    "private",
    "private_exports",
    "面经",
    "备份",
}
PRIVATE_FILE_NAMES = {".env"}
PRIVATE_FILE_SUFFIXES = {".xls", ".xlsm", ".xlsx"}
CONFIG_SUFFIXES = {".cfg", ".ini", ".json", ".properties", ".toml", ".yaml", ".yml"}
TEXT_SUFFIXES = CONFIG_SUFFIXES | {
    ".bat",
    ".cmd",
    ".css",
    ".csv",
    ".html",
    ".js",
    ".map",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".tsv",
    ".txt",
    ".xml",
}
CONFIG_SECRET_RE = re.compile(
    r"(?i)[\"']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret|token)"
    r"[\"']?\s*[:=]\s*[\"']?(?!\s*(?:null|none|false|\$\{|<redacted>))[A-Za-z0-9_./+-]{6,}"
)


@dataclass(frozen=True)
class ArtifactFinding:
    category: str
    path: str


@dataclass(frozen=True)
class ArtifactVerificationResult:
    findings: tuple[ArtifactFinding, ...]
    missing: set[str]

    @property
    def ok(self) -> bool:
        return not self.findings and not self.missing

    @property
    def failed_files(self) -> set[str]:
        return {finding.path for finding in self.findings}

    def summary(self) -> str:
        lines = [f"{finding.category}: {finding.path}" for finding in self.findings]
        lines.extend(f"missing: {path}" for path in sorted(self.missing))
        return "\n".join(lines)


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _has_private_directory(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts[:-1]
    return any(part.casefold() in PRIVATE_DIRECTORY_NAMES for part in relative_parts)


def _is_private_filename(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name in PRIVATE_FILE_NAMES
        or name.startswith(".env.")
        or path.suffix.casefold() in PRIVATE_FILE_SUFFIXES
    )


def _contains_configured_secret(path: Path) -> bool:
    if path.suffix.casefold() not in CONFIG_SUFFIXES:
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return CONFIG_SECRET_RE.search(text) is not None


def verify_artifact(artifact_root: Path) -> ArtifactVerificationResult:
    root = artifact_root.resolve()
    existing = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    } if root.is_dir() else set()
    missing = REQUIRED_FILES - existing
    findings: set[ArtifactFinding] = set()

    if root.is_dir():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = _relative_path(path, root)
            if _has_private_directory(path, root):
                findings.add(ArtifactFinding("private_directory", relative))
            if _is_private_filename(path):
                findings.add(ArtifactFinding("private_file", relative))
            if _contains_configured_secret(path):
                findings.add(ArtifactFinding("configured_secret", relative))
            if path.suffix.casefold() in TEXT_SUFFIXES:
                for privacy_finding in scan_file(path):
                    findings.add(ArtifactFinding(privacy_finding.kind, relative))

    return ArtifactVerificationResult(
        findings=tuple(sorted(findings, key=lambda finding: (finding.path, finding.category))),
        missing=missing,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: verify_release_artifact.py <release-directory>")
        return 2
    result = verify_artifact(Path(argv[0]))
    if result.summary():
        print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
