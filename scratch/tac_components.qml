    // ---------- bộ kiểu chiến thuật (Halo / Mass Effect): khung vát góc, băng + cam ----------
    readonly property color ice: "#8fd8ff"
    readonly property color amber: "#ffae42"
    readonly property color hazard: "#ff5a4f"
    readonly property color iceDim: "#5f84a6"
    readonly property string tacFont: Qt.fontFamilies().indexOf("Bahnschrift") >= 0 ? "Bahnschrift" : "Segoe UI"
    readonly property string monoFont: "Consolas"
    function tacLoad(v) { return v < 0 ? "#34506b" : v >= 0.85 ? win.hazard : v >= 0.6 ? win.amber : win.ice }
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
    component Chamfer: Shape {
        id: ch
        property real cut: 8
        property color fill: "transparent"
        property color stroke: win.ice
        property real strokeW: 1
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: ch.fill; strokeColor: ch.stroke; strokeWidth: ch.strokeW
            joinStyle: ShapePath.MiterJoin
            startX: ch.cut; startY: 0.5
            PathLine { x: ch.width - 0.5; y: 0.5 }
            PathLine { x: ch.width - 0.5; y: ch.height - ch.cut }
            PathLine { x: ch.width - ch.cut; y: ch.height - 0.5 }
            PathLine { x: 0.5; y: ch.height - 0.5 }
            PathLine { x: 0.5; y: ch.cut }
            PathLine { x: ch.cut; y: 0.5 }
        }
    }
    // Bảng chiến thuật: khung vát + nẹp sáng ở góc + tab tiêu đề "01 SYS · HỆ THỐNG"
    component TacPanel: Item {
        id: tp
        property string title: ""
        property string code: ""
        property color accent: win.ice
        default property alias content: tpBody.data
        property alias headerExtra: tpExtra.data
        readonly property real cut: 14
        Chamfer { anchors.fill: parent; cut: tp.cut; fill: "#c4061220"; stroke: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.22) }
        Shape {   // nẹp sáng góc trên trái / dưới phải
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: "transparent"; strokeColor: tp.accent; strokeWidth: 2; joinStyle: ShapePath.MiterJoin
                startX: 1; startY: tp.cut + 34
                PathLine { x: 1; y: tp.cut }
                PathLine { x: tp.cut; y: 1 }
                PathLine { x: tp.cut + 70; y: 1 }
            }
            ShapePath {
                fillColor: "transparent"; strokeColor: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.55); strokeWidth: 2
                joinStyle: ShapePath.MiterJoin
                startX: tp.width - 1; startY: tp.height - tp.cut - 26
                PathLine { x: tp.width - 1; y: tp.height - tp.cut }
                PathLine { x: tp.width - tp.cut; y: tp.height - 1 }
                PathLine { x: tp.width - tp.cut - 44; y: tp.height - 1 }
            }
        }
        Row {
            x: 22; y: 11
            spacing: 8
            Text { text: tp.code; color: win.amber; font.family: win.monoFont; font.pixelSize: 11
                   anchors.verticalCenter: parent.verticalCenter }
            Text { text: tp.title; color: "#d6eeff"; font.family: win.tacFont; font.pixelSize: 13; font.letterSpacing: 3
                   anchors.verticalCenter: parent.verticalCenter }
        }
        Row { id: tpExtra; anchors.right: parent.right; anchors.rightMargin: 12; y: 6; spacing: 4 }
        // vạch ngăn dưới tiêu đề: nét mảnh + 3 khấc cam
        Rectangle { x: 16; y: 38; width: tp.width - 32; height: 1; color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.14) }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 16; y: 36
            spacing: 3
            Repeater { model: 3; Rectangle { width: 10; height: 3; color: win.amber; opacity: 0.85 } }
        }
        Item { id: tpBody; anchors.fill: parent; anchors.topMargin: 50; anchors.leftMargin: 16; anchors.rightMargin: 16; anchors.bottomMargin: 14 }
    }
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
        signal clicked()
        opacity: enabled ? 1 : 0.35
        implicitHeight: 42
        implicitWidth: tbRow.implicitWidth + (showCaption ? 30 : 24)
        readonly property bool hot: tbMouse.containsMouse
        Chamfer {   // viền lan tỏa khi đang nghe
            anchors.fill: parent; anchors.margins: -4; cut: 11
            stroke: tb.tint; strokeW: 1.5
            visible: tb.pulsing
            SequentialAnimation on opacity {
                running: tb.pulsing; loops: Animation.Infinite
                NumberAnimation { from: 0.9; to: 0.1; duration: 900; easing.type: Easing.OutCubic }
            }
        }
        Chamfer {
            anchors.fill: parent; cut: 9
            fill: tb.primary ? Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, tbMouse.pressed ? 0.5 : tb.hot ? 0.34 : 0.22)
                 : tb.active ? Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, 0.16)
                 : tbMouse.pressed ? "#081628" : tb.hot ? "#13283f" : "#0a1828"
            stroke: Qt.rgba(tb.tint.r, tb.tint.g, tb.tint.b, tb.primary || tb.active || tb.hot ? 0.9 : 0.3)
        }
        Rectangle { visible: tb.active || tb.primary; x: 12; width: tb.width - 30; height: 2
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 4; color: tb.tint; opacity: 0.9 }
        Row {
            id: tbRow
            anchors.centerIn: parent
            spacing: 8
            scale: tbMouse.pressed ? 0.95 : 1
            Text { text: win.glyph(tb.glyphCode); font.family: win.iconFont; font.pixelSize: 15
                   color: tb.primary || tb.active ? "white" : (tb.hot ? tb.tint : "#bfe3ff")
                   anchors.verticalCenter: parent.verticalCenter }
            Text { visible: tb.showCaption; text: tb.caption.toUpperCase(); font.family: win.tacFont; font.pixelSize: 12
                   font.letterSpacing: 2; color: tb.primary || tb.active ? "white" : "#a9cbe6"
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
        Text { text: sb.label; color: win.iceDim; font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 3 }
        Text { anchors.right: parent.right; text: sb.sub; color: "#4f6f8c"; font.family: win.monoFont; font.pixelSize: 10 }
        Row {
            y: 14; spacing: 3
            Text { id: sbBig; text: sb.big; color: sb.v < 0 ? "#4f6f8c" : "#ecf8ff"; font.family: win.tacFont; font.pixelSize: 30 }
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
                    color: index < Math.round(Math.max(0, sb.shownV) * 20) ? sb.col : "#10233a"
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

