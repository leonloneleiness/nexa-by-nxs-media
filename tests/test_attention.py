"""Chú ý qua webcam: có ngồi ở máy không (khóa máy / dừng-phát video / chống nhìn trộm) + chọn màn hình theo hướng
quay đầu. Không camera thật, không khóa máy thật: Win32 giả lập, khuôn mặt tổng hợp."""
from __future__ import annotations

import os
import time
import types

import pytest

from fake_win32 import FakeWindow, dual_setup
from nexa.core.events import ToolResult
from nexa.desktop.monitors import MonitorManager
from nexa.desktop.window_history import WindowHistory
from nexa.desktop.windows import WindowManager
from nexa.vision.face_tracker import FaceObservation
from nexa.vision.head_monitor import HeadMonitorSelector, HeadParams
from nexa.vision.presence import AWAY, PRESENT, WARNING, PresenceMonitor, PresenceParams, split_faces


def face(yaw=0.0, pitch=0.0, size=0.08):
    return FaceObservation(yaw=yaw, pitch=pitch, size=size, center=(0.5, 0.5))


def kinds(events):
    return [e.kind for e in events]


# ------------------------------------------------------------------ có mặt (máy trạng thái thuần)
def run(pm, t0, t1, owner=False, onlookers=0, idle=999.0, step=0.1):
    out, t = [], t0
    while t <= t1 + 1e-9:
        out += pm.update(round(t, 3), owner, onlookers, idle)
        t += step
    return out


def test_presence_warns_then_goes_away_then_back():
    pm = PresenceMonitor(PresenceParams(away_after_s=45, warning_s=10))
    assert run(pm, 0, 1, owner=True) == []
    ev = run(pm, 1.1, 36.5)
    assert kinds(ev) == ["warning"] and pm.state == WARNING
    assert 9 < ev[0].seconds <= 10
    ev = run(pm, 36.6, 46.5)
    assert kinds(ev) == ["away"] and pm.state == AWAY
    assert run(pm, 46.6, 47.3, owner=True) == []          # thấy mặt chưa đủ return_s
    ev = run(pm, 47.4, 48.0, owner=True)
    assert kinds(ev) == ["back"] and pm.state == PRESENT and ev[0].seconds > 45


def test_presence_warning_is_cancelled_by_face_or_input():
    pm = PresenceMonitor(PresenceParams(away_after_s=45, warning_s=10))
    run(pm, 0, 36)
    assert pm.state == WARNING
    assert kinds(pm.update(36.1, True)) == ["cancel"] and pm.state == PRESENT
    run(pm, 36.2, 72)
    assert pm.state == WARNING
    assert kinds(pm.update(72.1, False, 0, 0.5)) == ["cancel"]


def test_recent_keyboard_counts_as_present_even_without_face():
    pm = PresenceMonitor(PresenceParams(away_after_s=45, warning_s=10))
    assert run(pm, 0, 120, idle=3.0) == [] and pm.state == PRESENT


def test_fresh_input_brings_back_from_away_but_old_input_does_not():
    pm = PresenceMonitor(PresenceParams(away_after_s=20, warning_s=5))
    run(pm, 0, 25)
    assert pm.state == AWAY
    assert pm.update(25.1, False, 0, 5.0) == []            # lần bấm cuối trước khi đi: không tính
    assert kinds(pm.update(25.2, False, 0, 0.3)) == ["back"]


def test_onlooker_needs_owner_and_persistence():
    p = PresenceParams()
    assert split_faces([0.08, 0.05], p) == (True, 1)
    assert split_faces([0.08, 0.02], p) == (True, 0)       # quá xa/nhỏ
    assert split_faces([0.08, 0.03], p) == (True, 0)       # nhỏ hơn 45 % mặt anh
    assert split_faces([], p) == (False, 0)
    pm = PresenceMonitor(p)
    assert run(pm, 0, 1.0, owner=True, onlookers=1) == []
    ev = run(pm, 1.1, 2.0, owner=True, onlookers=1)
    assert kinds(ev) == ["onlooker"] and pm.onlooker_active
    assert run(pm, 2.1, 3.5, owner=True) == []
    assert kinds(run(pm, 3.6, 4.5, owner=True)) == ["onlooker_gone"]


def test_presence_params_from_config_clamps_warning():
    p = PresenceParams.from_config({"away_after_s": 5, "warning_s": 30, "bogus": 1, "return_s": True})
    assert p.away_after_s == 5 and p.warning_s == 4 and p.return_s == 1.0


# ------------------------------------------------------------------ hướng quay đầu → màn hình
CENTERS = {"L": (-22.0, 0.0), "R": (18.0, -2.0)}


