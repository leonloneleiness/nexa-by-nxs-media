from pathlib import Path

p = Path("nexa/ui/qml/Main.qml")
s = p.read_text(encoding="utf-8")
new = Path("scratch/main_new_section.qml").read_text(encoding="utf-8")
a = s.index("    // ---------- thành phần tái sử dụng ----------")
b = s.index("            // Mô hình 3D (tệp riêng; Loader")
s = s[:a] + new + "\n" + s[b:]
a = s.index("        // Thanh dừng khẩn cấp — luôn hiển thị")
b = s.index("    // ---------- Bảng cử chỉ ----------")
s = s[:a].rstrip() + "\n    }\n\n" + s[b:]
s = s.replace("import QtQuick.Window\n", 'import QtQuick.Window\nimport "Theme.js" as Theme\n', 1)
s = s.replace("anchors.margins: 14; anchors.topMargin: 70; anchors.bottomMargin: 60", "anchors.margins: 14; anchors.topMargin: 64; anchors.bottomMargin: 14")
p.write_text(s, encoding="utf-8")
print("ok")
