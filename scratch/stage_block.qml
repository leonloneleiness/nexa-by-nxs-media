            // Sân khấu JARVIS: quả cầu lớn ở giữa, phụ đề ngay dưới quả cầu rồi mờ dần,
            // thông số máy là các vạch mảnh ở hai góc trên, hội thoại nằm trong ngăn kéo cạnh phải.
            Item {
                id: stage
                objectName: "stage"
                Layout.fillWidth: !win.codeShown
                Layout.preferredWidth: win.codeShown ? win.sideNexaWidth : -1
                Layout.maximumWidth: win.codeShown ? win.sideNexaWidth : Number.POSITIVE_INFINITY
                Layout.fillHeight: true
                clip: true
                readonly property bool tight: width < 560
                // ngăn kéo mở trên màn rộng: nội dung dịch sang trái nhường chỗ, không bị che
                readonly property bool drawerDocked: win.historyOpen && width >= 900
                readonly property real drawerW: Math.min(width - 24, 400)

                // khung góc HUD mảnh
                Repeater {
                    model: 4
                    Item {
                        required property int index
                        width: 22; height: 22
                        x: (index === 1 || index === 2) ? stage.width - width : 0
                        y: index >= 2 ? stage.height - height : 0
                        rotation: index * 90
                        opacity: 0.45
                        Rectangle { width: parent.width; height: 2; radius: 1; color: win.stateAccent }
                        Rectangle { width: 2; height: parent.height; radius: 1; color: win.stateAccent }
                    }
                }

                Item {
                    id: stageBody
                    anchors.fill: parent
                    anchors.rightMargin: stage.drawerDocked ? stage.drawerW + 16 : 0
                    Behavior on anchors.rightMargin { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }

                    // Thông số máy: vạch mảnh ở hai góc trên (CPU · GPU | RAM · AI)
                    Item {
                        id: statsStrip
                        objectName: "statsRing"
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                        anchors.leftMargin: 30; anchors.rightMargin: 30; anchors.topMargin: 12
                        height: 34
                        visible: nexa.sysStats.cpu !== undefined
                        readonly property var st: nexa.sysStats
                        function pct(v) { return v === null || v === undefined ? "—" : Math.round(v) + "%" }
                        function ms(v) { return !v ? "—" : v < 1000 ? Math.round(v) + " ms" : (v / 1000).toFixed(1) + " s" }
                        readonly property bool hasGpu: st.gpu !== null && st.gpu !== undefined
                        Row {
                            anchors.left: parent.left
                            spacing: 22
                            Meter { label: "CPU"; v: (statsStrip.st.cpu || 0) / 100; valueText: statsStrip.pct(statsStrip.st.cpu) }
                            Meter { visible: !stage.tight; label: "GPU"; v: statsStrip.hasGpu ? statsStrip.st.gpu / 100 : -1
                                    valueText: statsStrip.pct(statsStrip.st.gpu) }
                        }
                        Row {
                            anchors.right: parent.right
                            spacing: 22
                            Meter { visible: !stage.tight; label: "AI"; v: Math.min(1, (statsStrip.st.ai_ms || 0) / 5000)
                                    valueText: statsStrip.ms(statsStrip.st.ai_ms) }
                            Meter { label: "RAM"; v: (statsStrip.st.ram || 0) / 100; valueText: statsStrip.pct(statsStrip.st.ram) }
                        }
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.topMargin: statsStrip.visible ? 50 : 16
                        anchors.bottomMargin: 6
                        spacing: 8

                        Item {
                            id: orbArea
                            objectName: "orbArea"
                            Layout.fillWidth: true; Layout.fillHeight: true
                            readonly property real orbSize: Math.min(width * 0.86, height, 600)
                            // quầng sáng lớn theo màu trạng thái sau quả cầu
                            Canvas {
                                id: orbGlow
                                anchors.centerIn: parent
                                width: orbArea.orbSize * 1.7; height: width
                                visible: width > 0
                                property color ac: win.stateAccent
                                onAcChanged: requestPaint()
                                onWidthChanged: requestPaint()
                                renderStrategy: Canvas.Cooperative
                                onPaint: {
                                    var ctx = getContext("2d"); ctx.reset()
                                    var r = width / 2, g = ctx.createRadialGradient(r, r, 0, r, r, r)
                                    g.addColorStop(0.0, Qt.rgba(ac.r, ac.g, ac.b, 0.20))
                                    g.addColorStop(0.35, Qt.rgba(ac.r, ac.g, ac.b, 0.08))
                                    g.addColorStop(1.0, Qt.rgba(ac.r, ac.g, ac.b, 0.0))
                                    ctx.fillStyle = g; ctx.fillRect(0, 0, width, height)
                                }
                            }
                            Orb {
                                id: mainOrb
                                anchors.centerIn: parent
                                width: orbArea.orbSize; height: width
                                appState: nexa.state; micLevel: nexa.micLevel; outLevel: nexa.outLevel; outBands: nexa.outBands; effects: nexa.effects
                            }
                            MouseArea { anchors.fill: mainOrb; onDoubleClicked: nexa.wake() }
                            Text {
                                visible: nexa.showFps
                                anchors.left: parent.left; anchors.top: parent.top; anchors.leftMargin: 30
                                text: "FPS " + mainOrb.measuredFps.toFixed(0); color: "#34506e"; font.pixelSize: 10
                            }
                        }

                        // Trạng thái: chữ thưa, chấm nhấp nháy khi đang hoạt động
                        Rectangle {
                            id: statePill
                            objectName: "statePill"
                            Layout.alignment: Qt.AlignHCenter
                            readonly property real maxW: stageBody.width - 40
                            Layout.preferredWidth: Math.min(maxW, pillRow.implicitWidth + 30)
                            Layout.preferredHeight: 30
                            radius: 15
                            color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.08)
                            border.color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.45)
                            Row {
                                id: pillRow
                                anchors.centerIn: parent
                                spacing: 8
                                Rectangle {
                                    id: stateDot
                                    width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                                    color: win.stateAccent
                                    readonly property bool live: nexa.state !== "STANDBY" && nexa.state !== "INITIALIZING"
                                    onLiveChanged: if (!live) opacity = 1
                                    SequentialAnimation on opacity {
                                        running: stateDot.live; loops: Animation.Infinite
                                        NumberAnimation { to: 0.25; duration: 600; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
                                    }
                                }
                                Text { id: pillLabel; objectName: "stateLabel"; text: nexa.stateLabel.toUpperCase(); color: win.stateAccent
                                       font.pixelSize: 13; font.bold: true; font.letterSpacing: 3 }
                                Text {
                                    visible: nexa.stateDetail.length > 0 && nexa.state !== "STANDBY"
                                    width: Math.min(implicitWidth, Math.max(0, statePill.maxW - 30 - 16 - pillLabel.implicitWidth - 8))
                                    text: nexa.stateDetail; color: win.textDim; font.pixelSize: 12; elide: Text.ElideRight
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }

                        // Phụ đề: câu anh vừa nói (nghiêng, mờ) và câu NEXA trả lời (gõ dần), tự mờ sau ít giây
                        Item {
                            id: subs
                            objectName: "subtitles"
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.max(78, subCol.implicitHeight)
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
                                // việc đang chạy: một dòng nhỏ, không phải thẻ
                                Row {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    visible: win.liveTask !== null
                                    spacing: 8
                                    Text { text: win.glyph(0xE9F5); font.family: win.iconFont; font.pixelSize: 13; color: win.stateAccent
                                           anchors.verticalCenter: parent.verticalCenter
                                           RotationAnimator on rotation { from: 0; to: 360; duration: 1600; loops: Animation.Infinite
                                                                          running: win.liveTask !== null } }
                                    Text { text: win.liveTask ? (win.liveTask.title || "") + (win.liveTask.text ? " · " + win.liveTask.text : "") : ""
                                           color: win.textDim; font.pixelSize: 13; elide: Text.ElideRight
                                           width: Math.min(implicitWidth, subCol.width - 30) }
                                }
                                Text {
                                    id: userSub
                                    width: parent.width
                                    visible: text.length > 0
                                    text: subs.userLine.length > 0 ? "“" + subs.userLine + "”" : ""
                                    color: nexa.listeningSpeech ? "#a5f3fc" : "#8fb3d1"
                                    font.pixelSize: 16; font.italic: true
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
                                    color: "#f1f6ff"; font.pixelSize: stage.tight ? 17 : 21; lineHeight: 1.1
                                    style: Text.Raised; styleColor: "#040914"
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
                                }
                                Text {
                                    width: parent.width
                                    visible: nexa.timeline.length === 0 && !nexa.listeningSpeech
                                    text: "Vỗ tay, nói “Nexa ơi” hoặc bấm Nói"
                                    color: "#56759a"; font.pixelSize: 15; font.letterSpacing: 1
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }

                        // Điều khiển tạm khóa sau lệnh dừng
                        Rectangle {
                            visible: nexa.controlPaused
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: Math.min(stageBody.width - 20, pausedRow.implicitWidth + 24)
                            Layout.preferredHeight: pausedRow.implicitHeight + 12
                            radius: 12; color: "#1f1a0a"; border.color: "#b7791f"
                            RowLayout {
                                id: pausedRow; anchors.centerIn: parent; spacing: 10
                                Text { text: "Điều khiển đang tạm khóa sau lệnh dừng."; color: "#fbbf24"; font.pixelSize: 13 }
                                NButton { text: "▶ Tiếp tục"; tint: "#34d399"; font.pixelSize: 12; onClicked: nexa.resumeControl() }
                            }
                        }

                        // Dock tròn + nút DỪNG KHẨN CẤP
                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.bottomMargin: 8
                            spacing: stage.tight ? 8 : 14
                            Rectangle {
                                id: dock
                                objectName: "dock"
                                implicitWidth: dockRow.implicitWidth + (stage.tight ? 14 : 22)
                                implicitHeight: dockRow.implicitHeight + 14
                                radius: stage.tight ? height / 2 : 26
                                color: "#cc081226"
                                border.color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.3)
                                Row {
                                    id: dockRow
                                    anchors.centerIn: parent
                                    spacing: stage.tight ? 0 : 4
                                    DockButton {
                                        primary: true; tint: win.stateAccent; showCaption: !stage.tight
                                        size: stage.tight ? 40 : 46
                                        glyphCode: 0xE720
                                        pulsing: nexa.state === "LISTENING"
                                        caption: nexa.state === "STANDBY" ? "Đánh thức" : "Nói"
                                        tip: nexa.state === "STANDBY" ? "Đánh thức NEXA (Ctrl+Alt+N)" : "Nhấn để nói"
                                        onClicked: nexa.state === "STANDBY" ? nexa.wake() : nexa.pushToTalk()
                                    }
                                    DockButton { glyphCode: 0xE708; caption: "Nghỉ"; tip: "Cho NEXA nghỉ"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 enabled: nexa.state !== "STANDBY"; onClicked: nexa.sleep() }
                                    DockButton { glyphCode: 0xE815; caption: "Cử chỉ"; tint: win.purple; active: nexa.cameraOn
                                                 tip: nexa.cameraOn ? "Tắt cử chỉ tay (tắt camera)" : "Bật cử chỉ tay (bật camera)"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 onClicked: nexa.toggleGestures() }
                                    DockButton { glyphCode: 0xF158; caption: "3D"; active: nexa3d.workspace || win.viewer3dOpen
                                                 tip: "Mô hình 3D"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 onClicked: nexa3d.workspace = !nexa3d.workspace }
                                    DockButton { glyphCode: 0xE943; caption: "Code"; tint: win.blue; active: nexaCode.panelOpen
                                                 tip: "Sinh code"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 onClicked: nexaCode.panelOpen ? nexaCode.closePanel() : nexaCode.openPanel() }
                                    DockButton { glyphCode: 0xE8BD; caption: "Hội thoại"; active: win.historyOpen
                                                 tip: "Lịch sử hội thoại và ô gõ lệnh (Ctrl+H)"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 onClicked: win.toggleHistory() }
                                    DockButton { glyphCode: 0xE711; caption: "Hủy"; tint: "#fbbf24"; visible: win.busy
                                                 tip: "Hủy tác vụ đang chạy"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 onClicked: nexa.cancelTask() }
                                    DockButton { id: moreBtn; glyphCode: 0xE712; caption: "Thêm"; tip: "Bảng cử chỉ, chuột bằng tay…"
                                                 showCaption: !stage.tight; size: stage.tight ? 36 : 42
                                                 onClicked: moreMenu.popup(moreBtn, 0, -moreMenu.implicitHeight - 6) }
                                }
                                Menu {
                                    id: moreMenu
                                    padding: 6
                                    background: Rectangle { implicitWidth: 240; radius: 10; color: "#0b1a33"; border.color: win.panelBorder }
                                    DarkMenuItem { text: gesturePanel.visible ? "Đóng bảng cử chỉ" : "Bảng cử chỉ…"
                                                   onTriggered: gesturePanel.visible = !gesturePanel.visible }
                                    DarkMenuItem { text: nexa.airMouse ? "Tắt chuột bằng tay" : "Chuột bằng tay"
                                                   enabled: nexa.cameraOn; onTriggered: nexa.toggleAirMouse() }
                                    DarkMenuItem { text: "Xóa hội thoại"; onTriggered: nexa.clearConversation() }
                                    DarkMenuItem { text: "Thu gọn thành quả cầu nổi"; onTriggered: win.enterCompact(true) }
                                }
                            }
                            // DỪNG KHẨN CẤP: luôn hiện, viền đỏ, tách khỏi dock
                            Item {
                                id: stopBtn
                                objectName: "stopButton"
                                implicitWidth: Math.max(stopDisc.width, stopCap.visible ? stopCap.implicitWidth : 0)
                                implicitHeight: stopDisc.height + (stopCap.visible ? stopCap.implicitHeight + 3 : 0)
                                Rectangle {
                                    id: stopDisc
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: stage.tight ? 44 : 50; height: width; radius: width / 2
                                    color: stopMouse.pressed ? "#9f1239" : stopMouse.containsMouse ? "#4c0519" : "#1c0812"
                                    border.color: "#fb7185"; border.width: 2
                                    scale: stopMouse.pressed ? 0.94 : 1
                                    Rectangle { anchors.centerIn: parent; width: parent.width * 0.32; height: width; radius: 3
                                                color: stopMouse.containsMouse ? "white" : "#fb7185" }
                                }
                                Text { id: stopCap; visible: !stage.tight; anchors.top: stopDisc.bottom; anchors.topMargin: 3
                                       anchors.horizontalCenter: parent.horizontalCenter
                                       text: "DỪNG"; color: "#fb7185"; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1 }
                                MouseArea { id: stopMouse; anchors.fill: parent; hoverEnabled: true; onClicked: nexa.stop() }
                                NTip { visible: stopMouse.containsMouse; text: "DỪNG KHẨN CẤP (Ctrl+Alt+Esc)" }
                            }
                        }
                    }
                }

                // tay nắm ở mép phải khi ngăn kéo đóng: số tin + mở lịch sử
                Rectangle {
                    id: drawerHandle
                    visible: !win.historyOpen
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 96; radius: 10
                    color: handleMouse.containsMouse ? "#12243f" : "#0a1428"
                    border.color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.35)
                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: win.glyph(0xE76B); font.family: win.iconFont
                               font.pixelSize: 11; color: win.textDim }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: win.glyph(0xE8BD); font.family: win.iconFont
                               font.pixelSize: 14; color: win.stateAccent }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; visible: chat.count > 0
                               text: chat.count > 99 ? "99+" : chat.count; color: win.textDim; font.pixelSize: 10 }
                    }
                    MouseArea { id: handleMouse; anchors.fill: parent; hoverEnabled: true; onClicked: win.toggleHistory() }
                    NTip { visible: handleMouse.containsMouse; text: "Mở hội thoại (Ctrl+H)" }
                }

                // Ngăn kéo hội thoại: tin nhắn + thẻ tác vụ + ô gõ lệnh
                Rectangle {
                    id: chatPanel
                    objectName: "historyDrawer"
                    z: 10
                    width: stage.drawerW
                    anchors.top: parent.top; anchors.bottom: parent.bottom
                    x: win.historyOpen ? stage.width - width : stage.width + 8
                    Behavior on x { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
                    visible: x < stage.width
                    color: "#f00a1428"; radius: 16; border.color: win.panelBorder
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 14; spacing: 10
                        RowLayout {
                            spacing: 10
                            Rectangle { implicitWidth: 32; implicitHeight: 32; radius: 16
                                        color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.14)
                                        Text { anchors.centerIn: parent; text: win.glyph(0xE8BD); font.family: win.iconFont
                                               font.pixelSize: 14; color: win.stateAccent } }
                            Column {
                                Layout.fillWidth: true
                                Text { text: "Hội thoại"; color: "white"; font.pixelSize: 16; font.bold: true }
                                Text { text: nexa.foreground.length > 3 ? "Cửa sổ đích: " + nexa.foreground : "Lệnh và kết quả trong phiên này"
                                       color: win.textDim; font.pixelSize: 11; elide: Text.ElideMiddle
                                       width: Math.min(implicitWidth, chatPanel.width - 150) }
                            }
                            HeaderButton { glyphCode: 0xE74D; tip: "Xóa hội thoại"; hoverTint: "#fb7185"
                                           onClicked: nexa.clearConversation() }
                            HeaderButton { glyphCode: 0xE76C; tip: "Đóng ngăn hội thoại (Ctrl+H)"; onClicked: win.historyOpen = false }
                        }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: win.panelBorder; opacity: 0.7 }
