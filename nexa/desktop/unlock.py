"""Tự mở khóa Windows khi vỗ tay: phía user (client pipe + cài dịch vụ) và injector gõ phím.

Màn hình khóa là secure desktop của Winlogon; tiến trình quyền thường KHÔNG gõ phím vào đó được.
Vì vậy NEXA (chạy tài khoản thường) gửi lệnh qua named pipe tới một dịch vụ chạy quyền SYSTEM
(nexa/desktop/unlock_service.py). Dịch vụ đó spawn một "injector" cũng quyền SYSTEM nhưng vào đúng
console session, trên desktop Winlogon, để SendInput mã mở khóa.

Mã mở khóa được mã hóa DPAPI phạm vi máy, lưu ở %ProgramData%\\NEXA\\unlock.bin (SYSTEM ghi/đọc).
Mã KHÔNG bao giờ nằm trên dòng lệnh: chính injector (SYSTEM) tự đọc và giải mã file.

Kiến trúc và đánh đổi bảo mật: xem C:\\Users\\ASUS\\.claude\\plans (kế hoạch) và mục "Ngủ canh gác"
trong Cài đặt.
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from nexa.utils.logging import get_logger

log = get_logger("unlock")

SERVICE_NAME = "NexaUnlock"
SERVICE_DISPLAY = "NEXA Unlock Helper"
PIPE_NAME = r"\\.\pipe\nexa-unlock"
PIPE_TIMEOUT_MS = 3000

# Lệnh qua pipe: mỗi lệnh một dòng; SET kèm mã ở dòng thứ hai. Phản hồi: "OK" / "ERR ...".
CMD_PING = "PING"
CMD_UNLOCK = "UNLOCK"
CMD_SET = "SET"
CMD_CLEAR = "CLEAR"
CMD_NOLOCK_ON = "NOLOCK_ON"     # tắt yêu cầu mật khẩu khi thức dậy (khi NEXA canh gác)
CMD_NOLOCK_OFF = "NOLOCK_OFF"   # trả lại yêu cầu mật khẩu như cũ


def secret_path() -> Path:
    """%ProgramData%\\NEXA\\unlock.bin — SYSTEM và user cùng thấy (khác %LOCALAPPDATA% của mỗi tài khoản)."""
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(base) / "NEXA" / "unlock.bin"


def setup_service_logs() -> None:
    """Dịch vụ/injector chạy quyền SYSTEM (không qua nexa.app) nên tự bật ghi log vào %ProgramData%\\NEXA\\logs."""
    try:
        from nexa.utils.logging import setup_logging
        setup_logging(secret_path().parent / "logs")
    except Exception:
        pass


# ------------------------------------------------------------------ mã hóa (DPAPI phạm vi máy)
CRYPTPROTECT_LOCAL_MACHINE = 0x4  # win32crypt không phơi hằng này ra


def encrypt_secret(password: str) -> bytes:
    import win32crypt
    return win32crypt.CryptProtectData(password.encode("utf-8"), "nexa-unlock", None, None, None,
                                       CRYPTPROTECT_LOCAL_MACHINE)


def decrypt_secret(blob: bytes) -> str:
    import win32crypt
    _desc, data = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return data.decode("utf-8")


SECRET_SDDL = "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"


def _secret_security():
    import win32security
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        SECRET_SDDL, win32security.SDDL_REVISION_1)
    sa = win32security.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    return sd, sa


@contextmanager
def _secure_handle(path: Path, *, directory=False, create=False):
    """Open without following reparse points, then secure before any secret I/O.

    Secret files reject concurrent readers. Directory handles share read/write
    so children can be atomically replaced, but deny deletion to pin the parent.
    Never fall back to inherited ACLs or portable chmod on Windows.
    """
    import win32file
    import win32security
    sd, sa = _secret_security()
    h = win32file.CreateFile(
        str(path), 0xC00E0000, 3 if directory else 0, sa, 1 if create else 3,
        0x00200000 | (0x02000000 if directory else 0), None)
    try:
        info = win32file.GetFileInformationByHandle(h)
        if info[0] & 0x400 or bool(info[0] & 0x10) != directory:
            raise OSError("Unsafe unlock storage object")
        if not directory and info[7] != 1:
            raise OSError("Hard-linked unlock storage is forbidden")
        win32security.SetSecurityInfo(
            h, win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION |
            win32security.DACL_SECURITY_INFORMATION |
            win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            sd.GetSecurityDescriptorOwner(), None, sd.GetSecurityDescriptorDacl(), None)
        yield h
    finally:
        win32file.CloseHandle(h)


@contextmanager
def _secure_store():
    import win32file
    path = secret_path().absolute()
    # Do not traverse junctions/symlinks in the privileged storage path.
    for ancestor in reversed(path.parent.parents):
        if ancestor.lstat().st_file_attributes & 0x400:
            raise OSError("Reparse point in unlock storage path")
    _sd, sa = _secret_security()
    try:
        win32file.CreateDirectory(str(path.parent), sa)
    except Exception as exc:  # pywintypes.error is not an OSError subclass
        if getattr(exc, "winerror", None) != 183:
            raise
    with _secure_handle(path.parent, directory=True):
        yield path


def _secure_existing(path: Path) -> bool:
    try:
        with _secure_handle(path):
            pass
        return True
    except Exception as exc:
        if getattr(exc, "winerror", None) == 2:
            return False
        raise


def secure_secret_storage() -> None:
    """Privileged startup migration; repair legacy files without reading them."""
    with _secure_store() as path:
        _secure_existing(path)
        tmp = path.with_suffix(".tmp")
        if _secure_existing(tmp):
            tmp.unlink()


def save_secret(password: str) -> None:
    import win32file
    with _secure_store() as path:
        _secure_existing(path)
        tmp = path.with_suffix(".tmp")
        if _secure_existing(tmp):
            tmp.unlink()
        try:
            with _secure_handle(tmp, create=True) as handle:
                win32file.WriteFile(handle, encrypt_secret(password))
                win32file.FlushFileBuffers(handle)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    log.info("Đã lưu mã mở khóa (mã hóa DPAPI) tại %s", path)


def load_secret() -> str | None:
    try:
        import win32file
        with _secure_store() as path:
            with _secure_handle(path) as handle:
                size = win32file.GetFileSize(handle)
                if size > 65536:
                    raise ValueError("Oversized unlock secret")
                _status, blob = win32file.ReadFile(handle, size)
                return decrypt_secret(blob)
    except Exception as exc:
        if isinstance(exc, FileNotFoundError) or getattr(exc, "winerror", None) == 2:
            return None
        log.exception("Không giải mã được mã mở khóa")
        return None


def clear_secret() -> bool:
    try:
        with _secure_store() as path:
            for candidate in (path, path.with_suffix(".tmp")):
                if _secure_existing(candidate):
                    candidate.unlink()
        return True
    except Exception:
        log.exception("Không xóa được mã mở khóa")
        return False


# ------------------------------------------------------------------ injector: gõ phím vào Winlogon
# Cấu trúc INPUT cho SendInput (chỉ phần bàn phím).
import ctypes  # noqa: E402
from ctypes import wintypes  # noqa: E402

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_SHIFT = 0x10


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _vk_input(vk: int, up: bool) -> _INPUT:
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_INPUT._U(ki=_KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)))


def _unicode_input(ch: str, up: bool) -> _INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=INPUT_KEYBOARD, u=_INPUT._U(ki=_KEYBDINPUT(0, ord(ch), flags, 0, None)))


def char_inputs(text: str, enter: bool = True) -> list[_INPUT]:
    """Danh sách INPUT: từng ký tự (Unicode down+up) rồi Enter. Tách riêng để unit-test."""
    seq: list[_INPUT] = []
    for ch in text:
        seq.append(_unicode_input(ch, False))
        seq.append(_unicode_input(ch, True))
    if enter:
        seq.append(_vk_input(VK_RETURN, False))
        seq.append(_vk_input(VK_RETURN, True))
    return seq


def _send(inputs: list[_INPUT]) -> int:
    if not inputs:
        return 0
    arr = (_INPUT * len(inputs))(*inputs)
    return ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))


def _switch_to_input_desktop() -> bool:
    """Gắn luồng hiện tại vào desktop đang nhận đầu vào (Winlogon khi máy khóa)."""
    user32 = ctypes.windll.user32
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    h = user32.OpenInputDesktop(0, False, 0x0100 | 0x0001)  # SWITCHDESKTOP | READOBJECTS
    if not h:
        log.error("Không mở được input desktop (mã %d)", ctypes.get_last_error())
        return False
    try:
        return bool(user32.SetThreadDesktop(h))
    finally:
        pass  # để hệ điều hành đóng handle khi tiến trình injector thoát


def injector_main() -> int:
    """Chạy trong tiến trình SYSTEM do dịch vụ spawn vào console session. Gõ mã + Enter vào Winlogon."""
    setup_service_logs()
    try:
        ctypes.windll.kernel32.SetLastError(0)
        switched = _switch_to_input_desktop()
        log.info("Injector khởi động (chuyển desktop input: %s)", switched)
        password = load_secret()
        if not password:
            log.error("Không có mã mở khóa để gõ")
            return 2
        # Bỏ "màn che" của lock screen bằng một phím vô hại (Shift không sinh ký tự), rồi chờ ô nhập.
        _send([_vk_input(VK_SHIFT, False), _vk_input(VK_SHIFT, True)])
        time.sleep(1.2)
        _send(char_inputs(password))
        log.info("Injector đã gõ mã mở khóa")
        return 0
    except Exception:
        log.exception("Injector lỗi")
        return 1


# ------------------------------------------------------------------ phía user: client named pipe
def _pipe_request(lines: list[str]) -> str | None:
    """Gửi một lệnh tới dịch vụ, trả phản hồi (hoặc None nếu không kết nối được)."""
    import win32file
    import win32pipe
    import pywintypes
    try:
        win32pipe.WaitNamedPipe(PIPE_NAME, PIPE_TIMEOUT_MS)
        h = win32file.CreateFile(PIPE_NAME, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                 0, None, win32file.OPEN_EXISTING, 0, None)
    except pywintypes.error:
        return None
    try:
        win32file.WriteFile(h, ("\n".join(lines) + "\n").encode("utf-8"))
        _hr, data = win32file.ReadFile(h, 4096)
        return data.decode("utf-8", "replace").strip()
    except pywintypes.error:
        return None
    finally:
        win32file.CloseHandle(h)


def ping() -> bool:
    return _pipe_request([CMD_PING]) == "OK"


def request_unlock() -> bool:
    return (_pipe_request([CMD_UNLOCK]) or "").startswith("OK")


def set_no_lock(on: bool) -> bool:
    """Nhờ dịch vụ tắt/bật yêu cầu mật khẩu khi thức dậy. True = dịch vụ đã nhận và làm xong."""
    return (_pipe_request([CMD_NOLOCK_ON if on else CMD_NOLOCK_OFF]) or "").startswith("OK")


def set_password(password: str) -> bool:
    return (_pipe_request([CMD_SET, password]) or "").startswith("OK")


def clear_password() -> bool:
    # The ordinary client cannot inspect/delete the protected service files.
    return _pipe_request([CMD_CLEAR]) == "OK"


# ------------------------------------------------------------------ cài / gỡ dịch vụ (cần admin)
def _service_command() -> list[str]:
    """Lệnh để dịch vụ tự chạy: frozen → NEXA.exe --nexa-unlock-service; source → python main.py ...."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--nexa-unlock-service"]
    main = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else "main.py"
    return [sys.executable, main, "--nexa-unlock-service"]


