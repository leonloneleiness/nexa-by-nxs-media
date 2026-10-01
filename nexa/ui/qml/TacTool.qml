import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import "TacStyle.js" as S

// Nút lệnh vát góc: icon (tùy chọn) + chữ in hoa. on = đang bật (nền màu nhạt + vạch sáng dưới), primary = nền màu.
Item {
    id: tb
    property int glyphCode: 0
    property string text: ""
    property string tip: ""
    property color tint: S.ice
    property bool on: false
    property bool primary: false
    property bool small: false
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text || tip
    Accessible.onPressAction: if (enabled) clicked()
    Keys.onSpacePressed: if (enabled) clicked()
    Keys.onReturnPressed: if (enabled) clicked()
    signal clicked()
    readonly property string tacFont: S.tacFont(Qt.fontFamilies())
    readonly property string iconFont: S.iconFont(Qt.fontFamilies())
    readonly property bool hot: tbMouse.containsMouse
    opacity: enabled ? 1 : 0.35
    implicitHeight: small ? 28 : 34
    implicitWidth: tbRow.implicitWidth + (small ? 18 : 24)
    TacFrame {
        anchors.fill: parent; cut: tb.small ? 6 : 8
        fill: tb.primary ? Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, tbMouse.pressed ? 0.5 : tb.hot ? 0.34 : 0.22)
             : tb.on ? Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, 0.18)
             : tbMouse.pressed ? Theme.surfaceDeep : tb.hot ? Theme.surfaceRaised : Theme.surface
        stroke: tb.on || tb.hot || tb.activeFocus ? tb.tint : Theme.border
    }
    Rectangle { visible: tb.on; x: 8; width: tb.width - 22; height: 2
                anchors.bottom: parent.bottom; anchors.bottomMargin: 3; color: tb.tint; opacity: 0.9 }
    Row {
        id: tbRow
        anchors.centerIn: parent
        spacing: 7
        scale: tbMouse.pressed ? 0.95 : 1
        Text { visible: tb.glyphCode > 0; text: S.glyph(tb.glyphCode); font.family: tb.iconFont; font.pixelSize: tb.small ? 12 : 14
               color: tb.primary || tb.on ? "white" : (tb.hot ? tb.tint : Theme.textSecondary)
               anchors.verticalCenter: parent.verticalCenter }
        Text { visible: tb.text.length > 0; text: tb.text; font.family: tb.tacFont; font.pixelSize: tb.small ? 11 : 12
               font.letterSpacing: 0.3; color: tb.primary || tb.on ? "white" : S.textDim
               anchors.verticalCenter: parent.verticalCenter }
    }
    MouseArea { id: tbMouse; anchors.fill: parent; hoverEnabled: true; enabled: tb.enabled; cursorShape: Qt.PointingHandCursor
                onClicked: tb.clicked() }
    ToolTip.visible: tbMouse.containsMouse && tb.tip.length > 0
    ToolTip.delay: 450
    ToolTip.text: tb.tip
}
