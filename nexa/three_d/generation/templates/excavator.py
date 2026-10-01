"""Máy xúc bánh xích (máy đào thủy lực): cỡ mini (~3 t), trung (~20 t, tỷ lệ kiểu CAT 320 / Komatsu PC200), lớn (~45 t).

- Gầm xích: khung xích + bánh dẫn hướng (trước) + bánh sao chủ động (sau) + con lăn đỡ dưới/trên, xích guốc có vấu bám
  (bề rộng guốc, khoảng cách tâm hai dải xích theo bảng cỡ máy), ổ quay toàn vòng.
- Thân trên quay góc swing: sàn, cabin (kính là lớp mỏng trong hốc), nắp động cơ + ống xả, đối trọng đuôi tròn
  (bán kính quay đuôi), giá chân cần.
- Cần (boom) cong kiểu "chuối", tay gầu (stick), gầu có răng + thanh nối; 4 xi lanh thủy lực (2 nâng cần, 1 tay gầu,
  1 gầu) — mắt xi lanh ôm đúng chốt của bộ phận được nối (kiểm tra hình học), cần piston nằm trong hành trình.
- Tư thế: đào / di chuyển / vươn xa; gầu luôn ở trên mặt đất (tự nâng cần nếu cần).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# k: hệ số tỷ lệ; gauge: khoảng cách tâm hai dải xích; shoe: bề rộng guốc; boom/stick: chiều dài chốt–chốt (mm, k = 1)
SIZES = {"mini": dict(k=0.45, t=3.0, gauge=1300.0, shoe=300.0, boom=2500.0, stick=1350.0, tail=875.0),
         "medium": dict(k=1.0, t=20.0, gauge=2200.0, shoe=600.0, boom=5700.0, stick=2900.0, tail=2750.0),
         "large": dict(k=1.3, t=45.0, gauge=2750.0, shoe=700.0, boom=7000.0, stick=3350.0, tail=3500.0)}
POSES = {"dig": (38.0, -78.0, -40.0), "transport": (58.0, -105.0, 40.0), "reach": (14.0, -22.0, -55.0)}   # cần, tay gầu, gầu (độ)


def beam(p0: np.ndarray, p1: np.ndarray, h0: float, h1: float, w: float, y: float) -> K.Solid:
    """Dầm hộp bo tròn trong mặt XZ: bao lồi hai đĩa trụ (trục Y) đường kính h0, h1 tại p0, p1."""
    d0 = K.cylinder(h0 / 2, w, segments=32).rotate(90, 0, 0).translate(p0[0], y + w / 2, p0[2])
    d1 = K.cylinder(h1 / 2, w, segments=32).rotate(90, 0, 0).translate(p1[0], y + w / 2, p1[2])
    return K.hull([d0, d1])


def v2(a_deg: float) -> np.ndarray:
    return np.array([math.cos(math.radians(a_deg)), 0.0, math.sin(math.radians(a_deg))])


def nrm(a_deg: float) -> np.ndarray:
    return np.array([-math.sin(math.radians(a_deg)), 0.0, math.cos(math.radians(a_deg))])


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    size = p.get("size_class", "medium")
    Sz = SIZES[size]
    k = Sz["k"]
    pose = p.get("pose", "dig")
    swing = float(p.get("swing_deg", 0.0))
    mats = MC.tech_materials(spec, primary="#f2b705", secondary="#1b1d21", accent="#e63946")
    b = AssemblyBuilder(spec.name or f"Máy xúc bánh xích {Sz['t']:g} t", "excavator", mats)
    G, shoe = Sz["gauge"], Sz["shoe"]
    Ht, Lt = 950.0 * k, 4450.0 * k
    tb, gh = 80.0 * k, 28.0 * k                                       # dày xích, cao vấu bám
    contacts: list[list[str]] = []

    # ---------- gầm xích ----------
    r_end = Ht / 2
    xe = Lt / 2 - r_end
    rc = r_end - gh - tb / 2                                          # bán kính đường tâm xích quanh bánh đầu
    zc = gh + tb / 2 + rc                                             # tâm bánh dẫn/bánh sao
    path = []
    for t in np.linspace(0, 1, 90, endpoint=False):
        s = t * (2 * math.pi * rc + 4 * xe)
        L1 = 2 * xe
        if s < L1:
            path.append((xe - s, zc - rc))
        elif s < L1 + math.pi * rc:
            a = (s - L1) / rc
            path.append((-xe - rc * math.sin(a), zc - rc * math.cos(a)))
        elif s < 2 * L1 + math.pi * rc:
            path.append((-xe + (s - L1 - math.pi * rc), zc + rc))
        else:
            a = (s - 2 * L1 - math.pi * rc) / rc
            path.append((xe + rc * math.sin(a), zc + rc * math.cos(a)))
    path = np.array(path)
    under_parts, rollers = [], []
    r_roll = 0.12 * Ht
    n_roll = 7 if size != "mini" else 4
    for sy in (1, -1):
        yc = sy * G / 2
        p3 = np.column_stack([path[:, 0], np.full(len(path), yc), path[:, 1]])
        belt = K.sweep(P.rounded_rect(tb, shoe, 0.2 * tb, 2), np.vstack([p3, p3[:1]]))
        grous = []
        n_g = int((2 * math.pi * rc + 4 * xe) / (190.0 * k))
        tot = len(path)
        for i in range(n_g):
            j = int(i * tot / n_g)
            q, qn = path[j], path[(j + 1) % tot]
            tang = (qn - q) / np.linalg.norm(qn - q)
            out = np.array([tang[1], -tang[0]])                          # pháp tuyến ra ngoài (đường chạy ngược chiều kim đồng hồ)
            c = q + out * (tb / 2 + gh / 2)
            ang = math.degrees(math.atan2(tang[1], tang[0]))
            grous.append(K.box(0.18 * 190.0 * k, shoe, gh).rotate(0, -ang, 0).translate(c[0], yc, c[1]))
        side = "left" if sy > 0 else "right"
        under_parts.append((side, sy, yc, belt, K.Solid.union_all(grous)))
        z_in_bot = gh + tb
        for x in np.linspace(-xe + 0.1 * Lt, xe - 0.1 * Lt, n_roll):
            rollers.append(K.cylinder(r_roll, 0.55 * shoe, segments=28).rotate(90, 0, 0).translate(x, yc + 0.275 * shoe, z_in_bot + r_roll))
        for x in (-0.25 * Lt, 0.25 * Lt):
            rollers.append(K.cylinder(0.6 * r_roll, 0.4 * shoe, segments=24).rotate(90, 0, 0).translate(x, yc + 0.2 * shoe, zc + rc - tb / 2 - 0.6 * r_roll))
    frames, ends = [], []
    r_idl = rc - tb / 2
    for sy in (1, -1):
        yc = sy * G / 2
        fz0, fz1 = gh + tb + 2 * r_roll - 20.0 * k, zc + rc - tb / 2 - 1.2 * r_roll
        frames.append(K.rounded_box(2 * xe, 0.5 * shoe, fz1 - fz0, 40.0 * k, segments=8).translate(0, yc, (fz0 + fz1) / 2))
        idler = K.cylinder(r_idl, 0.5 * shoe, segments=48).rotate(90, 0, 0).translate(xe, yc + 0.25 * shoe, zc)
        sprk = K.extrude(P.involute_gear(2 * r_idl / 20.0, 20), 0.35 * shoe).rotate(90, 0, 0).translate(-xe, yc + 0.175 * shoe, zc)
        sprk = sprk & K.cylinder(r_idl, shoe, segments=48).rotate(90, 0, 0).translate(-xe, yc + 0.5 * shoe, zc)
        motor = K.cylinder(0.45 * r_idl, 0.35 * shoe, segments=32).rotate(90, 0, 0).translate(-xe, yc - sy * 0.3 * shoe + 0.175 * shoe, zc)
        ends += [idler, sprk, motor]
    z_cb0, z_cb1 = 0.4 * Ht, 0.85 * Ht
    carbody = K.rounded_box(0.45 * Lt, G, z_cb1 - z_cb0, 60.0 * k, segments=8).translate(0, 0, (z_cb0 + z_cb1) / 2)
    z_u = Ht + 180.0 * k
    ring = K.cylinder(0.9 * 1000.0 * k, z_u - z_cb1, segments=64).translate(0, 0, z_cb1)
    b.add("undercarriage", "Gầm xích (khung, bánh dẫn, bánh sao, con lăn)", "Undercarriage", "undercarriage",
          [Shape(K.Solid.union_all(frames) + carbody, "paint_primary", 40.0), Shape(K.Solid.union_all(ends + rollers), "steel", 40.0),
           Shape(ring, "steel_dark", 40.0)], required=True,
          aliases=["gầm", "gầm xích", "khung xích", "bánh sao", "bánh dẫn hướng", "con lăn", "ổ quay", "undercarriage"],
          function=f"Khung gầm + 2 khung xích, bánh dẫn hướng trước, bánh sao + motor di chuyển sau, {n_roll} con lăn đỡ dưới, ổ quay toàn vòng.",
          position_tag="bottom", dimensions={"track_gauge": G, "track_length": Lt})
    for side, sy, yc, belt, grous in under_parts:
        b.add(f"track_{side}", f"Dải xích {'trái' if sy > 0 else 'phải'}", "Crawler track", "track",
              [Shape(belt, "steel_dark", 40.0), Shape(grous, "steel_dark", 40.0)], parent_id="undercarriage", required=True,
              aliases=["xích", "dải xích", "guốc xích", "bánh xích", "track"], function=f"Xích guốc {shoe:.0f} mm có vấu bám.",
              position_tag="left" if sy > 0 else "right", explode_dir=(0, sy, 0), explode_distance=0.5 * shoe + 300.0 * k, explode_order=1,
              dimensions={"shoe_width": shoe})

    # ---------- thân trên (hệ cục bộ, quay swing quanh Z) ----------
    rot = lambda s_: s_.rotate(0, 0, swing)                            # noqa: E731
    R_sw = np.array([[math.cos(math.radians(swing)), -math.sin(math.radians(swing)), 0], [math.sin(math.radians(swing)), math.cos(math.radians(swing)), 0],
                     [0, 0, 1.0]])
    rp = lambda v: R_sw @ np.asarray(v, float)                          # noqa: E731
    tail = Sz["tail"]
    hd = 250.0 * k
    deck = K.rounded_box(4000.0 * k, 2800.0 * k, hd, 80.0 * k, segments=8).translate(-500.0 * k, 0, z_u + hd / 2)
    deck = deck & K.cylinder(tail + 5.0, 3 * hd, segments=96).translate(0, 0, z_u - hd)
    x_cw = -0.55 * tail                                               # đối trọng: hình quạt tròn đuôi, bán kính quay đuôi = tail
    cw = (K.cylinder(tail, 900.0 * k, segments=96) & K.box(tail, 2800.0 * k, 2000.0 * k).translate(x_cw - tail / 2, 0, 0)).translate(0, 0, z_u + hd)
    x_h1 = -700.0 * k
    hood = K.rounded_box(x_h1 - x_cw, 1650.0 * k, 800.0 * k, 60.0 * k, segments=8).translate((x_cw + x_h1) / 2, -575.0 * k, z_u + hd + 400.0 * k)
    stack = K.cylinder(60.0 * k, 450.0 * k, segments=20).translate((x_cw + x_h1) / 2, -900.0 * k, z_u + hd + 780.0 * k)
    grille = K.Solid.union_all([K.box(0.8 * (x_h1 - x_cw), 12.0 * k, 30.0 * k).translate((x_cw + x_h1) / 2, -1400.0 * k, z_u + hd + (200.0 + 80.0 * i) * k)
                                for i in range(6)])
    y_b = -250.0 * k
    xF, zF = 850.0 * k, z_u + 900.0 * k
    F = np.array([xF, y_b, zF])
    tower = beam(np.array([xF - 500.0 * k, 0, z_u + hd]), F, 250.0 * k, 520.0 * k, 700.0 * k, y_b - 350.0 * k)
    tower = tower - K.box(1e5, 1e5, 1e5).translate(0, 0, z_u + hd - 5e4)
    # cabin
    cab_x0, cab_x1, cab_y0, cab_y1 = -600.0 * k, 1050.0 * k, 350.0 * k, 1350.0 * k
    cab_h = 1650.0 * k
    cab = K.rounded_box(cab_x1 - cab_x0, cab_y1 - cab_y0, cab_h, 90.0 * k, segments=12).translate((cab_x0 + cab_x1) / 2, (cab_y0 + cab_y1) / 2,
                                                                                                  z_u + hd + cab_h / 2)
    wins = [(K.box(400.0 * k, (cab_y1 - cab_y0) * 0.78, cab_h * 0.72).translate(cab_x1, (cab_y0 + cab_y1) / 2, z_u + hd + cab_h * 0.57), (1, 0, 0)),
            (K.box((cab_x1 - cab_x0) * 0.72, 400.0 * k, cab_h * 0.55).translate((cab_x0 + cab_x1) / 2 + 80.0 * k, cab_y1, z_u + hd + cab_h * 0.62), (0, 1, 0)),
            (K.box((cab_x1 - cab_x0) * 0.6, 400.0 * k, cab_h * 0.4).translate((cab_x0 + cab_x1) / 2 + 150.0 * k, cab_y0, z_u + hd + cab_h * 0.68), (0, -1, 0))]
    recs, panes = [], []
    for bx, n_ in wins:
        n_ = np.array(n_, float)
        recs.append(bx - cab.translate(*(-n_ * 35.0 * k)))
        panes.append((bx & cab) - cab.translate(*(-n_ * 8.0 * k)))
    cab_body = cab - K.Solid.union_all(recs)
    glass = K.Solid.union_all(panes)
    seat = K.rounded_box(450.0 * k, 480.0 * k, 450.0 * k, 50.0 * k, segments=6).translate(0.0, 850.0 * k, z_u + hd + 225.0 * k)
    # xi lanh nâng cần: chân trên sàn (giá đỡ), đầu cần ở mặt dưới cần
    alpha0, beta, dgam = POSES[pose]
    Lb, Ls = Sz["boom"], Sz["stick"]
    boom_h, boom_w = 720.0 * k, 600.0 * k
    stick_w = 440.0 * k
    Rb = 0.5 * Ls
    alpha = alpha0

    def geometry(alpha: float) -> dict:
        dT = v2(alpha)
        T = F + Lb * dT
        knee = F + 0.52 * Lb * dT + 0.16 * Lb * nrm(alpha)
        dS = v2(beta)
        S = T + Ls * dS
        dB = v2(beta + dgam)
        tip = S + Rb * dB
        return {"T": T, "knee": knee, "S": S, "dS": dS, "tip": tip, "dB": dB}

    for _ in range(40):                                               # gầu phải ở trên mặt đất
        g = geometry(alpha)
        low = min(g["tip"][2], g["S"][2]) - 0.35 * Rb
        if low > 80.0 * k:
            break
        alpha += 2.0
    g = geometry(alpha)
    T, knee, S, dS, dB = g["T"], g["knee"], g["S"], g["dS"], g["dB"]
    nS = nrm(beta)
    boom = beam(F, knee, 0.75 * boom_h, boom_h, boom_w, y_b - boom_w / 2) + beam(knee, T, boom_h, 0.62 * boom_h, boom_w, y_b - boom_w / 2)
    dFK = (knee - F) / np.linalg.norm(knee - F)
    nFK = np.array([-dFK[2], 0, dFK[0]])
    pin_bc = F + 0.62 * np.linalg.norm(knee - F) * dFK - (0.5 * boom_h + 120.0 * k) * nFK        # chốt đầu cần xi lanh nâng cần (dưới cần)
    pin_sc = knee - 0.15 * np.linalg.norm(knee - F) * dFK + (0.5 * boom_h + 160.0 * k) * nFK      # chốt đáy xi lanh tay gầu (lưng cần)
    lug_bc = beam(pin_bc, pin_bc + (0.5 * boom_h) * nFK, 220.0 * k, 260.0 * k, boom_w + 160.0 * k, y_b - boom_w / 2 - 80.0 * k)
    lug_sc = beam(pin_sc, pin_sc - (0.5 * boom_h) * nFK, 220.0 * k, 260.0 * k, 0.5 * boom_w, y_b - boom_w / 4)
    pins_boom = [MC.pin(F, (0, 1, 0), 110.0 * k, boom_w + 120.0 * k), MC.pin(T, (0, 1, 0), 100.0 * k, boom_w + 80.0 * k),
                 MC.pin(pin_bc, (0, 1, 0), 90.0 * k, boom_w + 900.0 * k), MC.pin(pin_sc, (0, 1, 0), 90.0 * k, 0.5 * boom_w + 200.0 * k)]
    y_bc = boom_w / 2 + 0.12 * 1.24 * 150.0 * k + 110.0 * k                              # xi lanh nâng cần hai bên cần
    base_bc = np.array([1450.0 * k, y_b, z_u + hd + 250.0 * k])
    brk_bc = K.Solid.union_all([beam(np.array([1450.0 * k, 0, z_u + hd]), base_bc, 200.0 * k, 240.0 * k, 110.0 * k, y_b + sy * y_bc - 55.0 * k)
                                for sy in (1, -1)])
    brk_bc = brk_bc - K.box(1e5, 1e5, 1e5).translate(0, 0, z_u + hd - 5e4)
    pin_base = MC.pin(base_bc, (0, 1, 0), 90.0 * k, 2 * y_bc + 200.0 * k)
    upper = [Shape(deck + tower + brk_bc, "paint_primary", 40.0), Shape(cw, "paint_secondary", 40.0), Shape(hood, "paint_primary", 40.0),
             Shape(stack, "steel_dark", 40.0), Shape(grille, "steel_dark", 40.0), Shape(pin_base, "steel", 40.0)]
    b.add("upper_structure", "Thân trên (sàn quay, nắp máy, đối trọng)", "Upper structure", "upper_structure",
          [Shape(rot(s_.solid), s_.material, 40.0) for s_ in upper], parent_id="undercarriage", required=True,
          aliases=["thân trên", "bàn quay", "mâm quay", "nắp máy", "động cơ", "đối trọng", "ống xả", "upper structure"],
          function=f"Sàn quay toàn vòng (góc quay {swing:g}°), khoang động cơ diesel + bơm thủy lực, đối trọng đuôi tròn R{tail:.0f} mm.",
          position_tag="center", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=1200.0 * k, explode_order=4)
    b.add("cab", "Cabin người lái", "Operator cab", "cab",
          [Shape(rot(cab_body), "paint_primary", 40.0), Shape(rot(glass), "glass_tinted", 40.0), Shape(rot(seat), "plastic_black", 40.0)],
          parent_id="upper_structure", required=True, aliases=["cabin", "buồng lái", "ca bin", "kính cabin", "ghế lái", "cab"],
          function="Cabin ROPS/FOPS bên trái, kính trước + hông, ghế lái + cần điều khiển.", position_tag="left",
          explode_dir=(0, 0, 1), explode_distance=900.0 * k, explode_order=2)
    b.add("boom", "Cần (boom)", "Boom", "boom",
          [Shape(rot(boom + lug_bc + lug_sc), "paint_primary", 40.0), Shape(rot(K.Solid.union_all(pins_boom)), "steel", 40.0)],
          parent_id="upper_structure", required=True, aliases=["cần", "cần máy xúc", "boom", "cần chính"],
          function=f"Cần hộp hàn cong, dài chốt–chốt {Lb:.0f} mm, góc nâng {alpha:.0f}°.", position_tag="front", joint_axis=(0, 1, 0),
          explode_dir=(1, 0, 0.4), explode_distance=900.0 * k, explode_order=3, dimensions={"boom_length": Lb})
    # tay gầu
    heel = T - 0.22 * Ls * dS + 0.14 * Ls * nS
    stick = beam(heel, T, 0.5 * stick_w + 120.0 * k, 560.0 * k, stick_w, y_b - stick_w / 2) + beam(T, S, 560.0 * k, 360.0 * k, stick_w, y_b - stick_w / 2)
    pin_bk0 = T + 0.06 * Ls * dS + 0.2 * Ls * nS                                           # đáy xi lanh gầu (lưng tay gầu)
    lug_bk = beam(pin_bk0, pin_bk0 - 0.12 * Ls * nS, 200.0 * k, 240.0 * k, 0.5 * stick_w, y_b - stick_w / 4)
    link_p = S - 0.13 * Ls * dS + 0.16 * Ls * nS                                           # chốt thanh nối gầu
    pins_st = [MC.pin(S, (0, 1, 0), 90.0 * k, stick_w + 200.0 * k), MC.pin(heel, (0, 1, 0), 90.0 * k, stick_w + 60.0 * k),
               MC.pin(pin_bk0, (0, 1, 0), 80.0 * k, 0.5 * stick_w + 160.0 * k)]
    b.add("stick", "Tay gầu (stick)", "Stick (arm)", "stick",
          [Shape(rot(stick + lug_bk), "paint_primary", 40.0), Shape(rot(K.Solid.union_all(pins_st)), "steel", 40.0)], parent_id="boom", required=True,
          aliases=["tay gầu", "tay cần", "cánh tay", "stick", "arm"], function=f"Tay gầu dài {Ls:.0f} mm, quay quanh chốt đầu cần.",
          position_tag="front", joint_axis=(0, 1, 0), explode_dir=(1, 0, 0), explode_distance=700.0 * k, explode_order=2,
          dimensions={"stick_length": Ls})
    # gầu
    wB = 1100.0 * k
    uB, vB = dB, np.array([-dB[2], 0, dB[0]])                            # u: chốt → răng; v: lưng gầu
    arc = []
    for t in np.linspace(0, 1, 18):
        a = math.pi * t
        arc.append(0.5 * Rb * (1 - math.cos(a)) * uB + (-0.42 * Rb * math.sin(a)) * vB)
    arc = np.array(arc)
    outer2 = [(q @ uB, q @ vB) for q in arc]
    inner2 = [(u * 0.98 + 0.0, v * 0.86) for u, v in outer2[::-1]]
    shell2 = np.array(outer2 + inner2)
    side2 = np.array(outer2 + [(0.0, 0.0)])

    def place2(poly2: np.ndarray, thick: float, y0: float) -> K.Solid:
        ex = K.extrude(P.ensure_ccw(poly2), thick)                    # (u, v) trong mặt XY, đùn theo Z
        M3 = np.column_stack([uB, vB, [0, 1.0, 0]])
        mat = np.hstack([M3, (S + np.array([0, y0, 0]))[:, None]])
        return ex.transform(mat)
    shell = place2(shell2, wB, y_b - wB / 2)
    sides = place2(side2, 30.0 * k, y_b - wB / 2) + place2(side2, 30.0 * k, y_b + wB / 2 - 30.0 * k)
    lip = S + Rb * uB
    teeth = K.Solid.union_all([MC.orient(K.cylinder(45.0 * k, 200.0 * k, 5.0 * k, segments=12), lip - 60.0 * k * uB + np.array([0, y_b + yy, 0]), uB)
                               for yy in np.linspace(-0.4 * wB, 0.4 * wB, 5)])
    hlink = beam(S + 0.12 * Rb * uB - 0.05 * Rb * vB, link_p, 160.0 * k, 160.0 * k, 0.9 * stick_w, y_b - 0.45 * stick_w)
    dog = beam(link_p, S - 0.22 * Ls * dS, 140.0 * k, 140.0 * k, 0.9 * stick_w + 60.0 * k, y_b - 0.45 * stick_w - 30.0 * k)
    pin_l = MC.pin(link_p, (0, 1, 0), 80.0 * k, stick_w + 160.0 * k)
    b.add("bucket", "Gầu + thanh nối", "Bucket & linkage", "bucket",
          [Shape(rot(shell + sides), "paint_secondary", 40.0), Shape(rot(teeth), "steel", 40.0), Shape(rot(hlink + dog), "paint_primary", 40.0),
           Shape(rot(pin_l), "steel", 40.0)], parent_id="stick", required=True,
          aliases=["gầu", "gầu xúc", "răng gầu", "thanh nối gầu", "bucket"], function=f"Gầu rộng {wB:.0f} mm, 5 răng thay được, thanh nối chữ H.",
          position_tag="front", joint_axis=(0, 1, 0), explode_dir=(1, 0, -0.3), explode_distance=600.0 * k, explode_order=1)
    # xi lanh
    rams = []
    for sy in (1, -1):
        r_ = MC.hyd_ram(base_bc + np.array([0, sy * y_bc, 0]), pin_bc + np.array([0, sy * y_bc, 0]), 150.0 * k, 105.0 * k)
        rams.append((f"boom_cylinder_{'left' if sy > 0 else 'right'}", "Xi lanh nâng cần " + ("trái" if sy > 0 else "phải"), r_, "upper_structure",
                     ["upper_structure", "boom"], base_bc + np.array([0, sy * y_bc, 0]), pin_bc + np.array([0, sy * y_bc, 0])))
    r_ = MC.hyd_ram(pin_sc, heel, 160.0 * k, 110.0 * k)
    rams.append(("stick_cylinder", "Xi lanh tay gầu", r_, "boom", ["boom", "stick"], pin_sc, heel))
    r_ = MC.hyd_ram(pin_bk0, link_p, 130.0 * k, 90.0 * k)
    rams.append(("bucket_cylinder", "Xi lanh gầu", r_, "stick", ["stick", "bucket"], pin_bk0, link_p))
    links, ram_info = [], {}
    for rid, name, r_, par, joined, pa, pb in rams:
        ram_info[rid] = [r_["closed"], r_["stroke"]]
        b.add(rid, name, "Hydraulic cylinder", "hydraulic_cylinder",
              [Shape(rot(r_["barrel"]), "paint_secondary", 40.0), Shape(rot(r_["rod"]), "chrome", 40.0)], parent_id=par, required=True,
              aliases=["xi lanh", "xi lanh thủy lực", "ben", "ty ben", "piston", "hydraulic cylinder"],
              function=f"Xi lanh thủy lực chốt–chốt {r_['length']:.0f} mm (đóng {r_['closed']:.0f}, hành trình {r_['stroke']:.0f} mm).",
              position_tag="front", joint_axis=(0, 1, 0), explode_dir=(0, 0, 1), explode_distance=500.0 * k, explode_order=1)
        other = [j for j in joined if j != par][0]
        contacts.append([rid, other])
        links.append([f"{rid}@{joined[0]}", pa, [rid, joined[0]]])
        links.append([f"{rid}@{joined[1]}", pb, [rid, joined[1]]])
    b.note_stage(1, "Tháo xi lanh, gầu, dải xích")
    b.note_stage(2, "Tháo tay gầu, cabin")
    b.note_stage(3, "Tháo cần")
    b.note_stage(4, "Nhấc thân trên khỏi ổ quay")
    shift = b.place_on_ground(center_xy=True)
    sh = np.asarray(shift, float)
    pin_links = [[nm, (rp(pt) + sh).tolist(), ids] for nm, pt, ids in links]
    b.metadata.update({"size_class": size, "operating_weight_t": Sz["t"], "track_gauge_mm": G, "shoe_width_mm": shoe,
                       "boom_length_mm": Lb, "stick_length_mm": Ls, "tail_swing_radius_mm": tail, "boom_angle_deg": alpha,
                       "swing_deg": swing, "pose": pose, "pin_links": pin_links, "rams": ram_info, "swing_center": sh.tolist(),
                       "standard": "Tỷ lệ máy đào thủy lực bánh xích 20 t (CAT 320 / PC200); ISO 6165 thuật ngữ máy đào",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
