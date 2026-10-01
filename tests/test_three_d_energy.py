"""Đợt 4 — năng lượng & công trình: tuabin gió, hệ điện mặt trời, máy phát điện, máy bơm ly tâm, bồn chứa, cầu (giàn /
dây văng / vòm), giàn thép (bản mã + bu-lông thật), tháp thép (điện / viễn thông)."""
from __future__ import annotations

import pytest

from nexa.three_d import standards as S
from nexa.three_d.planner import LocalPlanner, Planner, detect_category
from nexa.three_d.spec import SAFETY_CRITICAL
from tech3d_helpers import assert_technical, build, measured

VARIANTS = [
    ("wind_turbine", {}), ("wind_turbine", {"rotor_diameter_mm": 120000, "nacelle_open": True}), ("wind_turbine", {"rotor_diameter_mm": 20000, "blades": 2}),
    ("solar_array", {}), ("solar_array", {"panels": 40, "rows": 4, "tilt_deg": 30}), ("solar_array", {"panels": 1, "rows": 1, "tilt_deg": 0, "inverter": False}),
    ("generator_set", {}), ("generator_set", {"power_kva": 1000, "enclosure": "open"}), ("generator_set", {"power_kva": 10}),
    ("centrifugal_pump", {}), ("centrifugal_pump", {"size": "125-100-250", "motor_kw": 90}), ("centrifugal_pump", {"size": "50-32-160", "motor_kw": 2.2}),
    ("storage_tank", {}), ("storage_tank", {"roof": "dome", "capacity_m3": 500}), ("storage_tank", {"orientation": "horizontal", "capacity_m3": 5}),
    ("storage_tank", {"capacity_m3": 2000, "diameter_mm": 16000}),
    ("bridge", {}), ("bridge", {"bridge_type": "cable_stayed", "span_mm": 80000}), ("bridge", {"bridge_type": "arch", "span_mm": 120000, "deck_width_mm": 14000}),
    ("bridge", {"span_mm": 20000, "deck_width_mm": 4000}),
    ("steel_truss", {}), ("steel_truss", {"truss_type": "fink", "span_mm": 20000}), ("steel_truss", {"truss_type": "warren", "span_mm": 24000}),
    ("steel_truss", {"truss_type": "howe", "span_mm": 9000, "panels": 6}),
    ("lattice_tower", {}), ("lattice_tower", {"tower_type": "telecom"}), ("lattice_tower", {"tower_type": "telecom", "legs": 3, "height_mm": 60000}),
    ("lattice_tower", {"height_mm": 15000}),
]


@pytest.mark.parametrize("cat,params", VARIANTS)
def test_energy_templates_pass_all_gates(cat, params):
    _sp, asm, rep, dt = build(cat, **params)
    assert_technical(asm, rep, dt)
    assert not rep.missing_parts


def test_wind_turbine_rotor_geometry():
    _sp, asm, rep, _ = build("wind_turbine", rotor_diameter_mm=90000, hub_height_mm=80000)
    for name in ("đường kính rotor", "chiều cao tâm rotor", "độ xoắn cánh", "Ø chân tháp", "Ø đỉnh tháp", "khoảng hở mũi cánh"):
        assert measured(rep, name)["ok"], name
    ids = {bp.part.id for bp in asm.parts}
    assert {"gearbox", "generator", "main_shaft", "yaw_system", "nacelle_cover", "hub"} <= ids


def test_solar_module_and_tilt():
    _sp, asm, rep, _ = build("solar_array", panels=12, rows=2, tilt_deg=15)
    for name in ("chiều dài tấm pin", "chiều rộng tấm pin", "góc nghiêng tấm pin", "mép dưới tấm pin", "khoảng cách hàng"):
        assert measured(rep, name)["ok"], name
    assert asm.metadata["kwp"] == pytest.approx(4.8)


def test_pump_flanges_and_alignment():
    _sp, asm, rep, _ = build("centrifugal_pump", size="65-50-160")
    assert measured(rep, "mặt bích hút DN65: đường kính ngoài D")["ok"] and measured(rep, "mặt bích hút DN65: số lỗ")["ok"]
    assert measured(rep, "mặt bích đẩy DN50: vòng tâm lỗ K")["ok"]
    assert measured(rep, "trục bơm và trục động cơ đồng tâm")["ok"] and measured(rep, "EN 733 h1")["ok"] and measured(rep, "IEC 60072")["ok"]
    assert S.FLANGE_PN16[65][3] == 8                                   # PN16 DN65: 8 lỗ


def test_tank_capacity_measured():
    for params in ({"capacity_m3": 50}, {"orientation": "horizontal", "capacity_m3": 20}, {"capacity_m3": 500, "roof": "dome"}):
        _sp, asm, rep, _ = build("storage_tank", **params)
        assert measured(rep, "dung tích")["ok"], params
    _sp, asm, rep, _ = build("storage_tank", capacity_m3=100)
    assert asm.metadata["has_cage"] and measured(rep, "lồng bảo vệ")["ok"]


