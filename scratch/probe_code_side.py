"""Offscreen: Main.qml + CodeBridge thật → bảng Sinh code nằm cột phải cạnh NEXA (như trình xem 3D); đo cỡ vùng kết quả."""
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

from PySide6.QtCore import Property, QObject, Signal  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

WEB = "--web" in sys.argv
if WEB:
    from PySide6.QtWebEngineQuick import QtWebEngineQuick
    QtWebEngineQuick.initialize()
app = QGuiApplication([])

from nexa.code.models import CodeFile, CodeResult  # noqa: E402
from nexa.code.service import CodeService  # noqa: E402
from nexa.ui.code_bridge import CodeBridge  # noqa: E402
from nexa.utils.config import QML_DIR, Config  # noqa: E402

d = Path(tempfile.mkdtemp())
cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
holder = {}


sig = Signal()
attrs = {"changed": sig, "toast": Signal(str, bool), "raiseWindow": Signal()}
VALS = {"compact": (bool, False), "showFps": (bool, False), "smokeOpen": (str, ""), "state": (str, "STANDBY"),
        "stateLabel": (str, "Đang chờ"), "stateDetail": (str, ""), "heardText": (str, ""), "effects": (str, "reduced"),
        "foreground": (str, ""), "statusText": (str, ""), "status": ("QVariantMap", {}),
        "confirmation": ("QVariantMap", {"active": False}), "messages": ("QVariantList",
        [{"role": "user", "source": "voice", "time": "17:00", "text": "tạo đoạn code html cơ bản cho tôi"},
         {"role": "nexa", "source": "", "time": "17:00", "text": "Em đang viết code cho “tạo đoạn code html cơ bản”…"}]),
        "tasks": ("QVariantList", []), "micLevel": (float, 0.0), "outLevel": (float, 0.0), "cameraOn": (bool, "--gest" in sys.argv),
        "listeningSpeech": (bool, False), "controlPaused": (bool, False), "visionSending": (bool, False),
        "viewerOpen": (bool, False), "workspace": (bool, False), "activeJob": ("QVariantMap", {})}
for k, (t, v) in VALS.items():
    attrs[k] = Property(t, (lambda v: lambda self: v)(v), notify=sig)
Fake = type("FakeNexa", (QObject,), attrs)


class C:
    config = cfg
    code = CodeService(cfg, notify=lambda k, v: holder["b"].post(k, v) if "b" in holder else None,
                       history_dir=d / "hist")


bridge = CodeBridge(C(), web_preview=WEB)
holder["b"] = bridge
eng = QQmlApplicationEngine()
eng.warnings.connect(lambda ws: [print("QML WARN", w.toString()) for w in ws])
fn, f3 = Fake(), Fake()
eng.rootContext().setContextProperty("nexa", fn)
eng.rootContext().setContextProperty("nexa3d", f3)
eng.rootContext().setContextProperty("nexaCode", bridge)
eng.load(str(QML_DIR / "Main.qml"))
win = eng.rootObjects()[0]


def pump(t):
    end = time.monotonic() + t
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


svc = C.code
res = CodeResult("p1", "html", "Trang HTML5 Cơ Bản", "python", "Trang HTML kèm kiểm thử.",
                 [CodeFile("main.py", "python", "for i in range(40):\n    print('Dòng kết quả số', i)\n")])
svc.current = res
svc._store(res)
bridge.openPanel()
bridge.post("code_result", {"id": "p1"})
pump(0.5)
svc.run_tests("p1")
svc.live.wait(20)
pump(1.0)
if WEB:
    h = d / "site"
    h.mkdir()
    (h / "index.html").write_text("<html><head><title>Trang thử</title></head><body style='font-family:Segoe UI;background:#eef'><h1>Xin chào NEXA</h1><p>Trang HTML chạy thử.</p><script>console.log('đã tải')</script></body></html>", encoding="utf-8")
    svc.run_file(h / "index.html")
    pump(4)