def feed(sel, t0, t1, yaw, pitch=0.0, step=0.05):
    key, t = None, t0
    while t <= t1 + 1e-9:
        key = sel.update(round(t, 3), yaw, pitch)
        t += step
    return key


def test_head_selects_nearest_center_with_dwell_and_hysteresis():
    sel = HeadMonitorSelector(HeadParams(), CENTERS)
    assert sel.ready
    assert feed(sel, 0, 0.5, -20) == "L"
    # lướt qua màn hình phải ngắn hơn dwell → không đổi
    assert feed(sel, 0.55, 0.7, 25) == "L"
    assert feed(sel, 0.75, 1.4, -21) == "L"
    # quay hẳn sang phải → đổi sau dwell
    assert feed(sel, 1.45, 2.4, 19) == "R"
    # ở giữa hai tâm (hơi lệch trái) → trễ giữ nguyên R
    assert feed(sel, 2.45, 3.5, -3) == "R"
    assert sel.looking_at(3.5) == "R"
    assert sel.looking_at(5.0) is None                     # mất mặt quá lâu


def test_head_not_ready_without_two_centers():
    sel = HeadMonitorSelector(HeadParams(), {"L": (-20.0, 0.0)})
    assert not sel.ready
    assert feed(sel, 0, 1, -20) is None


def test_head_calibration_median_and_rejects_duplicates():
    sel = HeadMonitorSelector(HeadParams(calib_s=1.5))
    got = []
    sel.start_calibration("L", 0.0, lambda k, c, m: got.append((k, c)))
    feed(sel, 0.0, 1.6, -20)
    assert got and got[0][0] == "L" and abs(got[0][1][0] + 20) < 0.5
    sel.start_calibration("R", 2.0, lambda k, c, m: got.append((k, c, m)))
    feed(sel, 2.0, 3.6, -18)                               # gần như trùng màn hình trái
    assert got[1][1] is None and "trùng" in got[1][2]
    sel.start_calibration("R", 4.0, lambda k, c, m: got.append((k, c)))
    feed(sel, 4.0, 5.6, 20)
    assert sel.ready and set(sel.centers) == {"L", "R"}


def test_head_calibration_fails_without_face():
    sel = HeadMonitorSelector(HeadParams(calib_s=1.0))
    got = []
    sel.start_calibration("L", 0.0, lambda k, c, m: got.append(c))
    feed(sel, 0.0, 1.2, None, None)
    assert got == [None] and sel.calibrating is None


# ------------------------------------------------------------------ dịch vụ (Win32 giả lập)
class FakeMedia:
    def __init__(self, playing=True):
        self.playing = playing
        self.calls = []

    def pause(self):
        self.calls.append("pause")
        was, self.playing = self.playing, False
        return ToolResult.success("Đã dừng", no_op=not was)

    def can_resume(self):
        return True

    def resume(self):
        self.calls.append("resume")
        self.playing = True
        return ToolResult.success("Đã phát tiếp")


class Env:
    def __init__(self, config, monkeypatch, presence=False, head="off", centers=None):
        from nexa.core import attention as att
        monkeypatch.setattr(att, "time", types.SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic))
        self.api, cfg, self.m1, self.m2 = dual_setup(left_negative=False)
        self.api.windows[10] = FakeWindow(pid=1, title="Soạn thảo - VS Code", rect=(100, 100, 1500, 900))
        self.api.windows[20] = FakeWindow(pid=2, title="YouTube - Edge", rect=(2000, 100, 4000, 1300), process="msedge.exe")
        self.api.windows[30] = FakeWindow(pid=3, title="Zalo", rect=(300, 200, 900, 800), process="Zalo.exe")
        self.api.foreground = 10
        self.mm = MonitorManager(self.api, cfg)
        self.wm = WindowManager(self.api, self.mm, WindowHistory("s"), own_pids={self.api.own}, sleep=lambda s: None)
        config.set("attention.presence_enabled", presence)
        config.set("attention.head_target", head)
        config.set("attention.head_calibration", centers or {})
        config.save = lambda: None
        self.config = config
        self.media = FakeMedia()
        self.idle = 999.0
        self.locked = False
        self.lock_calls = 0
        self.can = True
        self.cursor = (10, 10)
        self.moves = []
        self.events = []

        def lock():
            self.lock_calls += 1
            self.locked = True
            return True

        self.svc = att.AttentionService(
            config, self.wm, self.mm, self.media, lambda k, d: self.events.append((k, d)),
            input_idle_s=lambda: self.idle, can_act=lambda: self.can, camera_running=lambda: True,
            move_cursor=lambda x, y: self.moves.append((x, y)), cursor_pos=lambda: self.cursor,
            lock=lock, session_locked=lambda: self.locked, run_async=lambda fn, name: fn())

    def frames(self, t0, t1, faces, step=0.1):
        t = t0
        while t <= t1 + 1e-9:
            self.svc.on_faces(list(faces), round(t, 3))
            t += step

    def kinds(self):
        return [d["kind"] for k, d in self.events if k == "attention_event"]


