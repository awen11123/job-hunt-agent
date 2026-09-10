from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Callable, Final, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SyncStatus = Literal["local", "pending", "synced", "failed"]

RAW_NOTES_MARKER: Final = "<!-- job-hunt-agent:raw-notes -->"
INDEX_VERSION: Final = 1
LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS: Final = 0.05
_WINDOWS_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class _StoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalInterviewDraft(_StoreModel):
    application_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    round_name: str = Field(min_length=1)
    raw_notes: str = Field(min_length=1)
    scheduled_at: datetime | None = None
    format: str | None = None
    result: str | None = None
    self_score: int | None = Field(default=None, ge=1, le=10)

    @field_validator("application_id", "company", "round_name")
    @classmethod
    def normalize_required_metadata(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text must not be blank")
        return normalized

    @field_validator("raw_notes")
    @classmethod
    def raw_notes_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_notes must not be blank")
        return value


class LocalInterviewRecord(LocalInterviewDraft):
    id: str = Field(min_length=1)
    markdown_path: Path
    sync_status: SyncStatus = "local"
    notion_page_id: str | None = None
    operation_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def synced_record_has_page_id(self) -> LocalInterviewRecord:
        if self.sync_status == "synced" and not (
            self.notion_page_id and self.notion_page_id.strip()
        ):
            raise ValueError("notion_page_id is required when sync_status is synced")
        return self


class _IndexRecord(_StoreModel):
    id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    round_name: str = Field(min_length=1)
    scheduled_at: datetime | None = None
    format: str | None = None
    result: str | None = None
    self_score: int | None = Field(default=None, ge=1, le=10)
    markdown_filename: str = Field(min_length=1)
    sync_status: SyncStatus = "local"
    notion_page_id: str | None = None
    operation_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("application_id", "company", "round_name")
    @classmethod
    def normalize_required_metadata(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text must not be blank")
        return normalized

    @field_validator("markdown_filename")
    @classmethod
    def markdown_filename_is_relative_basename(cls, value: str) -> str:
        if value in {".", ".."} or Path(value).name != value or Path(value).is_absolute():
            raise ValueError("markdown_filename must be a relative filename")
        if Path(value).suffix.lower() != ".md":
            raise ValueError("markdown_filename must identify a Markdown file")
        return value

    @model_validator(mode="after")
    def synced_record_has_page_id(self) -> _IndexRecord:
        if self.sync_status == "synced" and not (
            self.notion_page_id and self.notion_page_id.strip()
        ):
            raise ValueError("notion_page_id is required when sync_status is synced")
        return self


class _Index(_StoreModel):
    version: Literal[1] = INDEX_VERSION
    records: list[_IndexRecord] = Field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _interview_id(operation_id: str) -> str:
    return hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:16]


def _filename_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    sanitized = _WINDOWS_INVALID_FILENAME.sub("", normalized).rstrip(". ")
    component: list[str] = []
    utf16_units = 0
    for character in sanitized:
        character_units = 2 if ord(character) > 0xFFFF else 1
        if utf16_units + character_units > 80:
            break
        component.append(character)
        utf16_units += character_units
    return "".join(component).rstrip(". ") or "interview"


def _markdown_filename(draft: LocalInterviewDraft, interview_id: str) -> str:
    company = _filename_component(draft.company)
    round_name = _filename_component(draft.round_name)
    return f"{company}-{round_name}-{interview_id}.md"


def _markdown_text(draft: LocalInterviewDraft) -> str:
    company = " ".join(draft.company.split())
    round_name = " ".join(draft.round_name.split())
    return f"# {company} - {round_name}\n\n{RAW_NOTES_MARKER}\n{draft.raw_notes}"


def _extract_raw_notes(markdown: str) -> str:
    separator = f"{RAW_NOTES_MARKER}\n"
    _, found, raw_notes = markdown.partition(separator)
    if not found:
        raise ValueError("Markdown raw-notes marker is missing")
    return raw_notes


def _try_lock_file(handle: BinaryIO) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _exclusive_index_lock(index_path: Path) -> Iterator[None]:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = os.path.normcase(str(index_path.resolve()))
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(lock_key, threading.Lock())

    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    if not thread_lock.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise RuntimeError("interview store is busy; try again later")

    handle: BinaryIO | None = None
    file_locked = False
    try:
        sidecar = index_path.with_name(f".{index_path.name}.lock")
        descriptor = os.open(
            sidecar,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0),
        )
        handle = os.fdopen(descriptor, "r+b")
        while not (file_locked := _try_lock_file(handle)):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("interview store is busy; try again later")
            time.sleep(min(_LOCK_POLL_SECONDS, remaining))
        handle.seek(0)
        handle.write(b"\0")
        handle.truncate(1)
        handle.flush()
        yield
    finally:
        try:
            if file_locked and handle is not None:
                _unlock_file(handle)
        finally:
            try:
                if handle is not None:
                    handle.close()
            finally:
                thread_lock.release()


