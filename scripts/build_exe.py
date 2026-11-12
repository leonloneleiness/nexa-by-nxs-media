"""Đóng gói NEXA thành thư mục chạy được bằng PyInstaller (one-folder).

  .venv\\Scripts\\python -m pip install -r requirements-dev.txt
  .venv\\Scripts\\python scripts\\build_exe.py

Kết quả: dist\\NEXA\\NEXA.exe (+ toàn bộ thư viện). Đây là bản one-folder, không được phát hành
riêng NEXA.exe. Bước prepare_windows_release.py sẽ chép model, cấu hình dịch vụ và chạy preflight
cuối trước khi tạo installer. Bản EXE phải được build và kiểm thử trên Windows.
"""
from __future__ import annotations

import shutil
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEP = ";"  # Windows
# module nạp động (import trong hàm) — PyInstaller không tự thấy
THREE_D_MODULES = [f"nexa.three_d.generation.templates.{t}" for t in
                   sorted(p.stem for p in (ROOT / "nexa/three_d/generation/templates").glob("*.py")
                          if p.stem != "__init__")] + \
    ["nexa.three_d.generation.tripo_provider", "nexa.three_d.generation.meshy_provider",
     "nexa.three_d.generation.hf_provider", "nexa.three_d.generation.dsl_designer", "nexa.three_d.tools",
     "nexa.three_d.intents", "nexa.three_d.service", "nexa.ui.three_d_bridge"]
# Sinh code (docs/code.md)
CODE_MODULES = [f"nexa.code.{m}" for m in ("models", "checks", "highlight", "generator", "service", "tools",
                                           "intents")] + ["nexa.ui.code_bridge"]


def build_environment() -> dict[str, str]:
    """Do not resolve native dependencies from unrelated apps/tools on PATH.

    In particular Poppler's icuuc.dll has a different ABI from Windows ICU used
    by Qt. Collecting it silently breaks every Qt import in the frozen app.
    Wheel-specific DLL directories are collected by their PyInstaller hooks.
    """
    env = dict(os.environ)
    windows = Path(env.get("SystemRoot", r"C:\Windows"))
    env["PATH"] = os.pathsep.join(dict.fromkeys(str(p) for p in (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
        windows / "System32", windows)))
    env["PYTHONUTF8"] = "1"
    for key in ("PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(key, None)
    return env


def main() -> int:
    # Redirected Windows consoles may use cp1258, which cannot encode all
    # Vietnamese messages. Keep build logs readable instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
    # Freeze every application module, including modules loaded by name. Keep
    # the inventory inside the distribution so the EXE can verify all of them.
    modules = sorted({".".join(p.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
                      for p in (ROOT / "nexa").rglob("*.py")})
    manifest = ROOT / "build" / "module-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(modules, indent=2), encoding="utf-8")
    datas.append((manifest, "."))
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "NEXA", "--windowed",
            "--distpath", str(dist), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build")]
    icon = ROOT / "assets" / "branding" / "nexa-icon.ico"
    if icon.is_file():
        args += ["--icon", str(icon)]
    for src, dst in datas:
        args += ["--add-data", f"{src}{SEP}{dst}"]
    for pkg in ("mediapipe", "faster_whisper", "ctranslate2", "winrt", "pywinauto", "comtypes", "edge_tts",
                "manifold3d", "fast_simplification", "gradio_client", "pygments", "pyflakes"):
        args += ["--collect-all", pkg]
    from packaging.requirements import Requirement
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    for line in [*requirements, 'opencv-contrib-python']:
        line = line.strip()
        if line and not line.startswith('#'):
            args += ['--copy-metadata', Requirement(line).name]
    # Mô hình 3D: Qt Quick 3D (+ Helpers, AssetUtils/RuntimeLoader) và các module nạp động trong nexa.three_d
    for mod in ("win32com.client", "pythoncom", "pycaw.pycaw", "miniaudio", "send2trash", "mss",
                "PySide6.QtQuick3D", "scipy.interpolate", *modules, *THREE_D_MODULES, *CODE_MODULES):
        args += ["--hidden-import", mod]
    # cuBLAS (gói pip nvidia-cublas-cu12) để nhận dạng chạy trên GPU NVIDIA. Đặt ở <_internal>/nvidia/<gói>/bin —
    # đúng chỗ nexa.audio.stt._add_cuda_dll_dirs() tìm. Không có gói này thì bản EXE vẫn chạy, chỉ dùng CPU.
    site = Path(sys.prefix) / "Lib" / "site-packages"
    for dll in sorted(site.glob("nvidia/*/bin/*.dll")):
        args += ["--add-binary", f"{dll}{SEP}{dll.parent.relative_to(site).as_posix()}"]
    args.append(str(ROOT / "main.py"))
    native = ROOT / "nexa/native/nexa_geometry.dll"
    if native.is_file():
        args[-1:-1] = ["--add-binary", f"{native}{SEP}nexa/native"]
    print("Chạy:", " ".join(args[:8]), "…")
    code = subprocess.call(args, cwd=str(ROOT), env=build_environment())
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
    report = out / "installation-check.json"
    check = subprocess.run([str(out / "NEXA.exe"), "--nexa-check-install", str(report.resolve())],
                           timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                           env=build_environment())
    if check.returncode or not report.exists():
        print("Bản EXE chưa vượt kiểm tra module/template; xem", report)
        return 6
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("ok"):
        print("Lỗi kiểm tra EXE:", result.get("errors"))
        return 6
    for required in (out / "_internal", out / "_internal" / "assets", out / "config", out / ".env.example"):
        if not required.exists():
            print("Thiếu thành phần runtime:", required)
            return 7
    print(f"Xong: {out / 'NEXA.exe'}")
    print("Bước tiếp theo: đóng gói NexaBridge.exe và chạy prepare_windows_release.py để kèm model offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
