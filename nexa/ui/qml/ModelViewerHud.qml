import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "TacStyle.js" as S

// Lớp HUD chiến thuật phủ trên cảnh 3D: thanh nhiệm vụ (tên · số liệu · điểm chất lượng · nhóm nút), cảnh báo sọc,
// la bàn trục theo camera, khung ngắm, HUD cử chỉ, nạp / lỗi. Không chặn chuột ở vùng trống (kéo xoay vẫn tới cảnh).
Item {
    id: hud
    property var viewer
    property real rightInset: 0                     // bề ngang cây bộ phận đang mở (để HUD tránh ra)
    readonly property var mdl: viewer.mdl || ({})
    readonly property real barBottom: bar.y + bar.height
    readonly property string tacFont: S.tacFont(Qt.fontFamilies())
    readonly property string iconFont: S.iconFont(Qt.fontFamilies())
    readonly property int partCount: viewer.parts.length
    readonly property string modeText: mdl.mode === "parametric" ? "CAD THAM SỐ" : mdl.mode === "cloud" ? ("CLOUD " + (mdl.provider || "")).toUpperCase() : "CAD DSL"
    readonly property real score: Math.round(mdl.quality_score || 0)
    readonly property color qTone: mdl.quality_status === "best_effort" ? S.amber : (mdl.status === "ready" ? S.ok : S.hazard)
    readonly property string qWord: mdl.reference_source ? "THAM CHIẾU" : (mdl.quality_status === "best_effort" ? "BEST EFFORT" : (mdl.status === "ready" ? "ĐẠT" : "CHƯA ĐẠT"))
    property bool warnOpen: false
    ProductMediaDialog { id: mediaDialog }
    BuildDossierDialog { id: buildDialog }

    // ---------- khung ngắm: nẹp 4 góc vùng nhìn + chữ thập mờ ở giữa ----------
    Item {
        id: sight
        anchors.fill: parent
        anchors.topMargin: hud.barBottom + 8; anchors.bottomMargin: 10
        anchors.leftMargin: 10; anchors.rightMargin: 10 + hud.rightInset
        Repeater {
            model: 4
            Item {
                required property int index
                readonly property bool r: index % 2 === 1
                readonly property bool b: index >= 2
                x: r ? sight.width - 22 : 0; y: b ? sight.height - 22 : 0
                width: 22; height: 22
                Rectangle { x: parent.r ? 20 : 0; width: 2; height: 22; color: S.ice; opacity: 0.2 }
                Rectangle { y: parent.b ? 20 : 0; width: 22; height: 2; color: S.ice; opacity: 0.2 }
            }
        }
        Item {
            anchors.centerIn: parent; width: 36; height: 36; opacity: 0.08
            Rectangle { anchors.centerIn: parent; width: 36; height: 1; color: S.ice }
            Rectangle { anchors.centerIn: parent; width: 1; height: 36; color: S.ice }
            Rectangle { anchors.centerIn: parent; width: 10; height: 10; color: "transparent"; border.color: S.ice; rotation: 45 }
        }
    }

    // ---------- thanh nhiệm vụ ----------
    component Group: Row {
        property string label: ""
        spacing: 4
        Text { text: parent.label; color: S.iceDim; font.family: hud.tacFont; font.pixelSize: 10; font.letterSpacing: 2
               anchors.verticalCenter: parent.verticalCenter; rightPadding: 4 }
    }

    Item {
        id: bar
        x: 10; y: 10
        width: hud.width - 20
        height: barCol.implicitHeight + 20
        TacFrame { anchors.fill: parent; cut: 12; fill: Theme.panelGlass; stroke: Qt.rgba(0.56, 0.85, 1, 0.22) }
        Rectangle { x: 14; y: 0; width: 56; height: 2; color: S.amber }
        Column {
            id: barCol
            x: 16; y: 10
            width: bar.width - 32
            spacing: 10
            RowLayout {
                width: parent.width
                spacing: 12
                Text { text: "02"; color: S.amber; font.family: S.mono; font.pixelSize: 11; Layout.alignment: Qt.AlignVCenter }
                Column {
                    Layout.fillWidth: true
                    spacing: 2
                    Text { width: parent.width; text: (hud.mdl.name || "Mô hình 3D").toUpperCase(); color: Theme.textPrimary
                           font.family: hud.tacFont; font.pixelSize: 17; font.letterSpacing: 2; elide: Text.ElideRight }
                    Text { width: parent.width; elide: Text.ElideRight; color: S.iceDim; font.family: S.mono; font.pixelSize: 11
                           text: hud.partCount + " BỘ PHẬN  ·  " + (hud.mdl.triangles || 0).toLocaleString(Qt.locale(), "f", 0)
                                 + " TAM GIÁC  ·  " + hud.modeText + (hud.mdl.has_assembly ? "  ·  ASSEMBLY" : "") }
                }
                // điểm chất lượng: số lớn + chữ trạng thái + thanh 10 đoạn
                Item {
                    objectName: "qualityBlock"
                    implicitWidth: qRow.implicitWidth + 22; implicitHeight: 42
                    TacFrame { anchors.fill: parent; cut: 8; fill: Qt.rgba(hud.qTone.r, hud.qTone.g, hud.qTone.b, 0.1)
                               stroke: Qt.rgba(hud.qTone.r, hud.qTone.g, hud.qTone.b, 0.7) }
                    Row {
                        id: qRow
                        anchors.centerIn: parent
                        spacing: 8
                        Text { id: qNum; text: hud.mdl.reference_source ? "CAD" : hud.score; color: "#f2fbff"; font.family: hud.tacFont; font.pixelSize: 24
                               anchors.verticalCenter: parent.verticalCenter }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Text { text: hud.qWord; color: hud.qTone; font.family: hud.tacFont; font.pixelSize: 11; font.letterSpacing: 2 }
                            Row {
                                spacing: 2
                                Repeater { model: 10
                                    Rectangle { required property int index; width: 5; height: 4
                                                color: index < Math.round(hud.score / 10) ? hud.qTone : Theme.border } }
                            }
                        }
                    }
                    ToolTip.visible: qMouse.containsMouse; ToolTip.delay: 400
                    ToolTip.text: hud.mdl.reference_source ? "Nguồn: " + hud.mdl.reference_source + ". Mô hình mô phỏng, chưa phải bản vẽ chế tạo." : "Điểm chất lượng hình học " + hud.score + "/100"
                    MouseArea { id: qMouse; anchors.fill: parent; hoverEnabled: true }
                }
                TacTool { glyphCode: 0xE711; tint: S.hazard; tip: "Đóng trình xem (Esc)"; Layout.alignment: Qt.AlignVCenter
                          onClicked: nexa3d.closeViewer() }
            }
            Flow {
                id: tools
                objectName: "viewerTools"
                width: parent.width
                spacing: 14
                Group {
                    label: "SẢN PHẨM"
                    TacTool { small: true; text: "Ảnh & video"; onClicked: mediaDialog.open() }
                    TacTool { small: true; text: "Linh kiện & lắp ráp"; onClicked: { nexa3d.refreshBuildDossier(); buildDialog.open() } }
                }
                Group {
                    label: "HIỂN THỊ"
                    TacTool { small: true; text: "Chuẩn"; on: hud.viewer.renderMode === "normal"; onClicked: nexa3d.setRenderMode("normal") }
                    TacTool { small: true; text: "X-quang"; on: hud.viewer.renderMode === "xray"
                              onClicked: nexa3d.setRenderMode(hud.viewer.renderMode === "xray" ? "normal" : "xray") }
                    TacTool { small: true; text: "Khung dây"; on: hud.viewer.renderMode === "wireframe"
                              onClicked: nexa3d.setRenderMode(hud.viewer.renderMode === "wireframe" ? "normal" : "wireframe") }
                }
                Group {
                    label: "THAO TÁC"
                    TacTool { small: true; glyphCode: hud.viewer.exploded ? 0xE73F : 0xE740; text: hud.viewer.exploded ? "Lắp lại" : "Tách rời"
                              on: hud.viewer.exploded; tint: S.amber; enabled: hud.mdl.has_assembly === true
                              tip: hud.mdl.has_assembly === true ? "Tách / lắp các bộ phận" : "Mô hình một khối — không tách được"
                              onClicked: hud.viewer.exploded ? nexa3d.collapse() : nexa3d.explode() }
                    TacTool { small: true; glyphCode: hud.viewer.animating ? 0xE769 : 0xE768
                              text: hud.viewer.animating ? "Dừng" : "Chuyển động"; on: hud.viewer.animating; tint: S.amber
                              enabled: !!hud.mdl.motion_mode && hud.mdl.motion_mode !== "none"
                              onClicked: nexa3d.toggleMotion() }
                }
                Group {
                    label: "CAMERA"
                    TacTool { small: true; glyphCode: 0xE890; text: "Hiện tất cả"; onClicked: nexa3d.showAll() }
                    TacTool { small: true; glyphCode: 0xE72C; text: "Đặt lại"; onClicked: nexa3d.resetView() }
                }
                Group {
                    label: "BẢNG"
                    TacTool { small: true; glyphCode: 0xE8FD; text: "Bộ phận"; on: hud.viewer.showTree; tip: "Cây bộ phận"
                              onClicked: hud.viewer.showTree = !hud.viewer.showTree }
                    TacTool { small: true; glyphCode: 0xE815; text: nexa3d.mode3d.camera ? "Cử chỉ: bật" : "Cử chỉ"; tint: S.violet
                              on: nexa3d.mode3d.camera === true; tip: "Điều khiển mô hình bằng tay (bật camera)"
                              onClicked: nexa3d.toggleCamera() }
                }
            }
        }
    }

    // ---------- cảnh báo: dải sọc cam, gọn một dòng, bấm để xem hết ----------
    Item {
        id: warnBox
        readonly property var list: hud.mdl.warnings || []
        visible: list.length > 0
        x: 10; y: hud.barBottom + 10
        width: Math.min(hud.width - 20 - hud.rightInset - 20, 640)
        height: warnCol.implicitHeight + 12
        TacFrame { anchors.fill: parent; cut: 7; fill: "#e61a1004"; stroke: Qt.rgba(1, 0.68, 0.26, 0.55) }
        Canvas {   // sọc cảnh báo bên trái
            x: 1; y: 1; width: 12; height: parent.height - 2
            onHeightChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                ctx.fillStyle = Theme.amber
                for (var yy = -12; yy < height + 12; yy += 8) {
                    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(width, yy - 6); ctx.lineTo(width, yy - 2); ctx.lineTo(0, yy + 4); ctx.closePath(); ctx.fill()
                }
            }
        }
        Column {
            id: warnCol
            x: 22; y: 6
            width: parent.width - 30
            spacing: 4
            Repeater {
                model: hud.warnOpen ? warnBox.list : warnBox.list.slice(0, 1)
                Text {
                    required property var modelData
                    required property int index
                    width: warnCol.width
                    text: (index === 0 ? "⚠ " : "· ") + modelData
                          + (!hud.warnOpen && warnBox.list.length > 1 ? "   [+" + (warnBox.list.length - 1) + "]" : "")
                    color: "#ffd9a0"; font.pixelSize: 12
                    wrapMode: hud.warnOpen ? Text.Wrap : Text.NoWrap; elide: hud.warnOpen ? Text.ElideNone : Text.ElideRight
                }
            }
        }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: hud.warnOpen = !hud.warnOpen }
    }

    // ---------- lỗi nạp asset ----------
    Item {
        visible: nexa3d.loadError !== ""
        x: 10; y: warnBox.visible ? warnBox.y + warnBox.height + 8 : hud.barBottom + 10
        width: Math.min(hud.width - 40 - hud.rightInset, 600); height: errTxt.implicitHeight + 14
        TacFrame { anchors.fill: parent; cut: 7; fill: "#e62a0808"; stroke: S.hazard }
        Text { id: errTxt; anchors.fill: parent; anchors.margins: 7; anchors.leftMargin: 12; color: "#ffc9c4"; font.pixelSize: 12
               wrapMode: Text.Wrap; text: "LỖI ASSET · " + nexa3d.loadError }
    }

    // ---------- la bàn trục (theo camera) + số liệu camera, góc dưới phải vùng nhìn ----------
    Row {
        anchors.right: parent.right; anchors.rightMargin: 22 + hud.rightInset
        anchors.bottom: parent.bottom; anchors.bottomMargin: 20
        spacing: 12
        Column {
            anchors.bottom: parent.bottom
            spacing: 3
            Text { anchors.right: parent.right; color: S.iceDim; font.family: S.mono; font.pixelSize: 10
                   text: "YAW " + ("00" + Math.round(((hud.viewer.smYaw % 360) + 360) % 360)).slice(-3) + "°  PITCH "
                         + Math.round(hud.viewer.smPitch) + "°  ZOOM " + hud.viewer.smZoom.toFixed(2) }
            Text { anchors.right: parent.right; visible: nexa.showFps; color: Theme.borderStrong; font.family: S.mono; font.pixelSize: 10
                   text: "FPS " + hud.viewer.fps.toFixed(0) + "  ·  NẠP " + (hud.mdl.load_ms || 0) + " MS" + (hud.mdl.lod ? "  ·  LOD" : "")
                         + (nexa3d.perf.gesture_latency_ms ? "  ·  TRỄ CỬ CHỈ " + nexa3d.perf.gesture_latency_ms + " MS" : "") }
        }
        Canvas {
            id: gizmo
            objectName: "axisGizmo"
            width: 64; height: 64
            property real yaw: hud.viewer.smYaw
            property real pitch: hud.viewer.smPitch
            onYawChanged: requestPaint(); onPitchChanged: requestPaint()
            renderStrategy: Canvas.Cooperative
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                var cx = width / 2, cy = height / 2, L = 22
                ctx.strokeStyle = "rgba(143,216,255,0.18)"; ctx.lineWidth = 1
                ctx.beginPath(); ctx.arc(cx, cy, 29, 0, Math.PI * 2); ctx.stroke()
                var a = yaw * Math.PI / 180, b = pitch * Math.PI / 180
                // trục kỹ thuật (X trước, Y trái, Z lên) = asset (Z, X, Y)
                var axes = [["X", [0, 0, 1], Theme.danger], ["Y", [1, 0, 0], Theme.success], ["Z", [0, 1, 0], Theme.accent]]
                var pts = []
                for (var i = 0; i < 3; i++) {
                    var v = axes[i][1]
                    var x1 = v[0] * Math.cos(a) + v[2] * Math.sin(a), z1 = -v[0] * Math.sin(a) + v[2] * Math.cos(a)
                    var y2 = v[1] * Math.cos(b) - z1 * Math.sin(b), z2 = v[1] * Math.sin(b) + z1 * Math.cos(b)
                    pts.push({ n: axes[i][0], c: axes[i][2], x: cx + x1 * L, y: cy - y2 * L, z: z2 })
                }
                pts.sort(function(p, q) { return p.z - q.z })
                ctx.font = "bold 10px Consolas"; ctx.textAlign = "center"; ctx.textBaseline = "middle"
                for (var j = 0; j < 3; j++) {
                    var p = pts[j]
                    ctx.globalAlpha = p.z < -0.2 ? 0.45 : 1
                    ctx.strokeStyle = p.c; ctx.lineWidth = 2
                    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(p.x, p.y); ctx.stroke()
                    ctx.fillStyle = p.c
                    ctx.fillText(p.n, cx + (p.x - cx) * 1.28, cy + (p.y - cy) * 1.28)
                }
                ctx.globalAlpha = 1
                ctx.fillStyle = Theme.amber; ctx.fillRect(cx - 1.5, cy - 1.5, 3, 3)
            }
        }
    }

    // ---------- HUD cử chỉ ----------
    Item {
        id: gHud
        property var g: nexa3d.gesture
        readonly property bool armed: g && (g.state === "EXPLODE_ARMED" || g.state === "OPEN_HOLD")
        readonly property color tone: armed ? S.amber : S.violet
        visible: nexa3d.mode3d.camera === true && g && g.label !== undefined && g.label !== ""
        anchors.horizontalCenter: sight.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 28
        width: Math.max(300, gTxt.implicitWidth + 48); height: 60
        TacFrame { anchors.fill: parent; cut: 10; fill: "#e6060b18"; stroke: gHud.tone }
        Column {
            anchors.centerIn: parent; spacing: 8
            Text { id: gTxt; anchors.horizontalCenter: parent.horizontalCenter; color: "white"; font.family: hud.tacFont
                   font.pixelSize: 14; font.letterSpacing: 1.5; text: gHud.g && gHud.g.label ? gHud.g.label.toUpperCase() : "" }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: gHud.g && (gHud.g.state === "FIST_HOLD" || gHud.g.state === "OPEN_HOLD" || gHud.g.state === "IDLE") && gHud.g.progress > 0
                spacing: 2
                Repeater { model: 24
                    Rectangle { required property int index; width: 8; height: 5
                                color: index < Math.round((gHud.g && gHud.g.progress ? gHud.g.progress : 0) * 24) ? gHud.tone : Theme.border } }
            }
        }
    }

    // ---------- đang nạp ----------
    Item {
        visible: nexa3d.loading
        anchors.centerIn: sight
        width: 300; height: 70
        TacFrame { anchors.fill: parent; cut: 10; fill: Theme.panelGlass; stroke: S.ice }
        Row {
            anchors.centerIn: parent; spacing: 14
            Item {
                width: 30; height: 30; anchors.verticalCenter: parent.verticalCenter
                Rectangle { anchors.fill: parent; radius: 15; color: "transparent"; border.color: Qt.rgba(0.56, 0.85, 1, 0.2); border.width: 2 }
                Item {
                    anchors.fill: parent
                    RotationAnimator on rotation { from: 0; to: 360; duration: 1200; loops: Animation.Infinite; running: nexa3d.loading }
                    Rectangle { x: 12; y: -1; width: 6; height: 4; color: S.amber }
                    Rectangle { x: 13; y: 27; width: 4; height: 4; color: S.ice }
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: 3
                Text { text: "ĐANG NẠP MÔ HÌNH"; color: "white"; font.family: hud.tacFont; font.pixelSize: 14; font.letterSpacing: 1.4 }
                Text { text: "dựng lưới · vật liệu · bóng đổ"; color: S.iceDim; font.family: S.mono; font.pixelSize: 11 }
            }
        }
    }
}
