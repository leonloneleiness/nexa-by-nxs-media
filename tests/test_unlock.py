"""Tự mở khóa khi vỗ tay: dispatch lệnh pipe, dựng chuỗi phím, lưu/giải mã mã, và controller.

Không dùng mã thật của anh Sơn ở bất cứ đâu — chỉ token thử vô hại. Các test chạy được trên mọi nền
(phần Win32 được mock); vài test round-trip DPAPI thật thì skip nếu không phải Windows.
"""
from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from nexa.desktop import unlock
from nexa.desktop import unlock_service

TOKEN = "13579"  # token thử, KHÔNG phải mã mở khóa thật


# ------------------------------------------------------------------ dispatch lệnh pipe
def test_handle_ping():
    assert unlock_service.handle_command("PING\n") == "OK"


def test_handle_unlock_calls_spawn():
    calls = []
    r = unlock_service.handle_command("UNLOCK\n", do_unlock=lambda: (calls.append(1), True)[1])
    assert r == "OK" and calls == [1]


def test_handle_unlock_failure():
    assert unlock_service.handle_command("UNLOCK", do_unlock=lambda: False) == "ERR unlock-failed"


def test_handle_set_passes_second_line():
    got = []
    r = unlock_service.handle_command(f"SET\n{TOKEN}\n", do_set=got.append)
    assert r == "OK" and got == [TOKEN]


def test_handle_set_without_password():
    assert unlock_service.handle_command("SET\n", do_set=lambda p: None) == "ERR no-password"


def test_handle_clear_calls_back():
    calls = []
    r = unlock_service.handle_command("CLEAR", do_clear=lambda: (calls.append(1), True)[1])
    assert r == "OK" and calls == [1]


def test_handle_unknown_and_empty():
    assert unlock_service.handle_command("NOPE") == "ERR unknown-command"
    assert unlock_service.handle_command("") == "ERR empty"
    assert unlock_service.handle_command("\n\n") == "ERR empty"


def test_handle_is_case_insensitive():
    assert unlock_service.handle_command("ping") == "OK"


def test_handle_nolock_on_off_dispatch():
    got = []
    r_on = unlock_service.handle_command("NOLOCK_ON", do_nolock=lambda d: (got.append(d), True)[1])
    r_off = unlock_service.handle_command("NOLOCK_OFF", do_nolock=lambda d: (got.append(d), True)[1])
    assert r_on == "OK" and r_off == "OK"
    assert got == [True, False]


def test_handle_nolock_failure():
    assert unlock_service.handle_command("NOLOCK_ON", do_nolock=lambda d: False) == "ERR nolock-failed"


# ------------------------------------------------------------------ dựng chuỗi phím
def test_char_inputs_shape():
    seq = unlock.char_inputs(TOKEN)
    # mỗi ký tự: down + up; cộng Enter down + up
    assert len(seq) == len(TOKEN) * 2 + 2


def test_char_inputs_unicode_codepoints():
    seq = unlock.char_inputs("A", enter=False)
    down, up = seq
    assert down.ki.wScan == ord("A")
    assert down.ki.dwFlags & unlock.KEYEVENTF_UNICODE
    assert not (down.ki.dwFlags & unlock.KEYEVENTF_KEYUP)
    assert up.ki.dwFlags & unlock.KEYEVENTF_KEYUP


def test_char_inputs_ends_with_enter():
    seq = unlock.char_inputs("A")
    enter_down, enter_up = seq[-2], seq[-1]
    assert enter_down.ki.wVk == unlock.VK_RETURN
    assert not (enter_down.ki.dwFlags & unlock.KEYEVENTF_KEYUP)
    assert enter_up.ki.wVk == unlock.VK_RETURN
    assert enter_up.ki.dwFlags & unlock.KEYEVENTF_KEYUP


def test_char_inputs_empty_no_enter():
    assert unlock.char_inputs("", enter=False) == []


# ------------------------------------------------------------------ lưu / giải mã (mock DPAPI)
@pytest.fixture
def fake_storage(monkeypatch):
    """Never apply production ACLs to pytest's directory or touch real secrets."""
    @contextmanager
    def store():
        yield unlock.secret_path()

    @contextmanager
    def handle(path, **kwargs):
        try:
            with path.open("xb+" if kwargs.get("create") else "rb+") as stream:
                yield stream
        except FileNotFoundError as exc:
            exc.winerror = 2
            raise

    monkeypatch.setattr(unlock, "_secure_store", store)
    monkeypatch.setattr(unlock, "_secure_handle", handle)
    monkeypatch.setitem(sys.modules, "win32file", SimpleNamespace(
        WriteFile=lambda h, data: h.write(data), FlushFileBuffers=lambda h: h.flush(),
        ReadFile=lambda h, size: (0, h.read(size)),
        GetFileSize=lambda h: os.fstat(h.fileno()).st_size))


