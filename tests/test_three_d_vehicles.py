"""Đợt 3 — phương tiện & hàng không vũ trụ: máy bay cánh bằng / UAV / VTOL, ô tô điện, xe hai bánh, máy xúc, xe nâng,
xe cẩu, tàu hỏa, CubeSat, tên lửa nhiều tầng. Mỗi mẫu: đủ gate, không xuyên khối, không lơ lửng, kích thước đo được
đúng tiêu chuẩn, xi lanh thủy lực đúng chốt, cảnh báo an toàn."""
from __future__ import annotations

import pytest

from nexa.three_d import standards as S
from nexa.three_d.planner import LocalPlanner, Planner, detect_category
from nexa.three_d.spec import SAFETY_CRITICAL
from tech3d_helpers import assert_technical, build, measured

VARIANTS = [
    ("fixed_wing", {}), ("fixed_wing", {"aircraft_type": "uav", "tail": "v_tail"}), ("fixed_wing", {"aircraft_type": "vtol"}),
    ("fixed_wing", {"tail": "t_tail", "dihedral_deg": 6}),
    ("car", {}), ("car", {"body_type": "suv", "drive": "awd"}), ("car", {"body_type": "hatchback"}), ("car", {"length_mm": 3200}),
    ("motorbike", {}), ("motorbike", {"bike_type": "scooter"}), ("motorbike", {"bike_type": "ebike"}),
    ("excavator", {}), ("excavator", {"size_class": "mini", "pose": "reach"}), ("excavator", {"size_class": "large", "pose": "transport", "swing_deg": 60}),
    ("forklift", {}), ("forklift", {"capacity_kg": 3500, "power": "diesel", "fork_height_mm": 4500}), ("forklift", {"capacity_kg": 1000, "fork_height_mm": 0}),
    ("forklift", {"capacity_kg": 5000, "power": "diesel"}),
    ("crane", {}), ("crane", {"boom_length_mm": 40000, "boom_angle_deg": 75, "axles": 4}), ("crane", {"boom_length_mm": 9000, "boom_angle_deg": 0, "axles": 2}),
    ("train", {"wagons": 1}), ("train", {"traction": "electric", "wagons": 2}), ("train", {"wagon_type": "freight", "gauge": "standard", "wagons": 3}),
    ("cubesat", {"units": 1}), ("cubesat", {"units": 3}), ("cubesat", {"units": 12}),
    ("launch_vehicle", {}), ("launch_vehicle", {"stages": 3, "height_mm": 60000}),
]


@pytest.mark.parametrize("cat,params", VARIANTS)
def test_vehicle_templates_pass_all_gates(cat, params):
    _sp, asm, rep, dt = build(cat, **params)
    assert_technical(asm, rep, dt)
    assert not rep.missing_parts


def test_fixed_wing_aero_geometry():
    _sp, asm, rep, _ = build("fixed_wing", wingspan_mm=11000, dihedral_deg=4)
    assert measured(rep, "sải cánh")["ok"] and measured(rep, "góc nhị diện")["ok"]
    assert measured(rep, "độ dày tương đối biên dạng")["ok"] and measured(rep, "số lá cánh quạt")["ok"]
    assert measured(rep, "khoảng hở đầu cánh quạt")["ok"]                     # FAR 23.925 ≥ 229 mm
    ids = {bp.part.id for bp in asm.parts}
    assert {"aileron_left", "aileron_right", "elevator", "rudder"} <= ids      # cánh lái tách riêng
    _sp, vt, rep2, _ = build("fixed_wing", aircraft_type="vtol")
    assert measured(rep2, "4 rotor nâng")["ok"] and measured(rep2, "2 dầm rotor")["ok"]


