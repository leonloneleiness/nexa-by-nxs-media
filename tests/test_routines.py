"""Kịch bản làm việc: khớp câu lệnh, vùng màn hình, mở + xếp cửa sổ (Win32 giả lập, không đụng cửa sổ thật)."""
from __future__ import annotations

from nexa.ai.intent_router import IntentRouter
from nexa.desktop.monitors import MonitorManager
from nexa.desktop.routines import (Step, find_routine, load_routines, match_routine, RoutineRunner, summarize,
                                   zone_rect)
from nexa.utils.config import DEFAULTS
from nexa.utils.text import fold
from tests.fake_win32 import FakeConfig, FakeWindow, dual_setup, FakeWin32, mon


def default_routines():
    return load_routines(FakeConfig(routines=DEFAULTS["routines"]))


class Clock:
    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def __call__(self):
        return self.t


def make_runner(api, cfg, launch, wait_s=10.0):
    clock = Clock()
    runner = RoutineRunner(api, MonitorManager(api, cfg), launch, "msedge.exe", sleep=clock.sleep, clock=clock,
                           wait_s=wait_s)
    return runner, clock


# ----- cấu hình & khớp câu -----
def test_default_routine_loads():
    rs = default_routines()
    r = rs["bat_dau_lam_viec"]
    assert [s.label for s in r.steps] == ["Claude", "Zalo", "YouTube", "ChatGPT", "VS Code", "Tin nhắn Zalo"]
    assert [s.monitor for s in r.steps if s.is_window] == [1, 1, 2, 2, 1]
    assert r.steps[-1].action == "check_zalo"


def test_load_skips_bad_steps():
    rs = load_routines(FakeConfig(routines={"x": {"name": "X", "phrases": ["làm x"], "steps": [
        {"label": "rỗng"}, {"action": "format_c"}, {"app": "Zalo", "zone": "diagonal", "monitor": 7}]}}))
    steps = rs["x"].steps
    assert len(steps) == 1 and steps[0].zone == "keep" and steps[0].monitor == 1


def test_match_phrases_and_suffixes():
    rs = default_routines()
    for text in ("bắt đầu làm việc", "bắt đầu làm việc thôi", "vào việc nào", "vào việc nhé", "chế độ làm việc",
                 "chạy kịch bản bắt đầu làm việc", "bật chế độ bắt đầu làm việc"):
        assert match_routine(fold(text), rs) == "bat_dau_lam_viec", text
    for text in ("làm việc với file này", "bắt đầu làm việc với excel", "mở zalo"):
        assert match_routine(fold(text), rs) is None, text


def test_find_routine_by_key_or_name():
    rs = default_routines()
    assert find_routine("bat_dau_lam_viec", rs).key == "bat_dau_lam_viec"
    assert find_routine("Bắt đầu làm việc", rs).key == "bat_dau_lam_viec"
    assert find_routine("không có", rs) is None


def test_router_routes_routine_before_other_commands():
    rs = default_routines()
    r = IntentRouter(routine_for=lambda u: match_routine(u, rs))
    for text in ("Nexa, bắt đầu làm việc thôi.", "em ơi vào việc đi"):
        route = r.route(text)
        assert route.kind == "basic" and route.calls == [("run_routine", {"name": "bat_dau_lam_viec"})], text
    assert r.route("mở zalo").calls == [("open_app", {"name": "Zalo"})]
    assert IntentRouter().route("bắt đầu làm việc").calls != [("run_routine", {"name": "bat_dau_lam_viec"})]


def test_zone_rect():
    work = (0, 0, 1920, 1040)
    assert zone_rect(work, "full") == work
    assert zone_rect(work, "left") == (0, 0, 960, 1040)
    assert zone_rect(work, "right") == (960, 0, 1920, 1040)
    assert zone_rect(work, "bottom") == (0, 520, 1920, 1040)
    assert zone_rect(work, "center_third") == (640, 0, 1280, 1040)
    assert zone_rect(work, "right_two_thirds") == (640, 0, 1920, 1040)
    assert zone_rect((1920, 0, 4480, 1400), "left") == (1920, 0, 3200, 1400)


# ----- chạy -----
PROC = {"Claude": ("claude.exe", "Claude"), "Zalo": ("zalo.exe", "Zalo"), "VS Code": ("code.exe", "NEXA - Visual Studio Code"),
        "YouTube": ("msedge.exe", "YouTube - Microsoft Edge"), "ChatGPT": ("msedge.exe", "ChatGPT - Microsoft Edge")}


