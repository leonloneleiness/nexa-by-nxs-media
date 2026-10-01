"""Lớp bọc ctypes cho các API Win32 mà NEXA dùng.

Toàn bộ tọa độ là pixel vật lý trong hệ virtual desktop (có thể âm) vì tiến trình được đặt
Per-Monitor DPI Aware v2 ngay khi khởi động (xem set_dpi_awareness và main.py).
Các module khác nhận một đối tượng Win32Api qua tham số để kiểm thử có thể thay bằng bản giả.
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

Rect = tuple[int, int, int, int]  # left, top, right, bottom

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOWNOACTIVATE = 4
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_RESTORE = 9
WPF_RESTORETOMAXIMIZED = 0x0002
WM_SYSCOMMAND = 0x0112
WM_CLOSE = 0x0010
SC_MINIMIZE = 0xF020
SC_RESTORE = 0xF120
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
SWP_ASYNCWINDOWPOS = 0x4000
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
GA_ROOT = 2
GA_ROOTOWNER = 3
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_CAPTION = 0x00C00000
WS_MINIMIZEBOX = 0x00020000
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

SHELL_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
    "Windows.UI.Core.CoreWindow", "TaskListThumbnailWnd", "XamlExplorerHostIslandWindow",
    "MultitaskingViewFrame", "ForegroundStaging", "TopLevelWindowForOverflowXamlIsland",
}


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("statusFlags", ctypes.c_uint32)]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("outputTechnology", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                ("scaling", ctypes.c_uint32), ("refreshRate", DISPLAYCONFIG_RATIONAL),
                ("scanLineOrdering", ctypes.c_uint32), ("targetAvailable", wintypes.BOOL),
                ("statusFlags", ctypes.c_uint32)]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
                ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO), ("flags", ctypes.c_uint32)]


class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
    # Chỉ cần kích thước đúng (64 byte) cho bộ đệm; NEXA không đọc nội dung mode.
    _fields_ = [("infoType", ctypes.c_uint32), ("id", ctypes.c_uint32), ("adapterId", LUID),
                ("_union", ctypes.c_uint64 * 6)]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapterId", LUID),
                ("id", ctypes.c_uint32)]


class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [("header", DISPLAYCONFIG_DEVICE_INFO_HEADER), ("viewGdiDeviceName", wintypes.WCHAR * 32)]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
    _fields_ = [("header", DISPLAYCONFIG_DEVICE_INFO_HEADER), ("flags", ctypes.c_uint32),
                ("outputTechnology", ctypes.c_uint32), ("edidManufactureId", ctypes.c_uint16),
                ("edidProductCodeId", ctypes.c_uint16), ("connectorInstance", ctypes.c_uint32),
                ("monitorFriendlyDeviceName", wintypes.WCHAR * 64),
                ("monitorDevicePath", wintypes.WCHAR * 128)]


@dataclass(frozen=True)
class RawMonitor:
    hmonitor: int
    device_name: str
    rect: Rect
    work: Rect
    primary: bool
    dpi: int
    device_id: str
    friendly_name: str


@dataclass
class Placement:
    show_cmd: int
    flags: int
    normal_rect: Rect  # tọa độ workspace

    @property
    def maximized(self) -> bool:
        return self.show_cmd == SW_SHOWMAXIMIZED

    @property
    def minimized(self) -> bool:
        return self.show_cmd in (SW_SHOWMINIMIZED, SW_MINIMIZE, SW_SHOWMINNOACTIVE)


def _rect(r: wintypes.RECT) -> Rect:
    return (int(r.left), int(r.top), int(r.right), int(r.bottom))


def set_dpi_awareness() -> str:
    """Đặt Per-Monitor DPI Aware v2 (gọi trước khi import Qt/pyautogui)."""
    if not IS_WINDOWS:
        return "n/a"
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except (AttributeError, OSError):
        return "unaware"


class Win32Api:
    """Triển khai thật bằng ctypes."""

    def __init__(self) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("Win32Api chỉ chạy trên Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.dwmapi = ctypes.WinDLL("dwmapi")
        try:
            self.shcore = ctypes.WinDLL("shcore")
        except OSError:
            self.shcore = None
        u = self.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.IsWindow.argtypes = [wintypes.HWND]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsIconic.argtypes = [wintypes.HWND]
        u.IsZoomed.argtypes = [wintypes.HWND]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
        u.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        u.MonitorFromWindow.restype = wintypes.HMONITOR
        u.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
        u.MonitorFromRect.restype = wintypes.HMONITOR
        u.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
        u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetAncestor.restype = wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        u.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
        self.dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    # ----- màn hình -----
    def enum_monitors(self) -> list[RawMonitor]:
        handles: list[int] = []
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def _cb(hmon, _hdc, _rect, _lp):
            handles.append(int(hmon))
            return 1

        self.user32.EnumDisplayMonitors(None, None, proc_type(_cb), 0)
        names = self._display_config_names()
        result: list[RawMonitor] = []
        for h in handles:
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if not self.user32.GetMonitorInfoW(h, ctypes.byref(info)):
                continue
            device = info.szDevice
            friendly, path = names.get(device, ("", ""))
            if not path:
                path, desc = self._device_interface(device)
                friendly = friendly or desc
            result.append(RawMonitor(
                hmonitor=h, device_name=device, rect=_rect(info.rcMonitor), work=_rect(info.rcWork),
                primary=bool(info.dwFlags & 1), dpi=self._dpi_for_monitor(h),
                device_id=path, friendly_name=friendly or device))
        return result

    def _dpi_for_monitor(self, hmon: int) -> int:
        if self.shcore is None:
            return 96
        x, y = wintypes.UINT(), wintypes.UINT()
        try:
            if self.shcore.GetDpiForMonitor(wintypes.HMONITOR(hmon), 0, ctypes.byref(x), ctypes.byref(y)) == 0:
                return int(x.value)
        except OSError:
            pass
        return 96

    def _device_interface(self, device_name: str) -> tuple[str, str]:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if self.user32.EnumDisplayDevicesW(device_name, 0, ctypes.byref(dd), 1):
            return dd.DeviceID, dd.DeviceString
        return "", ""

    def _display_config_names(self) -> dict[str, tuple[str, str]]:
        """GDI device name -> (tên thân thiện EDID, đường dẫn thiết bị ổn định)."""
        out: dict[str, tuple[str, str]] = {}
        try:
            flags = 2  # QDC_ONLY_ACTIVE_PATHS
            n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
            if self.user32.GetDisplayConfigBufferSizes(flags, ctypes.byref(n_paths), ctypes.byref(n_modes)) != 0:
                return out
            paths = (DISPLAYCONFIG_PATH_INFO * n_paths.value)()
            modes = (DISPLAYCONFIG_MODE_INFO * n_modes.value)()
            if self.user32.QueryDisplayConfig(flags, ctypes.byref(n_paths), paths, ctypes.byref(n_modes),
                                              modes, None) != 0:
                return out
            for i in range(n_paths.value):
                p = paths[i]
                src = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
                src.header.type = 1
                src.header.size = ctypes.sizeof(src)
                src.header.adapterId = p.sourceInfo.adapterId
                src.header.id = p.sourceInfo.id
                if self.user32.DisplayConfigGetDeviceInfo(ctypes.byref(src.header)) != 0:
                    continue
                tgt = DISPLAYCONFIG_TARGET_DEVICE_NAME()
                tgt.header.type = 2
                tgt.header.size = ctypes.sizeof(tgt)
                tgt.header.adapterId = p.targetInfo.adapterId
                tgt.header.id = p.targetInfo.id
                if self.user32.DisplayConfigGetDeviceInfo(ctypes.byref(tgt.header)) != 0:
                    continue
                out[src.viewGdiDeviceName] = (tgt.monitorFriendlyDeviceName, tgt.monitorDevicePath)
        except (AttributeError, OSError):
            return {}
        return out

    def monitor_from_window(self, hwnd: int) -> int:
        return int(self.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL) or 0)

    # ----- cửa sổ -----
    def get_foreground(self) -> int:
        return int(self.user32.GetForegroundWindow() or 0)

    def is_window(self, hwnd: int) -> bool:
        return bool(self.user32.IsWindow(hwnd))

    def is_visible(self, hwnd: int) -> bool:
        return bool(self.user32.IsWindowVisible(hwnd))

    def is_iconic(self, hwnd: int) -> bool:
        return bool(self.user32.IsIconic(hwnd))

    def is_zoomed(self, hwnd: int) -> bool:
        return bool(self.user32.IsZoomed(hwnd))

    def is_cloaked(self, hwnd: int) -> bool:
        val = wintypes.DWORD()
        try:
            if self.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                return val.value != 0
        except OSError:
            pass
        return False

    def get_title(self, hwnd: int) -> str:
        n = self.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(1, n + 1))
        self.user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def get_class(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def get_pid(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def get_ex_style(self, hwnd: int) -> int:
        return int(self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF

    def get_style(self, hwnd: int) -> int:
        return int(self.user32.GetWindowLongW(hwnd, GWL_STYLE)) & 0xFFFFFFFF

    def get_root_owner(self, hwnd: int) -> int:
        return int(self.user32.GetAncestor(hwnd, GA_ROOTOWNER) or 0)

    def get_root(self, hwnd: int) -> int:
        return int(self.user32.GetAncestor(hwnd, GA_ROOT) or 0)

    def get_rect(self, hwnd: int) -> Rect:
        """Khung hiển thị thật (DWM extended frame, không tính bóng đổ)."""
        r = wintypes.RECT()
        try:
            if self.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) == 0:
                return _rect(r)
        except OSError:
            pass
        self.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return _rect(r)

    def get_window_rect(self, hwnd: int) -> Rect:
        r = wintypes.RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return _rect(r)

    def get_placement(self, hwnd: int) -> Placement:
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(WINDOWPLACEMENT)
        if not self.user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
            raise OSError(ctypes.get_last_error(), "GetWindowPlacement thất bại")
        return Placement(show_cmd=int(wp.showCmd), flags=int(wp.flags), normal_rect=_rect(wp.rcNormalPosition))

    def set_placement(self, hwnd: int, placement: Placement) -> bool:
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(WINDOWPLACEMENT)
        wp.flags = placement.flags
        wp.showCmd = placement.show_cmd
        wp.ptMinPosition = wintypes.POINT(-1, -1)
        wp.ptMaxPosition = wintypes.POINT(-1, -1)
        l, t, r, b = placement.normal_rect
        wp.rcNormalPosition = wintypes.RECT(l, t, r, b)
        return bool(self.user32.SetWindowPlacement(hwnd, ctypes.byref(wp)))

    def set_pos(self, hwnd: int, x: int, y: int, w: int = 0, h: int = 0, no_size: bool = False,
                async_pos: bool = False) -> bool:
        # async_pos: cửa sổ của chính NEXA (luồng Qt) — không chặn luồng gọi chờ luồng giao diện xử lý
        flags = (SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER | (SWP_NOSIZE if no_size else 0)
                 | (SWP_ASYNCWINDOWPOS if async_pos else 0))
        return bool(self.user32.SetWindowPos(hwnd, None, int(x), int(y), int(w), int(h), flags))

    def show_async(self, hwnd: int, cmd: int) -> bool:
        return bool(self.user32.ShowWindowAsync(hwnd, cmd))

    def post_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> bool:
        return bool(self.user32.PostMessageW(hwnd, msg, wparam, lparam))

    def set_foreground(self, hwnd: int) -> bool:
        return bool(self.user32.SetForegroundWindow(hwnd))

    def force_foreground(self, hwnd: int) -> bool:
        """SetForegroundWindow; nếu Windows từ chối (NEXA không phải tiến trình nhận thao tác cuối) thì gắn tạm hàng
        đợi nhập liệu với luồng của cửa sổ đang foreground rồi thử lại — không gửi phím giả."""
        if self.user32.SetForegroundWindow(hwnd) and self.user32.GetForegroundWindow() == hwnd:
            return True
        fg = self.user32.GetForegroundWindow()
        fg_tid = self.user32.GetWindowThreadProcessId(fg, None) if fg else 0
        me = ctypes.windll.kernel32.GetCurrentThreadId()
        attached = bool(fg_tid and fg_tid != me and self.user32.AttachThreadInput(me, fg_tid, True))
        try:
            self.user32.BringWindowToTop(hwnd)
            self.user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                self.user32.AttachThreadInput(me, fg_tid, False)
        return self.user32.GetForegroundWindow() == hwnd

    def enum_windows(self) -> list[int]:
        out: list[int] = []
        proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lp):
            out.append(int(hwnd))
            return True

        self.user32.EnumWindows(proc_type(_cb), 0)
        return out

    def process_identity(self, pid: int) -> tuple[str, float, str]:
        """(tên tiến trình, thời điểm tạo, đường dẫn exe) — dùng để phát hiện HWND/PID bị tái sử dụng."""
        try:
            import psutil
            p = psutil.Process(pid)
            try:
                exe = p.exe()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                exe = ""
            return p.name(), float(p.create_time()), exe
        except Exception:
            return "", 0.0, ""

    def own_pid(self) -> int:
        return os.getpid()

    def cursor_pos(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)
