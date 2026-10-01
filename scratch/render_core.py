import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen:size=1920x1200"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
from pathlib import Path
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa
app = QGuiApplication([]); app.setFont(QFont("Segoe UI", 10))
qml = Path("nexa/ui/qml").resolve()
src = f'''import QtQuick
import QtQuick.Controls
import "file:///{qml.as_posix()}"
ApplicationWindow {{ width: 1400; height: 480; visible: true; color: "#03080f"
  Row {{ Repeater {{ model: ["STANDBY","LISTENING","THINKING","SPEAKING"]
     TacticalCore {{ required property string modelData; width: 350; height: 470; appState: modelData; micLevel: 0.6; outLevel: 0.6
                    outBands: [0.9,0.7,0.6,0.5,0.4,0.3,0.2,0.1] }} }} }} }}'''
p = Path("scratch/core_test.qml"); p.write_text(src, encoding="utf-8")
eng = QQmlApplicationEngine(); w=[]
eng.warnings.connect(lambda ws: w.extend(x.toString() for x in ws))
eng.load(str(p.resolve()))
win = eng.rootObjects()[0]
end = time.monotonic() + 2.5
while time.monotonic() < end: app.processEvents(); time.sleep(0.016)
win.grabWindow().save("scratch/core.png"); print("warn:", w)
