"""Quyền thao tác, xác nhận hành động và dừng khẩn cấp.

Mức ảnh hưởng (Risk) do mã Python xác định dựa trên công cụ, tham số và ngữ cảnh thực tế —
không dựa vào bất kỳ trường "an toàn" nào do model AI tự khai.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from nexa.core.events import Risk, Source, ToolCall
from nexa.utils.logging import get_logger

log = get_logger("safety")


class Cancelled(Exception):
    """Tác vụ đã bị hủy (dừng khẩn cấp, người dùng hủy hoặc hết giờ)."""


class CancelToken:
    """Token hủy gắn với 'epoch' của SafetyManager.

    Khi dừng khẩn cấp, epoch tăng lên nên mọi token cũ tự động bị hủy — kết quả LLM hoặc
    tác vụ đến muộn sẽ không thể kích hoạt executor.
    """

    def __init__(self, safety: "SafetyManager | None", epoch: int, label: str = "") -> None:
        self._safety = safety
        self._epoch = epoch
        self._event = threading.Event()
        self.label = label
        self.reason = ""

    def cancel(self, reason: str = "cancelled") -> None:
        self.reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        if self._event.is_set():
            return True
        return self._safety is not None and self._safety.epoch != self._epoch

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise Cancelled(self.reason or "stopped")

    def wait(self, seconds: float) -> bool:
        """Ngủ tối đa `seconds`, trả True nếu bị hủy trong lúc chờ."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.cancelled:
                return True
            self._event.wait(min(0.05, max(0.0, end - time.monotonic())))
        return self.cancelled


@dataclass
class Assessment:
    risk: Risk
    reason: str = ""

    def needs_confirmation(self, source: Source) -> bool:
        if self.risk >= Risk.HIGH:
            return True
        if self.risk == Risk.MEDIUM and source == Source.AI:
            return True
        return False


@dataclass
class PendingConfirmation:
    id: str
    call: ToolCall
    description: str
    fingerprint: str
    created: float
    expires_at: float
    preview: dict[str, Any] = field(default_factory=dict)
    approved: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at

    def remaining(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())


class SafetyManager:
    def __init__(self, confirm_timeout_s: float = 30.0) -> None:
        self._lock = threading.RLock()
        self.epoch = 0
        self.control_paused = False
        self.pause_reason = ""
        self.confirm_timeout_s = confirm_timeout_s
        self._pending: PendingConfirmation | None = None
        self._stop_listeners: list[Callable[[str], None]] = []
        self._confirm_listeners: list[Callable[[PendingConfirmation | None], None]] = []
        self._resume_listeners: list[Callable[[], None]] = []

    # ----- token -----
    def new_token(self, label: str = "") -> CancelToken:
        with self._lock:
            return CancelToken(self, self.epoch, label)

    # ----- listeners -----
    def on_stop(self, fn: Callable[[str], None]) -> None:
        self._stop_listeners.append(fn)

    def on_confirmation(self, fn: Callable[[PendingConfirmation | None], None]) -> None:
        self._confirm_listeners.append(fn)

    def on_resume(self, fn: Callable[[], None]) -> None:
        self._resume_listeners.append(fn)

    # ----- dừng khẩn cấp -----
    def emergency_stop(self, reason: str = "Dừng khẩn cấp") -> None:
        with self._lock:
            self.epoch += 1
            self.control_paused = True
            self.pause_reason = reason
            pending = self._pending
            self._pending = None
        log.warning("DỪNG KHẨN CẤP: %s (epoch=%d)", reason, self.epoch)
        if pending is not None:
            pending.approved = False
            pending._event.set()
            self._notify_confirmation(None)
        for fn in list(self._stop_listeners):
            try:
                fn(reason)
            except Exception:
                log.exception("Listener dừng khẩn cấp lỗi")

    def cancel_current(self, reason: str = "Người dùng hủy") -> None:
        """Hủy mọi tác vụ đang chạy nhưng không khóa điều khiển (lệnh 'hủy')."""
        with self._lock:
            self.epoch += 1
            pending = self._pending
            self._pending = None
        if pending is not None:
            pending.approved = False
            pending._event.set()
            self._notify_confirmation(None)
        log.info("Hủy tác vụ hiện tại: %s", reason)

    def resume_control(self) -> None:
        with self._lock:
            self.control_paused = False
            self.pause_reason = ""
        log.info("Người dùng bật lại quyền điều khiển")
        for fn in list(self._resume_listeners):
            try:
                fn()
            except Exception:
                log.exception("Listener resume lỗi")

    # ----- xác nhận -----
    @property
    def pending(self) -> PendingConfirmation | None:
        with self._lock:
            p = self._pending
            if p is not None and p.expired:
                self._pending = None
                p.approved = False
                p._event.set()
                expired = True
            else:
                expired = False
        if expired:
            self._notify_confirmation(None)
            return None
        return p

    def request_confirmation(self, call: ToolCall, description: str, fingerprint: str,
                             preview: dict[str, Any] | None = None,
                             timeout_s: float | None = None) -> PendingConfirmation:
        now = time.monotonic()
        pending = PendingConfirmation(
            id=uuid.uuid4().hex[:12], call=call, description=description, fingerprint=fingerprint,
            created=now, expires_at=now + (timeout_s or self.confirm_timeout_s), preview=preview or {})
        with self._lock:
            old = self._pending
            self._pending = pending
        if old is not None:
            old.approved = False
            old._event.set()
        log.info("Yêu cầu xác nhận %s: %s", pending.id, description)
        self._notify_confirmation(pending)
        return pending

    def resolve(self, confirm_id: str, approved: bool, extra: dict[str, Any] | None = None) -> bool:
        with self._lock:
            p = self._pending
            if p is None or p.id != confirm_id:
                return False
            self._pending = None
        if p.expired:
            p.approved = False
            p._event.set()
            self._notify_confirmation(None)
            log.info("Xác nhận %s đã hết hạn", confirm_id)
            return False
        p.approved = bool(approved)
        if extra:
            p.extra.update(extra)
        p._event.set()
        self._notify_confirmation(None)
        log.info("Xác nhận %s: %s", confirm_id, "ĐỒNG Ý" if approved else "TỪ CHỐI")
        return True

    def resolve_current(self, approved: bool) -> bool:
        p = self.pending
        return bool(p) and self.resolve(p.id, approved)

    def wait_confirmation(self, pending: PendingConfirmation, token: CancelToken) -> bool:
        while not pending._event.is_set():
            if token.cancelled:
                with self._lock:
                    if self._pending is pending:
                        self._pending = None
                self._notify_confirmation(None)
                return False
            if pending.expired:
                with self._lock:
                    if self._pending is pending:
                        self._pending = None
                self._notify_confirmation(None)
                return False
            pending._event.wait(0.1)
        return bool(pending.approved) and not token.cancelled

    def _notify_confirmation(self, pending: PendingConfirmation | None) -> None:
        for fn in list(self._confirm_listeners):
            try:
                fn(pending)
            except Exception:
                log.exception("Listener xác nhận lỗi")
