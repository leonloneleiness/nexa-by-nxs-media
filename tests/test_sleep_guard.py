"""Ngủ canh gác: lệnh "cho máy ngủ" chỉ tắt màn hình, lời chào khi quay lại, trạng thái khóa máy."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import h_power, risk_power
from nexa.core.events import ToolResult
from nexa.core.safety import Risk
from nexa.desktop import sleep_guard

R = IntentRouter(app_exists=lambda n: False)


@pytest.mark.parametrize("text", ["cho máy ngủ", "Nexa, cho máy tính ngủ đi", "máy tính vào chế độ ngủ",
                                  "tắt màn hình", "ngủ canh gác"])
def test_machine_sleep_routes_to_power_tool(text):
    r = R.route(text)
    assert r.kind == "basic", (text, r)
    assert r.calls == [("system_power", {"action": "sleep"})]


@pytest.mark.parametrize("text", ["nghỉ đi", "Nexa, ngủ đi", "về chế độ chờ"])
def test_nexa_rest_still_standby(text):
    assert R.route(text).kind == "sleep"


def _ctx(hooks=None, guard=True):
    cfg = SimpleNamespace(get=lambda k, d=None: guard if k == "power.clap_wake_guard" else d)
    return SimpleNamespace(services=SimpleNamespace(hooks=hooks or {}, config=cfg))


def test_sleep_uses_guard_hook(monkeypatch):
    import nexa.desktop.system as system
    monkeypatch.setattr(system, "power_action", lambda a: pytest.fail("không được ngủ thật"))
    r = h_power({"action": "sleep"}, _ctx({"guard_sleep": lambda: ToolResult.success("tắt màn hình", guard=True)}))
    assert r.ok and r.data.get("guard")


def test_sleep_falls_back_when_guard_off(monkeypatch):
    import nexa.desktop.system as system
    calls = []
    monkeypatch.setattr(system, "power_action", lambda a: calls.append(a) or ToolResult.success("ngủ"))
    h_power({"action": "sleep"}, _ctx({"guard_sleep": lambda: None}, guard=False))
    assert calls == ["sleep"]


def test_sleep_risk_depends_on_guard():
    assert risk_power({"action": "sleep"}, _ctx(guard=True)).risk == Risk.LOW
    assert risk_power({"action": "sleep"}, _ctx(guard=False)).risk == Risk.MEDIUM


@pytest.mark.parametrize("hour,part", [(7, "sáng"), (12, "trưa"), (15, "chiều"), (21, "tối"), (2, "tối")])
def test_away_greeting(hour, part):
    assert sleep_guard.away_greeting(hour) == f"Chào buổi {part} anh Sơn, em là Nexa. Em sẵn sàng."


@pytest.mark.skipif(sys.platform != "win32", reason="Win32")
def test_session_is_unlocked_while_tests_run():
    assert sleep_guard.session_locked() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Win32")
def test_guard_enable_disable():
    g = sleep_guard.SleepGuard()
    try:
        assert g.enable()
        assert g.enabled
    finally:
        g.disable()
    assert not g.enabled


# ----- trạng thái màn hình / ngủ thật / nút nguồn -----
def _broadcast(state: int):
    import ctypes
    buf = ctypes.create_string_buffer(bytes(sleep_guard.GUID_CONSOLE_DISPLAY_STATE) + (4).to_bytes(4, "little")
                                      + state.to_bytes(4, "little"))
    return buf, ctypes.addressof(buf)


def test_display_callback_parses_state():
    seen = []
    m = sleep_guard.PowerEventMonitor(on_display=seen.append)
    for st in (1, 0, 0, 2, 1):
        buf, addr = _broadcast(st)
        m._display_cb(None, sleep_guard.PBT_POWERSETTINGCHANGE, addr)
    assert seen == [1, 0, 2, 1]          # trạng thái trùng không báo lại
    assert m.display_state == 1 and m.wait_display_on(0)
    buf, addr = _broadcast(0)
    m._display_cb(None, sleep_guard.PBT_POWERSETTINGCHANGE, addr)
    assert m.display_off and not m.wait_display_on(0)


def test_resume_reported_once(monkeypatch):
    gaps = []
    g = sleep_guard.SleepGuard(on_resumed=gaps.append)
    t = [1000.0]
    monkeypatch.setattr(sleep_guard.time, "time", lambda: t[0])
    g.monitor._suspend_cb(None, sleep_guard.PBT_APMSUSPEND, None)
    t[0] += 600
    g.monitor._suspend_cb(None, sleep_guard.PBT_APMRESUMEAUTOMATIC, None)
    g.monitor._suspend_cb(None, sleep_guard.PBT_APMRESUMESUSPEND, None)
    assert gaps == [600.0]


class FakePowercfg:
    def __init__(self, values):
        self.values = dict(values)       # alias → [ac, dc]
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "/qh":
            ac, dc = self.values[args[3]]
            return (f"    Current AC Power Setting Index: 0x{ac:08x}\n"
                    f"    Current DC Power Setting Index: 0x{dc:08x}\n")
        if args[0] in ("/setacvalueindex", "/setdcvalueindex"):
            self.values[args[3]][0 if args[0] == "/setacvalueindex" else 1] = int(args[4])
        return ""


ORIG = {"PBUTTONACTION": [1, 1], "SBUTTONACTION": [1, 1], "LIDACTION": [0, 1]}


def test_button_remap_apply_and_restore(tmp_path):
    fake = FakePowercfg({k: list(v) for k, v in ORIG.items()})
    r = sleep_guard.ButtonRemap(tmp_path / "b.json", runner=fake)
    assert r.apply(lid=False)
    assert fake.values["PBUTTONACTION"] == [4, 4] and fake.values["SBUTTONACTION"] == [4, 4]
    assert fake.values["LIDACTION"] == [0, 1]
    assert ["/setactive", "SCHEME_CURRENT"] in fake.calls
    r.restore()
    assert fake.values == ORIG and not (tmp_path / "b.json").exists()


def test_button_remap_lid_and_crash_recovery(tmp_path):
    fake = FakePowercfg({k: list(v) for k, v in ORIG.items()})
    sleep_guard.ButtonRemap(tmp_path / "b.json", runner=fake).apply(lid=True)
    assert fake.values["LIDACTION"] == [0, 0]
    # NEXA bị tắt ngang: lần sau apply lại không được sao lưu nhầm giá trị đã đổi.
    again = sleep_guard.ButtonRemap(tmp_path / "b.json", runner=fake)
    again.apply(lid=False)
    again.restore()
    assert fake.values == ORIG


def test_button_remap_noop_when_already_set(tmp_path):
    fake = FakePowercfg({"PBUTTONACTION": [4, 4], "SBUTTONACTION": [4, 4]})
    r = sleep_guard.ButtonRemap(tmp_path / "b.json", runner=fake)
    assert r.apply()
    assert not (tmp_path / "b.json").exists()
    assert not any(c[0].startswith("/set") for c in fake.calls)


def test_keep_display_remaps_buttons_and_lid_then_restores(tmp_path):
    fake = FakePowercfg({k: list(v) for k, v in ORIG.items()})
    remap = sleep_guard.ButtonRemap(tmp_path / "backup.json", runner=fake)
    assert remap.apply(lid=True, keep_display=True)
    assert all(values == [0, 0] for values in fake.values.values())
    assert remap.restore()
    assert fake.values == ORIG


def test_unreadable_button_does_not_report_success(tmp_path):
    remap = sleep_guard.ButtonRemap(tmp_path / "backup.json", runner=lambda args: "")
    assert not remap.apply(lid=True)


def test_failed_restore_preserves_backup_and_prevents_new_apply(tmp_path):
    import json
    path = tmp_path / "backup.json"
    path.write_text(json.dumps(ORIG), encoding="utf-8")
    remap = sleep_guard.ButtonRemap(path, runner=lambda args: "")
    assert not remap.apply(lid=True, keep_display=True)
    assert json.loads(path.read_text(encoding="utf-8")) == ORIG


def test_fallback_failure_is_not_reported_as_enabled(monkeypatch):
    g = sleep_guard.SleepGuard()
    monkeypatch.setattr(sleep_guard.ctypes.windll.kernel32, "SetThreadExecutionState", lambda flags: 0)
    g._stes_fallback()
    assert not g.enabled
    g.disable()


@pytest.mark.skipif(sys.platform != "win32", reason="Win32")
def test_keep_display_power_requests_and_mode_switch():
    g = sleep_guard.SleepGuard()
    try:
        assert g.enable(keep_display=True)
        assert g.keep_display and g.enabled
        if g._handle is not None:
            assert g._requests == [sleep_guard.POWER_REQUEST_SYSTEM_REQUIRED, sleep_guard.POWER_REQUEST_DISPLAY_REQUIRED]
        assert g.enable(keep_display=False)
        assert not g.keep_display and g.enabled
        if g._handle is not None:
            assert g._requests == [sleep_guard.POWER_REQUEST_SYSTEM_REQUIRED]
    finally:
        g.disable()
    assert not g.enabled


@pytest.mark.skipif(sys.platform != "win32", reason="Win32")
def test_power_monitor_reports_display_state():
    m = sleep_guard.PowerEventMonitor()
    try:
        assert m.start()
        import time
        deadline = time.monotonic() + 2
        while m.display_state is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert m.display_state in (0, 1, 2)
    finally:
        m.stop()
