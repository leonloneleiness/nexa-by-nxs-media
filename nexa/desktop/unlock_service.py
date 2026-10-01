"""Dịch vụ Windows chạy quyền LocalSystem: nhận lệnh mở khóa qua named pipe và spawn injector.

NEXA (tài khoản thường) không gõ phím vào secure desktop Winlogon được, nên nó gửi lệnh tới dịch
vụ này (SYSTEM). Với lệnh UNLOCK, dịch vụ nhân bản token của winlogon.exe trong console session và
CreateProcessAsUser một injector (chính NEXA.exe / python với sentinel --nexa-unlock-inject) trên
desktop "Winlogon\\Winlogon", nơi injector SendInput mã mở khóa.

Các hàm thuần (đóng khung/parse lệnh, xử lý một dòng lệnh) tách khỏi phần Win32 để test được không
cần cài dịch vụ. Xem nexa/desktop/unlock.py cho phía client và injector, và kế hoạch trong
C:\\Users\\ASUS\\.claude\\plans.
"""
from __future__ import annotations

import os
import sys

from nexa.utils.logging import get_logger
from nexa.desktop import unlock

log = get_logger("unlock-svc")

# Security descriptor cho pipe: cho phép Interactive Users (S-1-5-4) đọc/ghi, Owner = SYSTEM.
# D:(A;;GRGW;;;IU)(A;;GA;;;SY) — IU generic read+write, SYSTEM full.
PIPE_SDDL = "D:(A;;GRGW;;;IU)(A;;GA;;;SY)"


# ------------------------------------------------------------------ xử lý lệnh (thuần, test được)
def handle_command(text: str, *, do_unlock=None, do_set=None, do_clear=None, do_nolock=None) -> str:
    """Parse một khối lệnh (một hoặc nhiều dòng) và gọi callback tương ứng. Trả chuỗi phản hồi.

    Tách riêng phần Win32 (spawn injector, lưu file, powercfg) qua callback để unit-test không cần service.
    """
    lines = text.replace("\r\n", "\n").strip("\n").split("\n")
    if not lines or not lines[0]:
        return "ERR empty"
    cmd = lines[0].strip().upper()
    try:
        if cmd == unlock.CMD_PING:
            return "OK"
        if cmd == unlock.CMD_UNLOCK:
            ok = do_unlock() if do_unlock else False
            return "OK" if ok else "ERR unlock-failed"
        if cmd == unlock.CMD_SET:
            if len(lines) < 2:
                return "ERR no-password"
            (do_set or unlock.save_secret)(lines[1])
            return "OK"
        if cmd == unlock.CMD_CLEAR:
            (do_clear or unlock.clear_secret)()
            return "OK"
        if cmd in (unlock.CMD_NOLOCK_ON, unlock.CMD_NOLOCK_OFF):
            fn = do_nolock or set_console_lock
            ok = fn(cmd == unlock.CMD_NOLOCK_ON)
            return "OK" if ok else "ERR nolock-failed"
        return "ERR unknown-command"
    except Exception:
        log.exception("Lỗi xử lý lệnh %s", cmd)
        return "ERR exception"


# ------------------------------------------------------------------ tắt/bật "đòi mật khẩu khi thức dậy"
CONSOLELOCK_GUID = "0e796bdb-100d-47d6-a2d5-f7d2daa51f51"


def _consolelock_backup_path():
    return unlock.secret_path().parent / "consolelock_backup.json"


def _powercfg(args: list[str]) -> tuple[int, str]:
    import subprocess
    try:
        r = subprocess.run(["powercfg"] + args, capture_output=True, creationflags=0x08000000)
        return r.returncode, r.stdout.decode("mbcs", "replace")
    except Exception:
        log.exception("Gọi powercfg lỗi: %s", args)
        return 1, ""


def _consolelock_read() -> tuple[int | None, int | None]:
    """Đọc giá trị hiện tại (AC, DC) của 'đòi mật khẩu khi thức dậy'. None nếu không đọc được."""
    _powercfg(["/attributes", "SUB_NONE", CONSOLELOCK_GUID, "-ATTRIB_HIDE"])  # bỏ ẩn để đọc/ghi được
    _rc, out = _powercfg(["/q", "SCHEME_CURRENT", "SUB_NONE", CONSOLELOCK_GUID])
    ac = dc = None
    for line in out.splitlines():
        low = line.lower()
        try:
            if "ac power setting index" in low:
                ac = int(line.strip().split()[-1], 16)
            elif "dc power setting index" in low:
                dc = int(line.strip().split()[-1], 16)
        except ValueError:
            continue
    return ac, dc


