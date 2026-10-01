// HUD góc màn hình (click-through, không nhận focus) — theme Arc Reactor.
// Python (nexa/ui/hud.py) đặt các thuộc tính dưới đây và gọi addCard(); khi không còn gì hiển thị,
// HUD phát idle() để Python ẩn cửa sổ (cửa sổ layered ẩn thì không tốn GPU).
import QtQuick
import "Theme.js" as Theme

Item {
    id: hud
    width: 480; height: 560

    property string corner: "bottom_right"
    property string subtitle: ""
    property bool showSubtitles: true
    property int cardSeconds: 5
    property string appState: "STANDBY"
    property real outLevel: 0
    property var bands: [0, 0, 0, 0, 0, 0, 0, 0]
    signal idle()

    readonly property bool atBottom: corner.indexOf("bottom") === 0
    readonly property bool atRight: corner.indexOf("right") > 0
    readonly property color cyan: Theme.accent
    // màu theo trạng thái (Theme.js), trùng quả cầu ở cửa sổ chính
    property color accent: Theme.stateColor(appState)
    Behavior on accent { ColorAnimation { duration: 450 } }
    readonly property color ice: "#a5f3fc"
    readonly property color glass: Theme.panelGlass
    readonly property color edge: "#5522d3ee"
    readonly property color textColor: Theme.textPrimary
    readonly property color dim: Theme.textSecondary
    readonly property color ok: Theme.success
    readonly property color err: Theme.danger
    readonly property int margin: 6

    // ---------- phụ đề ----------
    property string shownText: ""
    property bool subVisible: false
    onSubtitleChanged: {
        if (subtitle.length && showSubtitles) { shownText = subtitle; subVisible = true; holdTimer.stop() }
        else holdTimer.restart()
    }
    Timer { id: holdTimer; interval: 1400; onTriggered: hud.subVisible = false }

    function addCard(title, message, status) {
        cards.insert(0, { title: title, message: message, status: status })
        while (cards.count > 3) cards.remove(cards.count - 1)
    }
    ListModel { id: cards }

    readonly property bool busy: subVisible || cards.count > 0
    onBusyChanged: busy ? idleTimer.stop() : idleTimer.restart()
    Timer { id: idleTimer; interval: 450; onTriggered: if (!hud.busy) hud.idle() }

    // Lõi "arc reactor" nhỏ: 8 cung sáng theo 8 dải tần thật của giọng NEXA.
    component Reactor: Canvas {
        id: rc
        width: 40; height: 40
        property var b: hud.bands
        property real lvl: hud.outLevel
        onBChanged: requestPaint()
        onLvlChanged: requestPaint()
        property color ac: hud.accent
        onAcChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var cx = width / 2, cy = height / 2, n = 8
            for (var i = 0; i < n; i++) {
                var v = rc.b && rc.b.length > i ? rc.b[i] : 0
                var a0 = -Math.PI / 2 + i / n * Math.PI * 2 + 0.07, a1 = a0 + Math.PI * 2 / n - 0.14
                ctx.strokeStyle = Qt.rgba(rc.ac.r, rc.ac.g, rc.ac.b, 0.25 + 0.75 * v)
                ctx.lineWidth = 3 + 3 * v
                ctx.beginPath(); ctx.arc(cx, cy, 15, a0, a1); ctx.stroke()
            }
            var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 10)
            g.addColorStop(0, Qt.rgba(1, 1, 1, 0.95))
            g.addColorStop(0.5, Qt.rgba(0.65, 0.95, 0.99, 0.5 + 0.5 * rc.lvl))
            g.addColorStop(1, "transparent")
            ctx.fillStyle = g
            ctx.beginPath(); ctx.arc(cx, cy, 6 + 5 * rc.lvl, 0, Math.PI * 2); ctx.fill()
        }
    }

    Rectangle {
        id: subPanel
        width: Math.min(hud.width - 2 * hud.margin, Math.max(260, subText.implicitWidth + 86))
        height: Math.max(58, subText.implicitHeight + 40)
        x: hud.atRight ? hud.width - width - hud.margin : hud.margin
        y: hud.atBottom ? hud.height - height - hud.margin : hud.margin
        radius: 14
        color: hud.glass
        border.color: hud.edge; border.width: 1
        opacity: hud.subVisible ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        transform: Translate { y: hud.subVisible ? 0 : (hud.atBottom ? 14 : -14)
                               Behavior on y { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } } }
        // vạch sáng cạnh phía màn hình
        Rectangle { width: 3; radius: 1.5; height: parent.height - 18; anchors.verticalCenter: parent.verticalCenter
                    x: hud.atRight ? parent.width - 3 : 0; color: hud.accent; opacity: 0.55 + 0.45 * hud.outLevel }
        Reactor { id: reactor; x: 12; anchors.verticalCenter: parent.verticalCenter }
        Text {
            anchors.left: reactor.right; anchors.leftMargin: 10; anchors.top: parent.top; anchors.topMargin: 6
            text: "NEXA"; color: hud.accent; font.pixelSize: 10; font.bold: true; font.letterSpacing: 2
        }
        Text {
            id: subText
            anchors.left: reactor.right; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 6
            width: Math.min(implicitWidth, hud.width - 2 * hud.margin - 86)
            text: hud.shownText; color: hud.textColor; font.pixelSize: 16; wrapMode: Text.WordWrap
            maximumLineCount: 4; elide: Text.ElideRight
        }
    }

    // ---------- thẻ kết quả ----------
    ListView {
        id: cardList
        interactive: false
        spacing: 8
        width: hud.width - 2 * hud.margin
        x: hud.margin
        verticalLayoutDirection: hud.atBottom ? ListView.BottomToTop : ListView.TopToBottom
        anchors.top: hud.atBottom ? parent.top : subPanel.bottom
        anchors.bottom: hud.atBottom ? subPanel.top : parent.bottom
        anchors.topMargin: hud.atBottom ? 0 : 8
        anchors.bottomMargin: hud.atBottom ? 8 : 0
        model: cards
        readonly property real slide: hud.atRight ? 60 : -60
        add: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 240 }
            NumberAnimation { property: "x"; from: cardList.slide; duration: 320; easing.type: Easing.OutCubic }
        }
        remove: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: 260 }
            NumberAnimation { property: "x"; to: cardList.slide; duration: 260; easing.type: Easing.InCubic }
        }
        displaced: Transition { NumberAnimation { properties: "y"; duration: 220; easing.type: Easing.OutCubic } }
        delegate: Item {
            id: card
            width: cardList.width
            height: body.height
            required property int index
            required property string title
            required property string message
            required property string status
            readonly property bool good: status === "done"
            Rectangle {
                id: body
                width: Math.min(card.width, Math.max(240, Math.max(ct.implicitWidth, cm.implicitWidth) + 74))
                height: col.implicitHeight + 22
                x: hud.atRight ? card.width - width : 0
                radius: 12; color: hud.glass
                border.color: card.good ? "#5534d399" : "#55fb7185"; border.width: 1
                Rectangle { width: 26; height: 26; radius: 13; x: 12; y: 11
                            color: "transparent"; border.color: card.good ? hud.ok : hud.err; border.width: 2
                            Text { anchors.centerIn: parent; text: card.good ? "✓" : "✕"; color: card.good ? hud.ok : hud.err
                                   font.pixelSize: 14; font.bold: true } }
                Column {
                    id: col
                    x: 50; y: 11; spacing: 2
                    width: body.width - 62
                    Text { id: ct; text: card.title; color: hud.textColor; font.pixelSize: 14; font.bold: true
                           width: Math.min(implicitWidth, col.width); elide: Text.ElideRight }
                    Text { id: cm; text: card.message; color: hud.dim; font.pixelSize: 13; wrapMode: Text.WordWrap
                           width: Math.min(implicitWidth, hud.width - 2 * hud.margin - 62); maximumLineCount: 3; elide: Text.ElideRight
                           visible: text.length > 0 }
                }
                // thanh đếm thời gian tự ẩn
                Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: 4; x: 12; height: 2; radius: 1
                            color: card.good ? hud.ok : hud.err; opacity: 0.6
                            NumberAnimation on width { from: body.width - 24; to: 0; duration: hud.cardSeconds * 1000 } }
            }
            Timer { interval: hud.cardSeconds * 1000; running: true; onTriggered: cards.remove(card.index) }
        }
    }
}
