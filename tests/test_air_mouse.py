"""Chuột bằng tay: di chuyển, click, kéo thả, click phải, cuộn, nhả nút an toàn (landmarks tổng hợp, chuột giả)."""
from __future__ import annotations

import numpy as np
import pytest

from hand_synth import make_hand
from nexa.vision.air_mouse import AirMouse, MouseParams, clamp_to_monitors, mouse_frame

MONITORS = [(0, 0, 1920, 1200), (1920, 0, 3840, 1080)]
FPS = 30.0


class FakeMouse:
    def __init__(self, x=960, y=600):
        self.pos = (x, y)
        self.moves: list[tuple[int, int]] = []
        self.buttons: list[tuple[str, bool]] = []
        self.scrolls: list[int] = []

    def position(self):
        return self.pos

    def move_to(self, x, y):
        self.pos = (x, y)
        self.moves.append((x, y))

    def button(self, button, down):
        self.buttons.append((button, down))

    def scroll(self, notches):
        self.scrolls.append(notches)


def pinch_hand(finger: str = "index", pose: str = "point", **kw) -> np.ndarray:
    h = make_hand(pose, **kw)
    tip = 8 if finger == "index" else 12
    h[4, :2] = h[tip, :2] + 0.004
    h[3, :2] = (h[2, :2] + h[4, :2]) / 2
    return h


def mouse(**overrides) -> tuple[AirMouse, FakeMouse]:
    out = FakeMouse()
    params = MouseParams(**{"min_cutoff": 50.0, "beta": 0.0, **overrides})     # gần như không lọc: test tất định
    am = AirMouse(params, out, monitors=lambda: MONITORS, primary=lambda: MONITORS[0])
    am.set_enabled(True)
    return am, out


class Feeder:
    def __init__(self, am: AirMouse):
        self.am, self.t = am, 0.0

    def __call__(self, hand, frames: int = 1):
        acts = []
        for _ in range(frames):
            acts += self.am.update(mouse_frame(hand), self.t)
            self.t += 1 / FPS
        return acts

    def move(self, pose, x0, y0, x1, y1, frames, **kw):
        acts = []
        for i in range(frames + 1):
            f = i / frames
            hand = pose(cx=x0 + (x1 - x0) * f, cy=y0 + (y1 - y0) * f, **kw) if callable(pose) else \
                make_hand(pose, cx=x0 + (x1 - x0) * f, cy=y0 + (y1 - y0) * f)
            acts += self(hand)
        return acts


def test_disabled_does_nothing():
    am, out = mouse()
    am.set_enabled(False)
    feed = Feeder(am)
    feed.move("open", 0.4, 0.5, 0.6, 0.5, 10)
    assert out.moves == [] and out.buttons == []


def test_relative_movement_follows_hand_and_invert_x():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("open", 0.4, 0.5, 0.6, 0.5, 10)
    assert out.pos[0] > 960 + 100 and abs(out.pos[1] - 600) < 5
    feed.move("open", 0.6, 0.5, 0.6, 0.3, 10)
    assert out.pos[1] < 600 - 100

    am2, out2 = mouse(invert_x=True)
    Feeder(am2).move("open", 0.4, 0.5, 0.6, 0.5, 10)
    assert out2.pos[0] < 960 - 100


def test_acceleration_fast_goes_farther():
    am_slow, slow = mouse()
    Feeder(am_slow).move("open", 0.4, 0.5, 0.55, 0.5, 30)
    am_fast, fast = mouse()
    Feeder(am_fast).move("open", 0.4, 0.5, 0.55, 0.5, 5)
    assert fast.pos[0] - 960 > (slow.pos[0] - 960) * 1.3


def test_still_hand_with_jitter_barely_moves():
    am, out = mouse(min_cutoff=1.0, beta=0.4)
    rng = np.random.default_rng(0)
    feed = Feeder(am)
    for _ in range(60):
        feed(make_hand("open", jitter=0.0008, rng=rng))
    assert abs(out.pos[0] - 960) < 15 and abs(out.pos[1] - 600) < 15


def test_fist_is_clutch_no_move_and_no_jump():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("open", 0.5, 0.5, 0.52, 0.5, 3)
    before = out.pos
    feed.move("fist", 0.52, 0.5, 0.3, 0.5, 15)          # nắm tay đưa tay về trái: con trỏ đứng yên
    assert abs(out.pos[0] - before[0]) < 40
    feed.move("open", 0.3, 0.5, 0.3, 0.5, 5)            # xòe lại ở chỗ mới: không nhảy
    assert abs(out.pos[0] - before[0]) < 40
    assert out.buttons == []


