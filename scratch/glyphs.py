import os, sys
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["QT_QUICK_BACKEND"]="software"; os.environ["QT_QPA_FONTDIR"]="C:/Windows/Fonts"
from PySide6.QtGui import QGuiApplication, QColor, QFontDatabase
from PySide6.QtQuick import QQuickView
from PySide6.QtCore import QUrl
app=QGuiApplication([])
fam = sys.argv[1]
codes="E713 E720 E722 E767 E8BD E8F2 E72E E785 E71B E7E8 E945 E7BA E73E E71A E711 E708 E943 E774 E753 E712 E700 E8C1 E9D9 E9F5 E950 E7F4 E815 E7C9 EDA4 F158 E809 E99A E8D6 E9CA E1D6 E7B3 E7EF E82D E8D7 EA80 E83F EA8F E7C5 F0E3 E706 E73F E740 E921 E922 E8BB E7AD E9E9 EC4A E88E E80F E8CB".split()
qml = """import QtQuick
Rectangle { width: 900; height: 600; color: "#081226"
 Flow { anchors.fill: parent; anchors.margins: 8; spacing: 6
  Repeater { model: %s
   Column { width: 80; Text { text: String.fromCharCode(parseInt(modelData,16)); font.family: "%s"; font.pixelSize: 30; color: "white"; anchors.horizontalCenter: parent.horizontalCenter }
            Text { text: modelData; color: "#8fb3d1"; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter } } } } }""" % (str(codes), fam)
open("scratch/_g.qml","w").write(qml)
v=QQuickView(); v.setSource(QUrl.fromLocalFile(os.path.abspath("scratch/_g.qml"))); v.show()
for _ in range(10): app.processEvents()
v.grabWindow().save("scratch/glyphs.png"); print(v.errors())