def test_away_pauses_media_and_locks_then_resumes_after_unlock(config, monkeypatch):
    env = Env(config, monkeypatch, presence=True)
    env.frames(0, 1, [face()])
    env.frames(1.1, 46, [])
    assert env.kinds() == ["warning", "away"]
    assert env.media.calls == ["pause"] and env.lock_calls == 1
    env.locked = False                                     # anh mở khóa bằng PIN/Windows Hello
    env.frames(46.1, 47.5, [face()])
    assert "back" in env.kinds()
    env.svc._resume_waiter.join(2)
    assert env.media.calls == ["pause", "resume"]


def test_back_does_not_resume_media_nexa_did_not_pause(config, monkeypatch):
    env = Env(config, monkeypatch, presence=True)
    env.media.playing = False
    env.frames(0, 46, [])
    env.locked = False
    env.frames(46.1, 47.5, [face()])
    if env.svc._resume_waiter:
        env.svc._resume_waiter.join(2)
    assert env.media.calls == ["pause"] and env.lock_calls == 1


def test_away_does_nothing_while_control_paused(config, monkeypatch):
    env = Env(config, monkeypatch, presence=True)
    env.can = False
    env.frames(0, 46, [])
    assert "away" in env.kinds() and env.media.calls == [] and env.lock_calls == 0


def test_presence_disabled_never_locks(config, monkeypatch):
    env = Env(config, monkeypatch, presence=False)
    env.frames(0, 60, [])
    assert env.kinds() == [] and env.lock_calls == 0


def test_onlooker_minimizes_sensitive_windows_only(config, monkeypatch):
    env = Env(config, monkeypatch, presence=True)
    env.frames(0, 2.5, [face(size=0.08), face(size=0.06)])
    assert "onlooker" in env.kinds()
    assert env.api.windows[30].iconic                      # Zalo
    assert not env.api.windows[10].iconic and not env.api.windows[20].iconic


def test_voice_command_targets_monitor_user_looked_at(config, monkeypatch):
    env = Env(config, monkeypatch, head="commands",
              centers={env_key(2): [20.0, 0.0], env_key(1): [-20.0, 0.0]})
    t0 = time.monotonic()
    env.frames(t0, t0 + 0.6, [face(yaw=21)])               # nhìn màn hình 2 (bên phải)
    assert env.svc.looking_at().device_name == env.m2.device_name
    env.svc.capture_for_voice()
    env.svc.apply_for_voice()
    assert env.api.foreground == 20
    assert env.moves and env.moves[-1][0] >= 1920          # con trỏ sang màn hình 2 để cuộn đúng chỗ
    st = env.svc.status()
    assert st["head_monitor_name"] == "DISPLAY2" and st["head_ready"]


def test_head_off_does_not_touch_focus(config, monkeypatch):
    env = Env(config, monkeypatch, head="off", centers={env_key(2): [20.0, 0.0], env_key(1): [-20.0, 0.0]})
    t0 = time.monotonic()
    env.frames(t0, t0 + 0.6, [face(yaw=21)])
    env.svc.capture_for_voice()
    env.svc.apply_for_voice()
    env.svc.before_gesture()
    assert env.api.foreground == 10 and env.moves == []


def test_auto_mode_waits_for_idle_input(config, monkeypatch):
    env = Env(config, monkeypatch, head="auto", centers={env_key(2): [20.0, 0.0], env_key(1): [-20.0, 0.0]})
    env.idle = 0.2                                          # anh đang gõ phím
    t0 = time.monotonic()
    env.frames(t0, t0 + 1.5, [face(yaw=21)])
    assert env.api.foreground == 10
    env.idle = 3.0
    env.frames(t0 + 1.6, t0 + 1.8, [face(yaw=21)])
    assert env.api.foreground == 20


def test_calibration_saves_centers_and_enables_head_target(config, monkeypatch):
    env = Env(config, monkeypatch, head="off")
    env.frames(100.0, 100.0, [face()])
    done = []
    ok, msg = env.svc.calibrate(lambda ok, m: done.append((ok, m)))
    assert ok and env.svc.wants_faces()
    env.frames(100.05, 101.7, [face(yaw=-19)], step=0.05)  # màn hình trái (x nhỏ hơn) trước
    env.frames(101.75, 103.5, [face(yaw=17)], step=0.05)
    assert done and done[0][0], done
    cal = config.get("attention.head_calibration")
    assert cal[env_key(1)][0] < -15 and cal[env_key(2)][0] > 15
    assert config.get("attention.head_target") == "commands"


