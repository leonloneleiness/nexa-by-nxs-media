"""Lịch sử các cửa sổ do NEXA thu nhỏ thành công (chỉ trong phiên chạy hiện tại).

Ngăn xếp LIFO: thu nhỏ A rồi B -> khôi phục B trước, sau đó A.
Mục không còn hợp lệ (đã đóng, HWND bị tái sử dụng, người dùng tự khôi phục) bị loại bỏ.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from nexa.desktop.win32api import Placement, Rect


@dataclass(frozen=True)
class WindowIdentity:
    hwnd: int
    pid: int
    process_name: str
    create_time: float
    class_name: str


@dataclass
class MinimizedEntry:
    identity: WindowIdentity
    title: str
    placement: Placement      # trạng thái trước khi thu nhỏ
    was_maximized: bool
    rect: Rect
    monitor: dict[str, str]   # định danh màn hình lúc thu nhỏ
    session_id: str
    ts: float = field(default_factory=time.time)


Validator = Callable[[MinimizedEntry], "tuple[bool, str]"]


class WindowHistory:
    def __init__(self, session_id: str, max_items: int = 30) -> None:
        self.session_id = session_id
        self.max_items = max_items
        self._items: list[MinimizedEntry] = []
        self._lock = threading.Lock()

    def push(self, entry: MinimizedEntry) -> None:
        if entry.session_id != self.session_id:
            raise ValueError("Mục lịch sử không thuộc phiên hiện tại")
        with self._lock:
            # Một cửa sổ chỉ xuất hiện một lần, ở đỉnh ngăn xếp.
            self._items = [e for e in self._items if e.identity != entry.identity]
            self._items.append(entry)
            if len(self._items) > self.max_items:
                self._items = self._items[-self.max_items:]

    def pop_valid(self, validator: Validator) -> tuple[MinimizedEntry | None, list[tuple[MinimizedEntry, str]]]:
        skipped: list[tuple[MinimizedEntry, str]] = []
        with self._lock:
            while self._items:
                entry = self._items.pop()
                if entry.session_id != self.session_id:
                    skipped.append((entry, "khác phiên"))
                    continue
                ok, reason = validator(entry)
                if ok:
                    return entry, skipped
                skipped.append((entry, reason))
        return None, skipped

    def push_back(self, entry: MinimizedEntry) -> None:
        """Đưa lại mục vào đỉnh nếu khôi phục thất bại vì lý do tạm thời."""
        with self._lock:
            self._items.append(entry)

    def items(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"title": e.title, "process": e.identity.process_name, "hwnd": e.identity.hwnd}
                    for e in reversed(self._items)]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
