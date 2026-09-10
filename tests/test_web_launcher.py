from __future__ import annotations

import logging
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from job_hunt_agent.local_app.config import LocalAppConfig, LocalConfigStore
from job_hunt_agent.web import create_app
from job_hunt_agent.web.launcher import LocalLauncher, frontend_dist_path


HEADERS = (
    "企业",
    "投递岗位",
    "投递日期",
    "所在地",
    "当前状态",
    "下一节点",
    "节点时间",
    "岗位链接",
    "备注",
)


class _RootTokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.session_token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div" and attributes.get("id") == "root":
            self.session_token = attributes.get("data-session-token")


def _session_token(html: str) -> str:
    parser = _RootTokenParser()
    parser.feed(html)
    assert parser.session_token
    return parser.session_token


def _build_store(tmp_path: Path, *, with_excel: bool = False) -> LocalConfigStore:
    store = LocalConfigStore(tmp_path / "config.json")
    config = LocalAppConfig.defaults(tmp_path / "app-data")
    if with_excel:
        workbook_path = tmp_path / "tracker.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "投递总览"
        sheet.append(HEADERS)
        workbook.save(workbook_path)
        workbook.close()
        config.excel_path = workbook_path
    store.save(config)
    return store


def _build_frontend(tmp_path: Path) -> tuple[Path, str]:
    frontend = tmp_path / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    index = (
        '<!doctype html><html><body><div id="root"></div>'
        '<script type="module" src="/assets/app.js"></script></body></html>'
    )
    (frontend / "index.html").write_text(index, encoding="utf-8")
    (assets / "app.js").write_text("console.log('public asset')", encoding="utf-8")
    return frontend, index


def test_app_serves_assets_and_spa_with_an_in_memory_session_token(tmp_path: Path) -> None:
    frontend, original_index = _build_frontend(tmp_path)
    store = _build_store(tmp_path)
    app = create_app(store, static_dir=frontend)
    client = TestClient(app, base_url="http://127.0.0.1")

    home = client.get("/")
    spa = client.get("/applications")
    asset = client.get("/assets/app.js")

    token = _session_token(home.text)
    assert home.status_code == 200
    assert home.headers["cache-control"] == "no-store"
    assert _session_token(spa.text) == token
    assert asset.text == "console.log('public asset')"
    assert (frontend / "index.html").read_text(encoding="utf-8") == original_index
    assert token not in str(home.request.url)
    assert token not in store.path.read_text(encoding="utf-8")