def test_save_load_roundtrip_with_fake_dpapi(tmp_path, monkeypatch, fake_storage):
    monkeypatch.setattr(unlock, "secret_path", lambda: tmp_path / "unlock.bin")
    # "mã hóa" giả: đảo byte, đủ để kiểm luồng ghi/đọc/xóa mà không cần Windows.
    monkeypatch.setattr(unlock, "encrypt_secret", lambda pw: pw.encode("utf-8")[::-1])
    monkeypatch.setattr(unlock, "decrypt_secret", lambda blob: bytes(blob)[::-1].decode("utf-8"))
    assert unlock.load_secret() is None
    unlock.save_secret(TOKEN)
    assert (tmp_path / "unlock.bin").exists()
    assert unlock.load_secret() == TOKEN
    assert unlock.clear_secret() is True
    assert unlock.load_secret() is None


def test_load_secret_swallows_bad_blob(tmp_path, monkeypatch, fake_storage):
    p = tmp_path / "unlock.bin"
    p.write_bytes(b"garbage")
    monkeypatch.setattr(unlock, "secret_path", lambda: p)

    def boom(_blob):
        raise ValueError("cannot decrypt")

    monkeypatch.setattr(unlock, "decrypt_secret", boom)
    assert unlock.load_secret() is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI chỉ có trên Windows")
def test_dpapi_roundtrip_real(tmp_path, monkeypatch, fake_storage):
    monkeypatch.setattr(unlock, "secret_path", lambda: tmp_path / "unlock.bin")
    unlock.save_secret(TOKEN)
    assert unlock.load_secret() == TOKEN
    unlock.clear_secret()


@pytest.mark.skipif(sys.platform != "win32", reason="dịch vụ Windows")
def test_service_status_no_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "win32service", SimpleNamespace(SERVICE_RUNNING=4))
    monkeypatch.setitem(sys.modules, "win32serviceutil", SimpleNamespace(
        QueryServiceStatus=lambda name: (0, 4)))
    st = unlock.service_status()
    assert set(st) >= {"installed", "running"}


# ------------------------------------------------------------------ controller._wait_for_unlock
def _fake_controller(monkeypatch, *, auto_unlock, ping, request_ok, locked_after):
    """Dựng controller tối thiểu để chạy _wait_for_unlock đồng bộ (thread join)."""
    from nexa.core import controller as ctrl_mod

    calls = SimpleNamespace(pinged=0, requested=0, spoke=[])

    monkeypatch.setattr(unlock, "ping", lambda: (setattr(calls, "pinged", calls.pinged + 1), ping)[1])

    def req():
        calls.requested += 1
        return request_ok

    monkeypatch.setattr(unlock, "request_unlock", req)

    # session_locked: khóa cho tới khi locked_after lần gọi thì mở
    state = {"n": 0}

    def session_locked():
        state["n"] += 1
        return not (state["n"] >= locked_after)

    monkeypatch.setattr("nexa.desktop.sleep_guard.session_locked", session_locked)

    c = SimpleNamespace()
    c._unlock_waiter = None
    c._running = True
    c.config = SimpleNamespace(get=lambda k, d=None: auto_unlock if k == "power.auto_unlock" else d)
    c.tts = SimpleNamespace(chain=lambda: True, speak=lambda t: calls.spoke.append(t))
    c.notify = lambda *a, **k: None
    c.sm = SimpleNamespace(state=None)
    c.wake = lambda *a, **k: None
    c._away_greeting = lambda: "chào"
    c._wait_for_unlock = ctrl_mod.Controller._wait_for_unlock.__get__(c)
    return c, calls


def test_wait_for_unlock_uses_service_when_enabled(monkeypatch):
    c, calls = _fake_controller(monkeypatch, auto_unlock=True, ping=True, request_ok=True, locked_after=1)
    c._wait_for_unlock(prompt=True)
    c._unlock_waiter.join(timeout=5)
    assert calls.pinged >= 1
    assert calls.requested == 1
    assert calls.spoke == []  # không nhắc anh vì dịch vụ chạy


