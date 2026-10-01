"""Ngủ canh gác: giữ máy thức (màn hình vẫn tắt) để NEXA còn nghe tiếng vỗ tay.

Máy dùng Modern Standby (S0 Low Power Idle): khi máy ngủ THẬT, Windows đóng băng mọi ứng dụng desktop nên
không phần mềm nào nghe được mic, và vỗ tay không thể đánh thức phần cứng. Vì vậy thay cho ngủ thật, NEXA:
- giữ một power request "SystemRequired" (thấy trong `powercfg /requests`): Windows vẫn tắt màn hình theo hẹn
  giờ nhưng không tự ngủ;
- khi anh bảo "cho máy ngủ": tắt màn hình thay vì SetSuspendState;
- khi vỗ tay: bật màn hình lại.
Tùy chọn keep_display giữ thêm DisplayRequired, đổi nhấn ngắn nút nguồn/ngủ và gập nắp thành không làm gì.
Không chặn được Start → Sleep/Shut down, tắt cưỡng bức hoặc bảo vệ pin/nhiệt của Windows/phần cứng.
Một luồng nhịp tim phát hiện các lần ngủ thật để báo lại.

Màn hình khóa là desktop bảo mật của Winlogon: ứng dụng thường không gõ phím vào đó được (và NEXA không lưu mật
khẩu). NEXA chỉ phát hiện máy đang khóa, nhắc anh mở khóa (PIN/Windows Hello) rồi chào khi anh đã vào.
"""
from __future__ import annotations

import ctypes
import json
import re
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from nexa.utils.logging import get_logger

log = get_logger("sleep_guard")

POWER_REQUEST_CONTEXT_VERSION = 0
POWER_REQUEST_CONTEXT_SIMPLE_STRING = 0x1
POWER_REQUEST_SYSTEM_REQUIRED = 1
POWER_REQUEST_DISPLAY_REQUIRED = 0
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
MOUSEEVENTF_MOVE = 0x0001
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002

# Thông báo nguồn qua callback (powrprof, Windows 8+): không cần cửa sổ ẩn.
DEVICE_NOTIFY_CALLBACK = 2
PBT_APMSUSPEND = 0x4
PBT_APMRESUMESUSPEND = 0x7
PBT_APMRESUMEAUTOMATIC = 0x12
PBT_POWERSETTINGCHANGE = 0x8013
DISPLAY_OFF, DISPLAY_ON, DISPLAY_DIMMED = 0, 1, 2

WTS_CURRENT_SESSION = 0xFFFFFFFF
WTS_SESSION_INFO_EX = 25
WTS_SESSIONSTATE_LOCK = 0
WTS_SESSIONSTATE_UNLOCK = 1
DESKTOP_SWITCHDESKTOP = 0x0100
UOI_NAME = 2


class _REASON_CONTEXT(ctypes.Structure):
    # Union trong Windows lớn hơn con trỏ chuỗi (bản "Detailed"); đệm cho đủ kích thước.
    _fields_ = [("Version", wintypes.ULONG), ("Flags", wintypes.DWORD),
                ("SimpleReasonString", wintypes.LPWSTR), ("_pad", ctypes.c_byte * 16)]


def display_off() -> bool:
    """Tắt màn hình (không ngủ). PostMessage để không bị treo vì một cửa sổ không phản hồi."""
    try:
        return bool(ctypes.windll.user32.PostMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2))
    except Exception:
        log.exception("Không tắt được màn hình")
        return False


def _nudge_display() -> None:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_DISPLAY_REQUIRED)
    user32 = ctypes.windll.user32
    user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)


def _press_shift() -> None:
    # Phím Shift không gõ ký tự nào (kể cả ở màn hình khóa) nhưng vẫn là "thao tác" để Windows bật màn hình.
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_SHIFT, 0, 0, 0)
    user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)


def display_on(monitor: "PowerEventMonitor | None" = None, timeout_s: float = 1.5) -> bool:
    """Bật màn hình: báo 'cần màn hình' + nhích chuột 1 px rồi trả lại (Windows coi là có thao tác).
    Có monitor thì kiểm tra màn hình đã sáng thật chưa; chưa thì thử thêm Shift và SC_MONITORPOWER bật."""
    attempts = (_nudge_display, _press_shift,
                lambda: ctypes.windll.user32.PostMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, -1))
    for i, attempt in enumerate(attempts):
        try:
            attempt()
        except Exception:
            log.exception("Không bật được màn hình (cách %d)", i + 1)
        if monitor is None or not monitor.active:
            return True
        if monitor.wait_display_on(timeout_s):
            return True
        log.warning("Màn hình chưa sáng sau cách %d, thử cách khác", i + 1)
    return False


