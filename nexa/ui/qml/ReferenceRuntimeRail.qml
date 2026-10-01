import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme
ColumnLayout {
    id: root
    property var status: ({})
    property var provider: ({})
    property var libraries: []
    signal voice()
    signal code()
    signal models()
    signal stop()
    signal settings()
    spacing: 8
    component Action: Button {
        id: action
        Layout.fillWidth: true; implicitHeight: 30
        font.pixelSize: 10
        contentItem: Text { text: action.text; font: action.font; color: Theme.textSecondary; verticalAlignment: Text.AlignVCenter; leftPadding: 8; elide: Text.ElideRight }
        background: Rectangle { color: action.hovered ? Theme.surfaceRaised : "#091f2d"; border.color: action.hovered ? Theme.accent : Theme.border; radius: 2 }
    }
    TacCard {
        title: "Thao tác nhanh"; Layout.fillWidth: true; Layout.preferredHeight: 146
        ColumnLayout { anchors.fill: parent; spacing: 5
            Action { text: "◈   LỆNH GIỌNG NÓI"; onClicked: root.voice() }
            Action { text: "◇   KHÔNG GIAN 3D"; onClicked: root.models() }
            Action { text: "⌘   VIẾT MÃ / CODE"; onClicked: root.code() }
        }
    }
    TacCard {
        title: "API / dịch vụ AI"; Layout.fillWidth: true; Layout.preferredHeight: 214
        ColumnLayout {
            anchors.fill: parent; spacing: 4
            Repeater {
                model: [
                    {name:"Google Gemini",detail:(root.status.ai && root.status.ai.model)||"Hội thoại & suy luận",ok:!!(root.status.ai && root.status.ai.ok)},
                    {name:"Whisper",detail:(root.status.stt && root.status.stt.model)||"Nhận dạng cục bộ",ok:!!(root.status.stt && root.status.stt.ready)},
                    {name:"TTS / Giọng nói",detail:(root.status.tts && root.status.tts.backend)||"Chưa chọn backend",ok:!!(root.status.tts && root.status.tts.backend)},
                    {name:root.provider.name && root.provider.name!=="none" ? root.provider.name : "3D Cloud",detail:root.provider.ok ? "Đã cấu hình" : "Chưa cấu hình",ok:!!root.provider.ok}
                ]
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; Layout.fillHeight: true; color: modelData.ok ? "#0a2638" : "#081c29"; border.color: Theme.border; radius: 2
                    Rectangle { x: 0; y: 4; width: 2; height: parent.height-8; color: modelData.ok ? Theme.accent : Theme.amber; opacity: 0.65 }
                    Column { x: 10; anchors.verticalCenter: parent.verticalCenter; width: parent.width-20; spacing: 1
                        Text { width: parent.width; text: modelData.name; color: Theme.textPrimary; font.pixelSize: 11; elide: Text.ElideRight }
                        Text { width: parent.width; text: modelData.detail; color: Theme.textMuted; font.pixelSize: 9; elide: Text.ElideRight; textFormat: Text.PlainText }
                    }
                }
            }
        }
    }
    TacCard {
        title: "Thư viện phát triển"; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 150
        ListView {
            anchors.fill: parent; clip: true; model: root.libraries; spacing: 4
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: Item {
                required property var modelData
                width: ListView.view.width - 8; height: 34
                HudInfoRow { width: parent.width; label: modelData.name; value: modelData.version || "Chưa cài"; tint: modelData.installed ? Theme.accent : Theme.amber }
                Text { y: 21; x: 11; width: parent.width-11; text: modelData.purpose; color: Theme.textMuted; font.pixelSize: 9; elide: Text.ElideRight }
            }
        }
    }
    Text { text: "EMERGENCY / AN TOÀN"; color: Theme.danger; font.pixelSize: 9; font.letterSpacing: 1; Layout.topMargin: 5 }
    Button {
        id: emergency; text: "□   DỪNG KHẨN CẤP"; Layout.fillWidth: true; implicitHeight: 36
        contentItem: Text { text: emergency.text; color: "#ffc0c9"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 3; color: emergency.hovered ? "#541824" : "#300f1b"; border.color: "#8b3449" }
        onClicked: root.stop()
    }
    Action { text: "◇   CẤU HÌNH ĐIỀU KHIỂN"; onClicked: root.settings() }
}
