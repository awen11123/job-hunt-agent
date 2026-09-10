from __future__ import annotations

import threading
from pathlib import Path

from job_hunt_agent.web.launcher import LOOPBACK_HOST, WindowsLauncher


def build_frontend(tmp_path: Path) -> Path:
    frontend = tmp_path / "web_static"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        '<div id="root"></div>',
        encoding="utf-8",
    )
    return frontend


class FakeInstanceState:
    def __init__(self, *, acquired: bool, port: int | None = None) -> None:
        self.acquired = acquired
        self.port = port
        self.written_ports: list[int] = []
        self.clear_count = 0
        self.release_count = 0

    def try_acquire(self) -> bool:
        return self.acquired

    def read_port(self) -> int | None:
        return self.port

    def write_port(self, port: int) -> None:
        self.port = port
        self.written_ports.append(port)

    def clear(self) -> None:
        self.port = None
        self.clear_count += 1

    def release(self) -> None:
        self.release_count += 1


class FakeServer:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events
        self.configured: list[tuple[str, int]] = []
        self.stop_count = 0
        self.started = threading.Event()

    def configure(self, _app, *, host: str, port: int) -> None:
        self.configured.append((host, port))

    def run(self) -> None:
        if self.events is not None:
            self.events.append("server-start")
        self.started.set()

    def stop(self) -> None:
        self.stop_count += 1


class FakeBrowser:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events
        self.urls: list[str] = []

    def open(self, url: str) -> bool:
        if self.events is not None:
            self.events.append("browser-open")
        self.urls.append(url)
        return True


def test_second_launcher_reuses_healthy_instance(tmp_path: Path) -> None:
    state = FakeInstanceState(acquired=False, port=43127)
    server = FakeServer()
    browser = FakeBrowser()
    launcher = WindowsLauncher(
        instance_state=state,
        server=server,
        browser=browser,
        static_dir=build_frontend(tmp_path),
        health_probe=lambda url: url == "http://127.0.0.1:43127/api/health",
        startup_timeout=0,
        poll_interval=0,
    )

    result = launcher.start()

    assert result.started_server is False
    assert result.url == "http://127.0.0.1:43127/"
    assert browser.urls == [result.url]
    assert server.configured == []
    assert state.release_count == 0


def test_launcher_opens_browser_only_after_health_check(tmp_path: Path) -> None:
    events: list[str] = []
    state = FakeInstanceState(acquired=True)
    server = FakeServer(events)
    browser = FakeBrowser(events)

    def healthy(_url: str) -> bool:
        events.append("health-ok")
        return True

    launcher = WindowsLauncher(
        instance_state=state,
        server=server,
        browser=browser,
        static_dir=build_frontend(tmp_path),
        port_selector=lambda host: 43127 if host == LOOPBACK_HOST else 0,
        health_probe=healthy,
        startup_timeout=0,
        poll_interval=0,
    )

    launcher.start()

    assert events == ["server-start", "health-ok", "browser-open"]
    launcher.shutdown()


def test_stale_instance_state_is_replaced(tmp_path: Path) -> None:
    state = FakeInstanceState(acquired=True, port=43000)
    server = FakeServer()
    browser = FakeBrowser()

    launcher = WindowsLauncher(
        instance_state=state,
        server=server,
        browser=browser,
        static_dir=build_frontend(tmp_path),
        port_selector=lambda _host: 43127,
        health_probe=lambda url: ":43127/" in url,
        startup_timeout=0,
        poll_interval=0,
    )

    result = launcher.start()

    assert result.started_server is True
    assert state.clear_count == 1
    assert state.written_ports == [43127]
    launcher.shutdown()


def test_port_collision_retries_with_a_new_loopback_port(tmp_path: Path) -> None:
    selected = iter([43127, 43128])
    state = FakeInstanceState(acquired=True)
    server = FakeServer()
    launcher = WindowsLauncher(
        instance_state=state,
        server=server,
        browser=FakeBrowser(),
        static_dir=build_frontend(tmp_path),
        port_selector=lambda _host: next(selected),
        health_probe=lambda url: ":43128/" in url,
        startup_timeout=0,
        poll_interval=0,
        port_attempts=2,
    )

    result = launcher.start()

    assert result.url == "http://127.0.0.1:43128/"
    assert server.configured == [
        ("127.0.0.1", 43127),
        ("127.0.0.1", 43128),
    ]
    assert server.stop_count == 1
    launcher.shutdown()


def test_shutdown_stops_owned_server_and_releases_instance(tmp_path: Path) -> None:
    state = FakeInstanceState(acquired=True)
    server = FakeServer()
    launcher = WindowsLauncher(
        instance_state=state,
        server=server,
        browser=FakeBrowser(),
        static_dir=build_frontend(tmp_path),
        port_selector=lambda _host: 43127,
        health_probe=lambda _url: True,
        startup_timeout=0,
        poll_interval=0,
    )

    launcher.start()
    launcher.shutdown()
    launcher.shutdown()

    assert server.stop_count == 1
    assert state.clear_count == 1
    assert state.release_count == 1


def test_new_server_is_always_bound_to_loopback(tmp_path: Path) -> None:
    state = FakeInstanceState(acquired=True)
    server = FakeServer()
    launcher = WindowsLauncher(
        instance_state=state,
        server=server,
        browser=FakeBrowser(),
        static_dir=build_frontend(tmp_path),
        port_selector=lambda host: 43127 if host == LOOPBACK_HOST else 0,
        health_probe=lambda _url: True,
        startup_timeout=0,
        poll_interval=0,
    )

    launcher.start()

    assert server.configured == [("127.0.0.1", 43127)]
    launcher.shutdown()