def session_locked() -> bool | None:
    """True nếu màn hình khóa đang hiện, False nếu đã vào Windows, None nếu không xác định được."""
    try:
        wts = ctypes.windll.wtsapi32
        buf = ctypes.c_void_p()
        size = wintypes.DWORD()
        if wts.WTSQuerySessionInformationW(None, WTS_CURRENT_SESSION, WTS_SESSION_INFO_EX,
                                           ctypes.byref(buf), ctypes.byref(size)):
            try:
                # WTSINFOEXW: Level (DWORD) + union căn 8 byte (LEVEL1 có LARGE_INTEGER) →
                # SessionId @8, SessionState @12, SessionFlags @16 (đo trên máy: 01 00 00 00 ở offset 16 khi mở).
                flags = ctypes.c_long.from_address(buf.value + 16).value
            finally:
                wts.WTSFreeMemory(buf)
            if flags == WTS_SESSIONSTATE_LOCK:
                return True
            if flags == WTS_SESSIONSTATE_UNLOCK:
                return False
    except Exception:
        pass
    # Dự phòng: khi khóa, desktop nhập liệu là "Winlogon" và tiến trình thường không mở được nó.
    try:
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        h = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if not h:
            return True
        try:
            name = ctypes.create_unicode_buffer(64)
            if user32.GetUserObjectInformationW(h, UOI_NAME, name, ctypes.sizeof(name), None):
                return name.value.lower() != "default"
        finally:
            user32.CloseDesktop(h)
    except Exception:
        pass
    return None


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> "_GUID":
        h = s.replace("-", "")
        return cls(int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16),
                   (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:])))


GUID_CONSOLE_DISPLAY_STATE = _GUID.parse("6fe69556-704a-47a0-8f24-c28d936fda47")

_NOTIFY_CALLBACK = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p)


class _SUBSCRIBE_PARAMS(ctypes.Structure):
    _fields_ = [("Callback", _NOTIFY_CALLBACK), ("Context", ctypes.c_void_p)]


