from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_FILE = ROOT / "data" / "app_settings.json"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StoredSettings:
    settings: dict[str, Any]
    updated_at: str


def settings_file_path() -> Path:
    configured = os.getenv("SENTINEL_SETTINGS_FILE")
    return Path(configured) if configured else DEFAULT_SETTINGS_FILE


def load_settings_file() -> StoredSettings | None:
    path = settings_file_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        logger.warning("Ignoring corrupt settings file %s: %s", path, exc)
        return None
    except OSError as exc:
        logger.warning("Unable to read settings file %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    settings = raw.get("settings")
    if not isinstance(settings, dict):
        return None
    return StoredSettings(
        settings=settings,
        updated_at=str(raw.get("updated_at") or ""),
    )


def save_settings_file(settings: dict[str, Any], updated_at: str) -> None:
    path = settings_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    payload = {
        "settings": settings,
        "updated_at": updated_at,
    }
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)
