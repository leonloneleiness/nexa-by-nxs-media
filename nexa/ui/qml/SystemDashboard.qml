import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

TacCard {
    id: root
    title: "Hệ thống máy"; code: "SYS"
    property var st: ({})
    property var status: ({})
    readonly property bool hasData: st.cpu !== undefined
    readonly property bool hasGpu: st.gpu !== null && st.gpu !== undefined
    readonly property var channels: [!!(status.ai && status.ai.ok), !!(status.stt && status.stt.ready), !!(status.mic && status.mic.ok), !!(status.tts && status.tts.backend)]
    readonly property int readyCount: channels.filter(function(v) { return v }).length
    function pct(v) { return v === undefined || v === null ? "—" : Math.round(v) + "%" }
    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: parent.width; spacing: 14
            Repeater {
                model: [
                    {name: "CPU", value: root.st.cpu, detail: "Tải bộ xử lý"},
                    {name: "GPU", value: root.st.gpu, detail: root.hasGpu ? "VRAM  " + root.pct(root.st.vram) : "Không có số liệu GPU"},
                    {name: "RAM", value: root.st.ram, detail: "Bộ nhớ đang sử dụng"},
                    {name: "ROM / Ổ ĐĨA", value: root.st.disk, detail: root.st.disk_free_gb !== undefined && root.st.disk_free_gb !== null ? root.st.disk_path + "  ·  Còn " + root.st.disk_free_gb + " / " + root.st.disk_total_gb + " GB" : root.st.disk === null ? "Không đọc được ổ đĩa" : "Đang đọc dung lượng"}
                ]
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: 5
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: modelData.name; font.family: Theme.mono; font.pixelSize: 11; color: Theme.textSecondary; Layout.fillWidth: true }
                        Text { text: root.pct(modelData.value); font.family: Theme.mono; font.pixelSize: 22; color: Theme.textPrimary }
                    }
                    Rectangle {
                        Layout.fillWidth: true; height: 4; color: Theme.surfaceRaised
                        Rectangle { width: parent.width * Math.max(0, Math.min(1, (modelData.value || 0)/100)); height: 4; color: Theme.loadColor((modelData.value || 0)/100)
                            Behavior on width { NumberAnimation { duration: 500 } } }
                    }
                    Text { Layout.fillWidth: true; text: modelData.detail; font.pixelSize: 10; color: Theme.textMuted; wrapMode: Text.Wrap }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 7
                Text { text: "SỨC MẠNH NEXA"; color: Theme.accent; font.pixelSize: 11; font.letterSpacing: 1 }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: root.readyCount + " / 4"; font.family: Theme.mono; font.pixelSize: 28; color: Theme.textPrimary }
                    Text { text: "kênh sẵn sàng"; color: Theme.textSecondary; font.pixelSize: 11 }
                }
                Text { Layout.fillWidth: true; text: "AI · Nhận dạng · Mic · Giọng nói"; color: Theme.textMuted; font.pixelSize: 10; wrapMode: Text.Wrap }
                Row {
                    spacing: 5
                    Repeater { model: root.channels
                        Rectangle { required property var modelData; width: 38; height: 4; color: modelData ? Theme.accent : Theme.surfaceRaised } }
                }
                Text { Layout.fillWidth: true; text: (root.status.ai && root.status.ai.model) || "AI chưa có thông tin model"; color: Theme.textSecondary; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                Text { text: "Phản hồi AI  " + (root.st.ai_ms ? Math.round(root.st.ai_ms) + " ms" : "—"); color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 10 }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Text { text: "PIN MÁY TÍNH"; color: Theme.textSecondary; font.pixelSize: 11 }
                    Text { text: root.st.battery === undefined ? "Đang đọc" : root.st.battery === null ? "Không có dữ liệu pin" : root.st.charging ? "Đang cắm sạc" : "Đang dùng pin"; color: Theme.textMuted; font.pixelSize: 10 }
                }
                Text { text: root.pct(root.st.battery); color: root.st.battery !== null && root.st.battery < 20 ? Theme.amber : Theme.success; font.pixelSize: 22; font.family: Theme.mono }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 5
                readonly property var wifi: root.st.wifi || ({})
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "WI-FI"; color: Theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true }
                    Text { text: root.pct(parent.parent.wifi.signal); color: Theme.accent; font.pixelSize: 22; font.family: Theme.mono }
                }
                Text { Layout.fillWidth: true; text: parent.wifi.connected ? (parent.wifi.ssid || "Đã kết nối · không đọc được tín hiệu") : parent.wifi.available ? "Chưa kết nối Wi-Fi" : "Không đọc được Wi-Fi"; color: Theme.textMuted; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
            }
        }
    }
}