class PowerEventMonitor:
    """Nhận trạng thái màn hình (tắt/sáng/mờ) và sự kiện ngủ/thức từ Windows qua callback.

    Callback chạy trên luồng hệ thống: chỉ ghi trạng thái rồi gọi hàm xử lý ngắn gọn."""

    def __init__(self, on_display: Callable[[int], None] | None = None,
                 on_suspend: Callable[[], None] | None = None,
                 on_resume: Callable[[], None] | None = None) -> None:
        self.on_display = on_display
        self.on_suspend = on_suspend
        self.on_resume = on_resume
        self.display_state: int | None = None
        self._display_on = threading.Event()
        self._h_display = ctypes.c_void_p()
        self._h_suspend = ctypes.c_void_p()
        # Giữ tham chiếu để callback không bị thu gom rác khi Windows còn gọi.
        self._cb_display = _NOTIFY_CALLBACK(self._display_cb)
        self._cb_suspend = _NOTIFY_CALLBACK(self._suspend_cb)
        self._p_display = _SUBSCRIBE_PARAMS(self._cb_display, None)
        self._p_suspend = _SUBSCRIBE_PARAMS(self._cb_suspend, None)

    @property
    def active(self) -> bool:
        return bool(self._h_display.value)

    @property
    def display_off(self) -> bool:
        return self.display_state == DISPLAY_OFF

    def start(self) -> bool:
        try:
            pp = ctypes.windll.powrprof
            pp.PowerSettingRegisterNotification.argtypes = [ctypes.POINTER(_GUID), wintypes.DWORD, ctypes.c_void_p,
                                                            ctypes.POINTER(ctypes.c_void_p)]
            pp.PowerRegisterSuspendResumeNotification.argtypes = [wintypes.DWORD, ctypes.c_void_p,
                                                                  ctypes.POINTER(ctypes.c_void_p)]
            if not self._h_display.value:
                rc = pp.PowerSettingRegisterNotification(ctypes.byref(GUID_CONSOLE_DISPLAY_STATE),
                                                         DEVICE_NOTIFY_CALLBACK, ctypes.byref(self._p_display),
                                                         ctypes.byref(self._h_display))
                if rc != 0:
                    log.warning("Không đăng ký được trạng thái màn hình (mã %d)", rc)
                    self._h_display = ctypes.c_void_p()
            if not self._h_suspend.value:
                rc = pp.PowerRegisterSuspendResumeNotification(DEVICE_NOTIFY_CALLBACK, ctypes.byref(self._p_suspend),
                                                               ctypes.byref(self._h_suspend))
                if rc != 0:
                    log.warning("Không đăng ký được sự kiện ngủ/thức (mã %d)", rc)
                    self._h_suspend = ctypes.c_void_p()
        except Exception:
            log.exception("Không theo dõi được sự kiện nguồn")
        return self.active

    @property
    def suspend_events(self) -> bool:
        return bool(self._h_suspend.value)

    def stop(self) -> None:
        try:
            pp = ctypes.windll.powrprof
            if self._h_display.value:
                pp.PowerSettingUnregisterNotification(self._h_display)
            if self._h_suspend.value:
                pp.PowerUnregisterSuspendResumeNotification(self._h_suspend)
        except Exception:
            log.exception("Lỗi khi bỏ theo dõi sự kiện nguồn")
        self._h_display = ctypes.c_void_p()
        self._h_suspend = ctypes.c_void_p()
        self.display_state = None

    def wait_display_on(self, timeout_s: float) -> bool:
        return self._display_on.wait(timeout_s)

    def _set_display(self, state: int) -> None:
        if state == self.display_state:
            return
        self.display_state = state
        if state == DISPLAY_OFF:
            self._display_on.clear()
        else:
            self._display_on.set()
        log.info("Màn hình: %s", {0: "tắt", 1: "sáng", 2: "mờ"}.get(state, state))
        if self.on_display:
            try:
                self.on_display(state)
            except Exception:
                log.exception("on_display lỗi")

    def _display_cb(self, _ctx, typ, setting) -> int:
        try:
            if typ == PBT_POWERSETTINGCHANGE and setting:
                # POWERBROADCAST_SETTING: GUID (16 byte) + DataLength (DWORD) + Data (DWORD trạng thái màn hình).
                self._set_display(ctypes.c_ulong.from_address(setting + 20).value)
        except Exception:
            log.exception("Callback màn hình lỗi")
        return 0

    def _suspend_cb(self, _ctx, typ, _setting) -> int:
        try:
            if typ == PBT_APMSUSPEND:
                log.info("Windows báo: máy sắp ngủ thật")
                if self.on_suspend:
                    self.on_suspend()
            elif typ in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                # Windows gửi cả hai khi người dùng đánh thức; trình xử lý tự bỏ lần trùng.
                if self.on_resume:
                    self.on_resume()
        except Exception:
            log.exception("Callback ngủ/thức lỗi")
        return 0


class ButtonRemap:
    """Trong lúc ngủ canh gác: nút nguồn/nút ngủ = "Tắt màn hình" thay vì ngủ thật (tuỳ chọn: gập nắp = không làm gì).

    Giá trị gốc được lưu ra file trước khi đổi, trả lại khi tắt canh gác/thoát NEXA; nếu NEXA bị tắt ngang
    thì lần mở sau sẽ trả lại từ file. Đổi gói nguồn hiện tại bằng powercfg, không cần quyền quản trị."""

    TURN_OFF_DISPLAY = 4
    DO_NOTHING = 0

    def __init__(self, backup_path: Path, runner: Callable[[list[str]], str] | None = None) -> None:
        self.backup_path = Path(backup_path)
        self._run = runner or _powercfg

    def targets(self, lid: bool, keep_display: bool = False) -> dict[str, int]:
        action = self.DO_NOTHING if keep_display else self.TURN_OFF_DISPLAY
        t = {"PBUTTONACTION": action, "SBUTTONACTION": action}
        if lid:
            t["LIDACTION"] = self.DO_NOTHING
        return t

    def read(self, alias: str) -> tuple[int, int] | None:
        out = self._run(["/qh", "SCHEME_CURRENT", "SUB_BUTTONS", alias])
        vals = re.findall(r"Current (AC|DC) Power Setting Index:\s*0x([0-9a-fA-F]+)", out)
        d = {k: int(v, 16) for k, v in vals}
        return (d["AC"], d["DC"]) if "AC" in d and "DC" in d else None

    def _write(self, alias: str, ac: int, dc: int) -> None:
        self._run(["/setacvalueindex", "SCHEME_CURRENT", "SUB_BUTTONS", alias, str(ac)])
        self._run(["/setdcvalueindex", "SCHEME_CURRENT", "SUB_BUTTONS", alias, str(dc)])

    def apply(self, lid: bool = False, keep_display: bool = False) -> bool:
        if not self.restore():
            return False  # không ghi đè bản sao lưu khi khôi phục lần trước thất bại
        backup: dict[str, list[int]] = {}
        try:
            for alias, value in self.targets(lid, keep_display).items():
                cur = self.read(alias)
                if cur is None:
                    raise RuntimeError(f"Không đọc được hành động {alias}")
                if cur != (value, value):
                    backup[alias] = list(cur)
            if not backup:
                return True
            self.backup_path.parent.mkdir(parents=True, exist_ok=True)
            self.backup_path.write_text(json.dumps(backup), encoding="utf-8")
            for alias in backup:
                v = self.targets(lid, keep_display)[alias]
                self._write(alias, v, v)
            self._run(["/setactive", "SCHEME_CURRENT"])
            for alias, value in self.targets(lid, keep_display).items():
                if self.read(alias) != (value, value):
                    raise RuntimeError(f"Windows chưa áp dụng hành động {alias}")
            log.info("Đã áp dụng hành động nút nguồn/nút ngủ/gập nắp: %s", self.targets(lid, keep_display))
            return True
        except Exception:
            log.exception("Không đổi được hành động nút nguồn")
            self.restore()
            return False

    def restore(self) -> bool:
        if not self.backup_path.exists():
            return True
        try:
            backup = json.loads(self.backup_path.read_text(encoding="utf-8"))
            for alias, (ac, dc) in backup.items():
                self._write(alias, int(ac), int(dc))
            self._run(["/setactive", "SCHEME_CURRENT"])
            for alias, (ac, dc) in backup.items():
                if self.read(alias) != (int(ac), int(dc)):
                    raise RuntimeError(f"Chưa khôi phục được {alias}")
            self.backup_path.unlink()
            log.info("Đã trả lại hành động nút nguồn gốc: %s", backup)
            return True
        except Exception:
            log.exception("Không trả lại được hành động nút nguồn")
            return False


