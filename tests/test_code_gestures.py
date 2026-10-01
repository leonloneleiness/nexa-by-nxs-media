"""Cử chỉ khi bảng Sinh code mở: nắm tay giữ yên = lưu, búng tay = chạy thử, hai ngón = cuộn (như cần điều khiển).
Định tuyến camera: bảng code > viewer 3D > sáu cử chỉ lệnh; búng tay qua mic cũng chạy thử khi bảng mở."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from nexa.code.gesture_controller import CodeGestureParams, CodeGestureStateMachine, CState
from nexa.code.models import CodeFile, CodeResult
from nexa.vision.gesture_features import Pose
from nexa.vision.gesture_state_machine import Observation

DT = 1 / 30


class Feed:
    def __init__(self, sm: CodeGestureStateMachine) -> None:
        self.sm, self.t, self.events = sm, 10.0, []

    def frames(self, n: int, pose: Pose = Pose.UNKNOWN, y: float | list = 0.5, present: bool = True, **kw) -> list:
        out = []
        for i in range(n):
            yy = y[i] if isinstance(y, list) else y
            obs = Observation(t=self.t, present=present, pose=pose, confidence=0.95, center=(0.6, yy), scale=0.2, **kw)
            out += self.sm.update(obs)
            self.t += DT
        self.events += out
        return out


def kinds(evs, k):
    return [e for e in evs if e.kind == k]


def test_fist_hold_saves_once_until_released():
    f = Feed(CodeGestureStateMachine())
    evs = f.frames(40, Pose.FIST)                         # ~1.3 s giữ yên
    assert len(kinds(evs, "save")) == 1
    assert any(e.kind == "hud" and e.state == "FIST_HOLD" and 0 < e.progress < 1 for e in evs)
    f.frames(30, Pose.FIST)                               # vẫn nắm: không lưu lần 2
    assert len(kinds(f.events, "save")) == 1
    f.frames(20, Pose.OPEN_PALM)                          # mở tay rồi nắm lại (đã qua cooldown)
    f.frames(40, Pose.FIST)
    assert len(kinds(f.events, "save")) == 2


def test_short_or_moving_fist_does_nothing():
    f = Feed(CodeGestureStateMachine())
    f.frames(12, Pose.FIST)                               # 0.4 s < 0.7 s
    f.frames(10, Pose.OPEN_PALM)
    f.frames(40, Pose.FIST, y=[0.2 + 0.03 * i for i in range(40)])   # nắm tay nhưng đang kéo tay đi
    assert not kinds(f.events, "save")


def test_snap_runs():
    f = Feed(CodeGestureStateMachine())
    f.frames(8, Pose.UNKNOWN, snap_ready=True)
    evs = f.frames(2, Pose.UNKNOWN, snap_released=True)
    assert len(kinds(evs, "run")) == 1
    f.frames(2, Pose.UNKNOWN, snap_released=True)         # cùng một cú búng: không chạy lần 2
    assert len(kinds(f.events, "run")) == 1
    huds = [e.label for e in kinds(f.events, "hud")]
    assert any("chạy thử" in h for h in huds)


def test_snap_disabled_by_config():
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {"code.gesture": {}, "audio.snap.camera": False, "audio.snap.enabled": True}.get(k)
    assert CodeGestureParams.from_config(cfg).snap_enabled is False


def test_two_fingers_scroll_like_joystick():
    f = Feed(CodeGestureStateMachine())
    f.frames(15, Pose.TWO_FINGERS, y=0.5)                 # thu nhận + ghi điểm neo
    assert f.sm.state == CState.SCROLL_READY
    assert not kinds(f.events, "scroll")
    f.frames(4, Pose.TWO_FINGERS, y=[0.5 + 0.02 * i for i in range(1, 5)])
    down = kinds(f.frames(15, Pose.TWO_FINGERS, y=0.62), "scroll")   # tay thấp hơn neo 0.6 kích thước tay
    assert down and all(e.dy > 0 for e in down)
    slow = sum(e.dy for e in down[-5:])
    far = kinds(f.frames(15, Pose.TWO_FINGERS, y=0.75), "scroll")    # xa hơn → nhanh hơn
    assert sum(e.dy for e in far[-5:]) > slow
    f.frames(20, Pose.TWO_FINGERS, y=0.5)                 # về điểm neo → dừng
    assert not kinds(f.frames(5, Pose.TWO_FINGERS, y=0.5), "scroll")
    up = kinds(f.frames(15, Pose.TWO_FINGERS, y=0.38), "scroll")
    assert up and all(e.dy < 0 for e in up)


def test_scroll_stops_when_hand_lost_or_pose_changes():
    f = Feed(CodeGestureStateMachine())
    f.frames(15, Pose.TWO_FINGERS, y=0.5)
    f.frames(15, Pose.TWO_FINGERS, y=0.7)
    assert kinds(f.events, "scroll")
    assert not kinds(f.frames(15, present=False), "scroll")
    assert f.sm.state == CState.IDLE
    f.frames(15, Pose.TWO_FINGERS, y=0.7)                 # quay lại: neo mới tại chỗ tay → chưa cuộn
    assert not kinds(f.frames(5, Pose.TWO_FINGERS, y=0.7), "scroll")


def test_invert_scroll():
    f = Feed(CodeGestureStateMachine(CodeGestureParams(invert_scroll=True)))
    f.frames(15, Pose.TWO_FINGERS, y=0.5)
    evs = kinds(f.frames(20, Pose.TWO_FINGERS, y=0.7), "scroll")
    assert evs and all(e.dy < 0 for e in evs)


def test_locked_emits_nothing():
    sm = CodeGestureStateMachine()
    sm.lock(True)
    f = Feed(sm)
    f.frames(40, Pose.FIST)
    f.frames(8, snap_ready=True)
    f.frames(2, snap_released=True)
    assert not [e for e in f.events if e.kind != "hud"]


# ---------- CodeService ----------

def _svc(config, tmp_path):
    from nexa.code.service import CodeService
    config.set("code.save_dir", str(tmp_path / "saved"))
    svc = CodeService(config, history_dir=tmp_path / "hist")
    events = []
    svc._notify = lambda kind, data: events.append((kind, data))       # type: ignore[method-assign]
    res = CodeResult("g1", "p", "Chào NEXA", "python", "s", [CodeFile("main.py", "python", "print('hi')\n")])
    svc.current = res
    svc._store(res)
    return svc, events, res


def test_panel_open_switches_gesture_mode(config, tmp_path):
    svc, events, _ = _svc(config, tmp_path)
    calls = []
    svc.on_panel_mode = calls.append
    svc.set_panel_open(True)
    svc.set_panel_open(True)
    svc.set_panel_open(False)
    assert calls == [True, False] and not svc.panel_open


def test_fist_frames_save_without_duplicates(config, tmp_path):
    svc, events, res = _svc(config, tmp_path)
    f = Feed(svc.gesture_sm)
    f.sm = type("S", (), {"update": lambda _s, obs: svc.feed_gesture(obs)})()
    f.frames(40, Pose.FIST)
    saved = list((tmp_path / "saved").iterdir())
    assert len(saved) == 1 and (saved[0] / "main.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert any(k == "code_toast" and "Đã lưu code" in d["text"] for k, d in events)
    assert any(k == "code_gesture" and d.get("kind") == "hud" for k, d in events)
    ok, msg = svc.gesture_save()                          # chưa đổi code → không tạo thư mục trùng
    assert ok and "đã lưu rồi" in msg and len(list((tmp_path / "saved").iterdir())) == 1
    res.files[0].content = "print('mới')\n"
    assert svc.gesture_save()[0] and len(list((tmp_path / "saved").iterdir())) == 2


def test_gesture_save_without_code(config, tmp_path):
    svc, events, _ = _svc(config, tmp_path)
    svc.current = None
    ok, _ = svc.gesture_save()
    assert not ok and any(k == "code_toast" and d["error"] for k, d in events)


def test_gesture_run_prefers_current_code_or_reruns_file(config, tmp_path, monkeypatch):
    svc, _, res = _svc(config, tmp_path)
    calls = []
    monkeypatch.setattr(svc, "run_tests", lambda rid="": calls.append(("tests", rid)) or (True, "ok"))
    monkeypatch.setattr(svc, "rerun", lambda: calls.append(("rerun",)) or (True, "ok"))
    monkeypatch.setattr(svc, "SNAP_DEBOUNCE_S", 0.0)
    svc.gesture_run()
    svc.live = MagicMock(source="file")
    svc.gesture_run("mic")
    svc.live = MagicMock(source="code")
    svc.gesture_run()
    assert calls == [("tests", "g1"), ("rerun",), ("tests", "g1")]


def test_second_snap_stops_run_and_returns_to_code(config, tmp_path, monkeypatch):
    svc, events, _ = _svc(config, tmp_path)
    monkeypatch.setattr(svc, "SNAP_DEBOUNCE_S", 0.0)
    runs = []

    def fake_run(rid=""):
        runs.append(rid)
        svc.live = MagicMock(source="code", running=True)
        svc.panel_view = "run"                               # như _live_begin: bảng chuyển sang kết quả
        return True, "ok"
    monkeypatch.setattr(svc, "run_tests", fake_run)
    assert svc.gesture_run()[0] and runs == ["g1"]          # búng 1: chạy
    live = svc.live
    ok, msg = svc.gesture_run()                              # búng 2: tắt + về màn hình code
    assert ok and "tắt" in msg and runs == ["g1"]
    live.stop.assert_called_once()
    assert svc.panel_view == "code" and ("code_open", {"view": "code"}) in events
    svc.gesture_run()                                        # búng 3: chạy lại
    assert runs == ["g1", "g1"]
    svc.live.running = False                                 # chạy xong rồi mới búng → chỉ về màn hình code
    svc.set_panel_view("run")
    ok, msg = svc.gesture_run()
    assert ok and msg == "Về màn hình code." and svc.panel_view == "code"


def test_double_detected_snap_counts_once(config, tmp_path, monkeypatch):
    svc, _, _ = _svc(config, tmp_path)
    runs = []
    monkeypatch.setattr(svc, "run_tests", lambda rid="": runs.append(rid) or (True, "ok"))
    svc.gesture_run("camera")
    svc.gesture_run("mic")                                   # cùng một cái búng, mic bắt trễ một chút
    assert runs == ["g1"] and svc.panel_view == "code"


def test_scroll_events_reach_ui(config, tmp_path):
    svc, events, _ = _svc(config, tmp_path)
    f = Feed(svc.gesture_sm)
    f.sm = type("S", (), {"update": lambda _s, obs: svc.feed_gesture(obs)})()
    f.frames(15, Pose.TWO_FINGERS, y=0.5)
    f.frames(15, Pose.TWO_FINGERS, y=0.7)
    ds = [d["dy"] for k, d in events if k == "code_gesture" and d.get("kind") == "scroll"]
    assert ds and all(v > 0 for v in ds)


def test_emergency_locks_code_gestures(config, tmp_path):
    svc, _, _ = _svc(config, tmp_path)
    svc.on_emergency("x")
    assert svc.gesture_sm.locked
    svc.on_resume_control()
    assert not svc.gesture_sm.locked


# ---------- controller / engine / bridge ----------

def test_route_gestures_priority():
    from nexa.core.controller import Controller
    fake = MagicMock()
    fake.code.panel_open, fake.three_d.viewer.is_open = True, True
    Controller._route_gestures(fake)
    fake.gestures.set_viewer_mode.assert_called_with(True, fake.code.feed_gesture, name="code")
    fake.code.panel_open = False
    Controller._route_gestures(fake)
    fake.gestures.set_viewer_mode.assert_called_with(True, fake.three_d.feed_gesture, name="3d")
    fake.three_d.viewer.is_open = False
    Controller._route_gestures(fake)
    fake.gestures.set_viewer_mode.assert_called_with(False)


def test_code_panel_turns_off_air_mouse():
    from nexa.core.controller import Controller
    fake = MagicMock()
    fake.gestures.mouse_mode = True
    fake.config.get.return_value = False
    Controller._on_code_panel(fake, True)
    fake.gestures.set_mouse_mode.assert_called_with(False)
    fake._route_gestures.assert_called()


def test_air_mouse_refused_while_code_panel_open():
    from nexa.core.controller import Controller
    fake = MagicMock()
    fake.safety.control_paused = False
    fake.three_d.viewer_active = False
    fake.code.panel_open = True
    r = Controller.set_air_mouse(fake, True)
    assert not r.ok and r.error_code == "code_panel_open"


def test_mic_snap_runs_code_when_panel_open(monkeypatch):
    from nexa.core import controller as ctl
    monkeypatch.setattr(ctl, "_ms_since_last_input", lambda: None)
    fake = MagicMock()
    fake.clap_test = False
    fake.code.panel_open = True
    ctl.Controller._on_snap(fake, MagicMock(peak_db=-20.0))
    fake.code.gesture_run.assert_called_with("mic")
    fake.three_d.toggle_animation.assert_not_called()
    fake.code.panel_open = False
    ctl.Controller._on_snap(fake, MagicMock(peak_db=-20.0))
    fake.three_d.toggle_animation.assert_called_with("mic")


def test_engine_exclusive_mode_name(config):
    from nexa.vision.engine import GestureEngine
    eng = GestureEngine(config, Path("."), MagicMock(), MagicMock())
    feed = MagicMock()
    eng.set_viewer_mode(True, feed, name="code")
    assert eng.viewer_mode and eng.exclusive_mode == "code" and eng._viewer_feed is feed
    eng.set_viewer_mode(False)
    assert not eng.viewer_mode and eng.exclusive_mode == "" and eng._viewer_feed is None


def test_bridge_panel_and_gesture_events(config, tmp_path, qapp=None):
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    from nexa.ui.code_bridge import CodeBridge
    svc, _, _ = _svc(config, tmp_path)
    ctl = MagicMock(code=svc, config=config)
    b = CodeBridge(ctl)
    svc._notify = lambda k, d: b.post(k, d)               # type: ignore[method-assign]
    modes = []
    svc.on_panel_mode = modes.append
    got = []
    b.gestureScroll.connect(got.append)
    b.openPanel()
    assert svc.panel_open and modes == [True]
    b.post("code_gesture", {"kind": "scroll", "dy": 12.5})
    b.post("code_gesture", {"kind": "hud", "state": "FIST_HOLD", "label": "giữ", "progress": 0.4})
    app.processEvents()
    assert got == [12.5] and b.gesture["state"] == "FIST_HOLD" and b.gesture["progress"] == 0.4
    b.setView("web")
    assert svc.panel_view == "web"
    b.closePanel()
    app.processEvents()
    assert not svc.panel_open and modes == [True, False]
