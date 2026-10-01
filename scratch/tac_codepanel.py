"""Đổi CodePanel.qml sang phong cách chiến thuật (giữ nguyên logic, id, objectName)."""
import re
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "nexa/ui/qml/CodePanel.qml"
s = p.read_text(encoding="utf-8")


def rep(old, new, count=1):
    global s
    assert s.count(old) >= 1, old[:80]
    s = s.replace(old, new) if count == 0 else s.replace(old, new, count)


rep('import QtQuick.Layouts\n', 'import QtQuick.Layouts\nimport "TacStyle.js" as S\n')
rep('''Rectangle {
    id: panel
    signal closeRequested()
    color: "#f20a1428"
    radius: 16
    border.color: "#16325a"
''', '''Item {
    id: panel
    signal closeRequested()
    TacCard { anchors.fill: parent; headerH: 0; cut: 18; fillColor: "#f2040b16" }
    readonly property string tacFont: S.tacFont(Qt.fontFamilies())
''')
rep('readonly property color cyan: "#22d3ee"', 'readonly property color cyan: "#8fd8ff"')
rep('readonly property color dim: "#8fb3d1"', 'readonly property color dim: "#9cc0de"')
rep('readonly property color codeBg: "#282c34"', 'readonly property color codeBg: "#08121e"')
rep('readonly property color termBg: "#0b1020"', 'readonly property color termBg: "#03080f"')

# ---- components ----
a = s.index('    component PButton: Button {')
b = s.index('    component InfoText: TextEdit {')
s = s[:a] + '''    component PButton: Button {
        id: pb
        property color tint: panel.cyan
        font.pixelSize: 12
        font.family: panel.tacFont
        font.letterSpacing: 1.2
        leftPadding: 14; rightPadding: 14; topPadding: 7; bottomPadding: 7
        opacity: enabled ? 1 : 0.4
        contentItem: Text { text: pb.text.toUpperCase(); font: pb.font; color: pb.hovered ? "white" : "#d6eeff"
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
        background: Item {
            TacFrame {
                anchors.fill: parent; cut: 7
                fill: Qt.rgba(pb.tint.r, pb.tint.g, pb.tint.b, pb.down ? 0.34 : pb.hovered ? 0.2 : 0.08)
                stroke: Qt.rgba(pb.tint.r, pb.tint.g, pb.tint.b, pb.hovered ? 0.95 : 0.5)
            }
            Rectangle { x: 7; width: 14; height: 2; y: parent.height - 4; color: pb.tint; opacity: pb.hovered ? 1 : 0.7 }
        }
    }
    component Badge: Item {
        property string text: ""
        property color tone: panel.dim
        implicitHeight: 20; implicitWidth: badgeText.implicitWidth + 16
        TacFrame { anchors.fill: parent; cut: 5; fill: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.1)
                   stroke: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.55) }
        Text { id: badgeText; anchors.centerIn: parent; text: parent.text.toUpperCase(); color: parent.tone
               font.family: panel.tacFont; font.pixelSize: 10; font.letterSpacing: 1 }
    }
''' + s[b:]