def test_pinch_click_at_pointed_position():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("point", 0.4, 0.5, 0.5, 0.5, 10)
    feed(make_hand("point", cx=0.5, cy=0.5), 5)          # dừng tay trên nút
    pre = out.pos
    acts = feed(pinch_hand(cx=0.5, cy=0.5), 4)
    assert "press" in acts and out.buttons == [("left", True)]
    acts = feed(make_hand("point", cx=0.5, cy=0.5), 2)
    assert "click" in acts and out.buttons == [("left", True), ("left", False)]
    assert out.pos == pre


def test_pinch_rewinds_small_drift_before_detection():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("point", 0.4, 0.5, 0.5, 0.5, 10)
    feed(make_hand("point", cx=0.5, cy=0.5), 5)
    pre = out.pos
    feed(pinch_hand(cx=0.503, cy=0.5))                   # khung chụm đầu tiên (chưa đủ pinch_frames): lòng tay trôi nhẹ
    assert out.pos != pre
    assert "press" in feed(pinch_hand(cx=0.503, cy=0.5))
    assert out.pos == pre                                  # nhấn đúng chỗ anh đã dừng tay


def test_no_rewind_jump_when_pinching_while_moving_fast():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("point", 0.3, 0.5, 0.5, 0.5, 6)
    moving = out.pos
    feed(pinch_hand(cx=0.5, cy=0.5), 3)
    assert abs(out.pos[0] - moving[0]) <= 40


def test_pinch_small_wobble_stays_click_not_drag():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("point", 0.5, 0.5, 0.5, 0.5, 5)
    feed(pinch_hand(cx=0.5, cy=0.5), 3)
    locked_at = out.pos
    n = len(out.moves)
    feed.move(pinch_hand, 0.5, 0.5, 0.52, 0.5, 6)        # xê dịch nhỏ < drag_start
    assert out.moves[n:] == [] and out.pos == locked_at
    assert "click" in feed(make_hand("point", cx=0.52, cy=0.5), 2)


def test_pinch_drag_moves_while_held():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("point", 0.4, 0.5, 0.4, 0.5, 3)
    feed(pinch_hand(cx=0.4, cy=0.5), 3)
    start = out.pos
    acts = feed.move(pinch_hand, 0.4, 0.5, 0.6, 0.5, 12)
    assert "drag_start" in acts and out.pos[0] > start[0] + 100
    assert out.buttons == [("left", True)]                # vẫn đang giữ
    assert "drag_end" in feed(make_hand("point", cx=0.6, cy=0.5), 2)
    assert out.buttons[-1] == ("left", False)


def test_right_click_once_per_pinch():
    am, out = mouse()
    feed = Feeder(am)
    feed(make_hand("open"), 3)
    acts = feed(pinch_hand("middle", pose="open"), 6)
    assert acts.count("right_click") == 1 and out.buttons == [("right", True), ("right", False)]
    feed(make_hand("open"), 3)
    feed(pinch_hand("middle", pose="open"), 3)
    assert out.buttons.count(("right", True)) == 2


def test_fist_and_thumb_tucked_point_never_click():
    am, out = mouse()
    feed = Feeder(am)
    feed(make_hand("fist"), 20)
    feed(make_hand("point"), 20)
    feed(make_hand("thumb"), 20)
    assert out.buttons == []


def test_ambiguous_pinch_between_index_and_middle_ignored():
    am, out = mouse()
    h = make_hand("open")
    h[4, :2] = (h[8, :2] + h[12, :2]) / 2               # ngón cái chạm đúng giữa hai đầu ngón
    Feeder(am)(h, 6)
    assert out.buttons == []


def test_two_fingers_scroll_direction_and_invert():
    am, out = mouse()
    feed = Feeder(am)
    feed(make_hand("two", cy=0.6), 4)
    n = len(out.moves)
    feed.move("two", 0.5, 0.6, 0.5, 0.4, 12)             # đưa lên
    assert sum(out.scrolls) > 0 and out.moves[n:] == []   # cuộn, con trỏ không chạy
    am2, out2 = mouse(invert_scroll=True)
    f2 = Feeder(am2)
    f2(make_hand("two", cy=0.6), 4)
    f2.move("two", 0.5, 0.6, 0.5, 0.4, 12)
    assert sum(out2.scrolls) < 0


