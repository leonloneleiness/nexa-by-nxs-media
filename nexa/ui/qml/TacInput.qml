import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "TacStyle.js" as S

// Dòng lệnh vát góc: "> ô nhập". Viền chuyển cam khi đang gõ.
Item {
    id: ti
    property string prefix: ">"
    property real cornerRadius: Theme.radius
    property color accent: S.ice
    property alias text: tiField.text
    property alias placeholderText: tiField.placeholderText
    property alias field: tiField
    default property alias trailing: tiRow.data
    signal accepted()
    implicitHeight: 38
    TacFrame { anchors.fill: parent; cut: 8; radius: ti.cornerRadius; fill: S.fillDeep
               stroke: tiField.activeFocus ? ti.accent : Qt.rgba(0.56, 0.85, 1, 0.28) }
    RowLayout {
        id: tiRow
        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 4; spacing: 6
        Text { text: ti.prefix; color: ti.accent; font.family: S.mono; font.pixelSize: 16; font.bold: true }
        TextField {
            id: tiField
            objectName: "sentinelInputField"
            Layout.fillWidth: true
            color: "white"; font.family: Theme.font; font.pixelSize: 14
            placeholderTextColor: Theme.textMuted
            leftPadding: 0
            selectionColor: Theme.borderStrong; selectedTextColor: Theme.textPrimary
            background: Item {}
            onAccepted: ti.accepted()
        }
    }
}
