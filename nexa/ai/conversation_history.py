"""Bounded, text-only local history. Never serialize SDK Content objects."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from nexa.utils.logging import get_logger, redact

log = get_logger("conversation_history")
MAX_BYTES = 256 * 1024
MAX_TEXT = 16 * 1024
MAX_TURNS = 50


def bounded(turns: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for user, model in turns[-max(1, min(MAX_TURNS, limit)):]:
        if not all(isinstance(t, str) and t.strip() and len(t) <= MAX_TEXT for t in (user, model)):
            continue
        try:
            (user + model).encode("utf-8")
        except UnicodeError:
            continue
        result.append((redact(user), redact(model)))
    while result and len(_encode(result)) > MAX_BYTES:
        result.pop(0)
    return result


def _encode(turns: list[tuple[str, str]]) -> bytes:
    messages = [{"role": role, "text": text} for turn in turns
                for role, text in zip(("user", "model"), turn)]
    return json.dumps({"version": 1, "messages": messages}, ensure_ascii=False).encode("utf-8")


class ConversationHistory:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, limit: int) -> list[tuple[str, str]]:
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("size")
            data = json.loads(raw)
            if (not isinstance(data, dict) or set(data) != {"version", "messages"}
                    or type(data["version"]) is not int or data["version"] != 1):
                raise ValueError("schema")
            messages = data["messages"]
            if not isinstance(messages, list) or len(messages) % 2 or len(messages) > MAX_TURNS * 2:
                raise ValueError("turns")
            for i, message in enumerate(messages):
                if (not isinstance(message, dict) or set(message) != {"role", "text"}
                        or message["role"] != ("user" if i % 2 == 0 else "model")
                        or not isinstance(message["text"], str) or not message["text"].strip()
                        or len(message["text"]) > MAX_TEXT):
                    raise ValueError("message")
            return bounded([(messages[i]["text"], messages[i + 1]["text"])
                            for i in range(0, len(messages), 2)], limit)
        except FileNotFoundError:
            return []
        except (OSError, ValueError, RecursionError):
            log.warning("Không đọc được lịch sử hội thoại cục bộ; bỏ qua tệp.")
            return []

    def save(self, turns: list[tuple[str, str]], limit: int) -> None:
        temporary = None
        try:
            payload = _encode(bounded(turns, limit))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=self.path.name + ".",
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, ValueError):
            log.warning("Không lưu được lịch sử hội thoại cục bộ.")
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    log.warning("Không xóa được tệp lịch sử tạm.")

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            log.warning("Không xóa được lịch sử hội thoại đã lưu trên máy.")
