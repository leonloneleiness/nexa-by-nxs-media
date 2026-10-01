from pathlib import Path

p = Path("nexa/ui/qml/Main.qml")
src = Path("scratch/Main.qml.bak3").read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)
assert "// NEXA: 2 cột" in lines[349], lines[349]
assert lines[589].strip() == "Item {", lines[589]
assert lines[716].rstrip() == "            }", repr(lines[716])
block = Path("scratch/stage_block.qml").read_text(encoding="utf-8")
s = "".join(lines[:349]) + block + "".join(lines[589:716]) + "            }\n" + "".join(lines[717:])


def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:80])
    s = s.replace(old, new)


rep('''    function taskColor(st) {''', '''    readonly property string lastAssistantText: {
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
    function toggleHistory() {
        historyOpen = !historyOpen
        if (historyOpen) Qt.callLater(function() { input.forceActiveFocus() })
    }
    Shortcut { sequence: "Ctrl+H"; enabled: !nexa.compact; onActivated: win.toggleHistory() }
    Shortcut { sequence: "Esc"; enabled: win.historyOpen && !nexa.compact; onActivated: win.historyOpen = false }
    function taskColor(st) {''')

rep('''    component DarkMenuItem: MenuItem {''', '''    // Vạch đo mảnh ở góc sân khấu: nhãn · giá trị, 12 đoạn tô theo mức tải
    component Meter: Item {
        id: mt
        property string label: ""
        property real v: -1                 // 0..1; âm = không có số liệu
        property string valueText: "—"
        implicitWidth: 132; implicitHeight: 30
        readonly property int segs: 12
        readonly property color col: v < 0 ? "#334155" : Theme.loadColor(v)
        property real shownV: v
        Behavior on shownV { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
        Text { anchors.left: parent.left; anchors.top: parent.top; text: mt.label; color: "#6f8fb0"
               font.pixelSize: 11; font.bold: true; font.letterSpacing: 2 }
        Text { anchors.right: parent.right; anchors.top: parent.top; text: mt.valueText; color: "#dbeafe"; font.pixelSize: 12 }
        Row {
            anchors.left: parent.left; anchors.bottom: parent.bottom
            spacing: 3
            Repeater {
                model: mt.segs
                Rectangle {
                    required property int index
                    width: (mt.width - (mt.segs - 1) * 3) / mt.segs; height: 5; radius: 1
                    color: index < Math.round(Math.max(0, mt.shownV) * mt.segs) ? mt.col : "#132540"
                }
            }
        }
    }

    component DarkMenuItem: MenuItem {''')

p.write_text(s, encoding="utf-8")
print("ok", len(s.splitlines()))
