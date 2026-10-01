from pathlib import Path
p = Path("nexa/ui/qml/ModelViewer.qml")
s = p.read_text(encoding="utf-8")
lines = s.split("\n")
a = next(i for i, l in enumerate(lines) if l.strip() == "// ---------- thanh trên ----------")
b = next(i for i, l in enumerate(lines) if 'VBtn { text: "✕ Đóng"' in l) + 2
assert lines[b] == "    }", repr(lines[b])
old = lines[a:b + 1]
comp = [l[4:] for l in old[23:30]]   # component VBtn … }
assert comp[0].strip().startswith("component VBtn"), comp[0]
title = [l for l in old[7:22]]      # Column … badge Rectangle
btns = old[30:42]
new = ["    component VBtn: Button {"] + ["    " + l.strip() if False else l for l in comp[1:]]
new = [comp[0]] + comp[1:]
new += ["", "    // ---------- thanh trên (tự xuống dòng khi trình xem hẹp — đang mở song song với NEXA) ----------",
        "    Rectangle {", "        id: topBar",
        "        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top",
        "        height: barFlow.implicitHeight + 16",
        "        color: \"#cc050b18\"",
        "        Flow {", "            id: barFlow",
        "            anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter",
        "            anchors.leftMargin: 14; anchors.rightMargin: 10; spacing: 8"]
new += title
new += [l.replace("Layout.preferredWidth: 280", "width: 280") for l in []]
new += btns
new += ["        }", "    }"]
lines[a:b + 1] = new
out = "\n".join(lines).replace("                Layout.preferredWidth: 280\n", "                width: 280\n")
p.write_text(out, encoding="utf-8")
print("ok")
