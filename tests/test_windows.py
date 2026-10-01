"""Kiểm thử hai màn hình, chuyển cửa sổ, thu nhỏ/khôi phục và lịch sử — với Win32 giả lập."""
from __future__ import annotations

import pytest

from fake_win32 import FakeWindow, dual_setup, mon
from nexa.desktop.monitors import (MonitorManager, clamp_rect_to, map_rect_between_work_areas, rect_h, rect_w,
                                   screen_to_workspace, workspace_to_screen)
from nexa.desktop.window_history import WindowHistory
from nexa.desktop.windows import WindowManager


def make_wm(api, cfg):
    return WindowManager(api, MonitorManager(api, cfg), WindowHistory("sess"), own_pids={api.own}, sleep=lambda s: None)


# ------------------------------------------------------------------ hình học thuần
def test_workspace_roundtrip_with_top_taskbar():
    primary = mon(1, "D1", (0, 0, 1920, 1080), work=(0, 40, 1920, 1080), primary=True)
    r = (100, 200, 900, 800)
    ws = screen_to_workspace(r, primary)
    assert ws == (100, 160, 900, 760)
    assert workspace_to_screen(ws, primary) == r


def test_map_rect_negative_coordinates_keeps_relative_position_and_fits():
    src = (0, 0, 1920, 1040)
    dst = (-2560, -200, 0, 1200)
    win = (960, 520, 1760, 1020)  # nửa phải-dưới
    out = map_rect_between_work_areas(win, src, dst)
    assert dst[0] <= out[0] and out[2] <= dst[2] and dst[1] <= out[1] and out[3] <= dst[3]
    assert rect_w(out) == 800 and rect_h(out) == 500
    assert out[0] > dst[0] + (rect_w(dst) - 800) * 0.5  # vẫn ở nửa phải


def test_map_rect_larger_than_target_is_clamped():
    out = map_rect_between_work_areas((0, 0, 3000, 2000), (0, 0, 3840, 2100), (0, 0, 1280, 700))
    assert out == (0, 0, 1280, 700)


def test_clamp_rect_to_work_area():
    assert clamp_rect_to((0, 0, 100, 100), (90, 90, 140, 140)) == (50, 50, 100, 100)


# ------------------------------------------------------------------ chuyển màn hình
def test_move_normal_window_to_negative_high_dpi_monitor():
    api, cfg, m1, m2 = dual_setup()
    api.windows[10] = FakeWindow(pid=1, title="Ghi chú - Notepad", rect=(100, 100, 900, 700))
    api.foreground = 10
    wm = make_wm(api, cfg)
    r = wm.move_to_target_monitor(10)
    assert r.ok and r.verified, r.message
    rect = api.windows[10].rect
    assert m2.work[0] <= rect[0] and rect[2] <= m2.work[2]
    assert r.data["target"] == m2.device_name


def test_move_maximized_window_stays_maximized_on_target():
    api, cfg, m1, m2 = dual_setup()
    api.windows[11] = FakeWindow(pid=1, title="Trình duyệt", rect=m1.work, zoomed=True, normal_rect=(200, 200, 1000, 800))
    api.foreground = 11
    wm = make_wm(api, cfg)
    r = wm.move_to_target_monitor(11)
    assert r.ok and r.verified
    assert api.windows[11].zoomed
    assert api.windows[11].rect == m2.work


def test_window_already_on_target_is_not_sent_back():
    api, cfg, m1, m2 = dual_setup()
    api.windows[12] = FakeWindow(pid=1, title="A", rect=(-2000, 0, -1000, 600))
    wm = make_wm(api, cfg)
    before = api.windows[12].rect
    r = wm.move_to_target_monitor(12)
    assert r.ok and r.data.get("no_op")
    assert api.windows[12].rect == before
    assert api.set_pos_calls == []


def test_single_monitor_is_reported_and_skipped():
    api, cfg, m1, m2 = dual_setup()
    api.monitors = [m1]
    api.windows[13] = FakeWindow(pid=1, title="A", rect=(100, 100, 500, 500))
    r = make_wm(api, cfg).move_to_target_monitor(13)
    assert not r.ok and r.error_code == "monitor_unavailable"
    assert api.set_pos_calls == []


def test_disconnected_target_monitor_uses_no_stale_handle():
    api, cfg, m1, m2 = dual_setup()
    m3 = mon(3, r"\\.\DISPLAY3", (1920, 0, 3840, 1080))
    api.monitors = [m1, m3]           # màn hình đích đã rút, cắm màn hình khác
    api.windows[14] = FakeWindow(pid=1, title="A", rect=(100, 100, 500, 500))
    r = make_wm(api, cfg).move_to_target_monitor(14)
    assert not r.ok and r.error_code == "monitor_unavailable"


def test_move_denied_by_windows_reports_failure():
    api, cfg, m1, m2 = dual_setup()
    api.windows[15] = FakeWindow(pid=1, title="Admin app", rect=(100, 100, 500, 500), deny_move=True)
    r = make_wm(api, cfg).move_to_target_monitor(15)
    assert not r.ok and r.error_code == "move_denied"


@pytest.mark.parametrize("win", [
    FakeWindow(pid=999, title="NEXA", rect=(0, 0, 100, 100)),                 # cửa sổ của chính NEXA
    FakeWindow(pid=2, title="", rect=(0, 1040, 1920, 1080), cls="Shell_TrayWnd"),  # taskbar
    FakeWindow(pid=2, title="", rect=(0, 0, 1920, 1080), cls="Progman"),          # desktop
    FakeWindow(pid=3, title="tip", rect=(0, 0, 100, 100), ex_style=0x80),         # tool window/overlay
])
def test_invalid_targets_rejected(win):
    api, cfg, *_ = dual_setup()
    api.windows[20] = win
    wm = make_wm(api, cfg)
    assert not wm.move_to_target_monitor(20).ok
    assert not wm.minimize(20).ok


