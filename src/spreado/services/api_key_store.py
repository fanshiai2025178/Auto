"""本地 API Key 存储。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from spreado.conf import AI_SETTINGS_FILE, CONFIG_DIR, DOUBAO_VIDEO_MODEL


@dataclass
class AISettings:
    api_key: str = ""
    model: str = DOUBAO_VIDEO_MODEL

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())


def _settings_path() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return AI_SETTINGS_FILE


def load_ai_settings() -> AISettings:
    path = _settings_path()
    if not path.exists():
        return AISettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AISettings(
            api_key=str(data.get("api_key", "")).strip(),
            model=str(data.get("model", DOUBAO_VIDEO_MODEL)).strip() or DOUBAO_VIDEO_MODEL,
        )
    except (json.JSONDecodeError, OSError):
        return AISettings()


def save_ai_settings(api_key: str, model: Optional[str] = None) -> AISettings:
    settings = AISettings(
        api_key=api_key.strip(),
        model=(model or DOUBAO_VIDEO_MODEL).strip(),
    )
    path = _settings_path()
    path.write_text(
        json.dumps({"api_key": settings.api_key, "model": settings.model}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return settings


def mask_api_key(api_key: str) -> str:
    key = api_key.strip()
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"
