"""Mô hình 3D — tìm bộ phận, trạng thái viewer, công cụ/schema/executor, IntentRouter, cử chỉ VIEWER_3D."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import Services, build_registry, validate_schema
from nexa.core.events import Source, ToolCall
from nexa.core.executor import Executor
from nexa.core.safety import SafetyManager
from nexa.three_d.asset_store import AssetStore
from nexa.three_d.gesture_controller import ViewerGestureParams, ViewerGestureStateMachine, VState
from nexa.three_d.models import JobState
from nexa.three_d.part_resolver import resolve
from nexa.three_d.service import ThreeDService
from nexa.vision.gesture_features import Pose
from nexa.vision.gesture_state_machine import Observation

TOOLS_3D = ["generate_3d_model", "get_3d_job_status", "cancel_3d_job", "open_3d_model", "close_3d_viewer",
            "focus_3d_part", "isolate_3d_part", "hide_3d_part", "show_all_3d_parts", "show_3d_part_info",
            "explode_3d_assembly", "collapse_3d_assembly", "reset_3d_view", "rotate_3d_view", "zoom_3d_view",
            "rotate_3d_part", "reset_3d_part", "set_3d_render_mode", "list_3d_models", "export_3d_model"]


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    from nexa.utils.config import Config
    d = tmp_path_factory.mktemp("svc")
    cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
    cfg.set("three_d.ai_review", False)
    events = []
    s = ThreeDService(cfg, notify=lambda k, v: events.append((k, v)), store=AssetStore(d / "cache"), provider_factory=lambda: None)
    s.events = events
    ids = {}
    for key, prompt in (("uav", "Tạo UAV mini bốn cánh camera phía trước"), ("heli", "Tạo trực thăng cứu hộ"),
                        ("human", "Tạo robot hình người"), ("bolt", "Tạo bu-lông M8 dài 30 mm")):
        job = s.submit(prompt, open_when_ready=False)
        while not job.terminal:
            time.sleep(0.05)
        assert job.state == JobState.READY, job.message
        ids[key] = job.project_id
    s.ids = ids
    yield s
    s.shutdown()


# ------------------------------------------------------------------ resolver
def _parts(svc, key):
    return svc.store.load(svc.ids[key]).parts


@pytest.mark.parametrize("q,expected", [("cánh trước bên trái", ["propeller_front_left"]),
                                        ("propeller front left", ["propeller_front_left"]),
                                        ("motor phía sau bên phải", ["motor_rear_right"]),
                                        ("vỏ trên", ["shell_top"]), ("pin", ["battery"]),
                                        ("chong chóng trước phải", ["propeller_front_right"])])
def test_resolve_aliases_vi_en(svc, q, expected):
    r = resolve(_parts(svc, "uav"), q)
    assert r.ok and r.part_ids == expected


def test_resolve_ambiguous_asks_back(svc):
    r = resolve(_parts(svc, "uav"), "cánh quạt", model_name="UAV")
    assert r.status == "ambiguous" and len(r.part_ids) == 4
    assert r.message.startswith("UAV có bốn cánh quạt") and "trước trái" in r.message and "cả cụm" in r.message


def test_resolve_groups_and_plural(svc):
    heli = _parts(svc, "heli")
    main = resolve(heli, "rotor chính")
    assert main.ok and main.group == "main_rotor" and "main_rotor_hub" in main.part_ids
    tail = resolve(heli, "rotor đuôi")
    assert tail.ok and tail.group == "tail_rotor"
    assert len(resolve(_parts(svc, "uav"), "tất cả cánh quạt").part_ids) == 4
    cam = resolve(_parts(svc, "uav"), "cụm camera")
    assert set(cam.part_ids) == {"camera", "gimbal"}


def test_resolve_knee_and_deictic(svc):
    assert resolve(_parts(svc, "human"), "khớp đầu gối chân phải").part_ids == ["knee_right"]
    assert resolve(_parts(svc, "uav"), "bộ phận này", selected="battery").part_ids == ["battery"]
    assert resolve(_parts(svc, "uav"), "bánh răng").status == "not_found"


# ------------------------------------------------------------------ viewer state
def test_viewer_focus_hide_explode_collapse(svc):
    v = svc.viewer
    ok, msg = v.open(svc.ids["uav"])
    assert ok and v.is_open
    ok, msg, r = v.focus("cánh quạt")
    assert not ok and r.status == "ambiguous"
    ok, msg, r = v.focus("cánh trước bên trái")
    assert ok and v.focus_ids == ["propeller_front_left"] and v.state()["info"]["name"].startswith("Cánh quạt")
    assert "đường kính" in msg and v.frame_radius < v.project.bounds.radius
    ok, msg, _ = v.hide("lớp vỏ")
    assert ok and not v.visible["shell_top"] and not v.visible["shell_bottom"]
    assert v.explode()[0] and v.exploded and v.explode_seq == 1
    assert v.collapse()[0] and not v.exploded
    assert v.show_all()[0] and all(v.visible.values()) and not v.focus_ids
    v.rotate_view(400, 200)
    assert -180 <= v.yaw < 180 and v.pitch == 85
    assert v.reset_view()[0] and v.yaw == 35
    v.close()


def test_single_mesh_cannot_explode(svc):
    v = svc.viewer
    v.open(svc.ids["bolt"])
    ok, msg = v.explode()
    assert not ok and "assembly" in msg
    v.close()


def test_rotate_and_reset_part(svc):
    v = svc.viewer
    v.open(svc.ids["uav"])
    v.select("battery")
    ok, _, _ = v.rotate_part("bộ phận này", 90)
    assert ok and v.part_rot["battery"][1] == 90
    v.explode()
    assert v.reset_part("bộ phận này")[0] and "battery" not in v.part_rot and "battery" in v.assembled_override
    v.close()


# ------------------------------------------------------------------ tool schemas + executor
def test_tool_schemas_registered_and_valid(config):
    reg = build_registry(config)
    decl = {d["name"]: d for d in reg.gemini_declarations()}
    for name in TOOLS_3D:
        assert name in decl, name
        spec = reg.get(name)
        assert spec.needs_control is False and len(spec.description) > 20
    ok, err, _ = reg.validate("generate_3d_model", {"prompt": "x", "hack": 1}, Source.AI)
    assert not ok and "không được phép" in err
    ok, err, _ = reg.validate("rotate_3d_view", {"degrees": 999}, Source.AI)
    assert not ok


def _executor(svc, config):
    reg = build_registry(config)
    ex = Executor(reg, SafetyManager(), Services(config=config, three_d=svc), com_init=False)
    ex.start()
    return ex


def test_tools_via_executor_ambiguous_resume(svc, config):
    ex = _executor(svc, config)
    safety = ex.safety
    try:
        r = ex.execute(ToolCall("open_3d_model", {"project_id": svc.ids["uav"]}, Source.VOICE), safety.new_token())
        assert r.ok
        r = ex.execute(ToolCall("focus_3d_part", {"part": "cánh quạt"}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "ambiguous" and r.data["resume"] == "xem cánh quạt {}"
        r = ex.execute(ToolCall("explode_3d_assembly", {}, Source.VOICE), safety.new_token())
        assert r.ok and svc.viewer.exploded
        r = ex.execute(ToolCall("generate_3d_model", {"prompt": "tạo bu lông M6"}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "needs_input" and "{}" in r.data["resume"]
        t0 = time.monotonic()
        r = ex.execute(ToolCall("generate_3d_model", {"prompt": "Tạo đai ốc M12"}, Source.VOICE), safety.new_token())
        assert r.ok and r.data["job_id"] and time.monotonic() - t0 < 1.0   # trả job_id ngay, không chặn executor
    finally:
        svc.viewer.close()
        ex.stop()


def test_cloud_generation_needs_confirmation_from_ai(svc, config):
    reg = build_registry(config)
    spec = reg.get("generate_3d_model")
    ctx = SimpleNamespace(services=SimpleNamespace(three_d=svc))
    assert spec.assess({"prompt": "x", "mode": "cloud"}, ctx).needs_confirmation(Source.AI)
    assert not spec.assess({"prompt": "Tạo UAV", "mode": "auto"}, ctx).needs_confirmation(Source.AI)


def test_viewer_tools_blocked_when_paused(svc, config):
    ex = _executor(svc, config)
    try:
        ex.safety.emergency_stop("test")
        r = ex.execute(ToolCall("explode_3d_assembly", {}, Source.VOICE), ex.safety.new_token())
        assert not r.ok and r.error_code == "control_paused"
        r = ex.execute(ToolCall("get_3d_job_status", {}, Source.VOICE), ex.safety.new_token())
        assert r.ok
    finally:
        ex.stop()


# ------------------------------------------------------------------ IntentRouter
GEN = ["Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm.", "Tạo một UAV mini bốn cánh, thân carbon màu đen, camera phía trước.",
       "Tạo xe tự hành sáu bánh có LiDAR và camera.", "Tạo robot hình người.", "Tạo robot hình chó, mỗi chân có ba khớp.",
       "Tạo trực thăng cứu hộ có rotor chính và rotor đuôi."]


@pytest.mark.parametrize("text", GEN)
def test_router_generation_is_single_local_call(text, config):
    r = IntentRouter().route(text)
    assert r.kind == "basic" and len(r.calls) == 1 and r.calls[0][0] == "generate_3d_model"
    ok, err, _ = validate_schema(build_registry(config).get("generate_3d_model").parameters, r.calls[0][1])
    assert ok, err


@pytest.mark.parametrize("text,tool", [
    ("Xem chi tiết cánh quạt trước trái", "focus_3d_part"), ("Ẩn lớp vỏ", "hide_3d_part"),
    ("Tách riêng cụm camera", "isolate_3d_part"), ("Phóng to motor phía sau bên phải", "focus_3d_part"),
    ("Cho tôi xem rotor chính", "focus_3d_part"), ("Xem khớp đầu gối chân phải", "focus_3d_part"),
    ("Quay bộ phận này 90 độ", "rotate_3d_part"), ("Đưa bộ phận này về vị trí lắp", "reset_3d_part"),
    ("Hiện lại toàn bộ", "show_all_3d_parts"), ("Lắp mô hình lại", "collapse_3d_assembly"),
    ("Tách các bộ phận ra", "explode_3d_assembly"), ("đặt lại góc nhìn", "reset_3d_view"),
    ("quay sang trái 30 độ", "rotate_3d_view"), ("chế độ x quang", "set_3d_render_mode")])
def test_router_viewer_commands(text, tool):
    known = lambda p: p.lower() in {"cánh quạt trước trái", "lớp vỏ", "cụm camera", "motor phía sau bên phải",  # noqa: E731
                                    "rotor chính", "khớp đầu gối chân phải"}
    r = IntentRouter(viewer_active=lambda: True, part_known=known).route(text)
    assert r.kind == "basic" and r.calls[0][0] == tool, r


@pytest.mark.parametrize("text,tool", [("phóng to cửa sổ", "maximize_window"), ("xem thông tin hệ thống", "get_system_info"),
                                       ("tạo thư mục dự án", "create_folder"), ("tạo file word mới", "new_document"),
                                       ("thu nhỏ cửa sổ", "minimize_window")])
def test_router_old_commands_unchanged_with_viewer_open(text, tool):
    r = IntentRouter(viewer_active=lambda: True, part_known=lambda p: False).route(text)
    assert r.calls[0][0] == tool


def test_router_resume_after_ambiguous():
    r = IntentRouter(viewer_active=lambda: True, part_known=lambda p: True).route("trước trái", resume="xem cánh quạt {}")
    assert r.calls == [("focus_3d_part", {"part": "cánh quạt trước trái"})]


# ------------------------------------------------------------------ cử chỉ VIEWER_3D (landmark tổng hợp)
FPS, SCALE = 30, 0.2


class GSim:
    def __init__(self, **kw):
        self.sm = ViewerGestureStateMachine(ViewerGestureParams(**kw))
        self.t, self.x, self.y = 10.0, 0.6, 0.5
        self.events, self.exploded = [], False

    def f(self, pose, dx=0.0, dy=0.0):
        self.t += 1 / FPS
        if pose is None:
            out = self.sm.update(Observation(self.t, False), self.exploded)
        else:
            self.x += dx
            self.y += dy
            out = self.sm.update(Observation(self.t, True, pose, 0.9, (self.x, self.y), SCALE), self.exploded)
        for e in out:
            if e.kind == "explode":
                self.exploded = True
            elif e.kind == "collapse":
                self.exploded = False
        self.events += out
        return out

    def hold(self, pose, sec, **kw):
        for _ in range(int(round(sec * FPS))):
            self.f(pose, **kw)

    def count(self, kind):
        return sum(e.kind == kind for e in self.events)


def test_open_palm_direct_never_explodes():
    g = GSim()
    g.hold(Pose.OPEN_PALM, 2.0)
    assert g.count("explode") == 0 and g.sm.state == VState.ROTATE_READY


def test_open_swipe_rotates_yaw_and_pitch():
    g = GSim()
    g.hold(Pose.OPEN_PALM, 0.3)
    g.hold(Pose.OPEN_PALM, 0.5, dx=0.01)
    yaw = sum(e.dyaw for e in g.events if e.kind == "rotate")
    assert g.count("rotate") > 5 and yaw > 20 and g.count("explode") == 0
    g.hold(Pose.OPEN_PALM, 0.5, dy=-0.01)                            # tay đưa lên
    assert sum(e.dpitch for e in g.events if e.kind == "rotate") > 10


def test_entering_hand_motion_ignored():
    g = GSim()
    g.hold(Pose.OPEN_PALM, 0.4, dx=0.03)                             # đưa tay nhanh vào khung
    assert g.count("rotate") == 0


def test_short_fist_does_nothing():
    g = GSim()
    g.hold(Pose.FIST, 0.3)
    g.hold(Pose.OPEN_PALM, 1.0)
    assert g.count("explode") == 0


def test_fist_hold_arms_then_open_explodes_exactly_once():
    g = GSim()
    g.hold(Pose.FIST, 0.7)
    assert g.sm.state == VState.EXPLODE_ARMED
    g.hold(Pose.OPEN_PALM, 2.0)
    assert g.count("explode") == 1
    labels = [e.label for e in g.events if e.kind == "hud"]
    assert "Đang chuẩn bị tách… mở bàn tay và giữ yên" in labels and "Assembly đã tách" in labels


def test_rotate_after_explode_then_fist_collapses():
    g = GSim()
    g.hold(Pose.FIST, 0.7)
    g.hold(Pose.OPEN_PALM, 1.5)
    n = g.count("rotate")
    g.hold(Pose.OPEN_PALM, 0.6, dx=0.01)
    assert g.count("rotate") > n and g.exploded
    g.hold(Pose.FIST, 0.8)
    assert g.count("collapse") == 1 and not g.exploded


def test_fist_to_fast_open_does_not_explode():
    g = GSim()
    g.hold(Pose.FIST, 0.7)
    g.hold(Pose.OPEN_PALM, 1.0, dx=0.05)
    assert g.count("explode") == 0


def test_cooldown_blocks_immediate_retrigger():
    g = GSim(cooldown_ms=1500)
    g.hold(Pose.FIST, 0.7)
    g.hold(Pose.OPEN_PALM, 0.5)                                      # tách
    g.hold(Pose.FIST, 0.8)                                           # còn cooldown: chưa lắp
    assert g.count("explode") == 1 and g.count("collapse") == 0
    g.hold(Pose.OPEN_PALM, 1.5)
    g.hold(Pose.FIST, 0.8)
    assert g.count("collapse") == 1


def test_rotating_cannot_explode_without_new_fist():
    g = GSim()
    g.hold(Pose.OPEN_PALM, 0.3)
    g.hold(Pose.OPEN_PALM, 0.4, dx=0.01)
    g.hold(Pose.FIST, 0.2)                                           # nắm thoáng qua
    g.hold(Pose.OPEN_PALM, 1.0)
    assert g.count("explode") == 0


def test_hand_lost_resets_and_reacquire_does_not_jump():
    g = GSim()
    g.hold(Pose.FIST, 0.7)
    g.hold(None, 0.5)
    assert g.sm.state == VState.IDLE
    g.hold(Pose.OPEN_PALM, 1.0)
    assert g.count("explode") == 0                                   # chuẩn bị tách đã bị hủy khi mất tay
    g2 = GSim()
    g2.hold(Pose.OPEN_PALM, 0.3)
    g2.hold(Pose.OPEN_PALM, 0.3, dx=0.01)
    g2.hold(None, 0.5)
    g2.x += 0.3                                                      # tay xuất hiện lại ở chỗ khác
    n = len(g2.events)
    g2.hold(Pose.OPEN_PALM, 0.4)
    assert not [e for e in g2.events[n:] if e.kind == "rotate"]


def test_lost_hand_stops_rotation_immediately():
    g = GSim(inertia=0.9)
    g.hold(Pose.OPEN_PALM, 0.3)
    g.hold(Pose.OPEN_PALM, 0.4, dx=0.02)
    n = len(g.events)
    g.hold(None, 0.5)
    assert not [e for e in g.events[n:] if e.kind == "rotate"]


def test_locked_emits_nothing():
    g = GSim()
    g.sm.lock(True)
    g.hold(Pose.FIST, 0.8)
    g.hold(Pose.OPEN_PALM, 1.0, dx=0.01)
    assert not [e for e in g.events if e.kind != "hud"]


def test_two_finger_zoom():
    g = GSim()
    g.hold(Pose.TWO_FINGERS, 0.3)
    g.hold(Pose.TWO_FINGERS, 0.4, dy=-0.01)
    z = [e.factor for e in g.events if e.kind == "zoom"]
    assert z and all(f > 1 for f in z)                              # tay đưa lên → phóng to


def test_rotation_event_rate_matches_camera():
    g = GSim()
    g.hold(Pose.OPEN_PALM, 0.3)
    g.hold(Pose.OPEN_PALM, 1.0, dx=0.01)
    assert g.count("rotate") >= 20                                   # theo khung camera (~30 Hz), không phải 10 Hz


# ------------------------------------------------------------------ engine / controller
def _engine(config):
    from nexa.vision.engine import GestureEngine
    router = MagicMock()
    am = MagicMock()
    am.enabled = False
    eng = GestureEngine(config, config.settings_path.parent, MagicMock(), router, air_mouse=am)
    return eng, router, am


def test_viewer_mode_is_exclusive(config):
    eng, router, am = _engine(config)
    fed = []
    eng.set_viewer_mode(True, lambda obs, t: fed.append(obs))
    assert eng.viewer_mode
    am.release.assert_called()
    eng.set_mouse_mode(True)                                         # không bật được chuột bằng tay khi xem 3D
    am.set_enabled.assert_not_called()
    router.clear.assert_called()
    eng.set_viewer_mode(False)
    assert not eng.viewer_mode and eng._viewer_feed is None


def test_viewer_feed_does_not_touch_router_or_mouse(config, svc):
    """Mô phỏng vòng camera: ở chế độ viewer, nắm tay (= tạm dừng YouTube) không tới router, chuột không nhận gì."""
    eng, router, am = _engine(config)
    svc.viewer.open(svc.ids["uav"])
    eng.set_viewer_mode(True, svc.feed_gesture)
    t = 50.0
    for i in range(40):
        t += 1 / FPS
        obs = Observation(t, True, Pose.FIST, 0.9, (0.6, 0.5), SCALE)
        if eng.viewer_mode and eng._viewer_feed is not None:
            eng._viewer_feed(obs, time.monotonic())
            signals = []
        else:
            signals = eng.sm.update(obs)
        assert signals == []
    router.submit.assert_not_called()
    am.update.assert_not_called()
    assert svc.gesture_sm.state == VState.EXPLODE_ARMED
    svc.viewer.close()


def test_emergency_stop_locks_viewer_and_cancels_jobs(svc):
    svc.viewer.open(svc.ids["uav"])
    job = svc.submit("Tạo xe tự hành tám bánh dài 900 mm", open_when_ready=True)
    svc.on_emergency("test")
    assert job.state == JobState.CANCELLED and svc.gesture_sm.locked and svc.viewer.locked
    t = 100.0
    for _ in range(60):
        t += 1 / FPS
        svc.feed_gesture(Observation(t, True, Pose.FIST, 0.9, (0.5, 0.5), SCALE))
    assert not svc.viewer.exploded
    time.sleep(0.3)
    assert svc.viewer.project.id == svc.ids["uav"]                   # job đã hủy không mở viewer
    svc.on_resume_control()
    assert not svc.gesture_sm.locked
    svc.viewer.close()


def test_controller_viewer_mode_turns_off_air_mouse():
    from nexa.core.controller import Controller
    fake = MagicMock()
    fake.gestures.mouse_mode = True
    fake.gestures.running = True
    fake.config.get.return_value = False
    fake.code.panel_open = False
    fake.three_d.viewer.is_open = True
    fake._route_gestures = lambda: Controller._route_gestures(fake)
    Controller._on_viewer_mode(fake, True)
    fake.gestures.set_mouse_mode.assert_called_with(False)
    fake.gestures.set_viewer_mode.assert_called_with(True, fake.three_d.feed_gesture, name="3d")
    fake2 = MagicMock()
    Controller._on_emergency(fake2, "x")
    fake2.three_d.on_emergency.assert_called_with("x")


def test_air_mouse_refused_while_viewer_open():
    from nexa.core.controller import Controller
    fake = MagicMock()
    fake.safety.control_paused = False
    fake.three_d.viewer_active = True
    r = Controller.set_air_mouse(fake, True)
    assert not r.ok and r.error_code == "viewer_active"
