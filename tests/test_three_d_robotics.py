"""Đợt 2 — robot và tự động hóa: cánh tay robot 6 trục (động học kiểu UR, mặt bích ISO 9409-1), robot hút bụi,
AGV kho / robot giao hàng (vi sai hoặc mecanum)."""
from __future__ import annotations

import numpy as np
import pytest

from nexa.three_d import standards as S
from nexa.three_d.planner import LocalPlanner, Planner, detect_category
from nexa.three_d.spec import SAFETY_CRITICAL
from tech3d_helpers import assert_technical, build, measured

VARIANTS = [
    ("robot_arm", {}), ("robot_arm", {"pose": "upright", "end_effector": "none"}),
    ("robot_arm", {"pose": "reach", "end_effector": "vacuum"}),
    ("robot_arm", {"pose": "pick", "style": "industrial", "reach_mm": 1400, "payload_kg": 20}),
    ("robot_arm", {"reach_mm": 500, "payload_kg": 3, "j1_deg": 45}),
    ("robot_arm", {"style": "industrial", "reach_mm": 2500, "payload_kg": 150}),
    ("robot_vacuum", {}), ("robot_vacuum", {"side_brushes": 2, "mop": True, "diameter_mm": 330}),
    ("robot_vacuum", {"lidar": False, "dock": False}),
    ("agv", {}), ("agv", {"drive": "mecanum"}), ("agv", {"top": "cargo", "length_mm": 700}),
    ("agv", {"drive": "mecanum", "top": "cargo", "lidar": False}), ("agv", {"length_mm": 1600}),
]


@pytest.mark.parametrize("cat,params", VARIANTS)
def test_robot_templates_pass_all_gates(cat, params):
    _sp, asm, rep, dt = build(cat, **params)
    assert_technical(asm, rep, dt)
    assert not rep.missing_parts


def test_robot_arm_kinematics_and_iso_flange():
    _sp, asm, rep, _ = build("robot_arm", reach_mm=850, payload_kg=5)
    assert measured(rep, "cánh tay trên a2")["ok"] and "425" in measured(rep, "cánh tay trên a2")["detail"]
    assert measured(rep, "cẳng tay a3")["ok"]
    assert measured(rep, "số khớp quay")["ok"]
    assert measured(rep, "số lỗ trên vòng Ø50")["ok"] and measured(rep, "lỗ định tâm Ø31.5")["ok"]
    assert asm.metadata["tool_flange"] == "ISO 9409-1-50-4-M6"
    # tư thế "ready": trục dụng cụ hướng xuống; "reach": hướng về phía trước
    assert np.allclose(asm.metadata["tool_axis"], [0, 0, -1], atol=1e-6)
    _sp, asm2, _rep, _ = build("robot_arm", pose="reach")
    assert np.allclose(asm2.metadata["tool_axis"], [1, 0, 0], atol=1e-6)
    joints = [bp.part for bp in asm.parts if bp.part.joint_axis is not None]
    assert len(joints) == 6


def test_robot_arm_bigger_payload_bigger_flange():
    assert S.tool_flange_for(20) == "63-4-M6" and S.tool_flange_for(150) == "125-6-M10"
    _sp, _asm, rep, _ = build("robot_arm", style="industrial", reach_mm=2500, payload_kg=150)
    assert measured(rep, "số lỗ trên vòng Ø125")["ok"]


def test_robot_vacuum_sensors_and_ground():
    _sp, asm, rep, _ = build("robot_vacuum", diameter_mm=350)
    assert measured(rep, "đường kính thân")["ok"] and measured(rep, "cảm biến chống rơi")["ok"]
    assert measured(rep, "tháp LiDAR là điểm cao nhất")["ok"] and measured(rep, "bánh chủ động đối xứng")["ok"]
    assert measured(rep, "bộ phận tiếp đất chạm mặt đất")["ok"]
    assert 90 <= asm.metadata["height_mm"] <= 110                    # Roborock S7: 96,5 mm


def test_agv_mecanum_rollers_and_safety():
    _sp, asm, rep, _ = build("agv", drive="mecanum")
    assert measured(rep, "số con lăn mỗi bánh mecanum")["ok"] and measured(rep, "nút dừng khẩn cấp")["ok"]
    assert measured(rep, "máy quét laser an toàn")["ok"] and measured(rep, "bộ phận tiếp đất chạm mặt đất")["ok"]
    _sp, asm2, rep2, _ = build("agv", top="cargo")
    assert asm2.part("cargo_lid") is not None and measured(rep2, "4 bánh xoay")["ok"]


def test_robots_are_safety_critical():
    assert {"robot_arm", "robot_vacuum", "agv"} <= SAFETY_CRITICAL


@pytest.mark.parametrize("text,cat,params", [
    ("Tạo cánh tay robot 6 trục có tay kẹp", "robot_arm", {"end_effector": "gripper"}),
    ("tạo robot công nghiệp 6 trục tầm với 1,4 m tải 20 kg", "robot_arm", {"style": "industrial", "reach_mm": 1400.0, "payload_kg": 20.0}),
    ("tạo cobot UR5 có giác hút", "robot_arm", {"reach_mm": 850.0, "end_effector": "vacuum"}),
    ("tạo tay máy 6 bậc khớp 2 quay 30 độ", "robot_arm", {"j2_deg": 30.0}),
    ("Tạo robot hút bụi có lau nhà hai chổi cạnh", "robot_vacuum", {"mop": True, "side_brushes": 2}),
    ("tao robot hut bui khong co lidar", "robot_vacuum", {"lidar": False}),
    ("Tạo robot AGV nâng kệ bánh mecanum", "agv", {"top": "lift", "drive": "mecanum"}),
    ("tạo robot giao hàng dài 700 mm", "agv", {"top": "cargo", "length_mm": 700.0}),
])
def test_robot_prompts_parse(text, cat, params):
    raw = LocalPlanner().parse(text)
    assert raw["category"] == cat, raw["category"]
    for k, v in params.items():
        assert raw["params"].get(k) == v, (k, raw["params"])


@pytest.mark.parametrize("text,cat", [
    ("tạo xe tự hành sáu bánh có lidar", "rover"), ("tạo robot hình người", "humanoid"), ("tạo robot hình chó", "quadruped"),
    ("tạo xe robot bốn bánh", "rover"), ("tạo xe tự hành kho nâng kệ", "agv"), ("tạo UAV bốn cánh", "uav"),
])
def test_robot_keywords_do_not_break_old_groups(text, cat):
    assert detect_category(text) == cat


def test_robotics_benchmark_group():
    from collections import Counter
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    assert "robotics" in GROUPS
    cases = by_group()["robotics"]
    assert len(cases) >= 60 and min(Counter(c.category for c in cases).values()) >= 5
    pl = Planner(None)
    assert all(spec_matches(c, pl.plan(c.prompt).spec)[0] for c in cases)
