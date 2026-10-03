import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "TacStyle.js" as S

// "Xưởng chế tạo": dòng lệnh tạo mô hình 3D + pipeline giai đoạn của job + kho mô hình gần đây.
// (Giọng nói dùng cùng luồng qua IntentRouter/Gemini.)
TacCard {
    id: panel
    signal closeRequested()
    title: "Không gian sáng tạo 3D"; code: "STUDIO"
    sub: ""
    fillColor: Theme.panelGlass
    cut: 18
    pad: 18
    property var job: nexa3d.activeJob
    property string mode: "auto"
    property bool hq: false
    property string referenceMethod: "auto"
    property var references: ({})
    readonly property int referenceCount: Object.keys(references).length
    function setReference(view, url) {
        var updated = Object.assign({}, references)
        if (url) updated[view] = url
        else delete updated[view]
        references = updated
    }
    FileDialog {
        id: referencePicker
        property string view: "front"
        title: "Chọn ảnh tham chiếu của vật thể"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Ảnh (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: panel.setReference(view, selectedFile.toString())
    }
    property real pulse: 1
    SequentialAnimation on pulse {
        running: panel.hasJob && !panel.job.terminal; loops: Animation.Infinite
        NumberAnimation { to: 0.35; duration: 520 }
        NumberAnimation { to: 1; duration: 520 }
    }
    readonly property bool hasJob: !!(job && job.id !== undefined)
    readonly property bool needsPolish: hasJob && job.error_code === "quality_gate" && !!job.project_id
    readonly property var stateColor: ({"ready": S.ok, "failed": S.hazard, "cancelled": S.iceDim, "needs_input": S.amber})
    readonly property color jobTone: needsPolish ? S.amber : hasJob ? (stateColor[job.state] || S.ice) : S.ice
    // giai đoạn pipeline ↔ trạng thái job
    readonly property var stages: ([
        {"k": "PHÂN TÍCH", "s": ["queued", "planning"]},
        {"k": "DỰNG HÌNH", "s": ["generating_reference", "generating_geometry", "texturing"]},
        {"k": "TÁCH BỘ PHẬN", "s": ["segmenting"]},
        {"k": "KIỂM TRA", "s": ["validating", "rendering", "reviewing", "refining"]},
        {"k": "TỐI ƯU", "s": ["optimizing"]},
        {"k": "SẴN SÀNG", "s": ["ready"]}
    ]).filter(function(stage) { return !(panel.hasJob && panel.job.reference_based && stage.s[0] === "segmenting") })
    readonly property int reviewStageIdx: {
        for (var i = 0; i < stages.length; i++)
            if (stages[i].s.indexOf("reviewing") >= 0) return i
        return 3
    }
    readonly property int stageIdx: {
        if (!hasJob) return -1
        for (var i = 0; i < stages.length; i++)
            if (stages[i].s.indexOf(job.state) >= 0) return i
        return -1
    }
    // với failed/cancelled/needs_input: giữ vị trí theo tiến độ để biết dừng ở giai đoạn nào
    readonly property int reachedIdx: needsPolish ? reviewStageIdx : stageIdx >= 0 ? stageIdx
                                      : hasJob ? Math.min(stages.length - 2, Math.floor((job.progress || 0) * (stages.length - 1))) : -1

    headerExtra: [
        Item {
            visible: panel.width >= 850
            y: 3
            implicitWidth: provRow.implicitWidth + 18; implicitHeight: 24
            readonly property color tone: nexa3d.providerStatus.ok ? S.ok : S.iceDim
            TacFrame { anchors.fill: parent; cut: 6; fill: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.08)
                       stroke: Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.45) }
            Row {
                id: provRow; anchors.centerIn: parent; spacing: 6
                Rectangle { width: 6; height: 6; radius: 3; color: parent.parent.tone; anchors.verticalCenter: parent.verticalCenter }
                Text { color: S.textDim; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter
                       text: nexa3d.providerStatus.ok ? ("Cloud: " + (nexa3d.providerStatus.name || "") + " sẵn sàng")
                                                      : "Cloud: chưa có API key · CAD tham số cục bộ vẫn chạy" }
            }
        },
        TacTool { small: true; glyphCode: 0xE711; tint: S.hazard; tip: "Đóng"; onClicked: panel.closeRequested() }
    ]

    ScrollView {
        id: studioScroll
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
        width: studioScroll.availableWidth
        spacing: 12

        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: S.textDim; font.pixelSize: 12; lineHeight: 1.15
               text: "Mô tả ý tưởng hoặc thêm ảnh của vật thể bạn muốn dựng." }

        // ---------- dòng lệnh ----------
        TacInput {
            id: prompt
            Layout.fillWidth: true
            implicitHeight: 44
            placeholderText: "Mô tả mô hình cần tạo…"
            onAccepted: go.clicked()
            TacTool { id: go; text: "Tạo"; glyphCode: 0xE768; primary: true; tint: S.amber
                      Layout.rightMargin: 2
                      enabled: (prompt.text.trim().length > 2 || panel.referenceCount > 0) && (!panel.hasJob || panel.job.terminal)
                      onClicked: { if (!enabled) return
                                   if (panel.referenceCount > 0)
                                       nexa3d.generateFromReferences(prompt.text, panel.hq ? "high" : "standard", panel.references, panel.referenceMethod)
                                   else nexa3d.generate(prompt.text, panel.mode, panel.hq ? "high" : "standard") } }
        }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 9
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Ảnh tham chiếu"; color: Theme.textPrimary; font.pixelSize: 13; font.weight: Font.DemiBold }
                Text { text: panel.referenceCount + " / 6"; color: Theme.textMuted; font.pixelSize: 11 }
                Item { Layout.fillWidth: true }
                TacTool { small: true; text: "Xóa tất cả"; visible: panel.referenceCount > 0
                    onClicked: panel.references = ({}) }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: panel.width < 720 ? 3 : 6
                columnSpacing: 8; rowSpacing: 8
                Repeater {
                    model: [["front", "Trước"], ["back", "Sau"], ["left", "Trái"],
                            ["right", "Phải"], ["top", "Trên"], ["bottom", "Dưới"]]
                    ReferenceImageCard {
                        required property var modelData
                        Layout.fillWidth: true; Layout.preferredWidth: 130
                        label: modelData[1]
                        imageUrl: panel.references[modelData[0]] || ""
                        hint: "Ảnh góc " + modelData[1].toLowerCase() + " của cùng vật thể"
                        onClicked: { referencePicker.view = modelData[0]; referencePicker.open() }
                        onRemoveRequested: panel.setReference(modelData[0], "")
                    }
                }
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.textMuted; font.pixelSize: 11
                text: panel.referenceCount > 0
                    ? "Giữ cùng vật thể và hướng chụp. Thêm kích thước thật trong mô tả để xác định tỷ lệ."
                    : "Chọn các góc của cùng vật thể · JPG, PNG, WebP · tối đa 20 MB/ảnh"
            }
            RowLayout {
                visible: panel.referenceCount > 0; Layout.fillWidth: true
                TacTool { small: true; text: "Ảnh → 3D"; on: panel.referenceMethod === "auto"
                    onClicked: panel.referenceMethod = "auto" }
                TacTool { small: true; text: "CAD từ ảnh gốc"; on: panel.referenceMethod === "cad"
                    onClicked: panel.referenceMethod = "cad"
                    tip: "Dựng hình học từ ảnh gốc, không qua tách nền; vẫn là bản ước lượng." }
                Item { Layout.fillWidth: true }
                TacTool { small: true; text: "Chất lượng cao"; on: panel.hq; onClicked: panel.hq = !panel.hq }
            }
            RowLayout {
                visible: panel.referenceCount > 0; Layout.fillWidth: true
                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.textSecondary; font.pixelSize: 11
                    text: panel.referenceMethod === "cad"
                        ? "AI đọc ảnh gốc để dựng kết cấu. Chi tiết hoa, chữ và vật liệu có thể chưa giống; kết quả vẫn được kiểm tra."
                        : "Ảnh được gửi tới dịch vụ AI khi bấm Tạo. Kết quả được đối chiếu từng góc trước khi mở." }
            }
        }
        Flow {
            visible: panel.referenceCount === 0
            Layout.fillWidth: true; spacing: 6
            Text { text: "CHẾ ĐỘ"; color: S.iceDim; font.family: panel.tacFont; font.pixelSize: 10; font.letterSpacing: 2
                   Layout.rightMargin: 4 }
            Repeater {
                model: [["auto", "Tự động", "CAD tham số cho nhóm hỗ trợ, còn lại best effort"],
                        ["parametric", "CAD tham số", "Chỉ dựng CAD tham số cục bộ"],
                        ["cloud", "Cloud", "Tripo/Meshy (tốn credit)"]]
                TacTool { required property var modelData
                          small: true; text: modelData[1]; tip: modelData[2]; on: panel.mode === modelData[0]
                          onClicked: panel.mode = modelData[0] }
            }
            Rectangle { width: 1; height: 18; color: Qt.rgba(0.56, 0.85, 1, 0.2); Layout.leftMargin: 6; Layout.rightMargin: 6 }
            TacTool { small: true; text: panel.hq ? "Chất lượng cao · bật" : "Chất lượng cao"; on: panel.hq; tint: S.violet
                      onClicked: panel.hq = !panel.hq }
            Item { Layout.fillWidth: true }
        }

        // ---------- job đang chạy: pipeline giai đoạn ----------
        ColumnLayout {
            visible: panel.hasJob && panel.job.error_code === "reference_mask"
            Layout.fillWidth: true; spacing: 6
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: S.amber; font.pixelSize: 12
                text: "Ảnh tách nền chưa giữ đủ vật thể. Bạn có thể thử dựng CAD từ bộ ảnh gốc hiện tại, hoặc thay ảnh đã tách nền đầy đủ." }
            TacTool { text: "Thử CAD từ ảnh gốc"; tint: S.amber
                enabled: panel.referenceCount > 0 && panel.job.terminal
                onClicked: { panel.referenceMethod = "cad"; go.clicked() } }
        }
        Item {
            visible: panel.hasJob
            Layout.fillWidth: true
            implicitHeight: jobCol.implicitHeight + 24
            TacFrame { anchors.fill: parent; cut: 12; fill: "#0c8fd8ff"
                       stroke: Qt.rgba(panel.jobTone.r, panel.jobTone.g, panel.jobTone.b, 0.55) }
            Rectangle { x: 14; y: 0; width: 60; height: 2; color: panel.jobTone }
            ColumnLayout {
                id: jobCol
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 14; anchors.topMargin: 12
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true; spacing: 10
                    Text { text: "JOB"; color: S.amber; font.family: S.mono; font.pixelSize: 11 }
                    Text { text: (panel.job.label || "").toUpperCase(); color: "white"; font.family: panel.tacFont
                           font.pixelSize: 14; font.letterSpacing: 1.5; elide: Text.ElideRight; Layout.fillWidth: true }
                    Text { text: (panel.job.elapsed || 0).toFixed(1) + " s"; color: S.iceDim; font.family: S.mono; font.pixelSize: 12 }
                    Text { visible: !panel.job.terminal; text: Math.round((panel.job.progress || 0) * 100) + "%"
                           color: S.ice; font.family: panel.tacFont; font.pixelSize: 22 }
                    Text { visible: !!panel.job.terminal
                           text: panel.needsPolish ? "BẢN NHÁP" : ({"ready": "HOÀN TẤT", "failed": "THẤT BẠI", "cancelled": "ĐÃ HỦY", "needs_input": "CẦN THÊM THÔNG TIN"}[panel.job.state] || "")
                           color: panel.jobTone; font.family: panel.tacFont; font.pixelSize: 13; font.letterSpacing: 2 }
                    TacTool { visible: !panel.job.terminal; small: true; text: "Hủy"; glyphCode: 0xE711; tint: S.hazard
                              onClicked: nexa3d.cancelJob(panel.job.id) }
                    TacTool { visible: panel.job.state === "ready" || (panel.job.state === "failed" && !!panel.job.project_id)
                              small: true; primary: panel.job.state === "ready"; tint: panel.job.state === "ready" ? S.ok : S.amber
                              glyphCode: 0xF158
                              text: panel.job.state === "ready" ? "Mở" : "Xem bản chưa đạt"
                              onClicked: nexa3d.openModel(panel.job.project_id) }
                }
                // pipeline: ◆ PHÂN TÍCH ── ◆ DỰNG HÌNH ── …
                Item {
                    id: pipe
                    Layout.fillWidth: true
                    implicitHeight: panel.width < 700 ? 58 : 44
                    readonly property real step: width / panel.stages.length
                    Repeater {
                        model: panel.stages.length
                        Item {
                            required property int index
                            x: index * pipe.step; width: pipe.step; height: pipe.height
                            readonly property bool done: index < panel.reachedIdx || (index === panel.reachedIdx && panel.job.state === "ready")
                            readonly property bool cur: index === panel.reachedIdx && panel.job.state !== "ready"
                            readonly property color tone: cur ? (panel.job.terminal ? panel.jobTone : S.amber) : done ? S.ice : "#2a4660"
                            // vạch nối sang giai đoạn kế
                            Rectangle { visible: index < panel.stages.length - 1; x: parent.width / 2 + 10; y: 9
                                        width: parent.width - 20; height: 2
                                        color: parent.done ? Qt.rgba(0.56, 0.85, 1, 0.6) : Theme.border }
                            Rectangle {
                                x: parent.width / 2 - 7; y: 3; width: 14; height: 14; rotation: 45
                                color: parent.done ? S.ice : parent.cur ? Qt.rgba(parent.tone.r, parent.tone.g, parent.tone.b, 0.25) : "transparent"
                                border.color: parent.tone; border.width: 2
                                opacity: parent.cur && !panel.job.terminal ? panel.pulse : 1
                            }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; y: 26
                                   text: panel.stages[parent.index].k
                                   color: parent.cur ? "white" : parent.done ? S.textDim : Theme.textMuted
                                   width: parent.width - 4; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                                   font.family: panel.tacFont; font.pixelSize: 10; font.letterSpacing: 0.3 }
                        }
                    }
                }
                // thanh tiến độ 40 đoạn
                Row {
                    visible: !panel.job.terminal
                    Layout.fillWidth: true; spacing: 2
                    Repeater { model: 40
                        Rectangle { required property int index; width: (jobCol.width - 78) / 40; height: 5
                                    color: index < Math.round((panel.job.progress || 0) * 40) ? S.ice : Theme.surfaceRaised } }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Text { text: ">"; color: S.amber; font.family: S.mono; font.pixelSize: 12; Layout.alignment: Qt.AlignTop }
                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.textPrimary; font.family: S.mono; font.pixelSize: 12
                           text: panel.job.message || "" }
                }
                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: S.amber; font.pixelSize: 11; visible: text.length > 0
                       text: (panel.job.warnings || []).length ? "⚠ " + panel.job.warnings.join(" · ") : "" }
            }
        }

        // ---------- kho mô hình gần đây ----------
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Text { text: "KHO"; color: S.amber; font.family: S.mono; font.pixelSize: 11 }
            Text { text: "MÔ HÌNH GẦN ĐÂY"; color: Theme.textPrimary; font.family: panel.tacFont; font.pixelSize: 12; font.letterSpacing: 1.4 }
            Text { text: "[" + (nexa3d.models ? nexa3d.models.length : 0) + "]"; color: S.iceDim; font.family: S.mono; font.pixelSize: 11 }
            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(0.56, 0.85, 1, 0.14) }
        }
        GridView {
            id: grid
            Layout.fillWidth: true; Layout.preferredHeight: 220
            clip: true
            cellWidth: 176; cellHeight: 200
            model: nexa3d.models
            ScrollBar.vertical: ScrollBar {}
            delegate: Item {
                id: card
                required property var modelData
                required property int index
                width: 166; height: 190
                readonly property bool ok: modelData.status === "ready"
                readonly property color tone: ok ? S.ok : S.amber
                TacFrame { anchors.fill: parent; cut: 10; fill: gm.containsMouse ? "#1a8fd8ff" : "#0a8fd8ff"
                           stroke: gm.containsMouse ? S.ice : Qt.rgba(0.56, 0.85, 1, 0.25) }
                Rectangle { x: 10; y: 0; width: 28; height: 2; color: card.tone }
                Text { x: card.width - width - 10; y: 7; text: "M" + ("0" + (card.index + 1)).slice(-2)
                       color: Theme.borderStrong; font.family: S.mono; font.pixelSize: 10 }
                Image { x: 8; y: 18; width: 150; height: 116; fillMode: Image.PreserveAspectFit; asynchronous: true; cache: false
                        source: card.modelData.thumb_url || "" }
                Column {
                    x: 10; y: 140; width: 146; spacing: 3
                    Text { width: parent.width; text: card.modelData.name; color: "white"; font.pixelSize: 12; elide: Text.ElideRight }
                    Row {
                        spacing: 6
                        Text { text: Math.round(card.modelData.quality_score || 0); color: card.tone; font.family: panel.tacFont; font.pixelSize: 13 }
                        Text { text: "/100 · " + (card.ok ? "ĐẠT" : "CHƯA ĐẠT"); color: S.iceDim; font.family: panel.tacFont
                               font.pixelSize: 10; font.letterSpacing: 1; anchors.baseline: parent.children[0].baseline }
                    }
                }
                MouseArea { id: gm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: nexa3d.openModel(card.modelData.id) }
            }
        }
    }
    }
    Component.onCompleted: nexa3d.refreshModels()
}
