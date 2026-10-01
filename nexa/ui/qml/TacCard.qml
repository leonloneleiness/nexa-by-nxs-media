import QtQuick
import "TacStyle.js" as S
import "Theme.js" as Theme

Item {
    id: tp
    property string title: ""
    property string code: ""
    property string sub: ""
    property color accent: S.ice
    property color fillColor: S.fill
    property real cut: 14
    property real headerH: title.length > 0 ? 28 : 0
    property real pad: 10
    default property alias content: tpBody.data
    property alias headerExtra: tpExtra.data
    readonly property string tacFont: Theme.font
    TacFrame { anchors.fill: parent; cut: tp.cut; fill: tp.fillColor; stroke: Theme.border }
    Rectangle { x: 20; y: 0; width: 30; height: 1; color: tp.accent; opacity: 0.65 }
    Row {
        visible: tp.headerH > 0
        x: 10; y: 8; spacing: 9
        Text { text: tp.code; visible: text.length > 0; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 10
               anchors.verticalCenter: parent.verticalCenter }
        Text { text: tp.title.toUpperCase(); color: Theme.textPrimary; font.family: Theme.font; font.pixelSize: 10; font.weight: Font.DemiBold
               font.letterSpacing: 0.6; anchors.verticalCenter: parent.verticalCenter }
        Text { text: tp.sub; visible: text.length > 0; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 10
               anchors.verticalCenter: parent.verticalCenter }
    }
    Row { id: tpExtra; visible: tp.headerH > 0; anchors.right: parent.right; anchors.rightMargin: 12; y: 2; spacing: 6 }
    Rectangle { visible: tp.headerH > 0; x: 16; y: tp.headerH; width: tp.width - 32; height: 1; color: Theme.border; opacity: 0.7 }
    Item {
        id: tpBody
        anchors.fill: parent
        anchors.topMargin: tp.headerH + (tp.headerH > 0 ? 8 : tp.pad)
        anchors.leftMargin: tp.pad; anchors.rightMargin: tp.pad; anchors.bottomMargin: tp.pad
    }
}
