"""Cửa sổ NEXA mở ra được xếp CẠNH NEXA (nexa/desktop/side_by_side.py) — Win32 giả lập, không đụng cửa sổ thật."""
from __future__ import annotations

from fake_win32 import FakeConfig, FakeWin32, FakeWindow, dual_setup, mon

from nexa.desktop import win32api as w
from nexa.desktop.side_by_side import SideBySide, Snapshot, split_layout

WORK = (0, 0, 1920, 1040)


class Clock:
    def __init__(self, on_sleep=None):
        self.t = 0.0
        self.on_sleep = on_sleep

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s
        if self.on_sleep:
            self.on_sleep(self.t)


def setup(nexa_rect=(100, 60, 1420, 880), **nexa_kw):
    api = FakeWin32(monitors=[mon(1, r"\\.\DISPLAY1", (0, 0, 1920, 1080), work=WORK, primary=True)])
    api.windows[1] = FakeWindow(pid=api.own, title="NEXA — by NXS MEDIA", rect=nexa_rect, process="python.exe", **nexa_kw)
    clock = Clock()
    sbs = SideBySide(FakeConfig({"ui.side_by_side": True, "ui.side_by_side_ratio": 0.4}), api,
                     sleep=clock.sleep, clock=clock)
    return api, sbs, clock


def test_split_layout_keeps_nexa_side_and_min_width():
    nexa, other = split_layout(WORK, (100, 60, 1420, 880), 96, 0.4, False)
    assert nexa == (0, 0, 768, 1040) and other == (768, 0, 1920, 1040)       # NEXA đang lệch trái → giữ bên trái
    nexa, other = split_layout(WORK, (900, 60, 1900, 880), 96, 0.4, False)
    assert nexa == (1152, 0, 1920, 1040) and other == (0, 0, 1152, 1040)
    nexa, _ = split_layout(WORK, (0, 0, 1920, 1040), 144, 0.4, True)       # 150%: ≥ 600 px logic = 900 px
    assert nexa == (1020, 0, 1920, 1040)
    nexa, _ = split_layout(WORK, (1100, 0, 1800, 1040), 96, 0.4, False)    # anh tự chỉnh 700 px hợp lý → giữ
    assert nexa == (1220, 0, 1920, 1040)


def test_new_window_over_nexa_is_tiled_beside_it():
    api, sbs, _ = setup()
    api.windows[50] = FakeWindow(pid=4, title="Không có tiêu đề - Notepad", rect=(300, 200, 1100, 800))
    assert sbs.arrange(50, "open_app") == "arranged"
    assert api.windows[1].rect == (0, 0, 768, 1040)
    assert api.windows[50].rect == (768, 0, 1920, 1040)
    assert api.foreground == 0                                             # không giật tiêu điểm


def test_window_not_overlapping_nexa_is_left_alone():
    api, sbs, _ = setup(nexa_rect=(0, 0, 900, 1040))
    api.windows[50] = FakeWindow(pid=4, title="Notepad", rect=(950, 0, 1920, 1040))
    assert sbs.arrange(50) == "already_side_by_side"
    assert api.set_pos_calls == []


def test_minimized_nexa_is_restored_and_maximized_target_restored():
    api, sbs, _ = setup(iconic=True)
    api.windows[50] = FakeWindow(pid=4, title="Word", rect=WORK, zoomed=True, normal_rect=(200, 100, 1200, 900))
    assert sbs.arrange(50) == "arranged"
    assert not api.windows[1].iconic and not api.windows[50].zoomed
    assert api.windows[50].rect == (768, 0, 1920, 1040)


def test_maximized_nexa_goes_right():
    api, sbs, _ = setup(nexa_rect=WORK, zoomed=True)
    api.windows[50] = FakeWindow(pid=4, title="Chrome", rect=(100, 100, 900, 700))
    sbs.arrange(50)
    assert api.windows[1].rect == (1152, 0, 1920, 1040) and not api.windows[1].zoomed
    assert api.windows[50].rect == (0, 0, 1152, 1040)


def test_compact_nexa_not_tiled():
    api, sbs, _ = setup(nexa_rect=(1670, 780, 1900, 1010), ex_style=w.WS_EX_TOOLWINDOW)
    api.windows[50] = FakeWindow(pid=4, title="Notepad", rect=(0, 0, 1920, 1040))
    assert sbs.arrange(50) == "compact"


def test_other_monitor_window_left_alone():
    api, cfg, m1, m2 = dual_setup()
    api.windows[1] = FakeWindow(pid=api.own, title="NEXA — by NXS MEDIA", rect=(100, 60, 1420, 880))
    api.windows[50] = FakeWindow(pid=4, title="Notepad", rect=(-2000, 0, -800, 900))
    cfg["ui.side_by_side"] = True
    assert SideBySide(cfg, api).arrange(50) == "already_side_by_side"


def test_wait_target_sees_window_appearing_later():
    api, sbs, clock = setup()
    snap = Snapshot(frozenset(api.windows), 1, 0.0)

    def appear(t):
        if t >= 1.5 and 60 not in api.windows:
            api.windows[60] = FakeWindow(pid=7, title="NEXA chạy thử — main.py", rect=(300, 200, 1300, 800),
                                         cls="ConsoleWindowClass")
            api.windows[61] = FakeWindow(pid=7, title="", rect=(0, 0, 50, 50))          # không tiêu đề: bỏ qua
    clock.on_sleep = appear
    assert sbs.wait_target(snap, 8.0) == 60
    assert clock.t < 3


def test_wait_target_falls_back_to_focused_existing_window():
    api, sbs, clock = setup()
    api.windows[70] = FakeWindow(pid=8, title="Zalo", rect=(0, 0, 1000, 800))
    snap = Snapshot(frozenset(api.windows), 1, 0.0)
    api.foreground = 70                                                  # focus_window: đưa cửa sổ có sẵn lên trước
    assert sbs.wait_target(snap, 8.0) == 70
    api.foreground = 1                                                   # vẫn là NEXA, không có gì mới
    assert sbs.wait_target(snap, 2.0) == 0


def test_before_only_for_opener_tools_and_when_enabled():
    api, sbs, _ = setup()
    assert sbs.before("set_volume") is None
    assert sbs.before("open_app") is not None
    sbs.config["ui.side_by_side"] = False
    assert sbs.before("open_app") is None


def test_invisible_border_compensated():
    api, sbs, _ = setup()

    api.get_window_rect = lambda h: (api.windows[h].rect[0] - 7, api.windows[h].rect[1], api.windows[h].rect[2] + 7,
                                     api.windows[h].rect[3] + 7)
    api.windows[50] = FakeWindow(pid=4, title="Notepad", rect=(300, 200, 1100, 800))
    sbs.arrange(50)
    call = [c for c in api.set_pos_calls if c[0] == 50][0]
    assert call[1:5] == (768 - 7, 0, 1920 - 768 + 14, 1040 + 7)
