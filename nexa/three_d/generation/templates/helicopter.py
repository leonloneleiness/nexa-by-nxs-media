"""Trực thăng: thân loft theo biên dạng B-spline (mũi tròn, cabin, đuôi thuôn), kính buồng lái, cửa sổ cabin,
nắp động cơ, cần đuôi, cánh đuôi đứng/ngang, rotor chính (trục, đầu rotor, N lá xoắn NACA 0012), rotor đuôi,
càng trượt dạng ống (hoặc bánh), tời cứu hộ và đèn pha cho vai trò cứu hộ.

Tách: lá rotor chính tách theo phương bán kính rồi đầu rotor/trục nhấc theo trục rotor, rotor đuôi tách theo trục
rotor đuôi, nắp động cơ mở lên, kính tiến ra trước, càng trượt hạ xuống, cần đuôi lùi ra sau.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import details as D
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

ROLE_COLORS = {"rescue": ("#c1121f", "#e9ecef", "#f4c20d"), "medical": ("#e9ecef", "#c1121f", "#1d4ed8"),
               "utility": ("#606c38", "#23262b", "#f77f00"), "civil": ("#14213d", "#e9ecef", "#22d3ee")}


def _fuselage_sections(Lf: float, ring: int = 64):
    """Mặt cắt thân: (x, rộng, cao, tâm z, độ vuông) theo tham số dọc thân (mũi ở +X)."""
    # điểm điều khiển biên dạng (t: 0 = mũi, 1 = cuối cabin nối cần đuôi)
    ctrl_w = [(0.0, 0.0), (0.03, 0.5), (0.12, 0.8), (0.3, 0.98), (0.55, 1.0), (0.78, 0.9), (0.92, 0.55), (1.0, 0.36)]
    ctrl_h = [(0.0, 0.0), (0.03, 0.48), (0.12, 0.78), (0.3, 0.97), (0.55, 1.0), (0.78, 0.92), (0.92, 0.6), (1.0, 0.38)]
    ctrl_z = [(0.0, -0.12), (0.12, -0.06), (0.4, 0.0), (0.8, 0.06), (1.0, 0.2)]
    ts = np.linspace(0, 1, 34)
    w = np.interp(ts, *zip(*ctrl_w))
    h = np.interp(ts, *zip(*ctrl_h))
    zc = np.interp(ts, *zip(*ctrl_z))
    w = np.sqrt(np.clip(w, 0, 1)) * np.clip(w, 0, 1) ** 0.5
    return ts, w, h, zc


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    Lh = float(p.get("length_mm", 12500))
    role = p.get("role", "rescue")
    rc = ROLE_COLORS.get(role, ROLE_COLORS["civil"])
    style = spec.style or {}
    primary = M.color_from_name(style.get("primary_color"), rc[0])
    secondary = M.color_from_name(style.get("secondary_color"), rc[1])
    accent = M.color_from_name(style.get("accent_color"), rc[2])
    mats = M.library(primary, secondary, accent)
    b = AssemblyBuilder(spec.name or "Trực thăng cứu hộ", "helicopter", mats)

    Lf = 0.5 * Lh                       # thân (mũi → hết cabin)
    cab_w, cab_h = 0.13 * Lh, 0.15 * Lh
    x_nose = 0.36 * Lh
    z0 = 0.16 * Lh                      # tâm thân (càng trượt ở z = 0)
    ring = 64
    ts, w, h, zc = _fuselage_sections(Lf, ring)
    secs = []
    for t, ww, hh, zz in zip(ts, w, h, zc):
        x = x_nose - t * Lf
        if ww < 1e-3:
            secs.append(np.repeat([[x, 0.0, z0 + zz * cab_h]], ring, axis=0))
            continue
        prof = P.superellipse(cab_w * ww, cab_h * hh, 2.3 + 0.9 * min(1.0, t * 2), ring, bottom_flat=0.25 * min(1.0, t * 3))
        secs.append(np.column_stack([np.full(ring, x), prof[:, 0], z0 + zz * cab_h + prof[:, 1]]))
    hull = K.loft(secs)
    # kính buồng lái: vùng trên-trước của mũi (tách khỏi thân, không có mặt trùng nhau)
    glass_cut = K.box(0.2 * Lh, cab_w * 1.5, 0.2 * Lh).rotate(0, -38, 0).translate(x_nose - 0.03 * Lh, 0, z0 + 0.1 * Lh)
    glass_cut = glass_cut & K.box(0.16 * Lh, cab_w * 1.5, cab_h * 2).translate(x_nose - 0.07 * Lh, 0, z0)
    # kính = lớp vỏ mỏng (không phải khối đặc chung mặt với thân → hết nhiễu); nhìn xuyên kính thấy khoang lái thật
    glass_t = 0.0035 * Lh
    canopy = (hull - D.shrink(hull, glass_t)) & glass_cut
    body = hull - glass_cut
    inner = D.shrink(hull, glass_t * 2.5) & glass_cut
    ilo, ihi = inner.bounds()
    dash = inner & K.box(0.05 * Lh, cab_w * 2, 0.05 * Lh).translate(float(ihi[0]) - 0.02 * Lh, 0, z0 - 0.015 * Lh)
    seats = K.Solid.union_all([
        K.rounded_box(0.035 * Lh, 0.035 * Lh, 0.012 * Lh, 0.004 * Lh).translate(x_nose - 0.115 * Lh, s_ * 0.026 * Lh, z0 - 0.035 * Lh) +
        K.rounded_box(0.01 * Lh, 0.035 * Lh, 0.05 * Lh, 0.004 * Lh).translate(x_nose - 0.135 * Lh, s_ * 0.026 * Lh, z0 - 0.01 * Lh)
        for s_ in (1, -1)])
    cockpit = (dash + seats) & D.shrink(hull, glass_t * 2)
    windows = []
    for side in (1, -1):
        for xw in (x_nose - 0.2 * Lh, x_nose - 0.28 * Lh):
            win = K.rounded_box(0.06 * Lh, cab_w, 0.045 * Lh, 0.012 * Lh).translate(xw, side * cab_w * 0.5, z0 + 0.025 * Lh)
            windows.append(win & hull)
    win_all = K.Solid.union_all(windows)
    body = body - win_all
    # chi tiết thật: đường viền cửa trượt khoang sau + cửa phi công (hai bên), đường ghép tấm, tay nắm, ray trượt cửa
    x_door, x_pilot = x_nose - 0.24 * Lh, x_nose - 0.1 * Lh
    body = body - D.outline_groove(hull, (x_door, 0, z0 + 0.005 * Lh), 0.17 * Lh, 0.115 * Lh, 0.0022 * Lh, 0.003 * Lh)
    body = body - D.outline_groove(hull, (x_pilot, 0, z0 + 0.0 * Lh), 0.075 * Lh, 0.1 * Lh, 0.0022 * Lh, 0.003 * Lh)
    body = body - D.panel_lines(hull, [("x", x_nose - 0.345 * Lh), ("x", x_nose - 0.045 * Lh), ("z", z0 - cab_h * 0.3)],
                                width=0.0018 * Lh, depth=0.0025 * Lh)
    fittings, rails = [], []
    for side in (1, -1):
        y_h = D.surface_at(hull, "y", (x_door - 0.07 * Lh, 0, z0 - 0.01 * Lh), positive=side > 0)
        if y_h is not None:
            fittings.append(K.rounded_box(0.012 * Lh, 0.004 * Lh, 0.004 * Lh, 0.0015 * Lh).translate(x_door - 0.07 * Lh,
                                                                                                     y_h + side * 0.001 * Lh,
                                                                                                     z0 - 0.01 * Lh))
        y_r = D.surface_at(hull, "y", (x_door, 0, z0 + 0.07 * Lh), positive=side > 0)
        if y_r is not None:
            rails.append(K.tube(np.array([[x_door + 0.08 * Lh, y_r + side * 0.0015 * Lh, z0 + 0.07 * Lh],
                                          [x_door - 0.16 * Lh, y_r + side * 0.0015 * Lh, z0 + 0.07 * Lh]]), 0.0022 * Lh, 12))
    # ống pitot hai bên mũi + ăng-ten lưỡi dưới bụng + đèn chống va đỏ dưới bụng
    pitots, blades = [], []
    for side in (1, -1):
        y_p = D.surface_at(hull, "y", (x_nose - 0.05 * Lh, 0, z0 - 0.02 * Lh), positive=side > 0)
        if y_p is not None:
            pitots.append(K.tube(np.array([[x_nose - 0.05 * Lh, y_p - side * 0.003 * Lh, z0 - 0.02 * Lh],
                                           [x_nose - 0.03 * Lh, y_p + side * 0.006 * Lh, z0 - 0.02 * Lh],
                                           [x_nose + 0.005 * Lh, y_p + side * 0.006 * Lh, z0 - 0.02 * Lh]]), 0.0016 * Lh, 10))
    z_belly = D.surface_at(hull, "z", (x_nose - 0.3 * Lh, 0, 0), positive=False) or (z0 - cab_h * 0.45)
    blades.append(K.hull([K.box(0.03 * Lh, 0.003 * Lh, 0.002 * Lh).translate(x_nose - 0.3 * Lh, 0, z_belly + 0.001 * Lh),
                          K.box(0.012 * Lh, 0.002 * Lh, 0.002 * Lh).translate(x_nose - 0.31 * Lh, 0, z_belly - 0.018 * Lh)]))
    beacon_b = K.sphere(0.006 * Lh, 20).scale(1, 1, 0.6).translate(x_nose - 0.38 * Lh, 0, (
        D.surface_at(hull, "z", (x_nose - 0.38 * Lh, 0, 0), positive=False) or z_belly))
    band = K.box(Lf * 1.2, cab_w * 2, 0.018 * Lh).translate(x_nose - Lf / 2, 0, z0 - 0.03 * Lh)
    stripe = body & band
    body = body - band
    b.add("fuselage", "Thân trực thăng", "Fuselage", "fuselage",
          [Shape(body, "paint_primary", 40.0), Shape(stripe, "paint_secondary", 40.0), Shape(win_all, "glass_tinted", 40.0),
           Shape(K.Solid.union_all(fittings + rails), "aluminum_dark", 40.0),
           Shape(K.Solid.union_all(pitots + blades), "stainless", 40.0), Shape(beacon_b, "led_red", 40.0),
           Shape(cockpit, "plastic_black", 40.0)],
          required=True, aliases=["thân", "thân máy bay", "khoang", "cabin", "fuselage", "thân chính", "lớp vỏ"],
          function="Khoang lái và khoang chở người/bệnh nhân, kết cấu chịu lực chính.", position_tag="center",
          dimensions={"length": round(Lf, 0), "width": round(cab_w, 0), "height": round(cab_h, 0)})
    b.add("canopy", "Kính buồng lái", "Cockpit canopy", "canopy", Shape(canopy, "glass", 40.0), parent_id="fuselage", required=True,
          aliases=["kính", "kính buồng lái", "kính chắn gió", "canopy", "buồng lái"],
          function="Kính chắn gió và kính quan sát cho phi công.", position_tag="front",
          explode_dir=(1, 0, 0.5), explode_distance=0.08 * Lh, explode_order=2)
    # ---------- nắp động cơ ----------
    x_c0, x_c1 = x_nose - 0.46 * Lh, x_nose - 0.16 * Lh
    csecs = []
    for t in np.linspace(0, 1, 20):
        x = x_c0 + t * (x_c1 - x_c0)
        ww = 0.075 * Lh * (math.sin(math.pi * min(1.0, 0.15 + t * 0.85)) ** 0.5)
        hh = 0.05 * Lh * (math.sin(math.pi * min(1.0, 0.1 + t * 0.9)) ** 0.6)
        if t >= 1.0:
            csecs.append(np.repeat([[x, 0.0, z0 + cab_h * 0.42]], 48, axis=0))
            continue
        prof = P.superellipse(max(ww, 1.0), max(2 * hh, 1.0), 2.6, 48)
        csecs.append(np.column_stack([np.full(48, x), prof[:, 0], z0 + cab_h * 0.42 + prof[:, 1]]))
    cowl_outer = K.loft(csecs) & K.box(Lh, Lh, Lh).translate(0, 0, z0 + cab_h * 0.42 + Lh / 2)
    cowl = cowl_outer - hull
    # lưới hút gió turbine hai bên + đường ghép nắp bảo dưỡng
    for side in (1, -1):
        y_v = D.surface_at(cowl_outer, "y", (x_c1 - 0.08 * Lh, 0, z0 + cab_h * 0.5), positive=side > 0)
        if y_v is not None:
            cowl = cowl - D.vent_cutter((x_c1 - 0.08 * Lh, y_v, z0 + cab_h * 0.5), (0, side, 0), (1, 0, 0), 0.06 * Lh,
                                        0.022 * Lh, 6, 0.006 * Lh)
    cowl = cowl - D.panel_lines(cowl_outer, [("x", x_c0 + 0.12 * Lh)], width=0.0018 * Lh, depth=0.0025 * Lh)
    exhausts = [K.tube(P.spline_through([(x_c0 + 0.03 * Lh, s_ * 0.05 * Lh, z0 + cab_h * 0.47),
                                         (x_c0 - 0.01 * Lh, s_ * 0.075 * Lh, z0 + cab_h * 0.5)], 12), 0.012 * Lh, 20)
                for s_ in (1, -1)]
    b.add("engine_cowling", "Nắp động cơ", "Engine cowling", "shell",
          [Shape(cowl, "paint_primary", 40.0), Shape(K.Solid.union_all(exhausts), "steel_black_oxide", 40.0)], parent_id="fuselage",
          required=True, aliases=["nắp động cơ", "động cơ", "vỏ động cơ", "cowling", "turbine", "lớp vỏ"],
          function="Che chắn hai động cơ turbine trục và hộp số chính.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.07 * Lh, explode_order=2)
    # ---------- cần đuôi, cánh đuôi ----------
    x_b0 = x_nose - Lf + 0.02 * Lh
    x_b1 = x_nose - 0.92 * Lh
    bsecs = []
    for t in np.linspace(0, 1, 16):
        x = x_b0 + t * (x_b1 - x_b0)
        rr = 0.03 * Lh * (1 - 0.5 * t)
        zz = z0 + cab_h * 0.08 + t * 0.03 * Lh
        prof = P.circle(rr, 40)
        bsecs.append(np.column_stack([np.full(40, x), prof[:, 0], zz + prof[:, 1]]))
    boom = K.loft(bsecs) - hull
    fin_af = P.naca4("0012", 1.0, 40)
    fsecs = []
    for t in np.linspace(0, 1, 8):
        chord = 0.1 * Lh * (1 - 0.45 * t)
        zz = z0 + cab_h * 0.08 + 0.03 * Lh + t * 0.1 * Lh - 0.01 * Lh
        xs = x_b1 + 0.02 * Lh - t * 0.05 * Lh
        fsecs.append(np.column_stack([xs + (0.9 - fin_af[:, 0]) * chord - chord, fin_af[:, 1] * chord * 1.2, np.full(len(fin_af), zz)]))
    fin = K.loft(fsecs)
    hsecs = []
    for s_ in np.linspace(-1, 1, 7):
        chord = 0.055 * Lh * (1 - 0.3 * abs(s_))
        yy = s_ * 0.075 * Lh
        hsecs.append(np.column_stack([x_b0 - 0.3 * Lh + (0.5 - fin_af[:, 0]) * chord, np.full(len(fin_af), yy),
                                      z0 + cab_h * 0.08 + 0.018 * Lh + fin_af[:, 1] * chord]))
    stab = K.loft(hsecs)
    end_plates = [K.rounded_box(0.035 * Lh, 0.004 * Lh, 0.03 * Lh, 0.002 * Lh).translate(x_b0 - 0.3 * Lh, s_ * 0.076 * Lh,
                                                                                        z0 + cab_h * 0.08 + 0.02 * Lh) for s_ in (1, -1)]
    b.add("tail_boom", "Cần đuôi", "Tail boom", "tail_boom", [Shape(boom, "paint_primary", 40.0)], parent_id="fuselage",
          required=True, aliases=["cần đuôi", "đuôi", "tail boom", "đuôi máy bay"],
          function="Mang rotor đuôi ở khoảng cách đủ để triệt tiêu mô-men xoắn của rotor chính.", position_tag="rear",
          explode_dir=(-1, 0, 0), explode_distance=0.08 * Lh, explode_order=3)
    # đèn hàng hải: đỏ bên trái, xanh bên phải (quy ước hàng không), đèn trắng ở đuôi cánh đứng
    nav = {side: K.sphere(0.004 * Lh, 16).scale(1.4, 0.8, 0.8).translate(x_b0 - 0.3 * Lh + 0.02 * Lh, side * 0.078 * Lh,
                                                                        z0 + cab_h * 0.08 + 0.02 * Lh) for side in (1, -1)}
    fin_lo, fin_hi = fin.bounds()
    tail_light = K.sphere(0.003 * Lh, 12).translate(float(fin_lo[0]) + 0.002 * Lh, 0, float(fin_hi[2]) - 0.01 * Lh)
    b.add("stabilizers", "Cánh đuôi", "Tail stabilizers", "stabilizer",
          [Shape(fin, "paint_primary", 40.0), Shape(stab + K.Solid.union_all(end_plates), "paint_secondary", 40.0),
           Shape(nav[1], "led_red", 40.0), Shape(nav[-1], "led_green", 40.0), Shape(tail_light, "led_white", 40.0)],
          parent_id="tail_boom", required=True, aliases=["cánh đuôi", "cánh ổn định", "đuôi đứng", "đuôi ngang", "stabilizer", "fin"],
          function="Cánh đuôi đứng và ngang ổn định hướng và độ chúc khi bay tiến.", position_tag="rear",
          explode_dir=(-0.3, 0, 1), explode_distance=0.05 * Lh, explode_order=3)
    # ---------- rotor chính ----------
    x_m = x_nose - 0.28 * Lh
    z_m = z0 + cab_h * 0.42 + 0.06 * Lh
    mast = K.cylinder(0.012 * Lh, 0.07 * Lh, segments=40).translate(x_m, 0, z0 + cab_h * 0.35)
    swash = K.cylinder(0.03 * Lh, 0.008 * Lh, segments=48).translate(x_m, 0, z_m - 0.035 * Lh)
    b.add("rotor_mast", "Trục rotor chính", "Main rotor mast", "rotor_mast", [Shape(mast, "steel", 40.0), Shape(swash, "aluminum", 40.0)],
          parent_id="engine_cowling", required=True, aliases=["trục rotor", "trục chính", "mast", "đĩa nghiêng"],
          function="Truyền mô-men từ hộp số tới đầu rotor; đĩa nghiêng điều khiển góc cánh.", position_tag="top",
          group="main_rotor", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=0.05 * Lh, explode_order=3)
    nb = int(p.get("main_blades", 4))
    hub = K.revolve(P.fillet_polygon([(0, -0.012 * Lh), (0.035 * Lh, -0.012 * Lh), (0.035 * Lh, 0.008 * Lh), (0.015 * Lh, 0.018 * Lh),
                                      (0, 0.018 * Lh)], [0, 0.004 * Lh, 0.006 * Lh, 0.004 * Lh, 0], 4), segments=64).translate(x_m, 0, z_m)
    grips = [K.rounded_box(0.05 * Lh, 0.018 * Lh, 0.014 * Lh, 0.005 * Lh).translate(0.045 * Lh, 0, 0).rotate(0, 0, 360 * k / nb)
             .translate(x_m, 0, z_m) for k in range(nb)]
    b.add("main_rotor_hub", "Đầu rotor chính", "Main rotor hub", "rotor_hub", [Shape(hub + K.Solid.union_all(grips), "aluminum_dark", 40.0)],
          parent_id="rotor_mast", required=True, aliases=["đầu rotor", "moay ơ rotor", "hub", "đầu cánh quạt", "rotor chính"],
          function="Giữ các lá rotor, cho phép thay đổi góc cánh chung/chu kỳ.", position_tag="top", group="main_rotor",
          joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=0.05 * Lh, explode_order=2)
    R = 0.43 * Lh
    af = P.naca4("0012", 1.0, 32)
    af[:, 0] -= 0.25
    for k in range(nb):
        rs = np.linspace(0.07 * Lh, R, 12)
        secs2 = []
        for r in rs:
            t = (r - rs[0]) / (R - rs[0])
            chord = 0.035 * Lh * (1 - 0.25 * max(0.0, t - 0.85) / 0.15)
            twist = math.radians(8 - 10 * t)
            ca, sa = math.cos(twist), math.sin(twist)
            x2 = af[:, 0] * chord * ca - af[:, 1] * chord * sa
            z2 = af[:, 0] * chord * sa + af[:, 1] * chord * ca
            sweep_back = 0.02 * Lh * max(0.0, (t - 0.9) / 0.1) ** 2
            secs2.append(np.column_stack([-x2 + sweep_back, np.full(len(af), r), z2 - 0.002 * Lh * t]))
        blade = K.loft(secs2).rotate(0, 0, 360.0 * k / nb + 45).translate(x_m, 0, z_m)
        tipc = K.cylinder(0.004 * Lh, 0.004 * Lh, segments=16).rotate(90, 0, 0)
        del tipc
        ang = 360.0 * k / nb + 45
        d = (math.cos(math.radians(ang + 90)), math.sin(math.radians(ang + 90)), 0.0)
        b.add(f"main_blade_{k + 1}", f"Lá rotor chính số {k + 1}", f"Main rotor blade {k + 1}", "rotor_blade",
              [Shape(blade, "paint_secondary" if role != "utility" else "carbon", 45.0)], parent_id="main_rotor_hub", required=True,
              aliases=["lá rotor", "cánh quạt", "cánh", "rotor", "lá cánh quạt", "blade", "cánh chính", "rotor chính"],
              function="Lá cánh composite tạo lực nâng và lực đẩy; profile NACA 0012, xoắn âm 10°.",
              position_tag=f"blade_{k + 1}", group="main_rotor", joint_axis=(0, 0, 1),
              dimensions={"length": round(R - 0.07 * Lh, 0), "chord": round(0.035 * Lh, 0)},
              explode_dir=d, explode_distance=0.12 * Lh, explode_order=1, no_clash_with=["fuselage", "tail_boom", "stabilizers"])
    # ---------- rotor đuôi (bên trái cánh đuôi, trục Y) ----------
    ntb = int(p.get("tail_rotor_blades", 4))
    xt, zt = x_b1 - 0.02 * Lh, z0 + cab_h * 0.08 + 0.1 * Lh
    yt = 0.02 * Lh
    thub = K.revolve(P.fillet_polygon([(0, 0), (0.012 * Lh, 0), (0.012 * Lh, 0.012 * Lh), (0, 0.016 * Lh)], [0, 0.003 * Lh, 0.004 * Lh, 0], 4),
                     segments=40).rotate(-90, 0, 0).translate(xt, yt, zt)
    b.add("tail_rotor_hub", "Đầu rotor đuôi", "Tail rotor hub", "rotor_hub", [Shape(thub, "aluminum_dark", 40.0)],
          parent_id="stabilizers", required=True, aliases=["rotor đuôi", "đầu rotor đuôi", "cánh quạt đuôi", "tail rotor"],
          function="Giữ các lá rotor đuôi.", position_tag="rear", group="tail_rotor", joint_axis=(0, 1, 0),
          explode_dir=(0, 1, 0), explode_distance=0.04 * Lh, explode_order=2)
    tr = 0.07 * Lh
    for k in range(ntb):
        rs = np.linspace(0.008 * Lh, tr, 7)
        secs3 = []
        for r in rs:
            chord = 0.014 * Lh
            secs3.append(np.column_stack([af[:, 0] * chord, af[:, 1] * chord * 1.2, np.full(len(af), r)]))
        tb = K.loft(secs3).rotate(0, 0, 90).rotate(0, 360.0 * k / ntb, 0)
        tb = tb.translate(xt, yt + 0.008 * Lh, zt)
        b.add(f"tail_blade_{k + 1}", f"Lá rotor đuôi số {k + 1}", f"Tail rotor blade {k + 1}", "rotor_blade",
              [Shape(tb, "paint_accent", 45.0)], parent_id="tail_rotor_hub", required=True,
              aliases=["lá rotor đuôi", "rotor đuôi", "cánh quạt đuôi", "cánh đuôi quạt", "tail blade"],
              function="Tạo lực ngang chống xoay thân do mô-men rotor chính.", position_tag="rear", group="tail_rotor",
              joint_axis=(0, 1, 0), explode_dir=(0, 1, 0), explode_distance=0.04 * Lh, explode_order=1)
    # ---------- càng trượt / bánh ----------
    if p.get("landing", "skids") == "skids":
        gear = []
        for side in (1, -1):
            skid = P.spline_through([(x_nose - 0.02 * Lh, side * 0.1 * Lh, 0.018 * Lh), (x_nose - 0.07 * Lh, side * 0.1 * Lh, 0.006 * Lh),
                                     (x_nose - 0.4 * Lh, side * 0.1 * Lh, 0.006 * Lh), (x_nose - 0.44 * Lh, side * 0.1 * Lh, 0.01 * Lh)], 40)
            gear.append(K.tube(skid, 0.008 * Lh, 20, rounded_ends=True))
        for xc in (x_nose - 0.12 * Lh, x_nose - 0.34 * Lh):
            cross = P.spline_through([(xc, 0.1 * Lh, 0.006 * Lh), (xc, 0.085 * Lh, 0.07 * Lh), (xc, 0.04 * Lh, z0 - cab_h * 0.38),
                                      (xc, -0.04 * Lh, z0 - cab_h * 0.38), (xc, -0.085 * Lh, 0.07 * Lh), (xc, -0.1 * Lh, 0.006 * Lh)], 40)
            gear.append(K.tube(cross, 0.007 * Lh, 18))
        b.add("landing_skids", "Càng trượt", "Landing skids", "landing_gear", [Shape(K.Solid.union_all(gear), "aluminum", 40.0)],
              parent_id="fuselage", required=True, aliases=["càng", "càng trượt", "càng đáp", "chân đáp", "skid", "landing gear"],
              function="Càng trượt dạng ống hấp thụ va chạm khi hạ cánh.", position_tag="bottom",
              explode_dir=(0, 0, -1), explode_distance=0.08 * Lh, explode_order=2)
    else:
        wheels = []
        for (xw, yw) in ((x_nose - 0.05 * Lh, 0.0), (x_nose - 0.33 * Lh, 0.09 * Lh), (x_nose - 0.33 * Lh, -0.09 * Lh)):
            wheels.append(K.cylinder(0.022 * Lh, 0.018 * Lh, segments=48).rotate(90, 0, 0).translate(xw, yw + 0.009 * Lh, 0.022 * Lh))
            wheels.append(K.tube(np.array([[xw, yw, 0.022 * Lh], [xw, yw * 0.7, z0 - cab_h * 0.35]]), 0.006 * Lh, 16))
        b.add("landing_gear", "Càng bánh", "Wheeled landing gear", "landing_gear", [Shape(K.Solid.union_all(wheels), "rubber", 40.0)],
              parent_id="fuselage", required=True, aliases=["càng", "bánh", "càng đáp", "landing gear"],
              function="Càng bánh cố định cho lăn trên mặt đất.", position_tag="bottom", explode_dir=(0, 0, -1),
              explode_distance=0.08 * Lh, explode_order=2)
    # ---------- tời cứu hộ, đèn pha ----------
    if p.get("hoist", role == "rescue") and role in ("rescue", "medical", "utility"):
        yh = -cab_w * 0.5
        arm = K.tube(P.spline_through([(x_nose - 0.2 * Lh, yh, z0 + cab_h * 0.36), (x_nose - 0.2 * Lh, yh - 0.03 * Lh, z0 + cab_h * 0.4),
                                       (x_nose - 0.2 * Lh, yh - 0.06 * Lh, z0 + cab_h * 0.36)], 16), 0.006 * Lh, 16)
        drum = K.cylinder(0.014 * Lh, 0.035 * Lh, segments=40).rotate(0, 90, 0).translate(x_nose - 0.218 * Lh, yh - 0.06 * Lh, z0 + cab_h * 0.33)
        cable = K.cylinder(0.0012 * Lh, 0.05 * Lh, segments=8).translate(x_nose - 0.2 * Lh, yh - 0.06 * Lh, z0 + cab_h * 0.33 - 0.05 * Lh)
        hook = K.torus(0.006 * Lh, 0.0018 * Lh, segments=24, tube_segments=8).rotate(90, 0, 0).translate(x_nose - 0.2 * Lh, yh - 0.06 * Lh,
                                                                                                    z0 + cab_h * 0.33 - 0.056 * Lh)
        b.add("rescue_hoist", "Tời cứu hộ", "Rescue hoist", "hoist",
              [Shape(arm + drum, "paint_accent", 40.0), Shape(cable + hook, "steel", 40.0)], parent_id="fuselage", required=role == "rescue",
              aliases=["tời", "tời cứu hộ", "móc cứu hộ", "hoist", "cần cẩu"],
              function="Tời điện nâng hạ người/cáng cứu thương qua cửa bên phải.", position_tag="right",
              explode_dir=(0, -1, 0), explode_distance=0.06 * Lh, explode_order=2)
    if p.get("searchlight", role == "rescue"):
        base_l = K.cylinder(0.01 * Lh, 0.012 * Lh, segments=32).translate(x_nose - 0.07 * Lh, 0, z0 - cab_h * 0.46)
        lamp = K.sphere(0.016 * Lh, 40).translate(x_nose - 0.07 * Lh, 0, z0 - cab_h * 0.5)
        lens = K.cylinder(0.012 * Lh, 0.004 * Lh, segments=32).rotate(0, 110, 0).translate(x_nose - 0.056 * Lh, 0, z0 - cab_h * 0.505)
        b.add("searchlight", "Đèn pha tìm kiếm", "Searchlight", "light",
              [Shape(base_l + lamp, "aluminum_dark", 40.0), Shape(lens, "led_white", 40.0)], parent_id="fuselage",
              aliases=["đèn pha", "đèn", "đèn tìm kiếm", "searchlight"], function="Đèn công suất lớn chiếu sáng khu vực tìm kiếm ban đêm.",
              position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.05 * Lh, explode_order=2)
    b.note_stage(1, "Tách lá rotor chính và rotor đuôi theo phương bán kính/trục")
    b.note_stage(2, "Nhấc đầu rotor, mở nắp động cơ, kính, hạ càng, tháo tời/đèn")
    b.note_stage(3, "Nhấc trục rotor, tách cần đuôi và cánh đuôi")
    b.metadata.update({"main_blades": nb, "tail_rotor_blades": ntb, "rotor_diameter_mm": 2 * R, "ground_z_mm": 0.0,
                       "rotor_disk": {"center": [x_m, 0.0, z_m], "radius": R}})
    return b.build()
