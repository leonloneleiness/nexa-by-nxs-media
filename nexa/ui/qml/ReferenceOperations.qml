import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme
ScrollView {
    id: root
    property var timeline: []
    property string appState: ""
    property string stateLabel: ""
    property string stateDetail: ""
    property string foreground: ""
    property var status: ({})
    property var modelJob: ({})
    property var codeJob: ({})
    signal models()
    signal code()
    readonly property var tasks: timeline.filter(function(row){return row.kind === "task"}).slice(-8).reverse()
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ColumnLayout {
    width: root.availableWidth
    spacing: 8
    GenerationProgress { Layout.fillWidth: true; title: "TẠO MÔ HÌNH 3D"; job: root.modelJob; onOpenRequested: root.models() }
    GenerationProgress { Layout.fillWidth: true; title: "TẠO / XỬ LÝ CODE"; job: root.codeJob; onOpenRequested: root.code() }
    TacCard {
        title: "Lệnh gần đây"; Layout.fillWidth: true; Layout.preferredHeight: 114
        ListView {
            anchors.fill: parent; clip: true; spacing: 5; model: root.tasks
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width; height: 38; color: "#081d2a"; border.color: Theme.border; radius: 2
                Column { x: 9; anchors.verticalCenter: parent.verticalCenter; width: parent.width-18; spacing: 2
                    Text { width: parent.width; text: modelData.title || "Tác vụ"; font.pixelSize: 10; color: Theme.textPrimary; elide: Text.ElideRight; textFormat: Text.PlainText }
                    Text { text: modelData.status === "done" ? "✓  Đã xử lý lệnh" : modelData.status === "running" ? "◈  Đang xử lý lệnh" : modelData.status === "failed" ? "Lệnh gặp lỗi" : modelData.status; color: modelData.status === "done" ? Theme.success : Theme.accent; font.pixelSize: 9 }
                }
            }
            Text { visible: root.tasks.length===0; anchors.fill: parent; text: "Chưa có tác vụ.\nNói hoặc nhập lệnh để bắt đầu."; color: Theme.textMuted; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.6 }
        }
    }
    TacCard {
        title: "Hoạt động hiện tại"; Layout.fillWidth: true; Layout.preferredHeight: 152
        ColumnLayout { anchors.fill: parent; spacing: 7
            HudInfoRow { Layout.fillWidth: true; label: "NEXA"; value: root.stateLabel }
            HudInfoRow { Layout.fillWidth: true; label: "Chế độ"; value: root.status.companion ? "Tâm sự" : "Trợ lý" }
            Text { Layout.fillWidth: true; text: root.stateDetail || "Theo dõi giọng nói và lệnh của anh."; font.pixelSize: 10; color: Theme.textSecondary; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText }
            Item { Layout.fillHeight: true }
        }
    }
    TacCard {
        title: "Nhật ký phiên"; Layout.fillWidth: true; Layout.preferredHeight: 124
        ColumnLayout { anchors.fill: parent; spacing: 6
            HudInfoRow { Layout.fillWidth: true; label: "Hội thoại"; value: root.timeline.filter(function(r){return r.kind!=="task"}).length+" tin nhắn" }
            HudInfoRow { Layout.fillWidth: true; label: "Tác vụ"; value: root.tasks.length.toString() }
            Text { Layout.fillWidth: true; text: root.foreground || "NEXA Command Center"; font.pixelSize: 10; color: Theme.textMuted; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText }
            Item { Layout.fillHeight: true }
        }
    }
    }
}
