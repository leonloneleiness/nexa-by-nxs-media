"""Chuyển động cơ khí của mô hình 3D và búng tay (mic + camera) để bật/tắt chuyển động."""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest
from hand_synth import make_hand
from test_clap import knock, noise, speech

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import Services, build_registry, validate_schema
from nexa.audio.pipeline import AudioPipeline
from nexa.audio.snap_detector import SR, SnapConfig, SnapDetector
from nexa.core.events import Source, ToolCall
from nexa.core.executor import Executor
from nexa.core.safety import SafetyManager
from nexa.three_d.asset_store import AssetStore
from nexa.three_d.benchmark import by_group
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.gesture_controller import ViewerGestureParams, ViewerGestureStateMachine, VState
from nexa.three_d.models import JobState
from nexa.three_d.motion import infer_motions
from nexa.three_d.planner import Planner
from nexa.three_d.service import ThreeDService
from nexa.vision.gesture_features import Pose, classify
from nexa.vision.gesture_state_machine import Observation

MOVING = {"uav", "helicopter", "car", "gearbox", "robot_arm", "excavator", "crane", "humanoid", "quadruped",
          "wind_turbine", "cylinder", "bearing", "belt_drive", "chain_drive", "fixed_wing", "rover", "train"}
STATIC = {"bolt", "nut", "washer", "bracket", "bridge", "steel_truss", "storage_tank"}


# ------------------------------------------------------------------ suy luận chuyển động
@pytest.fixture(scope="module")
def built():
    planner = Planner(None, use_gemini=False)
    seen: dict[str, str] = {}
    for cases in by_group().values():
        for c in cases:
            seen.setdefault(c.category, c.prompt)
    out = {}
    for cat, prompt in seen.items():
        spec = planner.plan(prompt).spec
        parts = [p.part for p in build_parametric(spec).parts]
        out[cat] = (parts, *infer_motions(spec.category, parts))
    return out


def test_every_category_gets_motion(built):
    assert len(built) >= 40
    for cat, (parts, chains, mode) in built.items():
        assert mode in ("parts", "turntable"), cat
        assert any(chains.get(p.id) for p in parts), cat
        for ch in chains.values():
            for m in ch:
                assert m["t"] in ("spin", "swing", "slide") and len(m["a"]) == 3, (cat, m)


def test_mechanisms_move_their_own_parts(built):
    for cat in MOVING:
        assert built[cat][2] == "parts", cat
    for cat in STATIC:
        assert built[cat][2] == "turntable", cat


def _own(built, cat):
    parts, chains, _ = built[cat]
    return {p.id: chains[p.id][-1] for p in parts if chains.get(p.id)}


def test_uav_propellers_spin_and_body_stays(built):
    own = _own(built, "uav")
    props = [pid for pid in own if pid.startswith("propeller")]
    assert len(props) == 4 and all(own[p]["t"] == "spin" for p in props)
    assert "frame" not in own and "battery" not in own
    signs = {np.sign(own[p]["s"]) for p in props}
    assert signs == {-1.0, 1.0}                       # hai cặp cánh quay ngược chiều nhau


def test_gearbox_gears_counter_rotate(built):
    spins = [m for m in _own(built, "gearbox").values() if m["t"] == "spin"]
    assert len(spins) >= 2
    assert {np.sign(m["s"]) for m in spins} == {-1.0, 1.0}


def test_robot_arm_joints_chain(built):
    parts, chains, _ = built["robot_arm"]
    depth = max(len(ch) for ch in chains.values())
    assert depth >= 3                                 # khớp sau mang theo chuyển động của khớp trước
    assert any(m["t"] == "swing" for ch in chains.values() for m in ch)


def test_cylinder_rod_strokes(built):
    own = _own(built, "cylinder")
    assert any(m["t"] == "slide" for m in own.values())


# ------------------------------------------------------------------ viewer + công cụ + câu lệnh
@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    from nexa.utils.config import Config
    d = tmp_path_factory.mktemp("motion")
    cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
    cfg.set("three_d.ai_review", False)
    events = []
    s = ThreeDService(cfg, notify=lambda k, v: events.append((k, v)), store=AssetStore(d / "cache"), provider_factory=lambda: None)
    s.events = events
    s.ids = {}
    for key, prompt in (("uav", "Tạo UAV mini bốn cánh camera phía trước"), ("bolt", "Tạo bu-lông M8 dài 30 mm"),
                        ("robot_arm", "Tạo cánh tay robot công nghiệp 6 trục"), ("pump", "Tạo máy bơm ly tâm trục ngang")):
        job = s.submit(prompt, open_when_ready=False)
        while not job.terminal:
            time.sleep(0.05)
        assert job.state == JobState.READY, job.message
        s.ids[key] = job.project_id
    yield s
    s.shutdown()


