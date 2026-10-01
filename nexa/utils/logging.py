"""Logging xoay vòng có lọc bí mật.

Mọi bản ghi đi qua RedactingFilter: giá trị GEMINI_API_KEY hiện tại, các key đã đăng ký và
mẫu key Google (AIza...) đều bị thay bằng "[ĐÃ ẨN]" trước khi ghi ra tệp hoặc console.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import threading
from pathlib import Path

_SECRETS: set[str] = set()
_SECRETS_LOCK = threading.Lock()
_KEY_PATTERNS = [
    # Google (AIza…, key mới dạng AQ.…), Tripo (tsk_), Meshy (msy_), Hugging Face (hf_)
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}|\bAQ\.[0-9A-Za-z_\-]{30,}|\b(?:tsk|msy)_[0-9A-Za-z_\-]{12,}|\bhf_[0-9A-Za-z]{20,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s&'\"]+)"),
    re.compile(r"(?i)(key=)([0-9A-Za-z_\-]{20,})"),
]
REDACTED = "[ĐÃ ẨN]"


def register_secret(value: str | None) -> None:
    if value and len(value.strip()) >= 8:
        with _SECRETS_LOCK:
            _SECRETS.add(value.strip())


def redact(text: str) -> str:
    if not text:
        return text
    with _SECRETS_LOCK:
        secrets = set(_SECRETS)
    for var in ("GEMINI_API_KEY", "TRIPO_API_KEY", "MESHY_API_KEY", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        env_key = os.environ.get(var, "").strip()
        if len(env_key) >= 8:
            secrets.add(env_key)
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    text = _KEY_PATTERNS[0].sub(REDACTED, text)
    text = _KEY_PATTERNS[1].sub(lambda m: m.group(1) + REDACTED, text)
    text = _KEY_PATTERNS[2].sub(lambda m: m.group(1) + REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - định dạng lỗi
            message = str(record.msg)
        clean = redact(message)
        if record.exc_info:
            formatted = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact(formatted)
            record.exc_info = None
        record.msg = clean
        record.args = ()
        return True


_configured = False


def setup_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    global _configured
    root = logging.getLogger()
    if _configured:
        return logging.getLogger("nexa")
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "nexa.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactingFilter())
    stream = sys.stderr
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    console = logging.StreamHandler(stream)
    console.setFormatter(fmt)
    console.addFilter(RedactingFilter())
    root.handlers[:] = [file_handler, console]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for noisy in ("httpx", "httpcore", "urllib3", "comtypes", "PIL", "faster_whisper", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
    return logging.getLogger("nexa")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"nexa.{name}")
