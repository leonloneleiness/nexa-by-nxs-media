"""Đợt 1 — linh kiện cơ khí tiêu chuẩn: ổ bi ISO 15, động cơ bước NEMA, hộp số, xi lanh ISO 15552, van bi + phụ kiện
ống DN (EN 1092-1 / ASME B16.9 / B16.10), truyền động đai/xích/khớp nối, vít me bi, ray trượt, lò xo.

Mỗi mẫu: hiểu câu lệnh tiếng Việt, kích thước tiêu chuẩn ĐO trên khối, checklist, không xuyên nhau (quét mọi cặp),
mọi gate đạt, kế hoạch tách hợp lệ, số tam giác trong ngân sách."""
from __future__ import annotations

import math

import pytest

from nexa.three_d import standards as S
from nexa.three_d.planner import LocalPlanner, Planner, detect_category
from tech3d_helpers import assert_technical, build, measured

VARIANTS = [
    ("bearing", {"designation": "6204"}), ("bearing", {"designation": "6000", "seal": "2RS"}),
    ("bearing", {"designation": "6312", "seal": "ZZ", "cage": "polyamide"}),
    ("stepper_motor", {"frame_size": 17}), ("stepper_motor", {"frame_size": 23, "shaft": "double"}),
    ("stepper_motor", {"frame_size": 34, "body_length_mm": 114}),
    ("gearbox", {}), ("gearbox", {"stages": 3, "ratio": 80, "module_mm": 1.5}), ("gearbox", {"stages": 2, "ratio": 30, "housing": "aluminum"}),
    ("cylinder", {}), ("cylinder", {"bore_mm": 32, "stroke_mm": 200, "state": "extended"}),
    ("cylinder", {"cylinder_type": "hydraulic", "bore_mm": 80, "stroke_mm": 300, "state": "mid"}),
    ("ball_valve", {"dn": 15, "state": "closed"}), ("ball_valve", {"dn": 50}), ("ball_valve", {"dn": 200, "material": "stainless"}),
    ("pipe_fitting", {"fitting": "elbow90", "dn": 25}), ("pipe_fitting", {"fitting": "elbow45", "dn": 100}),
    ("pipe_fitting", {"fitting": "tee", "dn": 150}), ("pipe_fitting", {"fitting": "flange_joint", "dn": 200}),
    ("belt_drive", {}), ("belt_drive", {"belt": "HTD5M", "teeth_driver": 18, "teeth_driven": 36}),
    ("belt_drive", {"belt": "SPZ", "pulley_d_mm": 90, "pulley2_d_mm": 180}),
    ("chain_drive", {}), ("chain_drive", {"chain": "16B", "teeth_driver": 19, "teeth_driven": 38}),
    ("shaft_coupling", {}), ("shaft_coupling", {"coupling_type": "rigid", "bore_mm": 8, "bore2_mm": 10}),
    ("ball_screw", {}), ("ball_screw", {"diameter_mm": 32, "lead_mm": 10, "length_mm": 1200}),
    ("linear_guide", {}), ("linear_guide", {"series": "MGN9", "length_mm": 200, "carriages": 1}),
    ("spring", {}), ("spring", {"ends": "closed", "wire_d_mm": 1, "outer_d_mm": 10, "active_coils": 12}),
    ("spring", {"spring_type": "extension", "wire_d_mm": 1.5, "outer_d_mm": 12, "free_length_mm": 60}),
    ("spring", {"spring_type": "torsion"}),
]


@pytest.mark.parametrize("cat,params", VARIANTS)
def test_component_templates_pass_all_gates(cat, params):
    _sp, asm, rep, dt = build(cat, **params)
    assert_technical(asm, rep, dt)
    assert not rep.missing_parts


# ------------------------------------------------------------------ kích thước tiêu chuẩn đo trên khối
@pytest.mark.parametrize("code", ["6000", "6204", "6305", "6212"])
def test_bearing_iso15_dimensions(code):
    d, D, B, _ = S.BEARINGS[code]
    _, asm, rep, _ = build("bearing", designation=code, seal="2RS")
    for name, want in (("lỗ d", d), ("ngoài D", D), ("bề rộng B", B)):
        c = measured(rep, name)
        assert c["ok"] and f"{want:g} mm" in c["detail"], c
    assert measured(rep, "số bi")["ok"]
    z, _dw, _dm = S.bearing_balls(code)
    assert len([bp for bp in asm.parts if bp.part.category == "ball"]) == z


@pytest.mark.parametrize("size", [17, 23, 34])
def test_nema_flange_holes_shaft(size):
    t = S.NEMA[size]
    _, _asm, rep, _ = build("stepper_motor", frame_size=size)
    assert measured(rep, "cạnh mặt bích NEMA")["ok"] and f"{t['flange']:g} mm" in measured(rep, "cạnh mặt bích NEMA")["detail"]
    assert measured(rep, "khoảng cách tâm lỗ")["ok"] and f"{t['hole_spacing']:g} mm" in measured(rep, "khoảng cách tâm lỗ")["detail"]
    assert measured(rep, "đường kính trục")["ok"] and measured(rep, "gờ định tâm")["ok"]


