"""HUD góc màn hình: phụ đề câu NEXA đang nói + thẻ kết quả (lệnh đã chạy…) trượt ra rồi tự ẩn.

- Một QQuickView trong suốt, cùng cờ click-through/không nhận focus như overlay (_make_click_through).
- Vị trí đọc lại từ cấu hình mỗi lần hiện: ui.hud.screen (primary | cursor | tên thiết bị \\\\.\\DISPLAYn)
  và ui.hud.corner; đổi trong Cài đặt là có hiệu lực ngay lần nói tiếp theo.
- Hud.qml báo idle() khi hết phụ đề và thẻ → ẩn cửa sổ; mức âm/dải tần chỉ đẩy khi HUD đang hiện.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtQuick import QQuickView

from nexa.ui.overlay import _make_click_through
from nexa.utils.config import QML_DIR
from nexa.utils.logging import get_logger

log = get_logger("hud")

HUD_W, HUD_H = 480, 560
EDGE_MARGIN = 12
CORNERS = ("bottom_right", "bottom_left", "top_right", "top_left")
CARD_STATUSES = ("done", "failed")


def pick_screen(screens: list, choice: str, primary, cursor_screen=None):
    """primary | cursor | tên thiết bị; không khớp (màn hình đã rút) → màn hình chính."""
    choice = (choice or "primary").strip()
    if choice == "cursor" and cursor_screen is not None:
        return cursor_screen
    for s in screens:
        if s.name() == choice:
            return s
    return primary


def corner_pos(avail: tuple[int, int, int, int], corner: str, w: int = HUD_W, h: int = HUD_H,
               margin: int = EDGE_MARGIN) -> tuple[int, int]:
    """Góc trên-trái của HUD trong vùng làm việc (x, y, w, h) của màn hình — không đè thanh taskbar."""
    x0, y0, aw, ah = avail
    corner = corner if corner in CORNERS else "bottom_right"
    x = x0 + aw - w - margin if corner.endswith("right") else x0 + margin
    y = y0 + ah - h - margin if corner.startswith("bottom") else y0 + margin
    return x, y


class HudManager(QObject):
    def __init__(self, config: Any) -> None:
        super().__init__()
        self.config = config
        self.view: QQuickView | None = None

    def _cfg(self, key: str, default: Any = None) -> Any:
        v = self.config.get(f"ui.hud.{key}")
        return default if v is None else v

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("enabled", True))

    # ----- cửa sổ -----
    def _root(self):
        if self.view is None:
            view = QQuickView()
            view.setFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool |
                          Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
            view.setColor(QColor(0, 0, 0, 0))
            view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
            view.setSource(QUrl.fromLocalFile(str(QML_DIR / "Hud.qml")))
            if view.status() == QQuickView.Status.Error:
                for err in view.errors():
                    log.error("Hud.qml: %s", err.toString())
                return None
            view.resize(HUD_W, HUD_H)
            view.setTitle("NEXA HUD")
            view.rootObject().idle.connect(view.hide)
            self.view = view
        return self.view.rootObject()

    def _show(self):
        root = self._root()
        if root is None:
            return None
        view = self.view
        if not view.isVisible():
            app = QGuiApplication.instance()
            screen = pick_screen(app.screens(), str(self._cfg("screen", "primary")), app.primaryScreen(),
                                 app.screenAt(QCursor.pos()))
            corner = str(self._cfg("corner", "bottom_right"))
            g = screen.availableGeometry()
            x, y = corner_pos((g.x(), g.y(), g.width(), g.height()), corner)
            view.setScreen(screen)
            view.setPosition(QPoint(x, y))
            root.setProperty("corner", corner)
            root.setProperty("cardSeconds", int(self._cfg("card_seconds", 5)))
            root.setProperty("showSubtitles", bool(self._cfg("subtitles", True)))
            view.show()
            try:
                _make_click_through(int(view.winId()))
            except Exception:
                log.exception("Không đặt được click-through cho HUD")
        return root

    # ----- sự kiện (luồng GUI) -----
    def subtitle(self, text: str) -> None:
        if not self.enabled:
            return
        if text and self._cfg("subtitles", True):
            root = self._show()
        else:
            root = self.view.rootObject() if self.view is not None else None
        if root is not None:
            root.setProperty("subtitle", text or "")

    def task(self, data: dict) -> None:
        if not self.enabled or not self._cfg("cards", True) or data.get("status") not in CARD_STATUSES:
            return
        root = self._show()
        if root is not None:
            root.addCard(str(data.get("title") or data.get("tool") or ""), str(data.get("message") or ""),
                         str(data.get("status")))

    def _visible_root(self):
        if self.view is None or not self.view.isVisible():
            return None
        return self.view.rootObject()

    def levels(self, level: float | None = None, bands: list | None = None) -> None:
        root = self._visible_root()
        if root is None:
            return
        if level is not None:
            root.setProperty("outLevel", float(level))
        if bands is not None:
            root.setProperty("bands", list(bands))

    def state(self, state: str) -> None:
        if self.view is not None:
            self.view.rootObject().setProperty("appState", state)
