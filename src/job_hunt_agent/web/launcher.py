from __future__ import annotations

import json
import socket
import sys
import time
import webbrowser
from pathlib import Path
from threading import Thread
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn
from fastapi import FastAPI

from job_hunt_agent.local_app.config import LocalConfigStore
from job_hunt_agent.local_app.paths import app_data_root
from job_hunt_agent.web.app import create_app


LOOPBACK_HOST = "127.0.0.1"


class ServerController(Protocol):
    def configure(self, app: FastAPI, *, host: str, port: int) -> None: ...

    def run(self) -> None: ...

    def stop(self) -> None: ...


class Browser(Protocol):
    def open(self, url: str) -> bool: ...


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


def frontend_dist_path() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root is not None:
        return Path(bundled_root) / "web_static"
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


class LocalLauncher:
    def __init__(
        self,
        *,
        server: ServerController | None = None,
        browser: Browser | None = None,
        config_path: Path | None = None,
        static_dir: Path | None = None,
        port_selector=find_free_port,
        health_probe=health_is_ready,
        startup_timeout: float = 15.0,
        poll_interval: float = 0.05,
    ) -> None:
        self._server = server or UvicornServerController()
        self._browser = browser or DefaultBrowser()
        self._config_path = config_path or app_data_root() / "config.json"
        self._static_dir = static_dir or frontend_dist_path()
        self._port_selector = port_selector
        self._health_probe = health_probe
        self._startup_timeout = startup_timeout
        self._poll_interval = poll_interval

    def run(self) -> None:
        if not (self._static_dir / "index.html").is_file():
            raise RuntimeError("The frontend build is unavailable.")
        port = self._port_selector(LOOPBACK_HOST)
        app = create_app(
            LocalConfigStore(self._config_path),
            static_dir=self._static_dir,
        )
        self._server.configure(app, host=LOOPBACK_HOST, port=port)
        server_thread = Thread(target=self._server.run, name="job-hunt-agent-server", daemon=True)
        server_thread.start()

        root_url = f"http://{LOOPBACK_HOST}:{port}/"
        health_url = f"{root_url}api/health"
        deadline = time.monotonic() + self._startup_timeout
        healthy = False
        while True:
            if self._health_probe(health_url):
                healthy = True
                break
            if time.monotonic() >= deadline or not server_thread.is_alive():
                break
            time.sleep(self._poll_interval)

        if not healthy:
            self._server.stop()
            server_thread.join(timeout=1)
            raise RuntimeError("Local server failed to become healthy.")

        try:
            opened = self._browser.open(root_url)
            if not opened:
                print(f"浏览器未能自动打开，请访问：{root_url}")
            server_thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            self._server.stop()
            server_thread.join(timeout=5)


def main() -> int:
    try:
        LocalLauncher().run()
    except (OSError, RuntimeError):
        print("本地应用启动失败，请确认前端已构建且端口可用。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
