"""Phím tắt toàn cục bằng RegisterHotKey (không cần quyền admin, không cài hook bàn phím)."""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

from nexa.utils.logging import get_logger

log = get_logger("hotkeys")

MOD = {"alt": 0x0001, "ctrl": 0x0002, "control": 0x0002, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
VKS = {"escape": 0x1B, "esc": 0x1B, "space": 0x20, "enter": 0x0D, "pause": 0x13, "f12": 0x7B, "f11": 0x7A}


def parse_hotkey(spec: str) -> tuple[int, int]:
    mods, vk = 0, 0
    for part in spec.lower().replace(" ", "").split("+"):
        if part in MOD:
            mods |= MOD[part]
        elif part in VKS:
            vk = VKS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit():
            vk = 0x6F + int(part[1:])
        else:
            raise ValueError(f"Phím tắt không hợp lệ: {spec}")
    if not vk:
        raise ValueError(f"Phím tắt thiếu phím chính: {spec}")
    return mods | MOD_NOREPEAT, vk


class GlobalHotkeys:
    def __init__(self, bindings: dict[str, tuple[str, Callable[[], None]]]) -> None:
        """bindings: tên -> (chuỗi phím, callback). Callback chạy trên luồng hotkey — phải nhẹ."""
        self.bindings = bindings
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self.registered: dict[str, str] = {}
        self.failed: dict[str, str] = {}
        self._ready = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="nexa-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2)

    def _loop(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        self._thread_id = kernel32.GetCurrentThreadId()
        ids: dict[int, Callable[[], None]] = {}
        for i, (name, (spec, cb)) in enumerate(self.bindings.items(), start=1):
            try:
                mods, vk = parse_hotkey(spec)
            except ValueError as exc:
                self.failed[name] = str(exc)
                continue
            if user32.RegisterHotKey(None, i, mods, vk):
                ids[i] = cb
                self.registered[name] = spec
            else:
                self.failed[name] = f"{spec} đang bị ứng dụng khác chiếm (mã {ctypes.get_last_error()})"
                log.warning("Không đăng ký được phím tắt %s: %s", name, self.failed[name])
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                try:
                    ids[msg.wParam]()
                except Exception:
                    log.exception("Callback phím tắt lỗi")
        for i in ids:
            user32.UnregisterHotKey(None, i)

    def stop(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
