import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    title: "Linh kiện & lắp ráp — hồ sơ chuẩn bị chế tạo"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(820, parent ? parent.width - 24 : 820)
    height: Math.min(760, parent ? parent.height - 24 : 760)
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
    property var dossier: nexa3d.buildDossier || ({})
    property var rows: dossier.rows || []
    property var selected: parts.currentIndex >= 0 && parts.currentIndex < rows.length ? rows[parts.currentIndex] : ({})
    property string editingProject: ""
    property string editingPart: ""
    property string feedback: ""
    function loadFields() {
        if (!supply || !maker || !code || !url || !quantity || !notes) return
        var r = selected.record || ({})
        editingProject = dossier.project_id || ""
        editingPart = selected.id || ""
        supply.currentIndex = Math.max(0, ["unknown", "buy", "make", "reference"].indexOf(selected.mode || "unknown"))
        maker.text = r.manufacturer || ""
        code.text = r.model_number || ""
        url.text = r.url || ""
        quantity.value = r.quantity || 0
        notes.text = r.notes || ""
        feedback = ""
    }
    onSelectedChanged: loadFields()
    onOpened: {
        var selectedId = (nexa3d.viewState || {}).selected || ""
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].id === selectedId) { parts.currentIndex = i; break }
        }
        loadFields()
    }
    contentItem: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 12
            Label { text: dialog.dossier.error || dialog.dossier.notice || "Hãy mở mô hình trước."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Thông số cần hoàn thiện"; font.bold: true }
            Label { text: (dialog.dossier.requirements || []).join(" • "); wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: (dialog.dossier.blockers || []).join("\n"); wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#b35c18" }
            ComboBox {
                id: parts
                Layout.fillWidth: true
                model: dialog.rows
                textRole: "name"
                onCurrentIndexChanged: dialog.loadFields()
            }
            Button {
                text: "Xem bộ phận trên mô hình"
                enabled: !!dialog.selected.id && dialog.selected.id !== "@assembly"
                onClicked: { nexa3d.partAction("focus", [dialog.selected.id]); dialog.close() }
            }
            Label { text: dialog.selected.suggestion || ""; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label {
                text: "Thông số gốc (đơn vị chiều dài: " + (dialog.dossier.units || "mm") + "): " + JSON.stringify(dialog.selected.dimensions || ({}))
                wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
            }
            Label { text: (dialog.selected.missing || []).join("\n"); wrapMode: Text.WordWrap; Layout.fillWidth: true }
            GridLayout {
                columns: 2
                Layout.fillWidth: true
                enabled: !!dialog.editingPart
                Label { text: "Cách cung ứng" }
                ComboBox { id: supply; model: ["Chưa phân loại", "Mua sẵn", "Tự gia công", "Tham chiếu nội bộ"]; Layout.fillWidth: true }
                Label { text: "Hãng" }
                TextField { id: maker; placeholderText: "Hãng thực tế"; Layout.fillWidth: true; maximumLength: 4000 }
                Label { text: "Mã linh kiện" }
                TextField { id: code; placeholderText: "Mã đầy đủ, gồm phiên bản/hậu tố"; Layout.fillWidth: true; maximumLength: 4000 }
                Label { text: "Nguồn / datasheet" }
                TextField { id: url; placeholderText: "https://…"; Layout.fillWidth: true; maximumLength: 4000 }
                Label { text: "SL thực (0 = chưa biết)" }
                SpinBox { id: quantity; from: 0; to: 100000; editable: true }
            }
            TextArea { id: notes; placeholderText: "Ghi chú kích thước ghép, vật liệu, bản vẽ, thông số cần đối chiếu…"; wrapMode: TextEdit.Wrap; Layout.fillWidth: true; Layout.preferredHeight: 85 }
            Label { text: "Ghi chú do anh nhập, chưa được NEXA xác minh. Lưu không làm thay đổi hình học mô hình."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                Button {
                    text: "Lưu linh kiện"
                    enabled: !!dialog.editingPart && dialog.editingProject === dialog.dossier.project_id
                    onClicked: {
                        var ok = nexa3d.saveBuildRecord(dialog.editingProject, dialog.editingPart,
                            {mode: ["unknown", "buy", "make", "reference"][supply.currentIndex],
                             manufacturer: maker.text, model_number: code.text, url: url.text, quantity: quantity.value, notes: notes.text})
                        dialog.feedback = ok ? "Đã lưu ghi chú linh kiện." : "Chưa lưu được; xem thông báo lỗi."
                    }
                }
                Button { text: "Xuất hồ sơ đã lưu"; enabled: !!dialog.dossier.project_id; onClicked: nexa3d.exportBuildDossier(dialog.dossier.project_id) }
                Button { text: "Mở thư mục"; onClicked: nexa3d.openBuildDossierFolder() }
            }
            Label { text: dialog.feedback; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Label { text: "Lắp ráp: " + ((dialog.dossier.assembly || {}).note || "Chưa có hướng dẫn đã kiểm chứng."); wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Repeater {
                model: dialog.dossier.references || []
                Label { required property var modelData; text: modelData.title + "\n" + modelData.url; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            }
        }
    }
}