def launcher(api, launched, delay_title=None):
    def launch(step: Step):
        launched.append(step.label)
        proc, title = PROC[step.label]
        h = 100 + len(api.windows)
        if delay_title == step.label:
            title = "Đang tải - Microsoft Edge"
        api.windows[h] = FakeWindow(pid=h, title=title, rect=(100, 100, 900, 700), process=proc)
        return None
    return launch


def test_fresh_start_places_every_window_and_stacks_in_step_order():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    launched, focused = [], []
    runner, _ = make_runner(api, cfg, launcher(api, launched))
    routine = default_routines()["bat_dau_lam_viec"]
    out = runner.run(routine, focused.append)
    assert launched == ["Claude", "Zalo", "YouTube", "ChatGPT", "VS Code"]
    assert out["failed"] == [] and out["placed"] == ["Claude", "Zalo", "YouTube", "ChatGPT", "VS Code"]
    by_title = {win.title: win for win in api.windows.values()}
    # Chỉ đưa sang đúng màn hình, giữ nguyên kích thước; cửa sổ đã đúng màn hình thì để nguyên.
    for t in ("Claude", "Zalo", "NEXA - Visual Studio Code"):
        assert by_title[t].rect == (100, 100, 900, 700) and not by_title[t].zoomed, t
    for t in ("YouTube - Microsoft Edge", "ChatGPT - Microsoft Edge"):
        assert by_title[t].rect == (2020, 100, 2820, 700), t
    assert api.windows[focused[-1]] is by_title["NEXA - Visual Studio Code"]


def test_explicit_zones_still_tile():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    rs = load_routines(FakeConfig(routines={"x": {"name": "X", "steps": [
        {"label": "Claude", "app": "Claude", "process": "claude.exe", "monitor": 1, "zone": "left"},
        {"label": "YouTube", "url": "https://www.youtube.com", "title": "YouTube", "monitor": 2, "zone": "right"},
        {"label": "VS Code", "app": "VS Code", "process": "code.exe", "monitor": 1, "zone": "full"}]}}))
    runner, _ = make_runner(api, cfg, launcher(api, []))
    out = runner.run(rs["x"], lambda h: None)
    assert out["failed"] == []
    by_title = {win.title: win for win in api.windows.values()}
    assert by_title["Claude"].rect == zone_rect(m1.work, "left")
    assert by_title["YouTube - Microsoft Edge"].rect == zone_rect(m2.work, "right")
    assert by_title["NEXA - Visual Studio Code"].zoomed


def test_window_larger_than_target_is_shrunk_to_fit():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    api.windows[1] = FakeWindow(pid=1, title="YouTube - Microsoft Edge", rect=(1900, 0, 4500, 1500), process="msedge.exe")
    runner, _ = make_runner(api, cfg, launcher(api, []))
    runner.run(load_routines(FakeConfig(routines={"x": {"name": "X", "steps": [
        {"label": "YouTube", "url": "https://www.youtube.com", "title": "YouTube", "monitor": 1}]}}))["x"], lambda h: None)
    assert api.windows[1].rect == m1.work


def test_reuses_open_windows_and_restores_minimized():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    api.windows[1] = FakeWindow(pid=1, title="Zalo", rect=(3000, 100, 3800, 900), process="zalo.exe", iconic=True)
    api.windows[2] = FakeWindow(pid=2, title="Bài hát hay - YouTube - Microsoft Edge", rect=(0, 0, 800, 600),
                                process="msedge.exe", zoomed=True)
    api.windows[3] = FakeWindow(pid=3, title="Tin tức - Microsoft Edge", rect=(0, 0, 800, 600), process="msedge.exe")
    launched = []
    runner, _ = make_runner(api, cfg, launcher(api, launched))
    out = runner.run(default_routines()["bat_dau_lam_viec"], lambda h: None)
    assert "Zalo" not in launched and "YouTube" not in launched
    assert not api.windows[1].iconic and api.windows[1].rect == (1080, 100, 1880, 900)
    assert api.windows[2].zoomed and api.windows[2].rect == m2.work          # vẫn phóng to, nhưng trên màn hình 2
    assert api.windows[3].rect == (0, 0, 800, 600)       # cửa sổ trình duyệt anh đang dùng không bị kéo đi
    assert out["failed"] == []


