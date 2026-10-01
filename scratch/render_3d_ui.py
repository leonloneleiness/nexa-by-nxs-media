"""Render offscreen các màn 3D (viewer HUD + bảng bộ phận + xưởng tạo mô hình) ra PNG. Không chụp màn hình thật.

python scratch/render_3d_ui.py   → scratch/fab_*.png, scratch/viewer_*.png
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen:size=1920x1200"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402

app = QGuiApplication([])
app.setFont(QFont("Segoe UI", 10))
from nexa.utils.config import QML_DIR, Config  # noqa: E402

out = Path(__file__).resolve().parent


class FakeNexa(QObject):
    changed = Signal()
    toast = Signal(str, bool)

    @Property(bool, notify=changed)
    def showFps(self):
        return True


def pump(t):
    end = time.monotonic() + t
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def render(qml, ctx, w, h, name, t=1.2):
    v = QQuickView()
    v.setColor(QColor("#02060c"))
    warns = []
    v.engine().warnings.connect(lambda ws: warns.extend(x.toString() for x in ws))
    for k, val in ctx.items():
        v.rootContext().setContextProperty(k, val)
    v.setResizeMode(QQuickView.SizeRootObjectToView)
    v.setSource(QUrl.fromLocalFile(str(QML_DIR / qml)))
    for e in v.errors():
        warns.append(e.toString())
    v.resize(w, h)
    v.show()
    pump(t)
    v.grabWindow().save(str(out / name))
    print(name, "warnings:", warns or "none")
    v.hide()
    return v


class Fake3D(QObject):
    changed = Signal()

    def __init__(self, job, models):
        super().__init__()
        self._job, self._models = job, models

    @Property("QVariantMap", notify=changed)
    def activeJob(self):
        return self._job

    @Property("QVariantList", notify=changed)
    def models(self):
        return self._models

    @Property("QVariantMap", notify=changed)
    def providerStatus(self):
        return {"ok": False, "name": ""}

    @Slot()
    def refreshModels(self):
        pass


models = [{"id": f"m{i}", "name": n, "quality_score": q, "status": s, "thumb_url": ""}
          for i, (n, q, s) in enumerate([("UAV mini bốn cánh", 92, "ready"), ("Bu-lông M8×30", 97, "ready"),
                                         ("Robot chó 3 khớp", 71, "failed"), ("Xe tự hành 4 bánh", 88, "ready"),
                                         ("Trực thăng mini", 84, "ready")])]
job = {"id": "j1", "state": "segmenting", "label": "UAV mini bốn cánh", "progress": 0.47, "terminal": False,
       "elapsed": 6.4, "message": "Đang tách 26 bộ phận và dựng assembly…", "warnings": ["Chưa có kích thước sải cánh — dùng 250 mm"],
       "project_id": ""}
keep = []
keep.append(render("ModelGenerationPanel.qml", {"nexa3d": Fake3D(job, models), "nexa": FakeNexa()}, 980, 680, "fab_running.png"))
done = dict(job, state="ready", progress=1.0, terminal=True, message="Hoàn tất · 26 bộ phận · 92/100", warnings=[], project_id="p1")
keep.append(render("ModelGenerationPanel.qml", {"nexa3d": Fake3D(done, models), "nexa": FakeNexa()}, 980, 680, "fab_ready.png"))

# viewer thật với ThreeDBridge
from nexa.three_d.asset_store import AssetStore  # noqa: E402
from nexa.three_d.service import ThreeDService  # noqa: E402
from nexa.ui.three_d_bridge import ThreeDBridge, register_qml_types  # noqa: E402

register_qml_types()
d = Path(tempfile.mkdtemp())
cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
cfg.set("three_d.ai_review", False)
holder = {}


class C:
    config = cfg
    gestures = type("G", (), {"running": False})()
    three_d = ThreeDService(cfg, notify=lambda k, v: holder["b"].post(k, v) if "b" in holder else None,
                            store=AssetStore(d / "cache"), provider_factory=lambda: None)


c = C()
j = c.three_d.submit("Tạo UAV mini bốn cánh camera phía trước", open_when_ready=False)
while not j.terminal:
    time.sleep(0.05)
bridge = ThreeDBridge(c)
holder["b"] = bridge
c.three_d.viewer.open(j.project_id)
end = time.monotonic() + 15
while time.monotonic() < end and not (bridge.model.get("parts") and not bridge.loading):
    app.processEvents()
    time.sleep(0.02)
parts = bridge.model["parts"]
bridge.partAction("focus", [parts[3]["id"]])
pump(0.5)
keep.append(render("ModelViewer.qml", {"nexa3d": bridge, "nexa": FakeNexa()}, 1500, 860, "viewer_wide.png", 2.0))
keep.append(render("ModelViewer.qml", {"nexa3d": bridge, "nexa": FakeNexa()}, 900, 760, "viewer_narrow.png", 2.0))
c.three_d.viewer.close()
c.three_d.shutdown()