def test_wait_for_unlock_prompts_when_service_down(monkeypatch):
    c, calls = _fake_controller(monkeypatch, auto_unlock=True, ping=False, request_ok=False, locked_after=1)
    c._wait_for_unlock(prompt=True)
    c._unlock_waiter.join(timeout=5)
    assert calls.requested == 0  # không gọi mở khóa vì ping hỏng
    assert any("mở khóa" in s for s in calls.spoke)


def test_wait_for_unlock_prompts_when_auto_off(monkeypatch):
    c, calls = _fake_controller(monkeypatch, auto_unlock=False, ping=True, request_ok=True, locked_after=1)
    c._wait_for_unlock(prompt=True)
    c._unlock_waiter.join(timeout=5)
    assert calls.pinged == 0  # không đụng dịch vụ khi tắt tính năng
    assert calls.requested == 0
    assert any("mở khóa" in s for s in calls.spoke)


def test_quote_command_wraps_paths():
    q = unlock_service._quote_command(r"C:\Program Files\NEXA\NEXA.exe", ["--nexa-unlock-inject"])
    assert q.startswith('"C:\\Program Files\\NEXA\\NEXA.exe"')
    assert "--nexa-unlock-inject" in q


@pytest.mark.parametrize("reply,expected", [("OK", True), ("ERR clear-failed", False), (None, False)])
def test_clear_password_trusts_service_result(monkeypatch, reply, expected):
    monkeypatch.setattr(unlock, "_pipe_request", lambda lines: reply)
    monkeypatch.setattr(unlock, "clear_secret", lambda: pytest.fail("client must not delete files"))
    assert unlock.clear_password() is expected


def test_clear_failure_is_reported():
    assert unlock_service.handle_command("CLEAR", do_clear=lambda: False) == "ERR clear-failed"


def test_migration_secures_both_files_without_reading(tmp_path, monkeypatch, fake_storage):
    path = tmp_path / "unlock.bin"
    stale = path.with_suffix(".tmp")
    path.write_bytes(b"legacy")
    stale.write_bytes(b"stale")
    monkeypatch.setattr(unlock, "secret_path", lambda: path)
    seen = []
    original = unlock._secure_existing
    monkeypatch.setattr(unlock, "_secure_existing", lambda p: (seen.append(p), original(p))[1])
    monkeypatch.setattr(unlock, "decrypt_secret", lambda _: pytest.fail("migration must not decrypt"))
    unlock.secure_secret_storage()
    assert seen == [path, stale]
    assert path.read_bytes() == b"legacy"
    assert not stale.exists()


def test_acl_failure_prevents_secret_io(tmp_path, monkeypatch, fake_storage):
    path = tmp_path / "unlock.bin"
    path.write_bytes(b"legacy")
    monkeypatch.setattr(unlock, "secret_path", lambda: path)
    @contextmanager
    def denied(*args, **kwargs):
        raise PermissionError("ACL failed")
        yield
    monkeypatch.setattr(unlock, "_secure_handle", denied)
    monkeypatch.setattr(unlock, "encrypt_secret", lambda _: pytest.fail("must secure before encrypt"))
    monkeypatch.setattr(unlock, "decrypt_secret", lambda _: pytest.fail("must secure before decrypt"))
    with pytest.raises(PermissionError):
        unlock.save_secret(TOKEN)
    with pytest.raises(PermissionError):
        unlock.secure_secret_storage()
    assert unlock.load_secret() is None
    assert unlock.clear_secret() is False
    assert path.read_bytes() == b"legacy"


def test_failed_write_preserves_old_secret(tmp_path, monkeypatch, fake_storage):
    path = tmp_path / "unlock.bin"
    path.write_bytes(b"legacy")
    monkeypatch.setattr(unlock, "secret_path", lambda: path)
    monkeypatch.setattr(unlock, "encrypt_secret", lambda _: b"encrypted")
    def failed_write(handle, data):
        handle.write(data[:2])
        raise OSError("disk full")
    monkeypatch.setattr(sys.modules["win32file"], "WriteFile", failed_write)
    with pytest.raises(OSError):
        unlock.save_secret(TOKEN)
    assert path.read_bytes() == b"legacy"
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize("attributes,links,fail_acl", [(0, 1, False), (0x400, 1, False),
                                                        (0, 2, False), (0, 1, True)])
