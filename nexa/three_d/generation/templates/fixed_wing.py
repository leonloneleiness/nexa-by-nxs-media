"""Máy bay cánh bằng: máy bay hạng nhẹ 4 chỗ cánh thấp (tỷ lệ kiểu Piper PA-28 / Diamond DA40), UAV cánh cố định
cánh trên, UAV VTOL (quadplane: 4 rotor nâng trên 2 dầm dưới cánh + cánh quạt kéo ở mũi).

- Thân: loft các mặt cắt siêu elip dọc trục X (mũi +X), đuôi vuốt lên; buồng lái khoét + kính bọt (vỏ mỏng trong suốt,
  mặt trong/ngoài tính giải tích — không co giãn) + ghế + bảng đồng hồ.
- Cánh: loft mặt cắt NACA (2412 máy bay nhẹ, 4412 UAV) dọc sải, thuôn λ ≈ 0,6, xoắn giảm góc đầu cánh (washout 3°),
  góc nhị diện (dihedral) quay quanh trục X qua gốc cánh; sải cánh = khoảng cách chiếu hai đầu cánh.
- Cánh lái tách riêng: aileron hai bên (40 % sải ngoài, 27 % dây cung), elevator, rudder (35 % dây cung) — khe bản lề
  1 % dây cung, cánh lái gá bằng chốt bản lề ăn vào bộ phận cha.
- Đuôi: thường (conventional), chữ T hoặc chữ V (ruddervator); NACA 0012 / 0010.
- Động cơ + cánh quạt kéo (loft NACA xoắn theo bước), chóp cánh quạt; càng đáp ba điểm (bánh mũi) hoặc càng trượt
  dưới dầm (VTOL). Khoảng hở đầu cánh quạt – mặt đất ≥ 229 mm với máy bay nhẹ (FAR 23.925, càng mũi).
Bánh / chân càng chạm đất ở z = 0.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# tỷ lệ theo sải cánh b (máy bay nhẹ: b = 11 m, dài 7,5 m, dây cung gốc 1,7 m, cánh quạt Ø1,93 m)
TYPES = {
    "light": dict(L=0.68, W=0.105, H=0.125, cr=0.155, lam=0.62, foil="2412", prop=0.175, blades=2, wheel=0.038, high=False),
    "uav": dict(L=0.55, W=0.075, H=0.085, cr=0.12, lam=0.65, foil="4412", prop=0.13, blades=2, wheel=0.03, high=True),
    "vtol": dict(L=0.55, W=0.075, H=0.085, cr=0.12, lam=0.65, foil="4412", prop=0.11, blades=2, wheel=0.03, high=True),
}
TWIST_ROOT, TWIST_TIP = 1.5, -1.5                                   # góc đặt cánh gốc / đầu cánh (độ): washout 3°
AIL_ETA = (0.55, 0.95)                                              # vùng aileron theo sải nửa cánh
HINGE = 0.27                                                        # tỷ lệ dây cung cánh lái (aileron)
TAIL_HINGE = 0.35


def airfoil_section(code: str, chord: float, x_qc: float, y: float, z: float, twist_deg: float, samples: int = 40,
                    plane: str = "xz") -> np.ndarray:
    """Mặt cắt NACA đặt trong không gian: mép trước phía +X, trục xoắn ở 1/4 dây cung.
    plane "xz": cánh ngang (độ dày theo Z, đặt ở tung độ y); "xy": cánh đứng (độ dày theo Y, đặt ở cao độ z)."""
    af = P.naca4(code, chord, samples)
    dx = -(af[:, 0] - 0.25 * chord)                                   # về phía trước dương
    dz = af[:, 1]
    t = math.radians(twist_deg)
    dx, dz = dx * math.cos(t) - dz * math.sin(t), dz * math.cos(t) + dx * math.sin(t)
    if plane == "xz":
        return np.column_stack([x_qc + dx, np.full(len(dx), y), z + dz])
    return np.column_stack([x_qc + dx, y + dz, np.full(len(dx), z)])


def surface(code: str, span: float, c_root: float, lam: float, sweep_qc: float = 0.0, twist=(0.0, 0.0), n: int = 10,
            plane: str = "xz", tip_cap: bool = True) -> tuple[K.Solid, callable]:
    """Bề mặt nâng một nửa (gốc tại gốc tọa độ, sải theo +Y với "xz" hoặc +Z với "xy"). Trả (khối, hàm (η) →
    (x 1/4 dây cung, dây cung))."""
    def geo(eta: float) -> tuple[float, float]:
        c = c_root * (1 - (1 - lam) * eta)
        return -eta * span * math.tan(math.radians(sweep_qc)), c
    secs = []
    for eta in np.linspace(0.0, 1.0, n):
        xq, c = geo(eta)
        tw = twist[0] + (twist[1] - twist[0]) * eta
        secs.append(airfoil_section(code, c, xq, eta * span, 0.0, tw, plane=plane) if plane == "xz"
                    else airfoil_section(code, c, xq, 0.0, eta * span, tw, plane=plane))
    if tip_cap:                                                      # đầu cánh bo: mặt cắt thu nhỏ (dài 80 %, dày 35 %) thêm 1,5 % sải
        last = secs[-1]
        cen = last.mean(axis=0)
        span_ax, thick_ax = (1, 2) if plane == "xz" else (2, 1)
        cap = last.copy()
        cap[:, 0] = cen[0] + (last[:, 0] - cen[0]) * 0.8
        cap[:, thick_ax] = cen[thick_ax] + (last[:, thick_ax] - cen[thick_ax]) * 0.35
        cap[:, span_ax] = last[:, span_ax] + 0.015 * span
        secs.append(cap)
    return K.loft(secs), geo


def hinge_cutter(geo, span: float, eta0: float, eta1: float, frac: float, gap: float, plane: str = "xz",
                 inset: float = 0.0) -> K.Solid:
    """Khối cắt phần cánh lái (phía sau đường bản lề thẳng) trên đoạn sải [η0, η1]; gap > 0: lùi đường bản lề ra sau."""
    pts = []
    for eta in (eta0, eta1):
        xq, c = geo(eta)
        x_h = xq + 0.25 * c - frac * c - gap
        s = eta * span + (inset if eta == eta0 else -inset)
        big = c * 2
        for xx in (x_h, x_h - big):
            for w in (-big, big):
                pts.append((xx, s, w) if plane == "xz" else (xx, w, s))
    return K.hull_points(np.array(pts))


def rot_x(solid: K.Solid, deg: float) -> K.Solid:
    return solid.rotate(deg, 0, 0)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    typ = p.get("aircraft_type", "light")
    T = TYPES[typ]
    b_span = float(p["wingspan_mm"])
    dih = float(p.get("dihedral_deg", 3.0))
    tail = p.get("tail", "conventional")
    Lf, Wf, Hf = T["L"] * b_span, T["W"] * b_span, T["H"] * b_span
    mats = MC.tech_materials(spec, primary="#f1f3f5", secondary="#1d3557", accent="#e63946")
    names = {"light": "Máy bay hạng nhẹ 4 chỗ", "uav": "UAV cánh cố định", "vtol": "UAV VTOL cánh cố định"}
    b = AssemblyBuilder(spec.name or names[typ], "fixed_wing", mats)
    rw = T["wheel"] * b_span / 2
    R_prop = T["prop"] * b_span / 2
    x_nose = Lf / 2
    t_fw = 0.14 if typ == "light" else 0.1                           # vách lửa: ranh giới nắp động cơ / thân

    # ---------- mặt cắt thân ----------
    def fus(t: float) -> tuple[float, float, float]:
        """(rộng, cao, đáy) của thân tại t ∈ [0, 1] (0 = mũi, 1 = đuôi); đáy tương đối so với đáy thân zb0."""
        if t < 0.3:
            k = math.sin(math.pi / 2 * t / 0.3)
            w, h = Wf * (0.5 + 0.5 * k), Hf * (0.55 + 0.45 * k)
            zb = (Hf - h) * 0.35
        elif t < 0.5:
            w, h, zb = Wf, Hf, 0.0
        else:
            u = (t - 0.5) / 0.5
            w, h = Wf * (1 - 0.82 * u ** 1.1), Hf * (1 - 0.8 * u)
            zb = (Hf - h) * 0.8
        return w, h, zb

    # cao độ đáy thân: đủ cho bánh + khoảng hở đầu cánh quạt (≥ 229 mm máy bay nhẹ, ≥ 2 % sải UAV)
    w0, h0, zb_0 = fus(0.0)
    clear = 229.0 if typ == "light" else 0.02 * b_span
    zb0 = max(2 * rw + 0.2 * Hf, 1.02 * R_prop + 1.05 * clear - (zb_0 + h0 / 2))     # đầu lá bo vượt R ~1 %
    if typ == "vtol":
        zb0 = max(zb0, 0.045 * b_span)                                # càng trượt dưới dầm: thân cách đất ≥ 4,5 % sải
    x_of = lambda t: x_nose - t * Lf                                  # noqa: E731
    z_top = lambda t: zb0 + fus(t)[2] + fus(t)[1]                     # noqa: E731
    z_mid = lambda t: zb0 + fus(t)[2] + fus(t)[1] / 2                 # noqa: E731
    RING = 56

    def fus_loft(t0: float, t1: float, n: int, grow: float = 0.0) -> K.Solid:
        secs = []
        for t in np.linspace(t0, t1, n):
            w, h, zb = fus(t)
            pr = P.superellipse(w + 2 * grow, h + 2 * grow, 2.4, RING)
            secs.append(np.column_stack([np.full(RING, x_of(t)), pr[:, 0], zb0 + zb + h / 2 + pr[:, 1]]))
        return K.loft(secs)

    body_full = fus_loft(t_fw, 1.0, 26)
    fus_shapes = []
    # buồng lái / khoang thiết bị (UAV cánh trên: khoang đặt trước gốc cánh)
    t_c0, t_c1 = (0.2, 0.52) if typ == "light" else (0.11, 0.25)
    zc_floor = z_top(0.35) - (0.42 if typ == "light" else 0.3) * Hf
    cock = K.box(x_of(t_c0) - x_of(t_c1), Wf * 0.78, Hf).translate((x_of(t_c0) + x_of(t_c1)) / 2, 0, zc_floor + Hf / 2)
    body = body_full - cock
    fus_shapes.append(Shape(body, "paint_primary", 40.0))
    # sọc sơn: lớp mỏng nổi 0,15 % chiều cao thân (không trùng mặt vỏ)
    stripe = (fus_loft(t_fw + 0.01, 0.8, 20, grow=0.0015 * Hf) & K.box(Lf * 2, Wf * 2, 0.06 * Hf).translate(0, 0, zb0 + 0.45 * Hf)) - body_full
    fus_shapes.append(Shape(stripe - cock, "paint_secondary", 40.0))
    if typ == "light":
        seats = []
        for tt in (0.27, 0.41):
            for sy in (1, -1):
                xs = x_of(tt)
                seat = K.rounded_box(0.05 * Lf, 0.3 * Wf, 0.05 * Hf, 0.01 * Lf, segments=8).translate(xs, sy * 0.2 * Wf, zc_floor + 0.025 * Hf)
                back = K.rounded_box(0.012 * Lf, 0.3 * Wf, 0.3 * Hf, 0.005 * Lf, segments=8).rotate(0, -12, 0).translate(
                    xs - 0.03 * Lf, sy * 0.2 * Wf, zc_floor + 0.17 * Hf)
                seats.append(seat + back)
        panel = K.rounded_box(0.02 * Lf, 0.74 * Wf, 0.22 * Hf, 0.005 * Lf, segments=8).translate(x_of(t_c0) - 0.012 * Lf, 0, zc_floor + 0.3 * Hf)
        fus_shapes += [Shape(K.Solid.union_all(seats), "plastic_black", 40.0), Shape(panel, "steel_dark", 40.0)]
    else:
        bay = K.rounded_box((x_of(t_c0) - x_of(t_c1)) * 0.8, 0.5 * Wf, 0.25 * Hf, 0.02 * Hf, segments=8).translate(
            (x_of(t_c0) + x_of(t_c1)) / 2, 0, zc_floor + 0.125 * Hf)
        fus_shapes.append(Shape(bay, "pcb", 40.0))
    b.add("fuselage", "Thân máy bay", "Fuselage", "fuselage", fus_shapes, required=True,
          aliases=["thân", "thân máy bay", "fuselage", "khoang lái", "buồng lái"] + (["ghế"] if typ == "light" else ["khoang thiết bị"]),
          function="Thân vỏ chịu lực (semi-monocoque), buồng lái / khoang thiết bị, gá cánh và đuôi.",
          position_tag="center", dimensions={"length": Lf, "width": Wf, "height": Hf})
    contacts: list[list[str]] = []

    # ---------- kính buồng lái (bọt kính vỏ mỏng, mặt trong/ngoài giải tích) ----------
    def bubble(t0: float, t1: float, inset: float) -> K.Solid:
        secs = []
        for s in np.linspace(0.0, 1.0, 18):
            t = t0 + (t1 - t0) * s
            prof_h = math.sin(math.pi * min(1.0, s / 0.35) / 2) * (1 - max(0.0, (s - 0.45) / 0.55) ** 1.6)
            w = max(fus(t)[0] * 0.84 * (0.35 + 0.65 * prof_h ** 0.5) - 2 * inset, 1.0)
            h = max((0.3 if typ == "light" else 0.18) * Hf * max(prof_h, 0.04) + (z_top(t) - zc_floor) - inset, 1.0)
            half = [(0.5 * w * math.cos(a), h * math.sin(a) ** 0.8) for a in np.linspace(0, math.pi, 25)]
            ring = [(x, z) for x, z in half] + [(-w / 2, -0.02 * Hf - inset * 0.2), (w / 2, -0.02 * Hf - inset * 0.2)]
            ring = np.array(ring)
            secs.append(np.column_stack([np.full(len(ring), x_of(t)), ring[:, 0], zc_floor + ring[:, 1]]))
        return K.loft(secs)
    glass_t = max(3.0, 0.0008 * b_span)
    dt = 2.0 * glass_t / Lf                                          # mặt trong ngắn hơn → hai đầu kính kín, không trùng mặt
    can_out = bubble(t_c0 - 0.005, t_c1 + 0.02, 0.0)
    can_in = bubble(t_c0 - 0.005 + dt, t_c1 + 0.02 - dt, glass_t).translate(0, 0, -glass_t * 0.5)
    canopy = (can_out - can_in) - K.box(Lf * 2, Wf * 2, 0.04 * Hf).translate(0, 0, zc_floor - 0.02 * Hf + 1.0)
    frame = (can_out - can_in) & K.box(0.012 * Lf, Wf * 2, Hf * 2).translate(x_of((t_c0 + t_c1) / 2 + 0.03), 0, zc_floor + Hf)
    b.add("canopy", "Kính buồng lái" if typ == "light" else "Nắp kính khoang thiết bị", "Canopy", "canopy",
          [Shape(canopy - frame, "glass", 40.0), Shape(frame, "paint_secondary", 40.0)], parent_id="fuselage", required=True,
          aliases=["kính", "kính buồng lái", "kính chắn gió", "canopy", "nắp buồng lái"],
          function="Kính acrylic bọt (vỏ mỏng trong suốt), mở lên để vào buồng lái.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.5 * Hf, explode_order=1)

    # ---------- nắp động cơ + cánh quạt ----------
    cowl = fus_loft(0.0, t_fw, 8)
    x_fw = x_of(t_fw)
    zn = z_mid(0.0)
    inlets = K.Solid.union_all([K.cylinder(0.07 * Wf, 0.1 * Lf, segments=24).rotate(0, 90, 0).translate(x_nose - 0.05 * Lf, sy * 0.28 * w0, zn + 0.05 * Hf)
                                for sy in (1, -1)])
    cowl = cowl - inlets
    louvres = K.Solid.union_all([K.box(0.012 * Lf, 0.5 * Wf, 0.02 * Hf).translate(x_fw + 0.02 * Lf + i * 0.018 * Lf, 0, z_top(0.08) - 0.005 * Hf)
                                 for i in range(3)])
    cowl = cowl - louvres
    exh = K.Solid.union_all([K.tube(np.array([[x_fw + 0.03 * Lf, sy * 0.3 * Wf, zb0 + fus(0.1)[2] + 0.1 * Hf],
                                              [x_fw + 0.01 * Lf, sy * 0.3 * Wf, zb0 + fus(0.1)[2] - 0.03 * Hf]]), 0.03 * Wf, 12)
                             for sy in (1, -1)]) if typ == "light" else None
    eshapes = [Shape(cowl, "paint_primary", 40.0)]
    if exh is not None:
        eshapes.append(Shape(exh, "stainless", 40.0))
    b.add("engine", "Nắp động cơ" + (" (động cơ piston 4 xi lanh)" if typ == "light" else " + motor điện"), "Engine cowling", "engine",
          eshapes, parent_id="fuselage", required=True,
          aliases=["động cơ", "nắp động cơ", "engine", "cowling", "mô tơ"] + (["ống xả"] if typ == "light" else ["motor"]),
          function=("Động cơ piston 4 xi lanh nằm ngang (~180 hp) trong nắp; cửa gió làm mát, ống xả." if typ == "light"
                    else "Motor điện không chổi than kéo cánh quạt, nắp mũi có khe tản nhiệt."),
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=0.12 * Lf, explode_order=2)
    rs = 0.22 * w0
    spinner = K.revolve([(0.0, 0.0), (rs, 0.0)] + [(rs * math.cos(a) ** 0.7, 1.4 * rs * math.sin(a)) for a in np.linspace(0.05, math.pi / 2, 10)],
                        segments=48).rotate(0, 90, 0).translate(x_nose, 0, zn)
    prop = C.propeller(2 * R_prop, T["blades"], pitch=1.1 * R_prop * 2 * (0.55 if typ == "light" else 0.5), hub_d=1.6 * rs,
                       material="aluminum" if typ == "light" else "prop_plastic")
    blades = K.Solid.union_all([s_.solid for s_ in prop]).rotate(0, 90, 0).rotate(60, 0, 0).translate(x_nose + 0.5 * rs, 0, zn)
    b.add("propeller", "Cánh quạt + chóp", "Propeller & spinner", "propeller",
          [Shape(blades, "aluminum" if typ == "light" else "prop_plastic", 40.0), Shape(spinner, "paint_accent", 40.0)],
          parent_id="engine", required=True, aliases=["cánh quạt", "chong chóng", "propeller", "chóp cánh quạt", "spinner"],
          function=f"Cánh quạt kéo {T['blades']} lá Ø{2 * R_prop:.0f} mm, lá loft NACA xoắn theo bước.", position_tag="front",
          joint_axis=(1, 0, 0), explode_dir=(1, 0, 0), explode_distance=0.1 * Lf, explode_order=1)

    # ---------- cánh chính ----------
    half = b_span / 2 / math.cos(math.radians(dih)) / 1.015                # + nắp đầu cánh 1,5 % = đúng nửa sải chiếu
    c_r = T["cr"] * b_span
    t_w = 0.4 if typ == "light" else 0.36
    x_wq = x_of(t_w)
    th_r = 0.12 * c_r
    z_w = zb0 + 0.16 * Hf if not T["high"] else z_top(t_w) - 0.35 * th_r
    wing_half, geo = surface(T["foil"], half, c_r, T["lam"], 0.0, (TWIST_ROOT, TWIST_TIP), 12)
    gap = 0.01 * c_r
    cut_full = hinge_cutter(geo, half, AIL_ETA[0], AIL_ETA[1], HINGE, 0.0)
    cut_ail = hinge_cutter(geo, half, AIL_ETA[0], AIL_ETA[1], HINGE, gap, inset=gap)
    ail_half = wing_half & cut_ail
    hinge_pins = []
    for eta in np.linspace(AIL_ETA[0] + 0.05, AIL_ETA[1] - 0.05, 3):
        xq, c = geo(eta)
        x_h = xq + 0.25 * c - HINGE * c
        tw = math.radians(TWIST_ROOT + (TWIST_TIP - TWIST_ROOT) * eta)
        z_camber = (0.02 if T["foil"][0] == "2" else 0.035) * c * math.cos(tw) - (0.5 - HINGE) * c * math.sin(tw)
        hinge_pins.append(K.box(3.5 * gap, 0.012 * half, 0.025 * c).translate(x_h - 0.3 * gap, eta * half, z_camber))
    ail_half = ail_half + K.Solid.union_all(hinge_pins)
    wing_half = wing_half - cut_full
    wing_parts, ails = [], {}
    for side, sy in (("left", 1), ("right", -1)):
        mirror = (lambda s_: s_) if sy > 0 else (lambda s_: s_.mirror((0, 1, 0)))
        wing_parts.append(rot_x(mirror(wing_half), sy * dih))
        ails[side] = rot_x(mirror(ail_half), sy * dih)
    wing = K.Solid.union_all(wing_parts).translate(x_wq, 0, z_w)
    nav = [K.sphere(0.006 * b_span, segments=16).translate(x_wq - 0.1 * c_r, sy * b_span / 2 * 0.985, z_w + b_span / 2 * 0.985 * math.tan(math.radians(dih)))
           for sy in (1, -1)]
    b.add("wing", "Cánh chính", "Main wing", "wing",
          [Shape(wing, "paint_primary", 40.0), Shape(nav[0], "led_red", 40.0), Shape(nav[1], "led_green", 40.0)], parent_id="fuselage",
          required=True, aliases=["cánh", "cánh chính", "wing", "cánh máy bay", "đèn đầu cánh"],
          function=f"Cánh NACA {T['foil']} sải {b_span:.0f} mm, thuôn λ={T['lam']}, nhị diện {dih:g}°, xoắn giảm góc 3° về đầu cánh.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=0.35 * Hf + 0.02 * b_span, explode_order=3,
          dimensions={"wingspan": b_span, "root_chord": c_r, "dihedral_deg": dih})
    for side, sy in (("left", 1), ("right", -1)):
        b.add(f"aileron_{side}", f"Cánh liệng (aileron) {'trái' if sy > 0 else 'phải'}", "Aileron", "control_surface",
              Shape(ails[side].translate(x_wq, 0, z_w), "paint_secondary", 40.0), parent_id="wing", required=True,
              aliases=["cánh liệng", "aileron", f"aileron {'trái' if sy > 0 else 'phải'}", "cánh lái", "bánh lái nghiêng"],
              function="Cánh liệng điều khiển nghiêng (roll), bản lề dọc 73 % dây cung.", position_tag="left" if sy > 0 else "right",
              joint_axis=(0, 1, 0), explode_dir=(-1, 0, 0), explode_distance=0.35 * c_r, explode_order=1)

    # ---------- đuôi ----------
    tail_ids = []
    if tail == "v_tail":
        span_v = 0.15 * b_span                                        # mỗi mặt: diện tích ≈ ½ (đuôi ngang + đuôi đứng)
        c_v = 0.11 * b_span
        vs, vgeo = surface("0012", span_v, c_v, 0.6, 12.0, n=8)
        vcut = hinge_cutter(vgeo, span_v, 0.15, 0.95, TAIL_HINGE, 0.0)
        vcut_g = hinge_cutter(vgeo, span_v, 0.15, 0.95, TAIL_HINGE, 0.01 * c_v, inset=0.01 * c_v)
        rv = (vs & vcut_g) + K.box(0.035 * c_v, 0.03 * span_v, 0.03 * c_v).translate(vgeo(0.5)[0] + 0.25 * vgeo(0.5)[1] - TAIL_HINGE * vgeo(0.5)[1],
                                                                                        0.5 * span_v, 0.0)
        vs = vs - vcut
        t_t = 0.93
        xq_t = x_of(t_t)
        for side, sy in (("left", 1), ("right", -1)):
            mirror = (lambda s_: s_) if sy > 0 else (lambda s_: s_.mirror((0, 1, 0)))
            surf = rot_x(mirror(vs), sy * 38.0).translate(xq_t, 0, z_mid(t_t))
            rud = rot_x(mirror(rv), sy * 38.0).translate(xq_t, 0, z_mid(t_t))
            b.add(f"v_tail_{side}", f"Đuôi chữ V {'trái' if sy > 0 else 'phải'}", "V-tail surface", "tail", Shape(surf, "paint_primary", 40.0),
                  parent_id="fuselage", required=True, aliases=["đuôi chữ V", "đuôi", "v-tail", "cánh đuôi"],
                  function="Mặt đuôi chữ V 38° (kết hợp ổn định ngang + đứng).", position_tag="rear",
                  explode_dir=(0, sy * 0.6, 0.8), explode_distance=0.08 * b_span, explode_order=2)
            b.add(f"ruddervator_{side}", f"Cánh lái đuôi V {'trái' if sy > 0 else 'phải'}", "Ruddervator", "control_surface",
                  Shape(rud, "paint_secondary", 40.0), parent_id=f"v_tail_{side}", required=True,
                  aliases=["cánh lái đuôi", "ruddervator", "cánh lái độ cao", "cánh lái hướng", "cánh lái"],
                  function="Cánh lái đuôi V: lệch cùng chiều = độ cao (pitch), ngược chiều = hướng (yaw).", position_tag="rear",
                  joint_axis=(0, math.cos(math.radians(38)), sy * math.sin(math.radians(38))), explode_dir=(-1, 0, 0),
                  explode_distance=0.3 * c_v, explode_order=1)
            tail_ids.append(f"v_tail_{side}")
        contacts.append(["v_tail_left", "v_tail_right"])
    else:
        # đuôi đứng
        h_v = 0.12 * b_span
        c_v = 0.11 * b_span
        t_v = 0.9
        fin, fgeo = surface("0010", h_v, c_v, 0.55, 28.0, n=8, plane="xy")
        rcut = hinge_cutter(fgeo, h_v, 0.06, 0.88 if tail == "t_tail" else 0.96, TAIL_HINGE, 0.0, plane="xy")
        rcut_g = hinge_cutter(fgeo, h_v, 0.06, 0.88 if tail == "t_tail" else 0.96, TAIL_HINGE, 0.01 * c_v, plane="xy", inset=0.01 * c_v)
        xq5, c5 = fgeo(0.5)
        rud = (fin & rcut_g) + K.box(0.04 * c_v, 0.04 * c5, 0.03 * h_v).translate(xq5 + 0.25 * c5 - TAIL_HINGE * c5, 0, 0.5 * h_v)
        fin = fin - rcut
        x_vq = x_of(t_v) + 0.02 * b_span
        z_vb = z_top(t_v) - 0.04 * Hf
        fin = fin.translate(x_vq, 0, z_vb)
        b.add("fin", "Đuôi đứng", "Vertical stabilizer", "tail", Shape(fin, "paint_primary", 40.0), parent_id="fuselage", required=True,
              aliases=["đuôi đứng", "cánh đuôi đứng", "fin", "vertical stabilizer", "đuôi"],
              function="Đuôi đứng NACA 0010 vuốt sau 28°, ổn định hướng.", position_tag="rear",
              explode_dir=(0, 0, 1), explode_distance=0.06 * b_span, explode_order=2)
        b.add("rudder", "Cánh lái hướng (rudder)", "Rudder", "control_surface", Shape(rud.translate(x_vq, 0, z_vb), "paint_secondary", 40.0),
              parent_id="fin", required=True, aliases=["cánh lái hướng", "rudder", "bánh lái hướng", "cánh lái"],
              function="Cánh lái hướng điều khiển lệch hướng (yaw).", position_tag="rear", joint_axis=(0, 0, 1),
              explode_dir=(-1, 0, 0), explode_distance=0.3 * c_v, explode_order=1)
        tail_ids.append("fin")
        # đuôi ngang
        span_h = 0.15 * b_span
        c_h = 0.1 * b_span
        hs, hgeo = surface("0012", span_h, c_h, 0.7, 5.0, n=8)
        if tail == "t_tail":
            xq_tip, c_tip = fgeo(1.0)
            x_hq = x_vq + xq_tip + 0.05 * c_h
            z_h = z_vb + h_v + 0.25 * 0.12 * c_h
            parent_h = "fin"
            y_c = 0.06 * c_h
        else:
            x_hq = x_of(0.955) + 0.02 * b_span
            z_h = z_mid(0.955)
            parent_h = "fuselage"
            x_hinge = x_hq + (0.25 - TAIL_HINGE) * c_h
            y_c = 0.5 * fus(min(1.0, (x_nose - x_hinge) / Lf))[0] + 0.01 * c_h     # elevator hai nửa, chừa đuôi thân ở giữa
        ecut = hinge_cutter(hgeo, span_h, 0.0, 0.97, TAIL_HINGE, 0.0)
        ecut_g = hinge_cutter(hgeo, span_h, 0.0, 0.97, TAIL_HINGE, 0.01 * c_h)
        e_full = ecut + ecut.mirror((0, 1, 0))
        e_gap = ecut_g + ecut_g.mirror((0, 1, 0))
        center = K.box(c_h * 4, 2 * y_c, c_h).translate(-c_h, 0, 0)
        center_g = K.box(c_h * 4, 2 * (y_c + 0.01 * c_h), c_h).translate(-c_h, 0, 0)
        hs_full = hs + hs.mirror((0, 1, 0))
        elev = (hs_full & e_gap) - center_g
        xq5h, c5h = hgeo(0.5)
        horns = K.Solid.union_all([K.box(0.04 * c_h, 0.03 * span_h, 0.025 * c_h).translate(xq5h + 0.25 * c5h - TAIL_HINGE * c5h, sy * 0.5 * span_h, 0)
                                   for sy in (1, -1)])
        elev = elev + horns
        hs_full = hs_full - (e_full - center)
        b.add("h_stab", "Đuôi ngang", "Horizontal stabilizer", "tail", Shape(hs_full.translate(x_hq, 0, z_h), "paint_primary", 40.0),
              parent_id=parent_h, required=True, aliases=["đuôi ngang", "cánh đuôi ngang", "horizontal stabilizer", "đuôi"],
              function="Đuôi ngang NACA 0012, ổn định dọc.", position_tag="rear",
              explode_dir=(0, 0, 1), explode_distance=0.05 * b_span, explode_order=2)
        b.add("elevator", "Cánh lái độ cao (elevator)", "Elevator", "control_surface", Shape(elev.translate(x_hq, 0, z_h), "paint_secondary", 40.0),
              parent_id="h_stab", required=True, aliases=["cánh lái độ cao", "elevator", "bánh lái độ cao", "cánh lái"],
              function="Cánh lái độ cao điều khiển chúc/ngóc (pitch).", position_tag="rear", joint_axis=(0, 1, 0),
              explode_dir=(-1, 0, 0), explode_distance=0.3 * c_h, explode_order=1)
        tail_ids.append("h_stab")

    # ---------- càng đáp ----------
    def wheel_at(x: float, y: float, r: float, width: float) -> tuple[K.Solid, K.Solid]:
        tire, rim = C.wheel(2 * r, width, spokes=5, tread=False)
        t_ = K.Solid.union_all([s_.solid for s_ in tire]).translate(x, y, r)
        r_ = K.Solid.union_all([s_.solid for s_ in rim]).translate(x, y, r)
        return t_, r_
    z_wing_at = lambda y: z_w + abs(y) * math.tan(math.radians(dih))    # noqa: E731
    if typ != "vtol":
        y_m = (0.14 if typ == "light" else 0.09) * b_span
        x_m = x_wq - 0.25 * c_r + 0.08 * c_r if typ == "light" else x_of(t_w + 0.08)
        tires, rims, legs, pants = [], [], [], []
        for sy in (1, -1):
            tr, rm = wheel_at(x_m, sy * y_m, rw, 0.45 * rw)
            tires.append(tr)
            rims.append(rm)
            if typ == "light":
                z0 = z_wing_at(y_m) + 0.02 * c_r
                legs.append(K.cylinder(0.08 * rw, z0 - rw, segments=20).translate(x_m, sy * (y_m - 0.4 * rw), rw))
                legs.append(K.box(0.3 * rw, 0.4 * rw, 0.12 * rw).translate(x_m, sy * (y_m - 0.2 * rw), rw))
                pant = K.ellipsoid(1.5 * rw, 0.42 * rw, 0.75 * rw, segments=32).translate(x_m - 0.2 * rw, sy * y_m, 1.25 * rw)
                pants.append(pant - K.box(2.4 * rw, 0.6 * rw, 1.3 * rw).translate(x_m, sy * y_m, 0.65 * rw))
            else:
                path = np.array([[x_m, sy * 0.25 * Wf, zb0 + fus(t_w + 0.08)[2] + 0.1 * Hf], [x_m, sy * 0.5 * y_m, 0.5 * (zb0 + 2 * rw)],
                                 [x_m, sy * (y_m - 0.35 * rw), rw]])
                legs.append(K.tube(P.spline_through(path, 16), 0.06 * rw * 2, 12))
                legs.append(K.cylinder(0.08 * rw, 0.8 * rw, segments=16).rotate(90, 0, 0).translate(x_m, sy * (y_m - 0.1 * rw), rw))
        shapes = [Shape(K.Solid.union_all(tires), "rubber", 40.0), Shape(K.Solid.union_all(rims), "aluminum", 40.0),
                  Shape(K.Solid.union_all(legs), "steel_dark" if typ == "light" else "aluminum", 40.0)]
        if pants:
            shapes.append(Shape(K.Solid.union_all(pants), "paint_primary", 40.0))
        b.add("main_gear", "Càng đáp chính", "Main landing gear", "landing_gear", shapes, parent_id="wing" if typ == "light" else "fuselage",
              required=True, aliases=["càng đáp", "càng chính", "bánh xe", "landing gear", "giảm chấn càng"],
              function=("Càng chính giảm chấn dầu–khí, bánh có ốp chắn gió." if typ == "light" else "Càng chính dây thép lò xo, bánh cao su."),
              position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.6 * rw + 0.02 * b_span, explode_order=2)
        # càng mũi
        t_n = t_fw + 0.02
        x_n = x_of(t_n)
        rn = 0.8 * rw
        tr, rm = wheel_at(x_n + 0.3 * rn, 0.0, rn, 0.4 * rn)
        z_fb = zb0 + fus(t_n)[2]
        strut = K.cylinder(0.09 * rn, z_fb + 0.05 * Hf - rn, segments=20).translate(x_n, 0.32 * rn, rn)
        strut2 = K.cylinder(0.09 * rn, z_fb + 0.05 * Hf - rn, segments=20).translate(x_n, -0.32 * rn, rn)
        yoke = K.box(0.25 * rn, 0.82 * rn, 0.12 * rn).translate(x_n, 0, z_fb + 0.05 * Hf - 0.3 * rn)
        axle_n = K.cylinder(0.07 * rn, 0.8 * rn, segments=16).rotate(90, 0, 0).translate(x_n + 0.3 * rn, 0, rn)
        link = K.Solid.union_all([K.box(0.34 * rn, 0.1 * rn, 0.1 * rn).translate(x_n + 0.15 * rn, sy * 0.32 * rn, rn) for sy in (1, -1)])
        b.add("nose_gear", "Càng mũi", "Nose landing gear", "landing_gear",
              [Shape(tr, "rubber", 40.0), Shape(rm, "aluminum", 40.0), Shape(strut + strut2 + yoke + axle_n + link, "steel_dark", 40.0)],
              parent_id="fuselage", required=True, aliases=["càng mũi", "bánh mũi", "nose gear", "càng đáp"],
              function="Càng mũi lái hướng khi chạy đà, giảm chấn ống lồng.", position_tag="front",
              explode_dir=(0, 0, -1), explode_distance=0.6 * rn + 0.02 * b_span, explode_order=2)
    # ---------- VTOL: dầm + 4 rotor nâng + càng trượt ----------
    if typ == "vtol":
        y_b = 0.22 * b_span                                          # trong vùng không có aileron (η < 0,55)
        eta_b = y_b / (b_span / 2)
        xq_b, c_b = geo(eta_b)
        R_r = 0.085 * b_span
        x_le = x_wq + xq_b + 0.25 * c_b
        x_te = x_le - c_b
        x_f, x_r = x_le + R_r + 0.03 * b_span, x_te - R_r - 0.03 * b_span
        r_bm = 0.012 * b_span
        for side, sy in (("left", 1), ("right", -1)):
            yb = sy * y_b
            z_wb = z_wing_at(y_b) - 0.06 * c_b                           # mặt dưới cánh tại dầm (xấp xỉ)
            zb = z_wb - r_bm + 0.3 * r_bm
            boom = K.capsule(r_bm, x_f - x_r + 0.06 * b_span, segments=24).rotate(0, 90, 0).translate((x_f + x_r) / 2, yb, zb)
            pylon = K.rounded_box(0.5 * c_b, 1.2 * r_bm, 0.12 * c_b + r_bm, 0.2 * r_bm, segments=8).translate(x_le - 0.5 * c_b, yb, z_wb + 0.02 * c_b)
            skids = []
            for xs in (x_f - 0.5 * R_r, x_r + 0.5 * R_r):
                skids.append(K.tube(np.array([[xs, yb, zb], [xs, yb + sy * 0.02 * b_span, 0.012 * b_span]]), 0.35 * r_bm, 10))
            skid_bar = K.capsule(0.3 * r_bm, (x_f - x_r) - 0.4 * R_r, segments=16).rotate(0, 90, 0).translate(
                (x_f + x_r) / 2, yb + sy * 0.02 * b_span, 0.3 * r_bm)
            posts = K.Solid.union_all([K.cylinder(0.3 * r_bm, 0.012 * b_span - 0.3 * r_bm + 0.1, segments=12).translate(
                xs, yb + sy * 0.02 * b_span, 0.3 * r_bm) for xs in (x_f - 0.5 * R_r, x_r + 0.5 * R_r)])
            b.add(f"boom_{side}", f"Dầm rotor {'trái' if sy > 0 else 'phải'}", "Rotor boom", "boom",
                  [Shape(boom, "carbon", 40.0), Shape(pylon, "paint_primary", 40.0)], parent_id="wing", required=True,
                  aliases=["dầm", "dầm rotor", "boom", "tay đòn"], function="Dầm carbon mang 2 rotor nâng (trước/sau cánh).",
                  position_tag="left" if sy > 0 else "right", explode_dir=(0, 0, -1), explode_distance=0.05 * b_span, explode_order=3)
            b.add(f"skid_{side}", f"Càng trượt {'trái' if sy > 0 else 'phải'}", "Landing skid", "landing_gear",
                  Shape(K.Solid.union_all(skids) + skid_bar + posts, "aluminum", 40.0), parent_id=f"boom_{side}", required=True,
                  aliases=["càng trượt", "càng đáp", "chân đáp", "landing skid"], function="Càng trượt hạ cánh thẳng đứng.",
                  position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.04 * b_span, explode_order=2)
            for pos, xr in (("front", x_f), ("rear", x_r)):
                st_d = 0.025 * b_span
                mot = C.motor_outrunner(st_d, 0.35 * st_d)
                mh = C.motor_height(0.35 * st_d)
                ms = [Shape(s_.solid.translate(xr, yb, zb + r_bm - 0.2 * r_bm), s_.material, 40.0) for s_ in mot]
                cw = (sy > 0) == (pos == "front")
                pr = C.propeller(2 * R_r, 2, clockwise=cw, hub_d=0.6 * st_d)
                prs = K.Solid.union_all([s_.solid for s_ in pr]).translate(xr, yb, zb + r_bm - 0.2 * r_bm + mh + 0.03 * st_d)
                mid = f"lift_motor_{side}_{pos}"
                b.add(mid, f"Motor nâng {'trái' if sy > 0 else 'phải'} {'trước' if pos == 'front' else 'sau'}", "Lift motor", "motor", ms,
                      parent_id=f"boom_{side}", required=True, aliases=["motor nâng", "động cơ nâng", "rotor", "lift motor"],
                      function="Motor không chổi than nâng thẳng đứng (cất/hạ cánh VTOL).", position_tag="top", joint_axis=(0, 0, 1),
                      explode_dir=(0, 0, 1), explode_distance=0.03 * b_span, explode_order=2)
                b.add(f"lift_prop_{side}_{pos}", "Cánh quạt nâng", "Lift propeller", "propeller", Shape(prs, "prop_plastic", 40.0),
                      parent_id=mid, required=True, aliases=["cánh quạt nâng", "cánh quạt", "rotor", "propeller"],
                      function="Cánh quạt nâng 2 lá, chiều quay xen kẽ (triệt mô-men).", position_tag="top", joint_axis=(0, 0, 1),
                      explode_dir=(0, 0, 1), explode_distance=0.04 * b_span, explode_order=1)
        contacts.append(["skid_*", "boom_*"])
    b.note_stage(1, "Tháo cánh lái, cánh quạt, nắp kính")
    b.note_stage(2, "Tháo nắp động cơ, đuôi, càng đáp")
    b.note_stage(3, "Tháo cánh chính khỏi thân")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"aircraft_type": typ, "wingspan_mm": b_span, "dihedral_deg": dih, "tail": tail, "airfoil": f"NACA {T['foil']}",
                       "root_chord_mm": c_r, "prop_d_mm": 2 * R_prop, "prop_blades": T["blades"], "length_mm": Lf,
                       "prop_clearance_min_mm": clear,
                       "standard": "Tỷ lệ máy bay 4 chỗ cánh thấp (PA-28/DA40); FAR 23.925 khoảng hở cánh quạt; NACA 4 chữ số",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