def test_gearbox_center_distance_and_ratio_measured():
    sp, asm, rep, _ = build("gearbox", stages=2, ratio=12, module_mm=2)
    cd = [c for c in rep.checks if "khoảng cách tâm a" in c["name"]]
    assert len(cd) == 2 and all(c["ok"] for c in cd)
    teeth = asm.metadata["teeth"]
    mods = asm.metadata["modules"]
    for (z1, z2), m, a in zip(teeth, mods, asm.metadata["center_distances_mm"]):
        assert math.isclose(a, m * (z1 + z2) / 2)
    r = measured(rep, "tỷ số truyền tổng")
    assert r["ok"] and abs(asm.metadata["ratio_actual"] - 12) / 12 < 0.03
    # bánh răng ăn khớp không chạm nhau (khe hở cạnh răng)
    for mesh in asm.metadata["mesh"]:
        a_, b_ = asm.part(mesh["driver"]).solid, asm.part(mesh["driven"]).solid
        assert a_.intersection_volume(b_) < 1e-3


def test_gearbox_ratio_over_60_needs_three_stages():
    res = Planner(None).plan("tạo hộp số 2 cấp tỉ số 100")
    assert res.spec is None and "3 cấp" in res.questions[0]
    assert Planner(None).plan("tạo hộp số tỉ số 100").spec.params["stages"] == 3      # không nói số cấp → tự chọn 3 cấp


def test_cylinder_iso15552_and_stroke():
    _, asm, rep, _ = build("cylinder", bore_mm=63, stroke_mm=160, state="extended")
    for name in ("đường kính nòng", "đường kính cần piston", "khoảng tâm thanh giằng TG", "hành trình", "vị trí piston"):
        assert measured(rep, name)["ok"], name
    assert asm.metadata["tg_mm"] == S.ISO15552[63]["tg"]


def test_pneumatic_bore_must_be_iso():
    res = Planner(None).plan("tạo xi lanh khí nén phi 45 hành trình 100")
    assert res.spec is None and "ISO 15552" in res.questions[0]


@pytest.mark.parametrize("dn", [15, 50, 125, 200])
def test_valve_flange_en1092_and_face_to_face(dn):
    D, Kc, _L, n, _M, _C2 = S.FLANGE_PN16[dn]
    _, _asm, rep, _ = build("ball_valve", dn=dn)
    assert measured(rep, "mặt–mặt")["ok"] and f"{S.VALVE_FTF[dn]:g} mm" in measured(rep, "mặt–mặt")["detail"]
    assert measured(rep, "đường kính ngoài D")["ok"] and measured(rep, "vòng tâm lỗ K")["ok"]
    assert measured(rep, "số lỗ bu-lông")["ok"] and f"/ {n}" in measured(rep, "số lỗ bu-lông")["detail"]
    assert measured(rep, "toàn lỗ")["ok"]


def test_valve_handle_follows_state():
    _, asm_o, rep_o, _ = build("ball_valve", dn=50, state="open")
    _, asm_c, rep_c, _ = build("ball_valve", dn=50, state="closed")
    assert measured(rep_o, "tay gạt đúng trạng thái")["ok"] and measured(rep_c, "tay gạt đúng trạng thái")["ok"]
    assert measured(rep_o, "lỗ bi thông")["ok"] and measured(rep_c, "lỗ bi thông")["ok"]


@pytest.mark.parametrize("kind,name", [("elbow90", "tâm–mặt A"), ("elbow45", "tâm–mặt B"), ("tee", "tâm–mặt C"),
                                       ("flange_joint", "vòng tâm lỗ K")])
def test_pipe_fittings_asme_b169(kind, name):
    _, _asm, rep, _ = build("pipe_fitting", fitting=kind, dn=80)
    assert measured(rep, name)["ok"]


def test_timing_belt_teeth_mesh_pulleys():
    _, asm, rep, _ = build("belt_drive", belt="GT2", teeth_driver=20, teeth_driven=60)
    assert measured(rep, "tỷ số truyền z2/z1")["ok"]
    assert [c for c in rep.checks if "số răng puly" in c["name"] and c["ok"]].__len__() == 2
    belt = asm.part("belt").solid
    for pid in ("pulley_driver", "pulley_driven"):
        assert belt.intersection_volume(asm.part(pid).solid) < 1e-3 * belt.volume()   # răng đai nằm trong rãnh puly


def test_chain_even_links_pitch_and_teeth():
    _, asm, rep, _ = build("chain_drive", chain="10B", teeth_driver=19, teeth_driven=38, center_distance_mm=500)
    assert measured(rep, "số mắt xích chẵn")["ok"] and measured(rep, "bước xích")["ok"]
    assert [c for c in rep.checks if "số răng đĩa xích" in c["name"] and c["ok"]].__len__() == 2
    assert abs(asm.metadata["center_distance_mm"] - 500) <= S.CHAINS["10B"]["pitch"] / 2


