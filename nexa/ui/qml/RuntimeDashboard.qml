import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

TacCard {
    id: root
    title: "API & thư viện"; code: "DEV"
    property var status: ({})
    property var provider: ({})
    property var libraries: []
    ScrollView {
        anchors.fill: parent; clip: true; contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: parent.width; spacing: 10
            Text { text: "DỊCH VỤ & TÍCH HỢP"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1 }
            Repeater {
                model: [
                    {name: "Google Gemini", detail: (root.status.ai && root.status.ai.model) || "Trí tuệ & hội thoại", state: root.status.ai && root.status.ai.ok ? "Sẵn sàng" : "Chưa sẵn sàng", ok: !!(root.status.ai && root.status.ai.ok)},
                    {name: "Giọng nói / TTS", detail: (root.status.tts && root.status.tts.backend) || "Chưa chọn backend", state: root.status.tts && root.status.tts.backend ? "Đang dùng" : "Chờ", ok: !!(root.status.tts && root.status.tts.backend)},
                    {name: "Whisper / STT", detail: (root.status.stt && root.status.stt.model) || "Nhận dạng cục bộ", state: root.status.stt && root.status.stt.ready ? "Đã nạp" : "Chưa nạp", ok: !!(root.status.stt && root.status.stt.ready)},
                    {name: root.provider.name && root.provider.name !== "none" ? root.provider.name : "3D Cloud", detail: "API tạo mô hình 3D", state: root.provider.ok ? "Đã cấu hình" : "Chưa cấu hình", ok: !!root.provider.ok},
                    {name: "Browser Bridge", detail: root.status.bridge && root.status.bridge.browsers ? root.status.bridge.browsers.join(", ") || "Điều khiển trình duyệt" : "Điều khiển trình duyệt", state: root.status.bridge && root.status.bridge.connected ? "Đã kết nối" : "Chưa kết nối", ok: !!(root.status.bridge && root.status.bridge.connected)}
                ]
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; implicitHeight: serviceBody.implicitHeight + 16
                    color: Theme.surfaceDeep; border.color: Theme.border; radius: 3
                    ColumnLayout {
                        id: serviceBody; x: 9; y: 8; width: parent.width - 18; spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 4; height: 4; radius: 2; color: modelData.ok ? Theme.success : Theme.textMuted }
                            Text { Layout.fillWidth: true; text: modelData.name; color: Theme.textPrimary; font.pixelSize: 12; elide: Text.ElideRight; textFormat: Text.PlainText }
                        }
                        Text { Layout.fillWidth: true; text: modelData.detail; color: Theme.textMuted; font.pixelSize: 10; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { text: modelData.state; color: modelData.ok ? Theme.success : Theme.amber; font.pixelSize: 10 }
                    }
                }
            }
            Text { text: "THƯ VIỆN PHÁT TRIỂN"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1; Layout.topMargin: 6 }
            Text { Layout.fillWidth: true; text: "Phiên bản cài trên máy · cuộn để xem tất cả"; color: Theme.textMuted; font.pixelSize: 10; wrapMode: Text.Wrap }
            Repeater {
                model: root.libraries
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: 4
                    RowLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: modelData.name; font.family: Theme.mono; font.pixelSize: 11; color: Theme.textPrimary; elide: Text.ElideRight }
                        Text { text: modelData.version || "Chưa cài"; font.family: Theme.mono; font.pixelSize: 10; color: modelData.installed ? Theme.success : Theme.amber }
                    }
                    Text { Layout.fillWidth: true; text: modelData.purpose; color: Theme.textMuted; font.pixelSize: 10; wrapMode: Text.Wrap }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border; opacity: 0.5; Layout.topMargin: 3 }
                }
            }
        }
    }
}
