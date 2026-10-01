"""Nạp Settings.qml offscreen với UiBridge thật + controller giả (không mở camera/mic) để bắt lỗi QML."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Property, QObject, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402

from nexa.ui.bridge import UiBridge  # noqa: E402
from nexa.utils.config import QML_DIR, Config  # noqa: E402

app = QGuiApplication([])
d = Path(tempfile.mkdtemp())
cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TTS:
    def describe_backends(self):
        return [{"name": "edge", "available": True, "info": "fake", "online": True}]

    def winrt_voices(self):
        return ["Microsoft An"]


ctrl = NS(config=cfg, gestures=NS(running=True), tts=TTS(),
          monitors=NS(describe=lambda: [
              {"device_name": "\\\\.\\DISPLAY1", "friendly_name": "Laptop", "width": 1920, "height": 1200, "role": "source"},
              {"device_name": "\\\\.\\DISPLAY2", "friendly_name": "Dell", "width": 1920, "height": 1080, "role": "target"}]),
          media_targets=lambda: [], audio=NS(clap=NS(stats=lambda: {})))


class Fake3D(QObject):
    changed = Signal()

    @Property("QVariantMap", notify=changed)
    def providerStatus(self):
        return {}


ui = UiBridge(ctrl)
warns = []
v = QQuickView()
v.engine().warnings.connect(lambda ws: warns.extend(x.toString() for x in ws))
v.rootContext().setContextProperty("nexa", ui)
f3 = Fake3D()
v.rootContext().setContextProperty("nexa3d", f3)
v.setColor(QColor("#081226"))
v.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
v.setSource(QUrl.fromLocalFile(str(QML_DIR / "Settings.qml")))
warns += [e.toString() for e in v.errors()]
v.resize(900, 900)
v.show()
for _ in range(30):
    app.processEvents()
root = v.rootObject()
print("root:", root is not None)
print("warnings:", "\n".join(warns) or "none")
