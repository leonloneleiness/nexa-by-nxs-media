import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    signal closeRequested()
    color: Theme.panelGlass
    radius: 14
    border.color: Theme.border
    property var gs: nexa.gestureStatus
    property var last: nexa.gestureLast
    property var at: nexa.attentionStatus
    property var mons: []
    property int frameTick: 0
    onVisibleChanged: { nexa.setPreviewEnabled(visible); if (visible) { mons = nexa.monitors(); nexa.refreshAttention() } }
    Connections { target: nexa; function onCameraFrame(n) { if (panel.visible) panel.frameTick = n } }

    function roleOf(role) {
        for (var i = 0; i < mons.length; i++) if (mons[i].role === role) return mons[i].device_name.replace("\\\\.\\", "") + " · " + mons[i].friendly_name
        return "—"
    }
    readonly property var labels: ({
        "MOVE_WINDOW_TO_MONITOR_2": "Chuyển sang màn hình 2",
        "MINIMIZE_ACTIVE_WINDOW": "Thu nhỏ cửa sổ",
        "RESTORE_LAST_MINIMIZED_WINDOW": "Khôi phục cửa sổ",
        "YOUTUBE_PAUSE": "Tạm dừng YouTube",
        "YOUTUBE_RESUME": "Phát tiếp YouTube",
        "SCROLL_UP": "Cuộn lên"
    })

    Flickable {
        id: gestureViewport
        contentWidth: width
        ScrollBar.vertical: ScrollBar {}
        anchors.fill: parent; anchors.margins: 12
        contentHeight: col.implicitHeight
        clip: true
        ColumnLayout {
            id: col
            width: gestureViewport.width
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Cử chỉ tay"; color: "white"; font.pixelSize: 17; font.bold: true }
                Rectangle { visible: nexa.cameraOn; width: camTxt.implicitWidth + 16; height: 22; radius: 11; color: "#7f1d1d"
                            Text { id: camTxt; anchors.centerIn: parent; text: "● CAMERA ĐANG BẬT"; color: "#fecaca"; font.pixelSize: 11 } }
                Item { Layout.fillWidth: true }
                Button { text: "✕"; implicitWidth: 30; flat: true; onClicked: panel.closeRequested()
                         contentItem: Text { text: "✕"; color: "white" } background: Item {} }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: width * 0.75
                color: Theme.surface; radius: 8; border.color: Theme.border; clip: true
                Image {
                    anchors.fill: parent; anchors.margins: 2
                    fillMode: Image.PreserveAspectFit
                    cache: false
                    source: nexa.cameraOn && panel.visible ? "image://camera/f" + panel.frameTick : ""
                }
                Text { anchors.centerIn: parent; visible: !nexa.cameraOn; text: "Camera đang tắt"; color: Theme.textMuted }
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    text: nexa.cameraOn ? "Tắt camera" : "Bật camera"
                    onClicked: nexa.toggleGestures()
                }
                Button {
                    text: nexa.airMouse ? "Tắt chuột bằng tay" : "Chuột bằng tay"
                    highlighted: nexa.airMouse
                    onClicked: nexa.toggleAirMouse()
                }
                CheckBox { id: lm; text: "Hiện landmarks"; checked: nexa.showLandmarks; onToggled: nexa.setShowLandmarks(checked)
                           contentItem: Text { text: lm.text; color: "white"; leftPadding: lm.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
            }
            Rectangle {
                visible: nexa.airMouse
                Layout.fillWidth: true; implicitHeight: mouseCol.implicitHeight + 12
                radius: 8; color: Theme.surfaceRaised; border.color: Theme.accent
                ColumnLayout {
                    id: mouseCol
                    anchors.fill: parent; anchors.margins: 6; spacing: 2
                    Text { text: "🖱 CHUỘT BẰNG TAY ĐANG BẬT — sáu cử chỉ lệnh tạm ngưng"; color: Theme.accent; font.bold: true; font.pixelSize: 12 }
                    Text { color: "white"; font.pixelSize: 12
                           text: "Chế độ: " + ({"move": "di chuyển", "clutch": "nhấc tay (nắm tay)", "scroll": "cuộn"}[gs.mouse_mode] || "—")
                                 + (gs.mouse_pinch ? (gs.mouse_dragging ? " · đang kéo" : (gs.mouse_pinch === "left" ? " · đang chụm (click)" : " · click phải")) : "")
                                 + (gs.mouse_last ? " · vừa: " + gs.mouse_last : "") }
                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.textMuted; font.pixelSize: 11
                           text: "Di tay → con trỏ · 🤏 chụm cái + trỏ → click (2 lần = click đúp) · chụm giữ rồi kéo → kéo thả · chụm cái + giữa → click phải · ✌ hai ngón đưa lên/xuống → cuộn · ✊ nắm tay → nhấc tay, đặt lại chỗ khác. Cầm chuột thật thì NEXA tự nhường." }
                }
            }
            GridLayout {
                columns: 2; columnSpacing: 10; rowSpacing: 4
                Layout.fillWidth: true
                Text { text: "Tư thế"; color: Theme.textSecondary } Text { text: (gs.pose_label || "—") + (gs.confidence ? "  (" + Math.round(gs.confidence * 100) + "%)" : ""); color: "white"; font.bold: true }
                Text { text: "Tay"; color: Theme.textSecondary } Text { text: gs.hand || "—"; color: "white" }
                Text { text: "Tư thế ổn định"; color: Theme.textSecondary } Text { text: gs.stable_pose || "—"; color: "white" }
                Text { text: "Chuyển động"; color: Theme.textSecondary } Text { text: (gs.motion || "—") + (gs.speed !== undefined ? " · " + gs.speed + " tay/s" : ""); color: "white" }
                Text { text: "Giữ yên"; color: Theme.textSecondary }
                ProgressBar { Layout.fillWidth: true; value: gs.hold || 0 }
                Text { text: "Cooldown"; color: Theme.textSecondary }
                ProgressBar { Layout.fillWidth: true; value: gs.cooldown || 0 }
                Text { text: "Lặp lại"; color: Theme.textSecondary } Text { text: gs.need_rearm ? "đổi tư thế để làm lại" : "sẵn sàng"; color: gs.need_rearm ? Theme.amber : Theme.success }
                Text { text: "Sẵn sàng phát tiếp"; color: Theme.textSecondary } Text { text: gs.pause_armed ? "có (vừa nắm tay)" : "không"; color: "white" }
                Text { text: "FPS xử lý / camera"; color: Theme.textSecondary } Text { text: (gs.fps || 0) + " / " + (gs.camera_fps || 0); color: "white" }
                Text { text: "Trạng thái"; color: Theme.textSecondary } Text { text: gs.paused ? "tạm khóa (dừng khẩn cấp)" : (gs.calibrating ? "đang hiệu chuẩn" : "hoạt động"); color: gs.paused ? Theme.danger : "white" }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            Text { text: "Nhận biết anh qua webcam"; color: "white"; font.pixelSize: 15; font.bold: true }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    text: at.presence_enabled ? "Tắt tự khóa khi rời máy" : "Tự khóa khi rời máy"
                    highlighted: !!at.presence_enabled
                    onClicked: nexa.setPresence(!at.presence_enabled)
                }
                Button { text: "Hiệu chỉnh hướng nhìn"; onClicked: nexa.calibrateHead() }
            }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Text { text: "Chọn màn hình theo hướng quay đầu:"; color: Theme.textSecondary }
                Repeater {
                    model: [["off", "Tắt"], ["commands", "Theo lệnh"], ["auto", "Tự động"]]
                    delegate: Button {
                        required property var modelData
                        text: modelData[1]; checkable: true
                        checked: (at.head_target || "off") === modelData[0]
                        onClicked: nexa.setHeadTarget(modelData[0])
                    }
                }
            }
            GridLayout {
                columns: 2; columnSpacing: 10; rowSpacing: 4
                Layout.fillWidth: true
                Text { text: "Có mặt"; color: Theme.textSecondary }
                Text { color: at.onlooker ? Theme.amber : (at.presence === "away" ? Theme.danger : "white")
                       text: !nexa.cameraOn ? "— (camera tắt)"
                             : !at.face_active ? (panel.gs.face_error || "đang khởi động nhận diện mặt…")
                             : ({"present": "đang ngồi ở máy", "warning": "không thấy anh — sắp khóa", "away": "đã rời máy"}[at.presence] || "—")
                               + (at.faces > 1 ? " · " + at.faces + " khuôn mặt" : "")
                               + (at.onlooker ? " · CÓ NGƯỜI PHÍA SAU" : "")
                               + (at.presence_enabled ? "" : " (tự khóa đang tắt)") }
                Text { text: "Đang nhìn"; color: Theme.textSecondary }
                Text { color: "white"
                       text: (at.head_monitor_name || (at.head_ready ? "—" : "chưa hiệu chuẩn"))
                             + (at.head_calibrating ? " · đang hiệu chuẩn…" : "")
                             + (at.head_yaw !== undefined && at.head_yaw !== null ? "  (yaw " + at.head_yaw + "°, pitch " + at.head_pitch + "°)" : "") }
            }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.textMuted; font.pixelSize: 11
                   text: "Chạy cục bộ, không lưu ảnh. Rời máy ~45 giây → dừng video + khóa Windows (mở bằng PIN/Windows Hello); quay lại → phát tiếp. Có người nhìn từ phía sau → thu nhỏ cửa sổ nhạy cảm. Hướng nhìn: hiệu chỉnh một lần (nhìn vào giữa từng màn hình khi khung sáng lên)." }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            Text { text: "Cử chỉ vừa thực thi"; color: Theme.textSecondary }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: last.ok ? Theme.success : Theme.danger; font.pixelSize: 13
                   text: last.event ? ((panel.labels[last.event] || last.event) + " — " + (last.message || "") + "  (" + last.time + ")") : "—" }
            Text { text: "Cửa sổ đích hiện tại"; color: Theme.textSecondary }
            Text { Layout.fillWidth: true; text: nexa.foreground || "—"; color: "white"; elide: Text.ElideRight }
            Text { text: "Màn hình nguồn → đích"; color: Theme.textSecondary }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: "white"
                   text: mons.length < 2 ? "Chỉ có " + mons.length + " màn hình" : panel.roleOf("source") + "  →  " + panel.roleOf("target") }
            Text { text: "Mục tiêu YouTube"; color: Theme.textSecondary }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: "white"
                   text: nexa.mediaStatus.bound ? (nexa.mediaStatus.bound.title + " [" + nexa.mediaStatus.bound.backend + "] · " + nexa.mediaStatus.last_state) : "Tự động — video đang phát trong trình duyệt" }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.textMuted; font.pixelSize: 11
                   text: "Giữ yên tư thế ~0,5 giây (không cần vuốt):\n👉 chỉ ngón trỏ sang phải → màn hình 2 · 👎 ngón cái chỉ xuống → thu nhỏ · 👍 ngón cái chỉ lên → khôi phục · ✊ nắm tay → tạm dừng YouTube · 🖐 xòe tay ngay sau đó → phát tiếp · ✌ giữ hai ngón (trỏ + giữa) → cuộn lên liên tục." }
        }
    }
    Component.onCompleted: nexa.setPreviewEnabled(visible)
}
