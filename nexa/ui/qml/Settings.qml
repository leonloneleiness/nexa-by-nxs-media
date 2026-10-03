import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    signal closeRequested()
    property var s: JSON.parse(nexa.settingsJson())
    property var g: JSON.parse(nexa.gesturesJson())
    property string saveMsg: ""
    property string unlockMsg: ""
    property var unlockSvc: ({ installed: false, running: false })
    readonly property color cyan: Theme.accent
    readonly property color dim: Theme.textSecondary

    function save() { saveMsg = nexa.saveSettings(JSON.stringify(s), JSON.stringify(g)) }
    function refreshUnlock() { unlockSvc = JSON.parse(nexa.unlockServiceStatus()) }
    Component.onCompleted: refreshUnlock()

    // ---------- thành phần ----------
    component Label2: Text { color: root.dim; font.pixelSize: 13; Layout.preferredWidth: root.width < 700 ? -1 : root.width < 800 ? 145 : 210; Layout.fillWidth: root.width < 700; wrapMode: Text.Wrap }
    component Note: Text { color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.columnSpan: root.width < 700 ? 1 : 2 }
    component Head: Text { color: "white"; font.pixelSize: 16; font.bold: true; wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.columnSpan: root.width < 700 ? 1 : 2; Layout.topMargin: 8 }
    component DarkField: TextField {
        color: "white"; font.pixelSize: 13; Layout.fillWidth: true
        placeholderTextColor: Theme.textMuted
        background: Rectangle { radius: 6; color: Theme.surface; border.color: parent.activeFocus ? root.cyan : Theme.border }
    }
    component DarkCheck: CheckBox {
        id: dc
        Layout.fillWidth: true
        contentItem: Text { text: dc.text; color: "white"; font.pixelSize: 13; leftPadding: dc.indicator.width + 6; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap }
    }
    component DarkButton: Button {
        id: db
        contentItem: Text { text: db.text; color: "white"; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 7; color: db.down ? Theme.surfaceRaised : (db.hovered ? Theme.surfaceRaised : Theme.surfaceRaised); border.color: Theme.borderStrong }
    }
    component Tab: Flickable {
        id: tabViewport
        contentWidth: width
        default property alias content: grid.data
        contentHeight: grid.implicitHeight + 30
        clip: true
        ScrollBar.vertical: ScrollBar {}
        GridLayout { id: grid; x: 20; y: 16; width: tabViewport.width - 40; columns: root.width < 700 ? 1 : 2; columnSpacing: 16; rowSpacing: 10 }
    }

    Rectangle { anchors.fill: parent; color: Theme.surface; radius: Theme.radius; border.color: Theme.border }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 18
        RowLayout {
            Column {
                spacing: 4
                Text { text: "NEXA / CẤU HÌNH HỆ THỐNG"; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 10; font.letterSpacing: 1 }
                Text { text: "Thiết lập không gian của anh"; color: Theme.textPrimary; font.pixelSize: root.width < 700 ? 18 : 23; font.weight: Font.Light }
            }
            Item { Layout.fillWidth: true }
            Text { text: root.saveMsg; color: Theme.success; font.pixelSize: 12; elide: Text.ElideRight; Layout.maximumWidth: 460 }
            DarkButton { text: "Lưu"; onClicked: root.save() }
            DarkButton { text: "Đóng"; onClicked: root.closeRequested() }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        ComboBox {
            visible: root.width < 700
            Layout.fillWidth: true
            model: tabs.model
            currentIndex: tabs.currentIndex
            onActivated: tabs.currentIndex = currentIndex
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
            ListView {
                id: tabs
                visible: root.width >= 700
                objectName: "settingsNavigation"
                Layout.fillHeight: true; Layout.preferredWidth: root.width < 700 ? 124 : 174
                clip: true; spacing: 5; currentIndex: 0
                model: ["Âm thanh & vỗ tay", "Giọng nói", "AI (Gemini)", "Cử chỉ", "Màn hình", "YouTube", "Tệp & ứng dụng", "Giao diện", "Mô hình 3D"]
                delegate: ItemDelegate {
                    id: section
                    required property string modelData
                    required property int index
                    width: tabs.width; height: 45
                    text: modelData
                    onClicked: tabs.currentIndex = index
                    contentItem: Text { text: section.text; color: tabs.currentIndex === section.index ? Theme.accent : Theme.textSecondary
                        font.pixelSize: 12; leftPadding: 8; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap }
                    background: Rectangle { radius: 8; color: tabs.currentIndex === section.index ? Theme.surfaceRaised : section.hovered ? Theme.surfaceDeep : "transparent"
                        border.color: tabs.currentIndex === section.index ? Theme.borderStrong : "transparent"
                        Rectangle { visible: tabs.currentIndex === section.index; width: 2; height: 16; y: 14; color: Theme.accent } }
                }
            }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: tabs.currentIndex

            // ===== 1. Âm thanh & vỗ tay =====
            Tab {
                Head { text: "Thiết bị" }
                Label2 { text: "Mic" }
                ComboBox { id: micBox; Layout.fillWidth: true
                    model: ["(Mặc định Windows)"].concat(nexa.inputDevices())
                    currentIndex: Math.max(0, model.indexOf(root.s.audio.input_device || "(Mặc định Windows)"))
                    onActivated: root.s.audio.input_device = currentIndex === 0 ? null : currentText }
                Label2 { text: "Loa phát giọng NEXA" }
                ComboBox { Layout.fillWidth: true
                    model: ["(Mặc định Windows)"].concat(nexa.outputDevices())
                    currentIndex: Math.max(0, model.indexOf(root.s.audio.output_device || "(Mặc định Windows)"))
                    onActivated: root.s.audio.output_device = currentIndex === 0 ? null : currentText }
                Label2 { text: "Host API" }
                ComboBox { Layout.fillWidth: true; model: ["MME", "Windows WASAPI", "Windows DirectSound"]
                    currentIndex: Math.max(0, model.indexOf(root.s.audio.preferred_hostapi))
                    onActivated: root.s.audio.preferred_hostapi = currentText }
                Note { text: "Lưu ý: dùng mic của tai nghe Bluetooth sẽ chuyển tai nghe sang chế độ gọi (chất lượng âm thanh giảm). Nên dùng mic laptop/USB." }

                Head { text: "Đánh thức bằng vỗ tay" }
                Label2 { text: "Chế độ" }
                ComboBox { Layout.fillWidth: true; model: ["Một tiếng vỗ tay", "Hai tiếng liên tiếp (giảm kích hoạt nhầm)"]
                    currentIndex: root.s.audio.clap.mode === "double" ? 1 : 0
                    onActivated: root.s.audio.clap.mode = currentIndex === 1 ? "double" : "single" }
                Label2 { text: "Độ nhạy: " + sens.value.toFixed(2) }
                Slider { id: sens; Layout.fillWidth: true; from: 0; to: 1; value: root.s.audio.clap.sensitivity
                         onMoved: root.s.audio.clap.sensitivity = value }
                Label2 { text: "Khoảng cách hai tiếng (ms): " + gapMin.value + " – " + gapMax.value }
                RowLayout { Layout.fillWidth: true
                    SpinBox { id: gapMin; from: 60; to: 600; stepSize: 10; value: root.s.audio.clap.double_min_gap_ms; editable: true
                              onValueModified: root.s.audio.clap.double_min_gap_ms = value }
                    SpinBox { id: gapMax; from: 300; to: 2000; stepSize: 50; value: root.s.audio.clap.double_max_gap_ms; editable: true
                              onValueModified: root.s.audio.clap.double_max_gap_ms = value } }
                Label2 { text: "Cooldown sau khi đánh thức (ms)" }
                SpinBox { from: 300; to: 5000; stepSize: 100; value: root.s.audio.clap.cooldown_ms; editable: true
                          onValueModified: root.s.audio.clap.cooldown_ms = value }
                Label2 { text: "Mức tối thiểu tuyệt đối (dBFS)" }
                SpinBox { from: -70; to: -10; value: root.s.audio.clap.min_level_dbfs; editable: true
                          onValueModified: root.s.audio.clap.min_level_dbfs = value }

                Head { text: "Búng tay (bật/tắt chuyển động mô hình 3D)" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Nhận tiếng búng tay qua mic (chỉ khi đang mở trình xem 3D)"
                            checked: root.s.audio.snap.enabled
                            onToggled: root.s.audio.snap.enabled = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Nhận động tác búng tay qua camera"
                            checked: root.s.audio.snap.camera
                            onToggled: root.s.audio.snap.camera = checked }
                Label2 { text: "Độ nhạy búng tay: " + snapSens.value.toFixed(2) }
                Slider { id: snapSens; Layout.fillWidth: true; from: 0; to: 1; value: root.s.audio.snap.sensitivity
                         onMoved: root.s.audio.snap.sensitivity = value }
                Label2 { text: "Cooldown búng tay (ms)" }
                SpinBox { from: 300; to: 3000; stepSize: 50; value: root.s.audio.snap.cooldown_ms; editable: true
                          onValueModified: root.s.audio.snap.cooldown_ms = value }
                Label2 { text: "Mức tối thiểu búng tay (dBFS)" }
                SpinBox { from: -70; to: -10; value: root.s.audio.snap.min_level_dbfs; editable: true
                          onValueModified: root.s.audio.snap.min_level_dbfs = value }

                Head { text: "Thử mic & vỗ tay" }
                DarkCheck { id: clapTest; Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Chế độ thử (vỗ tay chỉ hiện ở đây, không đánh thức NEXA)"
                            onToggled: nexa.setClapTest(checked) }
                Label2 { text: "Mức mic" }
                Rectangle { Layout.fillWidth: true; height: 14; radius: 7; color: Theme.surface; border.color: Theme.border
                    Rectangle { width: parent.width * Math.min(1, nexa.micLevel); height: parent.height; radius: 7
                                color: nexa.micLevel > 0.7 ? Theme.amber : root.cyan } }
                Label2 { id: statsLbl; text: "Nền ồn / ngưỡng" }
                Text { id: statsTxt; color: "white"; font.pixelSize: 13; text: "—" }
                Label2 { text: "Tiếng vỗ tay gần nhất" }
                Rectangle {
                    id: clapFlash; Layout.fillWidth: true; height: 34; radius: 8
                    color: Theme.surface; border.color: Theme.border
                    property var c: nexa.lastClap
                    onCChanged: flashAnim.restart()
                    Text { anchors.centerIn: parent; color: "white"; font.pixelSize: 13
                           text: parent.c.time ? (parent.c.kind === "wake" ? "ĐÁNH THỨC (" + parent.c.count + " tiếng)" : "1 tiếng (chờ tiếng thứ 2)") + " · đỉnh " + parent.c.peak_db + " dBFS · " + parent.c.time : "Chưa phát hiện" }
                    SequentialAnimation { id: flashAnim
                        ColorAnimation { target: clapFlash; property: "color"; to: "#155e75"; duration: 80 }
                        ColorAnimation { target: clapFlash; property: "color"; to: Theme.surface; duration: 700 } }
                }
                DarkButton { text: "Hiệu chuẩn lại tiếng ồn nền (giữ yên lặng 2 giây)"; Layout.columnSpan: root.width < 700 ? 1 : 2; onClicked: nexa.recalibrateClap() }
                Timer { interval: 250; repeat: true; running: tabs.currentIndex === 0 && root.visible
                        onTriggered: { var st = nexa.clapStats(); statsTxt.text = st.calibrated ? ("nền " + st.floor_db + " dBFS · ngưỡng " + st.threshold_db + " dBFS") : "đang hiệu chuẩn…" } }
                Component.onDestruction: nexa.setClapTest(false)

                Head { text: "Nghe lệnh" }
                Label2 { text: "Kết thúc câu sau khoảng lặng (ms)" }
                SpinBox { from: 300; to: 3000; stepSize: 100; value: root.s.audio.vad.end_silence_ms; editable: true
                          onValueModified: root.s.audio.vad.end_silence_ms = value }
                Label2 { text: "Độ dài tối đa một câu (giây)" }
                SpinBox { from: 3; to: 30; value: root.s.audio.vad.max_utterance_s; editable: true
                          onValueModified: root.s.audio.vad.max_utterance_s = value }
                Label2 { text: "Về chế độ chờ sau khi không hoạt động (giây)" }
                SpinBox { from: 15; to: 900; stepSize: 15; value: root.s.session.idle_timeout_s; editable: true
                          onValueModified: root.s.session.idle_timeout_s = value }

                Label2 { text: "Tâm sự: về chờ sau khi im lặng (giây)" }
                SpinBox { from: 30; to: 1800; stepSize: 30; value: root.s.session.conversation_idle_timeout_s; editable: true
                          onValueModified: root.s.session.conversation_idle_timeout_s = value }

                Head { text: "Ngủ canh gác (vỗ tay bật lại máy)" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Giữ máy không tự ngủ để NEXA còn nghe tiếng vỗ tay"
                            checked: root.s.power.clap_wake_guard; onToggled: root.s.power.clap_wake_guard = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Giữ cả màn hình sáng; gập nắp và nhấn ngắn nút nguồn/ngủ không làm gì"
                            checked: root.s.power.keep_display_awake
                            onToggled: { root.s.power.keep_display_awake = checked; if (checked) root.s.power.clap_wake_guard = true } }
                Note { text: "Giữ màn hình sáng giúp tránh ngủ tự động trên máy Modern Standby. Không ngăn được Sleep/Shut down từ Windows, giữ nút nguồn để tắt cưỡng bức, quá nhiệt hay pin yếu. Cài đặt nút nguồn/gập nắp được trả lại khi thoát NEXA." }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Lệnh \"cho máy ngủ\" tắt màn hình (thay vì ngủ thật)"
                            checked: root.s.power.screen_off; onToggled: root.s.power.screen_off = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Nút nguồn chỉ tắt màn hình (vỗ tay để bật lại)"
                            checked: root.s.power.button_turns_off_display
                            onToggled: root.s.power.button_turns_off_display = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Gập nắp không cho máy ngủ (cẩn thận khi cho máy vào túi)"
                            checked: root.s.power.lid_keep_awake; onToggled: root.s.power.lid_keep_awake = checked }
                Label2 { text: "Chào đầy đủ nếu vắng quá (giây)" }
                SpinBox { from: 30; to: 3600; stepSize: 30; value: root.s.power.away_after_s; editable: true
                          onValueModified: root.s.power.away_after_s = value }
                Label2 { text: "Lời chào khi anh quay lại" }
                DarkField { text: root.s.power.wake_greeting; placeholderText: "(tự động: Chào buổi sáng/chiều/tối anh Sơn…)"
                            onEditingFinished: root.s.power.wake_greeting = text }
                Note { text: "Khi ngủ thật, Windows đóng băng NEXA nên không nghe được vỗ tay. Chế độ giữ cả màn hình sáng ưu tiên hơn các tùy chọn tắt màn hình phía trên. Nếu tắt tùy chọn này, máy Modern Standby dùng pin vẫn có thể ngủ dù NEXA yêu cầu giữ thức." }

                Head { text: "Vào thẳng desktop khi vỗ tay (không cần mật khẩu)" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Khi NEXA canh gác, không đòi mật khẩu lúc bật màn hình lại (khuyên dùng)"
                            checked: root.s.power.no_lock; onToggled: root.s.power.no_lock = checked }
                Label2 { text: "Trạng thái dịch vụ" }
                RowLayout { Layout.fillWidth: true; spacing: 10
                    Text { color: root.unlockSvc.running ? Theme.success : root.dim; font.pixelSize: 13
                           text: root.unlockSvc.running ? "Đang chạy" : (root.unlockSvc.installed ? "Đã cài (chưa chạy)" : "Chưa cài") }
                    DarkButton { text: "Làm mới"; onClicked: root.refreshUnlock() }
                }
                Label2 { text: "Cài / gỡ dịch vụ (cần quyền quản trị)" }
                RowLayout { Layout.fillWidth: true; spacing: 10
                    DarkButton { text: "Cài dịch vụ"; onClicked: { root.unlockMsg = nexa.installUnlockService(); root.refreshUnlock() } }
                    DarkButton { text: "Gỡ dịch vụ"; onClicked: { root.unlockMsg = nexa.uninstallUnlockService(); root.refreshUnlock() } }
                }
                Note { text: root.unlockMsg; visible: root.unlockMsg !== ""; color: Theme.success }
                Note { text: "Cách hoạt động (khuyên dùng): khi NEXA canh gác, một dịch vụ chạy quyền hệ thống tắt yêu cầu 'đòi mật khẩu khi thức dậy'. Màn hình tắt → vỗ tay → sáng lại vào thẳng desktop, KHỎI gõ mã. Tắt NEXA thì tự trả lại như cũ. CẢNH BÁO: trong lúc bật, chỉ cần bật màn hình là vào được máy, không hỏi mật khẩu. Nếu anh tự bấm Win+L thì Windows vẫn khóa (cách này không chặn khóa thủ công)." }

                Head { text: "Nâng cao: tự gõ mã khi màn hình đã khóa" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Nếu máy đang khóa (ví dụ bấm Win+L), vỗ tay thì thử tự gõ mã mở khóa"
                            checked: root.s.power.auto_unlock; onToggled: root.s.power.auto_unlock = checked }
                Label2 { text: "Mã mở khóa (PIN hoặc mật khẩu Windows)" }
                RowLayout { Layout.fillWidth: true; spacing: 10
                    DarkField { id: pwField; echoMode: TextInput.Password; Layout.fillWidth: true
                                placeholderText: "Nhập mã rồi bấm Lưu — mã KHÔNG hiện, KHÔNG lưu vào tệp cài đặt" }
                    DarkButton { text: "Lưu mã"; onClicked: { root.unlockMsg = nexa.setUnlockPassword(pwField.text); pwField.text = "" } }
                    DarkButton { text: "Xóa mã"; onClicked: { root.unlockMsg = nexa.clearUnlockPassword(); pwField.text = "" } }
                }
                Note { text: "Cách này gõ mã vào màn hình khóa (vùng bảo mật) — kém ổn định hơn tùy máy. Nếu đã bật mục 'không đòi mật khẩu' ở trên thì thường không cần tới đây. Mã được mã hóa lưu trong máy, không nằm trong tệp cài đặt." }
            }

            // ===== 2. Giọng nói =====
            Tab {
                Head { text: "Nhận dạng giọng nói (faster-whisper, chạy cục bộ)" }
                Label2 { text: "Model" }
                ComboBox { Layout.fillWidth: true; model: nexa.sttModels()
                    currentIndex: Math.max(0, model.indexOf(root.s.stt.model))
                    onActivated: root.s.stt.model = currentText }
                Note { text: "small: cân bằng cho CPU. medium / large-v3-turbo: chính xác hơn với tiếng Việt nhưng nặng và chậm hơn trên CPU. Model tải từ Hugging Face (Systran) ở lần dùng đầu và lưu trong models/whisper." }
                Label2 { text: "Beam size" }
                SpinBox { from: 1; to: 5; value: root.s.stt.beam_size; onValueModified: root.s.stt.beam_size = value }

                Head { text: "Đọc văn bản (TTS)" }
                Label2 { text: "Backend" }
                ComboBox { Layout.fillWidth: true; model: ["auto", "edge", "winrt", "sapi", "none"]
                    currentIndex: Math.max(0, model.indexOf(root.s.tts.backend))
                    onActivated: root.s.tts.backend = currentText }
                Repeater {
                    model: nexa.ttsBackends()
                    delegate: Text { Layout.columnSpan: root.width < 700 ? 1 : 2; color: modelData.available ? Theme.success : Theme.danger; font.pixelSize: 12; wrapMode: Text.Wrap
                                     Layout.fillWidth: true
                                     text: (modelData.available ? "✓ " : "✗ ") + modelData.name + (modelData.online ? " (online, cần Internet)" : " (offline)") + ": " + modelData.info }
                }
                Note { text: "edge dùng dịch vụ đọc văn bản trực tuyến của Microsoft Edge: cần Internet và có thể lỗi/giới hạn. winrt dùng giọng Windows cài trên máy (ví dụ Microsoft An). Không có giọng nào thì NEXA trả lời bằng chữ." }
                Label2 { text: "Giọng edge" }
                ComboBox { Layout.fillWidth: true; model: nexa.edgeVoices()
                    currentIndex: Math.max(0, model.indexOf(root.s.tts.edge_voice))
                    onActivated: root.s.tts.edge_voice = currentText }
                Label2 { text: "Hiệu ứng giọng" }
                ComboBox { Layout.fillWidth: true; model: nexa.voiceEffects()
                    currentIndex: Math.max(0, model.indexOf(root.s.tts.effect || "none"))
                    onActivated: root.s.tts.effect = currentText }
                Label2 { text: "Mức hiệu ứng: " + fxStr.value.toFixed(2) }
                Slider { id: fxStr; Layout.fillWidth: true; from: 0; to: 1; stepSize: 0.05; value: root.s.tts.effect_strength
                         onMoved: root.s.tts.effect_strength = value }
                Label2 { text: "Cao độ giọng Edge (Hz): " + edgePitch.value }
                Slider { id: edgePitch; Layout.fillWidth: true; from: -40; to: 20; stepSize: 1; value: root.s.tts.edge_pitch_hz
                         onMoved: root.s.tts.edge_pitch_hz = value }
                Note { text: "Mặc định: giọng nam đa ngữ en-US-AndrewMultilingualNeural (cần Internet, đọc được cả tiếng Việt lẫn thuật ngữ tiếng Anh) + hiệu ứng jarvis (trong trẻo, vang phòng nhẹ). vi-VN-NamMinhNeural cho giọng Việt chuẩn hơn; robot = giọng kim loại kiểu cũ. Khi mất mạng, NEXA dùng giọng Windows (Microsoft An) đã hạ cao độ." }
                Label2 { text: "Giọng Windows (winrt)" }
                ComboBox { Layout.fillWidth: true; model: ["(tự chọn giọng vi-VN)"].concat(nexa.winrtVoices())
                    currentIndex: Math.max(0, model.indexOf(root.s.tts.winrt_voice || "(tự chọn giọng vi-VN)"))
                    onActivated: root.s.tts.winrt_voice = currentIndex === 0 ? "" : currentText }
                Label2 { text: "Tốc độ đọc: " + rate.value.toFixed(0) + "%" }
                Slider { id: rate; Layout.fillWidth: true; from: -50; to: 50; stepSize: 5; value: root.s.tts.rate; onMoved: root.s.tts.rate = value }
                Label2 { text: "Lời chào khi thức dậy" }
                DarkField { text: root.s.session.greeting; onEditingFinished: root.s.session.greeting = text }
                DarkButton { text: "Lưu rồi nghe thử"; Layout.columnSpan: root.width < 700 ? 1 : 2; onClicked: { root.save(); nexa.testTts() } }
            }

            // ===== 3. AI (Gemini) =====
            Tab {
                id: aiTab
                property string testMsg: ""
                property bool testOk: false
                Connections { target: nexa; function onGeminiTestFinished(ok, msg) { aiTab.testOk = ok; aiTab.testMsg = msg } }
                Head { text: "Gemini — bộ AI chính" }
                Label2 { text: "Trạng thái" }
                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 13
                       color: nexa.status.ai && nexa.status.ai.ok ? Theme.success : Theme.amber
                       text: (nexa.status.ai && nexa.status.ai.reason) || "—" }
                Label2 { text: "API key" }
                Text { color: "white"; font.pixelSize: 13
                       text: !nexa.status.ai ? "—" : nexa.status.ai.key === "set" ? "Đã đặt (không hiển thị)" : nexa.status.ai.key === "placeholder" ? "Vẫn là giá trị mẫu" : "Chưa có" }
                Label2 { text: "Nhập key mới (ẩn ký tự)" }
                RowLayout { Layout.fillWidth: true
                    DarkField { id: keyField; echoMode: TextInput.Password; placeholderText: "Dán GEMINI_API_KEY mới của anh" }
                    DarkCheck { id: persistKey; text: "Lưu vào .env cục bộ"; checked: true }
                    DarkButton { text: "Đặt key"; onClicked: { aiTab.testMsg = nexa.setApiKey(keyField.text, persistKey.checked); keyField.text = "" } } }
                Note { text: "Key chỉ lưu trên máy này (biến môi trường của phiên hoặc tệp .env ở thư mục NEXA). NEXA không ghi key vào log, giao diện hay tệp cấu hình settings.yaml." }
                Label2 { text: "Model (GEMINI_MODEL)" }
                RowLayout { Layout.fillWidth: true
                    DarkField { id: modelField; text: (nexa.status.ai && nexa.status.ai.model) || "" }
                    DarkButton { text: "Dùng model này"; onClicked: nexa.setGeminiModel(modelField.text) } }
                Note { text: "Mặc định: gemini-3.5-flash-lite (ổn định, hỗ trợ function calling và ảnh, độ trễ/chi phí thấp). Có thể đổi sang model khác mà key của anh truy cập được, ví dụ gemini-3.8-flash. NEXA không tự đổi sang model khác khi lỗi." }
                DarkButton { text: "Kiểm tra kết nối Gemini"; onClicked: { aiTab.testMsg = "Đang kiểm tra…"; nexa.testGemini() } }
                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: aiTab.testMsg; color: aiTab.testOk ? Theme.success : Theme.amber; font.pixelSize: 13 }

                Head { text: "Quyền điều khiển" }
                Label2 { text: "Mức quyền" }
                ComboBox { Layout.fillWidth: true; model: ["Tiêu chuẩn — hỏi xác nhận hành động rủi ro", "Toàn quyền — không hỏi xác nhận"]
                    currentIndex: root.s.safety.autonomy === "full" ? 1 : 0
                    onActivated: root.s.safety.autonomy = currentIndex === 1 ? "full" : "standard" }
                Note { text: "Toàn quyền: NEXA tự thực hiện mọi lệnh (nhấp chuột theo tọa độ, bấm nút Gửi/Xóa, phím Enter trong ứng dụng chat, đóng cửa sổ, xóa vào Thùng rác, tắt máy hẹn 60 giây…) mà không hỏi lại; mỗi lần tự duyệt vẫn được ghi trong bảng Tác vụ và log. Vẫn giữ: DỪNG KHẨN CẤP / Ctrl+Alt+Esc / 'Dừng lại', xóa chỉ vào Thùng rác, xem trước ảnh trước khi gửi lên Gemini. Nhận dạng giọng nói có thể nghe nhầm — với toàn quyền, lệnh nghe nhầm cũng được thực hiện ngay." }

                Head { text: "Đọc màn hình bằng Gemini (NEXA_CLOUD_SCREEN_VISION)" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Cho phép gửi ảnh chụp cửa sổ/vùng do anh chọn lên Gemini khi anh yêu cầu 'đọc màn hình'"
                            checked: !!(nexa.status.ai && nexa.status.ai.vision); onToggled: nexa.setCloudVision(checked) }
                Note { text: "Mỗi lần gửi, NEXA hiện ảnh xem trước để anh kéo chọn vùng và bấm Đồng ý. Khi tắt, NEXA không chụp và không gửi ảnh. NEXA không tự phát hiện được mọi thông tin bí mật — anh tránh chọn vùng có mật khẩu/key." }

                Head { text: "Sử dụng trong phiên" }
                Label2 { text: "Số lần gọi / token" }
                Text { color: "white"; font.pixelSize: 13
                       text: nexa.status.ai && nexa.status.ai.usage ? ((nexa.status.ai.calls || 0) + " lần gọi · vào " + nexa.status.ai.usage.prompt + " · ra " + nexa.status.ai.usage.output + " · suy nghĩ " + nexa.status.ai.usage.thoughts + " token") : "—" }
                Label2 { text: "Giới hạn nội bộ của NEXA" }
                RowLayout {
                    SpinBox { from: 10; to: 5000; stepSize: 10; value: root.s.ai.max_calls_per_session; editable: true; onValueModified: root.s.ai.max_calls_per_session = value }
                    Text { text: "lần gọi/phiên · lịch sử"; color: root.dim }
                    SpinBox { from: 2; to: 50; value: root.s.ai.max_history_turns; onValueModified: root.s.ai.max_history_turns = value }
                    Text { text: "lượt"; color: root.dim }
                }
                Note { text: "Đây là giới hạn trong ứng dụng, khác với quota tài khoản Google. Quota/giá thực tế xem tại Google AI Studio. Số bước công cụ tối đa và timeout đọc từ NEXA_MAX_TOOL_STEPS và GEMINI_REQUEST_TIMEOUT_SECONDS trong .env." }
                Label2 { text: "Hội thoại" }
                DarkButton { text: "Xóa hội thoại và bản đã lưu trên máy"; onClicked: nexa.clearConversation() }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Lưu hội thoại trên thiết bị này (mặc định tắt)"
                            checked: root.s.ai.persist_history === true; onToggled: root.s.ai.persist_history = checked }
                Note { text: "Sau khi Lưu cài đặt: chỉ lưu các lượt trò chuyện chữ hoàn tất tiếp theo; bỏ lượt dùng công cụ và không ghi trực tiếp ghi chú/ngữ cảnh hệ thống. Tệp JSON không mã hóa mặc định ở %LOCALAPPDATA%/NEXA/conversation_history.json (cấu hình tùy chỉnh có thể dùng thư mục riêng), tối đa số lượt ở trên và 256 KB; khôi phục làm ngữ cảnh AI khi mở lại. Tắt rồi Lưu ngừng lưu và yêu cầu xóa bản trên đĩa; nút Xóa hội thoại xóa bộ nhớ và yêu cầu xóa tệp. Nếu lỗi quyền truy cập/ổ đĩa, tệp có thể còn và NEXA ghi cảnh báo trong log; cần kiểm tra/xóa tệp thủ công. Nội dung anh nhập và câu trả lời vẫn có thể chứa thông tin riêng tư; bộ lọc API key không loại bỏ mọi bí mật." }
                Note { text: "Dữ liệu gửi Gemini: câu lệnh đã chuyển thành chữ, giờ hiện tại, tên cửa sổ đang làm việc, số màn hình và kết quả các công cụ. Không gửi audio, video camera hay màn hình (trừ khi anh dùng 'đọc màn hình' và bấm Đồng ý). Mặc định lịch sử chỉ ở bộ nhớ; lưu trên thiết bị là tùy chọn ở trên. NEXA dùng API generate_content không lưu hội thoại phía máy chủ theo tính năng của NEXA, nhưng việc Google xử lý/lưu dữ liệu tuân theo điều khoản gói API anh dùng." }
            }

            // ===== 4. Cử chỉ =====
            Tab {
                id: gTab
                property string calMsg: ""
                Connections { target: nexa; function onCalibrationFinished(msg) { gTab.calMsg = msg } }
                Head { text: "Camera" }
                Label2 { text: "Chỉ số camera" }
                RowLayout { Layout.fillWidth: true
                    SpinBox { id: camIdx; from: 0; to: 9; value: root.s.gestures.camera_index; onValueModified: root.s.gestures.camera_index = value }
                    DarkButton { text: "Quét camera"; onClicked: camList.text = nexa.cameras().map(function(c) { return c.name }).join(" · ") || "Không thấy camera" }
                    Text { id: camList; color: root.dim; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight } }
                Label2 { text: "Tay điều khiển" }
                ComboBox { Layout.fillWidth: true; model: ["Bất kỳ", "Tay phải", "Tay trái"]
                    currentIndex: ["any", "right", "left"].indexOf(root.s.gestures.control_hand)
                    onActivated: root.s.gestures.control_hand = ["any", "right", "left"][currentIndex] }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Bật chế độ cử chỉ khi khởi động"; checked: root.s.gestures.enabled_on_start
                            onToggled: root.s.gestures.enabled_on_start = checked }

                Head { text: "Ngưỡng (giá trị khởi đầu — cần hiệu chuẩn theo webcam của anh)" }
                Label2 { text: "Giữ yên (ms): nắm tay / mở tay" }
                SpinBox { from: 200; to: 1500; stepSize: 50; value: root.g.hold.hold_ms; editable: true; onValueModified: root.g.hold.hold_ms = value }
                Label2 { text: "Giữ yên (ms): chỉ tay, like/dislike, hai ngón" }
                SpinBox { from: 300; to: 2000; stepSize: 50; value: root.g.hold.action_hold_ms; editable: true; onValueModified: root.g.hold.action_hold_ms = value }
                Label2 { text: "Ngưỡng đứng yên (tay/giây): " + stSpd.value.toFixed(1) }
                Slider { id: stSpd; Layout.fillWidth: true; from: 0.3; to: 3; stepSize: 0.1; value: root.g.hold.still_speed; onMoved: root.g.hold.still_speed = value }
                Label2 { text: "Cooldown sau cử chỉ (ms)" }
                SpinBox { from: 300; to: 3000; stepSize: 50; value: root.g.timing.cooldown_ms; editable: true; onValueModified: root.g.timing.cooldown_ms = value }
                Label2 { text: "Cuộn: mỗi lần cách nhau (ms)" }
                SpinBox { from: 80; to: 1000; stepSize: 20; value: root.g.scroll.repeat_ms; editable: true; onValueModified: root.g.scroll.repeat_ms = value }
                Label2 { text: "Cuộn: số nấc mỗi lần" }
                SpinBox { from: 1; to: 10; value: root.g.scroll.notch_size; editable: true; onValueModified: root.g.scroll.notch_size = value }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Đảo chiều cuộn (invert_scroll) — giữ hai ngón sẽ cuộn nội dung xuống thay vì lên"
                            checked: root.g.scroll.invert_scroll; onToggled: root.g.scroll.invert_scroll = checked }

                Head { text: "Hiệu chuẩn hướng (preview dạng gương)" }
                Note { text: "Bật camera, bấm một nút rồi giữ yên đúng tư thế ghi trên nút khoảng 1 giây. NEXA đo hướng thực tế và tự đảo trục nếu camera đã lật sẵn. Khi hiệu chuẩn, cử chỉ không kích hoạt thao tác." }
                DarkButton { text: "Hiệu chuẩn: tôi sẽ CHỈ NGÓN TRỎ SANG PHẢI"; onClicked: { gTab.calMsg = "Mời anh giữ ngón trỏ chỉ sang phải…"; nexa.calibrateGesture("right") } }
                DarkButton { text: "Hiệu chuẩn: tôi sẽ GIƠ NGÓN CÁI LÊN (like)"; onClicked: { gTab.calMsg = "Mời anh giữ ngón cái chỉ lên…"; nexa.calibrateGesture("up") } }
                Text { Layout.columnSpan: root.width < 700 ? 1 : 2; text: gTab.calMsg; color: Theme.success; font.pixelSize: 13 }
                Text { Layout.columnSpan: root.width < 700 ? 1 : 2; color: root.dim; font.pixelSize: 12
                       text: "Hiện tại: đảo trục ngang = " + root.g.calibration.invert_x + " · đảo trục dọc = " + root.g.calibration.invert_y }
            }

            // ===== 5. Màn hình =====
            Tab {
                id: mTab
                property var mons: nexa.monitors()
                property string msg: ""
                Connections { target: nexa; function onMonitorsChanged() { mTab.mons = nexa.monitors() } }
                Head { text: "Hai màn hình" }
                Note { text: "Bấm 'Nhận diện màn hình' để hiện nhãn lớn trên từng màn hình, rồi chọn màn hình nguồn (1) và đích (2). NEXA lưu định danh thiết bị (không chỉ số thứ tự) và kiểm tra lại mỗi lần thao tác." }
                DarkButton { text: "Nhận diện màn hình"; onClicked: { mTab.mons = nexa.monitors(); nexa.identifyMonitors() } }
                DarkButton { text: "Làm mới"; onClicked: mTab.mons = nexa.monitors() }
                Repeater {
                    model: mTab.mons
                    delegate: Text {
                        Layout.columnSpan: root.width < 700 ? 1 : 2; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "white"; font.pixelSize: 13
                        text: (modelData.role === "source" ? "[NGUỒN 1] " : modelData.role === "target" ? "[ĐÍCH 2] " : "") +
                              modelData.device_name + " · " + modelData.friendly_name + " · " + modelData.width + "×" + modelData.height +
                              " tại (" + modelData.x + ", " + modelData.y + ") · DPI " + modelData.dpi + " (" + modelData.scale + "%)" + (modelData.primary ? " · chính" : "")
                    }
                }
                Label2 { text: "Màn hình nguồn (1)" }
                ComboBox { id: srcBox; Layout.fillWidth: true; model: mTab.mons.map(function(m) { return m.device_name + " · " + m.friendly_name })
                           currentIndex: Math.max(0, mTab.mons.findIndex(function(m) { return m.role === "source" })) }
                Label2 { text: "Màn hình đích (2)" }
                ComboBox { id: dstBox; Layout.fillWidth: true; model: mTab.mons.map(function(m) { return m.device_name + " · " + m.friendly_name })
                           currentIndex: Math.max(0, mTab.mons.findIndex(function(m) { return m.role === "target" })) }
                DarkButton { text: "Lưu vai trò màn hình"; enabled: mTab.mons.length >= 2
                             onClicked: mTab.msg = nexa.setMonitorRoles(mTab.mons[srcBox.currentIndex].device_name, mTab.mons[dstBox.currentIndex].device_name) }
                Text { text: mTab.mons.length < 2 ? "Chỉ phát hiện " + mTab.mons.length + " màn hình (chế độ Duplicate hoặc chưa cắm màn hình 2)." : mTab.msg
                       color: mTab.mons.length < 2 ? Theme.amber : Theme.success; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }

            // ===== 6. YouTube =====
            Tab {
                id: yTab
                property var targets: nexa.mediaTargets()
                property string msg: ""
                Connections { target: nexa; function onMediaTargetsChanged() { yTab.targets = nexa.mediaTargets() } }
                Head { text: "Mục tiêu YouTube cho nắm tay / mở tay" }
                Label2 { text: "NEXA Bridge (extension)" }
                Text { color: nexa.status.bridge && nexa.status.bridge.connected ? Theme.success : Theme.amber; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true
                       text: nexa.status.bridge && nexa.status.bridge.connected ? "Đã kết nối: " + nexa.status.bridge.browsers.join(", ") : "Chưa kết nối — cài theo browser_bridge/README.md" }
                Label2 { text: "Backend" }
                ComboBox { Layout.fillWidth: true; model: ["auto", "bridge", "gsmtc"]; currentIndex: Math.max(0, model.indexOf(root.s.media.backend))
                           onActivated: root.s.media.backend = currentText }
                Note { text: "Không cần gắn tab: nói \"tạm dừng\" / nắm tay thì NEXA tự tìm video ĐANG PHÁT trong trình duyệt, \"phát tiếp\" / xòe tay thì tìm video ĐANG DỪNG (ưu tiên video NEXA vừa mở). Chỉ điều khiển trình duyệt, không đụng Spotify hay ứng dụng khác. Chọn tay bên dưới chỉ khi anh muốn cố định một video. bridge: chính xác tới từng tab (cần extension); gsmtc: Windows Media Controls, không cần cài gì." }
                Label2 { text: "Đang gắn" }
                Text { color: "white"; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true
                       text: nexa.mediaStatus.bound ? nexa.mediaStatus.bound.title + " [" + nexa.mediaStatus.bound.backend + " · " + nexa.mediaStatus.bound.app + "]" : "Tự động" }
                DarkButton { text: "Làm mới danh sách"; onClicked: { nexa.refreshMedia(); yTab.targets = nexa.mediaTargets() } }
                Text { text: yTab.msg; color: Theme.success; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Repeater {
                    model: yTab.targets
                    delegate: RowLayout {
                        Layout.columnSpan: root.width < 700 ? 1 : 2; Layout.fillWidth: true
                        Text { Layout.fillWidth: true; elide: Text.ElideRight; color: "white"; font.pixelSize: 13
                               text: "[" + modelData.backend + " · " + modelData.app + "] " + modelData.title }
                        DarkButton { text: "Gắn"; onClicked: yTab.msg = nexa.bindMedia(modelData.id) }
                    }
                }
            }

            // ===== 7. Tệp & ứng dụng =====
            Tab {
                Head { text: "Phạm vi tệp được phép" }
                Note { text: "Mỗi dòng một thư mục. NEXA chỉ tìm/mở/tạo/đổi tên/sao chép/di chuyển/xóa (vào Thùng rác) bên trong các thư mục này." }
                TextArea { Layout.columnSpan: root.width < 700 ? 1 : 2; Layout.fillWidth: true; Layout.preferredHeight: 110; color: "white"; font.pixelSize: 13
                           text: root.s.files.allowed_roots.join("\n")
                           background: Rectangle { color: Theme.surface; radius: 6; border.color: Theme.border }
                           onEditingFinished: root.s.files.allowed_roots = text.split("\n").map(function(x) { return x.trim() }).filter(function(x) { return x.length }) }
                Label2 { text: "Thư mục lưu ảnh chụp màn hình" }
                DarkField { text: root.s.files.screenshot_dir; onEditingFinished: root.s.files.screenshot_dir = text }
                Head { text: "Ứng dụng" }
                Label2 { text: "Đường dẫn trình duyệt (bỏ trống = mặc định Windows)" }
                DarkField { text: root.s.apps.browser_path; onEditingFinished: root.s.apps.browser_path = text }
                Note { text: "Ứng dụng tự thêm — mỗi dòng: Tên | đường dẫn .exe hoặc lối tắt | tên gọi khác 1, tên gọi khác 2" }
                TextArea {
                    Layout.columnSpan: root.width < 700 ? 1 : 2; Layout.fillWidth: true; Layout.preferredHeight: 120; color: "white"; font.pixelSize: 13
                    background: Rectangle { color: Theme.surface; radius: 6; border.color: Theme.border }
                    text: root.s.apps.custom.map(function(a) { return a.name + " | " + a.path + " | " + (a.aliases || []).join(", ") }).join("\n")
                    onEditingFinished: {
                        root.s.apps.custom = text.split("\n").map(function(line) {
                            var p = line.split("|").map(function(x) { return x.trim() })
                            if (p.length < 2 || !p[0] || !p[1]) return null
                            return { name: p[0], path: p[1], aliases: p.length > 2 && p[2] ? p[2].split(",").map(function(x) { return x.trim() }).filter(function(x) { return x.length }) : [] }
                        }).filter(function(x) { return x !== null })
                    }
                }
                Label2 { text: "Mẫu URL tìm kiếm ({query})" }
                DarkField { text: root.s.apps.search_engine; onEditingFinished: root.s.apps.search_engine = text }
            }

            // ===== 8. Giao diện =====
            Tab {
                Head { text: "Hiệu ứng" }
                Label2 { text: "Mức hiệu ứng" }
                ComboBox { Layout.fillWidth: true; model: ["full", "reduced", "minimal"]; currentIndex: Math.max(0, model.indexOf(root.s.ui.effects))
                           onActivated: root.s.ui.effects = currentText }
                Note { text: "reduced/minimal giảm hạt sáng, lưới và vòng quỹ đạo cho máy yếu (chế độ nhẹ)." }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Overlay trên màn hình khi điều khiển máy (click-through)"; checked: root.s.ui.overlay; onToggled: root.s.ui.overlay = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Âm thanh hiệu ứng"; checked: root.s.ui.sounds; onToggled: root.s.ui.sounds = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Vòng thông số quanh quả cầu (CPU · RAM · GPU · độ trễ AI)"; checked: root.s.ui.stats_ring; onToggled: root.s.ui.stats_ring = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Hiện FPS đo được";checked: root.s.ui.show_fps; onToggled: root.s.ui.show_fps = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Khởi động ở chế độ quả cầu thu gọn"; checked: root.s.ui.compact_on_start; onToggled: root.s.ui.compact_on_start = checked }
                Head { text: "HUD góc màn hình (theme Arc Reactor)" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Bật HUD (trong suốt, click xuyên qua)"; checked: root.s.ui.hud.enabled; onToggled: root.s.ui.hud.enabled = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Phụ đề câu NEXA đang nói"; checked: root.s.ui.hud.subtitles; onToggled: root.s.ui.hud.subtitles = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Thẻ kết quả khi lệnh chạy xong / lỗi"; checked: root.s.ui.hud.cards; onToggled: root.s.ui.hud.cards = checked }
                Label2 { text: "Màn hình hiển thị" }
                ComboBox {
                    id: hudScreen
                    Layout.fillWidth: true
                    property var ids: ["primary", "cursor"].concat(nexa.monitors().map(function(m) { return m.device_name }))
                    model: ["Màn hình chính", "Màn hình đang có chuột"].concat(nexa.monitors().map(function(m) {
                        return m.device_name.replace(/^[\\.]+/, "") + " · " + m.friendly_name + " · " + m.width + "×" + m.height }))
                    currentIndex: Math.max(0, ids.indexOf(root.s.ui.hud.screen))
                    onActivated: root.s.ui.hud.screen = ids[currentIndex]
                }
                Label2 { text: "Góc" }
                ComboBox {
                    Layout.fillWidth: true
                    property var ids: ["bottom_right", "bottom_left", "top_right", "top_left"]
                    model: ["Dưới phải", "Dưới trái", "Trên phải", "Trên trái"]
                    currentIndex: Math.max(0, ids.indexOf(root.s.ui.hud.corner))
                    onActivated: root.s.ui.hud.corner = ids[currentIndex]
                }
                Label2 { text: "Thẻ tự ẩn sau (giây)" }
                SpinBox { from: 2; to: 20; value: root.s.ui.hud.card_seconds; onValueModified: root.s.ui.hud.card_seconds = value }
                DarkButton { text: "Lưu rồi xem thử HUD"; Layout.columnSpan: root.width < 700 ? 1 : 2; onClicked: { root.save(); nexa.testHud() } }
                Head { text: "Nhật ký" }
                Text { Layout.columnSpan: root.width < 700 ? 1 : 2; color: root.dim; font.pixelSize: 12; text: "Log xoay vòng: " + nexa.logPath() + " (đã lọc API key)" }
            }

            // ===== 9. Mô hình 3D =====
            Tab {
                id: t3
                property var d: root.s.three_d
                property var gg: root.s.three_d.gesture
                component NumField: DarkField {
                    property string key: ""
                    property var obj: t3.d
                    text: obj[key] !== undefined ? String(obj[key]) : ""
                    validator: DoubleValidator { bottom: 0 }
                    onEditingFinished: { var v = Number(text); if (!isNaN(v)) obj[key] = v }
                }
                Head { text: "Tạo mô hình" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Bật tính năng mô hình 3D"; checked: t3.d.enabled; onToggled: t3.d.enabled = checked }
                Label2 { text: "Chế độ mặc định" }
                ComboBox { Layout.fillWidth: true; model: ["auto", "parametric", "cloud"]; currentIndex: Math.max(0, model.indexOf(t3.d.default_mode))
                           onActivated: t3.d.default_mode = currentText }
                Note { text: "auto: mức 1 — CAD tham số cục bộ cho UAV, xe tự hành, robot người, robot chó, trực thăng, ốc vít và chi tiết cơ khí (offline, có assembly, kích thước chính xác). Vật thể khác: Tripo/Meshy nếu có API key; không thì mức 2 — Gemini thiết kế CAD DSL, tự sửa lỗi và xem ảnh để tinh chỉnh; mức 3 miễn phí (Hugging Face Space) dùng khi nói \"chất lượng cao\"/\"bằng hugging face\" hoặc khi mức 2 không đạt." }
                Label2 { text: "Dịch vụ 3D cloud" }
                ComboBox { Layout.fillWidth: true; model: ["auto", "tripo", "meshy", "hf_space", "none"]; currentIndex: Math.max(0, model.indexOf(t3.d.provider))
                           onActivated: t3.d.provider = currentText }
                Note { text: "API key KHÔNG lưu ở đây: đặt TRIPO_API_KEY, MESHY_API_KEY hoặc HF_TOKEN (miễn phí, tăng hạn mức GPU của Hugging Face) trong tệp .env (biến NEXA_3D_PROVIDER nếu có sẽ được ưu tiên). Trạng thái: " +
                             (nexa3d.providerStatus.ok ? "sẵn sàng" : nexa3d.providerStatus.reason) }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Cho phép Hugging Face Space miễn phí (gửi mô tả + ảnh sinh ra tới Space công khai)"; checked: t3.d.hf_enabled; onToggled: t3.d.hf_enabled = checked }
                Label2 { text: "Mức 2: số vòng Gemini xem ảnh và sửa mô hình (0–4)" }
                NumField { key: "dsl_refine_rounds" }
                Label2 { text: "Mức 2: điểm dưới ngưỡng này thì thử thêm mức 3 (0 = tắt)" }
                NumField { key: "dsl_fallback_below" }
                Label2 { text: "Ngưỡng đạt chất lượng (điểm /100)" }
                NumField { key: "quality_threshold" }
                Label2 { text: "Số ứng viên cloud (chất lượng cao, 1–3)" }
                NumField { key: "candidate_count" }
                Label2 { text: "Số vòng làm lại tối đa (0–2)" }
                NumField { key: "refinement_rounds" }
                Label2 { text: "Thời gian tối đa mỗi yêu cầu (giây)" }
                NumField { key: "generation_timeout_s" }
                Label2 { text: "Giới hạn chi phí mỗi yêu cầu (credit, 0 = không giới hạn)" }
                NumField { key: "max_cost_per_job" }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Gemini chấm ảnh render 6 góc (chỉ là một phần điểm)"; checked: t3.d.ai_review; onToggled: t3.d.ai_review = checked }
                Label2 { text: "Ảnh tham chiếu nhiều góc (Gemini ảnh)" }
                ComboBox { Layout.fillWidth: true; model: ["auto", "on", "off"]; currentIndex: Math.max(0, model.indexOf(String(t3.d.reference_images)))
                           onActivated: t3.d.reference_images = currentText }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Tách bộ phận mô hình cloud (mesh segmentation, tốn thêm credit)"; checked: t3.d.cloud_segmentation; onToggled: t3.d.cloud_segmentation = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Tự mở trình xem khi mô hình xong"; checked: t3.d.open_viewer_when_ready; onToggled: t3.d.open_viewer_when_ready = checked }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Tự bật camera cử chỉ khi mở trình xem 3D"; checked: t3.d.viewer_auto_camera; onToggled: t3.d.viewer_auto_camera = checked }
                Head { text: "Giới hạn tài nguyên" }
                Label2 { text: "Dung lượng asset tối đa (MB)" }
                NumField { key: "max_asset_mb" }
                Label2 { text: "Số tam giác tối đa" }
                NumField { key: "max_triangles" }
                Label2 { text: "Kích thước texture tối đa (px)" }
                NumField { key: "max_texture_size" }
                Label2 { text: "Ngân sách tam giác của viewer (vượt → dùng LOD)" }
                NumField { key: "viewer_triangle_budget" }
                Label2 { text: "Dung lượng cache (MB)" }
                NumField { key: "cache_size_mb" }
                Head { text: "Cử chỉ trong trình xem 3D" }
                Note { text: "Bàn tay mở đưa vào camera, giữ yên ~0,2 s rồi di chuyển = xoay. Nắm tay giữ yên 0,5 s → mở tay giữ yên 0,35 s = tách bộ phận (đúng một lần). Nắm tay giữ yên khi đang tách = lắp lại. Hai ngón đưa lên/xuống = thu phóng. Trong lúc xem 3D, chuột bằng tay và sáu cử chỉ hệ thống tạm ngưng." }
                Label2 { text: "Độ nhạy xoay (độ / kích thước bàn tay)" }
                NumField { key: "rotate_sensitivity"; obj: t3.gg }
                Label2 { text: "Vùng chết khi bắt đầu xoay (× kích thước tay)" }
                NumField { key: "rotate_deadzone"; obj: t3.gg }
                Label2 { text: "Thời gian ổn định bàn tay mở (ms)" }
                NumField { key: "acquire_ms"; obj: t3.gg }
                Label2 { text: "Giữ nắm tay để chuẩn bị tách (ms)" }
                NumField { key: "fist_hold_ms"; obj: t3.gg }
                Label2 { text: "Giữ bàn tay mở để tách (ms)" }
                NumField { key: "open_hold_ms"; obj: t3.gg }
                Label2 { text: "Nghỉ sau tách/lắp (ms)" }
                NumField { key: "cooldown_ms"; obj: t3.gg }
                Label2 { text: "Quán tính xoay (0–0,9)" }
                NumField { key: "inertia"; obj: t3.gg }
                DarkCheck { Layout.columnSpan: root.width < 700 ? 1 : 2; text: "Hai ngón để thu phóng"; checked: t3.gg.zoom_two_fingers; onToggled: t3.gg.zoom_two_fingers = checked }
            }
        }
        }
    }
}
