import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Button {
    id: card
    property string label: ""
    property string imageUrl: ""
    property string hint: ""
    signal removeRequested()
    implicitWidth: 130
    implicitHeight: 126
    padding: 0
    hoverEnabled: true
    Accessible.name: (imageUrl ? "Thay ảnh " : "Thêm ảnh ") + label
    ToolTip.visible: hovered
    ToolTip.text: imageUrl ? "Bấm để thay ảnh · " + hint : hint
    background: Rectangle {
        radius: 10
        color: card.hovered ? Theme.surfaceRaised : Theme.surface
        border.color: card.activeFocus || card.hovered ? Theme.textSecondary : Theme.border
        border.width: 1
    }
    contentItem: Item {
        Rectangle {
            x: 7; y: 7; width: parent.width - 14; height: parent.height - 39
            radius: 6; color: card.imageUrl ? "#e7edef" : Theme.surfaceDeep
            Image {
                id: preview
                anchors.fill: parent; anchors.margins: 4
                source: card.imageUrl; fillMode: Image.PreserveAspectFit
                asynchronous: true; sourceSize.width: 384; sourceSize.height: 256
            }
            Column {
                anchors.centerIn: parent; spacing: 3
                visible: !card.imageUrl || preview.status === Image.Error
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: preview.status === Image.Error ? "!" : "+"
                    color: Theme.textSecondary; font.pixelSize: 26; font.weight: Font.Light }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: preview.status === Image.Error ? "Chọn lại ảnh" : "Thêm ảnh"
                    color: Theme.textMuted; font.pixelSize: 10 }
            }
        }
        Text {
            x: 10; anchors.bottom: parent.bottom; anchors.bottomMargin: 10
            text: card.label; color: Theme.textPrimary; font.pixelSize: 12; font.weight: Font.Medium
        }
        Rectangle {
            visible: !!card.imageUrl
            width: 5; height: 5; radius: 3; color: "#65d5b0"
            anchors.right: parent.right; anchors.rightMargin: 12
            anchors.bottom: parent.bottom; anchors.bottomMargin: 15
        }
    }
    Button {
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 9
        width: 24; height: 24; visible: !!card.imageUrl
        Accessible.name: "Xóa ảnh " + card.label
        ToolTip.visible: hovered; ToolTip.text: "Xóa ảnh"
        background: Rectangle { radius: 12; color: parent.hovered ? "#af4052" : "#d9081822" }
        contentItem: Text { text: "×"; color: "white"; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        onClicked: card.removeRequested()
    }
}
