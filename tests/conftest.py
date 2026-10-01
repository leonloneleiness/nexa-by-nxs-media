"""Cấu hình pytest chung. Kiểm thử KHÔNG điều khiển máy thật: ranh giới hệ điều hành được giả lập."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Config độc lập: không đọc .env thật, không ghi vào config/ của dự án."""
    for var in ("GEMINI_API_KEY", "GEMINI_MODEL", "NEXA_CLOUD_SCREEN_VISION", "NEXA_AI_PROVIDER",
                "NEXA_MAX_TOOL_STEPS", "GEMINI_REQUEST_TIMEOUT_SECONDS"):
        monkeypatch.delenv(var, raising=False)
    from nexa.utils.config import Config
    cfg = Config(settings_path=tmp_path / "settings.yaml", gestures_path=tmp_path / "gestures.yaml", load_env=False)
    cfg.set("files.allowed_roots", [str(tmp_path / "allowed")])
    cfg.set("files.screenshot_dir", str(tmp_path / "shots"))
    cfg.set("ai.retry_base_s", 0.01)
    (tmp_path / "allowed").mkdir()
    return cfg
