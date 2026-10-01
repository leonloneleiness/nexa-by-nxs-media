"""Cánh tay robot công nghiệp 6 trục: kiểu cobot (Universal Robots) hoặc công nghiệp (khâu đúc sơn cam kiểu KUKA).

Động học thuận thật theo tỷ lệ DH của UR5 (standards.UR_RATIOS, co giãn theo tầm với): J1 xoay đế (trục đứng), J2 vai,
J3 khuỷu, J4 cổ tay 1 (song song J2/J3), J5 cổ tay 2 (vuông góc), J6 cổ tay 3 → mặt bích dụng cụ ISO 9409-1 (cỡ theo
tải). Mỗi khớp là cụm servo (dùng lại mẫu actuator của robot hình người: vỏ + mặt bích nhấn + vòng ốc hai mặt), khâu nối
là ống/khâu đúc có rãnh ghép, cáp dụng cụ chạy dọc cánh tay có kẹp, đầu nối + cáp nguồn ở đế, đế bắt 4 bu-lông.
Dụng cụ: kẹp hai ngón song song (kiểu Robotiq 2F) hoặc giác hút chân không (ống xếp + bộ tạo chân không).
Tư thế: ready / upright / reach / pick hoặc góc từng khớp j1…j6 (độ).

Tháo (từ đầu dụng cụ về đế): dụng cụ → mặt bích → cổ tay 3 → cổ tay 2 → cổ tay 1 → cẳng tay → khuỷu → cánh tay trên →
khớp vai → đế.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import details as D
from nexa.three_d.generation.templates import humanoid as HU
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

POSES = {"ready": (0.0, 70.0, -100.0, -60.0, -90.0, 0.0), "upright": (0.0, 90.0, 0.0, -90.0, 0.0, 0.0),
         "reach": (0.0, 10.0, -10.0, 0.0, -90.0, 0.0), "pick": (0.0, 60.0, -95.0, -55.0, -90.0, 0.0)}


def _rot(axis: np.ndarray, deg: float) -> np.ndarray:
    return K.rotation_matrix(axis, deg)


def forward(q: tuple[float, ...], R_: float) -> dict:
    """Tâm khớp + trục khớp (hệ thế giới) theo góc khớp q (độ) và tầm với R_."""
    g = S.UR_RATIOS
    d1, a2, a3 = g["d1"] * R_, g["a2"] * R_, g["a3"] * R_
    y2 = g["y_shoulder"] * R_
    yf = y2 - g["elbow_back"] * R_
    d4, d5, d6 = g["d4"] * R_, g["d5"] * R_, g["d6"] * R_
    q1, q2, q3, q4, q5, q6 = q
    Rz = _rot(np.array([0, 0, 1.0]), q1)
    ex, ey = Rz @ np.array([1.0, 0, 0]), Rz @ np.array([0, 1.0, 0])

    def plane(ang: float) -> np.ndarray:
        a = math.radians(ang)
        return Rz @ np.array([math.cos(a), 0.0, math.sin(a)])
    Sc = Rz @ np.array([0.0, y2, d1])
    u2 = plane(q2)
    E_up = Sc + a2 * u2
    E_fo = E_up + ey * (yf - y2)
    u3 = plane(q2 + q3)
    W1 = E_fo + a3 * u3
    a5 = plane(q2 + q3 + q4 + 90.0)
    W2 = W1 + ey * d4
    a6 = _rot(a5, q5) @ ey
    W3 = W2 + a5 * d5
    TF = W3 + a6 * d6
    x6 = _rot(a6, q6) @ a5                                   # hướng ngón kẹp (vuông góc trục dụng cụ)
    return dict(S=Sc, u2=u2, E_up=E_up, E_fo=E_fo, u3=u3, W1=W1, W2=W2, W3=W3, TF=TF, a5=a5, a6=a6, x6=x6, ex=ex,
                ey=ey, y2=y2, yf=yf, d1=d1, a2=a2, a3=a3, d4=d4, d5=d5, d6=d6)


def _cyl_between(p0: np.ndarray, p1: np.ndarray, r: float, seg: int = 64) -> K.Solid:
    d = p1 - p0
    L = float(np.linalg.norm(d))
    return K.cylinder(r, L, segments=seg).align_z(d / L, p0)


def _joint(radius: float, width: float, center: np.ndarray, axis: np.ndarray, housing: str, bolts: int = 8) -> list[Shape]:
    """Cụm khớp servo (mẫu actuator của robot hình người) đặt theo trục bất kỳ."""
    shapes = HU.actuator(radius, width, "z", (0.0, 0.0, 0.0), housing=housing, bolts=bolts)
    for sh in shapes:
        sh.solid = sh.solid.align_z(axis, center)
    return shapes


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    R_ = float(p.get("reach_mm", 850.0))
    payload = float(p.get("payload_kg", 5.0))
    industrial = p.get("style", "cobot") == "industrial"
    q = list(POSES.get(p.get("pose", "ready"), POSES["ready"]))
    for i in range(6):
        if p.get(f"j{i + 1}_deg") is not None:
            q[i] = float(p[f"j{i + 1}_deg"])
    f = forward(tuple(q), R_)
    mats = MC.tech_materials(spec, primary="#f39200" if industrial else "#dde1e5", secondary="#1b1d21",
                             accent="#2b2e33" if industrial else "#5fa8dc")
    b = AssemblyBuilder(spec.name or ("Robot công nghiệp 6 trục" if industrial else "Cánh tay robot cộng tác 6 trục"), "robot_arm", mats)
    shell = "paint_primary"
    r1, r3, r4 = 0.072 * R_, 0.058 * R_, 0.045 * R_
    ru, rf = 0.05 * R_, 0.04 * R_
    ey, ez = f["ey"], np.array([0, 0, 1.0])
    contacts: list[list[str]] = []
    # ---------- đế ----------
    tb = 0.022 * R_
    rb = 1.3 * r1
    z_b1 = 0.42 * f["d1"]
    base = K.revolve(P.fillet_polygon([(0, 0), (rb, 0), (rb, tb), (r1 * 1.02, tb + 0.01 * R_), (r1 * 1.02, z_b1), (0, z_b1)],
                                      [0, 0.004 * R_, 0.004 * R_, 0.01 * R_, 0.004 * R_, 0], 4), segments=96)
    holes = [(1.12 * r1 * math.cos(a), 1.12 * r1 * math.sin(a)) for a in np.radians([45, 135, 225, 315])]
    bd = max(4.0, round(0.012 * R_))
    base = base.subtract_all([K.cylinder(bd / 2 + 0.3, tb + 1, segments=16).translate(x, y, -0.5) for x, y in holes])
    bolts = K.Solid.union_all([MC.socket_screw(bd, tb + 6).translate(x, y, tb) for x, y in holes])
    base = base - D.panel_lines(base, [("z", z_b1 * 0.72)], width=0.0025 * R_, depth=0.002 * R_)
    conn_c = np.array([-r1 * 1.02, 0.0, z_b1 * 0.55])
    conn = K.cylinder(0.022 * R_, 0.03 * R_, segments=32).rotate(0, -90, 0).translate(*(conn_c + np.array([0.001, 0, 0])))
    lead_pts = np.array([conn_c + [-0.03 * R_, 0, 0], conn_c + [-0.08 * R_, 0, -0.1 * z_b1], [conn_c[0] - 0.14 * R_, 0.0, 0.012 * R_],
                         [conn_c[0] - 0.35 * R_, 0.05 * R_, 0.012 * R_]])
    lead = K.tube(P.spline_through(lead_pts, 40), 0.011 * R_, 16, rounded_ends=True)
    b.add("base", "Đế robot", "Base", "base",
          [Shape(base, shell, 40.0), Shape(bolts, "steel_black_oxide", 40.0), Shape(conn, "steel", 40.0), Shape(lead, "cable_black", 40.0)],
          required=True, aliases=["đế", "chân đế", "base", "đế robot", "cáp nguồn", "đầu nối"],
          function="Đế bắt 4 bu-lông xuống bệ; đầu nối + cáp nguồn/tín hiệu ra tủ điều khiển.", position_tag="bottom",
          dimensions={"base_d": 2 * rb})
    # ---------- khớp vai (J1 + J2) ----------
    w2 = 1.05 * r1
    J2c = f["S"] + ey * (w2 * 0.1)
    col = K.cylinder(r1, f["d1"] - z_b1 - 0.01 * R_, segments=96).translate(0, 0, z_b1)
    neck = K.hull([K.cylinder(r1 * 0.92, 0.01, segments=64).translate(0, 0, f["d1"] - 0.25 * r1),
                   K.cylinder(r1 * 0.92, 0.01, segments=64).align_z(ey, J2c - ey * (w2 / 2 - 0.01))])
    j12 = [Shape(col + neck, shell, 40.0)] + _joint(r1, w2, J2c, ey, shell)
    if industrial:                                          # động cơ servo đen gắn ngoài hộp số khớp (kiểu KUKA)
        j12.append(Shape(_servo_motor(0.42 * r1, 0.9 * r1).align_z(ey, J2c + ey * (w2 / 2 + 0.018 * w2)), "steel_black_oxide", 40.0))
    b.add("shoulder", "Khớp vai (J1 + J2)", "Shoulder (J1, J2)", "joint", j12, parent_id="base", required=True,
          aliases=["khớp vai", "vai", "khớp 1", "khớp 2", "j1", "j2", "shoulder", "khớp xoay đế"],
          function="J1 xoay quanh trục đứng ±360°, J2 nâng/hạ cánh tay (cụm servo + hộp số điều hòa).", position_tag="bottom",
          joint_axis=tuple(ez), explode_dir=(0, 0, 1), explode_distance=0.35 * R_, explode_order=9)
    # ---------- cánh tay trên ----------
    y_u = J2c + ey * (w2 / 2 - ru)                       # ống nằm lệch ra mặt bích ra của J2
    p0 = y_u
    p1 = y_u + f["a2"] * f["u2"]
    if industrial:
        tube = K.hull([K.rounded_box(ru * 2.4, ru * 1.6, ru * 1.8, ru * 0.5).transform(K.affine(_frame(f["u2"], ey), p0 + f["u2"] * r1 * 0.6)),
                       K.rounded_box(ru * 1.6, ru * 1.3, ru * 1.4, ru * 0.4).transform(K.affine(_frame(f["u2"], ey), p1 - f["u2"] * r3 * 0.6))])
        tube = tube + _cyl_between(p0, p1, ru * 0.62)
    else:
        tube = _cyl_between(p0, p1, ru)
        cuffs = [K.cylinder(ru * 1.08, 0.05 * R_, segments=64).align_z(f["u2"], p0 + f["u2"] * t) for t in (r1 * 0.9, f["a2"] - r3 * 0.9 - 0.05 * R_)]
        tube = tube + K.Solid.union_all(cuffs)
    b.add("upper_arm", "Cánh tay trên", "Upper arm", "link", Shape(tube, shell, 40.0), parent_id="shoulder", required=True,
          aliases=["cánh tay trên", "khâu 2", "tay trên", "upper arm", "link 2"],
          function=f"Khâu nối vai–khuỷu dài {f['a2']:.0f} mm (tâm J2 → tâm J3).", position_tag="center",
          joint_axis=tuple(ey), explode_dir=tuple(f["u2"]), explode_distance=0.25 * R_, explode_order=8,
          dimensions={"length": f["a2"]})
    # ---------- khuỷu (J3) ----------
    e_top = p1 + ey * ru
    e_bot = f["E_fo"] - ey * rf
    J3c = (e_top + e_bot) / 2
    w3 = float(np.linalg.norm(e_top - e_bot)) + 0.02 * R_
    elbow_shapes = _joint(r3, w3, J3c, ey, shell)
    if industrial:
        elbow_shapes.append(Shape(_servo_motor(0.42 * r3, 0.9 * r3).align_z(ey, J3c + ey * (w3 / 2 + 0.018 * w3)), "steel_black_oxide", 40.0))
    b.add("elbow", "Khớp khuỷu (J3)", "Elbow (J3)", "joint", elbow_shapes, parent_id="upper_arm", required=True,
          aliases=["khuỷu", "khớp khuỷu", "khớp 3", "j3", "elbow"], function="J3 gập/duỗi cẳng tay (cụm servo).",
          position_tag="center", explode_dir=tuple(ey), explode_distance=0.12 * R_, explode_order=7)
    # ---------- cẳng tay ----------
    f0 = f["E_fo"]
    f1 = f["W1"]
    if industrial:
        fore = K.hull([K.rounded_box(rf * 2.2, rf * 1.5, rf * 1.7, rf * 0.5).transform(K.affine(_frame(f["u3"], ey), f0 + f["u3"] * r3 * 0.6)),
                       K.rounded_box(rf * 1.5, rf * 1.2, rf * 1.3, rf * 0.4).transform(K.affine(_frame(f["u3"], ey), f1 - f["u3"] * r4 * 0.6))])
        fore = fore + _cyl_between(f0, f1, rf * 0.62)
    else:
        fore = _cyl_between(f0, f1, rf) + K.Solid.union_all([K.cylinder(rf * 1.08, 0.04 * R_, segments=64).align_z(f["u3"], f0 + f["u3"] * t)
                                                               for t in (r3 * 0.9, f["a3"] - r4 * 0.9 - 0.04 * R_)])
    b.add("forearm", "Cẳng tay", "Forearm", "link", Shape(fore, shell, 40.0), parent_id="elbow", required=True,
          aliases=["cẳng tay", "khâu 3", "forearm", "link 3", "tay dưới"],
          function=f"Khâu khuỷu–cổ tay dài {f['a3']:.0f} mm (tâm J3 → tâm J4).", position_tag="center",
          joint_axis=tuple(ey), explode_dir=tuple(f["u3"]), explode_distance=0.2 * R_, explode_order=6,
          dimensions={"length": f["a3"]})
    # ---------- cổ tay 1, 2, 3 ----------
    r5 = r6 = r4
    y_start = f["W1"] - ey * rf
    y_end = f["W2"] - ey * r5
    J4c = (y_start + y_end) / 2
    w4 = float(np.linalg.norm(y_end - y_start))
    b.add("wrist_1", "Cổ tay 1 (J4)", "Wrist 1 (J4)", "joint", _joint(r4, w4, J4c, ey, shell, 6), parent_id="forearm", required=True,
          aliases=["cổ tay 1", "khớp 4", "j4", "wrist 1"], function="J4 gật cổ tay.", position_tag="front",
          explode_dir=tuple(ey), explode_distance=0.1 * R_, explode_order=5)
    a5, a6 = f["a5"], f["a6"]
    s5 = f["W2"] - a5 * (r4 * 0.95)
    e5 = f["W3"] - a5 * r6
    J5c = (s5 + e5) / 2
    b.add("wrist_2", "Cổ tay 2 (J5)", "Wrist 2 (J5)", "joint", _joint(r5, float(np.linalg.norm(e5 - s5)), J5c, a5, shell, 6),
          parent_id="wrist_1", required=True, aliases=["cổ tay 2", "khớp 5", "j5", "wrist 2"],
          function="J5 lắc cổ tay (trục vuông góc J4).", position_tag="front", joint_axis=tuple(ey),
          explode_dir=tuple(a5), explode_distance=0.1 * R_, explode_order=4)
    fl = S.ISO9409[S.tool_flange_for(payload)]
    tf = max(6.0, 0.012 * R_)
    s6 = f["W3"] - a6 * (r5 * 0.95)
    e6 = f["TF"] - a6 * tf
    J6c = (s6 + e6) / 2
    b.add("wrist_3", "Cổ tay 3 (J6)", "Wrist 3 (J6)", "joint", _joint(r6, float(np.linalg.norm(e6 - s6)), J6c, a6, shell, 6),
          parent_id="wrist_2", required=True, aliases=["cổ tay 3", "khớp 6", "j6", "wrist 3"],
          function="J6 xoay mặt bích dụng cụ ±360°.", position_tag="front", joint_axis=tuple(a5),
          explode_dir=tuple(a6), explode_distance=0.1 * R_, explode_order=3)
    # ---------- mặt bích ISO 9409-1 ----------
    Dfl = max(fl["d"], 2 * r6 * 0.92)
    flange = K.revolve([(0, 0), (Dfl / 2, 0), (Dfl / 2, tf), (0, tf)], segments=96)
    flange = flange - K.cylinder(fl["pilot"] / 2, 6.0, segments=64).translate(0, 0, tf - 6.0 + 0.01)
    th = [K.cylinder(fl["thread"] / 2, tf + 2, segments=16).translate(fl["pcd"] / 2 * math.cos(a), fl["pcd"] / 2 * math.sin(a), -1)
          for a in np.radians(np.arange(fl["n"]) * 360.0 / fl["n"] + 45.0 * (fl["n"] == 4) + 30.0 * (fl["n"] == 6))]
    pin = K.cylinder(fl["pin"] / 2, tf + 2, segments=16).translate(fl["pcd"] / 2, 0, -1)
    flange = flange.subtract_all(th + [pin])
    x6 = f["x6"]
    fl_m = K.affine(np.column_stack([x6, np.cross(a6, x6), a6]), f["TF"] - a6 * tf)
    b.add("tool_flange", f"Mặt bích dụng cụ ISO 9409-1-{S.tool_flange_for(payload)}", "Tool flange", "tool_flange",
          Shape(flange.transform(fl_m), "steel", 40.0), parent_id="wrist_3", required=True,
          aliases=["mặt bích dụng cụ", "mặt bích", "tool flange", "đầu lắp dụng cụ", "iso 9409"],
          function=f"Mặt bích ISO 9409-1: {fl['n']} lỗ M{fl['thread']:g} trên Ø{fl['pcd']:g}, lỗ định tâm Ø{fl['pilot']:g} H7, chốt Ø{fl['pin']:g}.",
          position_tag="front", joint_axis=tuple(a6), explode_dir=tuple(a6), explode_distance=0.08 * R_, explode_order=2,
          dimensions={"pcd": fl["pcd"], "pilot": fl["pilot"]})
    # ---------- dụng cụ ----------
    eff = p.get("end_effector", "gripper")
    frame6 = np.column_stack([x6, np.cross(a6, x6), a6])
    place6 = lambda s: s.transform(K.affine(frame6, f["TF"]))  # noqa: E731
    if eff == "gripper":
        gw = 0.1 * R_
        adapter = K.cylinder(Dfl / 2 * 0.95, 0.012 * R_, segments=64)
        body = K.rounded_box(gw, 0.065 * R_, 0.07 * R_, 0.012 * R_).translate(0, 0, 0.012 * R_ + 0.035 * R_)
        body = body - D.panel_lines(body, [("z", 0.012 * R_ + 0.035 * R_)], width=0.002 * R_, depth=0.0015 * R_)
        fingers, pads = [], []
        for sx in (1, -1):
            fx = sx * 0.022 * R_
            fg = K.rounded_box(0.012 * R_, 0.04 * R_, 0.06 * R_, 0.003 * R_).translate(fx, 0, 0.082 * R_ + 0.03 * R_ - 0.001)
            pad = K.rounded_box(0.004 * R_, 0.036 * R_, 0.03 * R_, 0.0015 * R_).translate(fx - sx * 0.008 * R_, 0, 0.082 * R_ + 0.045 * R_)
            fingers.append(fg)
            pads.append(pad)
        led = K.cylinder(0.006 * R_, 0.002 * R_, segments=24).rotate(90, 0, 0).translate(0, -0.0325 * R_, 0.047 * R_)
        eff_shapes = [Shape(place6(adapter), "aluminum_dark", 40.0), Shape(place6(body), "plastic_black", 40.0),
                      Shape(place6(K.Solid.union_all(fingers)), "aluminum", 40.0), Shape(place6(K.Solid.union_all(pads)), "rubber", 40.0),
                      Shape(place6(led), "led_green", 40.0)]
        name, alias = "Tay kẹp hai ngón", ["tay kẹp", "kẹp", "gripper", "ngón kẹp", "đầu kẹp"]
        func = "Kẹp song song hai ngón (kiểu Robotiq 2F-85), đệm cao su, đèn trạng thái."
    elif eff == "vacuum":
        adapter = K.cylinder(Dfl / 2 * 0.95, 0.012 * R_, segments=64)
        gen = K.rounded_box(0.06 * R_, 0.035 * R_, 0.05 * R_, 0.005 * R_).translate(0, 0, 0.012 * R_ + 0.025 * R_)
        fit = K.cylinder(0.006 * R_, 0.02 * R_, segments=16).rotate(0, 90, 0).translate(0.03 * R_ - 0.001, 0, 0.037 * R_)
        stem = K.cylinder(0.008 * R_, 0.05 * R_, segments=24).translate(0, 0, 0.062 * R_ - 0.001)
        rc = 0.03 * R_
        prof = [(0.006 * R_, 0), (0.012 * R_, 0), (rc * 0.7, 0.012 * R_), (rc * 0.5, 0.018 * R_), (rc * 0.95, 0.03 * R_),
                (rc, 0.034 * R_), (0.006 * R_, 0.034 * R_)]
        cup = K.revolve(P.fillet_polygon(prof, [0, 0.002 * R_, 0.003 * R_, 0.003 * R_, 0.002 * R_, 0, 0], 3), segments=48)
        cup = cup.translate(0, 0, 0.112 * R_ - 0.002)
        eff_shapes = [Shape(place6(adapter), "aluminum_dark", 40.0), Shape(place6(gen), "aluminum", 40.0),
                      Shape(place6(fit + stem), "brass", 40.0), Shape(place6(cup), "rubber", 40.0)]
        name, alias = "Giác hút chân không", ["giác hút", "đầu hút", "vacuum", "cốc hút", "ventouse"]
        func = "Bộ tạo chân không venturi + giác hút ống xếp 1,5 nếp."
    else:
        eff_shapes = []
    if eff_shapes:
        b.add("end_effector", name, "End effector", "end_effector", eff_shapes, parent_id="tool_flange", required=True,
              aliases=alias, function=func, position_tag="front", explode_dir=tuple(a6), explode_distance=0.12 * R_,
              explode_order=1)
    # ---------- cáp dụng cụ chạy dọc cánh tay (kẹp trên ống) ----------
    rc = 0.009 * R_
    for pid, lp0, lp1, rr, dirv, parent in (("cable_upper", p0, p1, ru, f["u2"], "upper_arm"),
                                             ("cable_fore", f0, f1, rf, f["u3"], "forearm")):
        side = np.cross(dirv, ey)
        side = side / np.linalg.norm(side)
        if side[2] < 0:
            side = -side                                   # chạy phía trên/lưng khâu
        L_ = float(np.linalg.norm(lp1 - lp0))
        off = rr * (1.2 if industrial else 1.0) + rc + 0.5
        t0, t1 = (r1 + 0.03 * R_) / L_, 1 - (r3 + 0.03 * R_) / L_
        if parent == "forearm":
            t0, t1 = (r3 + 0.03 * R_) / L_, 1 - (r4 + 0.05 * R_) / L_
        pts = [lp0 + dirv * L_ * t + side * off for t in np.linspace(t0, t1, 6)]
        cab = K.tube(np.asarray(pts), rc, 14, rounded_ends=True)
        clips = []
        for t in np.linspace(t0 + 0.08, t1 - 0.08, 3):
            c0 = lp0 + dirv * L_ * t
            clips.append(K.box(0.012 * R_, 2.4 * rc, off + rc).transform(K.affine(np.column_stack([dirv, np.cross(side, dirv), side]),
                                                                                 c0 + side * (off + rc) / 2)))
        clip_s = K.Solid.union_all(clips) - cab.scale(1.0)
        b.add(pid, "Cáp dụng cụ " + ("(cánh tay trên)" if parent == "upper_arm" else "(cẳng tay)"), "Tool cable", "cable",
              [Shape(cab, "cable_black", 40.0), Shape(clip_s, "plastic_black", 40.0)], parent_id=parent,
              aliases=["cáp", "dây cáp", "cáp dụng cụ", "cable", "bó dây"],
              function="Cáp tín hiệu/khí cho dụng cụ, kẹp dọc khâu.", position_tag="top",
              explode_dir=tuple(side), explode_distance=0.08 * R_, explode_order=6 if parent == "forearm" else 8)
        contacts.append([pid, "elbow"])
    b.note_stage(1, "Tháo dụng cụ (kẹp / giác hút)")
    b.note_stage(2, "Tháo mặt bích dụng cụ")
    b.note_stage(3, "Tháo cổ tay 3")
    b.note_stage(4, "Tháo cổ tay 2")
    b.note_stage(5, "Tháo cổ tay 1")
    b.note_stage(6, "Tháo cẳng tay (+ cáp)")
    b.note_stage(7, "Tháo cụm khuỷu")
    b.note_stage(8, "Tháo cánh tay trên (+ cáp)")
    b.note_stage(9, "Tháo khớp vai khỏi đế")
    b.place_on_ground(center_xy=False)
    b.metadata.update({"reach_mm": R_, "payload_kg": payload, "style": "industrial" if industrial else "cobot",
                       "pose": p.get("pose", "ready"), "joint_deg": [round(x, 2) for x in q], "a2_mm": f["a2"], "a3_mm": f["a3"],
                       "d1_mm": f["d1"], "tool_flange": f"ISO 9409-1-{S.tool_flange_for(payload)}",
                       "tool_axis": [round(float(x), 4) for x in a6], "joints": 6,
                       "standard": "Tỷ lệ DH kiểu UR5 (co giãn theo tầm với), mặt bích ISO 9409-1",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()


def _servo_motor(r: float, L: float) -> K.Solid:
    """Động cơ servo AC: thân trụ có gân, nắp encoder, hộp đầu nối — mặt lắp z = 0, thân về +Z."""
    body = K.revolve(P.fillet_polygon([(0, 0), (r, 0), (r, L), (0.8 * r, L + 0.12 * r), (0, L + 0.12 * r)], [0, 0.05 * r, 0.1 * r, 0.05 * r, 0], 3),
                     segments=48)
    fins = D.cooling_fins(r * 0.96, L * 0.6, 12, 0.08 * r, 0.05 * r).translate(0, 0, L * 0.5)
    box = K.rounded_box(0.5 * r, 0.6 * r, 0.45 * r, 0.06 * r).translate(r * 1.1, 0, L * 0.7)
    return body + fins + box


def _frame(u: np.ndarray, ey: np.ndarray) -> np.ndarray:
    """Ma trận quay: trục X theo u, Y theo ey (đã trực giao hóa)."""
    x = u / np.linalg.norm(u)
    y = ey - x * float(ey @ x)
    y /= np.linalg.norm(y)
    return np.column_stack([x, y, np.cross(x, y)])
