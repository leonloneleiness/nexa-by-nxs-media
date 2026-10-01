"""Tạo tài liệu MỚI: Word / Excel / PowerPoint (qua COM của Office — hoặc WPS nếu WPS đăng ký thay) và file mới
trong VS Code.

COM là cách Office cho phép điều khiển chính thức: tạo đúng một tài liệu trắng, không phải bấm qua màn hình khởi động.
Có tên thì lưu luôn (mặc định vào thư mục Tài liệu); trùng tên thì thêm " (2)", " (3)"… — không bao giờ ghi đè.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger

log = get_logger("office")

# kind -> (ProgID, tên hiển thị, đuôi file, tiến trình)
OFFICE = {
    "word": ("Word.Application", "Word", ".docx", "winword.exe"),
    "excel": ("Excel.Application", "Excel", ".xlsx", "excel.exe"),
    "powerpoint": ("PowerPoint.Application", "PowerPoint", ".pptx", "powerpnt.exe"),
}
XL_OPENXML_WORKBOOK = 51
PP_LAYOUT_TITLE = 1


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    p = folder / f"{stem}{ext}"
    n = 2
    while p.exists():
        p = folder / f"{stem} ({n}){ext}"
        n += 1
    return p


def new_office_document(kind: str, name: str | None = None, folder: Path | None = None,
                        dispatch: Callable[[str], object] | None = None) -> ToolResult:
    if kind not in OFFICE:
        return ToolResult.failure(f"Không hỗ trợ loại tài liệu '{kind}'.", "bad_kind")
    progid, label, ext, _proc = OFFICE[kind]
    try:
        if dispatch is None:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            dispatch = win32com.client.Dispatch
        app = dispatch(progid)
        app.Visible = True
        if kind == "word":
            doc = app.Documents.Add()
        elif kind == "excel":
            doc = app.Workbooks.Add()
        else:
            doc = app.Presentations.Add()
            doc.Slides.Add(1, PP_LAYOUT_TITLE)
        saved = ""
        if name:
            folder = folder or Path.home() / "Documents"
            folder.mkdir(parents=True, exist_ok=True)
            path = unique_path(folder, Path(name).stem if Path(name).suffix.lower() == ext else name, ext)
            if kind == "word":
                doc.SaveAs2(str(path))
            elif kind == "excel":
                doc.SaveAs(str(path), XL_OPENXML_WORKBOOK)
            else:
                doc.SaveAs(str(path))
            saved = str(path)
        try:
            app.Activate() if kind != "powerpoint" else doc.Windows(1).Activate()
        except Exception:
            pass
    except Exception as exc:
        log.exception("Không tạo được tài liệu %s qua COM", label)
        return ToolResult.failure(f"Em không tạo được tài liệu {label} mới ({type(exc).__name__}). Máy có cài và kích "
                                  f"hoạt {label} chưa ạ?", "com_failed")
    if saved:
        return ToolResult.success(f"Đã tạo {label} mới và lưu thành {Path(saved).name}.", verified=True, path=saved)
    return ToolResult.success(f"Đã mở tài liệu {label} mới.", verified=True)


# ------------------------------------------------------------------ VS Code
def find_vscode() -> str:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft VS Code" / "Code.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft VS Code" / "Code.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("code") or ""


def vscode_workspaces() -> list[Path]:
    """Thư mục dự án VS Code đang/vừa mở (cửa sổ hoạt động gần nhất trước), đọc từ storage.json của VS Code.
    Dùng để "mở file main.py trong VS Code" ưu tiên đúng main.py của dự án thay vì main.py ở chỗ khác."""
    import json
    import urllib.parse
    storage = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "globalStorage" / "storage.json"
    try:
        data = json.loads(storage.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    state = data.get("windowsState") or {}
    uris = [w.get("folder") for w in [state.get("lastActiveWindow") or {}, *(state.get("openedWindows") or [])]]
    uris += [f.get("folderUri") for f in (data.get("backupWorkspaces") or {}).get("folders") or []]
    out: list[Path] = []
    for uri in uris:
        if not isinstance(uri, str) or not uri.startswith("file:///"):
            continue
        p = Path(urllib.parse.unquote(uri[len("file:///"):]))
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def open_in_vscode(path: str, exe: str | None = None) -> ToolResult:
    exe = exe or find_vscode()
    if not exe:
        return ToolResult.failure("Em không tìm thấy VS Code trên máy.", "not_found")
    try:
        # -r: mở trong cửa sổ VS Code đang có (không mở thêm cửa sổ mới).
        subprocess.Popen([exe, "-r", path], shell=False, close_fds=True)
    except OSError as exc:
        return ToolResult.failure(f"Không mở được VS Code: {exc}", "launch_failed")
    return ToolResult(ok=True, verified=False, message=f"Đã mở {Path(path).name} trong VS Code.", data={"path": path})


VSCODE_TITLE = re.compile(r"^(?P<dirty>●\s*)?(?P<file>[^\\/:*?\"<>|]+?)(?: \([^)]*\))?"
                          r"(?: - (?P<ws>.+?))?(?: \[[^\]]*\])* - Visual Studio Code")
_WALK_SKIP = {"node_modules", ".git", ".venv", "venv", "env", "__pycache__", "dist", "build", "out", "target", "bin",
              "obj", ".idea", ".vs", ".mypy_cache", ".pytest_cache", "site-packages"}


def _find_in(folder: Path, name: str, budget: int = 40_000) -> list[Path]:
    hits: list[Path] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d.lower() not in _WALK_SKIP and not d.startswith(".")]
        seen += len(filenames) + len(dirnames)
        if name in filenames:
            hits.append(Path(dirpath) / name)
        if seen > budget:
            break
    return hits


def vscode_active_file(api: object | None = None) -> tuple[Path | None, bool, str]:
    """Tệp đang mở ở cửa sổ VS Code gần nhất (đọc tiêu đề "● main.py - NEXA - Visual Studio Code").
    Trả (đường dẫn | None, chưa lưu?, lý do khi không tìm được). Tiêu đề chỉ có tên tệp nên tìm trong thư mục dự án
    trùng tên; nhiều tệp cùng tên thì lấy tệp vừa sửa gần nhất."""
    if api is None:
        from nexa.desktop.win32api import Win32Api
        api = Win32Api()
    title = ""
    for hwnd in api.enum_windows():                          # thứ tự Z: cửa sổ trên cùng trước
        if not api.is_visible(hwnd):
            continue
        t = api.get_title(hwnd)
        if t.endswith("Visual Studio Code"):
            title = t
            break
    if not title:
        return None, False, "Em không thấy cửa sổ VS Code nào đang mở."
    m = VSCODE_TITLE.match(title)
    if not m or m.group("file").strip() in ("Welcome", "Chào mừng", "Settings", "Extensions", "Keyboard Shortcuts"):
        return None, False, "VS Code đang không mở tệp code nào (anh mở tệp cần chạy rồi nói lại nhé)."
    name, ws, dirty = m.group("file").strip(), (m.group("ws") or "").strip(), bool(m.group("dirty"))
    if not ws and "." not in name:                            # "NEXA - Visual Studio Code": chỉ mở thư mục
        return None, False, "VS Code đang không mở tệp code nào (anh mở tệp cần chạy rồi nói lại nhé)."
    folders = vscode_workspaces()
    ordered = [f for f in folders if f.name.lower() == ws.lower()] + [f for f in folders if f.name.lower() != ws.lower()]
    for folder in ordered:
        hits = _find_in(folder, name)
        if hits:
            return max(hits, key=lambda p: p.stat().st_mtime if p.exists() else 0.0), dirty, ""
    return None, dirty, f"Em thấy VS Code đang mở {name} nhưng không tìm ra tệp đó trong thư mục dự án."