def test_lost_hand_while_dragging_releases_button():
    am, out = mouse()
    feed = Feeder(am)
    feed(pinch_hand(), 3)
    assert out.buttons == [("left", True)]
    am.lost(feed.t + 0.1)
    assert out.buttons == [("left", True)]                # chưa đủ lost_hand_ms
    am.lost(feed.t + 0.5)
    assert out.buttons[-1] == ("left", False)


@pytest.mark.parametrize("how", ["disable", "locked", "params"])
def test_release_on_disable_lock_and_reload(how):
    allowed = {"v": True}
    out = FakeMouse()
    am = AirMouse(MouseParams(min_cutoff=50.0, beta=0.0), out, monitors=lambda: MONITORS,
                  can_control=lambda: allowed["v"])
    am.set_enabled(True)
    feed = Feeder(am)
    feed(pinch_hand(), 3)
    if how == "disable":
        am.set_enabled(False)
    elif how == "locked":
        allowed["v"] = False
        feed(pinch_hand(), 1)
    else:
        am.update_params(MouseParams())
    assert out.buttons == [("left", True), ("left", False)]


def test_yields_to_physical_mouse():
    am, out = mouse()
    feed = Feeder(am)
    feed.move("open", 0.4, 0.5, 0.45, 0.5, 3)
    out.pos = (200, 200)                                 # anh cầm chuột thật kéo đi
    n = len(out.moves)
    assert "yield" in feed(make_hand("open", cx=0.46))
    feed.move("open", 0.46, 0.5, 0.6, 0.5, 10)           # trong yield_ms: không giành
    assert out.moves[n:] == [] and out.pos == (200, 200)
    feed(make_hand("open", cx=0.6), 25)                  # hết 1 s
    feed.move("open", 0.6, 0.5, 0.7, 0.5, 5)
    assert out.pos[0] > 200


def test_clamp_dead_zone_and_failsafe_corners():
    assert clamp_to_monitors(2500, 1150, MONITORS) == (2500, 1079)       # dưới màn hình 2 thấp hơn
    assert clamp_to_monitors(-50, 500, MONITORS) == (0, 500)
    x, y = clamp_to_monitors(-10, -10, MONITORS, MONITORS[0], 3)
    assert (x, y) != (0, 0) and x >= 3                                    # không vào góc fail-safe
    x, y = clamp_to_monitors(1919, 1199, MONITORS, MONITORS[0], 3)
    assert x <= 1916
    assert clamp_to_monitors(1919, 5, MONITORS, MONITORS[0], 3) == (1919, 5)   # mép phải nhưng không phải góc


def test_absolute_mapping_center_and_edges():
    am, out = mouse(mapping="absolute")
    feed = Feeder(am)
    feed(make_hand("open", cx=0.5, cy=0.4), 3)
    feed(make_hand("open", cx=0.5, cy=0.5), 3)
    assert abs(out.pos[0] - 1920) < 80
    feed.move("open", 0.5, 0.5, 0.05, 0.5, 10)
    assert out.pos[0] <= 10


def test_params_from_config():
    p = MouseParams.from_config({"mouse": {"gain": 500, "mapping": "absolute", "pinch_frames": "3"},
                                 "calibration": {"invert_x": True}})
    assert p.gain == 500.0 and p.mapping == "absolute" and p.pinch_frames == 3 and p.invert_x is True


# ----- tích hợp: engine, controller, lệnh giọng nói, công cụ -----
from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402


class FailSafeException(Exception):
    """Cùng tên với pyautogui.FailSafeException (engine nhận theo tên lớp)."""


def _engine(config, am, on_failsafe=None):
    from nexa.vision.engine import GestureEngine
    return GestureEngine(config, config.settings_path.parent, MagicMock(), MagicMock(), air_mouse=am,
                         on_failsafe=on_failsafe)


def test_engine_mouse_mode_toggle_and_stop_releases(config):
    am, out = mouse()
    am.set_enabled(False)
    eng = _engine(config, am)
    eng.set_mouse_mode(True)
    assert eng.mouse_mode
    feed = Feeder(am)
    feed(pinch_hand(), 3)
    eng.stop("tắt")
    assert not eng.mouse_mode and out.buttons[-1] == ("left", False)


