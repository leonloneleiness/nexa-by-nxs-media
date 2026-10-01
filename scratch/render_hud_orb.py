"""Render Orb.qml (đang nói, có dải tần) và Hud.qml offscreen ra PNG — không chụp màn hình thật."""
import math
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402

from nexa.utils.config import QML_DIR  # noqa: E402

app = QGuiApplication([])
out = Path(__file__).resolve().parent
warns = []


def view(name, w, h, bg):
    v = QQuickView()
    v.engine().warnings.connect(lambda ws: warns.extend(x.toString() for x in ws))
    v.setColor(QColor(bg))
    v.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    v.setSource(QUrl.fromLocalFile(str(QML_DIR / name)))
    for e in v.errors():
        warns.append(e.toString())
    v.resize(w, h)
    v.show()
    return v


orb = view("Orb.qml", 520, 520, "#081226")
hud = view("Hud.qml", 480, 560, "#3a4a5a")
o, hr = orb.rootObject(), hud.rootObject()
o.setProperty("appState", "SPEAKING")
hr.setProperty("subtitle", "Dạ, em đã mở YouTube và tìm bài nhạc anh yêu cầu rồi ạ.")
hr.addCard("Mở ứng dụng", "Đã mở Microsoft Edge", "done")
hr.addCard("Chụp màn hình", "Không tìm thấy thư mục lưu ảnh", "failed")
t0 = time.monotonic()
while time.monotonic() - t0 < 2.0:
    t = time.monotonic() - t0
    bands = [max(0.0, min(1.0, 0.55 + 0.4 * math.sin(t * 5 + i * 0.9) - i * 0.06)) for i in range(8)]
    o.setProperty("outLevel", 0.6 + 0.3 * math.sin(t * 7))
    o.setProperty("outBands", bands)
    hr.setProperty("bands", bands)
    hr.setProperty("outLevel", 0.7)
    app.processEvents()
    time.sleep(0.016)
orb.grabWindow().save(str(out / "orb_speaking.png"))
hud.grabWindow().save(str(out / "hud_bottom_right.png"))
print("warnings:", warns)
