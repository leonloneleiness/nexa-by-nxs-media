import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Rectangle {
    id: root
    objectName: "educationPanel"
    color: Theme.surface
    radius: 16
    border.color: Theme.accent
    border.width: 1
    property alias bridge: root._bridge
    property var _bridge: nexaEdu
    signal closeRequested()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            Text { text: "NEXA EDU"; color: Theme.accent; font.pixelSize: 24; font.bold: true }
            Text { text: "MÔ PHỎNG STEM · PHÒNG THÍ NGHIỆM ẢO"; color: Theme.textSecondary; font.pixelSize: 11; font.family: Theme.mono; Layout.fillWidth: true }
            Button { text: "Đóng"; onClicked: root.closeRequested() }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
            Rectangle {
                Layout.preferredWidth: 270; Layout.fillHeight: true; color: Theme.surfaceDeep; radius: 12
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 12; spacing: 8
                    Text { text: "BÀI HỌC"; color: Theme.textSecondary; font.family: Theme.mono; font.pixelSize: 11 }
                    ListView {
                        id: lessons; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 6; clip: true
                        model: root._bridge.catalog
                        delegate: Button {
                            width: lessons.width; height: 62
                            text: modelData.title + "\n" + modelData.subject + " · " + modelData.level
                            highlighted: modelData.id === root._bridge.state.lesson.id
                            onClicked: root._bridge.selectLesson(modelData.id)
                            contentItem: Text { text: parent.text; color: parent.highlighted ? Theme.bg : Theme.textPrimary; wrapMode: Text.Wrap; leftPadding: 10; verticalAlignment: Text.AlignVCenter }
                        }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true; color: Theme.surfaceDeep; radius: 12
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        Text { text: root._bridge.state.lesson.title; color: Theme.textPrimary; font.pixelSize: 26; font.bold: true; Layout.fillWidth: true }
                        Button { text: "Đặt lại"; onClicked: root._bridge.resetLesson() }
                    }
                    Text { text: root._bridge.state.lesson.summary; color: Theme.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    EducationScene { Layout.fillWidth: true; Layout.preferredHeight: 180; lessonId: root._bridge.state.lesson.id }
                    Text { text: "BƯỚC " + (root._bridge.state.step + 1) + "/" + root._bridge.state.steps.length + "  ·  " + (root._bridge.state.steps[root._bridge.state.step] || ""); color: Theme.accent; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { text: "THAM SỐ THÍ NGHIỆM"; color: Theme.accent; font.family: Theme.mono; font.pixelSize: 11 }
                    Repeater {
                        model: root._bridge.state.parameters
                        delegate: RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            Text { text: modelData.label; color: Theme.textPrimary; Layout.preferredWidth: 150 }
                            Slider { Layout.fillWidth: true; from: modelData.min; to: modelData.max; value: modelData.value
                                onMoved: root._bridge.setParameter(modelData.id, value) }
                            Text { text: Number(modelData.value).toFixed(2) + " " + modelData.unit; color: Theme.accent; font.family: Theme.mono; Layout.preferredWidth: 100 }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 110; color: Theme.bg; radius: 10; border.color: Theme.border
                        ColumnLayout { anchors.fill: parent; anchors.margins: 14
                            Text { text: root._bridge.state.result.label || "Chưa chạy mô phỏng"; color: Theme.textSecondary; font.family: Theme.mono; font.pixelSize: 11 }
                            Text { text: root._bridge.state.result.value !== undefined ? root._bridge.state.result.value + " " + root._bridge.state.result.unit : "Hãy điều chỉnh tham số rồi bấm Chạy"; color: Theme.accent; font.pixelSize: 25; font.bold: true }
                            Text { text: root._bridge.state.result.feedback || "Dự đoán kết quả trước khi chạy."; color: Theme.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        }
                    }
                    RowLayout { Layout.fillWidth: true
                        Text { text: "Lần chạy: " + root._bridge.state.history_count; color: Theme.textSecondary; Layout.fillWidth: true }
                        Button { text: "Bước tiếp"; onClicked: root._bridge.nextStep() }
                        Button { text: "Lưu báo cáo"; onClicked: root._bridge.exportReport("") }
                        Button { text: "Chạy mô phỏng"; onClicked: root._bridge.runSimulation() }
                    }
                }
            }
        }
    }
}