a = s.index('    component ViewTab: Rectangle {')
b = s.index('    ColumnLayout {\n        anchors.fill: parent; anchors.margins: 16; spacing: 10')
s = s[:a] + '''    component ViewTab: Item {
        id: vt
        property string key: ""
        property string label: ""
        property color dot: "transparent"
        property bool pulse: false
        property bool showDot: false
        readonly property bool on: panel.view === key
        implicitHeight: 30; implicitWidth: vtRow.implicitWidth + 26
        TacFrame { anchors.fill: parent; cut: 7
                   fill: vt.on ? "#1f8fd8ff" : (vtMa.containsMouse ? "#13283f" : "#0a1828")
                   stroke: vt.on ? panel.cyan : Qt.rgba(0.56, 0.85, 1, 0.25) }
        Rectangle { visible: vt.on; x: 8; width: vt.width - 22; height: 2; anchors.bottom: parent.bottom
                    anchors.bottomMargin: 3; color: panel.cyan }
        MouseArea { id: vtMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: panel.view = vt.key }
        Row {
            id: vtRow; anchors.centerIn: parent; spacing: 7
            Rectangle {
                width: 7; height: 7; rotation: 45; anchors.verticalCenter: parent.verticalCenter
                visible: vt.showDot; color: vt.dot
                SequentialAnimation on opacity {
                    running: vt.pulse; loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 550 } NumberAnimation { to: 1; duration: 550 }
                }
            }
            Text { text: vt.label.toUpperCase(); color: vt.on ? "white" : panel.dim; font.pixelSize: 11
                   font.family: panel.tacFont; font.letterSpacing: 1.3 }
        }
    }

''' + s[b:]
rep('anchors.fill: parent; anchors.margins: 16; spacing: 10', 'anchors.fill: parent; anchors.margins: 18; anchors.topMargin: 14; spacing: 10')

# ---- header ----
rep('''            Text { text: "Sinh code"; color: "white"; font.pixelSize: 20; font.bold: true }''',
    '''            Row {
                spacing: 9
                Text { text: "04"; color: S.amber; font.family: S.mono; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                Text { text: "SINH CODE"; color: "white"; font.family: panel.tacFont; font.pixelSize: 18; font.letterSpacing: 3
                       anchors.verticalCenter: parent.verticalCenter }
                Text { text: "// XƯỞNG CODE"; color: S.iceDim; font.family: S.mono; font.pixelSize: 11
                       anchors.verticalCenter: parent.verticalCenter; visible: !panel.focusRun }
            }''')
rep('''            Button { flat: true; onClicked: panel.closeRequested()
                     contentItem: Text { text: "✕"; color: "white"; font.pixelSize: 14 } background: Item {} }''',
    '''            TacTool { small: true; glyphCode: 0xE711; tint: S.hazard; tip: "Đóng"; onClicked: panel.closeRequested() }''')
# vạch dưới tiêu đề
rep('''        // ---------- yêu cầu ----------''', '''        Rectangle {
            Layout.fillWidth: true; Layout.topMargin: -4; height: 1; color: Qt.rgba(0.56, 0.85, 1, 0.14)
            Row { anchors.right: parent.right; y: -1; spacing: 3
                  Repeater { model: 3; Rectangle { width: 10; height: 3; color: S.amber; opacity: 0.85 } } }
        }
        // ---------- yêu cầu ----------''')

# ô yêu cầu: dấu nhắc ">" cam
rep('''                Layout.fillWidth: true; Layout.preferredHeight: 64
                radius: 10; color: "#081226"; border.color: prompt.activeFocus ? panel.cyan : "#16325a"
                ScrollView {
                    anchors.fill: parent; anchors.margins: 2''',
    '''                Layout.fillWidth: true; Layout.preferredHeight: 68
                color: "transparent"
                TacFrame { anchors.fill: parent; cut: 9; fill: "#e0030a14"
                           stroke: prompt.activeFocus ? S.amber : Qt.rgba(0.56, 0.85, 1, 0.28) }
                Text { x: 12; y: 9; text: ">"; color: S.amber; font.family: S.mono; font.pixelSize: 16; font.bold: true }
                ScrollView {
                    anchors.fill: parent; anchors.margins: 2; anchors.leftMargin: 24''')
rep('''                    background: Rectangle { implicitHeight: 30; radius: 8; color: "#0d2142"
                                            border.color: langBox.activeFocus ? panel.cyan : "#16325a" }''',
    '''                    background: TacFrame { implicitHeight: 30; cut: 7; fill: "#0a1828"
                                           stroke: langBox.activeFocus ? panel.cyan : Qt.rgba(0.56, 0.85, 1, 0.3) }''')
