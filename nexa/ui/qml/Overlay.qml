import "Theme.js" as Theme
// Overlay trong suốt của một màn hình (click-through, không nhận focus).
// Python gọi các hàm dưới đây với tọa độ logic cục bộ của màn hình này.
import QtQuick
import QtQuick.Shapes

Item {
    id: root
    width: 800; height: 600

    readonly property color cyan: Theme.accent
    readonly property color purple: Theme.silver

    function ripple(x, y) { rippleC.createObject(root, { cx: x, cy: y }) }
    function highlight(x, y, w, h, text, kind) { highlightC.createObject(root, { rx: x, ry: y, rw: w, rh: h, label: text, kind: kind }) }
    function sweep(direction, text) { sweepC.createObject(root, { direction: direction, label: text }) }
    function mediaIcon(state, text) { mediaC.createObject(root, { mstate: state, label: text }) }
    function toast(text, isError) { toastC.createObject(root, { label: text, isError: isError }) }
    function identify(title, subtitle, role) { identifyC.createObject(root, { title: title, subtitle: subtitle, role: role }) }

    Component {
        id: rippleC
        Item {
            id: rp
            property real cx; property real cy
            x: cx - 60; y: cy - 60; width: 120; height: 120
            Repeater {
                model: 2
                Rectangle {
                    anchors.centerIn: parent
                    width: 16; height: 16; radius: width / 2
                    color: "transparent"; border.color: root.cyan; border.width: 3
                    SequentialAnimation on width {
                        PauseAnimation { duration: index * 140 }
                        NumberAnimation { from: 16; to: 110; duration: 650; easing.type: Easing.OutCubic }
                    }
                    SequentialAnimation on opacity {
                        PauseAnimation { duration: index * 140 }
                        NumberAnimation { from: 1; to: 0; duration: 650 }
                    }
                }
            }
            Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: "white"
                        NumberAnimation on opacity { from: 1; to: 0; duration: 700 } }
            Timer { interval: 1000; running: true; onTriggered: rp.destroy() }
        }
    }

    Component {
        id: highlightC
        Item {
            id: hl
            property real rx; property real ry; property real rw; property real rh
            property string label: ""
            property string kind: "highlight"
            anchors.fill: parent
            Rectangle {
                x: hl.rx; y: hl.ry; width: hl.rw; height: hl.rh
                color: "transparent"; radius: 8
                border.width: 3
                border.color: hl.kind === "minimize" ? root.purple : root.cyan
                SequentialAnimation on opacity {
                    NumberAnimation { from: 0; to: 1; duration: 180 }
                    PauseAnimation { duration: 900 }
                    NumberAnimation { to: 0; duration: 500 }
                }
            }
            Rectangle {
                visible: hl.label.length > 0
                x: Math.max(8, Math.min(root.width - width - 8, hl.rx + 12))
                y: Math.max(8, Math.min(root.height - height - 8, hl.ry + 12))
                width: lbl.implicitWidth + 28; height: 36; radius: 18
                color: Theme.panelGlass; border.color: root.cyan; border.width: 1
                Text {
                    id: lbl; anchors.centerIn: parent; color: "white"; font.pixelSize: 15
                    text: (hl.kind === "minimize" ? "⬇  " : hl.kind === "restore" ? "⬆  " : hl.kind === "arrive" ? "➜  " : "") + hl.label
                }
                SequentialAnimation on opacity { PauseAnimation { duration: 1200 } NumberAnimation { to: 0; duration: 400 } }
            }
            Timer { interval: 1800; running: true; onTriggered: hl.destroy() }
        }
    }

    Component {
        id: sweepC
        Item {
            id: sw
            property string direction: "right"
            property string label: ""
            anchors.fill: parent
            readonly property bool horizontal: direction === "right" || direction === "left"
            Rectangle {
                id: bar
                width: sw.horizontal ? root.width * 0.35 : 14
                height: sw.horizontal ? 14 : root.height * 0.35
                radius: 7
                gradient: Gradient {
                    orientation: sw.horizontal ? Gradient.Horizontal : Gradient.Vertical
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: root.cyan }
                }
                rotation: sw.direction === "left" || sw.direction === "up" ? 180 : 0
                y: sw.horizontal ? root.height / 2 - height / 2 : 0
                x: sw.horizontal ? 0 : root.width / 2 - width / 2
                NumberAnimation on x { running: sw.horizontal; from: sw.direction === "right" ? -bar.width : root.width;
                                       to: sw.direction === "right" ? root.width : -bar.width; duration: 700; easing.type: Easing.InOutCubic }
                NumberAnimation on y { running: !sw.horizontal; from: sw.direction === "down" ? -bar.height : root.height;
                                       to: sw.direction === "down" ? root.height : -bar.height; duration: 700; easing.type: Easing.InOutCubic }
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.12
                width: sl.implicitWidth + 36; height: 44; radius: 22; color: Theme.panelGlass; border.color: root.cyan
                Text { id: sl; anchors.centerIn: parent; text: sw.label; color: "white"; font.pixelSize: 17 }
                SequentialAnimation on opacity { PauseAnimation { duration: 900 } NumberAnimation { to: 0; duration: 400 } }
            }
            Timer { interval: 1400; running: true; onTriggered: sw.destroy() }
        }
    }

    Component {
        id: mediaC
        Item {
            id: md
            property string mstate: "paused"
            property string label: ""
            anchors.fill: parent
            Rectangle {
                id: disc
                anchors.centerIn: parent
                width: 150; height: 150; radius: 75
                color: "#cc050b18"
                border.width: 3; border.color: md.mstate === "error" ? Theme.danger : root.cyan
                Row {
                    visible: md.mstate === "paused"
                    anchors.centerIn: parent; spacing: 16
                    Rectangle { width: 18; height: 60; radius: 4; color: "white" }
                    Rectangle { width: 18; height: 60; radius: 4; color: "white" }
                }
                Shape {
                    visible: md.mstate === "playing"
                    anchors.centerIn: parent; width: 60; height: 64
                    ShapePath { fillColor: "white"; strokeWidth: -1
                        startX: 8; startY: 0
                        PathLine { x: 60; y: 32 } PathLine { x: 8; y: 64 } PathLine { x: 8; y: 0 } }
                }
                Text { visible: md.mstate === "error"; anchors.centerIn: parent; text: "!"; color: Theme.danger; font.pixelSize: 64; font.bold: true }
                NumberAnimation on scale { from: 0.6; to: 1; duration: 260; easing.type: Easing.OutBack }
                SequentialAnimation on opacity { PauseAnimation { duration: 900 } NumberAnimation { to: 0; duration: 400 } }
            }
            Text {
                anchors.top: disc.bottom; anchors.topMargin: 12; anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(root.width * 0.6, 640); horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                text: md.label; color: "white"; font.pixelSize: 16; style: Text.Outline; styleColor: Theme.surface
                SequentialAnimation on opacity { PauseAnimation { duration: 1000 } NumberAnimation { to: 0; duration: 400 } }
            }
            Timer { interval: 1500; running: true; onTriggered: md.destroy() }
        }
    }

    Component {
        id: toastC
        Rectangle {
            id: ts
            property string label: ""
            property bool isError: false
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - height - 90
            width: Math.min(parent.width * 0.7, tt.implicitWidth + 40); height: tt.implicitHeight + 22; radius: 14
            color: Theme.panelGlass; border.color: isError ? Theme.danger : root.cyan; border.width: 1.5
            Text { id: tt; anchors.centerIn: parent; width: Math.min(root.width * 0.7 - 40, implicitWidth)
                   text: ts.label; color: "white"; font.pixelSize: 15; wrapMode: Text.WordWrap }
            SequentialAnimation on opacity { NumberAnimation { from: 0; to: 1; duration: 150 } PauseAnimation { duration: 2000 } NumberAnimation { to: 0; duration: 350 } }
            Timer { interval: 2600; running: true; onTriggered: ts.destroy() }
        }
    }

    Component {
        id: identifyC
        Rectangle {
            id: idc
            property string title: ""
            property string subtitle: ""
            property string role: ""
            anchors.centerIn: parent
            width: Math.max(420, sub.implicitWidth + 60); height: 250; radius: 24
            color: Theme.panelGlass; border.color: role.length ? root.cyan : Theme.textMuted; border.width: 3
            Column {
                anchors.centerIn: parent; spacing: 8
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: idc.role.length ? idc.role : "Chưa gán vai trò"
                       color: idc.role.length ? root.cyan : "#94a3b8"; font.pixelSize: 26; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: idc.title; color: "white"; font.pixelSize: 64; font.bold: true }
                Text { id: sub; anchors.horizontalCenter: parent.horizontalCenter; text: idc.subtitle; color: "#cbd5e1"; font.pixelSize: 18 }
            }
            SequentialAnimation on opacity { NumberAnimation { from: 0; to: 1; duration: 200 } PauseAnimation { duration: 3600 } NumberAnimation { to: 0; duration: 400 } }
            Timer { interval: 4300; running: true; onTriggered: idc.destroy() }
        }
    }
}