def service_status() -> dict:
    """{'installed': bool, 'running': bool}. Không ném lỗi."""
    try:
        import win32service
        import win32serviceutil
        try:
            state = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
        except Exception:
            return {"installed": False, "running": False}
        return {"installed": True, "running": state == win32service.SERVICE_RUNNING}
    except Exception:
        log.exception("Không đọc được trạng thái dịch vụ")
        return {"installed": False, "running": False}


def install_service() -> bool:
    """Cài (hoặc cập nhật đường dẫn) rồi khởi động dịch vụ. Phải chạy với quyền admin."""
    import win32service
    import win32serviceutil
    exe_name, exe_args = _service_command()[0], " ".join(_service_command()[1:])
    try:
        try:
            win32serviceutil.QueryServiceStatus(SERVICE_NAME)
            exists = True
        except Exception:
            exists = False
        if exists:
            win32serviceutil.ChangeServiceConfig(None, SERVICE_NAME, exeName=exe_name, exeArgs=exe_args,
                                                 startType=win32service.SERVICE_AUTO_START,
                                                 displayName=SERVICE_DISPLAY)
        else:
            win32serviceutil.InstallService(None, SERVICE_NAME, SERVICE_DISPLAY,
                                            startType=win32service.SERVICE_AUTO_START,
                                            exeName=exe_name, exeArgs=exe_args)
        win32serviceutil.StartService(SERVICE_NAME)
        log.info("Đã cài và khởi động dịch vụ %s", SERVICE_NAME)
        return True
    except Exception:
        log.exception("Cài dịch vụ thất bại")
        return False


def uninstall_service() -> bool:
    import win32serviceutil
    try:
        try:
            win32serviceutil.StopService(SERVICE_NAME)
        except Exception:
            pass
        win32serviceutil.RemoveService(SERVICE_NAME)
        log.info("Đã gỡ dịch vụ %s", SERVICE_NAME)
        return True
    except Exception:
        log.exception("Gỡ dịch vụ thất bại")
        return False


def elevate_and_run(sentinel: str) -> bool:
    """Mở UAC để chạy chính NEXA với một sentinel cài/gỡ dịch vụ rồi thoát. True = đã bấm Có."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, sentinel
    else:
        main = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else "main.py"
        exe, params = sys.executable, f'"{main}" {sentinel}'
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 0)
    return rc > 32
