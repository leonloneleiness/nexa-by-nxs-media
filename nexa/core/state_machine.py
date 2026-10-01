"""Máy trạng thái tổng thể của NEXA."""
from __future__ import annotations

import threading
import time
from typing import Callable

from nexa.core.events import AppState
from nexa.utils.logging import get_logger

log = get_logger("state")

S = AppState
ALLOWED: dict[AppState, set[AppState]] = {
    S.INITIALIZING: {S.STANDBY, S.ERROR},
    S.STANDBY: {S.WAKING, S.LISTENING, S.THINKING, S.EXECUTING, S.CONFIRMING, S.SPEAKING, S.ERROR},
    S.WAKING: {S.SPEAKING, S.LISTENING, S.STANDBY, S.ERROR},
    S.LISTENING: {S.THINKING, S.EXECUTING, S.SPEAKING, S.STANDBY, S.CONFIRMING, S.ERROR},
    S.THINKING: {S.EXECUTING, S.SPEAKING, S.LISTENING, S.CONFIRMING, S.STANDBY, S.ERROR},
    S.EXECUTING: {S.THINKING, S.SPEAKING, S.LISTENING, S.CONFIRMING, S.STANDBY, S.ERROR},
    S.SPEAKING: {S.LISTENING, S.STANDBY, S.THINKING, S.EXECUTING, S.CONFIRMING, S.ERROR},
    S.CONFIRMING: {S.EXECUTING, S.SPEAKING, S.LISTENING, S.STANDBY, S.THINKING, S.ERROR},
    S.ERROR: {S.STANDBY, S.LISTENING, S.SPEAKING, S.ERROR},
}

Listener = Callable[[AppState, AppState, str], None]


class StateMachine:
    def __init__(self) -> None:
        self._state = AppState.INITIALIZING
        self._lock = threading.RLock()
        self._listeners: list[Listener] = []
        self.changed_at = time.monotonic()
        self.detail = ""

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    @property
    def awake(self) -> bool:
        return self.state not in (AppState.STANDBY, AppState.INITIALIZING)

    def add_listener(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def can(self, new: AppState) -> bool:
        with self._lock:
            return new == self._state or new in ALLOWED.get(self._state, set())

    def set(self, new: AppState, detail: str = "") -> bool:
        with self._lock:
            old = self._state
            if new == old:
                self.detail = detail or self.detail
                changed = False
            elif new not in ALLOWED.get(old, set()):
                log.warning("Bỏ qua chuyển trạng thái không hợp lệ %s -> %s", old.value, new.value)
                return False
            else:
                self._state = new
                self.changed_at = time.monotonic()
                self.detail = detail
                changed = True
        if changed:
            log.info("Trạng thái %s -> %s %s", old.value, new.value, detail)
        for fn in list(self._listeners):
            try:
                fn(old, new, detail)
            except Exception:  # pragma: no cover - listener lỗi không làm hỏng máy trạng thái
                log.exception("Listener trạng thái lỗi")
        return True
