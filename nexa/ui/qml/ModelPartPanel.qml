import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "TacStyle.js" as S

// Cây bộ phận (mã P01…, đường nhánh, bật/tắt hiển thị) + thẻ thông số bộ phận đang chọn + tóm tắt chất lượng.
TacCard {
    id: panel
    title: "Bộ phận"; code: "03"
    sub: "[" + (mdl.parts ? mdl.parts.length : 0) + "]"
    fillColor: Theme.panelGlass
    pad: 12
    property var mdl: nexa3d.model
    property var vs: nexa3d.viewState
    property var info: vs && vs.info ? vs.info : ({})
    readonly property string iconFont: S.iconFont(Qt.fontFamilies())
    headerExtra: [
        Item {
            implicitWidth: asmTxt.implicitWidth + 16; implicitHeight: 22
            readonly property color tone: panel.mdl.has_assembly ? S.ok : S.amber
            y: 4
            TacFrame { anchors.fill: parent; cut: 5; fill: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.1)
                       stroke: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.6) }
            Text { id: asmTxt; anchors.centerIn: parent; text: panel.mdl.has_assembly ? "ASSEMBLY" : "MỘT KHỐI"
                   color: parent.tone; font.family: panel.tacFont; font.pixelSize: 10; font.letterSpacing: 2 }
        }
    ]

    component KV: RowLayout {
        property string k: ""
        property string v: ""
        visible: v.length > 0
        Layout.fillWidth: true
        spacing: 8
        Text { text: parent.k; color: S.iceDim; font.family: panel.tacFont; font.pixelSize: 10; font.letterSpacing: 2
               Layout.preferredWidth: 86; Layout.alignment: Qt.AlignTop; topPadding: 2 }
        Text { text: parent.v; color: Theme.textPrimary; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 10
        ListView {
            id: tree
            objectName: "partTree"
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; spacing: 1
            model: panel.mdl.parts || []
            ScrollBar.vertical: ScrollBar {}
            delegate: Item {
                id: rowItem
                required property var modelData
                required property int index
                width: tree.width; height: 26
                readonly property bool sel: panel.vs && panel.vs.selected === modelData.id
                readonly property bool hidden: panel.vs && panel.vs.visible && panel.vs.visible[modelData.id] === false
                Rectangle { anchors.fill: parent; color: rowItem.sel ? "#1a8fd8ff" : (ma.containsMouse ? "#0f8fd8ff" : "transparent") }
                Rectangle { visible: rowItem.sel; width: 2; height: parent.height; color: S.ice }
                Text { x: 8; anchors.verticalCenter: parent.verticalCenter
                       text: "P" + ("0" + (rowItem.index + 1)).slice(-2); color: rowItem.sel ? S.amber : Theme.borderStrong
                       font.family: S.mono; font.pixelSize: 10 }
                // đường nhánh theo độ sâu
                Repeater {
                    model: rowItem.modelData.depth || 0
                    Rectangle { required property int index; x: 40 + index * 14; width: 1; height: rowItem.height
                                color: Qt.rgba(0.56, 0.85, 1, 0.14) }
                }
                Rectangle { visible: (rowItem.modelData.depth || 0) > 0; x: 40 + ((rowItem.modelData.depth || 1) - 1) * 14
                            anchors.verticalCenter: parent.verticalCenter; width: 9; height: 1; color: Qt.rgba(0.56, 0.85, 1, 0.3) }
                Rectangle { x: 38 + (rowItem.modelData.depth || 0) * 14; anchors.verticalCenter: parent.verticalCenter
                            width: 5; height: 5; rotation: 45
                            color: rowItem.hidden ? "transparent" : (rowItem.sel ? S.ice : S.iceDim)
                            border.color: rowItem.hidden ? Theme.borderStrong : "transparent" }
                Text {
                    x: 50 + (rowItem.modelData.depth || 0) * 14
                    width: rowItem.width - x - 30
                    anchors.verticalCenter: parent.verticalCenter
                    text: rowItem.modelData.name; elide: Text.ElideRight; font.pixelSize: 12
                    color: rowItem.hidden ? "#4b6a8a" : (rowItem.sel ? "white" : Theme.textPrimary)
                    font.strikeout: rowItem.hidden
                }
                MouseArea { id: ma; anchors.fill: parent; anchors.rightMargin: 26; hoverEnabled: true
                            onClicked: nexa3d.partAction("focus", [rowItem.modelData.id]) }
                Text {
                    anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                    text: S.glyph(rowItem.hidden ? 0xED1A : 0xE7B3); font.family: panel.iconFont; font.pixelSize: 12
                    color: rowItem.hidden ? Theme.borderStrong : (eyeMa.containsMouse ? S.ice : S.iceDim)
                    MouseArea { id: eyeMa; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true
                                onClicked: nexa3d.partAction("toggle", [rowItem.modelData.id]) }
                }
            }
        }

        // ---------- thẻ thông số bộ phận đang chọn ----------
        Item {
            visible: panel.info && panel.info.name !== undefined
            Layout.fillWidth: true
            implicitHeight: infoCol.implicitHeight + 20
            TacFrame { anchors.fill: parent; cut: 9; fill: "#0f8fd8ff"; stroke: Qt.rgba(0.56, 0.85, 1, 0.5) }
            Rectangle { x: 10; y: 0; width: 38; height: 2; color: S.amber }
            ColumnLayout {
                id: infoCol
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 10; anchors.topMargin: 10
                spacing: 4
                Text { text: (panel.info.name || "").toUpperCase(); color: "white"; font.family: panel.tacFont; font.pixelSize: 14
                       font.letterSpacing: 1.5; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Text { visible: text.length > 0; text: panel.info.name_en || ""; color: S.iceDim; font.family: S.mono; font.pixelSize: 11
                       Layout.fillWidth: true; elide: Text.ElideRight }
                KV { k: "VỊ TRÍ"; v: panel.info.position || "" }
                KV { k: "KÍCH THƯỚC"; v: panel.info.dimensions_text || "" }
                KV { k: "VẬT LIỆU"; v: panel.info.material || "" }
                KV { k: "CHỨC NĂNG"; v: panel.info.function || "" }
                Text { visible: panel.info.confidence !== undefined && panel.info.confidence < 0.99
                       text: "⚠ Độ tin cậy nhận dạng bộ phận: " + Math.round((panel.info.confidence || 0) * 100) + "%"
                       color: S.amber; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Flow {
                    Layout.fillWidth: true; Layout.topMargin: 4; spacing: 5
                    TacTool { small: true; text: "Tách riêng"; onClicked: nexa3d.partAction("isolate", [panel.info.id]) }
                    TacTool { small: true; text: "Ẩn"; onClicked: nexa3d.partAction("hide", [panel.info.id]) }
                    TacTool { small: true; text: "Hiện tất cả"; onClicked: nexa3d.showAll() }
                }
            }
        }

        // ---------- chất lượng: điểm + thanh 20 đoạn + các mục kiểm tra ----------
        Item {
            Layout.fillWidth: true
            implicitHeight: qCol.implicitHeight + 18
            readonly property real score: Math.round(panel.mdl.quality_score || 0)
            readonly property color tone: panel.mdl.quality_status === "passed" ? S.ok
                                         : panel.mdl.quality_status === "best_effort" ? S.amber : S.hazard
            TacFrame { anchors.fill: parent; cut: 9; fill: Theme.inputGlass; stroke: Qt.rgba(0.56, 0.85, 1, 0.22) }
            ColumnLayout {
                id: qCol
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 10; anchors.topMargin: 9
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Text { text: "CHẤT LƯỢNG"; color: S.iceDim; font.family: panel.tacFont; font.pixelSize: 10; font.letterSpacing: 2 }
                    Item { Layout.fillWidth: true }
                    Text { text: parent.parent.parent.score; color: "white"; font.family: panel.tacFont; font.pixelSize: 18 }
                    Text { text: "/100 · " + ({"passed": "ĐẠT", "failed": "CHƯA ĐẠT", "best_effort": "BEST EFFORT"}[panel.mdl.quality_status] || "—")
                           color: parent.parent.parent.tone; font.family: panel.tacFont; font.pixelSize: 11; font.letterSpacing: 1 }
                }
                Row {
                    Layout.fillWidth: true; spacing: 2
                    Repeater { model: 20
                        Rectangle { required property int index; width: (qCol.width - 38) / 20; height: 4
                                    color: index < Math.round(qCol.parent.score / 5) ? qCol.parent.tone : Theme.border } }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 4
                    property var md: panel.mdl.metadata || ({})
                    Repeater {
                        model: [
                            [parent.md.dimensionally_specified ? "Kích thước xác định" : "Mô hình ý tưởng", parent.md.dimensionally_specified === true],
                            [parent.md.geometry_validated ? "Hình học đã kiểm tra" : "Hình học chưa đạt", parent.md.geometry_validated === true],
                            parent.md.technical_thread === true ? ["Ren helix kỹ thuật", true]
                                : parent.md.technical_thread === false ? ["Ren minh họa", false] : null,
                            parent.md.assembly_confidence !== undefined && parent.md.assembly_confidence !== null
                                ? ["Assembly " + Math.round(parent.md.assembly_confidence * 100) + "%", parent.md.assembly_confidence >= 0.8] : null,
                            [parent.md.ai_review_used ? "Có AI chấm ảnh" : "Chưa có AI chấm ảnh", parent.md.ai_review_used === true],
                            ["Chưa kiểm chứng chế tạo", false]
                        ].filter(function(x) { return x !== null })
                        Item {
                            required property var modelData
                            readonly property color tone: modelData[1] ? S.ok : S.iceDim
                            implicitWidth: tagTxt.implicitWidth + 14; implicitHeight: 20
                            Rectangle { anchors.fill: parent; color: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.08)
                                        border.color: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.35) }
                            Text { id: tagTxt; anchors.centerIn: parent; text: (parent.modelData[1] ? "✓ " : "· ") + parent.modelData[0]
                                   color: parent.modelData[1] ? "#bff5d8" : Theme.textSecondary; font.pixelSize: 10 }
                        }
                    }
                }
            }
        }
    }
}
