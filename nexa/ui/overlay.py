"""Overlay trong suốt trên từng màn hình.

- Mỗi QScreen có một QQuickView riêng phủ đúng màn hình đó, cờ: không viền, luôn trên cùng, Tool,
  WindowTransparentForInput (click-through), WindowDoesNotAcceptFocus; thêm WS_EX_TRANSPARENT |
  WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW qua Win32 để chắc chắn không chặn chuột và
  không cướp focus.
- Tọa độ Win32 là pixel vật lý; mỗi màn hình được ánh xạ bằng tên thiết bị (\\\\.\\DISPLAYn = QScreen.name())
  và devicePixelRatio riêng của màn hình đó.
- Overlay chỉ phản ánh sự kiện thật (vị trí nhấp, cửa sổ đích, kết quả chuyển màn hình/media); không
  giả lập việc di chuyển cửa sổ bằng hoạt ảnh.
- Tự ẩn khi không có hiệu ứng.
"""
from __future__ import annotations

import ctypes
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQuick import QQuickView

from nexa.utils.config import QML_DIR
from nexa.utils.logging import get_logger

log = get_logger("overlay")

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def _make_click_through(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    get = user32.GetWindowLongPtrW if hasattr(user32, "GetWindowLongPtrW") else user32.GetWindowLongW
    set_ = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
    get.restype = ctypes.c_ssize_t
    set_.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    style = get(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    set_(ctypes.c_void_p(hwnd), GWL_EXSTYLE,
         style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


class OverlayManager(QObject):
    def __init__(self, controller: Any, config: Any) -> None:
        super().__init__()
        self.controller = controller
        self.config = config
        self.views: dict[str, QQuickView] = {}
        self._hide_timers: dict[str, QTimer] = {}
        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda _s: self.rebuild())
        app.screenRemoved.connect(lambda _s: self.rebuild())
        self.rebuild()

    # ----- tạo/xóa -----
    def rebuild(self) -> None:
        names = {s.name() for s in QGuiApplication.screens()}
        for name in list(self.views):
            if name not in names:
                view = self.views.pop(name)
                view.close()
                view.deleteLater()
        for screen in QGuiApplication.screens():
            if screen.name() not in self.views:
                self.views[screen.name()] = self._create(screen)
            else:
                self.views[screen.name()].setGeometry(screen.geometry())

    def _create(self, screen) -> QQuickView:
        view = QQuickView()
        view.setFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool |
                      Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        view.setColor(QColor(0, 0, 0, 0))
        view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        view.setScreen(screen)
        view.setSource(QUrl.fromLocalFile(str(QML_DIR / "Overlay.qml")))
        if view.status() == QQuickView.Status.Error:
            for err in view.errors():
                log.error("Overlay.qml: %s", err.toString())
        view.setGeometry(screen.geometry())
        view.setTitle("NEXA overlay")
        return view

    def _ensure_visible(self, name: str, ms: int = 2200) -> QQuickView | None:
        view = self.views.get(name)
        if view is None:
            return None
        if not view.isVisible():
            view.show()
            try:
                _make_click_through(int(view.winId()))
            except Exception:
                log.exception("Không đặt được click-through cho overlay")
        timer = self._hide_timers.get(name)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda n=name: self._hide(n))
            self._hide_timers[name] = timer
        timer.start(ms)
        return view

    def _hide(self, name: str) -> None:
        view = self.views.get(name)
        if view is not None:
            view.hide()

    # ----- ánh xạ tọa độ -----
    def _monitor_map(self) -> dict[str, Any]:
        return {m.device_name: m for m in self.controller.monitors.refresh()}

    def _screen_for_point(self, x: float, y: float) -> tuple[str | None, Any]:
        for name, m in self._monitor_map().items():
            l, t, r, b = m.rect
            if l <= x < r and t <= y < b and name in self.views:
                return name, m
        return None, None

    def _local(self, name: str, m: Any, x: float, y: float) -> tuple[float, float]:
        dpr = self.views[name].screen().devicePixelRatio() or 1.0
        return (x - m.rect[0]) / dpr, (y - m.rect[1]) / dpr

    def _root(self, name: str, ms: int = 2200):
        view = self._ensure_visible(name, ms)
        return view.rootObject() if view is not None else None

    def _cursor_screen(self) -> tuple[str | None, Any]:
        try:
            x, y = self.controller.api.cursor_pos()
        except Exception:
            x, y = 0, 0
        name, m = self._screen_for_point(x, y)
        if name is None:
            primary = next((mm for mm in self._monitor_map().values() if mm.primary), None)
            if primary is not None and primary.device_name in self.views:
                return primary.device_name, primary
        return name, m

    # ----- sự kiện -----
    def handle(self, data: dict) -> None:
        if not self.config.get("ui.overlay"):
            return
        kind = data.get("kind")
        try:
            if kind == "click" and data.get("x") is not None:
                self._ripple(data["x"], data["y"])
            elif kind in ("highlight", "minimize", "restore") and data.get("rect"):
                self._highlight(data["rect"], data.get("text", ""), kind)
            elif kind == "move_monitor":
                self._move_monitor(data)
            elif kind == "media":
                name, _m = self._cursor_screen()
                root = self._root(name, 1600) if name else None
                if root is not None:
                    root.mediaIcon(data.get("state", "error"), data.get("text", ""))
            elif kind == "toast":
                name, _m = self._cursor_screen()
                root = self._root(name, 2600) if name else None
                if root is not None:
                    root.toast(data.get("text", ""), bool(data.get("error")))
        except Exception:
            log.exception("Lỗi hiển thị overlay %s", kind)

    def _ripple(self, x: float, y: float) -> None:
        name, m = self._screen_for_point(x, y)
        if name is None:
            return
        lx, ly = self._local(name, m, x, y)
        root = self._root(name, 1200)
        if root is not None:
            root.ripple(lx, ly)

    def _highlight(self, rect: list, text: str, kind: str) -> None:
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        name, m = self._screen_for_point(cx, cy)
        if name is None:
            return
        x1, y1 = self._local(name, m, rect[0], rect[1])
        x2, y2 = self._local(name, m, rect[2], rect[3])
        root = self._root(name, 2000)
        if root is not None:
            root.highlight(x1, y1, x2 - x1, y2 - y1, text, kind)

    def _move_monitor(self, data: dict) -> None:
        src, dst = data.get("source"), data.get("target")
        if not src or not dst:
            return
        scx, scy = (src[0] + src[2]) / 2, (src[1] + src[3]) / 2
        dcx, dcy = (dst[0] + dst[2]) / 2, (dst[1] + dst[3]) / 2
        direction = "right" if dcx >= scx else "left"
        if abs(dcy - scy) > abs(dcx - scx):
            direction = "down" if dcy > scy else "up"
        sname, _sm = self._screen_for_point(scx, scy)
        if sname:
            root = self._root(sname, 1600)
            if root is not None:
                root.sweep(direction, "Chuyển sang màn hình 2 →" if direction == "right" else "Chuyển sang màn hình 2")
        if data.get("rect"):
            self._highlight(data["rect"], data.get("text", "Đã chuyển sang màn hình 2"), "arrive")

    def identify(self, monitors: list[dict]) -> None:
        for m in monitors:
            name = m["device_name"]
            if name not in self.views:
                continue
            role = {"source": "NGUỒN · 1", "target": "ĐÍCH · 2"}.get(m.get("role", ""), "")
            root = self._root(name, 4500)
            if root is not None:
                root.identify(m["device_name"].replace("\\\\.\\", "").replace("\\", "").replace(".", ""),
                              f"{m['friendly_name']} · {m['width']}×{m['height']} · {m['scale']}%"
                              + (" · màn hình chính" if m.get("primary") else ""), role)
