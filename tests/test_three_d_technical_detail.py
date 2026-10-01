"""Mô hình kỹ thuật chi tiết: thư viện chi tiết (rãnh ghép, ốc, khe gió, cáp…), vật liệu PBR có texture, tangent cho
normal map, mẫu thuyền/tàu mới và việc không để bộ phận xuyên nhau/lơ lửng."""
from __future__ import annotations

import itertools

import numpy as np
import pytest

from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.generation.templates import details as D
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.pipeline import ModelBuild
from nexa.three_d.planner import LocalPlanner, Planner
from nexa.three_d.quality import assess
from nexa.three_d.spec import normalize, validate_spec


def build(cat, **params):
    sp = normalize(validate_spec({"category": cat, "params": params}))
    asm = build_parametric(sp)
    rep = assess(sp, ModelBuild.from_assembly(asm).part_data(), mode="parametric", metadata=asm.metadata)
    return sp, asm, rep


# ------------------------------------------------------------------ thư viện chi tiết
def test_detail_library_produces_valid_solids():
    outer = K.rounded_box(400, 250, 100, 20)
    g = D.panel_lines(outer, [("x", 60), ("z", 30)], 2.0, 1.5)
    assert g.volume() > 0 and (outer - g).volume() < outer.volume()
    assert D.screws_at(D.corner_points(0, 0, 400, 250, 50, 18), (0, 0, 1), 5).status_ok
    v = D.vent_cutter((0, 125, 0), (0, 1, 0), (1, 0, 0), 120, 30, 6, 4)
    assert len((outer - v).split_components()) == 1 and v.volume() > 0
    wire, plugs = D.cable([(0, 0, 0), (50, 20, 30), (100, 0, 60)], 3)
    assert wire.volume() > 0 and plugs.volume() > 0
    base, cap = D.estop_button(20)
    assert base.status_ok and cap.status_ok
    ring = D.outline_groove(outer, (0, 0, 0), 150, 60, 2, 1.5)
    assert ring.volume() > 0
    assert D.surface_at(outer, "y", (0, 0, 0), positive=True) == pytest.approx(125, abs=0.5)
    assert D.surface_at(outer, "z", (0, 0, 0), positive=False) == pytest.approx(-50, abs=0.5)
    assert D.surface_at(outer, "y", (1000, 0, 0)) is None


def test_micro_textures_generated_and_tiled_in_real_units(tmp_path):
    mats = M.library()
    assert mats["aluminum"].textures["normal"].endswith("brushed_normal.png")
    assert mats["rubber"].textures["normal"].endswith("rubber_normal.png")
    assert M.texture_tile_mm(mats["paint_primary"]) == 140.0
    out = M.write_textures(tmp_path, {"brushed_normal", "rubber_normal", "paint_normal", "plastic_normal"})
    from PIL import Image
    for rel in out.values():
        im = Image.open(tmp_path / rel)
        assert im.size == (256, 256) and im.mode == "RGB"
        arr = np.asarray(im, float)
        assert 150 < arr[..., 2].mean() < 256                       # normal map: kênh Z (lam) trội


def test_assembly_adds_uvs_for_textured_materials():
    _, asm, _ = build("rover", wheel_count=4)
    tire = asm.part("wheel_front_left")
    assert all(m.uvs is not None and len(m.uvs) == len(m.vertices) for m, mid in tire.meshes if asm.materials[mid].textures)


def test_viewer_tangents_are_orthonormal():
    from nexa.ui.three_d_bridge import _tangents, pack_mesh
    m = K.rounded_box(40, 30, 20, 4).to_mesh().with_box_uv(10)
    uv = m.uvs.copy()
    uv[:, 1] = 1 - uv[:, 1]
    t, bt = _tangents(m.vertices, m.faces, m.normals, uv)
    assert np.allclose(np.linalg.norm(t, axis=1), 1, atol=1e-6) and np.allclose(np.linalg.norm(bt, axis=1), 1, atol=1e-6)
    assert np.abs(np.einsum("ij,ij->i", t, m.normals)).max() < 1e-6
    pm = pack_mesh(m.vertices, m.faces, m.normals, m.uvs, np.zeros(3), 1.0)
    assert pm.stride == 56 and pm.has_uv


# ------------------------------------------------------------------ mẫu kỹ thuật: điểm + không xuyên nhau
@pytest.mark.parametrize("cat,params", [
    ("rover", {"wheel_count": 6}), ("rover", {"wheel_count": 8, "suspension": "independent"}),
    ("humanoid", {}), ("humanoid", {"hands": "gripper", "head_sensor": "camera"}),
    ("quadruped", {}), ("quadruped", {"joints_per_leg": 2}),
    ("uav", {"arm_count": 4}), ("uav", {"arm_count": 6, "battery": "top"}), ("uav", {"arm_count": 8, "battery": "bottom", "camera": "bottom"}),
    ("helicopter", {}), ("helicopter", {"landing": "wheels", "role": "medical"}),
    ("boat", {"boat_type": "speedboat"}), ("boat", {"boat_type": "fishing", "length_mm": 12000}),
    ("boat", {"boat_type": "yacht", "engines": 2}), ("boat", {"boat_type": "patrol"}),
    ("boat", {"boat_type": "speedboat", "engines": 3, "cabin": False, "railings": False}),
])
def test_technical_templates_pass_all_gates(cat, params):
    _, asm, rep = build(cat, **params)
    failed = [k for k, g in rep.gates.items() if not g["ok"]]
    assert rep.total >= 99 and not failed, (rep.total, failed, [c for c in rep.checks if not c.get("ok", True)][:4])
    assert asm.triangle_count < 450_000


