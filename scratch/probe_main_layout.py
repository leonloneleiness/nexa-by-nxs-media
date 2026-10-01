"""Offscreen: nạp Main.qml với nexa giả + bridge 3D thật, mở viewer → kiểm tra NEXA và viewer nằm song song."""
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen:size=1920x1200"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtCore import Property, QObject, Signal  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

app = QGuiApplication([])

import tempfile  # noqa: E402

from nexa.three_d.asset_store import AssetStore  # noqa: E402
from nexa.three_d.service import ThreeDService  # noqa: E402
from nexa.ui.three_d_bridge import ThreeDBridge, register_qml_types  # noqa: E402
from nexa.utils.config import QML_DIR, Config  # noqa: E402

d = Path(tempfile.mkdtemp())
cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
cfg.set("three_d.ai_review", False)
holder = {}


class G:
    running = False


class C:
    config = cfg
    gestures = G()
    three_d = ThreeDService(cfg, notify=lambda k, v: holder["b"].post(k, v) if "b" in holder else None,
                            store=AssetStore(d / "cache"), provider_factory=lambda: None)


c = C()
job = c.three_d.submit("Tạo UAV mini bốn cánh camera phía trước", open_when_ready=False)
while not job.terminal:
    time.sleep(0.05)


class FakeNexa(QObject):
    changed = Signal()
    toast = Signal(str, bool)
    raiseWindow = Signal()

    @Property(bool, notify=changed)
    def compact(self):
        return False

    @Property(bool, notify=changed)
    def showFps(self):
        return False

    @Property(str, notify=changed)
    def smokeOpen(self):
        return ""

    @Property(str, notify=changed)
    def state(self):
        return "STANDBY"

    @Property(str, notify=changed)
    def stateLabel(self):
        return "Đang chờ"

    @Property(str, notify=changed)
    def stateDetail(self):
        return ""

    @Property(str, notify=changed)
    def heardText(self):
        return ""

    @Property(str, notify=changed)
    def effects(self):
        return "reduced"

    @Property(str, notify=changed)
    def foreground(self):
        return ""

    @Property(str, notify=changed)
    def statusText(self):
        return ""

    @Property("QVariantMap", notify=changed)
    def status(self):
        return {}

    @Property("QVariantMap", notify=changed)
    def confirmation(self):
        return {"active": False}

    @Property("QVariantList", notify=changed)
    def messages(self):
        return []

    @Property("QVariantList", notify=changed)
    def tasks(self):
        return []

    @Property(float, notify=changed)
    def micLevel(self):
        return 0.0

    @Property(float, notify=changed)
    def outLevel(self):
        return 0.0

    @Property(bool, notify=changed)
    def cameraOn(self):
        return False

    @Property(bool, notify=changed)
    def listeningSpeech(self):
        return False

    @Property(bool, notify=changed)
    def controlPaused(self):
        return False

    @Property(bool, notify=changed)
    def visionSending(self):
        return False


register_qml_types()
bridge = ThreeDBridge(c)
holder["b"] = bridge
eng = QQmlApplicationEngine()
fake_nexa = FakeNexa()
eng.rootContext().setContextProperty("nexa", fake_nexa)
eng.rootContext().setContextProperty("nexa3d", bridge)
eng.load(str(QML_DIR / "Main.qml"))
win = eng.rootObjects()[0]


def pump(t):
    end = time.monotonic() + t
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


pump(0.5)
grid = win.findChild(QQuickItem, "mainGrid")
print("closed: grid", grid.width(), "win", win.width(), win.property("visibility"))
c.three_d.viewer.open(job.project_id)
pump(3)
viewer = win.findChild(QQuickItem, "viewer3d")
print("bridge.viewerOpen", bridge.viewerOpen, "qml viewer3dOpen", win.property("viewer3dOpen"), "shown", win.property("viewerShown"))
print("open: win", win.width(), "x", win.height(), "visibility", win.property("visibility"),
      "autoMax", win.property("autoMaximized"))
print("grid x..", grid.mapToScene(grid.position()).x(), grid.width(), grid.height(), "cols", grid.property("columns"))
vp = viewer.mapToScene(viewer.boundingRect().topLeft())
print("viewer x", vp.x(), "w", viewer.width(), "h", viewer.height(), "item", viewer.property("item") is not None)
win.showNormal()
pump(0.3)
win.setProperty("height", 1080)
for w in (1320, 1920):
    win.setProperty("width", w)
    pump(0.4)
    vp = viewer.mapToScene(viewer.boundingRect().topLeft())
    print(f"width {w}: grid w {grid.width():.0f}, viewer x {vp.x():.0f} w {viewer.width():.0f}")
win.grabWindow().save(str(d / "main_viewer.png"))
print("png", d / "main_viewer.png")
c.three_d.viewer.close()
pump(1)
print("after close: viewer active", viewer.property("active"), "grid cols", grid.property("columns"), "grid w", grid.width(),
      "visibility", win.property("visibility"))
c.three_d.shutdown()
from PySide6.QtQml import QQmlExpression  # noqa: E402
ctx = eng.rootContext()
for e in ("nexa.compact", "win.viewerShown", "win.viewer3dOpen", "nexa3d.viewerOpen", "typeof nexa.compact"):
    ex = QQmlExpression(ctx, win, e)
    print(e, "=>", ex.evaluate())