def set_console_lock(disable: bool) -> bool:
    """disable=True → không đòi mật khẩu khi thức dậy (lưu giá trị gốc để trả lại). False → khôi phục."""
    import json
    backup = _consolelock_backup_path()
    if disable:
        # Lưu giá trị gốc một lần (nếu chưa có), để NOLOCK_OFF trả lại đúng.
        if not backup.exists():
            ac, dc = _consolelock_read()
            if ac is None and dc is None:
                ac = dc = 1  # mặc định Windows: có đòi mật khẩu
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(json.dumps({"ac": ac, "dc": dc}), encoding="utf-8")
            log.info("Đã lưu giá trị gốc đòi-mật-khẩu-khi-thức: ac=%s dc=%s", ac, dc)
        target_ac = target_dc = 0
    else:
        target_ac = target_dc = 1
        if backup.exists():
            try:
                data = json.loads(backup.read_text(encoding="utf-8"))
                target_ac = int(data.get("ac", 1))
                target_dc = int(data.get("dc", 1))
            except Exception:
                log.exception("Đọc backup consolelock lỗi — trả về mặc định 1")

    _powercfg(["/attributes", "SUB_NONE", CONSOLELOCK_GUID, "-ATTRIB_HIDE"])
    _powercfg(["/setacvalueindex", "SCHEME_CURRENT", "SUB_NONE", CONSOLELOCK_GUID, str(target_ac)])
    _powercfg(["/setdcvalueindex", "SCHEME_CURRENT", "SUB_NONE", CONSOLELOCK_GUID, str(target_dc)])
    rc, _ = _powercfg(["/setactive", "SCHEME_CURRENT"])
    if not disable and backup.exists():
        try:
            backup.unlink()
        except Exception:
            pass
    log.info("Đặt đòi-mật-khẩu-khi-thức: %s (ac=%s dc=%s)", "TẮT" if disable else "BẬT", target_ac, target_dc)
    return rc == 0


# ------------------------------------------------------------------ spawn injector vào Winlogon
def spawn_on_winlogon() -> bool:
    """Nhân bản token winlogon.exe của console session, chạy injector trên desktop Winlogon (SYSTEM)."""
    import win32api
    import win32con
    import win32event
    import win32process
    import win32profile
    import win32security
    import win32ts
    import pywintypes

    session_id = win32ts.WTSGetActiveConsoleSessionId()
    if session_id in (0xFFFFFFFF, None):
        log.error("Không có console session hoạt động")
        return False

    win_pid = _find_winlogon_pid(session_id)
    if not win_pid:
        log.error("Không tìm thấy winlogon.exe cho session %s", session_id)
        return False

    hproc = None
    htok = None
    hdup = None
    try:
        hproc = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, win_pid)
        htok = win32security.OpenProcessToken(
            hproc, win32con.TOKEN_DUPLICATE | win32con.TOKEN_QUERY | win32con.TOKEN_ASSIGN_PRIMARY)
        hdup = win32security.DuplicateTokenEx(
            htok, win32security.SecurityImpersonation, win32con.MAXIMUM_ALLOWED,
            win32security.TokenPrimary, None)

        exe, args = _injector_command()
        cmdline = _quote_command(exe, args)
        env = win32profile.CreateEnvironmentBlock(hdup, False)

        si = win32process.STARTUPINFO()
        si.dwFlags = 0
        si.lpDesktop = "Winlogon\\Winlogon"

        flags = win32con.CREATE_UNICODE_ENVIRONMENT | win32process.CREATE_NO_WINDOW
        hp, ht, pid, tid = win32process.CreateProcessAsUser(
            hdup, None, cmdline, None, None, False, flags, env, None, si)
        log.info("Đã spawn injector pid=%s trên desktop Winlogon", pid)
        # Chờ ngắn để bắt lỗi khởi động, nhưng không chặn lâu (injector còn ngủ chờ ô nhập).
        win32event.WaitForSingleObject(hp, 3000)
        try:
            win32api.CloseHandle(ht)
            win32api.CloseHandle(hp)
        except Exception:
            pass
        return True
    except pywintypes.error:
        log.exception("Spawn injector thất bại")
        return False
    finally:
        for h in (hdup, htok, hproc):
            try:
                if h:
                    win32api.CloseHandle(h)
            except Exception:
                pass


def _find_winlogon_pid(session_id: int) -> int | None:
    import win32api
    import win32con
    import win32process
    import win32security
    try:
        import psutil  # nếu có, nhanh và gọn
        for p in psutil.process_iter(["name", "pid"]):
            if (p.info["name"] or "").lower() == "winlogon.exe":
                try:
                    import win32ts
                    if win32ts.ProcessIdToSessionId(p.info["pid"]) == session_id:
                        return p.info["pid"]
                except Exception:
                    continue
    except Exception:
        pass
    # Dự phòng không cần psutil: quét bằng EnumProcesses.
    try:
        import win32ts
        for pid in win32process.EnumProcesses():
            try:
                if win32ts.ProcessIdToSessionId(pid) != session_id:
                    continue
                h = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                try:
                    name = win32process.GetModuleFileNameEx(h, 0)
                finally:
                    win32api.CloseHandle(h)
                if os.path.basename(name).lower() == "winlogon.exe":
                    return pid
            except Exception:
                continue
    except Exception:
        log.exception("Quét winlogon.exe thất bại")
    return None


