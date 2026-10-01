"""Điều khiển bàn phím, chuột và cuộn qua SendInput.

- Gõ tiếng Việt có dấu bằng KEYEVENTF_UNICODE (không phụ thuộc bộ gõ, không ghi đè clipboard).
- Trước mỗi đoạn gõ đều kiểm tra lại cửa sổ đích vẫn là foreground; nếu đổi thì dừng.
- Fail-safe của PyAutoGUI được giữ nguyên: mọi thao tác gọi pyautogui.failSafeCheck() trước
  (đưa chuột vào góc màn hình chính để dừng khẩn cấp).
- release_all() nhả mọi phím/chuột đang được NEXA giữ (dùng khi dừng khẩn cấp).
"""
from __future__ import annotations

import ctypes
import threading
import time
import unicodedata
from ctypes import wintypes
from typing import Callable

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger

log = get_logger("input")

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
WHEEL_DELTA = 120

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "capslock": 0x14, "menu": 0x5D,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
}
for _i in range(1, 13):
    VK[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)
EXTENDED = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5B, 0x5D, 0x2C}
MODIFIERS = {"ctrl", "control", "shift", "alt", "win", "windows"}

KEY_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "cmd": "win", "windows": "win", "return": "enter",
    "escape": "esc", "del": "delete", "pgup": "pageup", "pgdn": "pagedown", "page up": "pageup",
    "page down": "pagedown", "mũi tên lên": "up", "mũi tên xuống": "down",
}


def normalize_key(name: str) -> str:
    k = name.strip().lower().replace("_", "")
    return KEY_ALIASES.get(k, k)