def _moved(m: dict, g: np.ndarray, deg: float) -> float:
    """Độ dời của điểm g khi chuyển động quay m đi một góc deg quanh trục a qua tâm c."""
    a, c = np.asarray(m["a"], float), np.asarray(m["c"], float)
    a /= np.linalg.norm(a)
    r = g - c
    th = np.radians(deg)
    rot = r * np.cos(th) + np.cross(a, r) * np.sin(th) + a * np.dot(a, r) * (1 - np.cos(th))
    return float(np.linalg.norm(rot - r))


def _project(svc, key):
    from nexa.three_d.motion import _Builder
    from nexa.three_d.viewer_controller import ViewerController
    pid = svc.ids[key]
    project = svc.store.load(pid)
    geom = ViewerController.mesh_geom(project, str(svc.store.project_dir(pid)))
    b = _Builder(project.category, project.parts, geom)
    b.build()
    return b, geom


def test_spin_centre_on_real_axis(svc):
    """Cánh quạt 3 lá: tâm hộp bao lệch khỏi trục motor → phải quay quanh trọng tâm lưới (không đảo vòng)."""
    b, geom = _project(svc, "uav")
    props = [pid for pid, m in b.own.items() if m["t"] == "spin" and b.by[pid].cat == "propeller"]
    assert len(props) == 4
    for pid in props:
        g = geom.centroid(pid)
        span = float(np.max(b.by[pid].size))
        assert _moved(b.own[pid], g, 180) < 0.01 * span, pid


def test_hinges_stay_on_their_joint(svc):
    """Mỗi khớp tay robot quay quanh vùng tiếp xúc với khâu cha: vùng đó không trượt khi khớp quay hết biên độ."""
    b, geom = _project(svc, "robot_arm")
    swings = {pid: m for pid, m in b.own.items() if m["t"] == "swing"}
    assert len(swings) >= 5
    for pid, m in swings.items():
        p = b.by[pid]
        par = b.parent(p)
        g = geom.contact(pid, par.id, float(min(np.max(p.size), np.max(par.size))))
        assert g is not None, pid
        deg = abs(m["amp"]) + abs(m["off"])
        assert _moved(m, g, deg) <= 0.03 * float(np.max(p.size)), pid


def test_static_guard_and_fasteners(svc):
    """Chụp che khớp nối đứng yên; khớp nối quay đồng trục với trục bơm."""
    b, _ = _project(svc, "pump")
    chains = b.chains()
    assert not chains.get("coupling_guard")
    assert chains["coupling"][0]["t"] == "spin" and abs(chains["coupling"][0]["a"][2]) > 0.99


def test_fasteners_follow_rotating_hub(built):
    parts, chains, _ = built["shaft_coupling"]
    screws = [p for p in parts if p.category in ("set_screw", "screw", "bolt", "key")]
    assert screws
    for p in screws:
        par = next(q for q in parts if q.id == p.parent_id)
        if chains.get(par.id):
            assert chains.get(p.id), p.id


def test_toggle_requires_open_viewer(svc):
    svc.viewer.close()
    ok, _ = svc.toggle_animation("mic")
    assert not ok and not svc.viewer.animating


def test_viewer_payload_and_toggle(svc):
    svc.events.clear()
    svc.viewer.open(svc.ids["uav"])
    try:
        assert svc.viewer.motion_mode == "parts" and not svc.viewer.animating
        ok, _ = svc.toggle_animation("mic")
        assert ok and svc.viewer.animating
        assert any(k == "3d_toast" for k, _ in svc.events)
        ok, _ = svc.toggle_animation("camera")
        assert ok and not svc.viewer.animating
        ok, _ = svc.set_animation(False)
        assert ok and not svc.viewer.animating      # tắt khi đang tắt: vẫn ok, không đảo trạng thái
    finally:
        svc.viewer.close()


def test_static_part_uses_turntable(svc):
    svc.viewer.open(svc.ids["bolt"])
    try:
        ok, msg = svc.set_animation(True)
        assert ok and svc.viewer.motion_mode == "turntable" and "xoay trưng bày" in msg
    finally:
        svc.viewer.close()


