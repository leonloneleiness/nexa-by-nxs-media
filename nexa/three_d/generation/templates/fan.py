"""Quạt hướng trục cỡ máy tính (40/60/80/92/120/140 mm): khung vuông có miệng loe (venturi) + 4 lỗ vít theo khoảng
tâm chuẩn (120 mm: 105 mm), 4 thanh đỡ động cơ phía sau, cánh quạt (5–11 lá xoắn, bo đầu lá, khe hở đầu lá ≥ 1 mm),
lưới bảo vệ dây thép (vòng đồng tâm + nan), 4 vít, cáp 4 chân PWM.

`fan_parts(size, blades)` dùng lại cho tản nhiệt CPU. Quạt đặt thổi theo +Z (mặt hút phía −Z), tâm ở gốc, khung z ∈ [0, T].
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def fan_parts(size: int, blades: int = 7) -> dict:
    """Khối quạt (trục +Z, khung z ∈ [0, T]): frame, rotor, hub_label, screws_holes (lõi lỗ vít)."""
    A, T, hs = S.FANS[size]
    r_v = 0.485 * A                                                    # bán kính miệng venturi
    frame = K.extrude(P.rounded_rect(A, A, 0.06 * A, 6), T)             # góc bo trên mặt bằng, mặt trên/dưới phẳng như khung thật
    bell = K.revolve([(r_v, -1.0), (r_v + 0.03 * A, -1.0), (r_v, 0.2 * T), (r_v, 0.8 * T), (r_v + 0.03 * A, T + 1.0), (r_v, T + 1.0)], segments=96)
    frame = frame - K.cylinder(r_v, T + 2, segments=96).translate(0, 0, -1) - bell
    # hốc góc (khung chỉ dày ở 4 tai vít) + lỗ vít
    pockets = [K.box(0.18 * A, 0.18 * A, T - 2 * 0.12 * T).translate(sx * 0.41 * A, sy * 0.41 * A, T / 2) for sx in (1, -1) for sy in (1, -1)]
    frame = frame.subtract_all(pockets)
    holes = [K.cylinder(0.018 * A + 1.5, T + 2, segments=20).translate(sx * hs / 2, sy * hs / 2, -1) for sx in (1, -1) for sy in (1, -1)]
    frame = frame.subtract_all(holes)
    # thanh đỡ + vỏ động cơ (mặt sau, z ∈ [0, 0.35T])
    r_m = 0.19 * A
    motor = K.cylinder(r_m, 0.3 * T, segments=64)
    struts = K.Solid.union_all([K.box(r_v - r_m + 2.0, 0.04 * A, 0.18 * T).translate((r_v + r_m) / 2, 0, 0.09 * T).rotate(0, 0, 45 + 90 * k) for k in range(4)])
    # cánh quạt: moay-ơ dạng cốc + lá loft xoắn
    z0 = 0.3 * T + max(1.0, 0.04 * T)                                 # khe moay-ơ – vỏ động cơ
    hub = K.revolve([(0, z0), (r_m, z0), (r_m, 0.93 * T), (0.8 * r_m, T - 0.02 * T), (0, T - 0.02 * T)], segments=64)
    r_tip = r_v - max(1.0, 0.012 * A)                                  # khe hở đầu lá
    secs = []
    for t in np.linspace(0, 1, 7):
        r = (r_m - 1.0) + (r_tip - r_m + 1.0) * t
        chord = (0.5 + 0.35 * t) * (2 * math.pi * r / blades) * 0.85
        pitch = math.radians(38.0 - 16.0 * t)
        af = P.naca4("4406", 1.0, 20)
        pts = (af - [0.5, 0.0]) * chord
        ang0 = math.radians(18.0 * t)                                  # lá vuốt ngược
        cs, sn = math.cos(pitch), math.sin(pitch)
        loc = np.column_stack([pts[:, 0] * cs - pts[:, 1] * sn, pts[:, 0] * sn + pts[:, 1] * cs])   # (tiếp tuyến, trục)
        th = ang0 + loc[:, 0] / r
        z = z0 + 0.3 * T + loc[:, 1]
        secs.append(np.column_stack([r * np.cos(th), r * np.sin(th), np.clip(z, z0 + 0.02 * T, T - 0.03 * T)]))
    blade = K.loft(secs)
    shaft = K.cylinder(0.02 * A + 0.5, z0 - 0.08 * T + 1.0, segments=16).translate(0, 0, 0.08 * T)   # trục cắm vào ổ trong vỏ động cơ
    rotor = K.Solid.union_all([hub, shaft] + [blade.rotate(0, 0, 360.0 * k / blades) for k in range(blades)])
    recess = K.cylinder(0.75 * r_m, 0.4, segments=48).translate(0, 0, -0.01)
    motor = motor - recess
    label = K.cylinder(0.75 * r_m - 0.3, 0.3, segments=48)                # nhãn dán trong hốc mặt sau động cơ
    return {"frame": frame, "support": motor + struts, "rotor": rotor, "label": label, "A": A, "T": T, "hole_spacing": hs, "r_v": r_v,
            "r_tip": r_tip}


def guard(A: float, r_v: float, T: float, hs: float) -> K.Solid:
    """Lưới bảo vệ dây thép Ø1,2 ở mặt thổi: 5 vòng + 8 nan + 4 tai vít."""
    rings = [K.torus(r, 0.6, segments=64, tube_segments=8).translate(0, 0, T + 1.2) for r in np.linspace(0.2 * r_v, r_v + 0.02 * A, 5)]
    spokes = [MC.orient(K.cylinder(0.6, r_v + 0.02 * A, segments=8), (0, 0, T + 1.2), (math.cos(a), math.sin(a), 0)) for a in np.radians(np.arange(0, 360, 45))]
    r_h = hs / 2 * math.sqrt(2)                                        # tai lưới tới tâm lỗ vít góc
    ears = [K.tube(np.array([[math.cos(a) * (r_v + 0.02 * A), math.sin(a) * (r_v + 0.02 * A), T + 1.2], [math.cos(a) * r_h, math.sin(a) * r_h, T + 1.2]]), 0.6, 8)
            for a in np.radians([45, 135, 225, 315])]
    hub_disc = K.cylinder(0.2 * r_v, 1.2, segments=32).translate(0, 0, T + 0.6)
    return K.Solid.union_all(rings + spokes + ears + [hub_disc])


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    size = int(p.get("size_mm", 120))
    nb = int(p.get("blades", 7))
    mats = MC.tech_materials(spec, primary="#1b1d21", secondary="#2b2d42", accent="#e63946")
    b = AssemblyBuilder(spec.name or f"Quạt {size} mm", "axial_fan", mats)
    F = fan_parts(size, nb)
    A, T, hs = F["A"], F["T"], F["hole_spacing"]
    b.add("frame", f"Khung quạt {size}×{size}×{T:g}", "Fan frame", "fan_frame", [Shape(F["frame"] + F["support"], "plastic_black", 35.0), Shape(F["label"], "label_white", 35.0)], required=True,
          aliases=["khung quạt", "vỏ quạt", "frame", "miệng loe", "thanh đỡ"], function=f"Khung nhựa PBT, miệng loe, 4 lỗ vít khoảng tâm {hs:g} mm, 4 thanh đỡ động cơ.",
          position_tag="center", dimensions={"size": A, "thickness": T, "hole_spacing": hs})
    b.add("rotor", f"Cánh quạt {nb} lá + moay-ơ", "Impeller", "rotor", [Shape(F["rotor"], "plastic_black", 35.0)],
          parent_id="frame", required=True, aliases=["cánh quạt", "lá quạt", "moay-ơ", "impeller", "rotor"],
          function=f"Cánh {nb} lá xoắn NACA mỏng, khe hở đầu lá {F['r_v'] - F['r_tip']:.1f} mm với miệng loe.", position_tag="front",
          joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=0.8 * A, explode_order=2)
    screws = K.Solid.union_all([K.cylinder(0.018 * A + 1.5, T + 1.2, segments=20).translate(sx * hs / 2, sy * hs / 2, 0.0) +
                                K.cylinder(0.04 * A, 0.02 * A + 1.0, segments=20).translate(sx * hs / 2, sy * hs / 2, T + 1.2)
                                for sx in (1, -1) for sy in (1, -1)])
    if p.get("guard", True):
        b.add("guard", "Lưới bảo vệ dây thép", "Wire guard", "guard", Shape(guard(A, F["r_v"], T, hs), "chrome", 35.0), parent_id="frame", required=True,
              aliases=["lưới quạt", "lưới bảo vệ", "guard", "grill"], function="Lưới thép mạ crôm 5 vòng + 8 nan, bắt chung vít quạt.",
              position_tag="front", explode_dir=(0, 0, 1), explode_distance=1.5 * A, explode_order=1)
    b.add("screws", "Vít quạt (4)", "Fan screws", "screw", Shape(screws, "steel_black_oxide", 35.0), parent_id="frame", required=True,
          aliases=["vít", "vít quạt", "screw"], function="4 vít tự ren bắt quạt.", position_tag="front", explode_dir=(0, 0, 1), explode_distance=2.0 * A, explode_order=1)
    cable = K.tube(P.spline_through(np.array([[0.3 * A, 0.0, 0.1 * T], [0.5 * A, 0.1 * A, 0.1 * T], [0.6 * A, 0.3 * A, 0.1 * T]]), 16), 1.4, 8)
    plug = K.box(0.1 * A, 0.05 * A, 0.04 * A).translate(0.6 * A, 0.33 * A, 0.1 * T)
    b.add("cable", "Cáp PWM 4 chân", "4-pin PWM cable", "cable", [Shape(cable, "cable_black", 35.0), Shape(plug, "plastic_white", 35.0)], parent_id="frame",
          required=True, aliases=["dây quạt", "cáp quạt", "đầu cắm", "cable"], function="Cáp 4 chân (GND, 12 V, tachometer, PWM).", position_tag="side",
          explode_dir=(1, 0, 0), explode_distance=0.5 * A, explode_order=1)
    b.note_stage(1, "Tháo lưới, vít, cáp")
    b.note_stage(2, "Rút cánh quạt khỏi trục")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"size_mm": A, "thickness_mm": T, "hole_spacing_mm": hs, "blades": nb, "tip_clearance_mm": F["r_v"] - F["r_tip"],
                       "standard": "Quạt hướng trục cỡ PC (khoảng tâm lỗ 105 mm cho 120 mm), cáp PWM Intel 4 chân",
                       "strict_overlap": True, "contacts": [["screws", "guard"]]})
    return b.build()
