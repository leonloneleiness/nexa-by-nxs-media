import QtQuick
import "Theme.js" as Theme
Item {
    id: root
    property string label: ""
    property string value: ""
    property color tint: Theme.accent
    property bool dot: true
    implicitHeight: 21; implicitWidth: 160
    Rectangle { visible: root.dot; x: 0; anchors.verticalCenter: parent.verticalCenter; width: 5; height: 5; radius: 3; color: root.tint; opacity: 0.7 }
    Text { anchors.left: parent.left; anchors.leftMargin: root.dot ? 11 : 0; anchors.right: valueText.left; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; text: root.label; color: Theme.textSecondary; font.pixelSize: 10; elide: Text.ElideRight }
    Text { id: valueText; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: Math.min(implicitWidth, Math.max(40, root.width * 0.54)); text: root.value; color: root.tint; font.family: Theme.mono; font.pixelSize: 10; elide: Text.ElideRight; textFormat: Text.PlainText }
}
