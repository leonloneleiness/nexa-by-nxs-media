    // ---------- nền: lưới kỹ thuật mờ + tối dần ra mép ----------
    Canvas {
        anchors.fill: parent
        visible: !nexa.compact
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        renderStrategy: Canvas.Cooperative
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var g = ctx.createLinearGradient(0, 0, 0, height)
            g.addColorStop(0, "#040b16"); g.addColorStop(0.6, "#02070f"); g.addColorStop(1, "#040a12")
            ctx.fillStyle = g; ctx.fillRect(0, 0, width, height)
            for (var x = 0, i = 0; x < width; x += 40, i++) {
                ctx.fillStyle = i % 5 === 0 ? "rgba(143,216,255,0.055)" : "rgba(143,216,255,0.028)"
                ctx.fillRect(x, 0, 1, height)
            }
            for (var y = 0, j = 0; y < height; y += 40, j++) {
                ctx.fillStyle = j % 5 === 0 ? "rgba(143,216,255,0.055)" : "rgba(143,216,255,0.028)"
                ctx.fillRect(0, y, width, 1)
            }
            var r = Math.max(width, height) * 0.75
            var v = ctx.createRadialGradient(width / 2, height * 0.45, r * 0.25, width / 2, height * 0.45, r)
            v.addColorStop(0, "rgba(2,6,12,0)"); v.addColorStop(1, "rgba(1,3,7,0.85)")
            ctx.fillStyle = v; ctx.fillRect(0, 0, width, height)
        }
    }

    // ---------- chế độ thu gọn ----------
    Item {
        anchors.fill: parent
        visible: nexa.compact
        Rectangle { anchors.fill: parent; radius: width / 2; color: "#e0030810" }
        TacticalCore { anchors.fill: parent; appState: nexa.state; micLevel: nexa.micLevel; outLevel: nexa.outLevel; outBands: nexa.outBands
                       effects: nexa.effects === "full" ? "reduced" : nexa.effects }
        MouseArea {
            anchors.fill: parent
            property point press
            onPressed: (m) => press = Qt.point(m.x, m.y)
            onPositionChanged: (m) => { if (pressed) { win.x += m.x - press.x; win.y += m.y - press.y } }
            onDoubleClicked: win.enterCompact(false)
        }
        Text { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 6
               text: nexa.stateLabel.toUpperCase(); color: "white"; font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 2
               style: Text.Outline; styleColor: "#040914" }
        Rectangle {
            anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 6
            width: 26; height: 26; radius: 4; color: "#3a0c0c"; border.color: win.hazard
            Rectangle { anchors.centerIn: parent; width: 9; height: 9; color: win.hazard }
            MouseArea { anchors.fill: parent; onClicked: nexa.stop() }
        }
    }

    // ---------- giao diện đầy đủ ----------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 10
        spacing: 8
        visible: !nexa.compact

        // Thanh tiêu đề: logo · đồng hồ nhiệm vụ · icon trạng thái · Cài đặt / Thu gọn / Thoát
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Shape {   // logo lục giác
                implicitWidth: 30; implicitHeight: 30
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    fillColor: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.12); strokeColor: win.ice; strokeWidth: 1.5
                    joinStyle: ShapePath.MiterJoin
                    PathPolyline { path: [Qt.point(15, 1), Qt.point(27.1, 8), Qt.point(27.1, 22), Qt.point(15, 29),
                                          Qt.point(2.9, 22), Qt.point(2.9, 8), Qt.point(15, 1)] }
                }
                Rectangle { anchors.centerIn: parent; width: 8; height: 8; rotation: 45; color: win.amber }
            }
            Column {
                spacing: 1
                Row {
                    spacing: 12
                    Text { text: "NEXA"; color: "#e8f6ff"; font.family: win.tacFont; font.pixelSize: 24; font.bold: true; font.letterSpacing: 8 }
                    Text { visible: !win.narrow; text: "TACTICAL ASSISTANT"; color: win.amber; font.family: win.tacFont
                           font.pixelSize: 11; font.letterSpacing: 3; anchors.bottom: parent.bottom; anchors.bottomMargin: 5 }
                }
                Text { text: "Trợ lý của anh Nguyễn Xuân Sơn · NXS MEDIA"; color: win.iceDim; font.pixelSize: 11 }
            }
            Item { Layout.fillWidth: true }
            Column {   // đồng hồ nhiệm vụ
                visible: !win.stacked
                spacing: 1
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: win.missionClock; color: win.ice
                       font.family: win.monoFont; font.pixelSize: 16; font.letterSpacing: 1 }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "PHIÊN · " + win.wallClock; color: "#4f6f8c"
                       font.family: win.monoFont; font.pixelSize: 10 }
            }
            Item { Layout.fillWidth: true }
            // tiến độ việc dài (chỉ hiện khi đang chạy)
            Chip { visible: nexa3d.activeJob.id !== undefined && nexa3d.activeJob.terminal === false; label: "3D"
                   value: (nexa3d.activeJob.label || "") + " " + Math.round((nexa3d.activeJob.progress || 0) * 100) + "%"; level: 2
                   MouseArea { anchors.fill: parent; onClicked: nexa3d.workspace = true } }
            Chip { visible: nexaCode.busy; label: "Code"
                   value: (nexaCode.job.message || "") + " " + Math.round((nexaCode.job.progress || 0) * 100) + "%"; level: 2
                   MouseArea { anchors.fill: parent; onClicked: nexaCode.openPanel() } }
            Item {   // khung vát chứa icon trạng thái
                implicitWidth: statusRow.implicitWidth + 18; implicitHeight: 40
                Chamfer { anchors.fill: parent; cut: 8; fill: "#b3071424"; stroke: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.22) }
            Row {
                id: statusRow
                objectName: "statusIcons"
                anchors.centerIn: parent
                spacing: 3
                StatusIcon { visible: nexa.visionSending; glyphCode: 0xE7B3; label: "Đang gửi ảnh"; value: "Gemini"; level: 2 }
                StatusIcon { glyphCode: 0xE720; label: "Mic"; value: (nexa.status.mic && nexa.status.mic.ok) ? "bật" : "lỗi"
                             level: (nexa.status.mic && nexa.status.mic.ok) ? 1 : 3 }
                StatusIcon { glyphCode: 0xE722; label: "Camera"; value: nexa.cameraOn ? "ĐANG DÙNG" : "tắt"; level: nexa.cameraOn ? 2 : 0
                             onClicked: gesturePanel.visible = !gesturePanel.visible }
                StatusIcon { glyphCode: 0xE99A; label: "AI"; value: (nexa.status.ai && nexa.status.ai.ok) ? "Gemini" : "Cơ bản"
                             level: (nexa.status.ai && nexa.status.ai.ok) ? 1 : 2 }
                StatusIcon { glyphCode: 0xE8C1; label: "Nhận dạng giọng (STT)"
                             value: (nexa.status.stt && nexa.status.stt.ready) ? nexa.status.stt.model : ((nexa.status.stt && nexa.status.stt.loading) ? "đang nạp" : "chưa sẵn sàng")
                             level: (nexa.status.stt && nexa.status.stt.ready) ? 1 : 2 }
                StatusIcon { glyphCode: 0xE767; label: "Giọng nói"
                             value: (nexa.status.tts && nexa.status.tts.backend) ? nexa.status.tts.backend : ((nexa.status.tts && nexa.status.tts.chain && nexa.status.tts.chain.length) ? "chờ" : "chữ")
                             level: (nexa.status.tts && nexa.status.tts.backend) ? 1 : 0 }
                StatusIcon { glyphCode: 0xE71B; label: "Bridge trình duyệt"
                             value: (nexa.status.bridge && nexa.status.bridge.connected) ? nexa.status.bridge.browsers.join(", ") : "chưa nối"
                             level: (nexa.status.bridge && nexa.status.bridge.connected) ? 1 : 0 }
                StatusIcon { glyphCode: nexa.status.autonomy === "full" ? 0xE785 : 0xE72E; label: "Quyền"
                             value: nexa.status.autonomy === "full" ? "TOÀN QUYỀN" : "tiêu chuẩn"
                             level: nexa.status.autonomy === "full" ? 2 : 1 }
            }
            }
            Rectangle { implicitWidth: 1; implicitHeight: 24; color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2)
                        Layout.leftMargin: 2; Layout.rightMargin: 2 }
            HeaderButton { glyphCode: 0xE713; tip: "Cài đặt"; onClicked: settingsPopup.open() }
            HeaderButton { glyphCode: 0xE73F; tip: "Thu gọn thành lõi nổi (nhấp đúp để mở lại)"; onClicked: win.enterCompact(true) }
            HeaderButton { glyphCode: 0xE7E8; tip: "Thoát NEXA"; hoverTint: win.hazard; onClicked: nexa.quit() }
        }
        // vạch ngang có khấc dưới thanh tiêu đề
        Item {
            Layout.fillWidth: true
            implicitHeight: 6
            Rectangle { y: 2; width: parent.width; height: 1; color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.16) }
            Rectangle { y: 1; width: 110; height: 3; color: win.amber }
            Rectangle { x: 116; y: 1; width: 18; height: 3; color: win.amber; opacity: 0.5 }
            Row {
                anchors.right: parent.right; spacing: 7
                Repeater { model: 28; Rectangle { required property int index; width: 1; height: index % 4 === 0 ? 6 : 3
                                                  color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.35) } }
            }
        }

        // Nội dung chính: SYS | radar | LOG
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            // Bảng hệ thống bên trái (màn rộng): CPU / RAM / GPU / AI với số lớn, đồ thị và vạch chia
            TacPanel {
                id: sysPanel
                objectName: "statsRing"
                title: "SYS · HỆ THỐNG"; code: "01"; accent: win.ice
                Layout.fillHeight: true
                Layout.preferredWidth: 236
                visible: win.sysDocked && hasData
                readonly property var st: nexa.sysStats
                readonly property bool hasData: st.cpu !== undefined
                readonly property bool hasGpu: st.gpu !== null && st.gpu !== undefined
                property var cpuH: []
                property var ramH: []
                property var gpuH: []
                property var aiH: []
                function push(arr, v) { var a = arr.slice(-39); a.push(v); return a }
                onStChanged: {
                    if (!hasData) return
                    cpuH = push(cpuH, (st.cpu || 0) / 100)
                    ramH = push(ramH, (st.ram || 0) / 100)
                    gpuH = push(gpuH, hasGpu ? st.gpu / 100 : 0)
                    aiH = push(aiH, Math.min(1, (st.ai_ms || 0) / 5000))
                }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 12
                    StatBlock { Layout.fillWidth: true; label: "CPU"; sub: "TẢI"; v: (sysPanel.st.cpu || 0) / 100
                                big: sysPanel.hasData ? Math.round(sysPanel.st.cpu || 0) : "—"; unit: "%"; hist: sysPanel.cpuH }
                    StatBlock { Layout.fillWidth: true; label: "RAM"; sub: "BỘ NHỚ"; v: (sysPanel.st.ram || 0) / 100
                                big: sysPanel.hasData ? Math.round(sysPanel.st.ram || 0) : "—"; unit: "%"; hist: sysPanel.ramH }
                    StatBlock { Layout.fillWidth: true; label: "GPU"
                                sub: sysPanel.st.vram !== null && sysPanel.st.vram !== undefined ? "VRAM " + Math.round(sysPanel.st.vram) + "%" : "—"
                                v: sysPanel.hasGpu ? sysPanel.st.gpu / 100 : -1
                                big: sysPanel.hasGpu ? Math.round(sysPanel.st.gpu) : "—"; unit: sysPanel.hasGpu ? "%" : ""; hist: sysPanel.gpuH }
                    StatBlock { Layout.fillWidth: true; label: "AI"; sub: "PHẢN HỒI"
                                v: Math.min(1, (sysPanel.st.ai_ms || 0) / 5000)
                                big: !sysPanel.st.ai_ms ? "—" : sysPanel.st.ai_ms < 1000 ? Math.round(sysPanel.st.ai_ms) : (sysPanel.st.ai_ms / 1000).toFixed(1)
                                unit: !sysPanel.st.ai_ms ? "" : sysPanel.st.ai_ms < 1000 ? "ms" : "s"; hist: sysPanel.aiH }
                    Item { Layout.fillHeight: true }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.14) }
                    Column {
                        Layout.fillWidth: true
                        spacing: 3
                        Text { text: "MỤC TIÊU"; color: win.iceDim; font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 3 }
                        Text { width: parent.width; text: nexa.foreground.length > 3 ? "▸ " + nexa.foreground : "▸ —"
                               color: "#cfe9ff"; font.family: win.monoFont; font.pixelSize: 12; elide: Text.ElideMiddle }
                    }
                }
            }

            // Sân khấu: lõi radar ở giữa, trạng thái + phụ đề bên dưới, thanh lệnh vát góc ở đáy
            Item {
                id: stage
                objectName: "stage"
                Layout.fillWidth: !win.codeShown
                Layout.preferredWidth: win.codeShown ? win.sideNexaWidth : -1
                Layout.maximumWidth: win.codeShown ? win.sideNexaWidth : Number.POSITIVE_INFINITY
                Layout.fillHeight: true
                clip: false
                readonly property bool tight: width < 560
                readonly property real drawerW: Math.min(width - 24, 400)

                // Thông số rút gọn ở đỉnh sân khấu khi bảng SYS ẩn (màn hẹp / có bảng bên phải)
                Item {
                    id: statsStrip
                    objectName: "statsStrip"
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 4
                    height: 34
                    visible: !sysPanel.visible && sysPanel.hasData
                    readonly property var st: nexa.sysStats
                    Row {
                        anchors.left: parent.left
                        spacing: 22
                        Meter { label: "CPU"; v: (statsStrip.st.cpu || 0) / 100; valueText: win.pct(statsStrip.st.cpu) }
                        Meter { visible: !stage.tight; label: "GPU"; v: sysPanel.hasGpu ? statsStrip.st.gpu / 100 : -1
                                valueText: win.pct(statsStrip.st.gpu) }
                    }
                    Row {
                        anchors.right: parent.right
                        spacing: 22
                        Meter { visible: !stage.tight; label: "AI"; v: Math.min(1, (statsStrip.st.ai_ms || 0) / 5000)
                                valueText: win.ms(statsStrip.st.ai_ms) }
                        Meter { label: "RAM"; v: (statsStrip.st.ram || 0) / 100; valueText: win.pct(statsStrip.st.ram) }
                    }
                }

                ColumnLayout {
                    id: stageBody
                    anchors.fill: parent
                    anchors.topMargin: statsStrip.visible ? 46 : 4
                    spacing: 8

                    Item {
                        id: coreArea
                        objectName: "orbArea"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        readonly property real coreSize: Math.min(width * 0.9, height, 640)
                        TacticalCore {
                            id: mainOrb
                            anchors.centerIn: parent
                            width: coreArea.coreSize; height: width
                            appState: nexa.state; micLevel: nexa.micLevel; outLevel: nexa.outLevel; outBands: nexa.outBands; effects: nexa.effects
                        }
                        MouseArea { anchors.fill: mainOrb; onDoubleClicked: nexa.wake() }
                        // đồng hồ mức vào (mic) / ra (giọng NEXA) hai bên lõi
                        Repeater {
                            model: [{ k: "MIC", v: nexa.micLevel, left: true }, { k: "OUT", v: nexa.outLevel, left: false }]
                            Column {
                                required property var modelData
                                visible: !stage.tight
                                spacing: 4
                                anchors.verticalCenter: parent.verticalCenter
                                x: modelData.left ? Math.max(4, mainOrb.x - 34) : Math.min(coreArea.width - 26, mainOrb.x + mainOrb.width + 12)
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.k; color: win.iceDim
                                       font.family: win.tacFont; font.pixelSize: 10; font.letterSpacing: 2 }
                                Item {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 6; height: 96
                                    Rectangle { anchors.fill: parent; color: "#0d1f33"; border.color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2) }
                                    Rectangle { anchors.bottom: parent.bottom; width: parent.width
                                                height: parent.height * Math.max(0, Math.min(1, modelData.v))
                                                color: modelData.left ? win.ice : win.amber
                                                Behavior on height { NumberAnimation { duration: 90 } } }
                                }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: Math.round(modelData.v * 100)
                                       color: "#7fa3c0"; font.family: win.monoFont; font.pixelSize: 10 }
                            }
                        }
                        Text {
                            visible: nexa.showFps
                            anchors.left: parent.left; anchors.top: parent.top; anchors.leftMargin: 8
                            text: "FPS " + mainOrb.measuredFps.toFixed(0); color: "#34506e"; font.family: win.monoFont; font.pixelSize: 10
                        }
                    }

                    // Trạng thái: ── ▸ ĐANG NGHE ◂ ── với vạch mảnh hai bên
                    Item {
                        id: statePill
                        objectName: "statePill"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        readonly property real maxW: stage.width - 40
                        Row {
                            id: pillRow
                            anchors.centerIn: parent
                            spacing: 10
                            Text { text: "▸"; color: win.stateAccent; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter
                                   SequentialAnimation on opacity {
                                       running: nexa.state !== "STANDBY" && nexa.state !== "INITIALIZING"; loops: Animation.Infinite
                                       NumberAnimation { to: 0.2; duration: 600; easing.type: Easing.InOutSine }
                                       NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
                                   } }
                            Text { id: pillLabel; objectName: "stateLabel"; text: nexa.stateLabel.toUpperCase(); color: win.stateAccent
                                   font.family: win.tacFont; font.pixelSize: 15; font.letterSpacing: 5
                                   anchors.verticalCenter: parent.verticalCenter }
                            Text {
                                visible: nexa.stateDetail.length > 0 && nexa.state !== "STANDBY" && !stage.tight
                                width: Math.min(implicitWidth, Math.max(0, statePill.maxW - 200 - pillLabel.implicitWidth))
                                text: "// " + nexa.stateDetail; color: win.iceDim; font.family: win.monoFont; font.pixelSize: 12
                                elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
                            }
                            Text { text: "◂"; color: win.stateAccent; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: pillRow.left; anchors.rightMargin: 14
                            width: Math.min(160, pillRow.x - 30); height: 1
                            gradient: Gradient { orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: "transparent" }
                                GradientStop { position: 1; color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.7) } }
                        }
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: pillRow.right; anchors.leftMargin: 14
                            width: Math.min(160, pillRow.x - 30); height: 1
                            gradient: Gradient { orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.7) }
                                GradientStop { position: 1; color: "transparent" } }
                        }
                    }

                    // Phụ đề: câu anh vừa nói (nghiêng, mờ) và câu NEXA trả lời (gõ dần), tự mờ sau ít giây
                    Item {
                        id: subs
                        objectName: "subtitles"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(74, subCol.implicitHeight)
                        property bool fresh: true
                        readonly property bool holding: nexa.listeningSpeech || win.busy || nexa.state === "SPEAKING"
                        readonly property string userLine: nexa.listeningSpeech
                            ? (nexa.heardText.length > 0 ? nexa.heardText : "Em đang nghe…") : win.lastUserText
                        function refresh() { fresh = true; fadeTimer.restart() }
                        onUserLineChanged: refresh()
                        onHoldingChanged: if (!holding) fadeTimer.restart()
                        Timer { id: fadeTimer; interval: 14000; running: true; onTriggered: if (!subs.holding) subs.fresh = false }
                        opacity: (fresh || holding) ? 1 : 0.0
                        Behavior on opacity { NumberAnimation { duration: 1400; easing.type: Easing.InOutQuad } }
                        Column {
                            id: subCol
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: Math.min(parent.width - 40, 820)
                            spacing: 6
                            // việc đang chạy: một dòng nhỏ kiểu nhật ký
                            Row {
                                anchors.horizontalCenter: parent.horizontalCenter
                                visible: win.liveTask !== null
                                spacing: 8
                                Text { text: win.glyph(0xE9F5); font.family: win.iconFont; font.pixelSize: 12; color: win.amber
                                       anchors.verticalCenter: parent.verticalCenter
                                       RotationAnimator on rotation { from: 0; to: 360; duration: 1600; loops: Animation.Infinite
                                                                      running: win.liveTask !== null } }
                                Text { text: win.liveTask ? ((win.liveTask.title || "") + (win.liveTask.text ? " · " + win.liveTask.text : "")).toUpperCase() : ""
                                       color: win.amber; font.family: win.tacFont; font.pixelSize: 12; font.letterSpacing: 2; elide: Text.ElideRight
                                       width: Math.min(implicitWidth, subCol.width - 30) }
                            }
                            Text {
                                id: userSub
                                width: parent.width
                                visible: text.length > 0
                                text: subs.userLine.length > 0 ? "“" + subs.userLine + "”" : ""
                                color: nexa.listeningSpeech ? "#bfeaff" : "#7fa3c0"
                                font.pixelSize: 15; font.italic: true
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText
                            }
                            Text {
                                id: replySub
                                width: parent.width
                                property string full: win.lastAssistantText
                                property int shown: full.length
                                onFullChanged: {
                                    typer.stop(); shown = 0
                                    typer.to = full.length; typer.duration = Math.min(2200, full.length * 22)
                                    typer.start(); subs.refresh()
                                }
                                NumberAnimation { id: typer; target: replySub; property: "shown"; from: 0 }
                                visible: full.length > 0
                                text: full.substring(0, shown)
                                color: "#f2f9ff"; font.pixelSize: stage.tight ? 17 : 20; lineHeight: 1.1
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
                            }
                            Text {
                                width: parent.width
                                visible: nexa.timeline.length === 0 && !nexa.listeningSpeech
                                text: "VỖ TAY · NÓI “NEXA ƠI” · HOẶC BẤM NÓI"
                                color: "#4f6f8c"; font.family: win.tacFont; font.pixelSize: 13; font.letterSpacing: 3
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }
                    }

                    // Điều khiển tạm khóa sau lệnh dừng
                    Item {
                        visible: nexa.controlPaused
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: Math.min(stage.width - 20, pausedRow.implicitWidth + 28)
                        Layout.preferredHeight: pausedRow.implicitHeight + 12
                        Chamfer { anchors.fill: parent; cut: 8; fill: "#2a1a06"; stroke: win.amber }
                        RowLayout {
                            id: pausedRow; anchors.centerIn: parent; spacing: 10
                            Text { text: "ĐIỀU KHIỂN ĐANG TẠM KHÓA SAU LỆNH DỪNG"; color: win.amber; font.family: win.tacFont
                                   font.pixelSize: 12; font.letterSpacing: 2 }
                            NButton { text: "▶ Tiếp tục"; tint: "#34d399"; font.pixelSize: 12; onClicked: nexa.resumeControl() }
                        }
                    }

                    // Thanh lệnh vát góc + nút DỪNG KHẨN CẤP
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.bottomMargin: 4
                        spacing: stage.tight ? 8 : 12
                        Item {
                            id: dock
                            objectName: "dock"
                            implicitWidth: dockRow.implicitWidth + 20
                            implicitHeight: dockRow.implicitHeight + 14
                            Chamfer { anchors.fill: parent; cut: 12; fill: "#d9050e1a"; stroke: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.25) }
                            Rectangle { x: 12; y: 0; width: 46; height: 2; color: win.amber }
                            Row {
                                id: dockRow
                                anchors.centerIn: parent
                                spacing: 6
                                TacButton {
                                    primary: true; tint: win.stateAccent; showCaption: !stage.tight
                                    glyphCode: 0xE720
                                    pulsing: nexa.state === "LISTENING"
                                    caption: nexa.state === "STANDBY" ? "Đánh thức" : "Nói"
                                    tip: nexa.state === "STANDBY" ? "Đánh thức NEXA (Ctrl+Alt+N)" : "Nhấn để nói"
                                    onClicked: nexa.state === "STANDBY" ? nexa.wake() : nexa.pushToTalk()
                                }
                                TacButton { glyphCode: 0xE708; caption: "Nghỉ"; tip: "Cho NEXA nghỉ"; showCaption: !stage.tight
                                            enabled: nexa.state !== "STANDBY"; onClicked: nexa.sleep() }
                                TacButton { glyphCode: 0xE815; caption: "Cử chỉ"; tint: win.purple; active: nexa.cameraOn
                                            tip: nexa.cameraOn ? "Tắt cử chỉ tay (tắt camera)" : "Bật cử chỉ tay (bật camera)"
                                            showCaption: !stage.tight && !win.stacked; onClicked: nexa.toggleGestures() }
                                TacButton { glyphCode: 0xF158; caption: "3D"; active: nexa3d.workspace || win.viewer3dOpen
                                            tip: "Mô hình 3D"; showCaption: !stage.tight
                                            onClicked: nexa3d.workspace = !nexa3d.workspace }
                                TacButton { glyphCode: 0xE943; caption: "Code"; tint: win.blue; active: nexaCode.panelOpen
                                            tip: "Sinh code"; showCaption: !stage.tight
                                            onClicked: nexaCode.panelOpen ? nexaCode.closePanel() : nexaCode.openPanel() }
                                TacButton { glyphCode: 0xE8BD; caption: "Nhật ký"; active: win.historyOpen; visible: !win.logDocked
                                            tip: "Nhật ký hội thoại và ô gõ lệnh (Ctrl+H)"; showCaption: !stage.tight && !win.stacked
                                            onClicked: win.toggleHistory() }
                                TacButton { glyphCode: 0xE711; caption: "Hủy"; tint: win.amber; visible: win.busy
                                            tip: "Hủy tác vụ đang chạy"; showCaption: !stage.tight
                                            onClicked: nexa.cancelTask() }
                                TacButton { id: moreBtn; glyphCode: 0xE712; caption: ""; showCaption: false; tip: "Thêm: bảng cử chỉ, chuột bằng tay…"
                                            onClicked: moreMenu.popup(moreBtn, 0, -moreMenu.implicitHeight - 6) }
                            }
                            Menu {
                                id: moreMenu
                                padding: 6
                                background: Rectangle { implicitWidth: 240; radius: 3; color: "#081628"
                                                        border.color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.3) }
                                DarkMenuItem { text: gesturePanel.visible ? "Đóng bảng cử chỉ" : "Bảng cử chỉ…"
                                               onTriggered: gesturePanel.visible = !gesturePanel.visible }
                                DarkMenuItem { text: nexa.airMouse ? "Tắt chuột bằng tay" : "Chuột bằng tay"
                                               enabled: nexa.cameraOn; onTriggered: nexa.toggleAirMouse() }
                                DarkMenuItem { text: "Xóa hội thoại"; onTriggered: nexa.clearConversation() }
                                DarkMenuItem { text: "Thu gọn thành lõi nổi"; onTriggered: win.enterCompact(true) }
                            }
                        }
                        // DỪNG KHẨN CẤP: luôn hiện, đỏ cảnh báo, tách khỏi thanh lệnh
                        TacButton {
                            id: stopBtn
                            objectName: "stopButton"
                            implicitHeight: dock.implicitHeight
                            primary: true; tint: win.hazard
                            glyphCode: 0xE71A; caption: "Dừng"; showCaption: !stage.tight
                            tip: "DỪNG KHẨN CẤP (Ctrl+Alt+Esc)"
                            onClicked: nexa.stop()
                        }
                    }
                }

                // tab ở mép phải khi nhật ký thu vào (màn hẹp): số dòng + mở nhật ký
                Item {
                    id: drawerHandle
                    visible: !win.logDocked && !win.historyOpen
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 28; height: 104
                    Chamfer { anchors.fill: parent; cut: 7; fill: handleMouse.containsMouse ? "#13283f" : "#c4061220"
                              stroke: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.35) }
                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: win.glyph(0xE76B); font.family: win.iconFont
                               font.pixelSize: 11; color: win.iceDim }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "LOG"; rotation: -90; color: win.ice
                               font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 2 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; visible: chat.count > 0
                               text: chat.count > 99 ? "99+" : chat.count; color: win.amber; font.family: win.monoFont; font.pixelSize: 10 }
                    }
                    MouseArea { id: handleMouse; anchors.fill: parent; hoverEnabled: true; onClicked: win.toggleHistory() }
                    NTip { visible: handleMouse.containsMouse; text: "Mở nhật ký (Ctrl+H)" }
                }

                // nhật ký nằm đè lên sân khấu → phủ tối, bấm ra ngoài để đóng
                Rectangle {
                    anchors.fill: parent
                    z: 9
                    color: "#aa02060c"
                    opacity: win.historyOpen && !win.logDocked ? 1 : 0
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: 250 } }
                    MouseArea { anchors.fill: parent; onClicked: win.historyOpen = false }
                }

                // Nhật ký: tin nhắn + bước tác vụ + ô gõ lệnh. Màn rộng: gắn cố định bên phải sân khấu (chỗ logSlot);
                // màn hẹp / có bảng bên phải: ngăn kéo trượt từ mép phải.
                TacPanel {
                    id: chatPanel
                    objectName: "historyDrawer"
                    title: "LOG · NHẬT KÝ"; code: "03"; accent: win.amber
                    z: 10
                    width: win.logDocked ? logSlot.width : stage.drawerW
                    y: 0; height: stage.height
                    x: win.logDocked ? stage.width + 14 : (win.historyOpen ? stage.width - width : stage.width + 8)
                    Behavior on x { enabled: !win.logDocked; NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
                    visible: win.logDocked || x < stage.width
                    headerExtra: [
                        HeaderButton { width: 26; height: 26; glyphCode: 0xE74D; tip: "Xóa hội thoại"; hoverTint: win.hazard
                                       onClicked: nexa.clearConversation() },
                        HeaderButton { width: 26; height: 26; visible: !win.logDocked; glyphCode: 0xE711; tip: "Đóng nhật ký (Ctrl+H)"
                                       onClicked: win.historyOpen = false }
                    ]
                    ColumnLayout {
                        anchors.fill: parent; spacing: 8
                        Item {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            ListView {
                                id: chat
                                objectName: "chat"
                                anchors.fill: parent
                                clip: true; spacing: 10
                                model: nexa.timeline
                                onCountChanged: Qt.callLater(function() { chat.positionViewAtEnd() })
                                delegate: Item {
                                    id: row
                                    required property var modelData
                                    readonly property bool isTask: modelData.kind === "task"
                                    readonly property bool isUser: modelData.role === "user"
                                    width: chat.width
                                    height: isTask ? taskCard.height : bubble.height
                                    // tin nhắn: vạch màu bên trái (anh = băng, NEXA = cam), giờ · người nói, nội dung
                                    Item {
                                        id: bubble
                                        visible: !row.isTask
                                        width: Math.min(chat.width, Math.max(msg.implicitWidth, meta.implicitWidth) + 14)
                                        height: meta.implicitHeight + msg.implicitHeight + 8
                                        Rectangle { width: 2; height: parent.height; color: row.isUser ? win.ice : win.amber; opacity: 0.85 }
                                        Row {
                                            id: meta
                                            x: 12
                                            spacing: 7
                                            Text { text: row.modelData.time || ""; font.family: win.monoFont; font.pixelSize: 11; color: "#4f6f8c" }
                                            Text { text: row.isUser ? "▸ ANH SƠN" : "◂ NEXA"; font.family: win.tacFont; font.pixelSize: 11
                                                   font.letterSpacing: 2; color: row.isUser ? win.ice : win.amber }
                                            Text { visible: row.isUser && row.modelData.source === "voice"; text: win.glyph(0xE720)
                                                   font.family: win.iconFont; font.pixelSize: 10; color: win.iceDim
                                                   anchors.verticalCenter: parent.verticalCenter }
                                        }
                                        Text { id: msg; x: 12; y: meta.implicitHeight + 4
                                               width: Math.min(chat.width - 14, implicitWidth); text: row.isTask ? "" : (row.modelData.text || "")
                                               color: row.isUser ? "#cfe9ff" : "#f2f9ff"; font.pixelSize: 13.5; lineHeight: 1.12
                                               wrapMode: Text.Wrap; textFormat: Text.PlainText }
                                    }
                                    // bước tác vụ: [✓] / [⟳] tiêu đề · chi tiết · giờ, cập nhật tại chỗ
                                    Item {
                                        id: taskCard
                                        visible: row.isTask
                                        readonly property color sc: win.taskColor(row.modelData.status)
                                        readonly property bool spinning: row.isTask && (row.modelData.status === "running" || row.modelData.status === "queued")
                                        x: 12
                                        width: chat.width - 12
                                        height: 26
                                        Rectangle { anchors.fill: parent; color: Qt.rgba(taskCard.sc.r, taskCard.sc.g, taskCard.sc.b, 0.06) }
                                        Row {
                                            id: tRow
                                            x: 6; anchors.verticalCenter: parent.verticalCenter
                                            spacing: 7
                                            Text { text: "["; color: taskCard.sc; font.family: win.monoFont; font.pixelSize: 13
                                                   anchors.verticalCenter: parent.verticalCenter }
                                            Item {
                                                width: 14; height: 14; anchors.verticalCenter: parent.verticalCenter
                                                Text { anchors.centerIn: parent; visible: taskCard.spinning; text: win.glyph(0xE9F5)
                                                       font.family: win.iconFont; font.pixelSize: 12; color: taskCard.sc
                                                       RotationAnimator on rotation { from: 0; to: 360; duration: 1600; loops: Animation.Infinite
                                                                                      running: taskCard.spinning } }
                                                Text { anchors.centerIn: parent; visible: !taskCard.spinning; text: win.glyph(win.taskGlyph(row.modelData.status))
                                                       font.family: win.iconFont; font.pixelSize: 11; font.bold: true; color: taskCard.sc }
                                            }
                                            Text { text: "]"; color: taskCard.sc; font.family: win.monoFont; font.pixelSize: 13
                                                   anchors.verticalCenter: parent.verticalCenter }
                                            Text { id: tTitle; text: row.isTask ? (row.modelData.title || "").toUpperCase() : ""; color: "#e6f4ff"
                                                   font.family: win.tacFont; font.pixelSize: 12; font.letterSpacing: 1
                                                   anchors.verticalCenter: parent.verticalCenter }
                                            Text { text: row.isTask ? (row.modelData.text || "") : ""; color: "#7fa3c0"; font.pixelSize: 12; elide: Text.ElideRight
                                                   visible: text.length > 0 && text !== tTitle.text
                                                   width: Math.min(implicitWidth, Math.max(40, taskCard.width - 6 - 60 - tTitle.implicitWidth - tTime.implicitWidth - 20))
                                                   anchors.verticalCenter: parent.verticalCenter }
                                        }
                                        Text { id: tTime; anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                                               text: row.modelData.time || ""; color: "#4f6f8c"; font.family: win.monoFont; font.pixelSize: 10 }
                                    }
                                }
                            }
                            Column {
                                anchors.centerIn: parent
                                visible: chat.count === 0
                                spacing: 6
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "— CHƯA CÓ DỮ LIỆU —"; color: "#35526e"
                                       font.family: win.tacFont; font.pixelSize: 13; font.letterSpacing: 3 }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Vỗ tay, nói “Nexa ơi” hoặc gõ lệnh bên dưới"
                                       color: win.iceDim; font.pixelSize: 12 }
                            }
                        }
                        // dòng lệnh: > gõ lệnh
                        Item {
                            Layout.fillWidth: true
                            implicitHeight: 40
                            Chamfer { anchors.fill: parent; cut: 8; fill: "#e0030a14"
                                      stroke: input.activeFocus ? win.amber : Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.28) }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 4; spacing: 6
                                Text { text: ">"; color: win.amber; font.family: win.monoFont; font.pixelSize: 16; font.bold: true }
                                TextField {
                                    id: input
                                    Layout.fillWidth: true
                                    placeholderText: "Nhập lệnh… (mở Notepad, âm lượng 30%)"
                                    color: "white"; font.family: win.monoFont; font.pixelSize: 13
                                    placeholderTextColor: "#48677f"
                                    leftPadding: 0
                                    background: Item {}
                                    onAccepted: { if (text.trim().length) { nexa.sendText(text); text = "" } }
                                }
                                Item {
                                    id: sendBtn
                                    readonly property bool ready: input.text.trim().length > 0
                                    implicitWidth: 34; implicitHeight: 32
                                    Chamfer { anchors.fill: parent; cut: 6
                                              fill: sendBtn.ready ? (sendMouse.pressed ? Qt.darker(win.amber, 1.4) : win.amber) : "#0d1f33"
                                              stroke: sendBtn.ready ? win.amber : Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2) }
                                    Text { anchors.centerIn: parent; text: win.glyph(0xE724); font.family: win.iconFont; font.pixelSize: 14
                                           color: sendBtn.ready ? "#1a0e00" : "#48677f" }
                                    MouseArea { id: sendMouse; anchors.fill: parent; hoverEnabled: true
                                                onClicked: { if (input.text.trim().length) { nexa.sendText(input.text); input.text = "" } } }
                                    NTip { visible: sendMouse.containsMouse; text: "Gửi (Enter)" }
                                }
                            }
                        }
                        Text { Layout.fillWidth: true; visible: text.length > 0; text: nexa.statusText
                               color: "#4f6f8c"; font.family: win.monoFont; font.pixelSize: 10; elide: Text.ElideRight }
                    }
                }
            }

            // chỗ dành cho nhật ký khi gắn cố định (chatPanel vẽ đè đúng vị trí này)
            Item {
                id: logSlot
                visible: win.logDocked
                Layout.fillHeight: true
                Layout.preferredWidth: Math.min(380, Math.max(320, win.width * 0.25))
            }
