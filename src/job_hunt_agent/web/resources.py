from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root is not None:
        return Path(bundled_root) / "web_static"
    return Path(__file__).resolve().parents[1] / "web_static"
