"""Render Main.qml offscreen ra PNG với UiBridge thật + controller giả (không mở camera/mic, không chụp màn hình thật).

python scratch/render_main_ui.py            → 1320×820, 1600×900, 900×820 (hẹp) + in cảnh báo QML
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

from PySide6.QtCore import Property, QObject, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

app = QGuiApplication([])
from PySide6.QtGui import QFont  # noqa: E402
app.setFont(QFont("Segoe UI", 10))

from nexa.ui.bridge import UiBridge  # noqa: E402
from nexa.utils.config import QML_DIR, Config  # noqa: E402

out = Path(__file__).resolve().parent
d = Path(tempfile.mkdtemp())
cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


ctrl = NS(config=cfg, gestures=NS(running=False), provider=NS(last_latency_ms=1840.0),
          tts=NS(describe_backends=lambda: [], winrt_voices=lambda: []),
          monitors=NS(describe=lambda: []), media_targets=lambda: [], audio=NS(clap=NS(stats=lambda: {})))


def fake(name, vals, slots=()):
    sig = Signal()
    attrs = {"changed": sig, "toast": Signal(str, bool), "panelChanged": Signal()}
    for k, (t, v) in vals.items():
        attrs[k] = Property(t, (lambda v: lambda self: v)(v), notify=sig)
    for s in slots:
        attrs[s] = Slot()(lambda self: None)
    return type(name, (QObject,), attrs)()


f3 = fake("F3", {"viewerOpen": (bool, False), "workspace": (bool, False), "activeJob": ("QVariantMap", {}),
                 "providerStatus": ("QVariantMap", {})})
fc = fake("FC", {"panelOpen": (bool, False), "busy": (bool, False), "job": ("QVariantMap", {})}, ("openPanel", "closePanel"))

ui = UiBridge(ctrl)
warns = []
eng = QQmlApplicationEngine()
eng.warnings.connect(lambda ws: warns.extend(w.toString() for w in ws))
ctx = eng.rootContext()
ctx.setContextProperty("nexa", ui)
ctx.setContextProperty("nexa3d", f3)
ctx.setContextProperty("nexaCode", fc)
eng.load(str(QML_DIR / "Main.qml"))
win = eng.rootObjects()[0]


def pump(t):
    end = time.monotonic() + t
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


ui.post("status", {"mic": {"ok": True}, "ai": {"ok": True}, "stt": {"ready": True, "model": "large-v3-turbo"},
                   "tts": {"backend": "edge"}, "bridge": {"connected": False}, "autonomy": "standard"})
ui.post("state", {"state": "LISTENING", "label": "Đang nghe", "detail": "nói lệnh của anh"})
ui.post("user_message", {"text": "mở Notepad rồi đặt âm lượng 30 phần trăm", "source": "voice"})
ui.post("task", {"task_id": "t1", "step_id": "s1", "tool": "open_app", "title": "Mở ứng dụng", "status": "running",
                 "message": "Đang mở Notepad", "source": "voice"})
ui.post("task", {"task_id": "t1", "step_id": "s1", "tool": "open_app", "title": "Mở ứng dụng", "status": "done",
                 "message": "Đã mở Notepad", "source": "voice"})
ui.post("task", {"task_id": "t1", "step_id": "s2", "tool": "set_volume", "title": "Âm lượng", "status": "running",
                 "message": "Đặt 30%", "source": "voice"})
ui.post("assistant_message", {"text": "Dạ, em đã mở Notepad và đang chỉnh âm lượng về 30% ạ."})
ui.post("heard", {"text": "mở Notepad rồi đặt âm lượng 30 phần trăm"})
pump(2.2)   # chờ vài nhịp đo CPU/RAM/GPU
print("sysStats:", dict(ui.sysStats))
print("timeline:", [(x.get("kind"), x.get("status")) for x in ui.timeline])

for (w, h, tag, st) in ((1320, 820, "wide", "LISTENING"), (1600, 900, "big", "THINKING"), (900, 820, "narrow", "SPEAKING")):
    ui.post("state", {"state": st, "label": {"LISTENING": "Đang nghe", "THINKING": "Đang suy nghĩ",
                                             "SPEAKING": "Đang nói"}[st], "detail": "…"})
    win.setProperty("width", w)
    win.setProperty("height", h)
    pump(1.0)
    dock = win.findChild(QQuickItem, "dock")
    ring = win.findChild(QQuickItem, "statsRing")
    icons = win.findChild(QQuickItem, "statusIcons")
    print(f"{tag}: dock {dock.width():.0f}x{dock.height():.0f} ring visible {ring.isVisible()} icons h {icons.height():.0f}")
    win.grabWindow().save(str(out / f"main_{tag}.png"))
print("warnings:", "\n".join(warns) or "none")
win.setProperty("width", 1320); win.setProperty("height", 820)
win.setProperty("historyOpen", True)
pump(1.0)
win.grabWindow().save(str(out / "main_drawer.png"))
win.setProperty("width", 900)
pump(1.0)
win.grabWindow().save(str(out / "main_drawer_narrow.png"))
print("warnings2:", "\n".join(warns) or "none")