rep('''                    tint: nexaCode.busy ? "#fb7185" : panel.cyan''', '''                    tint: nexaCode.busy ? S.hazard : S.amber''')
rep('''                    Text { text: "Gần đây"; color: panel.dim; font.pixelSize: 12; font.bold: true }''',
    '''                    Row { spacing: 7
                          Text { text: "LOG"; color: S.amber; font.family: S.mono; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                          Text { text: "GẦN ĐÂY"; color: "#d6eeff"; font.family: panel.tacFont; font.pixelSize: 11; font.letterSpacing: 2.5 } }''')
# mục lịch sử: vạch chọn bên trái
rep('''                            MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true''',
    '''                            Rectangle { visible: modelData.id === panel.res.id; width: 2; height: parent.height; color: panel.cyan }
                            MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true''')
rep('''border.color: modelData.id === panel.res.id ? "#2b6cb0" : "transparent"''', '''border.color: "transparent"''')

# terminal
rep('''                                Text { text: panel.view === "web" ? "CONSOLE" : "ĐẦU RA"; color: panel.dim; font.pixelSize: 10
                                       font.bold: true; font.letterSpacing: 1.5 }''',
    '''                                Text { text: ">_"; color: S.amber; font.family: S.mono; font.pixelSize: 12; font.bold: true }
                                Text { text: panel.view === "web" ? "CONSOLE" : "ĐẦU RA"; color: "#d6eeff"; font.pixelSize: 11
                                       font.family: panel.tacFont; font.letterSpacing: 2.5 }''')
rep('''Text { text: "›"; color: panel.run.waitingInput ? "#fbbf24" : panel.cyan; font.pixelSize: 18; font.bold: true }''',
    '''Text { text: ">"; color: S.amber; font.family: S.mono; font.pixelSize: 16; font.bold: true }''')
rep('''                            text: "$ " + (panel.run.command || ""); color: "#6b8bab"''', '''                            text: "> " + (panel.run.command || ""); color: "#6b8bab"''')
rep('''                    Text { text: res.title || ""; color: "white"; font.pixelSize: 16; font.bold: true''',
    '''                    Text { text: (res.title || "").toUpperCase(); color: "white"; font.pixelSize: 15; font.family: panel.tacFont; font.letterSpacing: 1.5''')
rep('''                            Text { text: panel.run.title || ""; color: "white"; font.pixelSize: 15; font.bold: true''',
    '''                            Text { text: (panel.run.title || "").toUpperCase(); color: "white"; font.pixelSize: 14; font.family: panel.tacFont; font.letterSpacing: 1.5''')
rep('''                                    Text { text: (panel.run.stateLabel || "").toUpperCase(); color: panel.runTone
                                           font.pixelSize: 11; font.bold: true; font.letterSpacing: 1 }''',
    '''                                    Text { text: (panel.run.stateLabel || "").toUpperCase(); color: panel.runTone
                                           font.pixelSize: 11; font.family: panel.tacFont; font.letterSpacing: 2 }''')
# khung code: vạch gutter
rep('''                                color: "#21252b"
''', '''                                color: "#050c16"
                                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Qt.rgba(0.56, 0.85, 1, 0.16) }
''')

# ---- màu ----
for old, new in [("#16325a", "#1d3650"), ("#081226", "#050d18"), ("#0d2142", "#0a1828"), ("#12305a", "#13283f"),
                 ("#34d399", "#4ade9a"), ("#fb7185", "#ff5a4f"), ("#fbbf24", "#ffae42"), ("#a78bfa", "#b89cff"),
                 ("#60a5fa", "#6fb6ff"), ("#5b7a99", "#4f6f8c"), ("#0f1629", "#071321"), ("#1c2a44", "#1a3048"),
                 ("#0f1b30", "#071321"), ("#0d1526", "#050d18"), ("#1e293b", "#122539")]:
    s = s.replace(old, new)
# bo góc lớn → góc vuông (giữ chấm tròn nhỏ radius ≤ 5)
s = re.sub(r"radius: (6|7|8|9|10|11|12|13)\b", "radius: 1", s)
p.write_text(s, encoding="utf-8")
print("ok", len(s))