def test_secure_handle_applies_acl_before_yield(monkeypatch, tmp_path, attributes, links, fail_acl):
    events = []
    sd = SimpleNamespace(GetSecurityDescriptorOwner=lambda: "BA", GetSecurityDescriptorDacl=lambda: "ACL")
    monkeypatch.setattr(unlock, "_secret_security", lambda: (sd, "secure-at-creation"))
    def create(path, access, sharing, sa, disposition, flags, template):
        assert sharing == 0 and sa == "secure-at-creation" and disposition == 1
        assert flags & 0x00200000
        assert access & 0x00080000  # WRITE_OWNER
        events.append("create")
        return "handle"
    def set_acl(*args):
        events.append("acl")
        if fail_acl:
            raise PermissionError("denied")
    monkeypatch.setitem(sys.modules, "win32file", SimpleNamespace(
        CreateFile=create, GetFileInformationByHandle=lambda _: (attributes, 0, 0, 0, 0, 0, 0, links),
        CloseHandle=lambda _: events.append("close")))
    monkeypatch.setitem(sys.modules, "win32security", SimpleNamespace(
        SE_FILE_OBJECT=1, OWNER_SECURITY_INFORMATION=1, DACL_SECURITY_INFORMATION=4,
        PROTECTED_DACL_SECURITY_INFORMATION=0x80000000, SetSecurityInfo=set_acl))
    if attributes or links != 1 or fail_acl:
        with pytest.raises(OSError):
            with unlock._secure_handle(tmp_path / "unlock.tmp", create=True):
                pytest.fail("unsafe handle exposed")
    else:
        with unlock._secure_handle(tmp_path / "unlock.tmp", create=True):
            events.append("write")
        assert events == ["create", "acl", "write", "close"]
    assert events[-1] == "close"


@pytest.mark.parametrize("session,sid,console_sid,query_fails,expected", [
    (1, "alice", "alice", False, True), (2, "alice", "alice", False, False),
    (1, "bob", "alice", False, False), (1, "alice", "alice", True, False)])
def test_client_token_boundary(monkeypatch, session, sid, console_sid, query_fails, expected):
    events = []
    client = SimpleNamespace(Close=lambda: events.append("client-close"))
    console = SimpleNamespace(Close=lambda: events.append("console-close"))
    def info(token, kind):
        if query_fails:
            raise OSError("query failed")
        return session if kind == 12 else (sid if token is client else console_sid, 0)
    monkeypatch.setitem(sys.modules, "win32api", SimpleNamespace(GetCurrentThread=lambda: 1))
    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(TOKEN_QUERY=8))
    monkeypatch.setitem(sys.modules, "win32security", SimpleNamespace(
        ImpersonateNamedPipeClient=lambda _: events.append("impersonate"),
        OpenThreadToken=lambda *args: client, TokenSessionId=12, TokenUser=1,
        GetTokenInformation=info, RevertToSelf=lambda: events.append("revert")))
    monkeypatch.setitem(sys.modules, "win32ts", SimpleNamespace(
        WTSGetActiveConsoleSessionId=lambda: 1, WTSQueryUserToken=lambda _: console))
    assert unlock_service._client_is_console("pipe") is expected
    assert events[:3] == ["impersonate", "client-close", "revert"]


@pytest.mark.skipif(sys.platform != "win32", reason="Installed Windows API smoke test")
def test_installed_pipe_impersonation_api():
    import win32security
    assert callable(win32security.ImpersonateNamedPipeClient)
    assert callable(win32security.RevertToSelf)


def test_pipe_not_created_when_migration_fails(monkeypatch):
    def fail():
        raise PermissionError("migration failed")
    monkeypatch.setattr(unlock, "secure_secret_storage", fail)
    for module in ("win32pipe", "win32file", "win32security", "pywintypes", "win32ts"):
        monkeypatch.setitem(sys.modules, module, SimpleNamespace())
    with pytest.raises(PermissionError):
        unlock_service._serve_pipe(None)


@pytest.mark.parametrize("code,missing", [(2, True), (5, False), (32, False)])
def test_existing_file_handles_native_errors(monkeypatch, tmp_path, code, missing):
    # Match pywintypes.error's Exception base, which differs from OSError.
    class NativeError(Exception):
        winerror = code
    @contextmanager
    def fail(*args, **kwargs):
        raise NativeError()
        yield
    monkeypatch.setattr(unlock, "_secure_handle", fail)
    if missing:
        assert unlock._secure_existing(tmp_path / "unlock.bin") is False
    else:
        with pytest.raises(NativeError):
            unlock._secure_existing(tmp_path / "unlock.bin")


def test_load_missing_native_file_does_not_log_error(tmp_path, monkeypatch, fake_storage):
    class NativeError(Exception):
        winerror = 2
    @contextmanager
    def missing(*args, **kwargs):
        raise NativeError()
        yield
    monkeypatch.setattr(unlock, "secret_path", lambda: tmp_path / "unlock.bin")
    monkeypatch.setattr(unlock, "_secure_handle", missing)
    monkeypatch.setattr(unlock.log, "exception", lambda *args: pytest.fail("missing file is not an error"))
    assert unlock.load_secret() is None