def test_car_dimensions_tire_and_separable_parts():
    _sp, asm, rep, _ = build("car", body_type="sedan")
    for name in ("chiều dài toàn bộ", "chiều dài cơ sở", "vệt bánh", "đường kính lốp", "4 cửa tách rời", "heo phanh đĩa", "pin nằm dưới sàn"):
        assert measured(rep, name)["ok"], name
    assert abs(asm.metadata["tire_d_mm"] - (18 * 25.4 + 2 * 235 * 0.45)) < 1e-6   # 235/45R18
    doors = [bp for bp in asm.parts if bp.part.category == "door"]
    assert len(doors) == 4 and all(bp.part.parent_id == "body" for bp in doors)
    mats = {asm.materials[mid].id for bp in asm.parts for _, mid in bp.meshes}
    assert {"glass_tinted", "led_white", "led_red", "paint_red"} <= mats          # kính, đèn pha/hậu, heo phanh


def test_motorbike_steering_geometry():
    for t, rake in (("motorcycle", 25.0), ("scooter", 27.0), ("ebike", 19.0)):
        _sp, asm, rep, _ = build("motorbike", bike_type=t)
        assert measured(rep, "góc caster")["ok"] and asm.metadata["rake_deg"] == rake
        assert measured(rep, "chiều dài cơ sở")["ok"] and measured(rep, "đường kính lốp trước")["ok"]
        assert asm.metadata["trail_mm"] > 0


def test_heavy_machines_rams_on_pins_and_in_stroke():
    for cat, params in (("excavator", {}), ("forklift", {"fork_height_mm": 3000}), ("crane", {"boom_angle_deg": 70})):
        _sp, asm, rep, _ = build(cat, **params)
        assert measured(rep, "xi lanh thủy lực lắp đúng chốt")["ok"], cat
        assert measured(rep, "xi lanh trong hành trình")["ok"], cat
    _sp, asm, rep, _ = build("excavator")
    for name in ("khoảng cách tâm hai dải xích", "bề rộng guốc xích", "chiều dài cần", "chiều dài tay gầu", "bán kính quay đuôi"):
        assert measured(rep, name)["ok"], name


def test_forklift_iso_forks_and_mast_stages():
    _sp, asm, rep, _ = build("forklift", capacity_kg=2500)
    assert asm.metadata["fork_width_mm"] == 122 and asm.metadata["fork_thickness_mm"] == 40     # ISO 2331
    assert asm.metadata["carriage_class"] == "II" and asm.metadata["carriage_height_mm"] == 407   # ISO 2328
    for name in ("bề dày càng", "bề rộng càng", "cao độ mặt trên càng", "chiều dài lưỡi càng", "chiều cao giá càng"):
        assert measured(rep, name)["ok"], name
    _sp, hi, rep2, _ = build("forklift", capacity_kg=3500, fork_height_mm=4500)
    assert hi.metadata["mast_stages"] == 3 and measured(rep2, "cao độ mặt trên càng")["ok"]


def test_crane_telescopic_boom():
    _sp, asm, rep, _ = build("crane", boom_length_mm=30000, boom_angle_deg=55)
    for name in ("chiều dài cần", "góc nâng cần", "đoạn ống lồng chồng nhau", "4 chân chống", "nhánh cáp thả thẳng đứng"):
        assert measured(rep, name)["ok"], name
    assert asm.metadata["sections"] >= 5                                        # cần 30 m cần ≥ 5 đoạn


def test_train_gauge_and_running_gear():
    for gauge in ("meter", "standard"):
        _sp, asm, rep, _ = build("train", gauge=gauge, wagons=1)
        assert measured(rep, "khổ đường")["ok"] and asm.metadata["gauge_mm"] == S.RAIL_GAUGE[gauge]
        assert measured(rep, "số bộ trục bánh")["ok"] and measured(rep, "số móc nối")["ok"]


def test_cubesat_cds_dimensions():
    for u in (1, 2, 3, 6, 12):
        _sp, asm, rep, _ = build("cubesat", units=u)
        assert measured(rep, "kích thước X")["ok"] and measured(rep, "chiều cao Z")["ok"], u
    assert S.CUBESAT[1] == (100.0, 100.0, 113.5)


