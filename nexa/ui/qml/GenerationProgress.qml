import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Rectangle {
    id: card
    property var job: ({})
    property string title: ""
    property bool compact: false
    signal openRequested()
    readonly property string state: job.state || "idle"
    readonly property bool present: state !== "idle" && state !== ""
    readonly property bool done: state === "ready" || state === "done"
    readonly property bool draft: job.error_code === "quality_gate" && !!job.project_id
    readonly property bool stopped: state === "failed" || state === "cancelled" || state === "needs_input"
    readonly property bool running: present && !done && !stopped
    readonly property int percent: done ? 100 : Math.max(0, Math.min(99, Math.floor(Number(job.progress || 0) * 100)))
    property real now: Date.now() / 1000
    readonly property real seconds: present ? Math.max(0, (job.finished || now) - (job.started || job.created || now)) : 0
    readonly property string duration: Math.floor(seconds / 60) + " phút " + Math.floor(seconds % 60) + " giây"
    readonly property string statusText: !present ? "Chưa có tác vụ" : done ? "ĐÃ XONG" : draft ? "CẦN HOÀN THIỆN"
        : state === "failed" ? "LỖI — CHƯA XONG" : state === "cancelled" ? "ĐÃ HỦY"
        : state === "needs_input" ? "CẦN THÊM THÔNG TIN" : state === "queued" ? "ĐANG CHỜ" : "ĐANG TẠO"
    readonly property color tone: done ? Theme.success : stopped ? Theme.amber : Theme.accent
    implicitHeight: compact ? 104 : 166
    radius: 6; color: Theme.surface; border.color: present ? tone : Theme.border
    Timer { interval: 1000; repeat: true; running: card.running; onTriggered: card.now = Date.now() / 1000 }
    onJobChanged: now = Date.now() / 1000
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Text { text: card.title; color: Theme.textPrimary; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Text { text: !card.present ? "—" : card.percent + "%"; color: card.tone; font.pixelSize: 24; font.weight: Font.DemiBold }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: card.statusText; color: card.tone; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight }
            TacTool { small: true; text: card.done || card.draft ? "Xem kết quả" : "Chi tiết"
                onClicked: card.openRequested() }
        }
        ProgressBar {
            Layout.fillWidth: true; from: 0; to: 100; value: card.percent
            background: Rectangle { implicitHeight: 5; color: Theme.surfaceRaised; radius: 2 }
            contentItem: Item { implicitHeight: 5
                Rectangle { width: parent.width * card.percent / 100; height: parent.height; radius: 2; color: card.tone } }
        }
        Text { visible: !card.compact; Layout.fillWidth: true; text: card.job.message || "Tiến độ sẽ xuất hiện khi bắt đầu."
            color: Theme.textSecondary; font.pixelSize: 10; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText }
        Text { visible: !card.compact; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: 10
            text: card.present ? (card.state === "queued" ? "Đã chờ " : card.running ? "Đã chạy " : "Thời gian chạy ") + card.duration : ""
            elide: Text.ElideRight }
        Text { visible: !card.compact && card.running; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: 9
            text: "% ước lượng theo bước · Chưa có giờ hoàn tất"; elide: Text.ElideRight }
    }
}
