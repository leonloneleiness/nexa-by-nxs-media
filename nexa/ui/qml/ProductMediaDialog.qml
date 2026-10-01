import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    title: "Ảnh & video sản phẩm"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(460, parent ? parent.width - 24 : 460)
    palette.window: Theme.surface
    palette.windowText: Theme.textPrimary
    palette.text: Theme.textPrimary
    palette.base: Theme.surfaceDeep
    palette.button: Theme.surfaceRaised
    palette.buttonText: Theme.textPrimary
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.bg
    background: Rectangle { color: Theme.surface; radius: 14; border.color: Theme.border }
    modal: true
    standardButtons: Dialog.Close
    property var status: nexa3d.media || ({})
    contentItem: ColumnLayout {
        spacing: 10
        Label {
            text: "Xuất toàn bộ mô hình ở trạng thái lắp ráp, không kèm giao diện. Ánh sáng studio cố định; màu có thể khác trình xem."
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GridLayout {
            columns: 2
            enabled: !dialog.status.busy
            Label { text: "Định dạng" }
            ComboBox { id: format; model: ["Ảnh PNG", "Video MP4 · 360°"] ; Layout.fillWidth: true }
            Label { text: "Kích thước vuông" }
            ComboBox { id: resolution; model: ["512 × 512", "768 × 768", "1024 × 1024"]; currentIndex: 1; Layout.fillWidth: true }
            Label { text: "Nền" }
            ComboBox { id: background; model: ["Studio sáng", "Studio tối"]; Layout.fillWidth: true }
            Label { text: "Góc nhìn" }
            ComboBox { id: angle; model: ["Góc 3/4", "Chính diện", "Góc bên"]; Layout.fillWidth: true }
            Label { text: "Thời lượng"; visible: format.currentIndex === 1 }
            ComboBox { id: duration; model: ["3 giây", "6 giây", "10 giây"]; currentIndex: 1; visible: format.currentIndex === 1; Layout.fillWidth: true }
        }
        Label { text: "Video 24 hình/giây. Mô hình nhiều chi tiết có thể mất vài phút để xuất."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        ProgressBar { from: 0; to: 100; value: dialog.status.progress || 0; visible: !!dialog.status.busy; Layout.fillWidth: true }
        Label { text: "Đang xuất: " + (dialog.status.progress || 0) + "%"; visible: !!dialog.status.busy }
        Label { text: dialog.status.error || ""; visible: text.length > 0; color: "#e06555"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Label { text: dialog.status.path ? "Đã lưu: " + dialog.status.path : ""; visible: text.length > 0; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
        RowLayout {
            Button {
                text: format.currentIndex === 0 ? "Xuất ảnh" : "Xuất video xoay"
                enabled: !dialog.status.busy && nexa3d.viewerOpen && !nexa3d.loading
                onClicked: nexa3d.exportProductMedia(format.currentIndex === 0 ? "png" : "mp4",
                    [512, 768, 1024][resolution.currentIndex], background.currentIndex === 0 ? "light" : "dark",
                    [3, 6, 10][duration.currentIndex], [35, 0, 90][angle.currentIndex], angle.currentIndex === 0 ? 20 : 0)
            }
            Button { text: "Hủy xuất"; visible: !!dialog.status.busy; onClicked: nexa3d.cancelProductMedia() }
            Button { text: "Mở thư mục"; visible: !!dialog.status.path; onClicked: nexa3d.openProductMediaFolder() }
        }
    }
}
