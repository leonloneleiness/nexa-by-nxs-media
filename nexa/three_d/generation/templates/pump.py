"""Máy bơm ly tâm trục ngang một tầng, hút đầu – đẩy đỉnh (EN 733 / DIN 24255), ví dụ 65-50-160: DN hút 65, DN đẩy 50,
cánh bơm danh nghĩa Ø160 (Ø tối đa ≈ 1,05 × danh nghĩa).

- Vỏ xoắn ốc (volute) loft theo đường xoắn quanh trục, buồng cánh rỗng bao cánh bơm (khe 5 mm), họng hút dọc trục có
  mặt bích EN 1092-1 PN16 (D, K, số lỗ theo DN), họng đẩy thẳng đứng trên đường tâm; nắp vỏ + bu-lông, chân bơm.
- Cánh bơm kín: đĩa sau + đĩa trước côn + 6 lá cong ngược, miệng hút; trục + phớt cơ khí; giá đỡ ổ (lồng có cửa sổ) + chân.
- Khớp nối vấu + chụp che; động cơ điện IEC 60072 (cỡ khung H theo kW, thân có cánh tản nhiệt, hộp đấu dây, chụp quạt);
  đế thép chung, tâm trục bơm và trục động cơ trùng nhau (căn bằng đệm).
Kích thước EN 733: a (mặt bích hút → tâm họng đẩy), f (tâm họng đẩy → đầu trục), h1 (tâm trục → đáy chân bơm),
h2 (tâm trục → mặt bích đẩy).
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

EN733 = {"50-32-160": dict(a=80.0, f=360.0, h1=132.0, h2=160.0), "65-50-160": dict(a=80.0, f=360.0, h1=160.0, h2=180.0),
         "80-65-160": dict(a=100.0, f=360.0, h1=160.0, h2=200.0), "100-80-200": dict(a=100.0, f=470.0, h1=180.0, h2=225.0),
         "125-100-250": dict(a=125.0, f=470.0, h1=225.0, h2=280.0)}
IEC_FRAME = [(0.75, 80.0), (1.5, 90.0), (2.2, 100.0), (4.0, 112.0), (7.5, 132.0), (18.5, 160.0), (22.0, 180.0), (37.0, 200.0),
             (45.0, 225.0), (55.0, 250.0), (90.0, 280.0)]


def flange(dn: int, face_x: float, axis: str, sign: float = 1.0) -> K.Solid:
    """Mặt bích PN16 liền vỏ: đĩa D × C2 có n lỗ L trên vòng K, gờ nổi d1 × 2 mm; mặt tựa tại `face_x` trên trục, hướng `sign`."""
    D, Kc, Lh, n, _M, C2 = S.FLANGE_PN16[dn]
    d1 = S.FLANGE_RF[dn]
    disc = K.cylinder(D / 2, C2, segments=64).translate(0, 0, -C2 - 2.0) + K.cylinder(d1 / 2, 2.0, segments=64).translate(0, 0, -2.0)
    holes = [K.cylinder(Lh / 2, 3 * C2, segments=20).translate(Kc / 2 * math.cos(a), Kc / 2 * math.sin(a), -2 * C2)
             for a in np.radians(np.arange(n) * 360.0 / n + 180.0 / n)]
    disc = disc.subtract_all(holes) - K.cylinder(S.PIPE_OD[dn] / 2 - S.PIPE_WALL[dn], 10 * C2, segments=48).translate(0, 0, -5 * C2)
    # hiện dựng hướng +Z, mặt tựa z = 0 → đặt theo trục
    if axis == "x":
        return disc.rotate(0, 90 if sign > 0 else -90, 0).translate(face_x, 0, 0)
    return disc if sign > 0 else disc.mirror((0, 0, 1))


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    size = p.get("size", "65-50-160")
    kw = float(p.get("motor_kw", 7.5))
    dn_s, dn_d, d_nom = (int(v) for v in size.split("-"))
    E = EN733[size]
    D2 = 1.05 * d_nom                                                  # Ø cánh bơm lớn nhất
    Hm = next(h for k_, h in IEC_FRAME if kw <= k_ + 1e-9) if kw <= IEC_FRAME[-1][0] else IEC_FRAME[-1][1]
    mats = MC.tech_materials(spec, primary="#1d4e89", secondary="#2b2d42", accent="#e63946")
    b = AssemblyBuilder(spec.name or f"Máy bơm ly tâm {size} – {kw:g} kW", "centrifugal_pump", mats)
    contacts: list[list[str]] = []
    # ---------- hệ trục: trục bơm dọc X, họng hút hướng +X; tâm trục tại z = z_ax ----------
    h_pad_p = max(0.0, Hm - E["h1"])
    h_pad_m = max(0.0, E["h1"] - Hm)
    z_b = 120.0                                                        # mặt đế thép
    z_ax = z_b + E["h1"] + h_pad_p
    x_v = 0.0                                                          # mặt phẳng giữa buồng xoắn (tâm họng đẩy)
    wall = 0.06 * D2 + 6.0
    # ---------- vỏ xoắn ----------
    r3 = 0.5 * D2 + 8.0
    rho_min, rho_max = 0.05 * D2, 0.55 * (S.PIPE_OD[dn_d] - 2 * S.PIPE_WALL[dn_d]) + wall
    # đáy buồng xoắn (φ = 270°) phải nằm trên đáy chân bơm (h1) ≥ 12 mm → giới hạn độ nở tiết diện
    f270 = (270.0 - 110.0) / (450.0 - 110.0)
    rho270 = rho_min + (rho_max - rho_min) * f270 + wall * (1 - f270) * 0.5
    grow = min(1.0, max(0.2, (E["h1"] - 12.0 - r3 - 2 * (rho_min + wall * (1 - f270) * 0.5)) / (2 * (rho270 - rho_min - wall * (1 - f270) * 0.5))))
    secs = []
    phis = np.linspace(math.radians(110.0), math.radians(450.0), 34)
    for ph in phis:
        f = (ph - phis[0]) / (phis[-1] - phis[0])
        rho = rho_min + (rho_max - rho_min) * f * (grow if ph < math.radians(360.0) else grow + (1 - grow) * (ph - math.radians(360.0)) / math.radians(90.0))             + wall * (1 - f) * 0.5
        R = r3 + rho
        er = np.array([0.0, math.cos(ph), math.sin(ph)])
        c = np.array([x_v, 0.0, 0.0]) + R * er
        al = np.linspace(0, 2 * math.pi, 32, endpoint=False)
        secs.append(np.array([c + rho * (math.cos(a) * er + math.sin(a) * np.array([1.0, 0, 0])) for a in al]))
    volute = K.loft(secs)
    core = K.cylinder(r3 + wall, 0.16 * D2 + 2 * wall, segments=64).rotate(0, 90, 0).translate(x_v - 0.08 * D2 - wall, 0, 0)
    top_c = r3 + rho_max
    neck = K.cylinder(rho_max, E["h2"] - top_c - 2.0 - S.FLANGE_PN16[dn_d][5], segments=48).translate(x_v, 0, top_c)
    nozzle_d = K.cylinder(S.PIPE_OD[dn_d] / 2 + 6.0, E["h2"] - S.FLANGE_PN16[dn_d][5] - 2.0 - 0.6 * top_c, segments=48).translate(x_v, 0, 0.6 * top_c) + neck
    x_sf = x_v + E["a"]                                                # mặt bích hút
    nozzle_s = K.cylinder(S.PIPE_OD[dn_s] / 2 + 6.0, x_sf - S.FLANGE_PN16[dn_s][5] - 2.0 - x_v, segments=48).rotate(0, 90, 0).translate(x_v, 0, 0)
    casing = volute + core + nozzle_d + nozzle_s
    b2 = 0.06 * D2                                                     # bề rộng lối ra cánh bơm
    cav0, cav1 = x_v - b2 / 2 - 5.0 - 5.0, x_v + b2 / 2 + 16.0 + 5.0      # buồng cánh: phủ cánh (đĩa sau → miệng hút) + khe 5 mm
    cavity = K.cylinder(D2 / 2 + 5.0, cav1 - cav0, segments=64).rotate(0, 90, 0).translate(cav0, 0, 0)
    bore_s = K.cylinder(S.PIPE_OD[dn_s] / 2 - S.PIPE_WALL[dn_s], E["a"] + 10.0, segments=48).rotate(0, 90, 0).translate(x_v, 0, 0)
    bore_d = K.cylinder(S.PIPE_OD[dn_d] / 2 - S.PIPE_WALL[dn_d], E["h2"], segments=48).translate(x_v, 0, top_c - rho_max * 0.5)
    casing = casing - cavity - bore_s - bore_d
    fl_s = flange(dn_s, x_sf, "x", +1)
    fl_d = flange(dn_d, 0.0, "z", +1).translate(x_v, 0, E["h2"])
    foot = K.box(0.35 * D2, 1.3 * D2, 16.0).translate(x_v - 0.05 * D2, 0, -E["h1"] + 8.0) + \
        K.hull([K.box(0.25 * D2, 0.25 * D2, 1.0).translate(x_v - 0.05 * D2, 0, -E["h1"] + 16.0), K.box(0.25 * D2, 0.25 * D2, 1.0).translate(x_v - 0.05 * D2, 0, -r3 - wall * 0.3)])
    drain = K.cylinder(8.0, 20.0, segments=6).rotate(90, 0, 0).translate(x_v, -(r3 + 10.0), -0.5 * r3)
    casing_all = (casing + fl_s + fl_d + foot + drain).translate(0, 0, z_ax)
    b.add("casing", f"Vỏ bơm xoắn ốc (hút DN{dn_s} / đẩy DN{dn_d})", "Volute casing", "pump_casing",
          [Shape(casing_all, "cast_iron", 35.0)], parent_id="baseplate", required=True,
          aliases=["vỏ bơm", "buồng xoắn", "volute", "họng hút", "họng đẩy", "mặt bích bơm", "chân bơm"],
          function=f"Vỏ gang xoắn ốc, họng hút dọc trục DN{dn_s} và họng đẩy đứng DN{dn_d}, mặt bích EN 1092-1 PN16.",
          position_tag="front", dimensions={"a": E["a"], "h1": E["h1"], "h2": E["h2"]})
    # ---------- cánh bơm ----------
    r1 = 0.28 * D2
    back = K.cylinder(D2 / 2, 5.0, segments=64).rotate(0, 90, 0).translate(x_v - b2 / 2 - 5.0, 0, 0)
    front = K.revolve([(r1, 0.0), (D2 / 2, 0.0), (D2 / 2, 4.0), (r1 + 4.0, 16.0), (r1, 16.0)], segments=64)
    front = front.rotate(0, 90, 0).translate(x_v + b2 / 2, 0, 0)
    vanes = []
    for i in range(6):
        pts = []
        for t in np.linspace(0, 1, 10):
            r = r1 * (1 - t) + (D2 / 2 - 2.0) * t
            th = math.radians(60.0 * i) + 1.1 * t
            pts.append((r * math.cos(th), r * math.sin(th)))
        pts = np.array(pts)
        path = np.column_stack([np.full(len(pts), x_v), pts[:, 0], pts[:, 1]])
        vanes.append(K.sweep(P.rounded_rect(b2 + 2.0, 4.0, 1.0, 2), path))
    hub = K.cylinder(0.16 * D2, b2 + 18.0, segments=32).rotate(0, 90, 0).translate(x_v - b2 / 2 - 5.0, 0, 0)
    imp = (back + front + K.Solid.union_all(vanes) + hub) & K.cylinder(D2 / 2, 3 * D2, segments=64).rotate(0, 90, 0).translate(x_v - D2, 0, 0)
    b.add("impeller", f"Cánh bơm kín Ø{D2:.0f} (6 lá)", "Closed impeller", "impeller", Shape(imp.translate(0, 0, z_ax), "bronze", 35.0),
          parent_id="shaft", required=True, aliases=["cánh bơm", "bánh công tác", "impeller", "guồng bơm"],
          function=f"Cánh bơm kín đồng thau Ø{D2:.0f} mm, 6 lá cong ngược, miệng hút Ø{2 * r1:.0f}.", position_tag="front",
          joint_axis=(1, 0, 0), explode_dir=(1, 0, 0), explode_distance=2.5 * D2, explode_order=1, dimensions={"diameter": D2})
    # ---------- nắp vỏ + giá đỡ ổ + trục ----------
    x_cov = x_v - 0.08 * D2 - wall
    cover = K.cylinder(r3 + wall + 10.0, 18.0, segments=64).rotate(0, 90, 0).translate(x_cov - 18.0, 0, 0)
    bolts_c = K.Solid.union_all([MC.orient(MC.hex_bolt(12.0, 30.0), [x_cov - 18.0, (r3 + wall) * math.cos(a), (r3 + wall) * math.sin(a)], (-1, 0, 0))
                                 for a in np.radians(np.arange(0, 360, 45.0))])
    x_end = x_v - E["f"]                                               # đầu trục bơm
    L_br = (x_cov - 18.0) - (x_end + 0.28 * E["f"])
    brk = K.cylinder(0.3 * D2, L_br, segments=48).rotate(0, 90, 0).translate(x_end + 0.28 * E["f"], 0, 0)
    brk = brk - K.cylinder(0.3 * D2 - 8.0, L_br + 2, segments=48).rotate(0, 90, 0).translate(x_end + 0.28 * E["f"] - 1, 0, 0)
    windows = K.Solid.union_all([K.box(0.5 * L_br, 0.3 * D2, 0.3 * D2).translate(x_end + 0.28 * E["f"] + 0.5 * L_br, 0, s * 0.3 * D2) for s in (1, -1)])
    brk = brk - windows
    housing = K.cylinder(0.24 * D2, 0.3 * E["f"], segments=48).rotate(0, 90, 0).translate(x_end + 0.05 * E["f"], 0, 0)
    sup = K.box(0.2 * E["f"], 0.5 * D2, E["h1"] - 0.24 * D2 + 5.0).translate(x_end + 0.18 * E["f"], 0, -E["h1"] + (E["h1"] - 0.24 * D2 + 5.0) / 2)   # tì lên đệm căn
    b.add("bearing_bracket", "Nắp vỏ + giá đỡ ổ + chân", "Cover & bearing bracket", "housing",
          [Shape((cover + brk + housing + sup).translate(0, 0, z_ax), "cast_iron", 35.0), Shape(bolts_c.translate(0, 0, z_ax), "steel_dark", 35.0)],
          parent_id="casing", required=True, aliases=["nắp bơm", "giá đỡ ổ", "ổ bi bơm", "bearing bracket", "cụm ổ trục"],
          function="Nắp vỏ bắt 8 bu-lông, giá đỡ ổ lồng có cửa sổ, cụm 2 ổ bi bôi trơn mỡ, chân đỡ.", position_tag="rear",
          explode_dir=(-1, 0, 0), explode_distance=0.8 * E["f"], explode_order=2)
    r_s = 0.06 * D2 + 6.0
    shaft = K.cylinder(r_s, x_v + b2 / 2 + 10.0 - x_end, segments=32).rotate(0, 90, 0).translate(x_end, 0, 0)
    seal = K.cylinder(r_s + 14.0, 30.0, segments=32).rotate(0, 90, 0).translate(x_cov - 18.0 - 30.0, 0, 0)
    b.add("shaft", "Trục bơm + phớt cơ khí", "Pump shaft & mechanical seal", "shaft",
          [Shape(shaft.translate(0, 0, z_ax), "stainless", 35.0), Shape(seal.translate(0, 0, z_ax), "chrome", 35.0)], parent_id="bearing_bracket",
          required=True, aliases=["trục bơm", "phớt cơ khí", "phớt", "shaft", "mechanical seal"], function="Trục inox, phớt cơ khí làm kín tại nắp vỏ.",
          position_tag="center", joint_axis=(1, 0, 0), explode_dir=(-1, 0, 0), explode_distance=1.4 * E["f"], explode_order=1)
    contacts += [["shaft", "casing"], ["shaft", "coupling"]]
    # ---------- khớp nối + động cơ ----------
    gap_c = 4.0
    L_hub = 0.12 * E["f"] + 20.0
    R_c = 0.18 * D2 + 20.0
    x_c0 = x_end - 0.02 * E["f"]
    hub_p = K.cylinder(R_c, L_hub, segments=40).rotate(0, 90, 0).translate(x_c0 - L_hub + 0.02 * E["f"] + 5.0, 0, 0)
    spider = K.cylinder(R_c * 0.9, gap_c + 12.0, segments=40).rotate(0, 90, 0).translate(x_c0 - L_hub - gap_c - 12.0 + 0.02 * E["f"] + 5.0, 0, 0)
    x_m_end = x_c0 - L_hub - gap_c - 12.0 + 0.02 * E["f"] + 5.0
    hub_m = K.cylinder(R_c, L_hub, segments=40).rotate(0, 90, 0).translate(x_m_end - L_hub, 0, 0)
    guard_L = (x_end + 10.0) - (x_m_end - L_hub - 20.0)                  # chụp che dừng trước cụm ổ
    guard = (K.cylinder(R_c + 45.0, guard_L, segments=40) - K.cylinder(R_c + 40.0, guard_L + 2, segments=40).translate(0, 0, -1)).rotate(0, 90, 0)
    guard = (guard & K.box(guard_L * 3, 3 * R_c, 3 * R_c).translate(0, 0, 1.5 * R_c - 0.0)).translate(x_m_end - L_hub - 20.0, 0, 0)
    guard_leg = K.Solid.union_all([K.box(20.0, 2 * R_c + 90.0, 5.0).translate(x_m_end - L_hub - 20.0 + dx, 0, -(z_ax - z_b) + 2.5)
                                   for dx in (10.0, guard_L - 10.0)] +
                                  [K.box(20.0, 5.0, z_ax - z_b).translate(x_m_end - L_hub - 20.0 + dx, s * (R_c + 42.5), -(z_ax - z_b) / 2)
                                   for dx in (10.0, guard_L - 10.0) for s in (1, -1)])
    b.add("coupling", "Khớp nối vấu", "Jaw coupling", "coupling_hub",
          [Shape((hub_p + hub_m).translate(0, 0, z_ax), "steel", 35.0), Shape(spider.translate(0, 0, z_ax), "polyurethane", 35.0)],
          parent_id="shaft", required=True, joint_axis=(1, 0, 0),
          aliases=["khớp nối", "khớp nối trục", "coupling"], function="Khớp nối vấu đệm sao PU truyền mô-men từ động cơ sang trục bơm.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=2.0 * R_c, explode_order=1)
    # chụp che đứng yên trên đế, tách khỏi khớp nối để không quay theo
    b.add("coupling_guard", "Chụp che khớp nối", "Coupling guard", "guard",
          Shape((guard + guard_leg).translate(0, 0, z_ax), "paint_accent", 35.0), parent_id="baseplate",
          aliases=["chụp khớp nối", "che khớp nối", "coupling guard"], function="Chụp che an toàn quanh khớp nối đang quay.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=3.0 * R_c, explode_order=1)
    contacts += [["coupling", "motor"], ["coupling_guard", "baseplate"], ["coupling_guard", "motor"]]
    # động cơ IEC: thân Ø ≈ 1,9 H, dài ≈ 3,4 H
    Lm = 3.4 * Hm
    Rm = 0.76 * Hm                                                     # thân + cánh tản nhiệt < H (không chạm mặt đế)
    x_m1 = x_m_end - L_hub                                            # mặt bích trục động cơ (đầu trục)
    shaft_m = K.cylinder(0.12 * Hm, 0.5 * Hm, segments=24).rotate(0, 90, 0).translate(x_m1 - 0.5 * Hm + L_hub * 0.9, 0, 0)
    body = K.cylinder(Rm, Lm, segments=48).rotate(0, 90, 0).translate(x_m1 - 0.35 * Hm - Lm, 0, 0)
    fins = K.Solid.union_all([K.box(Lm * 0.85, 8.0, 0.14 * Hm).translate(x_m1 - 0.35 * Hm - Lm / 2, 0, Rm + 0.06 * Hm).rotate_axis((1, 0, 0), a)
                              for a in np.arange(0, 360, 15.0) if not 250 < a < 290])
    endc = K.cylinder(Rm * 0.92, 0.35 * Hm, segments=48).rotate(0, 90, 0).translate(x_m1 - 0.35 * Hm, 0, 0)
    fanc = K.cylinder(Rm * 1.02, 0.45 * Hm, segments=48).rotate(0, 90, 0).translate(x_m1 - 0.35 * Hm - Lm - 0.45 * Hm, 0, 0)
    feet = K.Solid.union_all([K.box(0.3 * Hm, 1.6 * Hm, Hm - Rm * 0.6).translate(x_m1 - 0.35 * Hm - dx, 0, -Hm + (Hm - Rm * 0.6) / 2)
                              for dx in (0.2 * Lm, 0.8 * Lm)])
    tbox = K.rounded_box(0.8 * Hm, 0.8 * Hm, 0.5 * Hm, 0.05 * Hm, segments=6).translate(x_m1 - 0.35 * Hm - 0.4 * Lm, 0, Rm + 0.2 * Hm)
    motor = (body + fins + endc + fanc + feet + tbox).translate(0, 0, z_ax)
    pad_m = K.box(Lm, 1.8 * Hm, h_pad_m).translate(x_m1 - 0.35 * Hm - Lm / 2, 0, z_b + h_pad_m / 2) if h_pad_m > 0.5 else None
    b.add("motor", f"Động cơ điện {kw:g} kW – khung IEC {Hm:g}", "Electric motor", "motor",
          [Shape(motor, "paint_primary", 35.0), Shape(shaft_m.translate(0, 0, z_ax), "steel", 35.0)] + ([Shape(pad_m, "steel_dark", 35.0)] if pad_m else []),
          parent_id="baseplate", required=True, aliases=["động cơ", "mô tơ", "motor", "động cơ điện", "hộp đấu dây"],
          function=f"Động cơ không đồng bộ 3 pha {kw:g} kW, 2 cực, khung IEC 60072 cỡ {Hm:g} (tâm trục cao {Hm:g} mm), IP55.",
          position_tag="rear", joint_axis=(1, 0, 0), explode_dir=(-1, 0, 0), explode_distance=1.2 * Lm, explode_order=2, dimensions={"frame_H": Hm})
    # ---------- đế ----------
    x0b, x1b = x_m1 - 0.35 * Hm - Lm - 0.45 * Hm - 60.0, x_sf + 40.0
    wb = max(1.8 * Hm, 1.3 * D2) + 80.0
    rails = K.Solid.union_all([K.box(x1b - x0b, 60.0, z_b).translate((x0b + x1b) / 2, s * (wb / 2 - 30.0), z_b / 2) for s in (1, -1)]
                              + [K.box(60.0, wb, z_b).translate(x, 0, z_b / 2) for x in (x0b + 30.0, x1b - 30.0)]
                              + [K.box(x1b - x0b, wb, 12.0).translate((x0b + x1b) / 2, 0, z_b - 6.0)])
    pad_p = K.box(0.4 * D2, 1.35 * D2, h_pad_p).translate(x_v - 0.05 * D2, 0, z_b + h_pad_p / 2) if h_pad_p > 0.5 else None
    pad_b = K.box(0.2 * E["f"] + 20.0, 0.5 * D2 + 20.0, h_pad_p).translate(x_end + 0.18 * E["f"], 0, z_b + h_pad_p / 2) if h_pad_p > 0.5 else None
    b.add("baseplate", "Đế thép chung + đệm căn", "Common baseplate", "base",
          [Shape(rails, "paint_secondary", 35.0)] + ([Shape(pad_p + pad_b, "steel_dark", 35.0)] if pad_p is not None else []), required=True,
          aliases=["đế bơm", "bệ bơm", "khung đế", "baseplate", "đế thép"], function="Đế thép hình hàn, đệm căn đồng tâm trục bơm – động cơ.",
          position_tag="bottom")
    b.note_stage(1, "Tháo khớp nối, trục + cánh bơm")
    b.note_stage(2, "Tháo nắp vỏ + giá đỡ ổ, động cơ")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"size": size, "dn_suction": dn_s, "dn_discharge": dn_d, "impeller_d_mm": D2, "motor_kw": kw, "iec_frame": Hm,
                       "en733": E, "shaft_axis_z_mm": z_ax,
                       "standard": "EN 733 / DIN 24255 (bơm hút đầu PN10), mặt bích EN 1092-1 PN16, động cơ IEC 60072",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
