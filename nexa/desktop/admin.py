"""Quản trị hệ thống: quyền Administrator, tiến trình nặng, tắt ứng dụng treo, ổ đĩa, mạng, công cụ quản trị.

Quyền Administrator: NEXA chỉ tự khởi động lại qua hộp thoại UAC của Windows (anh bấm "Có"). Không tắt UAC, không sửa
cài đặt bảo mật để bỏ qua bước xác nhận đó. Khi chạy quyền admin, NEXA điều khiển được cả cửa sổ đang chạy quyền admin
(Windows chặn ứng dụng thường gửi phím/chuột tới chúng — UIPI).
Tắt tiến trình: đóng lịch sự (WM_CLOSE) trước, chỉ buộc dừng khi được yêu cầu; tiến trình hệ thống thiết yếu bị chặn.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time
from typing import Any

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger
from nexa.utils.text import fold

log = get_logger("admin")

# Tắt các tiến trình này làm Windows treo/đăng xuất/màn hình xanh.
PROTECTED = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
             "services.exe", "lsass.exe", "lsaiso.exe", "svchost.exe", "dwm.exe", "fontdrvhost.exe", "sihost.exe",
             "memory compression", "secure system", "spoolsv.exe", "audiodg.exe", "ctfmon.exe", "msmpeng.exe",
             "securityhealthservice.exe", "taskhostw.exe", "runtimebroker.exe", "startmenuexperiencehost.exe"}

ADMIN_TOOLS = {  # tên gọi (fold) -> lệnh
    "task manager": "taskmgr.exe", "trinh quan ly tac vu": "taskmgr.exe", "quan ly tac vu": "taskmgr.exe",
    "device manager": "devmgmt.msc", "trinh quan ly thiet bi": "devmgmt.msc", "quan ly thiet bi": "devmgmt.msc",
    "services": "services.msc", "dich vu": "services.msc", "dich vu windows": "services.msc",
    "event viewer": "eventvwr.msc", "nhat ky su kien": "eventvwr.msc",
    "disk management": "diskmgmt.msc", "quan ly o dia": "diskmgmt.msc",
    "control panel": "control.exe", "bang dieu khien": "control.exe",
    "disk cleanup": "cleanmgr.exe", "don dep o dia": "cleanmgr.exe",
    "system information": "msinfo32.exe", "thong tin he thong": "msinfo32.exe",
    "registry": "regedit.exe", "registry editor": "regedit.exe", "trinh sua registry": "regedit.exe",
    "computer management": "compmgmt.msc", "quan ly may tinh": "compmgmt.msc",
    "firewall": "wf.msc", "tuong lua": "wf.msc",
    "startup": "ms-settings:startupapps", "ung dung khoi dong": "ms-settings:startupapps",
    "windows update": "ms-settings:windowsupdate", "cap nhat windows": "ms-settings:windowsupdate",
}


# ------------------------------------------------------------------ quyền admin
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _self_command() -> tuple[str, str]:
    if getattr(sys, "frozen", False):
        return sys.executable, " ".join(f'"{a}"' for a in sys.argv[1:])
    main = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    return sys.executable, " ".join(f'"{a}"' for a in [main, *sys.argv[1:]] if a)


def relaunch_as_admin() -> ToolResult:
    """Hiện hộp thoại UAC để mở một NEXA mới quyền admin. True = anh đã đồng ý (NEXA cũ nên thoát)."""
    if is_admin():
        return ToolResult.success("NEXA đang chạy với quyền quản trị rồi ạ.", verified=True, no_op=True)
    exe, params = _self_command()
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 1)
    if rc <= 32:
        return ToolResult.failure("Anh chưa đồng ý trên hộp thoại quyền quản trị nên NEXA vẫn chạy quyền thường.",
                                  "uac_declined")
    return ToolResult.success("Đang mở NEXA với quyền quản trị — cửa sổ hiện tại sẽ tự đóng.", verified=True,
                              relaunched=True)


def open_admin_shell(kind: str = "powershell") -> ToolResult:
    exe = {"powershell": "powershell.exe", "cmd": "cmd.exe", "terminal": "wt.exe"}.get(kind, "powershell.exe")
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, None, None, 1)
    if rc <= 32:
        return ToolResult.failure("Anh chưa đồng ý trên hộp thoại quyền quản trị.", "uac_declined")
    return ToolResult.success(f"Đã mở {exe.split('.')[0]} với quyền quản trị.", verified=True)


def open_admin_tool(name: str) -> ToolResult:
    key = re.sub(r"\s+", " ", fold(name)).strip()
    cmd = ADMIN_TOOLS.get(key)
    if cmd is None:
        return ToolResult.failure(f"Em chưa biết công cụ quản trị '{name}'.", "unknown_tool")
    try:
        os.startfile(cmd)  # noqa: S606 - lệnh cố định trong ADMIN_TOOLS, không nhận đường dẫn tùy ý
    except OSError as exc:
        return ToolResult.failure(f"Không mở được {name}: {exc}", "launch_failed")
    return ToolResult(ok=True, verified=False, message=f"Đã mở {name}.", data={"command": cmd})


# ------------------------------------------------------------------ tiến trình
def top_processes(n: int = 5, sample_s: float = 0.6, by: str = "both") -> ToolResult:
    import psutil
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            p.cpu_percent(None)
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(sample_s)
    cores = psutil.cpu_count() or 1
    groups: dict[str, dict[str, float]] = {}
    for p in procs:
        try:
            name = p.info["name"] or "?"
            if name.lower() in ("system idle process",):
                continue
            g = groups.setdefault(name, {"cpu": 0.0, "ram": 0.0, "count": 0})
            g["cpu"] += p.cpu_percent(None) / cores
            g["ram"] += (p.info["memory_info"].rss if p.info["memory_info"] else 0) / 2**20
            g["count"] += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    by_cpu = sorted(groups.items(), key=lambda kv: kv[1]["cpu"], reverse=True)[:n]
    by_ram = sorted(groups.items(), key=lambda kv: kv[1]["ram"], reverse=True)[:n]

    def label(name: str) -> str:
        return name[:-4] if name.lower().endswith(".exe") else name
    def gb(mb: float) -> str:
        return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"
    cpu_txt = ", ".join(f"{label(k)} {v['cpu']:.0f}%" for k, v in by_cpu)
    ram_txt = ", ".join(f"{label(k)} {gb(v['ram'])}" for k, v in by_ram)
    cpu_sentence = f"Ngốn CPU nhiều nhất là {cpu_txt}."
    ram_sentence = f"Ngốn RAM nhiều nhất là {ram_txt}."
    # Hỏi CPU thì câu đầu nói CPU, hỏi RAM thì câu đầu nói RAM (loa chỉ đọc câu đầu).
    order = {"cpu": [cpu_sentence, ram_sentence], "ram": [ram_sentence, cpu_sentence]}.get(
        by, [f"Ngốn CPU nhiều nhất là {label(by_cpu[0][0])}, ngốn RAM nhiều nhất là {label(by_ram[0][0])}.",
             cpu_sentence, ram_sentence])
    return ToolResult.success(" ".join(order), verified=True,
                              cpu=[{"name": k, **v} for k, v in by_cpu], ram=[{"name": k, **v} for k, v in by_ram])


def find_processes(name: str) -> list:
    import psutil
    q = fold(name).replace(".exe", "").strip()
    if not q:
        return []
    out = []
    for p in psutil.process_iter(["name", "pid"]):
        try:
            pname = fold(p.info["name"] or "").replace(".exe", "")
            if pname == q or (len(q) >= 3 and q in pname):
                out.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def end_process(name: str, force: bool = False, wm: Any = None, wait_s: float = 3.0) -> ToolResult:
    import psutil
    procs = find_processes(name)
    if not procs:
        return ToolResult.failure(f"Không thấy tiến trình nào tên '{name}' đang chạy.", "not_found")
    names = {(p.info["name"] or "").lower() for p in procs}
    blocked = names & PROTECTED
    if blocked:
        return ToolResult.failure(f"Em không tắt {', '.join(sorted(blocked))} vì đó là tiến trình hệ thống thiết yếu — "
                                  "tắt đi Windows có thể treo hoặc tự khởi động lại.", "protected")
    me = os.getpid()
    procs = [p for p in procs if p.pid != me]
    pids = {p.pid for p in procs}
    # 1) Đóng lịch sự các cửa sổ của tiến trình (ứng dụng còn kịp hỏi lưu).
    if wm is not None and not force:
        for w in wm.list_windows(limit=100):
            ident = wm.identity(w["hwnd"])
            if ident is not None and getattr(ident, "pid", None) in pids:
                wm.close(w["hwnd"])
        _gone, procs = psutil.wait_procs(procs, timeout=wait_s)
        if not procs:
            return ToolResult.success(f"Đã đóng {name}.", verified=True)
    if not force and wm is not None:
        return ToolResult(ok=True, verified=False, data={"remaining": len(procs)},
                          message=f"{name} vẫn đang chạy (có thể đang hỏi lưu hoặc bị treo). Anh nói "
                                  f"'buộc tắt {name}' nếu muốn dừng hẳn.")
    # 2) Buộc dừng.
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _gone, alive = psutil.wait_procs(procs, timeout=wait_s)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _gone, alive = psutil.wait_procs(alive, timeout=1.5)
    if alive:
        hint = "" if is_admin() else " Có thể cần chạy NEXA với quyền quản trị."
        return ToolResult.failure(f"Còn {len(alive)} tiến trình {name} không dừng được.{hint}", "access_denied")
    return ToolResult.success(f"Đã buộc tắt {name}.", verified=True)


# ------------------------------------------------------------------ ổ đĩa / mạng
def disk_usage() -> ToolResult:
    import psutil
    parts = []
    data = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        drive = part.mountpoint.rstrip("\\").rstrip(":")   # "ổ C" (không có ": " — phần đọc to cắt sau ": ")
        parts.append(f"ổ {drive} còn trống {u.free / 2**30:.0f} GB trên {u.total / 2**30:.0f} GB")
        data.append({"drive": drive, "free_gb": round(u.free / 2**30, 1), "total_gb": round(u.total / 2**30, 1),
                     "percent": u.percent})
    if not parts:
        return ToolResult.failure("Không đọc được thông tin ổ đĩa.", "no_disks")
    head = f"Ổ {data[0]['drive']} còn trống {data[0]['free_gb']:.0f} GB trên {data[0]['total_gb']:.0f} GB."
    rest = (" Các ổ khác: " + "; ".join(parts[1:]) + ".") if len(parts) > 1 else ""
    return ToolResult.success(head + rest, verified=True, disks=data)


def network_info() -> ToolResult:
    import socket
    import psutil
    ssid = ""
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        text = out.decode("utf-8", errors="ignore") if isinstance(out, bytes) else out
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", text, re.MULTILINE)
        ssid = m.group(1).strip() if m else ""
    except Exception:
        pass
    ips = []
    stats = psutil.net_if_stats()
    for iface, addrs in psutil.net_if_addrs().items():
        if not stats.get(iface) or not stats[iface].isup or "loopback" in iface.lower():
            continue
        for a in addrs:
            if a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254.")):
                ips.append((iface, a.address))
    online = False
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        online = True
    except OSError:
        pass
    # Câu đầu (loa đọc) không chứa dãy số IP — đọc to rất lâu; IP để ở câu sau, hiện trên màn hình.
    where = f"qua Wi-Fi {ssid}" if ssid else "qua mạng dây" if ips else ""
    head = (f"Máy đang có Internet {where}." if online else "Máy KHÔNG vào được Internet.").replace("  ", " ")
    detail = (" Địa chỉ IP: " + ", ".join(ip for _, ip in ips) + ".") if ips else " Máy chưa có địa chỉ IP."
    return ToolResult.success(head + detail, verified=True, ssid=ssid, ips=ips, online=online)
