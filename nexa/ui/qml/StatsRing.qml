// Vòng thông số HUD quanh quả cầu: 4 cung đo ở 4 góc chéo — CPU · RAM · GPU · độ trễ AI.
// Số liệu từ nexa.sysStats (nexa/ui/sysstats.py, 1,5 s/lần); cung chỉ vẽ lại khi số đổi (Canvas nhẹ).
// Vạch chia độ xoay chậm là một Canvas vẽ một lần rồi xoay bằng scene graph (không tốn CPU vẽ lại).
import QtQuick
import "Theme.js" as Theme

Item {
    id: ring
    property var stats: ({})
    property color accent: Theme.accent
    readonly property real s: Math.min(width, height)
    readonly property real radius: s * 0.445
    readonly property bool hasData: stats && stats.cpu !== undefined
    readonly property real aiFull: 5000               // độ trễ AI đầy cung (ms)

    // giá trị 0..1 đã làm mượt
    property real cpuV: hasData ? stats.cpu / 100 : 0
    property real ramV: hasData ? stats.ram / 100 : 0
    property real gpuV: hasData && stats.gpu !== null && stats.gpu !== undefined ? stats.gpu / 100 : 0
    property real aiV: hasData ? Math.min(1, (stats.ai_ms || 0) / aiFull) : 0
    Behavior on cpuV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
    Behavior on ramV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
    Behavior on gpuV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
    Behavior on aiV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
    onCpuVChanged: gauges.requestPaint()
    onRamVChanged: gauges.requestPaint()
    onGpuVChanged: gauges.requestPaint()
    onAiVChanged: gauges.requestPaint()
    onAccentChanged: { gauges.requestPaint(); ticks.requestPaint() }
    onWidthChanged: ticks.requestPaint()
    onHeightChanged: ticks.requestPaint()

    function pct(v) { return v === null || v === undefined ? "—" : Math.round(v) + "%" }
    function ms(v) { return !v ? "—" : v < 1000 ? Math.round(v) + " ms" : (v / 1000).toFixed(1) + " s" }

    // 4 cung: góc giữa (độ, 0 = phải, chiều kim đồng hồ), độ rộng cung
    readonly property real span: 62
    readonly property var gaugeDefs: [
        { key: "cpu", mid: -135, label: "CPU" },
        { key: "ram", mid: -45, label: "RAM" },
        { key: "gpu", mid: 45, label: "GPU" },
        { key: "ai", mid: 135, label: "AI" }
    ]
    function valueOf(key) { return key === "cpu" ? cpuV : key === "ram" ? ramV : key === "gpu" ? gpuV : aiV }
    function textOf(key) {
        if (!hasData) return "—"
        return key === "ai" ? ms(stats.ai_ms) : pct(stats[key])
    }
    function subOf(key) {
        if (!hasData) return ""
        if (key === "gpu") return stats.vram === null || stats.vram === undefined ? "không có" : "VRAM " + pct(stats.vram)
        if (key === "ai") return stats.ai_ms ? "phản hồi" : "chưa gọi"
        return ""
    }

    // ---- vạch chia độ (xoay chậm) ----
    Canvas {
        id: ticks
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var cx = width / 2, cy = height / 2, R = ring.radius + ring.s * 0.028, ac = ring.accent
            for (var i = 0; i < 120; i++) {
                var a = i / 120 * Math.PI * 2, major = i % 10 === 0
                var r0 = R, r1 = R + (major ? ring.s * 0.018 : ring.s * 0.008)
                ctx.strokeStyle = Qt.rgba(ac.r, ac.g, ac.b, major ? 0.45 : 0.18)
                ctx.lineWidth = major ? 1.5 : 1
                ctx.beginPath()
                ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0)
                ctx.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1)
                ctx.stroke()
            }
        }
        RotationAnimator on rotation { from: 0; to: 360; duration: 120000; loops: Animation.Infinite; running: ring.visible }
    }

    // ---- 4 cung đo ----
    Canvas {
        id: gauges
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var cx = width / 2, cy = height / 2, R = ring.radius, w = Math.max(3, ring.s * 0.009)
            var ac = ring.accent
            // vòng nền mảnh nối liền 4 cung
            ctx.lineWidth = 1
            ctx.strokeStyle = Qt.rgba(ac.r, ac.g, ac.b, 0.14)
            ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke()
            ctx.lineCap = "round"
            for (var i = 0; i < ring.gaugeDefs.length; i++) {
                var g = ring.gaugeDefs[i], v = ring.valueOf(g.key)
                var a0 = (g.mid - ring.span / 2) * Math.PI / 180, a1 = (g.mid + ring.span / 2) * Math.PI / 180
                // rãnh
                ctx.lineWidth = w
                ctx.strokeStyle = Qt.rgba(ac.r, ac.g, ac.b, 0.10)
                ctx.beginPath(); ctx.arc(cx, cy, R, a0, a1); ctx.stroke()
                // mức đo + quầng sáng
                if (v > 0.003) {
                    var c = Qt.color(Theme.loadColor(v)), a = a0 + (a1 - a0) * v
                    ctx.lineWidth = w * 2.6
                    ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.12)
                    ctx.beginPath(); ctx.arc(cx, cy, R, a0, a); ctx.stroke()
                    ctx.lineWidth = w
                    ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.95)
                    ctx.beginPath(); ctx.arc(cx, cy, R, a0, a); ctx.stroke()
                    // chấm đầu mức
                    ctx.fillStyle = "white"
                    ctx.beginPath(); ctx.arc(cx + Math.cos(a) * R, cy + Math.sin(a) * R, w * 0.55, 0, Math.PI * 2); ctx.fill()
                }
            }
        }
    }

    // ---- nhãn số liệu (Text thật cho chữ sắc nét) ----
    Repeater {
        model: ring.gaugeDefs
        delegate: Column {
            id: lab
            required property var modelData
            readonly property real ang: modelData.mid * Math.PI / 180
            readonly property real lr: ring.radius + ring.s * 0.06
            readonly property real ax: ring.width / 2 + Math.cos(ang) * lr
            readonly property real ay: ring.height / 2 + Math.sin(ang) * lr
            x: Math.cos(ang) < 0 ? ax - width : ax
            y: Math.sin(ang) < 0 ? ay - height : ay
            spacing: 0
            readonly property int align: Math.cos(ang) < 0 ? Text.AlignRight : Text.AlignLeft
            readonly property real colW: Math.max(t1.implicitWidth, t2.implicitWidth, t3.visible ? t3.implicitWidth : 0)
            Text { id: t1; width: lab.colW; horizontalAlignment: lab.align; text: lab.modelData.label
                   color: Qt.rgba(ring.accent.r, ring.accent.g, ring.accent.b, 0.75)
                   font.pixelSize: Math.max(9, ring.s * 0.02); font.bold: true; font.letterSpacing: 2 }
            Text { id: t2; width: lab.colW; horizontalAlignment: lab.align
                   text: ring.textOf(lab.modelData.key); color: "white"
                   font.pixelSize: Math.max(13, ring.s * 0.036); font.bold: true }
            Text { id: t3; width: lab.colW; horizontalAlignment: lab.align; text: ring.subOf(lab.modelData.key)
                   visible: text.length > 0; color: "#6f8fb0"; font.pixelSize: Math.max(9, ring.s * 0.018) }
        }
    }
}