def test_ball_screw_lead_and_rail_pitch():
    _, _asm, rep, _ = build("ball_screw", diameter_mm=20, lead_mm=5, length_mm=600)
    assert measured(rep, "bước vít")["ok"] and measured(rep, "đường kính danh nghĩa")["ok"]
    _, _asm2, rep2, _ = build("linear_guide", series="HGR25", length_mm=800, carriages=2)
    assert measured(rep2, "bước lỗ lắp ray P")["ok"] and measured(rep2, "bề rộng ray")["ok"]
    assert measured(rep2, "chiều cao lắp H")["ok"]


def test_spring_pitch_coils_free_length():
    _, _asm, rep, _ = build("spring", wire_d_mm=2, outer_d_mm=20, active_coils=8, free_length_mm=60, ends="ground")
    for name in ("chiều dài tự do", "bước vòng làm việc", "số vòng tổng", "đường kính dây", "đường kính ngoài"):
        assert measured(rep, name)["ok"], name


# ------------------------------------------------------------------ hiểu câu lệnh tiếng Việt
@pytest.mark.parametrize("text,cat,params", [
    ("Tạo ổ bi 6204", "bearing", {"designation": "6204"}),
    ("tao vong bi 6305 2rs", "bearing", {"designation": "6305", "seal": "2RS"}),
    ("Tạo bạc đạn 20x47x14 nắp thép", "bearing", {"designation": "6204", "seal": "ZZ"}),
    ("Tạo động cơ bước NEMA 23", "stepper_motor", {"frame_size": 23}),
    ("tạo hộp giảm tốc ba cấp tỷ số 80 module 1,5", "gearbox", {"stages": 3, "ratio": 80.0, "module_mm": 1.5}),
    ("Tạo xi lanh khí nén phi 50 hành trình 200", "cylinder", {"bore_mm": 50.0, "stroke_mm": 200.0}),
    ("tạo van bi tay gạt DN25 đang đóng", "ball_valve", {"dn": 25, "state": "closed"}),
    ("Tạo co 90 độ DN80", "pipe_fitting", {"fitting": "elbow90", "dn": 80}),
    ("tạo mặt bích nối ống DN65", "pipe_fitting", {"fitting": "flange_joint", "dn": 65}),
    ("Tạo bộ truyền đai GT2 puly 20 răng và 40 răng", "belt_drive", {"teeth_driver": 20, "teeth_driven": 40}),
    ("Tạo bộ truyền xích 08B đĩa 17 răng và 34 răng", "chain_drive", {"chain": "08B"}),
    ("tạo khớp nối mềm trục 14 sang 19", "shaft_coupling", {"bore_mm": 14.0, "bore2_mm": 19.0}),
    ("Tạo vít me bi SFU1605 dài 500 mm", "ball_screw", {"diameter_mm": 16.0, "lead_mm": 5.0, "length_mm": 500.0}),
    ("Tạo ray trượt HGR20 dài 600 mm hai con trượt", "linear_guide", {"series": "HGR20", "carriages": 2}),
    ("tạo lò xo kéo dây 1,5 ngoài 12 dài 60", "spring", {"spring_type": "extension", "free_length_mm": 60.0}),
])
def test_component_prompts_parse(text, cat, params):
    raw = LocalPlanner().parse(text)
    assert raw["category"] == cat
    for k, v in params.items():
        assert raw["params"].get(k) == v, (k, raw["params"])


@pytest.mark.parametrize("text,cat", [
    ("tạo bánh răng module 2 có 32 răng", "gear"), ("tạo bánh răng có 90 răng module 1", "gear"),
    ("tạo mặt bích đường kính 120 mm 4 lỗ", "flange"), ("tạo bu lông M8 dài 30", "bolt"), ("tạo vít M6 dài 20", "bolt"),
    ("tạo hộp số có ổ bi", "gearbox"), ("tạo robot hình chó mỗi chân có ba khớp", "quadruped"), ("tạo cái cốc", "generic"),
])
def test_component_keywords_do_not_steal_old_categories(text, cat):
    assert detect_category(text) == cat


def test_bearing_without_size_asks():
    res = Planner(None).plan("Tạo ổ bi")
    assert res.spec is None and "6204" in res.questions[0]


def test_intent_router_generates_components_but_not_commands():
    from nexa.ai.intent_router import IntentRouter
    r = IntentRouter(viewer_active=lambda: False, part_known=lambda p: False)
    for text in ("Tạo ổ bi 6204", "dựng hộp số hai cấp", "tạo van bi DN50", "tạo lò xo nén"):
        route = r.route(text)
        assert route.calls and route.calls[0][0] == "generate_3d_model", text
    for text in ("tạo thư mục báo cáo", "tạo file word", "tạo lò xo như thế nào", "vẽ sơ đồ hộp số"):
        route = r.route(text)
        assert not (route.calls and route.calls[0][0] == "generate_3d_model"), text


def test_components_benchmark_group():
    from collections import Counter
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    assert "components" in GROUPS
    cases = by_group()["components"]
    assert len(cases) >= 60 and min(Counter(c.category for c in cases).values()) >= 5
    pl = Planner(None)
    assert all(spec_matches(c, pl.plan(c.prompt).spec)[0] for c in cases)
