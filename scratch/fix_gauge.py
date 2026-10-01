from pathlib import Path
p = Path("nexa/ui/qml/Main.qml"); s = p.read_text(encoding="utf-8")
a = s.index("                        // đồng hồ mức vào (mic)")
b = s.index("                        Text {\n                            visible: nexa.showFps")
new = '''                        // đồng hồ mức vào (mic) / ra (giọng NEXA) hai bên lõi
                        LevelGauge { k: "MIC"; v: nexa.micLevel; c: win.ice
                                     x: Math.max(4, mainOrb.x - 34) }
                        LevelGauge { k: "OUT"; v: nexa.outLevel; c: win.amber
                                     x: Math.min(coreArea.width - 26, mainOrb.x + mainOrb.width + 12) }
'''
s = s[:a] + new + s[b:]
comp = '''    // Đồng hồ mức dọc cạnh lõi radar
    component LevelGauge: Column {
        id: lg
        property string k: ""
        property real v: 0
        property color c: win.ice
        visible: !stage.tight
        spacing: 4
        anchors.verticalCenter: parent.verticalCenter
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: lg.k; color: win.iceDim
               font.family: win.tacFont; font.pixelSize: 10; font.letterSpacing: 2 }
        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 6; height: 96
            Rectangle { anchors.fill: parent; color: "#0d1f33"; border.color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2) }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width
                        height: parent.height * Math.max(0, Math.min(1, lg.v)); color: lg.c
                        Behavior on height { NumberAnimation { duration: 90 } } }
        }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: Math.round(lg.v * 100)
               color: "#7fa3c0"; font.family: win.monoFont; font.pixelSize: 10 }
    }
'''
s = s.replace("    component DarkMenuItem: MenuItem {", comp + "    component DarkMenuItem: MenuItem {", 1)
p.write_text(s, encoding="utf-8")