if "--snap" in sys.argv:
    cp = win.findChild(QQuickItem, "codePanel").property("item")
    svc.SNAP_DEBOUNCE_S = 0.0
    res.files[0].content = "import time\nfor i in range(100):\n    print('dòng', i, flush=True)\n    time.sleep(0.1)\n"
    cp.setProperty("view", "code")
    pump(0.3)
    print("start view", cp.property("view"), "svc", svc.panel_view)
    print("snap 1:", svc.gesture_run())
    pump(1.5)
    print("  view", cp.property("view"), "svc", svc.panel_view, "running", svc.live.running)
    print("snap 2:", svc.gesture_run())
    pump(1.0)
    print("  view", cp.property("view"), "svc", svc.panel_view, "running", svc.live.running)
    win.grabWindow().save(str(ROOT / "scratch" / "snap_back.png"))
    print("snap 3:", svc.gesture_run())
    pump(1.0)
    print("  view", cp.property("view"), "svc", svc.panel_view, "running", svc.live.running)
    svc.stop_run()
    pump(0.5)
    sys.exit(0)
if "--gest" in sys.argv:
    win.setProperty("visibility", 2)
    win.setProperty("width", 1536)
    win.setProperty("height", 824)
    pump(0.5)
    tf = win.findChild(QQuickItem, "termFlick")
    tf.setProperty("contentY", 0)
    pump(0.2)
    y0 = tf.property("contentY")
    for _ in range(10):
        bridge.post("code_gesture", {"kind": "scroll", "dy": 30.0})
    bridge.post("code_gesture", {"kind": "hud", "state": "FIST_HOLD", "label": "✊ Giữ yên nắm tay để lưu…", "progress": 0.6})
    pump(0.4)
    print("run view: termFlick contentY", y0, "->", tf.property("contentY"))
    win.grabWindow().save(str(ROOT / "scratch" / "gest_run.png"))
    cp = win.findChild(QQuickItem, "codePanel").property("item")
    cp.setProperty("view", "code")
    res.files[0].content = "".join(f"print('dòng {i}')\n" for i in range(120))
    bridge.post("code_result", {"id": "p1"})
    pump(0.5)
    cp.setProperty("view", "code")
    pump(0.3)
    cf = win.findChild(QQuickItem, "codeFlick")
    for _ in range(10):
        bridge.post("code_gesture", {"kind": "scroll", "dy": 40.0})
    bridge.post("code_gesture", {"kind": "hud", "state": "SCROLLING", "label": "✌ Đang cuộn ↓", "progress": 0})
    pump(0.4)
    print("code view: codeFlick contentY", cf.property("contentY"), "contentH", cf.property("contentHeight"))
    for _ in range(30):
        bridge.post("code_gesture", {"kind": "scroll", "dy": -60.0})
    bridge.post("code_gesture", {"kind": "hud", "state": "IDLE", "label": "", "progress": 0})
    pump(0.4)
    print("after scroll up: codeFlick contentY", cf.property("contentY"))
    win.grabWindow().save(str(ROOT / "scratch" / "gest_code.png"))
    chip = win.findChild(QQuickItem, "gestureChip")
    print("chip", chip.isVisible(), f"{chip.width():.0f}x{chip.height():.0f}")
    sys.exit(0)
for w, h in ((1536, 824), (1280, 680), (1920, 1150)):
    win.setProperty("visibility", 2)
    win.setProperty("width", w)
    win.setProperty("height", h)
    pump(0.6)
    grid = win.findChild(QQuickItem, "mainGrid")
    cp = win.findChild(QQuickItem, "codePanel")
    term = win.findChild(QQuickItem, "runTerm")
    print("   terminal", f"{term.width():.0f}x{term.height():.0f}")
    wb = win.findChild(QQuickItem, "webBox")
    if WEB and wb:
        print("   web", f"{wb.width():.0f}x{wb.height():.0f}")
    print(f"win {w}x{h}: NEXA col {grid.width():.0f}  code panel {cp.width():.0f}x{cp.height():.0f}  stacked {win.property('stacked')}")
    win.grabWindow().save(str(ROOT / "scratch" / f"side_{w}{'_web' if WEB else ''}.png"))
bridge.closePanel()
pump(0.4)
print("after close: codeShown", win.property("codeShown"), "grid", win.findChild(QQuickItem, "mainGrid").width())
