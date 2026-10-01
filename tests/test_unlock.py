"""Tự mở khóa khi vỗ tay: dispatch lệnh pipe, dựng chuỗi phím, lưu/giải mã mã, và controller.

Không dùng mã thật của anh Sơn ở bất cứ đâu — chỉ token thử vô hại. Các test chạy được trên mọi nền
(phần Win32 được mock); vài test round-trip DPAPI thật thì skip nếu không phải Windows.
"""
from __future__ import annotations

import sys
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
    r = unlock_service.handle_command("CLEAR", do_clear=lambda: calls.append(1))
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
def test_save_load_roundtrip_with_fake_dpapi(tmp_path, monkeypatch):
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


def test_load_secret_swallows_bad_blob(tmp_path, monkeypatch):
    p = tmp_path / "unlock.bin"
    p.write_bytes(b"garbage")
    monkeypatch.setattr(unlock, "secret_path", lambda: p)

    def boom(_blob):
        raise ValueError("cannot decrypt")

    monkeypatch.setattr(unlock, "decrypt_secret", boom)
    assert unlock.load_secret() is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI chỉ có trên Windows")
def test_dpapi_roundtrip_real(tmp_path, monkeypatch):
    monkeypatch.setattr(unlock, "secret_path", lambda: tmp_path / "unlock.bin")
    unlock.save_secret(TOKEN)
    assert unlock.load_secret() == TOKEN
    unlock.clear_secret()


@pytest.mark.skipif(sys.platform != "win32", reason="dịch vụ Windows")
def test_service_status_no_error():
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