def test_unconfigured_roles_pick_primary_as_source():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    cfg.clear()
    roles = MonitorManager(api, cfg).roles()
    assert roles.source.device_name == m1.device_name and roles.target.device_name == m2.device_name


# ------------------------------------------------------------------ thu nhỏ / khôi phục
def _two_windows():
    api, cfg, m1, m2 = dual_setup()
    api.windows[1] = FakeWindow(pid=11, title="A", rect=(100, 100, 700, 600), process="a.exe", created=1.0)
    api.windows[2] = FakeWindow(pid=22, title="B", rect=(200, 200, 900, 700), zoomed=True, process="b.exe", created=2.0)
    return api, cfg, m1, m2


def test_minimize_a_then_b_restores_b_then_a():
    api, cfg, *_ = _two_windows()
    wm = make_wm(api, cfg)
    assert wm.minimize(1).ok and wm.minimize(2).ok
    r1 = wm.restore_last()
    assert r1.ok and r1.data["title"] == "B" and api.windows[2].zoomed  # giữ trạng thái phóng to
    r2 = wm.restore_last()
    assert r2.ok and r2.data["title"] == "A" and not api.windows[1].zoomed
    r3 = wm.restore_last()
    assert not r3.ok and r3.error_code == "history_empty"


def test_restore_skips_closed_window():
    api, cfg, *_ = _two_windows()
    wm = make_wm(api, cfg)
    wm.minimize(1)
    wm.minimize(2)
    del api.windows[2]
    r = wm.restore_last()
    assert r.ok and r.data["title"] == "A"


def test_restore_skips_reused_hwnd():
    api, cfg, *_ = _two_windows()
    wm = make_wm(api, cfg)
    wm.minimize(1)
    wm.minimize(2)
    api.windows[2] = FakeWindow(pid=77, title="Khác", rect=(0, 0, 10, 10), iconic=True, process="x.exe", created=9.0)
    r = wm.restore_last()
    assert r.data["title"] == "A"
    assert api.windows[2].iconic  # cửa sổ lạ dùng lại HWND không bị đụng tới


def test_restore_skips_window_user_already_restored():
    api, cfg, *_ = _two_windows()
    wm = make_wm(api, cfg)
    wm.minimize(1)
    wm.minimize(2)
    api.windows[2].iconic = False
    assert wm.restore_last().data["title"] == "A"


def test_history_only_records_verified_minimize():
    api, cfg, *_ = _two_windows()
    api.windows[1].hides_to_tray = True
    wm = make_wm(api, cfg)
    r = wm.minimize(1)
    assert not r.ok and r.error_code == "hidden_to_tray"
    assert len(wm.history) == 0


def test_restore_when_old_monitor_disconnected_goes_to_active_monitor():
    api, cfg, m1, m2 = dual_setup()
    api.windows[5] = FakeWindow(pid=5, title="Trên màn 2", rect=(-2000, 0, -1200, 600))
    wm = make_wm(api, cfg)
    assert wm.minimize(5).ok
    api.monitors = [m1]
    r = wm.restore_last()
    assert r.ok
    rect = api.windows[5].rect
    assert m1.work[0] <= rect[0] and rect[2] <= m1.work[2]


def test_history_is_per_session():
    h = WindowHistory("s1")
    from nexa.desktop.window_history import MinimizedEntry, WindowIdentity
    from nexa.desktop.win32api import Placement
    e = MinimizedEntry(WindowIdentity(1, 1, "a", 1.0, "c"), "A", Placement(1, 0, (0, 0, 1, 1)), False, (0, 0, 1, 1), {}, "s2")
    with pytest.raises(ValueError):
        h.push(e)


# ------------------------------------------------------------------ snapshot cử chỉ
def test_snapshot_invalid_when_foreground_changes():
    api, cfg, *_ = _two_windows()
    api.foreground = 1
    wm = make_wm(api, cfg)
    snap = wm.snapshot_foreground()
    assert wm.verify_snapshot(snap)[0]
    api.foreground = 2
    ok, reason = wm.verify_snapshot(snap)
    assert not ok and "thay đổi" in reason


def test_gesture_minimize_uses_snapshot_and_cancels_on_focus_change(config):
    """Luồng thật: tool registry + executor + snapshot; cửa sổ đổi giữa chừng -> hủy, không thu nhỏ cửa sổ mới."""
    from nexa.ai.tool_registry import Services, build_registry
    from nexa.core.events import Source, ToolCall
    from nexa.core.executor import Executor
    from nexa.core.safety import SafetyManager
    api, cfg, *_ = _two_windows()
    api.foreground = 1
    wm = make_wm(api, cfg)
    safety = SafetyManager()
    ex = Executor(build_registry(config), safety, Services(config=config, wm=wm, monitors=wm.monitors), com_init=False)
    ex.start()
    try:
        snap = wm.snapshot_foreground()
        api.foreground = 2  # người dùng chuyển cửa sổ trước khi cử chỉ được thực thi
        r = ex.execute(ToolCall("minimize_window", {"use_gesture_snapshot": True}, Source.GESTURE, snapshot=snap),
                       safety.new_token())
        assert not r.ok
        assert not api.windows[1].iconic and not api.windows[2].iconic
        api.foreground = 1
        snap = wm.snapshot_foreground()
        r = ex.execute(ToolCall("minimize_window", {"use_gesture_snapshot": True}, Source.GESTURE, snapshot=snap),
                       safety.new_token())
        assert r.ok and api.windows[1].iconic and not api.windows[2].iconic
    finally:
        ex.stop()
