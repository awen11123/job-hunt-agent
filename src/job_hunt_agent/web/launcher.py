from __future__ import annotations

import atexit
import json
import os
import secrets
import signal
import socket
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Thread, current_thread, main_thread
from types import FrameType
from typing import BinaryIO, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn
from fastapi import FastAPI

from job_hunt_agent.local_app.config import LocalConfigStore
from job_hunt_agent.local_app.paths import app_data_root
from job_hunt_agent.web.app import create_app
from job_hunt_agent.web.resources import resource_root


LOOPBACK_HOST = "127.0.0.1"


class ServerController(Protocol):
    def configure(self, app: FastAPI, *, host: str, port: int) -> None: ...

    def run(self) -> None: ...

    def stop(self) -> None: ...


class Browser(Protocol):
    def open(self, url: str) -> bool: ...


class InstanceState(Protocol):
    def try_acquire(self) -> bool: ...

    def read_port(self) -> int | None: ...

    def write_port(self, port: int) -> None: ...

    def clear(self) -> None: ...

    def release(self) -> None: ...


class UvicornServerController:
    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None

    def configure(self, app: FastAPI, *, host: str, port: int) -> None:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

    def run(self) -> None:
        if self._server is None:
            raise RuntimeError("Server is not configured.")
        self._server.run()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True


class DefaultBrowser:
    def open(self, url: str) -> bool:
        return webbrowser.open(url)


def _lock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class FileInstanceState:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state_path = self.root / "instance.json"
        self.lock_path = self.root / "instance.lock"
        self._lock_handle: BinaryIO | None = None

    def try_acquire(self) -> bool:
        if self._lock_handle is not None:
            return True
        self.root.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        try:
            _lock_file(handle)
        except OSError:
            handle.close()
            return False
        self._lock_handle = handle
        return True

    def read_port(self) -> int | None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            port = payload["port"]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            return None
        return port

    def write_port(self, port: int) -> None:
        if self._lock_handle is None:
            raise RuntimeError("Instance lock is not held.")
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.root,
                prefix=".instance.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"port": port, "pid": os.getpid()}, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.state_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def clear(self) -> None:
        self.state_path.unlink(missing_ok=True)

    def release(self) -> None:
        handle = self._lock_handle
        self._lock_handle = None
        if handle is None:
            return
        try:
            _unlock_file(handle)
        finally:
            handle.close()


def frontend_dist_path() -> Path:
    packaged_root = resource_root()
    if getattr(sys, "_MEIPASS", None) is not None or packaged_root.is_dir():
        return packaged_root
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def find_free_port(host: str = LOOPBACK_HOST) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((host, 0))
        return int(listener.getsockname()[1])


