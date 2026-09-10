import os
import sys
from collections.abc import Mapping
from pathlib import Path


def app_data_root(
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    environment = os.environ if env is None else env
    if sys.platform == "win32":
        appdata = environment.get("APPDATA")
        if appdata:
            return Path(appdata) / "JobHuntAgent"

    home_directory = Path.home() if home is None else home
    return home_directory / ".local" / "share" / "job-hunt-agent"