def test_web_page_still_loading_is_matched_when_only_one_left():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    runner, _ = make_runner(api, cfg, launcher(api, [], delay_title="ChatGPT"))
    out = runner.run(default_routines()["bat_dau_lam_viec"], lambda h: None)
    assert "ChatGPT" in out["placed"] and out["failed"] == []
    loading = next(win for win in api.windows.values() if win.title.startswith("Đang tải"))
    assert loading.rect == (2020, 100, 2820, 700)


def test_missing_window_and_launch_error_are_reported():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    base = launcher(api, [])

    def launch(step):
        if step.label == "Claude":
            return "chưa tìm thấy ứng dụng trên máy"
        if step.label == "Zalo":
            return None                                   # đã gửi lệnh mở nhưng cửa sổ không bao giờ hiện
        return base(step)

    runner, clock = make_runner(api, cfg, launch, wait_s=5.0)
    out = runner.run(default_routines()["bat_dau_lam_viec"], lambda h: None)
    failed = dict(out["failed"])
    assert failed["Claude"] == "chưa tìm thấy ứng dụng trên máy"
    assert failed["Zalo"] == "chưa thấy cửa sổ hiện ra"
    assert out["placed"] == ["YouTube", "ChatGPT", "VS Code"]
    assert clock.t < 10
    shown, spoken = summarize(default_routines()["bat_dau_lam_viec"], out, [])
    assert "3/5" in shown and "Claude" in spoken and "Zalo" in spoken


def test_single_monitor_puts_everything_on_it():
    m1 = mon(1, r"\\.\DISPLAY1", (0, 0, 1920, 1080), work=(0, 0, 1920, 1040), primary=True)
    api = FakeWin32(monitors=[m1])
    runner, _ = make_runner(api, FakeConfig(), launcher(api, []))
    out = runner.run(default_routines()["bat_dau_lam_viec"], lambda h: None)
    assert out["note"] and out["failed"] == []
    yt = next(win for win in api.windows.values() if win.title.startswith("YouTube"))
    assert yt.rect == (100, 100, 900, 700)


def test_cancel_stops_waiting():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    runner, clock = make_runner(api, cfg, lambda step: None, wait_s=25.0)
    out = runner.run(default_routines()["bat_dau_lam_viec"], lambda h: None, cancelled=lambda: clock.t > 1.0)
    assert out["cancelled"] and clock.t < 3


def test_denied_move_is_reported():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    api.windows[1] = FakeWindow(pid=1, title="Zalo", rect=(2000, 0, 2800, 600), process="zalo.exe", deny_move=True)
    runner, _ = make_runner(api, cfg, launcher(api, []))
    out = runner.run(default_routines()["bat_dau_lam_viec"], lambda h: None)
    assert ("Zalo", "Windows không cho di chuyển cửa sổ") in out["failed"]


# ----- công cụ run_routine -----
class _Token:
    cancelled = False


class _Apps:
    def __init__(self, api):
        self.api = api

    def browser_exe(self):
        return r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def test_run_routine_tool_places_and_checks_zalo(monkeypatch):
    from types import SimpleNamespace

    import nexa.desktop.routines as routines
    import nexa.desktop.zalo as zalo
    from nexa.ai.tool_registry import build_registry
    from nexa.core.events import ToolResult

    api, cfg, m1, m2 = dual_setup(left_negative=False)
    cfg["routines"] = DEFAULTS["routines"]
    monkeypatch.setattr(routines, "make_launcher", lambda apps: launcher(api, []))
    monkeypatch.setattr(zalo, "check_unread", lambda: ToolResult.success("Zalo có 2 cuộc trò chuyện chưa đọc. Chi tiết…"))
    monkeypatch.setattr(routines, "WAIT_S", 5.0)
    focused = []
    wm = SimpleNamespace(api=api, focus=focused.append)
    ctx = SimpleNamespace(token=_Token(), services=SimpleNamespace(config=cfg, apps=_Apps(api), wm=wm,
                                                                    monitors=MonitorManager(api, cfg)))
    monkeypatch.setattr(routines.time, "sleep", lambda s: None)
    res = routines.h_run_routine({"name": "bat_dau_lam_viec"}, ctx)
    assert res.ok, res.message
    assert "5/5" in res.message and "2 cuộc trò chuyện" in res.message
    assert res.data["spoken"] == "Đã mở xong 5 trên 5 ứng dụng. Zalo có 2 cuộc trò chuyện chưa đọc."
    assert len(focused) == 5
    assert routines.h_run_routine({"name": "nấu cơm"}, ctx).error_code == "not_found"
    spec = build_registry(cfg).get("run_routine")
    assert spec is not None and "Bắt đầu làm việc" in spec.description