def test_camera_snap_event_toggles_viewer(svc):
    from nexa.three_d.gesture_controller import ViewerEvent
    svc.viewer.open(svc.ids["uav"])
    try:
        svc.viewer.apply_gesture(ViewerEvent("motion_toggle", 1.0))
        assert svc.viewer.animating
        svc.viewer.apply_gesture(ViewerEvent("motion_toggle", 2.0))
        assert not svc.viewer.animating
    finally:
        svc.viewer.close()


def test_motion_tool_via_executor(svc, config):
    reg = build_registry(config)
    spec = reg.get("set_3d_motion")
    assert spec is not None
    assert validate_schema(spec.parameters, {"on": False})[0]
    ex = Executor(reg, SafetyManager(), Services(config=config, three_d=svc), com_init=False)
    ex.start()
    try:
        tok = ex.safety.new_token
        r = ex.execute(ToolCall("set_3d_motion", {"on": True}, Source.VOICE), tok())
        assert not r.ok                               # chưa mở viewer
        svc.viewer.open(svc.ids["uav"])
        r = ex.execute(ToolCall("set_3d_motion", {"on": True}, Source.VOICE), tok())
        assert r.ok and svc.viewer.animating
        r = ex.execute(ToolCall("set_3d_motion", {"on": False}, Source.VOICE), tok())
        assert r.ok and not svc.viewer.animating
    finally:
        svc.viewer.close()
        ex.stop()


@pytest.mark.parametrize("text,on", [
    ("cho mô hình chuyển động", True), ("mô phỏng hoạt động", True), ("chạy thử mô hình", True),
    ("bật chế độ chuyển động", True), ("cho nó chạy thử đi", True),
    ("dừng chuyển động", False), ("tắt chuyển động của mô hình", False), ("cho mô hình dừng lại", False)])
def test_router_motion_phrases(text, on):
    r = IntentRouter(viewer_active=lambda: True, part_known=lambda p: False).route(text)
    assert r.calls and r.calls[0] == ("set_3d_motion", {"on": on}), r


@pytest.mark.parametrize("text", ["cho mô hình chuyển động", "dừng chuyển động"])
def test_router_motion_needs_viewer(text):
    r = IntentRouter(viewer_active=lambda: False, part_known=lambda p: False).route(text)
    assert not r.calls or r.calls[0][0] != "set_3d_motion"


@pytest.mark.parametrize("text,tool", [("dừng tạo mô hình", "cancel_3d_job"), ("đặt lại góc nhìn", "reset_3d_view")])
def test_router_neighbours_unchanged(text, tool):
    r = IntentRouter(viewer_active=lambda: True, part_known=lambda p: False).route(text)
    assert r.calls[0][0] == tool


# ------------------------------------------------------------------ búng tay qua mic
_rng = np.random.default_rng(7)