def health_is_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.25) as response:  # noqa: S310 - fixed loopback URL
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload == {"status": "ok"}
    except (HTTPError, URLError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


@dataclass(frozen=True)
class LaunchResult:
    url: str
    started_server: bool


class WindowsLauncher:
    def __init__(
        self,
        *,
        server: ServerController | None = None,
        browser: Browser | None = None,
        instance_state: InstanceState | None = None,
        config_path: Path | None = None,
        static_dir: Path | None = None,
        port_selector: Callable[[str], int] = find_free_port,
        health_probe: Callable[[str], bool] = health_is_ready,
        startup_timeout: float = 15.0,
        poll_interval: float = 0.05,
        port_attempts: int = 3,
    ) -> None:
        if port_attempts < 1:
            raise ValueError("port_attempts must be positive")
        resolved_config_path = config_path or app_data_root() / "config.json"
        self._server = server or UvicornServerController()
        self._browser = browser or DefaultBrowser()
        self._instance_state = instance_state or FileInstanceState(resolved_config_path.parent)
        self._config_path = resolved_config_path
        self._static_dir = static_dir or frontend_dist_path()
        self._port_selector = port_selector
        self._health_probe = health_probe
        self._startup_timeout = startup_timeout
        self._poll_interval = poll_interval
        self._port_attempts = port_attempts
        self._server_thread: Thread | None = None
        self._owns_instance = False
        self._cleanup_registered = False

    def start(self) -> LaunchResult:
        if not (self._static_dir / "index.html").is_file():
            raise RuntimeError("The frontend build is unavailable.")

        if not self._instance_state.try_acquire():
            reused = self._wait_for_existing_instance()
            if reused is None:
                raise RuntimeError("Another instance is starting but is not healthy.")
            self._open_browser(reused)
            return LaunchResult(url=reused, started_server=False)

        existing_port = self._instance_state.read_port()
        if existing_port is not None:
            existing_url = self._root_url(existing_port)
            if self._health_probe(f"{existing_url}api/health"):
                self._instance_state.release()
                self._open_browser(existing_url)
                return LaunchResult(url=existing_url, started_server=False)
            self._instance_state.clear()

        self._owns_instance = True
        try:
            result = self._start_new_instance()
            if not self._cleanup_registered:
                atexit.register(self.shutdown)
                self._cleanup_registered = True
            self._open_browser(result.url)
            return result
        except BaseException:
            self.shutdown()
            raise

    def run(self) -> None:
        result = self.start()
        if not result.started_server:
            return

        previous_handlers = self._install_signal_handlers()
        try:
            if self._server_thread is not None:
                self._server_thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()
            self._restore_signal_handlers(previous_handlers)

    def shutdown(self) -> None:
        if not self._owns_instance:
            return
        self._owns_instance = False
        try:
            self._server.stop()
            if self._server_thread is not None:
                self._server_thread.join(timeout=5)
        finally:
            try:
                self._instance_state.clear()
            finally:
                self._instance_state.release()

    def _start_new_instance(self) -> LaunchResult:
        session_token = secrets.token_urlsafe(32)
        for _attempt in range(self._port_attempts):
            port = self._port_selector(LOOPBACK_HOST)
            app = create_app(
                LocalConfigStore(self._config_path),
                session_token=session_token,
                static_dir=self._static_dir,
            )
            self._server.configure(app, host=LOOPBACK_HOST, port=port)
            thread = Thread(
                target=self._server.run,
                name="job-hunt-agent-server",
                daemon=True,
            )
            self._server_thread = thread
            thread.start()
            root_url = self._root_url(port)
            if self._wait_until_healthy(f"{root_url}api/health", thread):
                self._instance_state.write_port(port)
                return LaunchResult(url=root_url, started_server=True)
            self._server.stop()
            thread.join(timeout=1)
            if thread.is_alive():
                raise RuntimeError("Local server did not stop after failed startup.")
        raise RuntimeError("Local server failed to become healthy.")

    def _wait_for_existing_instance(self) -> str | None:
        deadline = time.monotonic() + self._startup_timeout
        while True:
            port = self._instance_state.read_port()
            if port is not None:
                root_url = self._root_url(port)
                if self._health_probe(f"{root_url}api/health"):
                    return root_url
            if time.monotonic() >= deadline:
                return None
            time.sleep(self._poll_interval)

    def _wait_until_healthy(self, health_url: str, thread: Thread) -> bool:
        deadline = time.monotonic() + self._startup_timeout
        while True:
            if self._health_probe(health_url):
                return True
            if time.monotonic() >= deadline or not thread.is_alive():
                return False
            time.sleep(self._poll_interval)

    def _open_browser(self, root_url: str) -> None:
        if not self._browser.open(root_url):
            print(f"浏览器未能自动打开，请访问：{root_url}")

    def _install_signal_handlers(self) -> dict[signal.Signals, object]:
        if current_thread() is not main_thread():
            return {}
        previous: dict[signal.Signals, object] = {}
        for handled_signal in (signal.SIGINT, signal.SIGTERM):
            previous[handled_signal] = signal.getsignal(handled_signal)
            signal.signal(handled_signal, self._handle_signal)
        return previous

    @staticmethod
    def _restore_signal_handlers(previous: dict[signal.Signals, object]) -> None:
        for handled_signal, handler in previous.items():
            signal.signal(handled_signal, handler)

    def _handle_signal(self, _signum: int, _frame: FrameType | None) -> None:
        self.shutdown()

    @staticmethod
    def _root_url(port: int) -> str:
        return f"http://{LOOPBACK_HOST}:{port}/"


LocalLauncher = WindowsLauncher


def main() -> int:
    try:
        WindowsLauncher().run()
    except (OSError, RuntimeError):
        print("本地应用启动失败，请确认前端已构建且端口可用。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
