"""Khởi tạo ứng dụng NEXA: cấu hình, logging, controller, giao diện QML, overlay và shutdown sạch."""
from __future__ import annotations

import ctypes
import os
import sys

from nexa import DISPLAY_NAME, __version__
from nexa.utils.config import ASSETS_DIR, LOG_DIR, QML_DIR, Config, ensure_user_settings
from nexa.utils.logging import setup_logging

MUTEX_NAME = "Local\\NEXA_by_NXS_MEDIA_single_instance"


def _single_instance() -> object | None:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def run(argv: list[str]) -> int:
    if sys.platform != "win32":
        print("NEXA chỉ hỗ trợ Windows 10/11 64-bit.")
        return 2
    ensure_user_settings()
    log = setup_logging(LOG_DIR)
    log.info("Khởi động %s v%s (Python %s)", DISPLAY_NAME, __version__, sys.version.split()[0])
    mutex = _single_instance()
    if mutex is None:
        ctypes.windll.user32.MessageBoxW(None, "NEXA đang chạy rồi. Hãy dùng cửa sổ NEXA hiện có.", DISPLAY_NAME, 0x40)
        return 1

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFont, QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    web_preview = False
    try:                                          # trang HTML chạy thử hiện ngay trong NEXA (phải gọi trước QGuiApplication)
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
        web_preview = True
    except Exception:                             # bản dựng không có QtWebEngine → mở trình duyệt như trước
        pass
    app = QGuiApplication(argv)
    app.setApplicationName("NEXA")
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setOrganizationName("NXS MEDIA")
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "branding" / "nexa-icon.ico")))
    app.setFont(QFont("Segoe UI", 10))

    config = Config()
    holder: dict = {}

    def notify(kind: str, data: dict) -> None:
        if kind.startswith("3d_"):                    # mô hình 3D có cầu nối riêng (nexa/ui/three_d_bridge.py)
            ui3d = holder.get("ui3d")
            if ui3d is not None:
                ui3d.post(kind, data)
            return
        if kind.startswith("code_"):                  # sinh code: cầu nối riêng (nexa/ui/code_bridge.py)
            uic = holder.get("uicode")
            if uic is not None:
                uic.post(kind, data)
            return
        ui = holder.get("ui")
        if ui is not None:
            ui.post(kind, data)

    from nexa.core.controller import Controller
    from nexa.ui.bridge import CameraImageProvider, UiBridge
    from nexa.ui.overlay import OverlayManager

    try:
        controller = Controller(config, notify)
    except Exception:
        log.exception("Không khởi tạo được NEXA")
        ctypes.windll.user32.MessageBoxW(None, "NEXA không khởi động được. Xem logs/nexa.log.", DISPLAY_NAME, 0x10)
        return 3
    overlay = OverlayManager(controller, config)
    from nexa.ui.hud import HudManager
    ui = UiBridge(controller, overlay, HudManager(config))
    ui.compact = bool(config.get("ui.compact_on_start"))
    holder["ui"] = ui
    from nexa.ui.three_d_bridge import ThreeDBridge, register_qml_types
    register_qml_types()
    ui3d = ThreeDBridge(controller)
    holder["ui3d"] = ui3d
    from nexa.ui.code_bridge import CodeBridge
    uicode = CodeBridge(controller, web_preview=web_preview)
    holder["uicode"] = uicode

    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", CameraImageProvider(controller))
    engine.rootContext().setContextProperty("nexa", ui)
    engine.rootContext().setContextProperty("nexa3d", ui3d)
    engine.rootContext().setContextProperty("nexaCode", uicode)
    engine.warnings.connect(lambda warns: [log.warning("QML: %s", w.toString()) for w in warns])
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        log.error("Không nạp được giao diện QML")
        controller.shutdown()
        return 4

    controller.start()
    app.aboutToQuit.connect(controller.shutdown)
    autoquit = os.environ.get("NEXA_AUTOQUIT_SECONDS")  # chỉ dùng cho kiểm thử khói (scripts/diagnose.py)
    if autoquit:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(int(float(autoquit) * 1000), app.quit)
    grab_path = os.environ.get("NEXA_SMOKE_GRAB")  # kiểm thử khói: render CHÍNH cửa sổ NEXA ra PNG
    if grab_path:
        from PySide6.QtCore import QTimer

        def _grab() -> None:
            # grabWindow() render cảnh QML của NEXA, không chụp màn hình nên không lộ cửa sổ khác.
            engine.rootObjects()[0].grabWindow().save(grab_path)
        QTimer.singleShot(int(float(os.environ.get("NEXA_SMOKE_GRAB_AT", "8")) * 1000), _grab)
    smoke_text = os.environ.get("NEXA_SMOKE_TEXT")  # kiểm thử khói: gửi một lệnh như gõ bàn phím
    if smoke_text:
        from PySide6.QtCore import QTimer

        from nexa.core.events import Source
        QTimer.singleShot(5000, lambda: controller.submit_text(smoke_text, Source.KEYBOARD))
    code = app.exec()
    return code
