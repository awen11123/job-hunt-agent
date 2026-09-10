from __future__ import annotations

import hashlib
import importlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError


@pytest.fixture
def store_module() -> ModuleType:
    return importlib.import_module("job_hunt_agent.interviews.local_store")


def make_draft(store_module: ModuleType, **changes):
    values = {
        "application_id": "app_123",
        "company": "示例科技",
        "round_name": "技术一面",
        "raw_notes": "讨论了缓存一致性。\n\n回答包含中文和 emoji: ✅",
    }
    values.update(changes)
    return store_module.LocalInterviewDraft(**values)


def test_models_validate_required_fields_and_forbid_extras(store_module: ModuleType) -> None:
    draft = make_draft(store_module, self_score=10)

    assert draft.self_score == 10
    for field_name in ("application_id", "company", "round_name", "raw_notes"):
        with pytest.raises(ValidationError):
            make_draft(store_module, **{field_name: " \t "})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        store_module.LocalInterviewDraft(
            application_id="app_123",
            company="示例科技",
            round_name="一面",
            raw_notes="notes",
            token="must-not-be-accepted",
        )
    with pytest.raises(ValidationError):
        make_draft(store_module, self_score=0)
    with pytest.raises(ValidationError):
        make_draft(store_module, self_score=11)


def test_save_get_roundtrip_uses_utf8_markdown(store_module: ModuleType, tmp_path: Path) -> None:
    scheduled_at = datetime(2026, 9, 12, 10, 30, tzinfo=UTC)
    draft = make_draft(
        store_module,
        scheduled_at=scheduled_at,
        format="线上视频",
        result="通过",
        self_score=8,
    )
    store = store_module.LocalInterviewStore(tmp_path)

    saved = store.save(draft, "operation-save-roundtrip")
    loaded = store.get(saved.id)

    assert saved.id == loaded.id
    assert loaded.application_id == draft.application_id
    assert loaded.company == draft.company
    assert loaded.round_name == draft.round_name
    assert loaded.raw_notes == draft.raw_notes
    assert loaded.scheduled_at == scheduled_at
    assert loaded.format == "线上视频"
    assert loaded.result == "通过"
    assert loaded.self_score == 8
    assert loaded.sync_status == "local"
    assert loaded.markdown_path == saved.markdown_path
    assert loaded.markdown_path.parent == tmp_path
    markdown = loaded.markdown_path.read_text(encoding="utf-8")
    assert markdown.startswith("# 示例科技 - 技术一面")
    assert draft.raw_notes in markdown
    assert "✅" in markdown


