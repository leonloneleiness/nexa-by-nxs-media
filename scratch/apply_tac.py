from pathlib import Path
p = Path("nexa/ui/qml/Main.qml")
lines = Path("scratch/Main.qml.bak4").read_text(encoding="utf-8").splitlines(keepends=True)
assert lines[295].strip() == "// ---------- nền ----------", lines[295]
assert lines[916].strip().startswith("// Mô hình 3D"), lines[916]
assert lines[914].rstrip() == "            }", repr(lines[914])
block = Path("scratch/tac_block.qml").read_text(encoding="utf-8")
comps = Path("scratch/tac_components.qml").read_text(encoding="utf-8")
s = "".join(lines[:295]) + block + "\n" + "".join(lines[916:])

def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:80])
    s = s.replace(old, new)

rep("import QtQuick.Window\n", "import QtQuick.Window\nimport QtQuick.Shapes\n")
rep('    color: "#040914"\n', '    color: "#02070f"\n')
rep("    component DarkMenuItem: MenuItem {", comps + "    component DarkMenuItem: MenuItem {")
rep("""    readonly property bool stacked: sideShown || narrow
""", """    readonly property bool stacked: sideShown || narrow
    // bố cục chiến thuật: bảng SYS bên trái và nhật ký LOG bên phải chỉ gắn cố định khi đủ rộng
    readonly property bool sysDocked: !stacked && width >= 1120
    readonly property bool logDocked: !nexa.compact && !sideShown && width >= 1200
""")
rep("""        historyOpen = !historyOpen
        if (historyOpen)""", """        if (logDocked) { input.forceActiveFocus(); return }
        historyOpen = !historyOpen
        if (historyOpen)""")
rep("""    Shortcut { sequence: "Esc"; enabled: win.historyOpen && !nexa.compact""",
    """    Shortcut { sequence: "Esc"; enabled: win.historyOpen && !win.logDocked && !nexa.compact""")
rep("""(st === "running" || st === "queued") ? win.cyan""", """(st === "running" || st === "queued") ? win.ice""")
# khối kiểu góc cạnh: bo góc nhỏ thay vì tròn
rep("""        background: Rectangle { radius: 6; color: "#0b1a33"; border.color: win.panelBorder }
    }
    component Chip""", """        background: Rectangle { radius: 2; color: "#081628"; border.color: Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.35) }
    }
    component Chip""")
rep("        radius: 16; implicitHeight: 32\n", "        radius: 3; implicitHeight: 32\n")
rep("        width: 32; height: 32; radius: 16\n", "        width: 30; height: 30; radius: 3\n")
rep("        width: 34; height: 34; radius: 10\n", "        width: 34; height: 34; radius: 3\n")
rep("""        border.color: hbMouse.containsMouse ? Qt.rgba(hoverTint.r, hoverTint.g, hoverTint.b, 0.7) : "#1e3352\"""",
    """        border.color: hbMouse.containsMouse ? Qt.rgba(hoverTint.r, hoverTint.g, hoverTint.b, 0.7) : Qt.rgba(win.ice.r, win.ice.g, win.ice.b, 0.2)""")
# Meter theo bảng màu băng/cam
rep("""        readonly property color col: v < 0 ? "#334155" : Theme.loadColor(v)""", """        readonly property color col: win.tacLoad(v)""")
rep("""        Text { anchors.left: parent.left; anchors.top: parent.top; text: mt.label; color: "#6f8fb0"
               font.pixelSize: 11; font.bold: true; font.letterSpacing: 2 }
        Text { anchors.right: parent.right; anchors.top: parent.top; text: mt.valueText; color: "#dbeafe"; font.pixelSize: 12 }""",
    """        Text { anchors.left: parent.left; anchors.top: parent.top; text: mt.label; color: win.iceDim
               font.family: win.tacFont; font.pixelSize: 11; font.letterSpacing: 3 }
        Text { anchors.right: parent.right; anchors.top: parent.top; text: mt.valueText; color: "#e6f4ff"
               font.family: win.monoFont; font.pixelSize: 12 }""")
rep("""                    width: (mt.width - (mt.segs - 1) * 3) / mt.segs; height: 5; radius: 1
                    color: index < Math.round(Math.max(0, mt.shownV) * mt.segs) ? mt.col : "#132540\"""",
    """                    width: (mt.width - (mt.segs - 1) * 3) / mt.segs; height: 5
                    color: index < Math.round(Math.max(0, mt.shownV) * mt.segs) ? mt.col : "#10233a\"""")
rep("""        background: Rectangle { radius: 6; color: dmi.highlighted ? "#14305a" : "transparent" }""",
    """        background: Rectangle { radius: 2; color: dmi.highlighted ? "#13283f" : "transparent" }""")
p.write_text(s, encoding="utf-8")
print("ok", len(s.splitlines()))