def test_rocket_staging_order():
    _sp, asm, rep, _ = build("launch_vehicle", stages=3)
    assert measured(rep, "số tầng")["ok"] and measured(rep, "số động cơ tầng 1")["ok"] and measured(rep, "chóp mũi hai nửa")["ok"]
    orders = {bp.part.id: bp.part.explode_order for bp in asm.parts}
    assert orders["stage_2"] < orders["stage_3"] < orders["fairing_a"] < orders["payload"]      # tách tầng 1 → 2 → chóp → vệ tinh


def test_vehicles_are_safety_critical():
    assert {"fixed_wing", "car", "motorbike", "excavator", "forklift", "crane", "train", "cubesat", "launch_vehicle"} <= SAFETY_CRITICAL


@pytest.mark.parametrize("text,cat,params", [
    ("Tạo tàu hỏa 3 toa", "train", {"wagons": 3}), ("tạo tàu điện khổ 1435", "train", {"traction": "electric", "gauge": "standard"}),
    ("tạo đầu máy diesel", "train", {"traction": "diesel", "wagons": 0}), ("Tạo vệ tinh CubeSat 6U", "cubesat", {"units": 6}),
    ("tạo tên lửa 3 tầng cao 60 m", "launch_vehicle", {"stages": 3, "height_mm": 60000.0}),
    ("Tạo máy bay", "fixed_wing", {}), ("tạo UAV cánh cố định sải cánh 3 m", "fixed_wing", {"aircraft_type": "uav", "wingspan_mm": 3000.0}),
    ("Tạo máy bay VTOL", "fixed_wing", {"aircraft_type": "vtol"}), ("tạo ô tô điện SUV hai motor", "car", {"body_type": "suv", "drive": "awd"}),
    ("Tạo xe máy tay ga", "motorbike", {"bike_type": "scooter"}), ("tao xe dap dien", "motorbike", {"bike_type": "ebike"}),
    ("Tạo máy xúc mini", "excavator", {"size_class": "mini"}),
    ("tạo xe nâng 3 tấn chạy dầu nâng cao 3 m", "forklift", {"capacity_kg": 3000.0, "power": "diesel", "fork_height_mm": 3000.0}),
    ("tạo xe cẩu cần dài 30 m góc nâng 60 độ 4 trục", "crane", {"boom_length_mm": 30000.0, "boom_angle_deg": 60.0, "axles": 4}),
])
def test_vehicle_prompts_parse(text, cat, params):
    raw = LocalPlanner().parse(text)
    assert raw["category"] == cat, raw["category"]
    for k, v in params.items():
        assert raw["params"].get(k) == v, (k, raw["params"])


@pytest.mark.parametrize("text,cat", [
    ("tạo máy bay không người lái", "uav"), ("tạo máy bay trực thăng", "helicopter"), ("tạo drone 4 cánh", "uav"),
    ("tạo thuyền", "boat"), ("tạo tàu cá dài 12 m", "boat"), ("tạo xe tự hành", "rover"), ("tạo robot giao hàng", "agv"),
    ("tạo hộp số 2 cấp", "gearbox"),
])
def test_vehicle_keywords_do_not_break_old_groups(text, cat):
    assert detect_category(text) == cat


@pytest.mark.parametrize("text", ["tạo cây cầu dây văng", "tạo tàu ngầm"])
def test_conflicting_words_not_vehicles(text):
    assert detect_category(text) not in ("crane", "boat", "train")


def test_vehicles_benchmark_group():
    from collections import Counter
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    assert "vehicles" in GROUPS
    cases = by_group()["vehicles"]
    assert len(cases) >= 60 and min(Counter(c.category for c in cases).values()) >= 5
    pl = Planner(None)
    assert all(spec_matches(c, pl.plan(c.prompt).spec)[0] for c in cases)