class LocalInterviewStore:
    def __init__(self, root: Path, clock: Callable[[], datetime] = _utc_now) -> None:
        self.root = Path(root)
        self.index_path = self.root / "index.json"
        self._clock = clock

    def save(
        self,
        draft: LocalInterviewDraft,
        operation_id: str,
    ) -> LocalInterviewRecord:
        with _exclusive_index_lock(self.index_path):
            index = self._read_index()
            existing = next(
                (record for record in index.records if record.operation_id == operation_id),
                None,
            )
            if existing is not None:
                return self._record_from_index(existing)

            interview_id = _interview_id(operation_id)
            if any(record.id == interview_id for record in index.records):
                raise RuntimeError("interview id collision")
            now = self._clock()
            markdown_filename = _markdown_filename(draft, interview_id)
            markdown_path = self._safe_markdown_path(markdown_filename)
            record = LocalInterviewRecord(
                **draft.model_dump(mode="python"),
                id=interview_id,
                markdown_path=markdown_path,
                operation_id=operation_id,
                created_at=now,
                updated_at=now,
            )
            index_record = self._index_record(record)

            markdown = _markdown_text(draft)
            created_markdown = False
            if markdown_path.exists():
                if markdown_path.read_bytes().decode("utf-8") != markdown:
                    raise FileExistsError(markdown_path)
            else:
                self._atomic_write_markdown(markdown_path, markdown, draft.raw_notes)
                created_markdown = True
            try:
                updated_index = _Index(records=[*index.records, index_record])
                self._atomic_write_index(updated_index)
            except BaseException:
                if created_markdown:
                    markdown_path.unlink(missing_ok=True)
                raise
            return record

    def get(self, interview_id: str) -> LocalInterviewRecord:
        with _exclusive_index_lock(self.index_path):
            index = self._read_index()
            record = next(
                (record for record in index.records if record.id == interview_id),
                None,
            )
            if record is None:
                raise KeyError(interview_id)
            return self._record_from_index(record)

    def list(self, application_id: str | None = None) -> list[LocalInterviewRecord]:
        with _exclusive_index_lock(self.index_path):
            index = self._read_index()
            records = (
                index.records
                if application_id is None
                else [
                    record
                    for record in index.records
                    if record.application_id == application_id
                ]
            )
            newest_first = sorted(
                enumerate(records),
                key=lambda item: (item[1].created_at, item[0]),
                reverse=True,
            )
            return [self._record_from_index(record) for _, record in newest_first]

    def mark_sync(
        self,
        interview_id: str,
        status: SyncStatus,
        notion_page_id: str | None = None,
    ) -> LocalInterviewRecord:
        with _exclusive_index_lock(self.index_path):
            index = self._read_index()
            position = next(
                (
                    position
                    for position, record in enumerate(index.records)
                    if record.id == interview_id
                ),
                None,
            )
            if position is None:
                raise KeyError(interview_id)

            existing = index.records[position]
            values = existing.model_dump(mode="python")
            values["sync_status"] = status
            if notion_page_id is not None:
                values["notion_page_id"] = notion_page_id
            values["updated_at"] = self._clock()
            updated = _IndexRecord.model_validate(values)
            records = list(index.records)
            records[position] = updated
            self._atomic_write_index(_Index(records=records))
            return self._record_from_index(updated)

    def _read_index(self) -> _Index:
        if not self.index_path.exists():
            return _Index()
        return _Index.model_validate_json(self.index_path.read_text(encoding="utf-8"))

    def _record_from_index(self, record: _IndexRecord) -> LocalInterviewRecord:
        markdown_path = self._safe_markdown_path(record.markdown_filename)
        markdown = markdown_path.read_bytes().decode("utf-8")
        raw_notes = _extract_raw_notes(markdown)
        values = record.model_dump(mode="python", exclude={"markdown_filename"})
        return LocalInterviewRecord(
            **values,
            raw_notes=raw_notes,
            markdown_path=markdown_path,
        )

    def _safe_markdown_path(self, filename: str) -> Path:
        path = self.root / filename
        if path.resolve().parent != self.root.resolve():
            raise ValueError("markdown filename escapes interview root")
        return path

    @staticmethod
    def _index_record(record: LocalInterviewRecord) -> _IndexRecord:
        values = record.model_dump(
            mode="python",
            exclude={"raw_notes", "markdown_path"},
        )
        return _IndexRecord(**values, markdown_filename=record.markdown_path.name)

    def _atomic_write_markdown(
        self,
        destination: Path,
        content: str,
        expected_raw_notes: str,
    ) -> None:
        def validate(temporary_path: Path) -> None:
            decoded = temporary_path.read_bytes().decode("utf-8")
            if not decoded.startswith("# "):
                raise ValueError("Markdown title is missing")
            if _extract_raw_notes(decoded) != expected_raw_notes:
                raise ValueError("Markdown raw notes failed validation")

        self._atomic_write(destination, content, validate)

    def _atomic_write_index(self, index: _Index) -> None:
        content = f"{index.model_dump_json(indent=2)}\n"

        def validate(temporary_path: Path) -> None:
            _Index.model_validate_json(temporary_path.read_text(encoding="utf-8"))

        self._atomic_write(self.index_path, content, validate)

    def _atomic_write(
        self,
        destination: Path,
        content: str,
        validate: Callable[[Path], None],
    ) -> None:
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=self.root,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            validate(temporary_path)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