def _burst(db, f0, bw, tau, dur=0.05):
    n = int(SR * dur)
    t = np.arange(n) / SR
    spec = np.fft.rfft(_rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec *= np.exp(-((f - f0) / bw) ** 2)
    y = np.fft.irfft(spec, n) * np.exp(-t / tau)
    y *= 10 ** (db / 20) / (np.sqrt(np.mean(y[:160] ** 2)) + 1e-12)
    return y.astype(np.float32)


def snap_sound(db=-30.0, f0=3000.0):
    return _burst(db, f0, 1400, 0.003)


def clap_sound(db=-22.0):
    return _burst(db, 1200, 1300, 0.009)


def _snaps(sig, **cfg):
    det = SnapDetector(SnapConfig(**cfg))
    ev = []
    for i in range(0, len(sig), 320):
        ev += det.process(sig[i:i + 320], i / SR)
    return [e for e in ev if e.kind == "trigger"]


@pytest.mark.parametrize("sound", [snap_sound(), snap_sound(-18), snap_sound(f0=2500)])
def test_snap_detected(sound):
    assert len(_snaps(np.concatenate([noise(2.5), sound, noise(1)]))) == 1


@pytest.mark.parametrize("sound", [clap_sound(), clap_sound(-32), speech(), knock()])
def test_non_snap_sounds_rejected(sound):
    assert _snaps(np.concatenate([noise(2.5), sound, noise(1)])) == []


def test_silence_no_snap_and_cooldown():
    assert _snaps(noise(4)) == []
    sig = np.concatenate([noise(2.5), snap_sound(), noise(0.3), snap_sound(), noise(1)])
    assert len(_snaps(sig, cooldown_ms=900)) == 1


class _Fake:
    def __init__(self, schedule):
        self.schedule = schedule        # t_chunk -> list[event]

    def process(self, x, t0):
        return self.schedule.pop(round(t0, 2), [])


def _pipe(config, gate, snaps, claps):
    got = {"snap": [], "clap": []}
    p = AudioPipeline(config, on_clap=lambda e: got["clap"].append(e.t), on_snap=lambda e: got["snap"].append(e.t),
                      snap_gate=lambda: gate)
    p.snap = _Fake({t: [SimpleNamespace(t=t, kind="trigger", peak_db=-30.0)] for t in snaps})
    p.clap = _Fake({t: [SimpleNamespace(t=t, kind="trigger")] for t in claps})
    x = np.zeros(160, np.float32)
    for i in range(300):
        p._detect_transients(x, round(i * 0.01, 2))
    return got


def test_snap_suppresses_its_clap_when_viewer_open(config):
    got = _pipe(config, True, snaps=[1.0], claps=[1.0, 1.02])
    assert got == {"snap": [1.0], "clap": []}


def test_clap_before_snap_is_held_and_dropped(config):
    got = _pipe(config, True, snaps=[1.05], claps=[1.0])
    assert got == {"snap": [1.05], "clap": []}


def test_real_clap_passes_when_viewer_open(config):
    got = _pipe(config, True, snaps=[], claps=[1.0])
    assert got == {"snap": [], "clap": [1.0]}


def test_snap_ignored_and_clap_direct_when_viewer_closed(config):
    got = _pipe(config, False, snaps=[1.0], claps=[2.0])
    assert got == {"snap": [], "clap": [2.0]}


def test_snap_disabled_in_config(config):
    config.set("audio.snap.enabled", False)
    got = _pipe(config, True, snaps=[1.0], claps=[2.0])
    assert got == {"snap": [], "clap": [2.0]}


# ------------------------------------------------------------------ búng tay qua camera
@pytest.mark.parametrize("pose,ready,released", [("snap_ready", True, False), ("snap_released", False, True),
                                                 ("open", False, False), ("fist", False, False),
                                                 ("point", False, False), ("two", False, False)])
@pytest.mark.parametrize("angle", [-30, 0, 30])
def test_snap_hand_features(pose, ready, released, angle):
    rng = np.random.default_rng(3)
    for _ in range(20):
        f = classify(make_hand(pose, angle_deg=angle, jitter=0.002, rng=rng))
        assert f.snap_ready == ready, (pose, angle)
        if pose != "snap_released":
            assert not f.snap_released, (pose, angle)
        else:
            assert f.snap_released


def test_snap_shape_keeps_system_poses():
    assert classify(make_hand("open")).pose == Pose.OPEN_PALM
    assert classify(make_hand("fist")).pose == Pose.FIST


FPS = 30


class SnapSim:
    def __init__(self, **kw):
        self.sm = ViewerGestureStateMachine(ViewerGestureParams(**kw))
        self.t = 10.0
        self.events = []

    def frame(self, ready=False, released=False, pose=Pose.UNKNOWN):
        self.t += 1 / FPS
        obs = Observation(self.t, True, pose, 0.9, (0.5, 0.5), 0.2, snap_ready=ready, snap_released=released)
        self.events += self.sm.update(obs, False)

    def snap(self, ready_frames=5, gap_frames=1):
        for _ in range(ready_frames):
            self.frame(ready=True)
        for _ in range(gap_frames):
            self.frame()
        self.frame(released=True)
        for _ in range(3):
            self.frame(released=True)

    def count(self):
        return sum(e.kind == "motion_toggle" for e in self.events)


def test_camera_snap_fires_once():
    g = SnapSim()
    g.snap()
    assert g.count() == 1 and g.sm.state == VState.IDLE


def test_camera_snap_needs_ready_hold():
    g = SnapSim()
    g.snap(ready_frames=1)
    assert g.count() == 0


def test_camera_snap_window_expires():
    g = SnapSim()
    g.snap(gap_frames=20)
    assert g.count() == 0


def test_camera_snap_cooldown_then_again():
    g = SnapSim()
    g.snap()
    g.snap()
    assert g.count() == 1
    for _ in range(30):
        g.frame()
    g.snap()
    assert g.count() == 2


def test_camera_snap_disabled():
    g = SnapSim(snap_enabled=False)
    g.snap()
    assert g.count() == 0


def test_released_alone_does_nothing():
    g = SnapSim()
    for _ in range(10):
        g.frame(released=True)
    assert g.count() == 0