def test_raw_notes_preserve_leading_spaces_and_trailing_newlines(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    raw_notes = "    indented code\nsecond line\n\n"
    draft = make_draft(store_module, raw_notes=raw_notes)

    saved = store_module.LocalInterviewStore(tmp_path).save(draft, "verbatim-notes")

    assert draft.raw_notes == raw_notes
    assert saved.raw_notes == raw_notes
    assert store_module.LocalInterviewStore(tmp_path).get(saved.id).raw_notes == raw_notes


def test_save_is_idempotent_by_operation_id_without_rewriting(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    original = store.save(make_draft(store_module), "same-operation")
    original_bytes = original.markdown_path.read_bytes()
    original_index = (tmp_path / "index.json").read_bytes()

    def unexpected_replace(source: str | Path, destination: str | Path) -> None:
        raise AssertionError(f"idempotent save attempted to replace {destination}")

    monkeypatch.setattr(store_module.os, "replace", unexpected_replace)
    repeated = store.save(
        make_draft(store_module, raw_notes="different notes", company="另一家公司"),
        "same-operation",
    )

    assert repeated == original
    assert repeated.raw_notes == original.raw_notes
    assert original.markdown_path.read_bytes() == original_bytes
    assert (tmp_path / "index.json").read_bytes() == original_index


def test_operation_id_is_preserved_and_idempotent_with_surrounding_spaces(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    operation_id = " operation-with-spaces "
    store = store_module.LocalInterviewStore(tmp_path)

    first = store.save(make_draft(store_module), operation_id)
    repeated = store.save(make_draft(store_module), operation_id)

    assert repeated == first
    assert first.operation_id == operation_id
    assert first.id == hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:16]


def test_ids_are_stable_sha256_prefixes(store_module: ModuleType, tmp_path: Path) -> None:
    first = store_module.LocalInterviewStore(tmp_path).save(
        make_draft(store_module),
        "stable-operation",
    )
    second = store_module.LocalInterviewStore(tmp_path).get(first.id)

    assert first.id == "0ef89931cdd47865"
    assert second.id == first.id


def test_list_is_newest_first_and_filters_by_application(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    start = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    moments = iter(start + timedelta(minutes=offset) for offset in range(3))
    store = store_module.LocalInterviewStore(tmp_path, clock=lambda: next(moments))
    first = store.save(make_draft(store_module, application_id="app_a"), "op-a")
    second = store.save(make_draft(store_module, application_id="app_b"), "op-b")
    third = store.save(
        make_draft(store_module, application_id="app_a", round_name="二面"),
        "op-c",
    )

    assert [record.id for record in store.list()] == [third.id, second.id, first.id]
    assert [record.id for record in store.list("app_a")] == [third.id, first.id]
    assert store.list("missing") == []


def test_list_uses_latest_insertion_when_created_times_match(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    fixed_time = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    store = store_module.LocalInterviewStore(tmp_path, clock=lambda: fixed_time)
    first = store.save(make_draft(store_module), "same-time-first")
    second = store.save(
        make_draft(store_module, round_name="二面"),
        "same-time-second",
    )

    assert [record.id for record in store.list()] == [second.id, first.id]


def test_filename_is_normalized_sanitized_bounded_and_stays_under_root(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    company = "Ａ" * 100 + "../\\CON:<bad>*? |. "
    round_name = "Ｂ" * 100 + "\x00\x1f../../escape. "
    store = store_module.LocalInterviewStore(tmp_path)

    saved = store.save(
        make_draft(store_module, company=company, round_name=round_name),
        "unsafe-path-operation",
    )

    assert saved.markdown_path.parent.resolve() == tmp_path.resolve()
    assert saved.markdown_path.name.startswith("A" * 80 + "-" + "B" * 80 + "-")
    assert saved.markdown_path.name.endswith(f"-{saved.id}.md")
    assert not any(character in saved.markdown_path.name for character in '<>:"/\\|?*')
    assert not any(ord(character) < 32 for character in saved.markdown_path.name)
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    filename = index["records"][0]["markdown_filename"]
    assert filename == saved.markdown_path.name
    assert Path(filename).name == filename


def test_filename_limits_components_by_windows_utf16_units(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    draft = make_draft(store_module, company="😀" * 80, round_name="🚀" * 80)

    saved = store_module.LocalInterviewStore(tmp_path).save(draft, "emoji-filename")

    assert saved.markdown_path.exists()
    assert len(saved.markdown_path.name.encode("utf-16-le")) // 2 <= 255
    company_component, round_component, _ = saved.markdown_path.name.rsplit("-", 2)
    assert len(company_component.encode("utf-16-le")) // 2 <= 80
    assert len(round_component.encode("utf-16-le")) // 2 <= 80


def test_save_recovers_matching_orphan_markdown_after_interrupted_index_commit(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    operation_id = "interrupted-save"
    draft = make_draft(store_module)
    interview_id = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:16]
    tmp_path.mkdir(parents=True, exist_ok=True)
    orphan = tmp_path / store_module._markdown_filename(draft, interview_id)
    orphan.write_text(store_module._markdown_text(draft), encoding="utf-8")

    saved = store_module.LocalInterviewStore(tmp_path).save(draft, operation_id)

    assert saved.markdown_path == orphan
    assert len(store_module.LocalInterviewStore(tmp_path).list()) == 1


def test_index_excludes_raw_notes_tokens_and_private_links(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    secret = "secret-token https://private.example/interview/42"
    saved = store_module.LocalInterviewStore(tmp_path).save(
        make_draft(store_module, raw_notes=f"notes {secret}"),
        "privacy-operation",
    )

    index_text = (tmp_path / "index.json").read_text(encoding="utf-8")
    assert "raw_notes" not in index_text
    assert "secret-token" not in index_text
    assert "private.example" not in index_text
    assert secret in saved.markdown_path.read_text(encoding="utf-8")


def test_missing_markdown_file_is_reported(store_module: ModuleType, tmp_path: Path) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    saved = store.save(make_draft(store_module), "missing-markdown")
    saved.markdown_path.unlink()

    with pytest.raises(FileNotFoundError):
        store.get(saved.id)
    with pytest.raises(FileNotFoundError):
        store.list()


def test_missing_interview_id_raises_key_error(store_module: ModuleType, tmp_path: Path) -> None:
    store = store_module.LocalInterviewStore(tmp_path)

    with pytest.raises(KeyError, match="missing"):
        store.get("missing")
    with pytest.raises(KeyError, match="missing"):
        store.mark_sync("missing", "pending")


def test_record_and_mark_sync_reject_invalid_sync_states(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    saved = store.save(make_draft(store_module), "sync-validation")
    record_data = saved.model_dump(mode="python")
    record_data["sync_status"] = "invalid"

    with pytest.raises(ValidationError):
        store_module.LocalInterviewRecord.model_validate(record_data)
    with pytest.raises(ValidationError):
        store.mark_sync(saved.id, "invalid")
    with pytest.raises(ValidationError, match="notion_page_id"):
        store.mark_sync(saved.id, "synced")


def test_mark_sync_updates_only_index_and_preserves_page_id(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    created_at = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    updated_at = created_at + timedelta(minutes=5)
    moments = iter((created_at, updated_at, updated_at + timedelta(minutes=5)))
    store = store_module.LocalInterviewStore(tmp_path, clock=lambda: next(moments))
    saved = store.save(make_draft(store_module), "sync-update")
    markdown_before = saved.markdown_path.read_bytes()

    synced = store.mark_sync(saved.id, "synced", "notion-page-123")
    pending = store.mark_sync(saved.id, "pending")

    assert synced.sync_status == "synced"
    assert synced.notion_page_id == "notion-page-123"
    assert synced.updated_at == updated_at
    assert pending.sync_status == "pending"
    assert pending.notion_page_id == "notion-page-123"
    assert pending.updated_at > synced.updated_at
    assert pending.created_at == saved.created_at
    assert saved.markdown_path.read_bytes() == markdown_before
    assert b"notion-page-123" not in markdown_before


def test_markdown_replace_failure_keeps_index_absent_and_cleans_temps(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    real_replace = store_module.os.replace

    def fail_markdown(source: str | Path, destination: str | Path) -> None:
        if Path(destination).suffix == ".md":
            raise OSError("simulated markdown replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(store_module.os, "replace", fail_markdown)

    with pytest.raises(OSError, match="markdown replace"):
        store.save(make_draft(store_module), "markdown-atomic-failure")

    assert not (tmp_path / "index.json").exists()
    assert not list(tmp_path.glob("*.md"))
    assert not list(tmp_path.glob("*.tmp"))


def test_index_replace_failure_removes_new_markdown_and_keeps_old_index(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    existing = store.save(make_draft(store_module), "existing-operation")
    index_before = (tmp_path / "index.json").read_bytes()
    markdown_before = existing.markdown_path.read_bytes()
    real_replace = store_module.os.replace

    def fail_index(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == tmp_path / "index.json":
            raise OSError("simulated index replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(store_module.os, "replace", fail_index)

    with pytest.raises(OSError, match="index replace"):
        store.save(
            make_draft(store_module, company="新公司", round_name="二面"),
            "new-operation",
        )

    assert (tmp_path / "index.json").read_bytes() == index_before
    assert existing.markdown_path.read_bytes() == markdown_before
    assert [path.name for path in tmp_path.glob("*.md")] == [existing.markdown_path.name]
    assert not list(tmp_path.glob("*.tmp"))


def test_mark_sync_index_failure_keeps_previous_state(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    saved = store.save(make_draft(store_module), "mark-atomic-failure")
    index_before = (tmp_path / "index.json").read_bytes()
    real_replace = store_module.os.replace

    def fail_index(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == tmp_path / "index.json":
            raise OSError("simulated sync index failure")
        real_replace(source, destination)

    monkeypatch.setattr(store_module.os, "replace", fail_index)

    with pytest.raises(OSError, match="sync index"):
        store.mark_sync(saved.id, "pending")

    assert (tmp_path / "index.json").read_bytes() == index_before
    assert store.get(saved.id).sync_status == "local"
    assert not list(tmp_path.glob("*.tmp"))


def test_concurrent_save_and_mark_sync_do_not_lose_updates(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    seed_store = store_module.LocalInterviewStore(tmp_path)
    seed = seed_store.save(make_draft(store_module), "seed-operation")
    barrier = threading.Barrier(13)

    def save_one(number: int):
        store = store_module.LocalInterviewStore(tmp_path)
        barrier.wait()
        return store.save(
            make_draft(
                store_module,
                application_id=f"app_{number}",
                company=f"公司{number}",
                round_name=f"第{number}轮",
            ),
            f"concurrent-save-{number}",
        )

    def mark_seed(number: int):
        store = store_module.LocalInterviewStore(tmp_path)
        barrier.wait()
        return store.mark_sync(seed.id, "pending", f"page-{number}")

    with ThreadPoolExecutor(max_workers=13) as executor:
        futures = [executor.submit(save_one, number) for number in range(10)]
        futures.extend(executor.submit(mark_seed, number) for number in range(3))
        results = [future.result(timeout=15) for future in futures]

    records = seed_store.list()
    assert len(records) == 11
    assert len({record.id for record in records}) == 11
    assert len([result for result in results if result.id != seed.id]) == 10
    seed_after = seed_store.get(seed.id)
    assert seed_after.sync_status == "pending"
    assert seed_after.notion_page_id in {"page-0", "page-1", "page-2"}
    json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))


def test_concurrent_idempotent_saves_create_one_record_and_file(
    store_module: ModuleType,
    tmp_path: Path,
) -> None:
    barrier = threading.Barrier(8)

    def save_once():
        barrier.wait()
        return store_module.LocalInterviewStore(tmp_path).save(
            make_draft(store_module),
            "shared-concurrent-operation",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(executor.map(lambda _: save_once(), range(8)))

    assert len({record.id for record in records}) == 1
    assert len(store_module.LocalInterviewStore(tmp_path).list()) == 1
    assert len(list(tmp_path.glob("*.md"))) == 1


def test_lock_timeout_releases_thread_lock_and_sidecar_is_one_byte(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store_module, "LOCK_TIMEOUT_SECONDS", 0.05)
    entered = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with store_module._exclusive_index_lock(store.index_path):
            entered.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert entered.wait(timeout=2)

    try:
        with pytest.raises(RuntimeError, match="interview store is busy"):
            store.list()
    finally:
        release.set()
        holder.join(timeout=2)

    assert not holder.is_alive()
    assert store.list() == []
    sidecar = tmp_path / ".index.json.lock"
    assert sidecar.read_bytes() == b"\0"


def test_os_lock_timeout_releases_thread_lock(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = store_module.LocalInterviewStore(tmp_path)
    real_try_lock = store_module._try_lock_file
    monkeypatch.setattr(store_module, "LOCK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(store_module, "_try_lock_file", lambda _handle: False)

    with pytest.raises(RuntimeError, match="interview store is busy"):
        store.list()

    monkeypatch.setattr(store_module, "_try_lock_file", real_try_lock)
    assert store.list() == []
    assert (tmp_path / ".index.json.lock").read_bytes() == b"\0"


def test_empty_sidecar_is_os_locked_before_initialization(
    store_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.json"
    sizes_seen_when_locking: list[int] = []
    real_try_lock = store_module._try_lock_file

    def record_size_before_lock(handle) -> bool:
        handle.seek(0, 2)
        sizes_seen_when_locking.append(handle.tell())
        return real_try_lock(handle)

    monkeypatch.setattr(store_module, "_try_lock_file", record_size_before_lock)

    with store_module._exclusive_index_lock(index_path):
        pass

    assert sizes_seen_when_locking == [0]
    assert (tmp_path / ".index.json.lock").read_bytes() == b"\0"