def test_uav_known_clash_pairs_fixed():
    """Trước đây: pin sau lấn vỏ trên 1.138 mm³, bo mạch chạm vỏ, pin dưới đè camera dưới, GPS xuyên pin."""
    for params in ({"arm_count": 4}, {"arm_count": 6, "battery": "top"}, {"arm_count": 8, "battery": "bottom", "camera": "bottom"}):
        _, asm, _ = build("uav", **params)
        pairs = [("battery", "shell_top"), ("flight_controller", "shell_top"), ("battery", "camera"), ("gps", "battery"),
                 ("battery", "antenna")]
        for a, b in pairs:
            pa, pb = asm.part(a), asm.part(b)
            if pa is not None and pb is not None:
                assert pa.solid.intersection_volume(pb.solid) < 1.0, (params, a, b)


def test_uav_bottom_battery_with_bottom_camera_moves_and_warns():
    _, asm, _ = build("uav", arm_count=4, battery="bottom", camera="bottom")
    assert any("pin được chuyển ra phía sau" in w for w in asm.warnings)


def test_humanoid_visor_not_coincident_with_head():
    _, asm, _ = build("humanoid")
    head = asm.part("head")
    mats = {asm.materials[mid].id for _, mid in head.meshes}
    assert {"glass_tinted", "sensor_black", "led_white"} <= mats
    joints = [bp for bp in asm.parts if bp.part.category == "joint"]
    assert all(any(asm.materials[mid].id == "steel" for _, mid in j.meshes) for j in joints if j.part.id != "abdomen")


# ------------------------------------------------------------------ thuyền/tàu
@pytest.mark.parametrize("text,kind,extra", [
    ("Tạo ca nô cao tốc dài 6 m màu trắng", "speedboat", {"length_mm": 6000.0}),
    ("Tạo tàu cá dài 12 m", "fishing", {"length_mm": 12000.0}),
    ("tạo du thuyền 20 mét hai máy", "yacht", {"length_mm": 20000.0, "engines": 2}),
    ("Tạo tàu tuần tra có máy trong", "patrol", {"propulsion": "inboard"}),
    ("Tạo xuồng máy hai máy gắn ngoài, không lan can", "speedboat", {"engines": 2, "propulsion": "outboard", "railings": False}),
])
def test_boat_prompts_parse(text, kind, extra):
    raw = LocalPlanner().parse(text)
    assert raw["category"] == "boat" and raw["params"].get("boat_type") == kind
    for k, v in extra.items():
        assert raw["params"].get(k) == v, (k, raw["params"])


@pytest.mark.parametrize("text", ["tạo tàu hỏa", "tạo tàu ngầm", "tạo tàu vũ trụ"])
def test_non_boat_tau_not_detected(text):
    assert LocalPlanner().parse(text)["category"] != "boat"


def test_boat_structure_and_real_proportions():
    sp, asm, rep = build("boat", boat_type="speedboat", length_mm=6500)
    hull = asm.part("hull").part.bounds.size
    assert 2.8 < hull[2] / hull[0] < 3.6                                # dài/rộng ca nô thật ≈ 3
    assert abs(max(asm.bounds.size) - 6500) < 1
    cats = {bp.part.category for bp in asm.parts}
    assert {"hull", "deck", "cabin", "windshield", "railing", "motor", "propeller", "fitting", "seat"} <= cats
    mats = {asm.materials[mid].id for bp in asm.parts for _, mid in bp.meshes}
    assert {"antifouling", "led_red", "led_green"} <= mats                # sơn chống hà + đèn mạn đỏ/xanh
    _, fishing, _ = build("boat", boat_type="fishing")
    assert fishing.part("rudder") is not None and fishing.part("shaft_1") is not None   # tàu cá: máy trong mặc định
    prop = fishing.part("propeller_1").solid
    assert prop.intersection_volume(fishing.part("hull").solid) < 1.0      # chân vịt không xuyên đáy tàu
    assert prop.intersection_volume(fishing.part("rudder").solid) < 1.0


def test_boat_route_and_benchmark_group():
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    assert "boat" in GROUPS and len(by_group()["boat"]) >= 50
    pl = Planner(None)
    assert all(spec_matches(c, pl.plan(c.prompt).spec)[0] for c in by_group()["boat"])


def test_intent_router_generates_boat():
    from nexa.ai.intent_router import IntentRouter
    r = IntentRouter(viewer_active=lambda: False, part_known=lambda p: False).route("Tạo tàu cá dài 12 m")
    assert r is not None and r.calls[0][0] == "generate_3d_model"


def test_no_overlap_scan_rover_quadruped():
    for cat in ("rover", "quadruped"):
        _, asm, _ = build(cat)
        big = [bp for bp in asm.parts if bp.solid is not None]
        bad = [(a.part.id, b.part.id) for a, b in itertools.combinations(big, 2)
               if a.part.category in ("battery", "lidar", "camera") and b.part.category in ("shell", "battery", "lidar")
               and a.part.parent_id != b.part.id and b.part.parent_id != a.part.id
               and a.solid.intersection_volume(b.solid) > 0.01 * min(abs(a.solid.volume()), abs(b.solid.volume()))]
        assert not bad, (cat, bad)
