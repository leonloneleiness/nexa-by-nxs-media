"""Offscreen: CodePanel.qml + CodeBridge/CodeService thật → chạy thử bản code và một tệp có input, chụp ảnh bảng
(chỉ ảnh render offscreen của QML NEXA, không đụng màn hình thật)."""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402

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


class C:
    config = cfg
    code = CodeService(cfg, notify=lambda k, v: holder["b"].post(k, v) if "b" in holder else None,
                       history_dir=d / "hist")


bridge = CodeBridge(C(), web_preview=WEB)
holder["b"] = bridge
view = QQuickView()
view.rootContext().setContextProperty("nexaCode", bridge)
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.setSource(QUrl.fromLocalFile(str(Path(QML_DIR) / "CodePanel.qml")))
if view.status() != QQuickView.Ready:
    for e in view.errors():
        print("QML:", e.toString())
    sys.exit(1)
view.resize(1180, 760)
view.show()


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def grab(name):
    pump(0.4)
    out = ROOT / "scratch" / name
    view.grabWindow().save(str(out))
    print("saved", out, "view =", view.rootObject().property("view"))


svc = C.code
if WEB:
    h = d / "site"
    h.mkdir()
    (h / "index.html").write_text("<html><head><title>Trang thử</title></head><body style='font-family:Segoe UI'><h1>Xin chào NEXA</h1><script>console.log('đã tải'); nope();</script></body></html>", encoding="utf-8")
    print(svc.run_file(h / "index.html"))
    pump(6)
    grab("run_view_web.png")
    print(svc.live.plain_text())
    sys.exit(0)
code = ("def cong(a, b):\n    return a + b\n\n\ndef tru(a, b):\n    return a - b\n")
test = ("import unittest\nfrom calc import cong, tru\n\n\nclass T(unittest.TestCase):\n"
        "    def test_cong(self):\n        self.assertEqual(cong(2, 3), 5)\n\n"
        "    def test_tru(self):\n        self.assertEqual(tru(5, 3), 3)\n")
res = CodeResult("p1", "máy tính", "Máy tính cộng trừ", "python", "Hai hàm cộng/trừ kèm kiểm thử.",
                 [CodeFile("calc.py", "python", code), CodeFile("test_calc.py", "python", test)])
svc.current = res
svc._store(res)
bridge.post("code_open", {})
bridge.post("code_result", {"id": "p1"})
grab("run_view_code.png")
print(svc.run_tests("p1"))
svc.live.wait(30)
pump(1.5)
grab("run_view_tests.png")
print(bridge.run.get("state"), bridge.run.get("summary"))

f = d / "hoi_ten.py"
f.write_text("import time\nprint('Chương trình chào hỏi')\nfor p in (25, 50, 100):\n"
             "    print(f'\\rĐang tải {p}%', end='', flush=True); time.sleep(0.1)\nprint()\n"
             "ten = input('Nhập tên của anh: ')\nprint('Xin chào', ten)\n", encoding="utf-8")
print(svc.run_file(f))
end = time.time() + 15
while time.time() < end and not svc.live.waiting_input():
    pump(0.1)
pump(0.5)
grab("run_view_input.png")
svc.send_input("Sơn")
svc.live.wait(10)
pump(1.0)
grab("run_view_file_done.png")
view.resize(820, 700)
grab("run_view_narrow.png")
