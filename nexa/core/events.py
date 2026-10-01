"""Kiểu dữ liệu sự kiện và kết quả dùng chung giữa các module."""
from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class AppState(str, Enum):
    INITIALIZING = "INITIALIZING"
    STANDBY = "STANDBY"
    WAKING = "WAKING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    CONFIRMING = "CONFIRMING"
    ERROR = "ERROR"


STATE_LABELS_VI = {
    AppState.INITIALIZING: "Đang khởi tạo",
    AppState.STANDBY: "Đang chờ tiếng vỗ tay",
    AppState.WAKING: "Đang thức dậy",
    AppState.LISTENING: "Đang nghe",
    AppState.THINKING: "Đang suy nghĩ",
    AppState.EXECUTING: "Đang thực hiện",
    AppState.SPEAKING: "Đang nói",
    AppState.CONFIRMING: "Cần anh xác nhận",
    AppState.ERROR: "Có lỗi",
}


class Risk(IntEnum):
    LOW = 0      # thực hiện ngay
    MEDIUM = 1   # cần xác nhận khi do AI đề xuất
    HIGH = 2     # luôn cần xác nhận


class Source(str, Enum):
    VOICE = "voice"
    KEYBOARD = "keyboard"
    GESTURE = "gesture"
    AI = "ai"
    SYSTEM = "system"


class GestureEvent(str, Enum):
    MOVE_WINDOW_TO_MONITOR_2 = "MOVE_WINDOW_TO_MONITOR_2"
    MINIMIZE_ACTIVE_WINDOW = "MINIMIZE_ACTIVE_WINDOW"
    RESTORE_LAST_MINIMIZED_WINDOW = "RESTORE_LAST_MINIMIZED_WINDOW"
    YOUTUBE_PAUSE = "YOUTUBE_PAUSE"
    YOUTUBE_RESUME = "YOUTUBE_RESUME"
    SCROLL_UP = "SCROLL_UP"


_step_counter = itertools.count(1)


def new_task_id(prefix: str = "task") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def new_step_id() -> str:
    return f"step-{next(_step_counter)}"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    source: Source = Source.SYSTEM
    task_id: str = field(default_factory=new_task_id)
    step_id: str = field(default_factory=new_step_id)
    call_id: str | None = None          # ID function call do Gemini cấp (nếu có)
    snapshot: Any = None                # ảnh chụp trạng thái cửa sổ lúc bắt đầu cử chỉ

    @property
    def idempotency_key(self) -> tuple[str, str]:
        return (self.task_id, self.call_id or self.step_id)


@dataclass
class ToolResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    error_code: str | None = None

    @classmethod
    def success(cls, message: str, verified: bool = True, **data: Any) -> "ToolResult":
        return cls(ok=True, message=message, data=data, verified=verified)

    @classmethod
    def failure(cls, message: str, code: str = "failed", **data: Any) -> "ToolResult":
        return cls(ok=False, message=message, data=data, verified=False, error_code=code)

    def to_model_payload(self) -> dict[str, Any]:
        """Dữ liệu gửi lại cho Gemini dưới dạng tool response."""
        payload: dict[str, Any] = {"ok": self.ok, "verified": self.verified, "message": self.message}
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.data:
            payload["data"] = _json_safe(self.data)
        return payload


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in list(value.items())[:60]}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, depth + 1) for v in list(value)[:60]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > 4000:
            return value[:4000] + "…"
        return value
    return str(value)


@dataclass
class TaskEvent:
    """Sự kiện hiển thị trong bảng tác vụ/overlay."""
    task_id: str
    step_id: str
    tool: str
    status: str            # queued | running | done | failed | cancelled | rejected
    message: str
    source: Source
    ts: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
