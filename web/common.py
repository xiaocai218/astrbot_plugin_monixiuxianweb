from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "webui"
CONFIG_DIR = ROOT_DIR / "config"


def load_json_file(path: Path, default: Any):
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return default


def load_web_server_config() -> dict[str, Any]:
    config = load_json_file(CONFIG_DIR / "game_config.json", {})
    web_config = config.get("web_server", {}) if isinstance(config, dict) else {}

    enabled = bool(web_config.get("enabled", False))
    host = str(web_config.get("host", "0.0.0.0") or "0.0.0.0")
    try:
        port = int(web_config.get("port", 8765) or 8765)
    except (TypeError, ValueError):
        port = 8765

    return {
        "enabled": enabled,
        "host": host,
        "port": port,
    }


def detect_default_db() -> Path | None:
    candidates = [
        ROOT_DIR / "xiuxian_data_lite.db",
        ROOT_DIR / "xiuxian_data_v2.db",
    ]

    appdata = os.getenv("APPDATA")
    if appdata:
        plugin_dir = Path(appdata) / "AstrBot" / "data" / "astrbot_plugin_monixiuxian2"
        candidates.extend(
            [
                plugin_dir / "xiuxian_data_v2.db",
                plugin_dir / "xiuxian_data_lite.db",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