def test_existing_session_attribute_is_replaced_without_changing_index(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    original_index = '<div id="root" data-session-token="stale-token"></div>'
    index_path = frontend / "index.html"
    index_path.write_text(original_index, encoding="utf-8")
    client = TestClient(
        create_app(
            _build_store(tmp_path),
            session_token="current-process-token",
            static_dir=frontend,
        ),
        base_url="http://localhost",
    )

    response = client.get("/")

    assert response.status_code == 200
    assert _session_token(response.text) == "current-process-token"
    assert response.text.count("data-session-token") == 1
    assert "stale-token" not in response.text
    assert index_path.read_text(encoding="utf-8") == original_index


def test_static_fallback_does_not_mask_api_404_and_keeps_host_restriction(
    tmp_path: Path,
) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    app = create_app(_build_store(tmp_path), static_dir=frontend)
    local = TestClient(app, base_url="http://localhost")
    hostile = TestClient(app, base_url="http://attacker.example")

    missing_api = local.get("/api/not-found")

    assert missing_api.status_code == 404
    assert missing_api.headers["content-type"].startswith("application/json")
    assert "<!doctype html>" not in missing_api.text
    assert hostile.get("/").status_code == 400


def test_missing_asset_returns_404_instead_of_spa_html(tmp_path: Path) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    client = TestClient(
        create_app(_build_store(tmp_path), static_dir=frontend),
        base_url="http://localhost",
    )

    response = client.get("/assets/missing.js")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "<!doctype html>" not in response.text


@pytest.mark.parametrize("index_contents", [None, "<main>Missing root marker</main>"])
def test_static_frontend_requires_an_index_with_a_root_mount(
    tmp_path: Path,
    index_contents: str | None,
) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    if index_contents is not None:
        (frontend / "index.html").write_text(index_contents, encoding="utf-8")

    with pytest.raises(RuntimeError, match="frontend build is unavailable"):
        create_app(_build_store(tmp_path), static_dir=frontend)


def test_frontend_fails_closed_if_root_mount_disappears_after_start(tmp_path: Path) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    client = TestClient(
        create_app(_build_store(tmp_path), static_dir=frontend),
        base_url="http://localhost",
    )
    (frontend / "index.html").write_text("<main>Broken build</main>", encoding="utf-8")

    response = client.get("/")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "frontend_unavailable"


def test_served_token_authorizes_confirm_and_cancel_without_persistence(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    store = _build_store(tmp_path, with_excel=True)
    client = TestClient(
        create_app(store, static_dir=frontend),
        base_url="http://127.0.0.1",
    )
    caplog.set_level(logging.DEBUG)
    token = _session_token(client.get("/").text)

    confirm_preview = client.post(
        "/api/actions/propose",
        json={"text": "今天投了确认科技的 Agent 工程师，杭州"},
    ).json()
    confirmed = client.post(
        f"/api/actions/{confirm_preview['id']}/confirm",
        headers={"X-Job-Hunt-Session": token},
        json={"confirmation_token": confirm_preview["confirmation_token"]},
    )
    cancel_preview = client.post(
        "/api/actions/propose",
        json={"text": "今天投了取消科技的 LLM 应用工程师，上海"},
    ).json()
    cancelled = client.post(
        f"/api/actions/{cancel_preview['id']}/cancel",
        headers={"X-Job-Hunt-Session": token},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["receipt"]["status"] == "created"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert token not in store.path.read_text(encoding="utf-8")
    assert token not in caplog.text
    assert all(
        token.encode("utf-8") not in path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )


class _FakeServer:
    def __init__(self) -> None:
        self.host: str | None = None
        self.port: int | None = None
        self.ran = False
        self.stopped = False

    def configure(self, _app, *, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def run(self) -> None:
        self.ran = True

    def stop(self) -> None:
        self.stopped = True


class _FakeBrowser:
    def __init__(
        self,
        health_state: dict[str, bool],
        *,
        open_result: bool = True,
    ) -> None:
        self.health_state = health_state
        self.open_result = open_result
        self.urls: list[str] = []

    def open(self, url: str) -> bool:
        assert self.health_state["checked"]
        self.urls.append(url)
        return self.open_result


def test_launcher_binds_loopback_and_opens_browser_after_health_check(
    tmp_path: Path,
) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    server = _FakeServer()
    health_state = {"checked": False}
    browser = _FakeBrowser(health_state)

    def healthy(url: str) -> bool:
        health_state["checked"] = True
        assert url == "http://127.0.0.1:43127/api/health"
        return True

    launcher = LocalLauncher(
        server=server,
        browser=browser,
        config_path=tmp_path / "config.json",
        static_dir=frontend,
        port_selector=lambda host: 43127 if host == "127.0.0.1" else 0,
        health_probe=healthy,
        startup_timeout=0.1,
        poll_interval=0,
    )

    launcher.run()

    assert server.host == "127.0.0.1"
    assert server.port == 43127
    assert server.ran is True
    assert browser.urls == ["http://127.0.0.1:43127/"]


def test_launcher_prints_manual_url_when_browser_does_not_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    server = _FakeServer()
    browser = _FakeBrowser({"checked": True}, open_result=False)
    launcher = LocalLauncher(
        server=server,
        browser=browser,
        config_path=tmp_path / "config.json",
        static_dir=frontend,
        port_selector=lambda _host: 43127,
        health_probe=lambda _url: True,
    )

    launcher.run()

    output = capsys.readouterr().out
    assert output == "浏览器未能自动打开，请访问：http://127.0.0.1:43127/\n"
    assert "token" not in output.lower()
    assert server.ran is True
    assert server.stopped is True


def test_launcher_stops_server_and_does_not_open_browser_when_startup_fails(
    tmp_path: Path,
) -> None:
    frontend, _original_index = _build_frontend(tmp_path)
    server = _FakeServer()
    browser = _FakeBrowser({"checked": True})
    launcher = LocalLauncher(
        server=server,
        browser=browser,
        config_path=tmp_path / "config.json",
        static_dir=frontend,
        port_selector=lambda _host: 43127,
        health_probe=lambda _url: False,
        startup_timeout=0,
        poll_interval=0,
    )

    with pytest.raises(RuntimeError, match="failed to become healthy"):
        launcher.run()

    assert server.stopped is True
    assert browser.urls == []


def test_launcher_rejects_a_missing_frontend_before_starting(tmp_path: Path) -> None:
    server = _FakeServer()
    browser = _FakeBrowser({"checked": True})
    launcher = LocalLauncher(
        server=server,
        browser=browser,
        config_path=tmp_path / "config.json",
        static_dir=tmp_path / "missing-dist",
        port_selector=lambda _host: 43127,
        health_probe=lambda _url: True,
    )

    with pytest.raises(RuntimeError, match="frontend build is unavailable"):
        launcher.run()

    assert server.ran is False
    assert browser.urls == []


def test_frontend_dist_path_supports_source_and_pyinstaller_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert frontend_dist_path().as_posix().endswith("/frontend/dist")

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert frontend_dist_path() == tmp_path / "web_static"