def _powercfg(args: list[str]) -> str:
    import subprocess
    r = subprocess.run(["powercfg", *args], capture_output=True, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"powercfg {' '.join(args)}: mã {r.returncode}")
    # Chỉ cần dòng "Current AC/DC Power Setting Index" (luôn là tiếng Anh), tên hiển thị có thể lỗi mã hoá.
    return r.stdout.decode("mbcs", "replace")


class SleepGuard:
    """Giữ power request SystemRequired và theo dõi các lần máy ngủ thật."""

    HEARTBEAT_S = 2.0
    SUSPEND_GAP_S = 20.0

    def __init__(self, on_resumed: Callable[[float], None] | None = None,
                 on_display: Callable[[int], None] | None = None,
                 buttons: ButtonRemap | None = None) -> None:
        self.on_resumed = on_resumed
        self.on_display = on_display
        self.buttons = buttons
        self.monitor = PowerEventMonitor(on_display=self._on_display, on_suspend=self._on_suspend,
                                         on_resume=self._on_resume)
        self._suspended_at: float | None = None
        self._handle = None
        self._requests: list[int] = []
        self.keep_display = False
        self.error = ""
        self._stes_active = False
        self._stes_thread: threading.Thread | None = None
        self._stes_stop = threading.Event()
        self._reason = ctypes.create_unicode_buffer("NEXA đang canh tiếng vỗ tay để đánh thức")
        self._lock = threading.RLock()
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self._handle is not None or self._stes_active

    @property
    def display_off(self) -> bool:
        """True khi Windows báo màn hình đang tắt (theo hẹn giờ, nút nguồn hoặc lệnh của NEXA)."""
        return self.monitor.active and self.monitor.display_off

    def enable(self, remap_buttons: bool = False, lid: bool = False, keep_display: bool = False) -> bool:
        with self._lock:
            self.error = ""
            if self.enabled and self.keep_display != keep_display:
                self.disable()
            self.keep_display = keep_display
            if not self.enabled:
                if not self._power_request():
                    self._stes_fallback()
                self.monitor.start()
                self._start_heartbeat()
                if not self.enabled:
                    self.error = "Windows không chấp nhận yêu cầu giữ máy thức."
                log.info("Giữ máy thức: %s; giữ màn hình: %s", self.enabled, keep_display)
            if self.buttons is not None:
                if remap_buttons:
                    if not self.buttons.apply(lid=lid, keep_display=keep_display):
                        self.error = "Không áp dụng được hành động nút nguồn/gập nắp; máy vẫn có thể ngủ."
                else:
                    self.buttons.restore()
            return self.enabled and not self.error

    def disable(self) -> None:
        with self._lock:
            if self._handle is not None:
                k32 = ctypes.windll.kernel32
                for request in self._requests:
                    k32.PowerClearRequest(self._handle, request)
                k32.CloseHandle(self._handle)
                self._handle = None
                self._requests = []
            self._stes_stop.set()
            if self._stes_thread is not None:
                self._stes_thread.join(timeout=1)
            self._stes_thread = None
            self._stes_active = False
            self._hb_stop.set()
            self._hb_thread = None
            self.monitor.stop()
            if self.buttons is not None:
                self.buttons.restore()
            log.info("Ngủ canh gác: TẮT")

    # ----- sự kiện từ Windows -----
    def _on_display(self, state: int) -> None:
        if self.on_display:
            self.on_display(state)

    def _on_suspend(self) -> None:
        self._suspended_at = time.time()

    def _on_resume(self) -> None:
        start, self._suspended_at = self._suspended_at, None
        if start is None:
            return                      # lần báo thức thứ hai (RESUMESUSPEND sau RESUMEAUTOMATIC)
        self._report_resume(time.time() - start)

    def _report_resume(self, gap: float) -> None:
        log.info("Máy vừa ngủ thật khoảng %.0f giây", gap)
        if self.on_resumed:
            try:
                self.on_resumed(gap)
            except Exception:
                log.exception("on_resumed lỗi")

    # ----- giữ máy thức -----
    def _power_request(self) -> bool:
        try:
            k32 = ctypes.windll.kernel32
            k32.PowerCreateRequest.restype = wintypes.HANDLE
            k32.PowerCreateRequest.argtypes = [ctypes.POINTER(_REASON_CONTEXT)]
            k32.PowerSetRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
            k32.PowerClearRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            k32.CloseHandle.restype = wintypes.BOOL
            ctx = _REASON_CONTEXT(POWER_REQUEST_CONTEXT_VERSION, POWER_REQUEST_CONTEXT_SIMPLE_STRING,
                                  ctypes.cast(self._reason, wintypes.LPWSTR))
            h = k32.PowerCreateRequest(ctypes.byref(ctx))
            if not h or h == INVALID_HANDLE_VALUE:
                return False
            requests = [POWER_REQUEST_SYSTEM_REQUIRED]
            if self.keep_display:
                requests.append(POWER_REQUEST_DISPLAY_REQUIRED)
            applied = []
            for request in requests:
                if not k32.PowerSetRequest(h, request):
                    for previous in applied:
                        k32.PowerClearRequest(h, previous)
                    k32.CloseHandle(h)
                    return False
                applied.append(request)
            self._requests = applied
            self._handle = h
            return True
        except Exception:
            log.exception("PowerCreateRequest lỗi, dùng SetThreadExecutionState")
            return False

    def _stes_fallback(self) -> None:
        # SetThreadExecutionState gắn với luồng gọi: giữ một luồng riêng sống suốt thời gian bật.
        stop = self._stes_stop = threading.Event()
        ready = threading.Event()
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | (ES_DISPLAY_REQUIRED if self.keep_display else 0)

        def hold() -> None:
            try:
                k32 = ctypes.windll.kernel32
                self._stes_active = bool(k32.SetThreadExecutionState(flags))
                ready.set()
                if self._stes_active:
                    stop.wait()
                    k32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                log.exception("SetThreadExecutionState thất bại")
            finally:
                self._stes_active = False
                ready.set()

        self._stes_thread = threading.Thread(target=hold, name="nexa-sleep-guard", daemon=True)
        self._stes_thread.start()
        ready.wait(timeout=1)

    # ----- phát hiện ngủ thật -----
    def _start_heartbeat(self) -> None:
        stop = self._hb_stop = threading.Event()

        def beat() -> None:
            last = time.time()
            while not stop.wait(self.HEARTBEAT_S):
                now = time.time()
                gap = now - last
                last = now
                # Có sự kiện ngủ/thức của Windows thì dùng nó; đồng hồ nhảy cóc chỉ là dự phòng.
                if gap > self.SUSPEND_GAP_S and not self.monitor.suspend_events:
                    self._report_resume(gap)

        self._hb_thread = threading.Thread(target=beat, name="nexa-heartbeat", daemon=True)
        self._hb_thread.start()


def away_greeting(hour: int, name: str = "anh Sơn") -> str:
    part = "sáng" if 4 <= hour < 11 else "trưa" if 11 <= hour < 13 else "chiều" if 13 <= hour < 18 else "tối"
    return f"Chào buổi {part} {name}, em là Nexa. Em sẵn sàng."
