"""Đóng gói NEXA thành thư mục chạy được bằng PyInstaller (one-folder).

  .venv\\Scripts\\python -m pip install -r requirements-dev.txt
  .venv\\Scripts\\python scripts\\build_exe.py

Kết quả: dist\\NEXA\\NEXA.exe (+ thư viện). KHÔNG đóng gói .env, config/settings.yaml, logs hay model
lớn; model được tải vào dist\\NEXA\\models ở lần chạy đầu (hoặc chép thư mục models\\ vào cạnh NEXA.exe).
Bản EXE phải được build và kiểm thử trên Windows; NEXA không coi ZIP mã nguồn là EXE đã kiểm chứng.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEP = ";"  # Windows
# module nạp động (import trong hàm) — PyInstaller không tự thấy
THREE_D_MODULES = [f"nexa.three_d.generation.templates.{t}" for t in
                   ("fasteners", "mechanical", "uav", "rover", "humanoid", "quadruped", "helicopter")] + \
    ["nexa.three_d.generation.tripo_provider", "nexa.three_d.generation.meshy_provider",
     "nexa.three_d.generation.hf_provider", "nexa.three_d.generation.dsl_designer", "nexa.three_d.tools",
     "nexa.three_d.intents", "nexa.three_d.service", "nexa.ui.three_d_bridge"]
# Sinh code (docs/code.md)
CODE_MODULES = [f"nexa.code.{m}" for m in ("models", "checks", "highlight", "generator", "service", "tools",
                                           "intents")] + ["nexa.ui.code_bridge"]


def main() -> int:
    # --dist <thư mục>: build ra chỗ khác (kiểm thử) để không ghi đè bản dist/NEXA đã giao
    dist = Path(sys.argv[sys.argv.index("--dist") + 1]) if "--dist" in sys.argv else ROOT / "dist"
    try:
        import importlib
        importlib.import_module("PyInstaller")
    except ImportError:
        print("Chưa có PyInstaller: .venv\\Scripts\\python -m pip install -r requirements-dev.txt")
        return 1
    datas = [
        (ROOT / "nexa" / "ui" / "qml", "nexa/ui/qml"),
        (ROOT / "assets", "assets"),
        (ROOT / "config" / "settings.example.yaml", "config"),
        (ROOT / "config" / "gestures.yaml", "config"),
        (ROOT / ".env.example", "."),
        (ROOT / "browser_bridge", "browser_bridge"),
    ]
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "NEXA", "--windowed",
            "--distpath", str(dist), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build")]
    for src, dst in datas:
        args += ["--add-data", f"{src}{SEP}{dst}"]
    for pkg in ("mediapipe", "faster_whisper", "ctranslate2", "winrt", "pywinauto", "comtypes", "edge_tts",
                "manifold3d", "fast_simplification", "gradio_client", "pygments", "pyflakes"):
        args += ["--collect-all", pkg]
    # Mô hình 3D: Qt Quick 3D (+ Helpers, AssetUtils/RuntimeLoader) và các module nạp động trong nexa.three_d
    for mod in ("win32com.client", "pythoncom", "pycaw.pycaw", "miniaudio", "send2trash", "mss",
                "PySide6.QtQuick3D", "scipy.interpolate", *THREE_D_MODULES, *CODE_MODULES):
        args += ["--hidden-import", mod]
    # cuBLAS (gói pip nvidia-cublas-cu12) để nhận dạng chạy trên GPU NVIDIA. Đặt ở <_internal>/nvidia/<gói>/bin —
    # đúng chỗ nexa.audio.stt._add_cuda_dll_dirs() tìm. Không có gói này thì bản EXE vẫn chạy, chỉ dùng CPU.
    site = Path(sys.prefix) / "Lib" / "site-packages"
    for dll in sorted(site.glob("nvidia/*/bin/*.dll")):
        args += ["--add-binary", f"{dll}{SEP}{dll.parent.relative_to(site).as_posix()}"]
    args.append(str(ROOT / "main.py"))
    print("Chạy:", " ".join(args[:8]), "…")
    code = subprocess.call(args, cwd=str(ROOT))
    if code != 0:
        return code
    out = dist / "NEXA"
    # Qt Quick 3D phải có đủ plugin QML (QtQuick3D, Helpers, AssetUtils/RuntimeLoader) — báo lỗi ngay nếu thiếu
    qml = out / "_internal" / "PySide6" / "qml" / "QtQuick3D"
    missing = [sub or "QtQuick3D" for sub in ("", "Helpers", "AssetUtils") if not (qml / sub / "qmldir").exists()]
    if missing:
        print("THIẾU plugin QML trong bản đóng gói:", ", ".join(missing))
        return 5
    # Tệp cấu hình mẫu cạnh exe (PROJECT_ROOT khi frozen = thư mục chứa exe).
    (out / "config").mkdir(exist_ok=True)
    for name in ("settings.example.yaml", "gestures.yaml"):
        shutil.copy2(ROOT / "config" / name, out / "config" / name)
    shutil.copy2(ROOT / ".env.example", out / ".env.example")
    for bad in (out / ".env", out / "config" / "settings.yaml"):
        if bad.exists():
            bad.unlink()
    print(f"Xong: {out / 'NEXA.exe'}")
    print("Lưu ý: bridge YouTube trong bản EXE vẫn cần Python để chạy native_host.py (xem browser_bridge/README.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
