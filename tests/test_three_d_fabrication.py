"""Đợt 5 — máy chế tạo & điện tử: máy in 3D FDM (kiểu i3 / CoreXY), máy CNC router 3 trục (vít me bi, ray, gantry dẫn động
kép), tủ rack 19", tủ điện (ray DIN TH35), quạt hướng trục, tản nhiệt (tháp ống đồng / nhôm đùn), bo mạch (Arduino / Pi)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.motion import infer_motions
from nexa.three_d.planner import LocalPlanner, Planner, detect_category
from tech3d_helpers import assert_technical, build, measured

VARIANTS = [
    ("fdm_printer", {}), ("fdm_printer", {"kinematics": "corexy", "build_x_mm": 300, "build_y_mm": 300, "build_z_mm": 350}),
    ("fdm_printer", {"build_x_mm": 100, "build_y_mm": 100, "build_z_mm": 100}), ("fdm_printer", {"kinematics": "corexy", "build_x_mm": 400, "build_y_mm": 400, "build_z_mm": 450}),
    ("cnc_router", {}), ("cnc_router", {"travel_x_mm": 1200, "travel_y_mm": 800, "travel_z_mm": 200, "spindle_kw": 4}),
    ("cnc_router", {"travel_x_mm": 300, "travel_y_mm": 300, "travel_z_mm": 60, "spindle_kw": 0.8}),
    ("server_rack", {}), ("server_rack", {"rack_units": 6, "depth_mm": 450, "equipment": False}), ("server_rack", {"rack_units": 48, "depth_mm": 1200}),
    ("electrical_enclosure", {}), ("electrical_enclosure", {"width_mm": 200, "height_mm": 200, "depth_mm": 120, "window": True}),
    ("electrical_enclosure", {"width_mm": 1200, "height_mm": 1400, "depth_mm": 400}),
    ("axial_fan", {}), ("axial_fan", {"size_mm": 40, "blades": 5, "guard": False}), ("axial_fan", {"size_mm": 140, "blades": 11}),
    ("heatsink", {}), ("heatsink", {"heatsink_type": "extruded", "fan": False}), ("heatsink", {"heat_pipes": 0}), ("heatsink", {"heat_pipes": 8}),
    ("dev_board", {}), ("dev_board", {"board": "raspberry_pi"}),
]


@pytest.mark.parametrize("cat,params", VARIANTS)
def test_fabrication_templates_pass_all_gates(cat, params):
    _sp, asm, rep, dt = build(cat, **params)
    assert_technical(asm, rep, dt)
    assert not rep.missing_parts


@pytest.mark.parametrize("params", [{}, {"kinematics": "corexy", "build_x_mm": 300, "build_y_mm": 300, "build_z_mm": 350}])
def test_printer_build_volume_and_nozzle(params):
    _sp, asm, rep, _ = build("fdm_printer", **params)
    for name in ("tấm in phủ vùng in", "khe mũi phun – mặt tấm in", "mũi phun nằm trên vùng tấm in", "chiều dài ray x_rail"):
        assert measured(rep, name)["ok"], name
    assert measured(rep, "khung cao hơn mặt in" if params.get("kinematics") != "corexy" else "bàn hạ được")["ok"]


def test_cnc_axes_and_clearances():
    _sp, asm, rep, _ = build("cnc_router", travel_x_mm=800, travel_y_mm=600, travel_z_mm=120, spindle_kw=2.2)
    for name in ("chiều dài bàn máy", "bề rộng bàn máy", "mũi dao chạm được mặt bàn", "khe hở dưới dầm giàn > hành trình Z",
                 "Ø thân trục chính", "Ø dao phay", "số vít me trục Y", "chiều dài vít me X", "chiều dài vít me Z",
                 "dao nằm trong vùng bàn", "ray Y đủ hành trình", "ray X đủ hành trình"):
        assert measured(rep, name)["ok"], name
    ids = {bp.part.id for bp in asm.parts}
    assert {"y_screws", "x_screw", "z_screw", "y_supports", "spindle", "tool", "estop"} <= ids
    assert asm.metadata["strict_overlap"] and asm.metadata["travel_mm"] == pytest.approx([800.0, 600.0, 120.0])


def test_rack_din_fan_board_standards():
    _sp, asm, rep, _ = build("server_rack", rack_units=42)
    for name in ("số lỗ vuông trên ray", "bước 1U", "lọt lòng giữa hai ray", "khoảng tâm lỗ ngang"):
        assert measured(rep, name)["ok"], name
    _sp, asm, rep, _ = build("electrical_enclosure")
    for name in ("chiều cao ray TH35", "bề rộng ray TH35", "bước mô-đun DIN 43880", "ốc siết cáp ở đáy tủ", "cửa tủ ở mặt trước"):
        assert measured(rep, name)["ok"], name
    _sp, asm, rep, _ = build("axial_fan", size_mm=120, blades=7)
    for name in ("cạnh khung quạt", "khoảng tâm lỗ vít", "số lá cánh", "khe hở đầu lá"):
        assert measured(rep, name)["ok"], name
    _sp, asm, rep, _ = build("heatsink", heat_pipes=6)
    assert measured(rep, "số nhánh ống dẫn nhiệt xuyên lá")["ok"] and measured(rep, "bước lá")["ok"]
    for board in ("arduino_uno", "raspberry_pi"):
        _sp, asm, rep, _ = build("dev_board", board=board)
        assert measured(rep, "4 lỗ bắt đúng tọa độ")["ok"] and measured(rep, "bước chân header")["ok"], board


# ------------------------------------------------------------------ chuyển động: trục máy trên ray, cửa tủ, cánh quạt
def _disp(chain, t):
    d = np.zeros(3)
    for m in chain:
        if m["t"] == "slide":
            d += np.asarray(m["a"]) * (m["off"] + m["amp"] * math.sin(2 * math.pi * t / m["per"] + m["ph"]))
    return d


def _motions(prompt):
    spec = Planner(None, use_gemini=False).plan(prompt).spec
    parts = {bp.part.id: bp.part for bp in build_parametric(spec).parts}
    chains, mode = infer_motions(spec.category, list(parts.values()))
    return parts, chains, mode


@pytest.mark.parametrize("prompt,axes,tip,bed", [
    ("tạo máy in 3D", [("y_carriages", "y_rail"), ("x_carriage", "x_rail"), ("z_carriage_l", "z_rail_l"), ("z_carriage_r", "z_rail_r")],
     "hotend", "build_plate"),
    ("tạo máy in 3D CoreXY", [("y_carriages", "y_rails"), ("x_carriage", "x_rail"), ("z_carriage_l", "z_rail_l"), ("z_carriage_r", "z_rail_r")],
     "hotend", "build_plate"),
    ("tạo máy CNC 6040", [("y_carriages", "y_rails"), ("x_carriages", "x_rails"), ("z_carriages", "z_rails")], "tool", "table"),
    ("tạo máy CNC 300x300x60 0.8 kW", [("y_carriages", "y_rails"), ("x_carriages", "x_rails"), ("z_carriages", "z_rails")], "tool", "table"),
])
def test_machine_axes_stay_on_rails_and_above_bed(prompt, axes, tip, bed):
    parts, chains, mode = _motions(prompt)
    assert mode == "parts"
    home = parts[tip].bounds.min[1] - parts[bed].bounds.max[1]
    for car, _rail in axes:
        assert chains[car] and chains[car][0]["t"] == "slide", car
    for t in np.linspace(0.0, 60.0, 601):
        for car, rail in axes:
            c, r = parts[car], parts[rail]
            i = int(np.argmax(np.abs(chains[car][0]["a"])))
            dc, dr = _disp(chains[car], t), _disp(chains[rail], t)
            assert c.bounds.min[i] + dc[i] >= r.bounds.min[i] + dr[i] - 1e-6, (car, t)      # con trượt không rời ray
            assert c.bounds.max[i] + dc[i] <= r.bounds.max[i] + dr[i] + 1e-6, (car, t)
        gap = (parts[tip].bounds.min[1] + _disp(chains[tip], t)[1]) - (parts[bed].bounds.max[1] + _disp(chains[bed], t)[1])
        assert gap >= min(home, 0.2) - 1e-6, t                          # đầu phun / dao không ăn xuống bàn


def test_cnc_nuts_follow_carriage_and_tool_spins():
    parts, chains, _ = _motions("tạo máy CNC 6040")
    for nut in ("y_nuts", "x_nut", "z_nut"):
        assert chains[nut] and all(m["t"] == "slide" for m in chains[nut]), nut        # đai ốc đi theo con trượt, không quay theo vít
    assert chains["x_screw"][0]["t"] == "swing" and chains["z_screw"][0]["t"] == "swing"
    assert chains["tool"][0]["t"] == "spin" and "spin" not in {m["t"] for m in chains["spindle"]}
    assert not chains["y_screws"]                                       # 2 vít một bộ phận: không quay quanh tâm chung


def test_rack_and_enclosure_doors_open_outward():
    for prompt in ("tạo tủ rack 42U", "tạo tủ điện 600x800x250"):
        parts, chains, mode = _motions(prompt)
        assert mode == "parts"
        doors = [pid for pid, p in parts.items() if p.category == "door"]
        assert doors
        lo = np.min([p.bounds.min for p in parts.values()], axis=0)
        hi = np.max([p.bounds.max for p in parts.values()], axis=0)
        mid = (lo + hi) / 2
        for pid in doors:
            m = chains[pid][0]
            assert m["t"] == "swing"
            a, c = np.asarray(m["a"]), np.asarray(m["c"])
            ang = math.radians(m["off"] + m["amp"])                     # góc mở lớn nhất
            k = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
            rot = np.eye(3) + math.sin(ang) * k + (1 - math.cos(ang)) * (k @ k)
            pc = (np.asarray(parts[pid].bounds.min) + np.asarray(parts[pid].bounds.max)) / 2
            assert np.linalg.norm(rot @ (pc - c) + c - mid) > np.linalg.norm(pc - mid), pid
    parts, chains, _ = _motions("tạo tủ rack 42U")
    spins = [chains[p][0] for p in ("fan_rotor_1", "fan_rotor_2")]
    assert all(m["t"] == "spin" for m in spins) and abs(spins[0]["c"][0] - spins[1]["c"][0]) > 50   # mỗi cánh quay quanh trục riêng


# ------------------------------------------------------------------ câu lệnh
@pytest.mark.parametrize("text,cat,params", [
    ("tạo máy in 3D CoreXY 300x300x350", "fdm_printer", {"kinematics": "corexy", "build_x_mm": 300.0, "build_y_mm": 300.0, "build_z_mm": 350.0}),
    ("tạo máy in 3D kiểu i3 vùng in 250 cao in 300", "fdm_printer", {"kinematics": "bedslinger", "build_x_mm": 250.0, "build_z_mm": 300.0}),
    ("tạo máy CNC 6040", "cnc_router", {"travel_x_mm": 600.0, "travel_y_mm": 400.0}),
    ("tạo máy khắc gỗ CNC 1325", "cnc_router", {"travel_x_mm": 1300.0, "travel_y_mm": 1500.0}),
    ("tạo máy phay CNC 1200x800x200 trục chính 4 kW", "cnc_router", {"travel_x_mm": 1200.0, "travel_z_mm": 200.0, "spindle_kw": 4.0}),
    ("tạo máy CNC router 800w", "cnc_router", {"spindle_kw": 0.8}),
    ("tạo tủ mạng 12U sâu 600", "server_rack", {"rack_units": 12, "depth_mm": 600.0}),
    ("tủ rack 42U không thiết bị", "server_rack", {"rack_units": 42, "equipment": False}),
    ("tạo tủ điện 600x800x250 có cửa kính", "electrical_enclosure", {"width_mm": 600.0, "height_mm": 800.0, "depth_mm": 250.0, "window": True}),
    ("tủ điện rộng 400 cao 500 sâu 200", "electrical_enclosure", {"width_mm": 400.0, "height_mm": 500.0, "depth_mm": 200.0}),
    ("quạt tản nhiệt 80 mm 9 cánh", "axial_fan", {"size_mm": 80, "blades": 9}),
    ("quạt 92mm không lưới", "axial_fan", {"size_mm": 92, "guard": False}),
    ("tạo tản nhiệt CPU 6 ống đồng", "heatsink", {"heatsink_type": "tower", "heat_pipes": 6}),
    ("tản nhiệt nhôm đùn không quạt", "heatsink", {"heatsink_type": "extruded", "fan": False}),
    ("tạo Raspberry Pi 4", "dev_board", {"board": "raspberry_pi"}),
    ("tạo bo mạch Arduino Uno", "dev_board", {"board": "arduino_uno"}),
])
def test_fabrication_prompts_parse(text, cat, params):
    raw = LocalPlanner().parse(text)
    assert raw["category"] == cat, raw["category"]
    for k, v in params.items():
        assert raw["params"].get(k) == v, (k, raw["params"])


@pytest.mark.parametrize("text,cat", [
    ("tủ rack có quạt", "server_rack"), ("tủ điện có quạt", "electrical_enclosure"), ("quạt tản nhiệt", "axial_fan"),
    ("tản nhiệt có quạt", "heatsink"), ("tản nhiệt tháp không quạt", "heatsink"), ("tản nhiệt cho raspberry pi", "heatsink"),
    ("bo mạch có tản nhiệt", "dev_board"), ("máy cnc có vít me bi và ray trượt", "cnc_router"), ("máy in 3d có ổ bi và vít me", "fdm_printer"),
    # không phá nhóm khác
    ("tạo máy bay cánh quạt", "fixed_wing"), ("tạo drone 4 cánh quạt", "uav"), ("hệ pin mặt trời có tủ điện", "solar_array"),
    ("tạo máy phát điện 100 kVA", "generator_set"), ("tạo vít me bi SFU1605", "ball_screw"), ("tạo ray trượt HGR20", "linear_guide"),
    ("tạo động cơ bước NEMA 23", "stepper_motor"), ("tạo bánh răng thanh răng rack", "gear"), ("tạo tháp viễn thông", "lattice_tower"),
    ("tạo từ điển", "generic"), ("tạo tuabin gió", "wind_turbine"),
])
def test_fabrication_keywords_do_not_break_others(text, cat):
    assert detect_category(text) == cat


def test_fabrication_benchmark_group():
    from collections import Counter
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    assert "fabrication" in GROUPS
    cases = by_group()["fabrication"]
    assert len(cases) >= 60 and min(Counter(c.category for c in cases).values()) >= 5
    pl = Planner(None)
    assert all(spec_matches(c, pl.plan(c.prompt).spec)[0] for c in cases)