@pytest.mark.parametrize("code", [183, 5])
def test_store_handles_native_directory_errors(monkeypatch, code):
    class NativeError(Exception):
        winerror = code
    directory = SimpleNamespace(parents=[])
    path = SimpleNamespace(parent=directory)
    path.absolute = lambda: path
    monkeypatch.setattr(unlock, "secret_path", lambda: path)
    monkeypatch.setattr(unlock, "_secret_security", lambda: (None, "protected"))
    events = []
    def mkdir(name, sa):
        assert sa == "protected"
        raise NativeError()
    @contextmanager
    def secure(p, **kwargs):
        assert p is directory and kwargs == {"directory": True}
        events.append("secured")
        yield
    monkeypatch.setitem(sys.modules, "win32file", SimpleNamespace(CreateDirectory=mkdir))
    monkeypatch.setattr(unlock, "_secure_handle", secure)
    if code == 183:
        with unlock._secure_store() as actual:
            assert actual is path and events == ["secured"]
    else:
        with pytest.raises(NativeError):
            with unlock._secure_store():
                pytest.fail("must fail closed")


def test_spawn_rejects_changed_console_before_process_access(monkeypatch):
    for module in ("win32api", "win32con", "win32event", "win32process", "win32profile",
                   "win32security", "pywintypes"):
        monkeypatch.setitem(sys.modules, module, SimpleNamespace())
    monkeypatch.setitem(sys.modules, "win32ts", SimpleNamespace(WTSGetActiveConsoleSessionId=lambda: 2))
    assert unlock_service.spawn_on_winlogon(session_id=1) is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL integration")
def test_real_acl_in_isolated_child_only(tmp_path, monkeypatch):
    import win32api
    import win32con
    import win32file
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        if not win32security.GetTokenInformation(token, win32security.TokenElevation):
            pytest.skip("Requires an already elevated runner; never elevate or restrict pytest's temp root")
    finally:
        token.Close()
    root = tmp_path / "isolated-unlock-store"
    root.mkdir()
    path = root / "unlock.bin"
    path.write_bytes(b"dummy legacy ciphertext")
    path.with_suffix(".tmp").write_bytes(b"dummy stale ciphertext")
    monkeypatch.setattr(unlock, "secret_path", lambda: path)
    flags = win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION
    parent_before = win32security.GetFileSecurity(str(tmp_path), flags)
    def assert_secure(sd):
        assert sd.GetSecurityDescriptorControl()[0] & 0x1000  # SE_DACL_PROTECTED
        assert win32security.ConvertSidToStringSid(sd.GetSecurityDescriptorOwner()) == "S-1-5-32-544"
        acl = sd.GetSecurityDescriptorDacl()
        assert acl.GetAceCount() == 2
        assert {win32security.ConvertSidToStringSid(acl.GetAce(i)[2]) for i in range(2)} == {
            "S-1-5-18", "S-1-5-32-544"}
        for i in range(2):
            assert acl.GetAce(i)[0][0] == 0  # ACCESS_ALLOWED_ACE_TYPE
            assert acl.GetAce(i)[1] == 0x1F01FF  # FILE_ALL_ACCESS
    original_write = win32file.WriteFile
    def checked_write(handle, data):
        # Verify the actual temporary object's ACL before its first secret byte.
        assert_secure(win32security.GetSecurityInfo(handle, win32security.SE_FILE_OBJECT, flags))
        return original_write(handle, data)
    monkeypatch.setattr(win32file, "WriteFile", checked_write)
    try:
        unlock.secure_secret_storage()
        assert not path.with_suffix(".tmp").exists()
        for item in (root, path):
            assert_secure(win32security.GetFileSecurity(str(item), flags))
        unlock.save_secret(TOKEN)
        assert unlock.load_secret() == TOKEN
        assert unlock.clear_secret()
        assert not path.exists()
    finally:
        # Only this dedicated child is touched; the elevated runner retains full access.
        for item in (path, path.with_suffix(".tmp")):
            item.unlink(missing_ok=True)
        root.rmdir()
    parent_after = win32security.GetFileSecurity(str(tmp_path), flags)
    assert (win32security.ConvertSecurityDescriptorToStringSecurityDescriptor(parent_before, 1, flags) ==
            win32security.ConvertSecurityDescriptorToStringSecurityDescriptor(parent_after, 1, flags))