def _injector_command() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        return sys.executable, ["--nexa-unlock-inject"]
    main = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else "main.py"
    return sys.executable, [main, "--nexa-unlock-inject"]


def _quote_command(exe: str, args: list[str]) -> str:
    parts = [f'"{exe}"'] + [f'"{a}"' if " " in a else a for a in args]
    return " ".join(parts)


# ------------------------------------------------------------------ vòng lặp pipe (SYSTEM)
def _serve_pipe(stop_event) -> None:
    """Vòng lặp: tạo pipe, chờ client, đọc một lệnh, phản hồi, lặp. Dừng khi stop_event bật."""
    import win32pipe
    import win32file
    import win32security
    import pywintypes

    sa = win32security.SECURITY_ATTRIBUTES()
    sa.SetSecurityDescriptorDacl(1, _pipe_dacl(), 0)

    while not _event_is_set(stop_event):
        try:
            handle = win32pipe.CreateNamedPipe(
                unlock.PIPE_NAME,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                1, 4096, 4096, 0, sa)
        except pywintypes.error:
            log.exception("Không tạo được pipe")
            return
        try:
            # ConnectNamedPipe chặn tới khi có client; poll stop_event bằng cách đóng khi dừng.
            try:
                win32pipe.ConnectNamedPipe(handle, None)
            except pywintypes.error:
                win32file.CloseHandle(handle)
                continue
            if _event_is_set(stop_event):
                win32file.CloseHandle(handle)
                return
            try:
                _hr, data = win32file.ReadFile(handle, 4096)
                text = data.decode("utf-8", "replace")
                first = text.replace("\r\n", "\n").split("\n", 1)[0].strip().upper()
                log.info("Nhận lệnh: %s", first or "(rỗng)")
                if not _client_is_console(handle):
                    reply = "ERR forbidden"
                    log.warning("Từ chối client không thuộc console session")
                else:
                    reply = handle_command(text, do_unlock=spawn_on_winlogon)
                log.info("Phản hồi: %s", reply)
                win32file.WriteFile(handle, reply.encode("utf-8"))
                win32file.FlushFileBuffers(handle)
            except pywintypes.error:
                log.exception("Lỗi giao tiếp pipe")
            finally:
                try:
                    win32pipe.DisconnectNamedPipe(handle)
                except Exception:
                    pass
                win32file.CloseHandle(handle)
        except Exception:
            log.exception("Vòng lặp pipe lỗi")


def _pipe_dacl():
    import win32security
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        PIPE_SDDL, win32security.SDDL_REVISION_1)
    return sd.GetSecurityDescriptorDacl()


def _client_is_console(handle) -> bool:
    """Chỉ chấp nhận client thuộc console session (chống tiến trình lạ ở session khác gọi mở khóa)."""
    try:
        import win32pipe
        import win32ts
        pid = win32pipe.GetNamedPipeClientProcessId(handle)
        return win32ts.ProcessIdToSessionId(pid) == win32ts.WTSGetActiveConsoleSessionId()
    except Exception:
        log.exception("Không xác thực được client pipe")
        return False


def _event_is_set(ev) -> bool:
    if ev is None:
        return False
    import win32event
    return win32event.WaitForSingleObject(ev, 0) == win32event.WAIT_OBJECT_0


# ------------------------------------------------------------------ khung dịch vụ Windows
def _build_service_class():
    """Tạo lớp dịch vụ lúc chạy để import module không bắt buộc có pywin32 (test trên mọi nền)."""
    import win32event
    import win32service
    import win32serviceutil
    import servicemanager
    import threading

    class NexaUnlockService(win32serviceutil.ServiceFramework):
        _svc_name_ = unlock.SERVICE_NAME
        _svc_display_name_ = unlock.SERVICE_DISPLAY
        _svc_description_ = "Gõ mã mở khóa Windows giúp NEXA khi vỗ tay (chạy quyền hệ thống)."

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 1, 0, None)
            self._thread = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ""))
            self._thread = threading.Thread(target=_serve_pipe, args=(self.stop_event,),
                                            name="nexa-unlock-pipe", daemon=True)
            self._thread.start()
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

    return NexaUnlockService


def service_main() -> None:
    """Điểm vào khi chạy dưới SCM (main.py --nexa-unlock-service)."""
    import servicemanager
    import win32serviceutil

    unlock.setup_service_logs()
    cls = _build_service_class()
    if len(sys.argv) == 1:
        # SCM khởi động: chạy dispatcher.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(cls)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(cls)