def test_engine_failsafe_corner_triggers_emergency(config):
    class CornerMouse(FakeMouse):
        def move_to(self, x, y):
            raise FailSafeException("góc")
    out = CornerMouse()
    am = AirMouse(MouseParams(min_cutoff=50.0, beta=0.0), out, monitors=lambda: MONITORS)
    fired = []
    eng = _engine(config, am, on_failsafe=lambda: fired.append(1))
    eng.set_mouse_mode(True)
    for i in range(6):
        eng._drive_mouse(SimpleNamespace(landmarks=make_hand("open", cx=0.4 + i * 0.03)), None, 4 / 3, i / FPS)
    assert fired == [1] and not eng.mouse_mode


def test_engine_hand_lost_releases_via_drive(config):
    am, out = mouse()
    eng = _engine(config, am)
    for i in range(3):
        eng._drive_mouse(SimpleNamespace(landmarks=pinch_hand()), None, 4 / 3, i / FPS)
    eng._drive_mouse(None, None, 4 / 3, 1.0)
    assert out.buttons == [("left", True), ("left", False)]


def _fake_controller(running=False, paused=False, start_ok=True):
    from nexa.core.events import ToolResult
    fake = MagicMock()
    fake.safety.control_paused = paused
    fake.gestures.running = running
    state = {"mouse": False}
    fake.gestures.set_mouse_mode.side_effect = lambda on: state.update(mouse=on)
    type(fake.gestures).mouse_mode = property(lambda self: state["mouse"])

    def start(on):
        fake.gestures.running = start_ok
        return ToolResult.success("ok") if start_ok else ToolResult.failure("không mở được camera", "camera")
    fake.set_gesture_mode.side_effect = start
    return fake, state


def test_controller_set_air_mouse_starts_camera_first():
    from nexa.core.controller import Controller
    fake, state = _fake_controller(running=False)
    r = Controller.set_air_mouse(fake, True)
    assert r.ok and state["mouse"] and fake.set_gesture_mode.called
    r = Controller.set_air_mouse(fake, False)
    assert r.ok and not state["mouse"]


def test_controller_set_air_mouse_refused_when_locked_or_no_camera():
    from nexa.core.controller import Controller
    fake, state = _fake_controller(paused=True)
    r = Controller.set_air_mouse(fake, True)
    assert not r.ok and r.error_code == "control_paused" and not state["mouse"]
    fake, state = _fake_controller(start_ok=False)
    r = Controller.set_air_mouse(fake, True)
    assert not r.ok and not state["mouse"]


def test_emergency_stop_turns_air_mouse_off():
    from nexa.core.controller import Controller
    fake = MagicMock()
    fake._ai_token = None
    fake._awake = False
    Controller._on_emergency(fake, "Ctrl+Alt+Esc")
    fake.gestures.set_mouse_mode.assert_called_with(False)
    fake.input.release_all.assert_called()


@pytest.mark.parametrize("text,enabled", [("bật chuột bằng tay", True), ("Nexa, bật chế độ chuột ảo", True),
                                          ("sử dụng chuột bằng tay", True), ("tắt chuột bằng tay", False),
                                          ("dừng chuột bằng tay", False), ("thôi chuột bằng tay", False)])
def test_voice_commands(text, enabled):
    from nexa.ai.intent_router import IntentRouter
    r = IntentRouter().route(text)
    assert r.kind == "basic" and r.calls == [("set_air_mouse", {"enabled": enabled})]


def test_voice_gesture_mode_unchanged():
    from nexa.ai.intent_router import IntentRouter
    assert IntentRouter().route("bật điều khiển bằng tay").calls == [("set_gesture_mode", {"enabled": True})]


def test_tool_registered_and_calls_hook(config):
    from nexa.ai.tool_registry import build_registry, h_air_mouse
    from nexa.core.events import ToolResult
    reg = build_registry(config)
    spec = reg.get("set_air_mouse")
    assert spec is not None and spec.needs_control is False
    seen = []
    ctx = SimpleNamespace(services=SimpleNamespace(hooks={"set_air_mouse": lambda on: seen.append(on)
                                                          or ToolResult.success("ok")}))
    assert h_air_mouse({"enabled": True}, ctx).ok and seen == [True]


def test_mouse_defaults_in_config(config):
    p = MouseParams.from_config(config.gestures)
    assert p.mapping == "relative" and p.pinch_on < p.pinch_off
