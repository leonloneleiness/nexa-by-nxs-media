from pathlib import Path

p = Path("nexa/ui/qml/Main.qml")
s = p.read_text(encoding="utf-8")


def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:80])
    s = s.replace(old, new)


rep('''                    color: win.panel; radius: 14; border.color: win.panelBorder
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 8
                        RowLayout {
                            Text { text: "Hội thoại"; color: "white"; font.pixelSize: 16; font.bold: true }
                            Item { Layout.fillWidth: true }
                            Text { text: nexa.foreground.length > 3 ? "Cửa sổ đích: " + nexa.foreground : ""; color: win.textDim
                                   font.pixelSize: 11; elide: Text.ElideMiddle; Layout.maximumWidth: 300 }
                            NButton { text: "Xóa"; font.pixelSize: 11; onClicked: nexa.clearConversation() }
                        }''',
'''                    color: win.panel; radius: 16; border.color: win.panelBorder
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
                                       width: Math.min(implicitWidth, chatPanel.width - 120) }
                            }
                            HeaderButton { glyphCode: 0xE74D; tip: "Xóa hội thoại"; hoverTint: "#fb7185"
                                           onClicked: nexa.clearConversation() }
                        }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: win.panelBorder; opacity: 0.7 }''')

# bong bóng: nền dịu, viền mảnh, tên người nói có màu, giờ dễ đọc
rep('''                                        width: Math.min(chat.width * 0.82, Math.max(msg.implicitWidth, meta.implicitWidth) + 26)
                                        height: msg.implicitHeight + meta.implicitHeight + 18
                                        radius: 12
                                        color: row.isUser ? "#10284d" : "#101a33"
                                        border.color: row.isUser ? "#1d4ed8" : "#5b21b6"
                                        Column {
                                            anchors.fill: parent; anchors.margins: 9; spacing: 2
                                            Text { id: meta; color: win.textDim; font.pixelSize: 10
                                                   text: (row.isUser ? (row.modelData.source === "voice" ? "Anh Sơn (giọng nói)" : "Anh Sơn") : "NEXA") + " · " + (row.modelData.time || "") }
                                            Text { id: msg; width: Math.min(chat.width * 0.82 - 26, implicitWidth); text: row.isTask ? "" : (row.modelData.text || "")
                                                   color: "white"; font.pixelSize: 14; wrapMode: Text.Wrap; textFormat: Text.PlainText }''',
'''                                        width: Math.min(chat.width * 0.82, Math.max(msg.implicitWidth, meta.implicitWidth) + 28)
                                        height: msg.implicitHeight + meta.implicitHeight + 24
                                        radius: 14
                                        color: row.isUser ? "#13315f" : "#0f1d38"
                                        border.color: row.isUser ? "#2a5ba8" : "#233a62"
                                        Column {
                                            anchors.fill: parent; anchors.margins: 12; anchors.topMargin: 10; spacing: 4
                                            Row {
                                                id: meta
                                                spacing: 6
                                                Text { text: row.isUser ? "Anh Sơn" : "NEXA"; font.pixelSize: 11; font.bold: true
                                                       color: row.isUser ? "#93c5fd" : "#67e8f9" }
                                                Text { visible: row.isUser && row.modelData.source === "voice"; text: win.glyph(0xE720)
                                                       font.family: win.iconFont; font.pixelSize: 10; color: "#6f8fb0"
                                                       anchors.verticalCenter: parent.verticalCenter }
                                                Text { text: row.modelData.time || ""; font.pixelSize: 11; color: "#6f8fb0" }
                                            }
                                            Text { id: msg; width: Math.min(chat.width * 0.82 - 28, implicitWidth); text: row.isTask ? "" : (row.modelData.text || "")
                                                   color: "#f1f6ff"; font.pixelSize: 14; lineHeight: 1.12; wrapMode: Text.Wrap; textFormat: Text.PlainText }''')

rep('''                                        x: 14
                                        width: Math.min(chat.width - 28, tRow.implicitWidth + 30)
                                        height: 34''', '''                                        x: 12
                                        width: Math.min(chat.width - 28, tRow.implicitWidth + 30)
                                        height: 36''')
rep('''                                            Text { id: tTime; text: row.modelData.time || ""; color: "#4b6a8a"; font.pixelSize: 10''',
    '''                                            Text { id: tTime; text: row.modelData.time || ""; color: "#56759a"; font.pixelSize: 11''')

# ô nhập: viên nang, nút gửi tròn đổi màu theo trạng thái
rep('''                        RowLayout {
                            spacing: 8
                            TextField {
                                id: input
                                Layout.fillWidth: true
                                placeholderText: "Nhập lệnh cho NEXA… (ví dụ: mở Notepad, đặt âm lượng 30 phần trăm)"
                                color: "white"; font.pixelSize: 14
                                placeholderTextColor: "#5b7a99"
                                background: Rectangle { radius: 10; color: "#081226"; border.color: input.activeFocus ? win.cyan : win.panelBorder }
                                onAccepted: { if (text.trim().length) { nexa.sendText(text); text = "" } }
                            }
                            NButton { text: "Gửi"; onClicked: { if (input.text.trim().length) { nexa.sendText(input.text); input.text = "" } } }
                        }''',
'''                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 46; radius: 23
                            color: "#081226"
                            border.color: input.activeFocus ? win.stateAccent : win.panelBorder
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 5; spacing: 6
                                TextField {
                                    id: input
                                    Layout.fillWidth: true
                                    placeholderText: "Nhập lệnh cho NEXA… (ví dụ: mở Notepad, đặt âm lượng 30 phần trăm)"
                                    color: "white"; font.pixelSize: 14
                                    placeholderTextColor: "#5b7a99"
                                    leftPadding: 0
                                    background: Item {}
                                    onAccepted: { if (text.trim().length) { nexa.sendText(text); text = "" } }
                                }
                                Rectangle {
                                    id: sendBtn
                                    readonly property bool ready: input.text.trim().length > 0
                                    implicitWidth: 36; implicitHeight: 36; radius: 18
                                    color: ready ? (sendMouse.pressed ? Qt.darker(win.stateAccent, 1.4) : win.stateAccent) : "#12243f"
                                    Text { anchors.centerIn: parent; text: win.glyph(0xE724); font.family: win.iconFont; font.pixelSize: 15
                                           color: sendBtn.ready ? "#041020" : "#5b7a99" }
                                    MouseArea { id: sendMouse; anchors.fill: parent; hoverEnabled: true
                                                onClicked: { if (input.text.trim().length) { nexa.sendText(input.text); input.text = "" } } }
                                    NTip { visible: sendMouse.containsMouse; text: "Gửi (Enter)" }
                                }
                            }
                        }''')
p.write_text(s, encoding="utf-8")
print("ok")
