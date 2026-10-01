"""Win32 GIẢ LẬP cho kiểm thử — không đụng tới cửa sổ thật trên máy."""
from __future__ import annotations

from dataclasses import dataclass, field

from nexa.desktop import win32api as w
from nexa.desktop.win32api import Placement, RawMonitor


def mon(h, name, rect, work=None, dpi=96, primary=False, dev_id=None, friendly=None):
    return RawMonitor(hmonitor=h, device_name=name, rect=rect, work=work or rect, primary=primary, dpi=dpi,
                      device_id=dev_id or f"\\\\?\\DISPLAY#{name}#id", friendly_name=friendly or f"Monitor {h}")


@dataclass
class FakeWindow:
    pid: int
    title: str
    rect: tuple
    cls: str = "Notepad"
    visible: bool = True
    iconic: bool = False
    zoomed: bool = False
    style: int = w.WS_MINIMIZEBOX | w.WS_CAPTION
    ex_style: int = 0
    normal_rect: tuple | None = None
    process: str = "notepad.exe"
    created: float = 1000.0
    hides_to_tray: bool = False
    deny_move: bool = False


@dataclass
class FakeWin32:
    monitors: list = field(default_factory=list)
    windows: dict = field(default_factory=dict)
    foreground: int = 0
    own: int = 999
    set_pos_calls: list = field(default_factory=list)

    # --- màn hình ---
    def enum_monitors(self):
        return list(self.monitors)

    def _mon_for_rect(self, r):
        best, area = None, 0
        for m in self.monitors:
            a = max(0, min(r[2], m.rect[2]) - max(r[0], m.rect[0])) * max(0, min(r[3], m.rect[3]) - max(r[1], m.rect[1]))
            if a > area:
                best, area = m, a
        return best

    def monitor_from_window(self, hwnd):
        m = self._mon_for_rect(self.windows[hwnd].rect)
        return m.hmonitor if m else 0

    def _primary(self):
        return next(m for m in self.monitors if m.primary)

    # --- cửa sổ ---
    def get_foreground(self):
        return self.foreground

    def is_window(self, h):
        return h in self.windows

    def is_visible(self, h):
        return self.windows[h].visible

    def is_iconic(self, h):
        return self.windows[h].iconic

    def is_zoomed(self, h):
        return self.windows[h].zoomed

    def is_cloaked(self, h):
        return False

    def get_title(self, h):
        return self.windows[h].title if h in self.windows else ""

    def get_class(self, h):
        return self.windows[h].cls if h in self.windows else ""

    def get_pid(self, h):
        return self.windows[h].pid if h in self.windows else 0

    def get_ex_style(self, h):
        return self.windows[h].ex_style

    def get_style(self, h):
        return self.windows[h].style

    def get_root(self, h):
        return h

    def get_root_owner(self, h):
        return h

    def get_rect(self, h):
        return self.windows[h].rect

    def get_window_rect(self, h):
        return self.windows[h].rect

    def get_placement(self, h):
        win = self.windows[h]
        p = self._primary()
        nr = win.normal_rect or win.rect
        ws = (nr[0] - p.work[0], nr[1] - p.work[1], nr[2] - p.work[0], nr[3] - p.work[1])
        cmd = w.SW_SHOWMINIMIZED if win.iconic else (w.SW_SHOWMAXIMIZED if win.zoomed else w.SW_SHOWNORMAL)
        return Placement(cmd, w.WPF_RESTORETOMAXIMIZED if win.zoomed else 0, ws)

    def set_placement(self, h, pl):
        win = self.windows[h]
        if win.deny_move:
            return False
        p = self._primary()
        nr = (pl.normal_rect[0] + p.work[0], pl.normal_rect[1] + p.work[1], pl.normal_rect[2] + p.work[0], pl.normal_rect[3] + p.work[1])
        win.normal_rect = nr
        if pl.show_cmd == w.SW_SHOWMAXIMIZED:
            m = self._mon_for_rect(nr) or p
            win.rect, win.zoomed, win.iconic = m.work, True, False
        elif pl.show_cmd in (w.SW_RESTORE, w.SW_SHOWNORMAL):
            win.rect, win.zoomed, win.iconic = nr, False, False
        return True

    def set_pos(self, h, x, y, cw=0, ch=0, no_size=False, async_pos=False):
        win = self.windows[h]
        self.set_pos_calls.append((h, x, y, cw, ch, no_size))
        if win.deny_move:
            return False
        if no_size:
            cw, ch = win.rect[2] - win.rect[0], win.rect[3] - win.rect[1]
        win.rect = (x, y, x + cw, y + ch)
        win.normal_rect = win.rect
        return True

    def show_async(self, h, cmd):
        win = self.windows[h]
        if cmd == w.SW_MINIMIZE:
            win.iconic = True
        elif cmd in (w.SW_RESTORE, w.SW_SHOWNOACTIVATE):
            if win.iconic:
                win.iconic = False
            elif win.zoomed:                     # đang phóng to → về kích thước thường
                win.zoomed = False
                win.rect = win.normal_rect or win.rect
        elif cmd == w.SW_SHOWMAXIMIZED:
            m = self._mon_for_rect(win.rect) or self._primary()
            win.rect, win.zoomed, win.iconic = m.work, True, False
        return True

    def post_message(self, h, msg, wp=0, lp=0):
        win = self.windows.get(h)
        if win is None:
            return False
        if msg == w.WM_SYSCOMMAND and wp == w.SC_MINIMIZE:
            if win.hides_to_tray:
                win.visible = False
            else:
                win.iconic = True
            if self.foreground == h:
                self.foreground = 0
        elif msg == w.WM_CLOSE:
            del self.windows[h]
        return True

    def set_foreground(self, h):
        if h in self.windows:
            self.foreground = h
            return True
        return False

    def enum_windows(self):
        return list(self.windows)

    def process_identity(self, pid):
        for win in self.windows.values():
            if win.pid == pid:
                return win.process, win.created, ""
        return "", 0.0, ""

    def own_pid(self):
        return self.own

    def cursor_pos(self):
        return (10, 10)


class FakeConfig(dict):
    def get(self, key, default=None):  # noqa: D401 - giống Config.get
        return super().get(key, default)

    def set(self, key, value):
        self[key] = value

    def save(self):
        pass


def dual_setup(dpi2=144, left_negative=True):
    """Màn hình 1 (chính) 1920x1080 @96 DPI; màn hình 2 bên TRÁI tọa độ âm, 2560x1440 @144 DPI."""
    m1 = mon(1, r"\\.\DISPLAY1", (0, 0, 1920, 1080), work=(0, 0, 1920, 1040), dpi=96, primary=True)
    if left_negative:
        m2 = mon(2, r"\\.\DISPLAY2", (-2560, -200, 0, 1240), work=(-2560, -200, 0, 1200), dpi=dpi2)
    else:
        m2 = mon(2, r"\\.\DISPLAY2", (1920, 0, 4480, 1440), work=(1920, 0, 4480, 1400), dpi=dpi2)
    api = FakeWin32(monitors=[m1, m2])
    cfg = FakeConfig({"monitors.source": {"device_id": m1.device_id, "device_name": m1.device_name, "friendly_name": m1.friendly_name},
                      "monitors.target": {"device_id": m2.device_id, "device_name": m2.device_name, "friendly_name": m2.friendly_name}})
    return api, cfg, m1, m2
