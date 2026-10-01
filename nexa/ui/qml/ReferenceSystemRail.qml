import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme
ColumnLayout {
    id: root
    property var st: ({})
    property var status: ({})
    property string foreground: ""
    property bool paused: false
    readonly property bool hasData: st.cpu !== undefined
    readonly property bool hasGpu: st.gpu !== undefined && st.gpu !== null
    readonly property int ready: Number(!!(status.ai && status.ai.ok))+Number(!!(status.stt && status.stt.ready))+Number(!!(status.mic && status.mic.ok))+Number(!!(status.tts && status.tts.backend))
    function pct(v) {return v===undefined || v===null ? "—" : Math.round(v)+"%"}
    spacing: 8
    TacCard {
        title: "Tổng quan hệ thống"; Layout.fillWidth: true; Layout.preferredHeight: 184
        RowLayout {
            anchors.fill: parent; spacing: 6
            ColumnLayout {
                Layout.fillWidth: true; spacing: 1
                HudInfoRow { Layout.fillWidth: true; label: "CPU"; value: root.pct(root.st.cpu) }
                HudInfoRow { Layout.fillWidth: true; label: "GPU"; value: root.pct(root.st.gpu) }
                HudInfoRow { Layout.fillWidth: true; label: "RAM"; value: root.pct(root.st.ram) }
                HudInfoRow { Layout.fillWidth: true; label: "Ổ đĩa"; value: root.pct(root.st.disk) }
                HudInfoRow { Layout.fillWidth: true; label: "AI / ms"; value: root.st.ai_ms ? Math.round(root.st.ai_ms).toString() : "—" }
                HudInfoRow { Layout.fillWidth: true; label: "Nguồn"; value: root.st.charging ? "Cắm sạc" : "Pin / AC"; tint: Theme.amber }
            }
            Item {
                Layout.preferredWidth: 82; Layout.preferredHeight: 100
                Canvas {
                    anchors.centerIn: parent; width: 82; height: 82
                    property int ready: root.ready
                    onReadyChanged: requestPaint()
                    onPaint: {
                        var c=getContext('2d');c.reset();
                        for(var i=0;i<3;i++){c.beginPath();c.arc(41,41,30+i*5,0,Math.PI*2);c.strokeStyle=i===1?'#183d4e':'#25586a';c.lineWidth=1;c.stroke();}
                        c.beginPath();c.arc(41,41,35,-Math.PI/2,-Math.PI/2+Math.PI*2*ready/4);c.strokeStyle=Theme.accent;c.lineWidth=2;c.stroke();
                    }
                }
                Column { anchors.centerIn: parent; spacing: 1
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.ready+"/4"; color: Theme.accent; font.pixelSize: 23; font.family: Theme.mono }
                    Text { text: "SẴN SÀNG"; color: Theme.textMuted; font.pixelSize: 8 }
                }
            }
        }
    }
    TacCard {
        title: "Kết nối & thiết bị"; Layout.fillWidth: true; Layout.preferredHeight: 178
        ColumnLayout {
            anchors.fill: parent; spacing: 2
            HudInfoRow { Layout.fillWidth: true; label: "Gemini AI"; value: root.status.ai && root.status.ai.ok ? "Sẵn sàng" : "Chưa kết nối"; tint: root.status.ai && root.status.ai.ok ? Theme.success : Theme.amber }
            HudInfoRow { Layout.fillWidth: true; label: "Microphone"; value: root.status.mic && root.status.mic.ok ? "Đang bật" : "Đang tắt" }
            HudInfoRow { Layout.fillWidth: true; label: "Nhận dạng"; value: root.status.stt && root.status.stt.ready ? "Đã nạp" : "Chưa nạp" }
            HudInfoRow { Layout.fillWidth: true; label: "Giọng nói"; value: (root.status.tts && root.status.tts.backend) || "Chờ" }
            HudInfoRow { Layout.fillWidth: true; label: "Browser Bridge"; value: root.status.bridge && root.status.bridge.connected ? "Đã kết nối" : "Chưa kết nối"; tint: Theme.amber }
            HudInfoRow { Layout.fillWidth: true; label: "Quyền"; value: root.status.autonomy === "full" ? "Toàn quyền" : "Tiêu chuẩn" }
        }
    }
    TacCard {
        title: "Lưu trữ & năng lượng"; Layout.fillWidth: true; Layout.preferredHeight: 150
        ColumnLayout {
            anchors.fill: parent; spacing: 3
            HudInfoRow { Layout.fillWidth: true; label: "ROM / ổ đĩa"; value: root.pct(root.st.disk) }
            Text { Layout.fillWidth: true; text: root.st.disk_free_gb != null ? "Còn " + root.st.disk_free_gb + " / " + root.st.disk_total_gb + " GB" : "Chưa có dữ liệu dung lượng"; color: Theme.textMuted; font.pixelSize: 10; elide: Text.ElideRight }
            HudInfoRow { Layout.fillWidth: true; label: "Pin máy tính"; value: root.pct(root.st.battery); tint: Theme.success }
            HudInfoRow { Layout.fillWidth: true; label: "Wi-Fi"; value: root.st.wifi && root.st.wifi.connected ? (root.st.wifi.signal != null ? root.pct(root.st.wifi.signal) : "Đã kết nối") : "Chưa kết nối" }
            Text { Layout.fillWidth: true; text: root.st.wifi && root.st.wifi.ssid ? root.st.wifi.ssid : "Tín hiệu: " + root.pct(root.st.wifi ? root.st.wifi.signal : null); color: Theme.textMuted; font.pixelSize: 9; elide: Text.ElideRight; textFormat: Text.PlainText }
        }
    }
    TacCard {
        title: "Trạng thái hiện tại"; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 104
        ColumnLayout {
            anchors.fill: parent; spacing: 6
            HudInfoRow { Layout.fillWidth: true; label: "Điều khiển"; value: root.paused ? "Tạm khóa" : "Sẵn sàng"; tint: root.paused ? Theme.amber : Theme.success }
            Text { Layout.fillWidth: true; text: root.foreground || "NEXA · Command Center"; color: Theme.textSecondary; font.pixelSize: 11; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText }
            Text { Layout.fillWidth: true; text: "Ctrl + Alt + Esc  /  Dừng khẩn cấp"; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 9; wrapMode: Text.Wrap }
            Item { Layout.fillHeight: true }
        }
    }
}
