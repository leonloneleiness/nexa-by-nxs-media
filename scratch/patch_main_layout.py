from pathlib import Path

p = Path("nexa/ui/qml/Main.qml")
lines = p.read_text(encoding="utf-8").split("\n")
start = next(i for i, l in enumerate(lines) if l.strip() == "// Nội dung chính")
assert lines[start + 1].strip() == "RowLayout {"
# chat column ends at the "            }" right before the "        }" that closes the RowLayout (line before blank + emergency bar)
emerg = next(i for i, l in enumerate(lines) if "// Thanh dừng khẩn cấp" in l)
row_close = emerg - 2
assert lines[row_close] == "        }", repr(lines[row_close])
body_start = start + 5  # after RowLayout {, fillWidth, fillHeight, spacing
assert lines[start + 4].strip() == "spacing: 14", lines[start + 4]
assert lines[body_start] == "", repr(lines[body_start])
body = ["    " + l if l else l for l in lines[body_start + 1:row_close]]

grid_head = [
    "",
    "            // NEXA: 2 cột (quả cầu | hội thoại) hoặc xếp dọc khi trình xem 3D mở bên phải",
    "            GridLayout {",
    "                id: mainGrid",
    "                Layout.fillWidth: true",
    "                Layout.fillHeight: true",
    "                columns: win.viewerShown ? 1 : 2",
    "                columnSpacing: 14; rowSpacing: 10",
]
grid_tail = [
    "            }",
    "",
    "            // Mô hình 3D (tệp riêng; Loader để lỗi plugin Qt Quick 3D không ảnh hưởng giao diện chính)",
    "            Loader {",
    "                id: viewer3d",
    "                active: win.viewerShown",
    "                visible: active",
    "                focus: active",
    "                Layout.fillHeight: true",
    "                Layout.preferredWidth: Math.max(560, Math.min(win.width * 0.6, win.width - 520))",
    "                source: \"ModelViewer.qml\"",
    "                onStatusChanged: if (status === Loader.Error) toastBox.show(\"Không nạp được trình xem 3D (thiếu Qt Quick 3D?). Xem logs/nexa.log.\", true)",
    "            }",
]
lines[body_start:row_close] = grid_head + body + grid_tail
p.write_text("\n".join(lines), encoding="utf-8")
print("ok")
