"""Mọi cửa sổ NEXA mở ra (ứng dụng, trang web, tệp, console chạy thử…) hiện SONG SONG với NEXA — không che, không ẩn NEXA.

Trước khi chạy một công cụ "mở" (open_app, open_url, open_named, run_file…) NEXA ghi lại các cửa sổ đang có. Công cụ
xong thì một luồng nền chờ tối đa vài giây để cửa sổ mới xuất hiện (hoặc cửa sổ được đưa lên trước), rồi nếu nó CHE
NEXA (hoặc NEXA đang thu nhỏ) thì chia màn hình của NEXA: NEXA một bên (~40% bề ngang, ≥ 600 px logic), cửa sổ kia
phần còn lại. Không đổi tiêu điểm: cửa sổ vừa mở vẫn được gõ phím như bình thường. Cửa sổ nằm ở màn hình khác, hoặc
đã không đè lên NEXA, thì để nguyên. Chế độ thu gọn (quả cầu nhỏ luôn nổi trên cùng) không cần xếp.
Tắt bằng ui.side_by_side: false.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from nexa.desktop import win32api as w
from nexa.utils.logging import get_logger

log = get_logger("desktop.side_by_side")

# Công cụ có thể làm hiện một cửa sổ khác (che NEXA). Không gồm công cụ tự sắp cửa sổ (maximize_window, chuyển màn hình…).
OPENER_TOOLS = frozenset({
    "open_app", "open_url", "web_search", "site_search", "play_youtube", "focus_window", "new_document",
    "vscode_new_file", "check_zalo", "open_admin_tool", "admin_shell", "open_path", "open_named",
    "restore_last_minimized", "run_file",
})
SHELL_CLASSES = frozenset({
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
    "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow", "ForegroundStaging", "MultitaskingViewFrame",
    "TaskListThumbnailWnd", "TopLevelWindowForOverflowXamlIsland", "#32768", "tooltips_class32",
})
WS_THICKFRAME = 0x00040000
WS_EX_TRANSPARENT = 0x00000020
OVERLAP_MIN = 0.05          # cửa sổ mới đè lên > 5% NEXA mới xếp lại
MIN_W, MIN_H = 240, 160     # nhỏ hơn: popup/thông báo, bỏ qua
NEXA_MIN_LOGICAL = 600      # = minimumWidth của Main.qml khi không thu gọn

Rect = tuple[int, int, int, int]


@dataclass
class Snapshot:
    windows: frozenset[int]
    foreground: int
    started: float


def _area(r: Rect) -> int:
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def _intersect(a: Rect, b: Rect) -> int:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def move_visible(api: Any, hwnd: int, rect: Rect, async_pos: bool = False) -> bool:
    """Đặt khung NHÌN THẤY của cửa sổ đúng `rect` (bù viền vô hình ~7 px của Windows 10/11)."""
    vis, full = api.get_rect(hwnd), api.get_window_rect(hwnd)
    dl, dt = vis[0] - full[0], vis[1] - full[1]
    dr, db = full[2] - vis[2], full[3] - vis[3]
    x, y = rect[0] - dl, rect[1] - dt
    cw, ch = rect[2] - rect[0] + dl + dr, rect[3] - rect[1] + dt + db
    if async_pos:
        return api.set_pos(hwnd, x, y, cw, ch, async_pos=True)
    return api.set_pos(hwnd, x, y, cw, ch)


def split_layout(work: Rect, nexa_rect: Rect, dpi: int, ratio: float, nexa_maximized: bool) -> tuple[Rect, Rect]:
    """Chia vùng làm việc của màn hình: trả (khung NEXA, khung cửa sổ kia). NEXA giữ phía nó đang đứng
    (đang phóng to → bên phải); giữ bề ngang hiện tại nếu đã hợp lý (anh tự chỉnh), không thì ~ratio màn hình."""
    left, top, right, bottom = work
    width = right - left
    min_w = int(round(NEXA_MIN_LOGICAL * dpi / 96))
    cap = max(min_w, int(width * 0.5))
    cur = nexa_rect[2] - nexa_rect[0]
    if not nexa_maximized and min_w <= cur <= cap:
        nexa_w = cur
    else:
        nexa_w = min(cap, max(min_w, int(width * ratio)))
    nexa_w = min(nexa_w, width - MIN_W)
    on_right = nexa_maximized or (nexa_rect[0] + nexa_rect[2]) / 2 >= left + width / 2
    if on_right:
        return (right - nexa_w, top, right, bottom), (left, top, right - nexa_w, bottom)
    return (left, top, left + nexa_w, bottom), (left + nexa_w, top, right, bottom)


class SideBySide:
    def __init__(self, config: Any, api: Any | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.api = api or w.Win32Api()
        self._sleep = sleep
        self._clock = clock
        self._gen = 0
        self._lock = threading.Lock()
        self.last: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("ui.side_by_side", True))

    # ----- nhận diện cửa sổ -----
    def _own_pid(self) -> int:
        return self.api.own_pid()

    def nexa_window(self) -> int:
        """Cửa sổ chính của NEXA: cửa sổ có tiêu đề lớn nhất của tiến trình này (bỏ lớp phủ trong suốt)."""
        best, best_area = 0, -1
        own = self._own_pid()
        for h in self.api.enum_windows():
            try:
                if self.api.get_pid(h) != own or not self.api.get_title(h):
                    continue
                if not (self.api.is_visible(h) or self.api.is_iconic(h)):
                    continue
                if self.api.get_ex_style(h) & WS_EX_TRANSPARENT:           # lớp phủ click-through
                    continue
                area = _area(self.api.get_rect(h))
                if self.api.get_title(h).startswith("NEXA"):
                    area += 1 << 40
                if area > best_area:
                    best, best_area = h, area
            except OSError:
                continue
        return best

    def is_candidate(self, h: int) -> bool:
        api = self.api
        try:
            if not api.is_window(h) or not api.is_visible(h) or api.is_iconic(h) or api.is_cloaked(h):
                return False
            if api.get_pid(h) == self._own_pid() or not api.get_title(h).strip():
                return False
            if api.get_class(h) in SHELL_CLASSES:
                return False
            if api.get_ex_style(h) & (w.WS_EX_TOOLWINDOW | w.WS_EX_NOACTIVATE):
                return False
            if api.get_root_owner(h) not in (h, 0):
                return False
            style = api.get_style(h)
            if (style & w.WS_CAPTION) != w.WS_CAPTION and not style & WS_THICKFRAME:
                return False
            r = api.get_rect(h)
            return r[2] - r[0] >= MIN_W and r[3] - r[1] >= MIN_H
        except OSError:
            return False

    # ----- vòng đời một công cụ -----
    def before(self, tool: str) -> Snapshot | None:
        if tool not in OPENER_TOOLS or not self.enabled:
            return None
        try:
            return Snapshot(frozenset(self.api.enum_windows()), self.api.get_foreground(), self._clock())
        except OSError:
            return None

    def after(self, snap: Snapshot | None, tool: str, ok: bool, timeout: float = 10.0) -> None:
        """Gọi sau khi công cụ chạy xong: chờ cửa sổ trong luồng nền (không làm chậm câu trả lời)."""
        if snap is None or not ok:
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
        threading.Thread(target=self._watch, args=(snap, tool, gen, timeout), daemon=True,
                         name="side-by-side").start()

    def _watch(self, snap: Snapshot, tool: str, gen: int, timeout: float) -> None:
        try:
            target = self.wait_target(snap, timeout, lambda: gen != self._gen)
            if target and gen == self._gen:
                self.arrange(target, tool)
        except Exception:                                   # không bao giờ làm hỏng công cụ vừa chạy
            log.exception("Xếp cửa sổ cạnh NEXA lỗi")

    def wait_target(self, snap: Snapshot, timeout: float, superseded: Callable[[], bool] = lambda: False) -> int:
        """Cửa sổ vừa hiện ra (mới nhất theo thứ tự Z), hoặc cửa sổ vừa được đưa lên trước."""
        start = self._clock()
        while True:
            elapsed = self._clock() - start
            if superseded():
                return 0
            windows = self.api.enum_windows()
            fresh = [h for h in windows if h not in snap.windows and self.is_candidate(h)]
            if fresh:
                return fresh[0]
            fg = self.api.get_foreground()
            if fg and fg != snap.foreground and elapsed >= 0.6 and self.is_candidate(fg):
                return fg
            if elapsed >= timeout:
                # trang mở thành tab trong trình duyệt đang ở trước: xếp chính trình duyệt đó
                return fg if fg and self.is_candidate(fg) else 0
            self._sleep(0.25)

    # ----- sắp xếp -----
    def _monitor_of(self, hwnd: int) -> Any:
        mons = self.api.enum_monitors()
        hmon = self.api.monitor_from_window(hwnd)
        for m in mons:
            if m.hmonitor == hmon:
                return m
        return next((m for m in mons if m.primary), mons[0] if mons else None)

    def _wait(self, cond: Callable[[], bool], limit: float) -> None:
        end = self._clock() + limit
        while not cond() and self._clock() < end:
            self._sleep(0.05)

    def _move_visible(self, hwnd: int, rect: Rect, async_pos: bool = False) -> bool:
        return move_visible(self.api, hwnd, rect, async_pos)

    def arrange(self, target: int, tool: str = "") -> str:
        """Xếp `target` cạnh NEXA. Trả mô tả ngắn (để ghi log/kiểm thử)."""
        api = self.api
        nexa = self.nexa_window()
        if not nexa or not api.is_window(target) or target == nexa:
            return "no_nexa"
        was_iconic = api.is_iconic(nexa)
        if was_iconic:                                       # NEXA không bao giờ bị ẩn: hiện lại, KHÔNG lấy tiêu điểm
            api.show_async(nexa, w.SW_SHOWNOACTIVATE)
            self._wait(lambda: not api.is_iconic(nexa), 0.8)
        if api.get_ex_style(nexa) & w.WS_EX_TOOLWINDOW:     # chế độ thu gọn: quả cầu nhỏ luôn nổi trên cùng
            return "compact"
        nr, tr = api.get_rect(nexa), api.get_rect(target)
        if not was_iconic and _intersect(nr, tr) <= OVERLAP_MIN * max(1, _area(nr)):
            return "already_side_by_side"
        mon = self._monitor_of(nexa)
        if mon is None:
            return "no_monitor"
        nexa_max = api.is_zoomed(nexa)
        ratio = float(self.config.get("ui.side_by_side_ratio", 0.4) or 0.4)
        nexa_rect, other_rect = split_layout(mon.work, nr, mon.dpi, min(0.6, max(0.25, ratio)), nexa_max)
        if api.is_zoomed(target):
            api.show_async(target, w.SW_RESTORE)             # cửa sổ vừa mở vốn đã ở trước: khôi phục không đổi tiêu điểm
            self._wait(lambda: not api.is_zoomed(target), 0.8)
        moved_target = self._move_visible(target, other_rect)
        if nexa_max:
            api.show_async(nexa, w.SW_SHOWNOACTIVATE)
            self._wait(lambda: not api.is_zoomed(nexa), 0.8)
        moved_nexa = self._move_visible(nexa, nexa_rect, async_pos=True)
        self.last = {"tool": tool, "target": target, "title": api.get_title(target), "nexa": nexa_rect,
                     "other": other_rect, "ok": bool(moved_target and moved_nexa)}
        log.info("Xếp cạnh NEXA sau %s: «%s» %s | NEXA %s", tool, api.get_title(target)[:60], other_rect, nexa_rect)
        return "arranged" if moved_target else "target_refused"