def env_key(n):
    from fake_win32 import mon
    return mon(n, rf"\\.\DISPLAY{n}", (0, 0, 1, 1)).device_id


def test_follow_attention_no_op_when_foreground_already_there():
    api, cfg, m1, m2 = dual_setup(left_negative=False)
    api.windows[10] = FakeWindow(pid=1, title="A", rect=(100, 100, 900, 700))
    api.windows[20] = FakeWindow(pid=2, title="B", rect=(2000, 100, 3000, 700))
    api.foreground = 10
    wm = WindowManager(api, MonitorManager(api, cfg), WindowHistory("s"), own_pids={api.own}, sleep=lambda s: None)
    r = wm.follow_attention(m1.device_name)
    assert r.ok and r.data.get("no_op")
    r = wm.follow_attention(m2.device_name)
    assert r.ok and api.foreground == 20 and r.data["hwnd"] == 20


# ------------------------------------------------------------------ câu lệnh giọng nói
@pytest.mark.parametrize("text,call", [
    ("bật tự khóa máy", ("set_presence_lock", {"enabled": True})),
    ("bật chế độ khóa máy khi anh rời đi", ("set_presence_lock", {"enabled": True})),
    ("tắt chống nhìn trộm", ("set_presence_lock", {"enabled": False})),
    ("hiệu chỉnh hướng nhìn", ("calibrate_head", {})),
    ("bật chọn màn hình theo hướng nhìn", ("set_head_target", {"mode": "commands"})),
    ("bật tự động chọn màn hình theo hướng quay đầu", ("set_head_target", {"mode": "auto"})),
    ("tắt chọn màn hình theo hướng nhìn", ("set_head_target", {"mode": "off"})),
])
def test_router(text, call):
    from nexa.ai.intent_router import IntentRouter
    assert IntentRouter().route(text).calls == [call]


# ------------------------------------------------------------------ giao diện
def test_gesture_panel_qml_loads_with_attention_section():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from nexa.utils.config import QML_DIR
    app = QGuiApplication.instance() or QGuiApplication([])
    calls = []

    class Fake(QObject):
        changed = Signal()
        cameraFrame = Signal(int)

        def _p(v, t="QVariantMap", sig=changed):
            return Property(t, lambda self: v, notify=sig)
        gestureStatus = _p({"face_error": ""})
        gestureLast = _p({})
        attentionStatus = _p({"presence": "warning", "faces": 2, "onlooker": True, "presence_enabled": True,
                              "head_target": "auto", "head_monitor_name": "DISPLAY2", "head_yaw": 18.5,
                              "head_pitch": -2.0, "head_ready": True, "head_calibrating": None, "face_active": True})
        mediaStatus = _p({})
        cameraOn = _p(True, bool)
        airMouse = _p(False, bool)
        showLandmarks = _p(False, bool)
        foreground = _p("", str)

        @Slot(bool)
        def setPreviewEnabled(self, v): pass

        @Slot(result="QVariantList")
        def monitors(self): return []

        @Slot()
        def refreshAttention(self): calls.append("refresh")

        @Slot(bool)
        def setPresence(self, v): calls.append(("presence", v))

        @Slot(str)
        def setHeadTarget(self, v): calls.append(("head", v))

        @Slot()
        def calibrateHead(self): calls.append("calib")

        @Slot()
        def toggleGestures(self): pass

        @Slot()
        def toggleAirMouse(self): pass

        @Slot(bool)
        def setShowLandmarks(self, v): pass

    fake = Fake()
    engine = QQmlEngine()
    warns: list[str] = []
    engine.warnings.connect(lambda ws: warns.extend(w.toString() for w in ws))
    engine.rootContext().setContextProperty("nexa", fake)
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "GesturePanel.qml")))
    obj = comp.create()
    app.processEvents()
    warns[:] = [w for w in warns if "image provider" not in w]      # khung camera: không cần trong test
    problems = [e.toString() for e in comp.errors()] + warns
    assert obj is not None and not problems, problems
    obj.setProperty("width", 520)
    obj.setProperty("height", 900)
    app.processEvents()
    from PySide6.QtQuick import QQuickItem
    texts = [i.property("text") for i in obj.findChildren(QQuickItem) if isinstance(i.property("text"), str)]
    assert any("sắp khóa" in t and "CÓ NGƯỜI PHÍA SAU" in t for t in texts), texts
    assert any(t.startswith("DISPLAY2") and "yaw 18.5" in t for t in texts)
    assert not [w for w in warns if "image provider" not in w], warns
