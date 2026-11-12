import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtQuick.Shapes
import "Theme.js" as Theme

ApplicationWindow {
    id: win
    width: 1320; height: 820
    minimumWidth: nexa.compact ? 200 : 600
    minimumHeight: nexa.compact ? 200 : 640
    visible: true
    title: "NEXA / COMMAND CENTER — NXS MEDIA"
    color: Theme.bg
    font.family: Theme.font
    palette.window: Theme.surface
    palette.windowText: Theme.textPrimary
    palette.base: Theme.surfaceDeep
    palette.alternateBase: Theme.surfaceRaised
    palette.text: Theme.textPrimary
    palette.button: Theme.surfaceRaised
    palette.buttonText: Theme.textPrimary
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.bg
    palette.mid: Theme.border
    palette.light: Theme.borderStrong
    palette.dark: Theme.bg
    palette.placeholderText: Theme.textMuted
    flags: nexa.compact ? (Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool) : Qt.Window

    readonly property color cyan: Theme.accent
    readonly property color blue: Theme.blue
    readonly property color purple: Theme.silver
    readonly property color panel: Theme.surface
    readonly property color panelBorder: Theme.border
    readonly property color textDim: Theme.textSecondary
    property var savedGeometry: null
    property string pendingProductPanel: ""
    // Trình xem 3D mở SONG SONG với giao diện NEXA (cột phải), không che NEXA.
    readonly property bool viewer3dOpen: nexa3d.viewerOpen
    readonly property bool educationOpen: nexaEdu.open
    // Sinh code cũng mở SONG SONG (cột phải) như trình xem 3D; đang mở code thì trình xem 3D nhường chỗ.
    readonly property bool codeShown: nexaCode.panelOpen && !nexa.compact
    readonly property bool viewerShown: viewer3dOpen && !nexa.compact && !codeShown
    readonly property bool sideShown: viewerShown || codeShown || educationOpen
    // cột NEXA khi có bảng bên phải: đủ cho quả cầu + hội thoại, phần còn lại cho bảng (≥ bề ngang iPad mini khi đủ chỗ)
    readonly property real sideNexaWidth: Math.max(360, Math.min(520, win.width * 0.32))
    // Cửa sổ hẹp (NEXA xếp cạnh ứng dụng vừa mở — nexa/desktop/side_by_side.py): quả cầu trên, hội thoại dưới.
    readonly property bool narrow: !nexa.compact && width < 1000
    readonly property bool stacked: sideShown || narrow
    // bố cục chiến thuật: bảng SYS bên trái và nhật ký LOG bên phải chỉ gắn cố định khi đủ rộng
    readonly property bool sysDocked: !stacked && width >= 1000
    readonly property bool logDocked: false // history now floats below the core, never in the right rail
    property bool autoMaximized: false
    function makeRoom() {
        if (nexa.compact) win.enterCompact(false)
        if (win.visibility === Window.Minimized || !win.visible) win.showNormal()
        if (win.visibility === Window.Windowed && win.width < 1500) { autoMaximized = true; win.showMaximized() }
        win.raise()
    }
    onSideShownChanged: {
        if (sideShown) makeRoom()
        else if (autoMaximized) {
            autoMaximized = false
            if (win.visibility === Window.Maximized) win.showNormal()
        }
    }
    onViewer3dOpenChanged: if (viewer3dOpen && nexa.compact) win.enterCompact(false)

    Connections {
        target: nexa3d
        function onToast(text, isError) { toastBox.show(text, isError) }
    }
    Connections {
        target: nexaCode
        function onToast(text, isError) { toastBox.show(text, isError) }
        function onPanelChanged() {
            if (nexaCode.panelOpen) {
                if (nexa.compact) win.enterCompact(false)
                if (win.visibility === Window.Minimized || !win.visible) win.showNormal()
            }
        }
    }
    Connections {
        target: nexa
        function onCommandNavigation(action, panel) {
            if (action === "compact") { win.enterCompact(panel === "on"); return }
            var opened = action === "open"
            if (panel === "settings") { if (opened) settingsPopup.open(); else settingsPopup.close() }
            else if (panel === "gestures") gesturePanel.visible = opened
            else if (panel === "history") {
                win.historyOpen = opened
                win.historyMode = opened ? 2 : 1
            } else if (panel === "build" || panel === "media") {
                win.pendingProductPanel = opened ? panel : ""
                if (viewer3d.item) {
                    viewer3d.item.commandProductPanel(action, panel)
                    win.pendingProductPanel = ""
                }
            }
        }
        function onToast(text, isError) { toastBox.show(text, isError) }
        // Vỗ tay đánh thức sau lúc vắng: đưa NEXA lên trước để chào anh.
        function onRaiseWindow() {
            if (win.visibility === Window.Minimized || !win.visible) win.showNormal()
            win.raise()
            win.requestActivate()
        }
    }
    Component.onCompleted: {
        if (nexa.smokeOpen === "settings") settingsPopup.open()
        else if (nexa.smokeOpen === "gestures") gesturePanel.visible = true
        else if (nexa.smokeOpen === "3d") nexa3d.workspace = true
        else if (nexa.smokeOpen === "edu") nexaEdu.open = true
        else if (nexa.smokeOpen === "code") nexaCode.openPanel()
    }

    function enterCompact(on) {
        if (on) {
            savedGeometry = { x: win.x, y: win.y, w: win.width, h: win.height }
            nexa.compact = true
            win.width = 230; win.height = 230
            win.x = Screen.desktopAvailableWidth - 250 + Screen.virtualX
            win.y = Screen.desktopAvailableHeight - 260 + Screen.virtualY
        } else {
            nexa.compact = false
            if (savedGeometry) { win.x = savedGeometry.x; win.y = savedGeometry.y; win.width = savedGeometry.w; win.height = savedGeometry.h }
        }
    }

    // ---------- thành phần tái sử dụng ----------
    // Icon: Segoe Fluent Icons (Windows 11), dự phòng Segoe MDL2 Assets (Windows 10) — cùng mã glyph.
    readonly property string iconFont: Qt.fontFamilies().indexOf("Segoe Fluent Icons") >= 0 ? "Segoe Fluent Icons" : "Segoe MDL2 Assets"
    function glyph(code) { return String.fromCharCode(code) }
    // Màu chủ đạo theo trạng thái (Theme.js) — trùng màu quả cầu: nghe cyan · suy nghĩ tím · nói vàng cam…
    property color stateAccent: Theme.stateColor(nexa.state)
    Behavior on stateAccent { ColorAnimation { duration: 450 } }
    readonly property bool busy: nexa.state === "THINKING" || nexa.state === "EXECUTING" || nexa.state === "CONFIRMING"
    readonly property string lastUserText: {
        var tl = nexa.timeline
        for (var i = tl.length - 1; i >= 0; i--)
            if (tl[i].kind !== "task" && tl[i].role === "user") return tl[i].text || ""
        return ""
    }
    readonly property string lastAssistantText: {
        var tl = nexa.timeline
        for (var i = tl.length - 1; i >= 0; i--)
            if (tl[i].kind !== "task" && tl[i].role === "assistant") return tl[i].text || ""
        return ""
    }
    // bước đang chạy gần nhất (hiện thành một dòng nhỏ dưới quả cầu)
    readonly property var liveTask: {
        var tl = nexa.timeline
        for (var i = tl.length - 1; i >= 0; i--)
            if (tl[i].kind === "task")
                return (tl[i].status === "running" || tl[i].status === "queued" || tl[i].status === "confirming") ? tl[i] : null
        return null
    }
    // ngăn kéo hội thoại ở mép phải (đóng mặc định: màn hình chính chỉ có quả cầu + phụ đề)
    property bool historyOpen: false
    // 0: normal, 1: collapsed, 2: expanded. Empty history stays unobtrusive by default.
    property int historyMode: 0
    readonly property bool historyCompact: historyMode === 1 || (nexa.timeline.length === 0 && historyMode !== 2)
    function toggleHistory() {
        if (!sideShown) { historyMode = historyCompact ? 2 : 1; return }
        historyOpen = !historyOpen
        if (historyOpen) Qt.callLater(function() { input.forceActiveFocus() })
    }
    Shortcut { sequence: "Ctrl+K"; enabled: !nexa.compact
        onActivated: { if (win.sideShown) { win.historyOpen = true; Qt.callLater(function() { input.forceActiveFocus() }) }
                       else commandInput.field.forceActiveFocus() } }
    Shortcut { sequence: "Ctrl+H"; enabled: !nexa.compact; onActivated: win.toggleHistory() }
    Shortcut { sequence: "Esc"; enabled: win.historyOpen && !win.logDocked && !nexa.compact; onActivated: win.historyOpen = false }
    function taskColor(st) {
        return st === "done" ? Theme.success : (st === "running" || st === "queued") ? win.ice
             : st === "confirming" ? Theme.amber : st === "auto_approved" ? Theme.silver : st === "cancelled" ? Theme.textMuted : Theme.danger
    }
    function taskGlyph(st) {
        return st === "done" ? 0xE73E : st === "confirming" ? 0xE7BA : st === "auto_approved" ? 0xE785 : 0xE711
    }

    component NButton: Button {
        id: nb
        property color tint: win.cyan
        property bool danger: false
        font.pixelSize: 13
        leftPadding: 14; rightPadding: 14; topPadding: 7; bottomPadding: 7
        contentItem: Text { text: nb.text; font: nb.font; color: nb.enabled ? "white" : Theme.textMuted
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
        background: Rectangle {
            radius: 8
            color: nb.danger ? (nb.down ? "#9f1239" : "#be123c") : (nb.down ? Qt.darker(nb.tint, 2.2) : (nb.hovered ? Theme.surfaceRaised : Theme.surfaceRaised))
            border.color: nb.danger ? Theme.danger : Qt.rgba(nb.tint.r, nb.tint.g, nb.tint.b, nb.hovered ? 0.9 : 0.45)
            border.width: 1
        }
    }
    component NTip: ToolTip {
        id: tip
        delay: 300
        contentItem: Text { text: tip.text; color: "white"; font.pixelSize: 12 }
        background: Rectangle { radius: 2; color: Theme.surfaceDeep; border.color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.35) }
    }
    component Chip: Rectangle {
        id: chip
        property string label: ""
        property string value: ""
        property int level: 0     // 0 tắt, 1 tốt, 2 cảnh báo, 3 lỗi
        // implicit* (không phải width/height): RowLayout của thanh tiêu đề xếp theo implicit size
        radius: 3; implicitHeight: 32
        implicitWidth: chipRow.implicitWidth + 20
        color: Theme.surface
        border.color: level === 1 ? Theme.success : level === 2 ? "#b7791f" : level === 3 ? "#be123c" : Theme.border
        Row {
            id: chipRow; anchors.centerIn: parent; spacing: 6
            Rectangle { width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                        color: chip.level === 1 ? Theme.success : chip.level === 2 ? Theme.amber : chip.level === 3 ? Theme.danger : Theme.textMuted }
            Text { text: chip.label; color: win.textDim; font.pixelSize: 12 }
            Text { text: chip.value; color: "white"; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight
                   width: Math.min(implicitWidth, win.narrow ? 90 : 150) }
        }
    }
    // Icon trạng thái tròn ở thanh tiêu đề: màu = mức (tốt / cảnh báo / lỗi), rê chuột xem chi tiết.
    component StatusIcon: Rectangle {
        id: si
        property int glyphCode: 0
        property string label: ""
        property string value: ""
        property int level: 0     // 0 tắt, 1 tốt, 2 cảnh báo, 3 lỗi
        signal clicked()
        readonly property color levelColor: level === 1 ? Theme.success : level === 2 ? Theme.amber : level === 3 ? Theme.danger : Theme.textMuted
        width: 28; height: 28; radius: 7
        color: siMouse.containsMouse ? Theme.surfaceRaised : Qt.rgba(levelColor.r, levelColor.g, levelColor.b, level === 0 ? 0 : 0.08)
        border.width: 1
        border.color: Qt.rgba(levelColor.r, levelColor.g, levelColor.b, level === 0 ? 0.25 : 0.55)
        Text { anchors.centerIn: parent; text: win.glyph(si.glyphCode); font.family: win.iconFont; font.pixelSize: 15
               color: si.level === 0 ? Theme.textMuted : si.level === 1 ? Theme.textPrimary : si.levelColor }
        Rectangle { visible: si.level >= 2; width: 10; height: 10; radius: 5; color: si.levelColor
                    border.color: Theme.bg; border.width: 2
                    anchors.right: parent.right; anchors.top: parent.top; anchors.rightMargin: -2; anchors.topMargin: -2 }
        MouseArea { id: siMouse; anchors.fill: parent; hoverEnabled: true; onClicked: si.clicked() }
        NTip { visible: siMouse.containsMouse; text: si.label + ": " + si.value }
    }
    component HeaderButton: Rectangle {
        id: hb
        property int glyphCode: 0
        property string tip: ""
        property color hoverTint: win.cyan
        signal clicked()
        width: 34; height: 34; radius: 8
        color: hbMouse.pressed ? Theme.surfaceDeep : hbMouse.containsMouse ? Theme.surfaceRaised : "transparent"
        border.width: 1
        border.color: hbMouse.containsMouse ? Qt.rgba(hoverTint.r, hoverTint.g, hoverTint.b, 0.7) : Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2)
        Text { anchors.centerIn: parent; text: win.glyph(hb.glyphCode); font.family: win.iconFont; font.pixelSize: 15
               color: hbMouse.containsMouse ? hb.hoverTint : Theme.textSecondary }
        MouseArea { id: hbMouse; anchors.fill: parent; hoverEnabled: true; onClicked: hb.clicked() }
        NTip { visible: hbMouse.containsMouse; text: hb.tip }
    }
    // Nút tròn trên dock: icon + chú thích nhỏ; primary = nền màu trạng thái; active = đang bật.
    component DockButton: Item {
        id: db
        property int glyphCode: 0
        property string caption: ""
        property string tip: caption
        property color tint: win.cyan
        property bool active: false
        property bool primary: false
        property bool pulsing: false
        property bool showCaption: true
        property real size: 42
        signal clicked()
        opacity: enabled ? 1 : 0.4
        implicitWidth: Math.max(size, showCaption ? capText.implicitWidth : 0) + 8
        implicitHeight: size + (showCaption ? capText.implicitHeight + 3 : 0)
        width: implicitWidth; height: implicitHeight
        Rectangle {   // vòng lan tỏa khi đang nghe
            anchors.centerIn: disc
            width: db.size; height: db.size; radius: db.size / 2
            color: "transparent"; border.color: db.tint; border.width: 2
            visible: db.pulsing
            NumberAnimation on scale { running: db.pulsing; loops: Animation.Infinite; from: 1; to: 1.45; duration: 1100; easing.type: Easing.OutCubic }
            NumberAnimation on opacity { running: db.pulsing; loops: Animation.Infinite; from: 0.8; to: 0; duration: 1100; easing.type: Easing.OutCubic }
        }
        Rectangle {
            id: disc
            width: db.size; height: db.size; radius: db.size / 2
            anchors.horizontalCenter: parent.horizontalCenter
            color: db.primary ? Qt.rgba(db.tint.r, db.tint.g, db.tint.b, dbMouse.pressed ? 0.55 : dbMouse.containsMouse ? 0.42 : 0.3)
                 : db.active ? Qt.rgba(db.tint.r, db.tint.g, db.tint.b, 0.28)
                 : dbMouse.pressed ? Theme.surfaceDeep : dbMouse.containsMouse ? Theme.surfaceRaised : Theme.surfaceRaised
            border.width: db.primary || db.active ? 1.5 : 1
            border.color: Qt.rgba(db.tint.r, db.tint.g, db.tint.b, db.primary || db.active || dbMouse.containsMouse ? 0.95 : 0.4)
            scale: dbMouse.pressed ? 0.94 : 1
            Behavior on scale { NumberAnimation { duration: 90 } }
            Text { anchors.centerIn: parent; text: win.glyph(db.glyphCode); font.family: win.iconFont
                   font.pixelSize: Math.round(db.size * 0.42); color: db.primary || db.active ? "white" : Theme.textPrimary }
        }
        Text { id: capText; visible: db.showCaption; anchors.top: disc.bottom; anchors.topMargin: 3
               anchors.horizontalCenter: parent.horizontalCenter; text: db.caption; font.pixelSize: 11
               color: db.active || db.primary ? "white" : win.textDim }
        MouseArea { id: dbMouse; anchors.fill: parent; hoverEnabled: true; enabled: db.enabled; onClicked: db.clicked() }
        NTip { visible: dbMouse.containsMouse && db.tip.length > 0; text: db.tip }
    }
    // Vạch đo mảnh ở góc sân khấu: nhãn · giá trị, 12 đoạn tô theo mức tải
    component Meter: Item {
        id: mt
        property string label: ""
        property real v: -1                 // 0..1; âm = không có số liệu
        property string valueText: "—"
        implicitWidth: 132; implicitHeight: 30
        readonly property int segs: 12
        readonly property color col: win.tacLoad(v)
        property real shownV: v
        Behavior on shownV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
        Text { anchors.left: parent.left; anchors.top: parent.top; text: mt.label; color: win.iceDim
               font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 1 }
        Text { anchors.right: parent.right; anchors.top: parent.top; text: mt.valueText; color: Theme.textPrimary
               font.family: win.monoFont; font.pixelSize: 12 }
        Row {
            anchors.left: parent.left; anchors.bottom: parent.bottom
            spacing: 3
            Repeater {
                model: mt.segs
                Rectangle {
                    required property int index
                    width: (mt.width - (mt.segs - 1) * 3) / mt.segs; height: 5
                    color: index < Math.round(Math.max(0, mt.shownV) * mt.segs) ? mt.col : Theme.surfaceDeep
                }
            }
        }
    }

    // ---------- bộ kiểu chiến thuật (Halo / Mass Effect): khung vát góc, băng + cam ----------
    readonly property color ice: Theme.accent
    readonly property color amber: Theme.amber
    readonly property color hazard: Theme.danger
    readonly property color iceDim: Theme.textMuted
    readonly property string tacFont: Theme.font
    readonly property string monoFont: "Consolas"
    function tacLoad(v) { return v < 0 ? Theme.borderStrong : v >= 0.85 ? win.hazard : v >= 0.6 ? win.amber : win.ice }
    function pct(v) { return v === null || v === undefined ? "—" : Math.round(v) + "%" }
    function ms(v) { return !v ? "—" : v < 1000 ? Math.round(v) + " ms" : (v / 1000).toFixed(1) + " s" }
    // đồng hồ nhiệm vụ: thời gian từ lúc mở NEXA
    readonly property real bootMs: Date.now()
    property string missionClock: "T+00:00:00"
    property string wallClock: ""
    Timer {
        interval: 1000; repeat: true; triggeredOnStart: true
        running: win.visible && !nexa.compact
        onTriggered: {
            var s = Math.floor((Date.now() - win.bootMs) / 1000)
            function two(n) { return n < 10 ? "0" + n : "" + n }
            win.missionClock = "T+" + two(Math.floor(s / 3600)) + ":" + two(Math.floor(s / 60) % 60) + ":" + two(s % 60)
            win.wallClock = Qt.formatDateTime(new Date(), "dd.MM.yyyy  HH:mm")
        }
    }

    // Khung vát hai góc (trên trái, dưới phải)
    component Chamfer: TacFrame {}
    // Bảng chiến thuật: khung vát + nẹp sáng ở góc + tab tiêu đề "01 SYS · HỆ THỐNG"
    component TacPanel: TacCard {}
    // Nút lệnh vát góc: icon + chữ in hoa; primary = nền màu; active = đang bật (vạch sáng dưới)
    component TacButton: Item {
        id: tb
        property int glyphCode: 0
        property string caption: ""
        property string tip: caption
        property color tint: win.ice
        property bool active: false
        property bool primary: false
        property bool pulsing: false
        property bool showCaption: true
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: caption || tip
        Accessible.onPressAction: if (enabled) clicked()
        Keys.onSpacePressed: if (enabled) clicked()
        Keys.onReturnPressed: if (enabled) clicked()
        signal clicked()
        opacity: enabled ? 1 : 0.35
        implicitHeight: 30
        implicitWidth: tbRow.implicitWidth + (showCaption ? 20 : 14)
        readonly property bool hot: tbMouse.containsMouse
        Chamfer {   // viền lan tỏa khi đang nghe
            anchors.fill: parent; anchors.margins: -4; cut: 11
            stroke: tb.tint; strokeW: 1.5
            visible: tb.pulsing
            SequentialAnimation on opacity {
                running: tb.pulsing && tb.visible && nexa.effects !== "minimal"; loops: Animation.Infinite
                NumberAnimation { from: 0.9; to: 0.1; duration: 900; easing.type: Easing.OutCubic }
            }
        }
        Chamfer {
            anchors.fill: parent; cut: 9
            fill: tb.primary ? Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, tbMouse.pressed ? 0.5 : tb.hot ? 0.34 : 0.22)
                 : tb.active ? Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, 0.16)
                 : tbMouse.pressed ? Theme.surfaceDeep : tb.hot ? Theme.surfaceRaised : Theme.surface
            stroke: tb.active || tb.hot || tb.activeFocus ? tb.tint : Theme.border
        }
        Rectangle { visible: tb.active; x: 12; width: tb.width - 30; height: 2
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 4; color: tb.tint; opacity: 0.9 }
        Row {
            id: tbRow
            anchors.centerIn: parent
            spacing: 8
            scale: tbMouse.pressed ? 0.95 : 1
            Text { text: win.glyph(tb.glyphCode); font.family: win.iconFont; font.pixelSize: 15
                   color: tb.primary || tb.active ? "white" : (tb.hot ? tb.tint : Theme.textSecondary)
                   anchors.verticalCenter: parent.verticalCenter }
            Text { visible: tb.showCaption; text: tb.caption; font.family: win.tacFont; font.pixelSize: 10
                   font.letterSpacing: 0.4; color: tb.primary || tb.active ? "white" : Theme.textSecondary
                   anchors.verticalCenter: parent.verticalCenter }
        }
        MouseArea { id: tbMouse; anchors.fill: parent; hoverEnabled: true; enabled: tb.enabled; onClicked: tb.clicked() }
        NTip { visible: tbMouse.containsMouse && tb.tip.length > 0; text: tb.tip }
    }
    // Khối số liệu ở bảng SYS: nhãn · số lớn · đồ thị nhỏ · thanh 20 đoạn · vạch chia
    component StatBlock: Item {
        id: sb
        property string label: ""
        property string sub: ""
        property real v: -1                 // 0..1; âm = không có số liệu
        property string big: "—"
        property string unit: ""
        property var hist: []
        implicitHeight: 78
        readonly property color col: win.tacLoad(v)
        property real shownV: v
        Behavior on shownV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
        Text { text: sb.label; color: win.iceDim; font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 1 }
        Text { anchors.right: parent.right; text: sb.sub; color: Theme.textMuted; font.family: win.monoFont; font.pixelSize: 10 }
        Row {
            y: 14; spacing: 3
            Text { id: sbBig; text: sb.big; color: sb.v < 0 ? Theme.textMuted : Theme.textPrimary; font.family: win.tacFont; font.pixelSize: 26; font.weight: Font.Light }
            Text { text: sb.unit; color: sb.col; font.family: win.tacFont; font.pixelSize: 13
                   anchors.baseline: sbBig.baseline }
        }
        Canvas {
            id: spark
            x: 92; y: 18; width: sb.width - 92; height: 30
            property var h: sb.hist
            property color c: sb.col
            onHChanged: requestPaint(); onCChanged: requestPaint(); onWidthChanged: requestPaint()
            renderStrategy: Canvas.Cooperative
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                ctx.strokeStyle = Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.08); ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(0, height - 0.5); ctx.lineTo(width, height - 0.5); ctx.stroke()
                var n = h.length
                if (n < 2) return
                var step = width / 39
                ctx.beginPath()
                for (var i = 0; i < n; i++) {
                    var px = width - (n - 1 - i) * step, py = height - 2 - Math.max(0, Math.min(1, h[i])) * (height - 4)
                    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
                }
                ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.9); ctx.lineWidth = 1.4; ctx.stroke()
                ctx.lineTo(width, height); ctx.lineTo(width - (n - 1) * step, height); ctx.closePath()
                ctx.fillStyle = Qt.rgba(c.r, c.g, c.b, 0.12); ctx.fill()
            }
        }
        Row {
            y: 56; spacing: 2
            Repeater {
                model: 20
                Rectangle {
                    required property int index
                    width: (sb.width - 19 * 2) / 20; height: 5
                    color: index < Math.round(Math.max(0, sb.shownV) * 20) ? sb.col : Theme.surfaceDeep
                }
            }
        }
        Repeater {   // vạch chia 0 · 25 · 50 · 75 · 100
            model: 11
            Rectangle {
                required property int index
                x: Math.round(index * (sb.width - 1) / 10); y: 64
                width: 1; height: index % 5 === 0 ? 6 : 3
                color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, index % 5 === 0 ? 0.4 : 0.18)
            }
        }
    }

    // Đồng hồ mức dọc cạnh lõi radar
    component LevelGauge: Column {
        id: lg
        property string k: ""
        property real v: 0
        property color c: win.ice
        visible: !stage.tight && nexa.state !== "STANDBY"
        spacing: 4
        anchors.verticalCenter: parent.verticalCenter
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: lg.k; color: win.iceDim
               font.family: win.tacFont; font.pixelSize: 10; font.letterSpacing: 2 }
        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 6; height: 96
            Rectangle { anchors.fill: parent; color: Theme.surfaceDeep; border.color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2) }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width
                        height: parent.height * Math.max(0, Math.min(1, lg.v)); color: lg.c
                        Behavior on height { NumberAnimation { duration: 90 } } }
        }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: Math.round(lg.v * 100)
               color: Theme.textSecondary; font.family: win.monoFont; font.pixelSize: 10 }
    }
    component DarkMenuItem: MenuItem {
        id: dmi
        implicitWidth: 230
        contentItem: Text { text: dmi.text; color: dmi.enabled ? "white" : Theme.textMuted; font.pixelSize: 13
                            leftPadding: 6; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 2; color: dmi.highlighted ? Theme.surfaceRaised : "transparent" }
    }

    // ---------- nền: lưới kỹ thuật mờ + tối dần ra mép ----------
    Canvas {
        anchors.fill: parent
        visible: !nexa.compact
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        renderStrategy: Canvas.Cooperative
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var g = ctx.createLinearGradient(0, 0, 0, height)
            g.addColorStop(0, Theme.bg); g.addColorStop(0.6, Theme.bg); g.addColorStop(1, Theme.bg)
            ctx.fillStyle = g; ctx.fillRect(0, 0, width, height)
            ctx.strokeStyle="rgba(66,166,204,0.035)"; ctx.lineWidth=1;
            ctx.beginPath();
            for(var gx=0;gx<width;gx+=32) { ctx.moveTo(gx,0); ctx.lineTo(gx,height); }
            for(var gy=0;gy<height;gy+=32) { ctx.moveTo(0,gy); ctx.lineTo(width,gy); }
            ctx.stroke();
            var halo = ctx.createRadialGradient(width * 0.48, height * 0.42, 0, width * 0.48, height * 0.42, width * 0.6)
            halo.addColorStop(0, "rgba(88,155,158,0.065)"); halo.addColorStop(1, "rgba(7,11,16,0)")
            ctx.fillStyle = halo; ctx.fillRect(0, 0, width, height)
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
               style: Text.Outline; styleColor: Theme.bg }
        Rectangle {
            anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 6
            width: 26; height: 26; radius: 4; color: "#3a0c0c"; border.color: win.hazard
            Rectangle { anchors.centerIn: parent; width: 9; height: 9; color: win.hazard }
            MouseArea { anchors.fill: parent; onClicked: nexa.stop() }
        }
    }

    // ---------- giao diện đầy đủ ----------
    ColumnLayout {
        id: fullLayout
        anchors.fill: parent
        anchors.margins: 8
        anchors.topMargin: 6
        spacing: 6
        visible: !nexa.compact

        // Identity and ownership remain readable even in the minimum-width window.
        RowLayout {
            id: identityHeader
            objectName: "identityHeader"
            Layout.preferredHeight: win.width >= 1200 ? 58 : 66; Layout.maximumHeight: Layout.preferredHeight; Layout.minimumHeight: Layout.preferredHeight
            Layout.fillWidth: true; spacing: win.width < 760 ? 8 : 14
            TacticalCore { visible: win.width >= 1200; Layout.preferredWidth: 38; Layout.preferredHeight: 38; effects: "minimal"; appState: nexa.state }
            ColumnLayout {
                spacing: 3
                Text { text: "N.E.X.A."; color: Theme.textPrimary; font.pixelSize: 21; font.weight: Font.DemiBold }
                Text { text: "v" + nexa.appVersion + "  /  PERSONAL AI"; color: Theme.accent; font.family: Theme.mono; font.pixelSize: 9 }
                Text { text: nexa.stateLabel; color: win.stateAccent; font.pixelSize: 10 }
            }
            Rectangle { width: 1; Layout.fillHeight: true; color: Theme.border }
            Item { id: headerNavSlot; visible: win.width >= 1200; Layout.preferredWidth: win.width >= 1500 ? 470 : 365; Layout.preferredHeight: 34 }
            ColumnLayout {
                objectName: "nxsMediaIdentity"
                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 3
                Text { Layout.fillWidth: true; text: "NXS MEDIA"; color: Theme.accent; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 2 }
                Text { Layout.fillWidth: true; text: "CEO & Founder Nguyễn Xuân Sơn"; color: Theme.textPrimary; font.pixelSize: 10; wrapMode: Text.Wrap }
                Text { Layout.fillWidth: true; text: "0963750357  ·  nson992008@gmail.com"; color: Theme.textSecondary; font.family: Theme.mono; font.pixelSize: 10; wrapMode: Text.Wrap }
            }
            ColumnLayout {
                visible: win.width >= 1500; spacing: 3
                Text { text: win.wallClock; color: Theme.textSecondary; font.family: Theme.mono; font.pixelSize: 11 }
                Row {
                    objectName: "statusIcons"; spacing: 5
                    StatusIcon { glyphCode: 0xE720; label: "Microphone"; value: nexa.status.mic && nexa.status.mic.ok ? "Bật" : "Chưa sẵn sàng"; level: nexa.status.mic && nexa.status.mic.ok ? 1 : 0 }
                    StatusIcon { glyphCode: 0xE99A; label: "Gemini"; value: nexa.status.ai && nexa.status.ai.ok ? "Sẵn sàng" : "Chưa sẵn sàng"; level: nexa.status.ai && nexa.status.ai.ok ? 1 : 0 }
                    StatusIcon { glyphCode: 0xE722; label: "Camera"; value: nexa.cameraOn ? "Bật" : "Tắt"; level: nexa.cameraOn ? 1 : 0; onClicked: gesturePanel.visible = !gesturePanel.visible }
                    StatusIcon { glyphCode: 0xE72E; label: "Quyền"; value: nexa.status.autonomy === "full" ? "Toàn quyền" : "Tiêu chuẩn"; level: nexa.status.autonomy === "full" ? 2 : 1 }
                }
            }
            HeaderButton { glyphCode: 0xE713; tip: "Cài đặt"; onClicked: settingsPopup.open() }
            HeaderButton { glyphCode: 0xE73F; tip: "Thu gọn NEXA"; onClicked: win.enterCompact(true) }
            HeaderButton { glyphCode: 0xE7E8; tip: "Thoát NEXA"; hoverTint: win.hazard; onClicked: nexa.quit() }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }

        RowLayout {
            visible: (win.width < 1200 || win.sideShown) && !nexa.compact
            Layout.fillWidth: true; spacing: 8
            GenerationProgress { Layout.fillWidth: true; compact: true; title: "MÔ HÌNH 3D"; job: nexa3d.activeJob
                onOpenRequested: nexa3d.workspace = true }
            GenerationProgress { Layout.fillWidth: true; compact: true; title: "CODE"; job: nexaCode.job
                onOpenRequested: nexaCode.openPanel() }
        }

        Item { id: narrowNavSlot; visible: win.width < 1200; Layout.fillWidth: true; Layout.preferredHeight: 34 }
        RowLayout {
            parent: win.width >= 1200 ? headerNavSlot : narrowNavSlot
            width: parent.width; height: 34
            Layout.fillWidth: true; spacing: 5
            TacButton { caption: "TRUNG TÂM"; glyphCode: 0xE80F; active: !win.sideShown && !nexa3d.workspace
                onClicked: { if (nexaCode.panelOpen) nexaCode.closePanel(); if (win.viewer3dOpen) nexa3d.closeViewer(); nexa3d.workspace = false } }
            TacButton { caption: "3D"; glyphCode: 0xF158; showCaption: win.width >= 760; active: nexa3d.workspace || win.viewerShown
                onClicked: { if (nexaCode.panelOpen) nexaCode.closePanel(); nexa3d.workspace = true } }
            TacButton { caption: "EDU"; glyphCode: 0xE7BE; showCaption: win.width >= 760; active: nexaEdu.open
                onClicked: { if (nexaCode.panelOpen) nexaCode.closePanel(); if (nexa3d.viewerOpen) nexa3d.closeViewer(); nexa3d.workspace = false; nexaEdu.open = true } }
            TacButton { caption: "CODE"; glyphCode: 0xE943; active: win.codeShown; onClicked: nexaCode.openPanel() }
            TacButton { caption: "CỬ CHỈ"; glyphCode: 0xE815; showCaption: win.width >= 1500; active: gesturePanel.visible
                onClicked: gesturePanel.visible = !gesturePanel.visible }
            Item { Layout.fillWidth: true }
            TacButton { caption: "HỆ THỐNG"; glyphCode: 0xE9D9; showCaption: false; tip: "CPU, GPU, RAM, ổ đĩa, pin và Wi-Fi"; onClicked: systemDetails.open() }
            TacButton { caption: "API / LIB"; glyphCode: 0xE774; showCaption: false; tip: "API và thư viện phát triển"; onClicked: runtimeDetails.open() }
            Text { visible: false; text: "●  " + nexa.stateLabel.toUpperCase(); color: win.stateAccent; font.family: Theme.mono; font.pixelSize: 11 }
            TacButton { caption: "HỘI THOẠI"; glyphCode: 0xE8BD; showCaption: false; onClicked: win.toggleHistory() }
        }

        // Nội dung chính: SYS | radar | LOG
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Rectangle {
                objectName: "workspaceRail"
                Layout.fillHeight: true; Layout.preferredWidth: 56
                visible: win.width >= 760 && (win.sideShown || win.narrow)
                radius: Theme.radius; color: Theme.surfaceDeep; border.color: Theme.border
                Column {
                    anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 10; spacing: 12
                    TacButton { implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xE80F
                        active: !win.sideShown && !nexa3d.workspace; tip: "Trung tâm NEXA"
                        onClicked: { if (nexaCode.panelOpen) nexaCode.closePanel(); if (win.viewer3dOpen) nexa3d.closeViewer(); nexa3d.workspace = false } }
                    TacButton { implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xF158
                        active: win.viewerShown || nexa3d.workspace; tip: "Không gian 3D"
                        onClicked: { if (nexaCode.panelOpen) nexaCode.closePanel(); nexa3d.workspace = true } }
                    TacButton { implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xE7BE
                        active: nexaEdu.open; tip: "Mô phỏng STEM / Phòng thí nghiệm"
                        onClicked: { if (nexaCode.panelOpen) nexaCode.closePanel(); nexaEdu.open = true } }
                    TacButton { implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xE943
                        active: win.codeShown; tip: "Không gian Code"; onClicked: nexaCode.openPanel() }
                    TacButton { implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xE8BD
                        active: win.historyOpen; tip: "Hội thoại · Ctrl+H"; onClicked: win.toggleHistory() }
                    Rectangle { width: 24; height: 1; anchors.horizontalCenter: parent.horizontalCenter; color: Theme.border }
                    TacButton { implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xE815
                        active: gesturePanel.visible; tip: "Điều khiển cử chỉ"; onClicked: gesturePanel.visible = !gesturePanel.visible }
                }
                TacButton { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 10
                    implicitWidth: 40; implicitHeight: 40; showCaption: false; glyphCode: 0xE713; tip: "Cài đặt"; onClicked: settingsPopup.open() }
            }

            ReferenceSystemRail {
                id: sysPanel; objectName: "statsRing"
                Layout.fillHeight: true; Layout.preferredWidth: Math.min(270, win.width * 0.18); Layout.minimumWidth: Layout.preferredWidth; Layout.maximumWidth: Layout.preferredWidth
                visible: win.sysDocked
                st: nexa.sysStats; status: nexa.status; foreground: nexa.foreground; paused: nexa.controlPaused
            }

            // Sân khấu: lõi radar ở giữa, trạng thái + phụ đề bên dưới, thanh lệnh vát góc ở đáy
            Item {
                id: stage
                objectName: "stage"
                // có bảng bên phải (3D / code): sân khấu thu về 0, NEXA thành radar nổi ở góc (copilot) — bảng chiếm hết bề ngang.
                // Sân khấu vẫn giữ để ngăn kéo nhật ký trượt ra đè lên bảng (z cao hơn các bảng).
                Layout.fillWidth: !win.sideShown
                Layout.preferredWidth: win.sideShown ? 0 : -1
                Layout.maximumWidth: win.sideShown ? 0 : Number.POSITIVE_INFINITY
                Layout.rightMargin: win.sideShown ? -14 : 0
                Layout.fillHeight: true
                z: 6 // conversation floats over the neighboring operations cards
                clip: false
                readonly property bool tight: width < 710
                readonly property real drawerW: win.sideShown ? 400 : Math.min(width - 24, 400)

                TacFrame { anchors.fill: parent; visible: !win.sideShown; fill: Theme.panelGlass; stroke: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.34) }
                Rectangle { visible: !win.sideShown; anchors.fill: parent; color: "transparent"
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.035) }
                        GradientStop { position: 0.48; color: "transparent" }
                        GradientStop { position: 1.0; color: Qt.rgba(0.02, 0.04, 0.08, 0.28) }
                    }
                }
                Rectangle { visible: !win.sideShown; x: 16; y: 0; width: 112; height: 2; color: win.stateAccent; opacity: 0.82 }
                Row { visible: !win.sideShown && win.width >= 1000
                    anchors.right: parent.right; anchors.top: parent.top; anchors.rightMargin: 18; anchors.topMargin: 14; spacing: 8
                    Rectangle { width: 6; height: 6; radius: 3; color: win.stateAccent; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "COMMAND CENTER"; color: Theme.textSecondary; font.family: Theme.mono; font.pixelSize: 9; font.letterSpacing: 1.6 }
                }
                Column {
                    visible: win.width >= 1200 && !win.sideShown
                    x: 18; y: 100; width: 112; spacing: 15; z: 2
                    Repeater {
                        model: [
                            {name:"AI MODEL",value:(nexa.status.ai && nexa.status.ai.model)||"Chưa có dữ liệu"},
                            {name:"VOICE ENGINE",value:(nexa.status.tts && nexa.status.tts.backend)||"Đang chờ"},
                            {name:"MEMORY",value:win.pct(nexa.sysStats.ram)},
                            {name:"STORAGE",value:win.pct(nexa.sysStats.disk)},
                            {name:"SESSION",value:win.missionClock}]
                        Column { required property var modelData; width: 112; spacing: 4
                            Text { text: "◈  " + modelData.name; color: Theme.textSecondary; font.family: Theme.mono; font.pixelSize: 9; font.letterSpacing: 1 }
                            Text { width: 104; x: 8; text: modelData.value; color: Theme.accent; font.family: Theme.mono; font.pixelSize: 9; elide: Text.ElideRight; textFormat: Text.PlainText }
                        }
                    }
                }
                Column {
                    visible: win.width >= 1200 && !win.sideShown
                    anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.leftMargin: 12; anchors.bottomMargin: 16; spacing: 3
                    TacticalCore { width: 96; height: 96; effects: "minimal"; appState: nexa.state }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "N E X A"; color: Theme.accent; font.pixelSize: 9; font.letterSpacing: 2 }
                }
                // Thông số rút gọn ở đỉnh sân khấu khi bảng SYS ẩn (màn hẹp / có bảng bên phải)
                Item {
                    id: statsStrip
                    objectName: "statsStrip"
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 4
                    height: 34
                    visible: !sysPanel.visible && sysPanel.hasData && !win.sideShown
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
                    visible: !win.sideShown
                    anchors.fill: parent
                    anchors.topMargin: statsStrip.visible ? 40 : 4
                    spacing: 4

                    Column {
                        visible: win.height >= 740
                        Layout.fillWidth: true; Layout.leftMargin: 14; Layout.topMargin: 8; spacing: 3
                        Text { width: parent.width; text: "NEXA / SYSTEM INTELLIGENCE"; color: Theme.textMuted
                            font.pixelSize: 9; horizontalAlignment: Text.AlignLeft }
                        Text { width: parent.width; text: "LIVING MIRROR CORE"
                            color: Theme.textPrimary; font.pixelSize: 17; font.weight: Font.DemiBold; font.letterSpacing: 2
                            horizontalAlignment: Text.AlignLeft }
                    }

                    Item {
                        id: coreArea
                        objectName: "orbArea"
                        Layout.fillWidth: true; Layout.fillHeight: true
                readonly property real coreSize: Math.max(0, Math.min(width * 0.94, height - 8, 620))
                        TacticalCore {
                            id: mainOrb
                            objectName: "sentinelCore"
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: (parent.height - height) / 2
                            width: coreArea.coreSize; height: width
                            appState: nexa.state; micLevel: nexa.micLevel; outLevel: nexa.outLevel; outBands: nexa.outBands; effects: nexa.effects
                        }
                        MouseArea { anchors.fill: mainOrb; onDoubleClicked: nexa.wake() }
                        // đồng hồ mức vào (mic) / ra (giọng NEXA) hai bên lõi
                        LevelGauge { k: "MIC"; v: nexa.micLevel; c: win.ice
                                     x: win.width >= 1200 ? Math.max(140, mainOrb.x + 8) : Math.max(4, mainOrb.x - 56) }
                        LevelGauge { k: "OUT"; v: nexa.outLevel; c: win.amber
                                     x: Math.min(coreArea.width - 26, mainOrb.x + mainOrb.width + 32) }
                        Text {
                            visible: nexa.showFps
                            anchors.left: parent.left; anchors.top: parent.top; anchors.leftMargin: 8
                            text: "FPS " + mainOrb.measuredFps.toFixed(0); color: Theme.borderStrong; font.family: win.monoFont; font.pixelSize: 10
                        }
                    }

                    // Trạng thái: ── ▸ ĐANG NGHE ◂ ── với vạch mảnh hai bên
                    Item {
                        id: statePill
                        objectName: "statePill"
                        visible: win.width < 1200
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        readonly property real maxW: stage.width - 40
                        Row {
                            id: pillRow
                            anchors.centerIn: parent
                            spacing: 10
                            Text { text: "▸"; color: win.stateAccent; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter
                                   SequentialAnimation on opacity {
                                       running: statePill.visible && nexa.effects !== "minimal" && nexa.state !== "STANDBY" && nexa.state !== "INITIALIZING"; loops: Animation.Infinite
                                       NumberAnimation { to: 0.2; duration: 600; easing.type: Easing.InOutSine }
                                       NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
                                   } }
                            Text { id: pillLabel; objectName: "stateLabel"; text: nexa.stateLabel.toUpperCase(); color: win.stateAccent
                                   font.family: win.tacFont; font.pixelSize: 15; font.letterSpacing: 2.5
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
                            width: Math.max(0, Math.min(100, pillRow.x - 30)); height: 1
                            gradient: Gradient { orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: "transparent" }
                                GradientStop { position: 1; color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.7) } }
                        }
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: pillRow.right; anchors.leftMargin: 14
                            width: Math.max(0, Math.min(100, pillRow.x - 30)); height: 1
                            gradient: Gradient { orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.7) }
                                GradientStop { position: 1; color: "transparent" } }
                        }
                    }

                    // Phụ đề: câu anh vừa nói (nghiêng, mờ) và câu NEXA trả lời (gõ dần), tự mờ sau ít giây
                    Item {
                        id: subs
                        objectName: "subtitles"
                        visible: false
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(54, subCol.implicitHeight)
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
                                                                      running: subs.visible && nexa.effects !== "minimal" && win.liveTask !== null } }
                                Text { text: win.liveTask ? ((win.liveTask.title || "") + (win.liveTask.text ? " · " + win.liveTask.text : "")).toUpperCase() : ""
                                       color: win.amber; font.family: win.tacFont; font.pixelSize: 12; font.letterSpacing: 2; elide: Text.ElideRight
                                       width: Math.min(implicitWidth, subCol.width - 30) }
                            }
                            Text {
                                id: userSub
                                width: parent.width
                                visible: text.length > 0
                                text: subs.userLine.length > 0 ? "“" + subs.userLine + "”" : ""
                                color: nexa.listeningSpeech ? Theme.accent : Theme.textSecondary
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
                                color: Theme.textPrimary; font.pixelSize: stage.tight ? 17 : 20; lineHeight: 1.1
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
                            }
                            Text {
                                width: parent.width
                                visible: nexa.timeline.length === 0 && !nexa.listeningSpeech
                                text: "Nói “NEXA ơi”, hoặc nhập điều anh muốn làm."
                                color: Theme.textMuted; font.family: win.tacFont; font.pixelSize: 13; font.letterSpacing: 1.4
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }
                    }

                    Item {
                        id: historyAnchor
                        visible: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: win.historyCompact ? 42 : win.historyMode === 2 ? Math.min(320, stage.height * 0.43) : Math.max(150, Math.min(210, stage.height * 0.28))
                        Item {
                            id: historySlot; objectName: "floatingHistorySlot"
                            parent: historyAnchor
                            x: 0; y: 0
                            width: historyAnchor.width
                            height: historyAnchor.height
                            z: 12
                        }
                    }

                    Item {
                        id: commandAnchor; visible: win.width < 1200
                        Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.preferredHeight: 46
                    TacInput {
                        id: commandInput
                        parent: !win.sideShown && win.width >= 1200 ? footerInputSlot : commandAnchor
                        width: parent.width; height: 44
                        objectName: "commandInput"
                        Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                        implicitHeight: 44; cornerRadius: 22; accent: win.stateAccent; prefix: "⌁"
                        placeholderText: "NÓI VỚI NEXA   /   Nhập lệnh · Ctrl+K"
                        function submit() { if (text.trim().length) { nexa.sendText(text.trim()); text = "" } }
                        onAccepted: submit()
                        TacTool { text: "Gửi"; glyphCode: 0xE724; primary: true; enabled: commandInput.text.trim().length > 0
                            onClicked: commandInput.submit() }
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
                            Text { text: "Điều khiển đang tạm khóa"; color: win.amber; font.family: win.tacFont
                                   font.pixelSize: 12; font.letterSpacing: 2 }
                            NButton { text: "▶ Tiếp tục"; tint: Theme.success; font.pixelSize: 12; onClicked: nexa.resumeControl() }
                        }
                    }

                    // Thanh lệnh vát góc + nút DỪNG KHẨN CẤP
                    Item {
                        id: actionAnchor; visible: win.width < 1200
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: dock.implicitWidth + stopBtn.implicitWidth + 12
                        Layout.preferredHeight: 38
                    RowLayout {
                        parent: !win.sideShown && win.width >= 1200 ? footerActionsSlot : actionAnchor
                        height: 34; width: implicitWidth
                        Layout.alignment: Qt.AlignHCenter
                        Layout.bottomMargin: 4
                        spacing: stage.tight ? 8 : 12
                        Item {
                            id: dock
                            objectName: "dock"
                            implicitWidth: dockRow.implicitWidth + (stage.tight ? 12 : 20)
                            implicitHeight: dockRow.implicitHeight + 4
                            Chamfer { anchors.fill: parent; cut: 14; fill: Theme.panelGlass; stroke: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.38) }
                            Rectangle { x: 24; y: 0; width: 54; height: 2; color: win.stateAccent; opacity: 0.72 }
                            Row {
                                id: dockRow
                                anchors.centerIn: parent
                                spacing: stage.tight ? 3 : 6
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
                                TacButton { glyphCode: 0xE8F2; caption: "Tâm sự"; tint: win.purple; showCaption: !stage.tight
                                            active: nexa.status.companion === true
                                            tip: active ? "Thoát chế độ tâm sự" : "Trò chuyện liên tục với NEXA"
                                            onClicked: nexa.sendText(active ? "thoát chế độ tâm sự" : "bật chế độ tâm sự") }
                                TacButton { glyphCode: 0xE815; caption: "Cử chỉ"; tint: win.purple; active: nexa.cameraOn; showCaption: !stage.tight
                                            tip: nexa.cameraOn ? "Tắt cử chỉ tay (tắt camera)" : "Bật cử chỉ tay (bật camera)"
                                            onClicked: nexa.toggleGestures() }
                                TacButton { glyphCode: 0xF158; caption: "3D"; active: nexa3d.workspace || win.viewer3dOpen; showCaption: !stage.tight
                                            tip: "Mô hình 3D"
                                            onClicked: nexa3d.workspace = !nexa3d.workspace }
                                TacButton { glyphCode: 0xE943; caption: "Code"; tint: win.blue; active: nexaCode.panelOpen; showCaption: !stage.tight
                                            tip: "Sinh code"
                                            onClicked: nexaCode.panelOpen ? nexaCode.closePanel() : nexaCode.openPanel() }
                                TacButton { glyphCode: 0xE8BD; caption: "Nhật ký"; active: win.historyOpen; visible: !win.logDocked; showCaption: !stage.tight
                                            tip: "Nhật ký hội thoại và ô gõ lệnh (Ctrl+H)"
                                            onClicked: win.toggleHistory() }
                                TacButton { glyphCode: 0xE711; caption: "Hủy"; tint: win.amber; visible: win.busy
                                            tip: "Hủy tác vụ đang chạy"; showCaption: false
                                            onClicked: nexa.cancelTask() }
                                TacButton { id: moreBtn; glyphCode: 0xE712; caption: ""; showCaption: false; tip: "Thêm: bảng cử chỉ, chuột bằng tay…"
                                            onClicked: moreMenu.popup(moreBtn, 0, -moreMenu.implicitHeight - 6) }
                            }
                            Menu {
                                id: moreMenu
                                padding: 6
                                background: Rectangle { implicitWidth: 240; radius: 3; color: Theme.surfaceDeep
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
                            glyphCode: 0xE71A; caption: "Dừng"; showCaption: false
                            tip: "DỪNG KHẨN CẤP (Ctrl+Alt+Esc)"
                            onClicked: nexa.stop()
                        }
                    }
                    }
                }

                // tab ở mép phải khi nhật ký thu vào (màn hẹp): số dòng + mở nhật ký
                Item {
                    id: drawerHandle
                    visible: false // floating history is always available on the home screen
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 28; height: 104
                    Chamfer { anchors.fill: parent; cut: 7; fill: handleMouse.containsMouse ? Theme.surfaceRaised : Theme.panelGlass
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
                    anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.left: parent.left
                    width: win.sideShown ? win.width : parent.width
                    z: 9
                    color: "#aa02060c"
                    opacity: win.historyOpen && win.sideShown ? 1 : 0
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: 250 } }
                    MouseArea { anchors.fill: parent; onClicked: win.historyOpen = false }
                }

                // Nhật ký: tin nhắn + bước tác vụ + ô gõ lệnh. Màn rộng: gắn cố định bên phải sân khấu (chỗ logSlot);
                // màn hẹp / có bảng bên phải: ngăn kéo trượt từ mép phải.
                TacPanel {
                    id: chatPanel
                    objectName: "historyDrawer"
                    title: win.historyCompact && !win.sideShown ? "HỘI THOẠI · " + nexa.timeline.filter(function(r){return r.kind !== "task"}).length + " TIN NHẮN" : "HỘI THOẠI / " + nexa.stateLabel.toUpperCase(); code: "◈"; accent: win.stateAccent
                    parent: win.sideShown ? stage : historySlot
                    fillColor: "#fc071c2b"
                    z: 10
                    width: win.sideShown ? stage.drawerW : Math.min(760, historySlot.width - 24)
                    height: win.sideShown ? stage.height : historySlot.height
                    y: 0
                    x: win.sideShown ? (win.historyOpen ? 0 : -width - 24) : (historySlot.width - width) / 2
                    visible: !win.sideShown || win.historyOpen
                    Rectangle { parent: chatPanel; anchors.fill: parent; anchors.margins: -4; z: -1; radius: 9; color: "#05121e"; border.color: "#31667e"; border.width: 2 }
                    headerExtra: [
                        HeaderButton { objectName: "historyResizeButton"; width: 26; height: 26; visible: !win.sideShown
                            glyphCode: win.historyMode === 2 ? 0xE73F : 0xE740
                            tip: win.historyMode === 2 ? "Cỡ hội thoại mặc định" : "Mở rộng lịch sử (quả cầu tự điều chỉnh)"
                            onClicked: win.historyMode = win.historyMode === 2 ? 0 : 2 },
                        HeaderButton { objectName: "historyCollapseButton"; width: 26; height: 26; visible: !win.sideShown
                            glyphCode: win.historyCompact ? 0xE70D : 0xE70E
                            tip: win.historyCompact ? "Hiện hội thoại (Ctrl+H)" : "Thu gọn hội thoại (Ctrl+H)"
                            onClicked: win.historyMode = win.historyCompact ? (nexa.timeline.length ? 0 : 2) : 1 },
                        HeaderButton { width: 26; height: 26; glyphCode: 0xE74D; tip: "Xóa hội thoại"; hoverTint: win.hazard
                                       onClicked: nexa.clearConversation() },
                        HeaderButton { width: 26; height: 26; visible: win.sideShown; glyphCode: 0xE711; tip: "Đóng nhật ký (Ctrl+H)"
                                       onClicked: win.historyOpen = false }
                    ]
                    ColumnLayout {
                        visible: win.sideShown || !win.historyCompact
                        anchors.fill: parent; spacing: 8
                        Item {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            ListView {
                                id: chat
                                objectName: "chat"
                                anchors.fill: parent
                                clip: true; spacing: 10
                                model: nexa.timeline
                                property bool followTail: true
                                onWidthChanged: if (followTail) Qt.callLater(function() { chat.positionViewAtEnd() })
                                onHeightChanged: if (followTail) Qt.callLater(function() { chat.positionViewAtEnd() })
                                onModelChanged: if (followTail) Qt.callLater(function() { chat.positionViewAtEnd() })
                                onMovementEnded: followTail = atYEnd
                                onCountChanged: if (followTail) Qt.callLater(function() { chat.positionViewAtEnd() })
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
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
                                            Text { text: row.modelData.time || ""; font.family: win.monoFont; font.pixelSize: 11; color: Theme.textMuted }
                                            Text { text: row.isUser ? "▸ ANH SƠN" : "◂ NEXA"; font.family: win.tacFont; font.pixelSize: 11
                                                   font.letterSpacing: 2; color: row.isUser ? win.ice : win.amber }
                                            Text { visible: row.isUser && row.modelData.source === "voice"; text: win.glyph(0xE720)
                                                   font.family: win.iconFont; font.pixelSize: 10; color: win.iceDim
                                                   anchors.verticalCenter: parent.verticalCenter }
                                        }
                                        Text { id: msg; x: 12; y: meta.implicitHeight + 4
                                               width: Math.min(chat.width - 14, implicitWidth); text: row.isTask ? "" : (row.modelData.text || "")
                                               color: Theme.textPrimary; font.pixelSize: 14; lineHeight: 1.12
                                               wrapMode: Text.Wrap; textFormat: Text.PlainText }
                                    }
                                    // A bounded task card keeps long tool titles and results readable.
                                    Rectangle {
                                        id: taskCard
                                        visible: row.isTask
                                        readonly property color sc: win.taskColor(row.modelData.status)
                                        readonly property bool spinning: row.isTask && (row.modelData.status === "running" || row.modelData.status === "queued")
                                        readonly property string detail: row.modelData.text || ""
                                        x: 4; width: chat.width - 4
                                        height: taskDetails.implicitHeight + 20
                                        radius: 8; color: Qt.rgba(sc.r, sc.g, sc.b, 0.055)
                                        border.color: Theme.border
                                        ColumnLayout {
                                            id: taskDetails
                                            x: 10; y: 10; width: parent.width - 20; spacing: 5
                                            RowLayout {
                                                Layout.fillWidth: true; spacing: 7
                                                Text {
                                                    text: win.glyph(taskCard.spinning ? 0xE9F5 : win.taskGlyph(row.modelData.status))
                                                    color: taskCard.sc; font.family: win.iconFont; font.pixelSize: 12
                                                    RotationAnimator on rotation { from: 0; to: 360; duration: 1800; loops: Animation.Infinite
                                                        running: taskCard.visible && taskCard.spinning && nexa.effects !== "minimal" }
                                                }
                                                Text { Layout.fillWidth: true; text: row.modelData.title || "Tác vụ"
                                                    color: Theme.textPrimary; font.pixelSize: 12; font.weight: Font.DemiBold
                                                    elide: Text.ElideRight; textFormat: Text.PlainText }
                                                Text { text: row.modelData.time || ""; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 9 }
                                            }
                                            Text { Layout.fillWidth: true; visible: taskCard.detail.length > 0 && taskCard.detail !== row.modelData.title
                                                text: taskCard.detail; color: Theme.textSecondary; font.pixelSize: 12
                                                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText }
                                        }
                                    }
                                }
                            }
                            Column {
                                anchors.centerIn: parent
                                visible: chat.count === 0
                                spacing: 6
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Hội thoại giữa anh và NEXA"; color: Theme.textSecondary
                                       font.family: win.tacFont; font.pixelSize: 13; font.letterSpacing: 1.4 }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Nói hoặc nhập lệnh để bắt đầu."
                                       color: win.iceDim; font.pixelSize: 12 }
                            }
                        }
                        // Workspace drawer retains its own command entry.
                        Item {
                            visible: win.sideShown
                            Layout.fillWidth: true
                            implicitHeight: 40
                            Chamfer { anchors.fill: parent; cut: 8; fill: Theme.inputGlass
                                      stroke: input.activeFocus ? win.amber : Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.28) }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 4; spacing: 6
                                Text { text: ">"; color: win.amber; font.family: win.monoFont; font.pixelSize: 16; font.bold: true }
                                TextField {
                                    id: input
                                    Layout.fillWidth: true
                                    placeholderText: "Nhập lệnh… (mở Notepad, âm lượng 30%)"
                                    color: "white"; font.family: win.monoFont; font.pixelSize: 13
                                    placeholderTextColor: Theme.textMuted
                                    leftPadding: 0
                                    background: Item {}
                                    onAccepted: { if (text.trim().length) { nexa.sendText(text); text = "" } }
                                }
                                Item {
                                    id: sendBtn
                                    readonly property bool ready: input.text.trim().length > 0
                                    implicitWidth: 34; implicitHeight: 32
                                    Chamfer { anchors.fill: parent; cut: 6
                                              fill: sendBtn.ready ? (sendMouse.pressed ? Qt.darker(win.amber, 1.4) : win.amber) : Theme.surfaceDeep
                                              stroke: sendBtn.ready ? win.amber : Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2) }
                                    Text { anchors.centerIn: parent; text: win.glyph(0xE724); font.family: win.iconFont; font.pixelSize: 14
                                           color: sendBtn.ready ? "#1a0e00" : Theme.textMuted }
                                    MouseArea { id: sendMouse; anchors.fill: parent; hoverEnabled: true
                                                onClicked: { if (input.text.trim().length) { nexa.sendText(input.text); input.text = "" } } }
                                    NTip { visible: sendMouse.containsMouse; text: "Gửi (Enter)" }
                                }
                            }
                        }
                        Text { Layout.fillWidth: true; visible: text.length > 0; text: nexa.statusText
                               color: Theme.textMuted; font.family: win.monoFont; font.pixelSize: 10; elide: Text.ElideRight }
                    }
                }
            }

            ReferenceOperations {
                id: operationsRail
                visible: win.width >= 1200 && !win.sideShown
                Layout.fillHeight: true; Layout.preferredWidth: Math.min(290, win.width * 0.19)
                Layout.minimumWidth: Layout.preferredWidth; Layout.maximumWidth: Layout.preferredWidth
                timeline: nexa.timeline; appState: nexa.state; stateLabel: nexa.stateLabel; stateDetail: nexa.stateDetail; status: nexa.status; foreground: nexa.foreground
                modelJob: nexa3d.activeJob; codeJob: nexaCode.job
                onModels: nexa3d.workspace = true
                onCode: nexaCode.openPanel()
            }
            ReferenceRuntimeRail {
                objectName: "runtimeRail"
                visible: win.width >= 1000 && !win.sideShown
                Layout.fillHeight: true; Layout.preferredWidth: Math.min(270, win.width * 0.18)
                Layout.minimumWidth: Layout.preferredWidth; Layout.maximumWidth: Layout.preferredWidth
                status: nexa.status; provider: nexa3d.providerStatus; libraries: nexa.libraries
                onVoice: nexa.state === "STANDBY" ? nexa.wake() : nexa.pushToTalk()
                onCode: nexaCode.openPanel()
                onModels: nexa3d.workspace = true
                onStop: nexa.stop()
                onSettings: settingsPopup.open()
            }

            // Mô hình 3D (tệp riêng; Loader để lỗi plugin Qt Quick 3D không ảnh hưởng giao diện chính)
            Loader {
                id: viewer3d
                objectName: "viewer3d"
                active: win.viewerShown
                visible: active
                focus: active
                Layout.fillHeight: true
                Layout.fillWidth: true
                source: "ModelViewer.qml"
                onLoaded: {
                    if (win.pendingProductPanel) {
                        item.commandProductPanel("open", win.pendingProductPanel)
                        win.pendingProductPanel = ""
                    }
                }
                onStatusChanged: if (status === Loader.Error) toastBox.show("Không nạp được trình xem 3D (thiếu Qt Quick 3D?). Xem logs/nexa.log.", true)
            }

            // Sinh code (cột phải, giống trình xem 3D): NEXA vẫn hiện đầy đủ bên trái
            Loader {
                id: codePanel
                objectName: "codePanel"
                active: win.codeShown
                visible: active
                Layout.fillHeight: true
                Layout.fillWidth: true
                sourceComponent: Component { CodePanel { copilotReserve: copilot.visible ? copilot.height + 10 : 0
                                                          onCloseRequested: nexaCode.closePanel() } }
            }
        }
        RowLayout {
            visible: !win.sideShown && win.width >= 1200
            Layout.fillWidth: true; Layout.preferredHeight: 40; Layout.maximumHeight: 40; spacing: 12
            Text { text: "◈  NEXA " + nexa.appVersion + "\n" + win.missionClock; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 9; Layout.preferredWidth: 180 }
            Item { id: footerInputSlot; Layout.fillWidth: true; Layout.preferredHeight: 34 }
            Item { id: footerActionsSlot; Layout.preferredWidth: 360; Layout.preferredHeight: 34 }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Rectangle { implicitWidth: 5; implicitHeight: 5; radius: 3; color: win.stateAccent }
            Text { text: nexa.stateLabel; color: Theme.textSecondary; font.pixelSize: 10 }
            Text { visible: win.width > 800; text: " /  " + (nexa.foreground || "NEXA"); color: Theme.textMuted
                font.pixelSize: 10; elide: Text.ElideRight; Layout.maximumWidth: 400 }
            Item { Layout.fillWidth: true }
            Text { text: "CTRL + K  ·  RA LỆNH"; color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 10 }
        }
    }

    Popup {
        id: systemDetails; objectName: "systemDetails"; anchors.centerIn: parent
        width: Math.min(400, win.width - 32); height: Math.min(760, win.height - 40)
        modal: true; focus: true; padding: 0; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Item {}
        SystemDashboard { anchors.fill: parent; st: nexa.sysStats; status: nexa.status
            headerExtra: HeaderButton { width: 26; height: 26; glyphCode: 0xE711; tip: "Đóng"; onClicked: systemDetails.close() } }
    }
    Popup {
        id: runtimeDetails; objectName: "runtimeDetails"; anchors.centerIn: parent
        width: Math.min(430, win.width - 32); height: Math.min(760, win.height - 40)
        modal: true; focus: true; padding: 0; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Item {}
        RuntimeDashboard { anchors.fill: parent; status: nexa.status; provider: nexa3d.providerStatus; libraries: nexa.libraries
            headerExtra: HeaderButton { width: 26; height: 26; glyphCode: 0xE711; tip: "Đóng"; onClicked: runtimeDetails.close() } }
    }

    // ---------- NEXA copilot: radar nổi ở góc dưới trái khi bảng 3D / code chiếm hết màn ----------
    // Lõi radar nhỏ + trạng thái + phụ đề cuối + nút nói / dừng / nhật ký. Thu gọn → chỉ còn radar + nút dừng.
    Item {
        id: copilot
        objectName: "copilot"
        property bool collapsed: false
        visible: win.sideShown && !nexa.compact
        z: 7
        x: win.historyOpen ? 20 + 70 + 400 + 14 : 20 + 70 + 22           // tránh ngăn nhật ký trượt ra từ trái
        Behavior on x { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        y: win.height - 14 - 20 - height
        width: collapsed ? 150 : 232
        height: collapsed ? 84 : 150
        Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        readonly property bool listening: nexa.state === "LISTENING"
        Chamfer { anchors.fill: parent; cut: 12; fill: Theme.panelGlass; stroke: Qt.rgba(win.stateAccent.r, win.stateAccent.g, win.stateAccent.b, 0.55) }
        Rectangle { x: 12; y: 0; width: 42; height: 2; color: win.amber }
        MouseArea { anchors.fill: parent; onDoubleClicked: copilot.collapsed = !copilot.collapsed }   // chặn click xuyên xuống bảng
        TacticalCore {
            id: copilotCore
            x: 8; y: 6
            width: 72; height: 72
            appState: nexa.state; micLevel: nexa.micLevel; outLevel: nexa.outLevel; outBands: nexa.outBands
            effects: nexa.effects === "full" ? "reduced" : nexa.effects
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: nexa.state === "STANDBY" ? nexa.wake() : nexa.pushToTalk()
                        onDoubleClicked: nexa.wake() }
        }
        Column {
            x: 86; y: 10
            width: copilot.width - x - 10
            spacing: 3
            Row {
                spacing: 6
                Text { text: "NEXA"; color: win.amber; font.family: win.monoFont; font.pixelSize: 10
                       anchors.verticalCenter: parent.verticalCenter }
                Text { visible: !copilot.collapsed; text: nexa.stateLabel.toUpperCase(); color: win.stateAccent
                       font.family: win.tacFont; font.pixelSize: 12; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
            }
            Text {
                visible: !copilot.collapsed
                width: parent.width
                text: copilot.listening ? (nexa.heardText.length > 0 ? "▸ " + nexa.heardText : "▸ Em đang nghe…")
                      : (win.lastAssistantText.length > 0 ? win.lastAssistantText : (win.lastUserText.length > 0 ? "▸ " + win.lastUserText : "Nói “NEXA” hoặc bấm radar để ra lệnh"))
                color: copilot.listening ? "white" : Theme.textPrimary; font.pixelSize: 11; lineHeight: 1.1
                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
            }
            // thu gọn: chỉ nút dừng
            TacButton { visible: copilot.collapsed; implicitHeight: 30; showCaption: false; primary: true; tint: win.hazard
                        glyphCode: 0xE71A; tip: "DỪNG KHẨN CẤP (Ctrl+Alt+Esc)"; onClicked: nexa.stop() }
        }
        Row {
            visible: !copilot.collapsed
            x: 10; y: copilot.height - height - 10
            spacing: 5
            TacButton { implicitHeight: 32; showCaption: false; primary: true; tint: win.stateAccent; glyphCode: 0xE720
                        pulsing: copilot.listening
                        tip: nexa.state === "STANDBY" ? "Đánh thức NEXA (Ctrl+Alt+N)" : "Nhấn để nói"
                        onClicked: nexa.state === "STANDBY" ? nexa.wake() : nexa.pushToTalk() }
            TacButton { implicitHeight: 32; showCaption: false; glyphCode: 0xE8BD; active: win.historyOpen
                        tip: "Nhật ký hội thoại và ô gõ lệnh (Ctrl+H)"; onClicked: win.toggleHistory() }
            TacButton { implicitHeight: 32; showCaption: false; glyphCode: 0xE711; tint: win.amber; visible: win.busy
                        tip: "Hủy tác vụ đang chạy"; onClicked: nexa.cancelTask() }
            TacButton { implicitHeight: 32; showCaption: false; glyphCode: 0xE73F; tip: "Thu gọn radar"
                        onClicked: copilot.collapsed = true }
            TacButton { implicitHeight: 32; showCaption: true; caption: "Dừng"; primary: true; tint: win.hazard; glyphCode: 0xE71A
                        tip: "DỪNG KHẨN CẤP (Ctrl+Alt+Esc)"; onClicked: nexa.stop() }
        }
        // thu gọn: bấm mép phải để mở lại
        Text {
            visible: copilot.collapsed
            anchors.right: parent.right; anchors.rightMargin: 8; anchors.top: parent.top; anchors.topMargin: 6
            text: win.glyph(0xE740); font.family: win.iconFont; font.pixelSize: 11; color: expandMa.containsMouse ? win.ice : win.iceDim
            MouseArea { id: expandMa; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; onClicked: copilot.collapsed = false }
        }
    }

    // ---------- Bảng cử chỉ ----------
    GesturePanel {
        id: gesturePanel
        objectName: "gesturePanel"
        visible: false
        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.margins: 14; anchors.topMargin: 64; anchors.bottomMargin: 14
        width: Math.min(420, win.width - 40)
        z: 5
        onCloseRequested: visible = false
    }

    // ---------- Mô hình 3D (tệp riêng; Loader để lỗi plugin Qt Quick 3D không ảnh hưởng giao diện chính) ----------
    Loader {
        id: generation3d
        active: nexa3d.workspace && !nexa3d.viewerOpen && !nexa.compact
        anchors.centerIn: parent
        width: Math.min(win.width - 80, 980); height: Math.min(win.height - 90, 680)
        z: 18
        sourceComponent: Component { ModelGenerationPanel { onCloseRequested: nexa3d.workspace = false } }
    }
    Loader {
        id: educationWorkspace
        active: nexaEdu.open && !nexa.compact
        anchors.centerIn: parent
        width: Math.min(win.width - 80, 1050); height: Math.min(win.height - 90, 700)
        z: 18
        sourceComponent: Component { EducationPanel { onCloseRequested: nexaEdu.close() } }
    }
    // (trình xem 3D nằm trong "Nội dung chính", cạnh cột NEXA)

    // (Sinh code nằm trong "Nội dung chính", cạnh cột NEXA)

    // ---------- Hộp xác nhận ----------
    Popup {
        id: confirmPopup
        modal: true
        closePolicy: Popup.NoAutoClose
        visible: nexa.confirmation.active === true
        anchors.centerIn: parent
        width: Math.min(win.width - 80, nexa.confirmation.previewUrl ? 900 : 560)
        padding: 20
        property int remaining: nexa.confirmation.timeout || 30
        onVisibleChanged: { if (visible) { remaining = nexa.confirmation.timeout || 30; cropRect.reset() } }
        Timer { interval: 1000; repeat: true; running: confirmPopup.visible; onTriggered: confirmPopup.remaining = Math.max(0, confirmPopup.remaining - 1) }
        background: Rectangle { radius: 16; color: Theme.surface; border.color: Theme.amber; border.width: 2 }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: "Cần anh xác nhận"; color: Theme.amber; font.pixelSize: 20; font.bold: true }
            Text { Layout.fillWidth: true; text: nexa.confirmation.description || ""; color: "white"; font.pixelSize: 15; wrapMode: Text.Wrap }
            Item {
                id: previewBox
                visible: !!nexa.confirmation.previewUrl
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? Math.min(420, width * (nexa.confirmation.preview_height || 1) / Math.max(1, nexa.confirmation.preview_width || 1)) : 0
                Image {
                    id: shot
                    anchors.fill: parent
                    source: nexa.confirmation.previewUrl || ""
                    fillMode: Image.PreserveAspectFit
                    cache: false
                }
                // Kéo chuột để chọn vùng gửi đi (tọa độ quy đổi về pixel ảnh gốc).
                Rectangle {
                    id: cropRect
                    property bool has: false
                    function reset() { has = false; x = 0; y = 0; width = 0; height = 0 }
                    visible: has
                    color: "#2222d3ee"; border.color: win.cyan; border.width: 2
                }
                MouseArea {
                    anchors.fill: parent
                    property point p0
                    onPressed: (m) => { p0 = Qt.point(m.x, m.y); cropRect.has = true; cropRect.x = m.x; cropRect.y = m.y; cropRect.width = 0; cropRect.height = 0 }
                    onPositionChanged: (m) => { cropRect.x = Math.min(p0.x, m.x); cropRect.y = Math.min(p0.y, m.y)
                                                cropRect.width = Math.abs(m.x - p0.x); cropRect.height = Math.abs(m.y - p0.y) }
                }
                Text { anchors.bottom: parent.bottom; anchors.left: parent.left; color: win.textDim; font.pixelSize: 11
                       text: "Kéo chuột trên ảnh để chỉ gửi một vùng. Không chọn = gửi toàn bộ ảnh trên." }
            }
            RowLayout {
                spacing: 10
                Text { text: "Tự hủy sau " + confirmPopup.remaining + " giây"; color: win.textDim; font.pixelSize: 12 }
                Item { Layout.fillWidth: true }
                NButton { text: "Hủy"; onClicked: nexa.deny(nexa.confirmation.id) }
                NButton {
                    text: "Đồng ý"; tint: Theme.success
                    onClicked: {
                        var cx = 0, cy = 0, cw = 0, ch = 0
                        if (cropRect.has && cropRect.width > 8 && cropRect.height > 8 && shot.paintedWidth > 0) {
                            var ox = (shot.width - shot.paintedWidth) / 2, oy = (shot.height - shot.paintedHeight) / 2
                            var sx = shot.sourceSize.width / shot.paintedWidth, sy = shot.sourceSize.height / shot.paintedHeight
                            cx = Math.max(0, (cropRect.x - ox) * sx); cy = Math.max(0, (cropRect.y - oy) * sy)
                            cw = cropRect.width * sx; ch = cropRect.height * sy
                        }
                        nexa.confirm(nexa.confirmation.id, cx, cy, cw, ch)
                    }
                }
            }
        }
    }

    // ---------- Cài đặt ----------
    Popup {
        id: settingsPopup
        objectName: "settingsPopup"
        modal: true
        anchors.centerIn: parent
        width: Math.min(win.width - 60, 1040); height: Math.min(win.height - 60, 720)
        padding: 0
        background: Rectangle { radius: 16; color: Theme.surface; border.color: win.panelBorder }
        contentItem: Loader {
            active: settingsPopup.visible
            sourceComponent: Component { Settings { onCloseRequested: settingsPopup.close() } }
        }
    }

    // ---------- Thông báo nổi ----------
    Rectangle {
        id: toastBox
        property bool isError: false
        function show(text, err) { toastText.text = text; isError = err; opacity = 1; toastTimer.restart() }
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - 120
        width: Math.min(parent.width - 80, toastText.implicitWidth + 40); height: toastText.implicitHeight + 20
        radius: 12; color: Theme.panelGlass; border.color: isError ? Theme.danger : win.cyan
        opacity: 0; visible: opacity > 0; z: 50
        Behavior on opacity { NumberAnimation { duration: 250 } }
        Text { id: toastText; anchors.centerIn: parent; width: Math.min(implicitWidth, win.width - 120); color: "white"
               font.pixelSize: 14; wrapMode: Text.Wrap }
        Timer { id: toastTimer; interval: 3500; onTriggered: toastBox.opacity = 0 }
    }
}