def test_truss_real_joints():
    _sp, asm, rep, _ = build("steel_truss", span_mm=12000)
    for name in ("nhịp giàn", "chiều cao giàn", "cạnh thép góc", "bề dày thép góc", "khe kẹp bản mã", "số bản mã", "mỗi bản mã có ≥ 4 bu-lông", "tổng số bu-lông"):
        assert measured(rep, name)["ok"], name
    # thanh bụng không lấn thanh cánh / bản mã: kiểm tra trực tiếp giao khối (kể cả cha–con)
    top, web, gus = asm.part("top_chord").solid, asm.part("diagonal").solid, asm.part("gussets").solid
    assert top.intersection_volume(web) < 1.0 and web.intersection_volume(gus) < 1.0


def test_bridges_and_towers():
    _sp, asm, rep, _ = build("bridge", bridge_type="truss", span_mm=60000)
    assert measured(rep, "nhịp (tâm gối")["ok"] and measured(rep, "tĩnh không dưới thanh chống")["ok"]
    _sp, asm, rep, _ = build("bridge", bridge_type="cable_stayed")
    assert measured(rep, "số dây văng")["ok"] and measured(rep, "dây văng đối xứng")["ok"]
    _sp, asm, rep, _ = build("bridge", bridge_type="arch")
    assert measured(rep, "đường tên vòm")["ok"] and measured(rep, "dây treo thẳng đứng")["ok"]
    _sp, asm, rep, _ = build("lattice_tower", tower_type="power", height_mm=30000)
    assert measured(rep, "chiều cao thân tháp")["ok"] and measured(rep, "bát cách điện")["ok"] and measured(rep, "bu-lông liên kết")["ok"]
    br, lg = asm.part("bracing").solid, asm.part("legs").solid
    assert br.intersection_volume(lg) < 50.0                             # thanh giằng áp cánh chân (chỉ chạm)


def test_energy_are_safety_flagged():
    assert {"wind_turbine", "bridge", "steel_truss", "lattice_tower", "storage_tank", "generator_set", "solar_array"} <= SAFETY_CRITICAL


@pytest.mark.parametrize("text,cat,params", [
    ("Tạo tua bin gió rotor 120 m cao 90 m mở nắp", "wind_turbine", {"rotor_diameter_mm": 120000.0, "hub_height_mm": 90000.0, "nacelle_open": True}),
    ("tạo hệ điện mặt trời 20 tấm 2 hàng nghiêng 15 độ", "solar_array", {"panels": 20, "rows": 2, "tilt_deg": 15.0}),
    ("tạo máy phát điện 250 kVA khung trần", "generator_set", {"power_kva": 250.0, "enclosure": "open"}),
    ("tạo máy bơm ly tâm 80-65-160 11 kW", "centrifugal_pump", {"size": "80-65-160", "motor_kw": 11.0}),
    ("tạo bồn nước inox nằm ngang 5000 lít", "storage_tank", {"orientation": "horizontal", "capacity_m3": 5.0}),
    ("tạo cầu dây văng nhịp 80 m", "bridge", {"bridge_type": "cable_stayed", "span_mm": 80000.0}),
    ("tạo cây cầu giàn thép", "bridge", {"bridge_type": "truss"}),
    ("tạo giàn thép kiểu Howe nhịp 18 m", "steel_truss", {"truss_type": "howe", "span_mm": 18000.0}),
    ("tạo cột điện cao thế 40 m", "lattice_tower", {"tower_type": "power", "height_mm": 40000.0}),
    ("tạo tháp viễn thông 3 chân cao 45 m", "lattice_tower", {"tower_type": "telecom", "legs": 3, "height_mm": 45000.0}),
])
def test_energy_prompts_parse(text, cat, params):
    raw = LocalPlanner().parse(text)
    assert raw["category"] == cat, raw["category"]
    for k, v in params.items():
        assert raw["params"].get(k) == v, (k, raw["params"])


@pytest.mark.parametrize("text,cat", [
    ("tạo xe cẩu", "crane"), ("tạo cẩu trục", "crane"), ("tạo cẩu", "crane"), ("tạo cây cầu", "bridge"), ("tạo máy phát điện gió", "wind_turbine"),
    ("tạo máy phát điện năng lượng mặt trời", "solar_array"), ("Thiết kế xe 5 chỗ sedan cầu sau", "car"), ("tạo máy xúc", "excavator"),
    ("tạo hộp số 2 cấp", "gearbox"), ("tạo drone 4 cánh", "uav"),
])
def test_energy_keywords_do_not_break_others(text, cat):
    assert detect_category(text) == cat


def test_energy_benchmark_group():
    from collections import Counter
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    assert "energy" in GROUPS
    cases = by_group()["energy"]
    assert len(cases) >= 60 and min(Counter(c.category for c in cases).values()) >= 5
    pl = Planner(None)
    assert all(spec_matches(c, pl.plan(c.prompt).spec)[0] for c in cases)