class InputController:
    def __init__(self, get_foreground: Callable[[], int] | None = None) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self._user32.SendInput.restype = wintypes.UINT
        self._get_foreground = get_foreground or (lambda: int(self._user32.GetForegroundWindow() or 0))
        self._held_keys: set[int] = set()
        self._held_buttons: set[str] = set()
        self._lock = threading.RLock()
        self._pyautogui = None
        try:
            import pyautogui
            pyautogui.FAILSAFE = True  # không bao giờ tắt fail-safe
            self._pyautogui = pyautogui
        except Exception:
            log.warning("Không nạp được pyautogui; fail-safe góc màn hình không khả dụng")

    # ----- tiện ích -----
    def _failsafe(self) -> None:
        if self._pyautogui is not None:
            self._pyautogui.failSafeCheck()

    def _send(self, inputs: list[INPUT]) -> int:
        arr = (INPUT * len(inputs))(*inputs)
        sent = self._user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            log.warning("SendInput chỉ gửi %d/%d sự kiện (UIPI có thể chặn ứng dụng quyền cao)", sent, len(inputs))
        return sent

    @staticmethod
    def _key(vk: int, up: bool) -> INPUT:
        flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
        return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)))

    @staticmethod
    def _unicode(code_unit: int, up: bool) -> INPUT:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
        return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=flags, time=0, dwExtraInfo=0)))

    @staticmethod
    def _mouse(flags: int, data: int = 0) -> INPUT:
        return INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(dx=0, dy=0, mouseData=ctypes.c_uint32(data).value,
                                                                   dwFlags=flags, time=0, dwExtraInfo=0)))

    # ----- bàn phím -----
    def type_text(self, text: str, target_hwnd: int | None, chunk: int = 40,
                  cancelled: Callable[[], bool] = lambda: False) -> ToolResult:
        text = unicodedata.normalize("NFC", text or "")
        if not text:
            return ToolResult.failure("Không có nội dung để gõ.", "empty")
        typed = 0
        with self._lock:
            for start in range(0, len(text), chunk):
                if cancelled():
                    return ToolResult.failure(f"Đã dừng sau {typed} ký tự.", "cancelled", typed=typed)
                if target_hwnd and self._get_foreground() != target_hwnd:
                    return ToolResult.failure(
                        f"Cửa sổ đích đã thay đổi nên em dừng gõ (đã gõ {typed}/{len(text)} ký tự).",
                        "target_changed", typed=typed)
                self._failsafe()
                events: list[INPUT] = []
                for ch in text[start:start + chunk]:
                    if ch == "\n":
                        events += [self._key(0x0D, False), self._key(0x0D, True)]
                    elif ch == "\r":
                        continue
                    elif ch == "\t":
                        events += [self._key(0x09, False), self._key(0x09, True)]
                    else:
                        data = ch.encode("utf-16-le")
                        for i in range(0, len(data), 2):
                            cu = int.from_bytes(data[i:i + 2], "little")
                            events += [self._unicode(cu, False), self._unicode(cu, True)]
                if events and self._send(events) == 0:
                    return ToolResult.failure("Windows chặn thao tác gõ vào cửa sổ này (có thể chạy quyền quản trị).",
                                              "uipi_blocked", typed=typed)
                typed += len(text[start:start + chunk])
                time.sleep(0.01)
        return ToolResult.success(f"Đã gõ {typed} ký tự.", verified=False, typed=typed)

    def hotkey(self, keys: list[str], target_hwnd: int | None = None) -> ToolResult:
        names = [normalize_key(k) for k in keys if k.strip()]
        vks = []
        for n in names:
            if n not in VK:
                return ToolResult.failure(f"Không hỗ trợ phím '{n}'.", "unknown_key")
            vks.append(VK[n])
        if not vks:
            return ToolResult.failure("Chưa có phím nào.", "empty")
        if target_hwnd and self._get_foreground() != target_hwnd:
            return ToolResult.failure("Cửa sổ đích không còn được chọn nên em không bấm phím.", "target_changed")
        with self._lock:
            self._failsafe()
            try:
                for vk in vks:
                    self._send([self._key(vk, False)])
                    self._held_keys.add(vk)
                    time.sleep(0.02)
            finally:
                for vk in reversed(vks):
                    self._send([self._key(vk, True)])
                    self._held_keys.discard(vk)
                    time.sleep(0.01)
        return ToolResult.success("Đã bấm " + "+".join(names) + ".", verified=False)

    def press(self, key: str, times: int = 1, target_hwnd: int | None = None) -> ToolResult:
        n = normalize_key(key)
        if n not in VK:
            return ToolResult.failure(f"Không hỗ trợ phím '{n}'.", "unknown_key")
        for _ in range(max(1, min(times, 50))):
            r = self.hotkey([n], target_hwnd)
            if not r.ok:
                return r
        return ToolResult.success(f"Đã bấm {n} {times} lần.", verified=False)

    def paste_text(self, text: str, target_hwnd: int | None) -> ToolResult:
        """Dán qua clipboard; chỉ khôi phục clipboard cũ nếu người dùng chưa sao chép gì mới."""
        import win32clipboard as cb
        text = unicodedata.normalize("NFC", text or "")
        previous: str | None = None
        try:
            cb.OpenClipboard()
            try:
                if cb.IsClipboardFormatAvailable(cb.CF_UNICODETEXT):
                    previous = cb.GetClipboardData(cb.CF_UNICODETEXT)
                cb.EmptyClipboard()
                cb.SetClipboardData(cb.CF_UNICODETEXT, text)
            finally:
                cb.CloseClipboard()
        except Exception as exc:
            return ToolResult.failure(f"Không truy cập được clipboard: {exc}", "clipboard")
        seq_after_set = self._user32.GetClipboardSequenceNumber()
        result = self.hotkey(["ctrl", "v"], target_hwnd)
        time.sleep(0.35)
        if previous is not None and self._user32.GetClipboardSequenceNumber() == seq_after_set:
            try:
                cb.OpenClipboard()
                try:
                    cb.EmptyClipboard()
                    cb.SetClipboardData(cb.CF_UNICODETEXT, previous)
                finally:
                    cb.CloseClipboard()
            except Exception:
                log.warning("Không khôi phục được clipboard cũ")
        if not result.ok:
            return result
        return ToolResult.success(f"Đã dán {len(text)} ký tự.", verified=False)

    # ----- chuột -----
    def cursor(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)

    def move(self, x: int, y: int) -> ToolResult:
        with self._lock:
            self._failsafe()
            if not self._user32.SetCursorPos(int(x), int(y)):
                return ToolResult.failure("Không di chuyển được chuột.", "move_failed")
        cx, cy = self.cursor()
        return ToolResult.success(f"Chuột ở ({cx}, {cy}).", verified=abs(cx - x) <= 2 and abs(cy - y) <= 2, x=cx, y=cy)

    def click(self, button: str = "left", x: int | None = None, y: int | None = None, double: bool = False) -> ToolResult:
        flags = {"left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
                 "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
                 "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)}.get(button)
        if flags is None:
            return ToolResult.failure("Nút chuột không hợp lệ.", "bad_button")
        with self._lock:
            if x is not None and y is not None:
                r = self.move(x, y)
                if not r.ok:
                    return r
            self._failsafe()
            for _ in range(2 if double else 1):
                self._send([self._mouse(flags[0])])
                self._held_buttons.add(button)
                time.sleep(0.03)
                self._send([self._mouse(flags[1])])
                self._held_buttons.discard(button)
                time.sleep(0.06)
        cx, cy = self.cursor()
        return ToolResult.success(("Đã nhấp đúp" if double else "Đã nhấp") + f" tại ({cx}, {cy}).", verified=False,
                                  x=cx, y=cy)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.4,
             cancelled: Callable[[], bool] = lambda: False) -> ToolResult:
        with self._lock:
            r = self.move(x1, y1)
            if not r.ok:
                return r
            self._send([self._mouse(MOUSEEVENTF_LEFTDOWN)])
            self._held_buttons.add("left")
            try:
                steps = max(5, int(duration / 0.02))
                for i in range(1, steps + 1):
                    if cancelled():
                        return ToolResult.failure("Đã dừng kéo thả.", "cancelled")
                    self._failsafe()
                    self._user32.SetCursorPos(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
                    time.sleep(duration / steps)
            finally:
                self._send([self._mouse(MOUSEEVENTF_LEFTUP)])
                self._held_buttons.discard("left")
        return ToolResult.success(f"Đã kéo thả tới ({x2}, {y2}).", verified=False)

    def scroll(self, notches: int, horizontal: bool = False) -> ToolResult:
        """notches > 0: cuộn lên (hoặc sang phải nếu horizontal)."""
        notches = max(-30, min(30, int(notches)))
        if notches == 0:
            return ToolResult.success("Không cuộn.", verified=True)
        with self._lock:
            self._failsafe()
            flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
            self._send([self._mouse(flag, notches * WHEEL_DELTA)])
        return ToolResult.success(f"Đã cuộn {'lên' if notches > 0 else 'xuống'} {abs(notches)} nấc.", verified=False,
                                  notches=notches)

    # ----- chuột bằng tay (gọi mỗi khung hình: không chờ, không trả ToolResult) -----
    def air_move(self, x: int, y: int) -> None:
        """Fail-safe vẫn kiểm tra: chuột bằng tay không bao giờ tự vào góc, nên nếu con trỏ đang ở góc thì đó là anh
        vừa đưa chuột thật vào — pyautogui.FailSafeException được ném ra để NEXA dừng khẩn cấp."""
        with self._lock:
            self._failsafe()
            self._user32.SetCursorPos(int(x), int(y))

    def air_button(self, button: str, down: bool) -> None:
        flags = {"left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
                 "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)}[button]
        with self._lock:
            if down:
                self._failsafe()
                self._send([self._mouse(flags[0])])
                self._held_buttons.add(button)
            else:
                self._send([self._mouse(flags[1])])      # nhả luôn được gửi, kể cả khi đang ở góc fail-safe
                self._held_buttons.discard(button)

    def air_scroll(self, notches: int) -> None:
        notches = max(-10, min(10, int(notches)))
        if notches:
            with self._lock:
                self._failsafe()
                self._send([self._mouse(MOUSEEVENTF_WHEEL, notches * WHEEL_DELTA)])

    # ----- dừng khẩn cấp -----
    def release_all(self) -> None:
        with self._lock:
            # Chỉ nhả phím NEXA thực sự đang giữ: gửi Alt/Win "up" lẻ có thể kích hoạt menu.
            events = [self._key(vk, True) for vk in list(self._held_keys)]
            if events:
                try:
                    self._send(events)
                except Exception:
                    log.exception("Lỗi nhả phím")
            for button, up in (("left", MOUSEEVENTF_LEFTUP), ("right", MOUSEEVENTF_RIGHTUP), ("middle", MOUSEEVENTF_MIDDLEUP)):
                if button in self._held_buttons:
                    self._send([self._mouse(up)])
            self._held_keys.clear()
            self._held_buttons.clear()
        log.info("Đã nhả mọi phím/chuột do NEXA giữ")
