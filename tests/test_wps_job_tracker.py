import os
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from scripts.wps_job_tracker import HEADERS, build_workbook


def sample_record(*, company: str, applied_date: str) -> dict[str, str]:
    return {
        "company": company,
        "role": "Agent 工程师",
        "applied_date": applied_date,
        "location": "杭州",
        "status": "已投递",
        "next_step": "等待通知",
        "next_time": "",
        "link": "",
        "notes": "",
    }


def test_build_workbook_layout_sorting_and_links(tmp_path: Path) -> None:
    output = tmp_path / "tracker.xlsx"
    records = [
        {
            "company": "较早企业",
            "role": "AI 工程师",
            "applied_date": "2026-08-01",
            "location": "北京",
            "status": "已投递",
            "next_step": "等待通知",
            "next_time": "",
            "link": "https://example.com/old",
            "notes": "",
        },
        {
            "company": "最新企业",
            "role": "Agent 工程师",
            "applied_date": "2026-08-30",
            "location": "杭州",
            "status": "面试安排中",
            "next_step": "确认时间",
            "next_time": "2026-09-01 10:00",
            "link": "https://example.com/new",
            "notes": "重点跟进",
        },
    ]

    build_workbook(records, output)

    workbook = load_workbook(output)
    sheet = workbook["投递总览"]
    assert [cell.value for cell in sheet[1]] == list(HEADERS)
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:I3"
    assert sheet["A2"].value == "最新企业"
    assert sheet["A3"].value == "较早企业"
    assert sheet["H2"].hyperlink.target == "https://example.com/new"
    assert sheet["E2"].fill.fgColor.rgb != sheet["E3"].fill.fgColor.rgb


def test_failed_save_preserves_existing_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "tracker.xlsx"
    build_workbook(
        [sample_record(company="第一版", applied_date="2026-08-29")], output
    )

    def interrupted_save(_workbook: Workbook, filename: str | Path) -> None:
        Path(filename).write_bytes(b"incomplete workbook")
        raise OSError("simulated interrupted save")

    monkeypatch.setattr(Workbook, "save", interrupted_save)
    with pytest.raises(OSError, match="simulated interrupted save"):
        build_workbook(
            [sample_record(company="第二版", applied_date="2026-08-30")], output
        )
    monkeypatch.undo()

    workbook = load_workbook(output)
    assert workbook["投递总览"]["A2"].value == "第一版"


def test_build_workbook_rejects_unexpected_fields(tmp_path: Path) -> None:
    record = sample_record(company="示例企业", applied_date="2026-08-30")
    record["unexpected"] = "不应写入"

    with pytest.raises(ValueError, match="exactly the nine normalized fields"):
        build_workbook([record], tmp_path / "tracker.xlsx")


def test_locked_workbook_reports_how_to_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "tracker.xlsx"
    build_workbook(
        [sample_record(company="第一版", applied_date="2026-08-29")], output
    )

    def deny_replace(_source: str | Path, _target: str | Path) -> None:
        raise PermissionError("file is locked")

    monkeypatch.setattr(os, "replace", deny_replace)
    with pytest.raises(RuntimeError, match="关闭 WPS"):
        build_workbook(
            [sample_record(company="第二版", applied_date="2026-08-30")], output
        )
