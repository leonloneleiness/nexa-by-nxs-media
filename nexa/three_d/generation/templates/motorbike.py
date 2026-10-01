"""Xe hai bánh: mô tô côn tay 150 cc (tỷ lệ kiểu naked bike: cơ sở 1300 mm, lốp 110/70-17 & 150/60-17, góc lái 25°),
xe tay ga (kiểu SH 125: lốp 16", sàn để chân phẳng, động cơ liền càng sau), xe đạp điện (khung kim cương, bánh 700×40C,
motor trục bánh sau, pin trên ống dưới).

- Trục lái nghiêng theo góc caster, phuộc song song trục lái, độ lệch phuộc (offset) → vệt quét (trail) dương.
- Bánh: lốp theo ký hiệu ISO (vd. 110/70-17 → Ø586 mm; 700×40C = ISO 40-622 → Ø702 mm), cả hai bánh chạm đất.
- Mô tô: khung ống, động cơ xi lanh nghiêng có cánh tản nhiệt, ống xả vòng dưới máy ra pô bên phải, bình xăng, yên,
  càng sau hai nhánh + giảm xóc đơn, xích tải bên trái. Tay ga: yếm trước, sàn để chân, thân sau, động cơ + hộp CVT
  làm luôn càng sau. Xe đạp điện: đùi đĩa + bàn đạp, xích, pin, motor hub, chắn bùn, baga.
Hệ trục: X trước, Y trái, Z lên; bánh chạm đất z = 0.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# (bề rộng lốp, tỷ lệ thành, vành inch) hoặc ("iso", bề rộng, đường kính vành ISO mm)
TYPES = {
    "motorcycle": dict(wb=1300.0, front=(110, 70, 17), rear=(150, 60, 17), rake=25.0, offset=30.0, seat=800.0, fork=700.0,
                       bar=760.0, name="Mô tô côn tay 150 cc"),
    "scooter": dict(wb=1340.0, front=(100, 80, 16), rear=(120, 80, 16), rake=27.0, offset=25.0, seat=790.0, fork=640.0,
                    bar=700.0, name="Xe tay ga 125 cc"),
    "ebike": dict(wb=1100.0, front=("iso", 40, 622), rear=("iso", 40, 622), rake=19.0, offset=45.0, seat=870.0, fork=580.0,
                  bar=600.0, name="Xe đạp điện"),
}


def tire_d(t: tuple) -> tuple[float, float]:
    """(đường kính ngoài, bề rộng lốp) theo ký hiệu: 110/70-17 → 17×25,4 + 2×110×0,70; ISO 40-622 → 622 + 2×40."""
    if t[0] == "iso":
        return t[2] + 2.0 * t[1], float(t[1])
    return t[2] * 25.4 + 2.0 * t[0] * t[1] / 100.0, float(t[0])


def tube(a, b, r: float, seg: int = 16) -> K.Solid:
    return K.tube(np.array([a, b], float), r, seg)


def poly_tube(pts, r: float, seg: int = 16, smooth: bool = True) -> K.Solid:
    pts = np.array(pts, float)
    return K.tube(P.spline_through(pts, 12 * len(pts)) if smooth and len(pts) > 2 else pts, r, seg)


def bike_wheel(D: float, tw: float, spokes: int = 32, hub_r: float = 22.0, hub_w: float = 100.0) -> tuple[K.Solid, K.Solid, K.Solid]:
    """Bánh xe đạp trục Y: (lốp, vành + nan hoa, moay-ơ). Tâm ở gốc."""
    R = D / 2
    tire = K.torus(R - tw / 2, tw / 2, segments=96, tube_segments=16)
    r_rim = R - tw + 4.0
    rim = K.revolve([(r_rim - 22.0, -11.0), (r_rim, -12.0), (r_rim, 12.0), (r_rim - 22.0, 11.0)], segments=96)
    sp = []
    for k in range(spokes):
        a = 2 * math.pi * k / spokes
        side = 1 if k % 2 else -1
        a0 = a + side * 0.25
        p0 = np.array([hub_r * 0.8 * math.cos(a0), hub_r * 0.8 * math.sin(a0), side * (hub_w / 2 - 6.0)])
        p1 = np.array([(r_rim - 20.0) * math.cos(a), (r_rim - 20.0) * math.sin(a), side * 2.0])
        sp.append(tube(p0, p1, 1.0, 6))
    hub = K.cylinder(hub_r, hub_w, segments=32).translate(0, 0, -hub_w / 2)
    rot = lambda s: s.rotate(-90, 0, 0)                               # noqa: E731
    return rot(tire), rot(rim + K.Solid.union_all(sp)), rot(hub)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    typ = p.get("bike_type", "motorcycle")
    T = TYPES[typ]
    wb = T["wb"]
    Df, twf = tire_d(T["front"])
    Dr, twr = tire_d(T["rear"])
    Rf, Rr = Df / 2, Dr / 2
    mats = MC.tech_materials(spec, primary="#b1121b" if typ == "motorcycle" else ("#e9ecef" if typ == "scooter" else "#2d6a4f"),
                             secondary="#1b1d21", accent="#f4a261")
    mats["leather"] = M.material("leather", "plastic", "#1d1d1f", 0.0, 0.6, name="Da yên")
    b = AssemblyBuilder(spec.name or T["name"], "motorbike", mats)
    th = math.radians(90.0 - T["rake"])                               # góc trục lái so với phương ngang
    u = np.array([-math.cos(th), 0.0, math.sin(th)])                  # hướng trục lái (lên, ra sau)
    n = np.array([math.sin(th), 0.0, math.cos(th)])                   # vuông góc trục lái (ra trước)
    A = np.array([wb / 2, 0.0, Rf])                                   # trục bánh trước
    Rax = np.array([-wb / 2, 0.0, Rr])                                # trục bánh sau
    o = T["offset"]
    axis_pt = lambda s: A - o * n + s * u                             # noqa: E731  điểm trên trục lái
    Lf = T["fork"]
    s_lc, s_tc = Lf - 130.0, Lf - 20.0                                # kẹp dưới / kẹp trên
    H0, H1 = axis_pt(s_lc + 20.0), axis_pt(s_tc - 20.0)
    trail = (A[2] * math.cos(th) / math.sin(th)) - o / math.sin(th)   # vệt quét (trail) hình học
    moto, scoot, ebike = typ == "motorcycle", typ == "scooter", typ == "ebike"
    contacts: list[list[str]] = []
    frame_mat = "paint_secondary" if not ebike else "paint_primary"
    r_ft = 20.0 if not ebike else 14.0

    # ---------- khung ----------
    head = K.cylinder(32.0 if not ebike else 22.0, float(np.linalg.norm(H1 - H0)) + 40.0, segments=32)
    head = MC.orient(head, H0 - 20.0 * u, u)
    fr = [head]
    if moto:
        P_sw = np.array([-wb / 2 + 0.42 * wb, 0.0, Rr + 80.0])      # trục càng sau
        for sy in (1, -1):
            fr.append(poly_tube([H0, [150.0, sy * 90.0, 560.0], [-40.0, sy * 90.0, 520.0], P_sw + [0, sy * 90.0, 0]], r_ft))
            fr.append(poly_tube([[-60.0, sy * 90.0, 640.0], [-330.0, sy * 90.0, 720.0], [-620.0, sy * 80.0, 740.0]], 14.0))
            fr.append(tube([-40.0, sy * 90.0, 520.0], [-60.0, sy * 90.0, 650.0], 16.0))
        fr.append(poly_tube([H1, [120.0, 0.0, 760.0], [-60.0, 0.0, 650.0]], 26.0))
        fr.append(tube(P_sw + [0, -100.0, 0], P_sw + [0, 100.0, 0], 18.0))
        fr.append(tube([-60.0, 90.0, 650.0], [-60.0, -90.0, 650.0], 16.0))
        pegs = [tube([-120.0, sy * 90.0, 330.0], [-120.0, sy * 190.0, 330.0], 12.0) for sy in (1, -1)]
        peg_m = [tube([-120.0, sy * 90.0, 330.0], P_sw + [0, sy * 90.0, 0], 14.0) for sy in (1, -1)]
        fr += pegs + peg_m
    elif scoot:
        P_sw = np.array([-150.0, 0.0, 330.0])
        fr.append(poly_tube([H0, [260.0, 0.0, 420.0], [180.0, 0.0, 300.0], [-80.0, 0.0, 300.0], [-180.0, 0.0, 420.0], [-300.0, 0.0, 620.0]], 26.0))
        for sy in (1, -1):
            fr.append(poly_tube([[-280.0, sy * 60.0, 600.0], [-500.0, sy * 90.0, 640.0], [-760.0, sy * 90.0, 660.0]], 16.0))
        fr.append(tube([-280.0, 60.0, 600.0], [-280.0, -60.0, 600.0], 16.0))
        fr.append(tube([-150.0, 0.0, 300.0], [-150.0, 0.0, 345.0], 20.0))
        fr.append(tube(P_sw + [0, -30.0, 0], P_sw + [0, 90.0, 0], 18.0))
        fr.append(tube([-540.0, 90.0, 645.0], [-540.0, 135.0, 615.0], 12.0))            # tai bắt giảm xóc sau
    else:
        BB = np.array([-wb / 2 + 450.0, 0.0, Rr - 70.0])             # trục giữa (đùi đĩa), hạ 70 mm dưới trục bánh
        st_dir = np.array([-math.cos(math.radians(73)), 0, math.sin(math.radians(73))])
        ST = BB + 520.0 * st_dir
        fr += [tube(H1, ST - 40.0 * st_dir, r_ft), tube(H0, BB, 19.0), tube(BB, ST + 60.0 * st_dir, 15.0)]
        for sy in (1, -1):
            fr.append(tube(BB + [0, sy * 20.0, 0], Rax + [0, sy * 68.0, 0], 10.0))
            fr.append(tube(ST - 30.0 * st_dir + [0, sy * 15.0, 0], Rax + [0, sy * 68.0, 0], 9.0))
        fr.append(K.cylinder(22.0, 76.0, segments=24).rotate(90, 0, 0).translate(BB[0], 38.0, BB[2]))
        P_sw = Rax
    frame = K.Solid.union_all(fr)
    fshapes = [Shape(frame, frame_mat, 40.0)]
    b.add("frame", "Khung xe", "Frame", "frame", fshapes, required=True,
          aliases=["khung", "khung xe", "sườn xe", "cổ lái", "frame", "gác chân"] + (["đùi giữa"] if ebike else []),
          function={"motorcycle": "Khung ống thép kép ôm động cơ, cổ lái nghiêng, khung phụ đỡ yên.",
                    "scooter": "Khung ống xương sống thấp (underbone) cho sàn để chân phẳng.",
                    "ebike": "Khung kim cương nhôm: ống trên, ống dưới, ống yên, gióng xích, gióng yên."}[typ],
          position_tag="center", dimensions={"wheelbase": wb, "rake_deg": T["rake"]})

    # ---------- phuộc + ghi-đông ----------
    y_fk = twf / 2 + (35.0 if not ebike else 18.0)
    r_fk = 22.0 if moto else (20.0 if scoot else 12.0)
    legs = [tube(A + [0, sy * y_fk, 0] - 40.0 * u, A + [0, sy * y_fk, 0] + s_tc * u, r_fk) for sy in (1, -1)]
    lowers = [tube(A + [0, sy * y_fk, 0] - 50.0 * u, A + [0, sy * y_fk, 0] + 0.45 * Lf * u, r_fk + 7.0) for sy in (1, -1)] if not ebike else []
    clamps = []
    for s_ in (s_lc, s_tc):
        c0 = A + s_ * u
        clamps.append(K.hull([K.cylinder(r_fk + 8.0, 24.0, segments=24).translate(0, 0, -12.0).rotate(0, 90 - math.degrees(th), 0)
                              .translate(*(c0 + [0, sy * y_fk, 0])) for sy in (1, -1)]
                             + [K.cylinder(28.0, 24.0, segments=24).translate(0, 0, -12.0).rotate(0, 90 - math.degrees(th), 0).translate(*axis_pt(s_))]))
    stem_top = axis_pt(s_tc + 60.0)
    stem = tube(axis_pt(s_tc - 30.0), stem_top, 16.0)
    bw = T["bar"] / 2
    bar_pts = [stem_top + [-40.0, bw, 30.0], stem_top + [-10.0, 0.45 * bw, 10.0], stem_top, stem_top + [-10.0, -0.45 * bw, 10.0],
               stem_top + [-40.0, -bw, 30.0]]
    bar = poly_tube(bar_pts, 11.0)
    grips = [tube(stem_top + [-40.0, sy * (bw - 110.0), 30.0], stem_top + [-40.0, sy * (bw + 10.0), 30.0], 16.0) for sy in (1, -1)]
    fork_sh = [Shape(K.Solid.union_all(legs), "chrome" if not ebike else "paint_secondary", 40.0),
               Shape(K.Solid.union_all(clamps) + stem + bar, "aluminum_dark", 40.0),
               Shape(K.Solid.union_all(grips), "rubber", 40.0)]
    if lowers:
        fork_sh.append(Shape(K.Solid.union_all(lowers), "aluminum", 40.0))
    # chắn bùn trước (cung trên lốp) gá vào chân phuộc
    fen_r = Rf + (22.0 if not ebike else 16.0)
    fen_w = min(2 * y_fk - 2 * r_fk - 14.0, twf + 40.0)
    fen = K.revolve([(fen_r, -fen_w / 2), (fen_r + 4.0, -fen_w / 2), (fen_r + 4.0, fen_w / 2), (fen_r, fen_w / 2)], segments=64, degrees=120.0)
    fen = fen.rotate(0, 0, -110.0).rotate(-90, 0, 0).translate(*A)                # cung từ −10° (trước) tới 110° (trên)
    fork_sh.append(Shape(fen, "plastic_black" if not scoot else "paint_primary", 40.0))
    lamp_c = A + 0.62 * Lf * u + n * (95.0 if not ebike else 60.0)
    if moto:
        housing = K.sphere(85.0, segments=32).scale(0.8, 1.0, 1.0).translate(*lamp_c)
        lens = K.cylinder(78.0, 6.0, segments=40).rotate(0, 90, 0).translate(*(lamp_c + [48.0, 0, 0]))
        brk_l = tube(lamp_c - [0, 0, 0], A + 0.62 * Lf * u, 12.0)
        fork_sh += [Shape(housing - lens.translate(-2.0, 0, 0) + brk_l, "steel_dark", 40.0), Shape(lens, "led_white", 40.0)]
    elif ebike:
        lens = K.cylinder(22.0, 30.0, segments=24).rotate(0, 90, 0).translate(*(A + 0.8 * Lf * u + n * 40.0))
        fork_sh.append(Shape(lens + tube(A + 0.8 * Lf * u, A + 0.8 * Lf * u + n * 40.0, 6.0), "led_white", 40.0))
    if not ebike:
        for sy in (1, -1):
            m0 = stem_top + [-40.0, sy * (bw - 140.0), 30.0]
            m1 = m0 + [-20.0, sy * 50.0, 150.0]
            fork_sh.append(Shape(tube(m0, m1, 6.0) + K.ellipsoid(40.0, 60.0, 35.0, segments=20).translate(*(m1 + [0, sy * 20.0, 20.0])),
                                 "steel_dark", 40.0))
    b.add("fork", "Phuộc trước + ghi-đông", "Front fork & handlebar", "fork", fork_sh, parent_id="frame", required=True,
          aliases=["phuộc", "phuộc trước", "ghi đông", "tay lái", "cổ phuộc", "đèn pha", "gương", "chắn bùn trước", "fork"],
          function=f"Phuộc {'ống lồng' if not ebike else 'cứng'} song song trục lái (caster {T['rake']:g}°, offset {o:g} mm, "
                   f"vệt quét ≈ {trail:.0f} mm), ghi-đông + tay nắm" + (", đèn pha, gương." if not ebike else ", đèn trước."),
          position_tag="front", joint_axis=tuple(float(x) for x in u), explode_dir=(1, 0, 0.3), explode_distance=0.25 * wb, explode_order=2)

    # ---------- bánh ----------
    def road_wheel(D: float, tw: float) -> tuple[K.Solid, K.Solid]:
        ts, rs = C.wheel(D, tw, spokes=6 if moto else 5, tread=True)
        return K.Solid.union_all([s_.solid for s_ in ts]), K.Solid.union_all([s_.solid for s_ in rs])

    for pos, Dd, tw_, c_ in (("front", Df, twf, A), ("rear", Dr, twr, Rax)):
        if ebike:
            tire, rim, hub = bike_wheel(Dd, tw_, hub_r=22.0 if pos == "front" else 85.0, hub_w=100.0 if pos == "front" else 110.0)
            shapes = [Shape(tire.translate(*c_), "rubber", 40.0), Shape(rim.translate(*c_), "aluminum", 40.0),
                      Shape(hub.translate(*c_), "steel_dark" if pos == "front" else "cast_aluminum", 40.0)]
        else:
            tire, rim = road_wheel(Dd, tw_)
            disc = K.cylinder(0.46 * Dd / 2, 5.0, segments=48).translate(0, 0, -2.5) - K.cylinder(0.3 * Dd / 2, 10.0, segments=40).translate(0, 0, -5.0)
            disc = disc.rotate(-90, 0, 0).translate(0, -0.3 * tw_, 0)
            axle_ = K.cylinder(9.0, 2 * (tw_ / 2 + 40.0) + 20.0, segments=16).rotate(90, 0, 0).translate(0, tw_ / 2 + 50.0, 0)
            shapes = [Shape(tire.translate(*c_), "rubber", 40.0), Shape(rim.translate(*c_), "aluminum_dark" if moto else "aluminum", 40.0),
                      Shape((disc + axle_).translate(*c_), "stainless", 40.0)]
        if pos == "rear" and (moto or ebike):
            spr_r = 105.0 if moto else 38.0
            spr = K.cylinder(spr_r, 6.0, segments=48) - K.cylinder(spr_r * 0.55, 10.0, segments=32).translate(0, 0, -2.0)
            spr = spr.rotate(90, 0, 0).translate(c_[0], (135.0 if moto else 72.0) + 3.0, c_[2])
            shapes.append(Shape(spr, "steel", 40.0))
        vi = "trước" if pos == "front" else "sau"
        b.add(f"wheel_{pos}", f"Bánh {vi}", f"{pos.title()} wheel", "wheel", shapes,
              parent_id="fork" if pos == "front" else ("swingarm" if moto else ("engine" if scoot else "frame")), required=True,
              aliases=["bánh xe", f"bánh {vi}", "lốp", "vành", "mâm", "wheel"] + (["đĩa phanh"] if not ebike else ["nan hoa"])
              + (["motor trục bánh", "hub motor"] if ebike and pos == "rear" else []),
              function=f"Bánh {vi}: lốp Ø{Dd:.0f} mm (bề rộng {tw_:.0f} mm)" + ("" if not (ebike and pos == "rear") else ", motor không chổi than 250 W trong moay-ơ") + ".",
              position_tag="front" if pos == "front" else "rear", joint_axis=(0, 1, 0),
              explode_dir=(1, 0, 0) if pos == "front" else (-1, 0, 0), explode_distance=0.3 * wb, explode_order=1,
              dimensions={"diameter": Dd, "width": tw_})

    # ---------- càng sau / giảm xóc ----------
    if moto:
        y_sa = twr / 2 + 30.0
        arms = [poly_tube([P_sw + [0, sy * y_sa, 0], Rax + [0, sy * y_sa, 0]], 15.0, smooth=False) for sy in (1, -1)]
        x_br = -250.0
        z_br = float(np.interp(x_br, [Rax[0], P_sw[0]], [Rax[2], P_sw[2]]))
        br = tube([x_br, y_sa, z_br], [x_br, -y_sa, z_br], 14.0)
        piv = tube(P_sw + [0, -y_sa - 15.0, 0], P_sw + [0, y_sa + 15.0, 0], 22.0)
        b.add("swingarm", "Càng sau (gắp)", "Swingarm", "swingarm", Shape(K.Solid.union_all(arms) + br + piv, "aluminum", 40.0),
              parent_id="frame", required=True, aliases=["càng sau", "gắp", "gắp sau", "swingarm"],
              function="Càng sau nhôm hai nhánh quay quanh trục càng, giữ bánh sau + tăng xích.", position_tag="rear",
              joint_axis=(0, 1, 0), explode_dir=(-1, 0, -0.3), explode_distance=0.2 * wb, explode_order=2)
        sh0, sh1 = np.array([x_br, 0.0, z_br + 10.0]), np.array([-200.0, 0.0, 650.0])
        contacts.append(["rear_shock", "swingarm"])
    elif ebike:
        sh0 = sh1 = None
    else:
        sh0, sh1 = np.array([-560.0, 150.0, 420.0]), np.array([-540.0, 150.0, 615.0])
    if sh0 is not None:
        dsh = (sh1 - sh0) / np.linalg.norm(sh1 - sh0)
        Lsh = float(np.linalg.norm(sh1 - sh0))
        damper = tube(sh0, sh1, 14.0) + tube(sh0, sh0 + 0.55 * Lsh * dsh, 22.0)
        spring = MC.orient(K.tube(MC.helix_path(34.0, [(7.0, 0.55 * Lsh / 7.0)], z0=0.0, per_turn=16), 5.0, 8), sh0 + 0.4 * Lsh * dsh, dsh)
        eyes = K.Solid.union_all([K.cylinder(20.0, 40.0, segments=20).rotate(90, 0, 0).translate(*(q + [0, 20.0, 0])) for q in (sh0, sh1)])
        b.add("rear_shock", "Giảm xóc sau", "Rear shock absorber", "spring",
              [Shape(damper + eyes, "steel_dark", 40.0), Shape(spring, "paint_accent" if moto else "spring_steel", 40.0)],
              parent_id="frame", required=True, aliases=["giảm xóc", "giảm xóc sau", "phuộc sau", "lò xo", "shock"],
              function="Giảm xóc lò xo trụ + giảm chấn dầu.", position_tag="rear", joint_axis=tuple(float(x) for x in dsh),
              explode_dir=(0, 0.4 if scoot else 0, 1), explode_distance=0.18 * wb, explode_order=1)
        if scoot:
            contacts.append(["rear_shock", "engine"])

    # ---------- động cơ / thân ----------
    if moto:
        cc = np.array([115.0, 0.0, 330.0])
        case = K.rounded_box(380.0, 250.0, 260.0, 50.0, segments=12).translate(*cc)
        cdir = np.array([math.sin(math.radians(30)), 0, math.cos(math.radians(30))])
        base = np.array([185.0, 0.0, 440.0])
        cyl = MC.orient(K.cylinder(70.0, 220.0, segments=40), base, cdir)
        fins = K.Solid.union_all([MC.orient(K.cylinder(95.0, 5.0, segments=40), base + (40.0 + 16.0 * k) * cdir, cdir) for k in range(9)])
        head_e = MC.orient(K.rounded_box(170.0, 200.0, 70.0, 20.0, segments=8).translate(0, 0, 35.0), base + 210.0 * cdir, cdir)
        cover = K.cylinder(80.0, 20.0, segments=40).rotate(90, 0, 0).translate(60.0, -125.0 + 0.0, 320.0)
        mounts = K.Solid.union_all([tube([-40.0, -95.0, 520.0], [-40.0, 95.0, 520.0], 14.0), tube([150.0, -95.0, 560.0], [150.0, 95.0, 560.0], 14.0)])
        spr_f = K.cylinder(40.0, 6.0, segments=32).rotate(90, 0, 0).translate(-40.0, 138.0, 330.0)
        b.add("engine", "Động cơ 150 cc", "Engine", "engine",
              [Shape(case + cover, "cast_aluminum", 40.0), Shape(cyl + fins + head_e, "steel_dark", 40.0), Shape(mounts + spr_f, "steel", 40.0)],
              parent_id="frame", required=True, aliases=["động cơ", "máy", "lốc máy", "xi lanh", "cánh tản nhiệt", "engine"],
              function="Động cơ 4 kỳ 1 xi lanh làm mát bằng gió (cánh tản nhiệt), nghiêng 30°, hộp số 6 cấp liền lốc.",
              position_tag="center", explode_dir=(0, 0, -1), explode_distance=0.3 * wb, explode_order=3)
        ex_pts = [base + 230.0 * cdir + [60.0, 0, -40.0], [330.0, 0.0, 420.0], [320.0, -20.0, 240.0], [150.0, -60.0, 170.0], [-150.0, -150.0, 200.0],
                  [-300.0, -175.0, 420.0]]
        header = poly_tube(ex_pts, 22.0)
        muff = K.cylinder(45.0, 260.0, 38.0, segments=32).rotate(0, -90, 0).rotate(0, -8, 0).translate(-300.0, -175.0, 425.0)
        b.add("exhaust", "Ống xả + pô", "Exhaust", "pipe", [Shape(header, "chrome", 40.0), Shape(muff, "stainless", 40.0)], parent_id="engine",
              required=True, aliases=["ống xả", "pô", "bô", "exhaust", "muffler"], function="Ống xả vòng trước–dưới lốc máy ra pô tiêu âm bên phải.",
              position_tag="right", explode_dir=(0, -1, 0), explode_distance=0.2 * wb, explode_order=1)
        # xích: nhông trước (lốc máy) → nhông sau (bánh sau), phía trái
        path, _, _ = MC.open_belt_path(40.0, 105.0, float(np.hypot(-40.0 - Rax[0], 330.0 - Rax[2])), step=4.0)
        ang = math.atan2(Rax[2] - 330.0, Rax[0] - (-40.0))
        ca, sa = math.cos(ang), math.sin(ang)
        p3 = np.column_stack([-40.0 + path[:, 0] * ca - path[:, 1] * sa, np.full(len(path), 141.0), 330.0 + path[:, 0] * sa + path[:, 1] * ca])
        chain = K.sweep(P.rounded_rect(8.0, 16.0, 2.0, 2), np.vstack([p3, p3[:1]]))
        b.add("chain", "Xích tải", "Drive chain", "chain", Shape(chain, "steel_dark", 40.0), parent_id="engine", required=True,
              aliases=["xích", "sên", "xích tải", "chain", "nhông xích"], function="Xích con lăn 428 truyền lực từ nhông trước tới nhông sau.",
              position_tag="left", explode_dir=(0, 1, 0), explode_distance=0.15 * wb, explode_order=1)
        contacts += [["chain", "wheel_rear"], ["chain", "swingarm"]]
        tank = K.loft([np.column_stack([np.full(40, x), P.superellipse(w, h, 2.4, 40)[:, 0], zc + P.superellipse(w, h, 2.4, 40)[:, 1]])
                       for x, w, h, zc in ((290.0, 180.0, 90.0, 800.0), (230.0, 330.0, 190.0, 815.0), (80.0, 360.0, 220.0, 800.0),
                                           (-60.0, 300.0, 170.0, 770.0), (-110.0, 200.0, 90.0, 745.0))])
        cap = K.cylinder(35.0, 12.0, segments=24).translate(120.0, 0, 905.0)
        b.add("fuel_tank", "Bình xăng", "Fuel tank", "fuel_tank", [Shape(tank, "paint_primary", 40.0), Shape(cap, "chrome", 40.0)],
              parent_id="frame", required=True, aliases=["bình xăng", "thùng xăng", "fuel tank", "nắp xăng"],
              function="Bình xăng thép dập ~12 lít ôm khung trên.", position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.2 * wb,
              explode_order=1)
        contacts.append(["fuel_tank", "seat"])
    elif scoot:
        cvt = K.hull([K.cylinder(110.0, 90.0, segments=32).rotate(90, 0, 0).translate(-230.0, 150.0, 340.0),
                      K.cylinder(85.0, 90.0, segments=32).rotate(90, 0, 0).translate(Rax[0], 150.0, Rax[2])])
        crank = K.rounded_box(260.0, 240.0, 200.0, 40.0, segments=8).translate(-230.0, 20.0, 330.0)
        cylh = K.rounded_box(240.0, 120.0, 130.0, 30.0, segments=8).translate(-60.0, 0.0, 330.0)
        piv = tube(P_sw + [0, -30.0, 0], P_sw + [0, 110.0, 0], 26.0) + tube(P_sw + [0, 60.0, 0], [-230.0, 60.0, 340.0], 30.0)
        muf = K.cylinder(55.0, 300.0, segments=32).rotate(0, -90, 0).translate(-420.0, -130.0, 360.0) + tube([-230.0, -80.0, 300.0], [-420.0, -130.0, 360.0], 18.0)
        axle_r = K.cylinder(12.0, 2 * (twr / 2 + 60.0), segments=16).rotate(90, 0, 0).translate(Rax[0], twr / 2 + 60.0, Rax[2])
        arm_r = tube([-420.0, -110.0, 360.0], Rax + [0, -twr / 2 - 40.0, 0], 16.0)
        hug = K.revolve([(Rr + 20.0, -45.0), (Rr + 24.0, -45.0), (Rr + 24.0, 45.0), (Rr + 20.0, 45.0)], segments=48, degrees=80.0)
        hug = hug.rotate(0, 0, -150.0).rotate(-90, 0, 0).translate(*Rax)
        b.add("engine", "Động cơ + hộp số CVT (càng sau liền khối)", "Unit-swing engine & CVT", "engine",
              [Shape(cvt + crank + piv, "cast_aluminum", 40.0), Shape(cylh, "steel_dark", 40.0), Shape(muf + arm_r + axle_r, "stainless", 40.0),
               Shape(hug, "plastic_black", 40.0)], parent_id="frame", required=True,
              aliases=["động cơ", "máy", "hộp số", "cvt", "nồi", "pô", "engine", "càng sau"],
              function="Động cơ 125 cc làm mát dung dịch + hộp số vô cấp CVT, cả cụm quay quanh trục làm càng sau.",
              position_tag="rear", joint_axis=(0, 1, 0), explode_dir=(0, 0, -1), explode_distance=0.25 * wb, explode_order=2)
        shield = K.hull([K.box(40.0, 380.0, 60.0).translate(*(H0 + [-30.0, 0, -40.0])), K.box(40.0, 420.0, 20.0).translate(200.0, 0, 390.0),
                         K.box(20.0, 300.0, 20.0).translate(*(H1 + [-40.0, 0, 30.0]))])
        shield = shield - K.hull([K.box(40.0, 300.0, 40.0).translate(*(H0 + [-80.0, 0, -40.0])), K.box(40.0, 340.0, 20.0).translate(150.0, 0, 390.0),
                                  K.box(20.0, 240.0, 20.0).translate(*(H1 + [-80.0, 0, 30.0]))])
        floor = K.rounded_box(340.0, 360.0, 30.0, 12.0, segments=8).translate(80.0, 0, 415.0)
        rear = K.loft([np.column_stack([np.full(40, x), P.superellipse(w, h, 2.6, 40)[:, 0], zc + P.superellipse(w, h, 2.6, 40)[:, 1]])
                       for x, w, h, zc in ((-150.0, 300.0, 50.0, 495.0), (-260.0, 330.0, 200.0, 580.0), (-500.0, 320.0, 150.0, 720.0),
                                           (-760.0, 240.0, 100.0, 725.0), (-820.0, 120.0, 50.0, 725.0))])
        cowl = K.rounded_box(160.0, T["bar"] * 0.62, 90.0, 30.0, segments=8).translate(*(stem_top + [-5.0, 0, 20.0]))
        lamp = K.box(20.0, 200.0, 40.0).translate(*(stem_top + [72.0, 0, 20.0]))
        tl = K.box(12.0, 160.0, 40.0).translate(-826.0, 0, 725.0)
        b.add("body_panels", "Vỏ nhựa (yếm, sàn để chân, thân sau)", "Body panels", "body_panel",
              [Shape(shield + floor + rear, "paint_primary", 40.0), Shape(tl, "led_red", 40.0)], parent_id="frame", required=True,
              aliases=["yếm", "yếm xe", "sàn để chân", "thân sau", "vỏ xe", "dè", "cốp xe", "đèn hậu", "body panel"],
              function="Yếm chắn gió trước, sàn để chân phẳng, thân sau che cốp dưới yên, đèn hậu LED.", position_tag="center",
              explode_dir=(0, 0, 1), explode_distance=0.35 * wb, explode_order=2)
        contacts += [["body_panels", "fork"], ["body_panels", "seat"]]
        b.add("headlight", "Mặt nạ ghi-đông + đèn pha", "Handlebar cowl & headlight", "headlight",
              [Shape(cowl - lamp.translate(4.0, 0, 0), "paint_primary", 40.0), Shape(lamp & cowl.translate(12.0, 0, 0), "led_white", 40.0)],
              parent_id="fork", required=True, aliases=["đèn pha", "mặt nạ", "đầu đèn", "headlight"], function="Ốp ghi-đông tích hợp đèn pha LED.",
              position_tag="front", explode_dir=(0, 0, 1), explode_distance=0.15 * wb, explode_order=1)
    else:
        down = (BB - H0) / np.linalg.norm(BB - H0)
        bc = H0 + 0.55 * np.linalg.norm(BB - H0) * down
        batt = MC.orient(K.rounded_box(80.0, 70.0, 360.0, 18.0, segments=8), bc + np.array([down[2], 0, -down[0]]) * 60.0, down)
        mnt = MC.orient(K.box(40.0, 30.0, 300.0), bc + np.array([down[2], 0, -down[0]]) * 22.0, down)
        b.add("battery", "Pin xe đạp điện 36 V", "E-bike battery", "battery", [Shape(batt, "plastic_black", 40.0), Shape(mnt, "aluminum", 40.0)],
              parent_id="frame", required=True, aliases=["pin", "ắc quy", "pin xe", "battery"], function="Pin lithium-ion 36 V 10 Ah gắn trên ống dưới, khóa tháo sạc.",
              position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.25 * wb, explode_order=1)
        ring = K.cylinder(90.0, 5.0, segments=48) - K.cylinder(60.0, 10.0, segments=32).translate(0, 0, -2.0)
        ring = ring.rotate(90, 0, 0).translate(BB[0], 72.0 + 3.0, BB[2])
        cranks, pedals = [], []
        for sy, a in ((1, 20.0), (-1, 200.0)):
            e = BB + 170.0 * np.array([math.cos(math.radians(a)), 0, -math.sin(math.radians(a))])
            cranks.append(tube(BB + [0, sy * 45.0, 0], e + [0, sy * 45.0, 0], 12.0))
            pedals.append(K.rounded_box(70.0, 95.0, 22.0, 6.0, segments=6).translate(*(e + [0, sy * 110.0, 0])) + tube(e + [0, sy * 45.0, 0], e + [0, sy * 65.0, 0], 7.0))
        spindle = tube(BB + [0, -50.0, 0], BB + [0, 50.0, 0], 10.0)
        b.add("crankset", "Đùi đĩa + bàn đạp", "Crankset & pedals", "crankset",
              [Shape(ring + K.Solid.union_all(cranks) + spindle, "aluminum", 40.0), Shape(K.Solid.union_all(pedals), "plastic_black", 40.0)],
              parent_id="frame", required=True, aliases=["đùi đĩa", "giò đạp", "bàn đạp", "đĩa xích", "pedal", "crankset"],
              function="Đùi đĩa 170 mm, đĩa 44 răng, bàn đạp nhựa; cảm biến trợ lực.", position_tag="center", joint_axis=(0, 1, 0),
              explode_dir=(0, 1, 0), explode_distance=0.2 * wb, explode_order=1)
        path, _, _ = MC.open_belt_path(38.0, 90.0, float(np.hypot(Rax[0] - BB[0], Rax[2] - BB[2])), step=4.0)
        ang = math.atan2(Rax[2] - BB[2], Rax[0] - BB[0]) + math.pi
        ca, sa = math.cos(ang), math.sin(ang)
        p3 = np.column_stack([BB[0] + path[:, 0] * ca - path[:, 1] * sa, np.full(len(path), 78.0), BB[2] + path[:, 0] * sa + path[:, 1] * ca])
        chain = K.sweep(P.rounded_rect(6.0, 8.0, 1.5, 2), np.vstack([p3, p3[:1]]))
        b.add("chain", "Xích xe đạp", "Bicycle chain", "chain", Shape(chain, "steel_dark", 40.0), parent_id="crankset", required=True,
              aliases=["xích", "sên", "chain"], function="Xích 1/2\" × 3/32\" nối đĩa trước với líp sau.", position_tag="left",
              explode_dir=(0, 1, 0), explode_distance=0.12 * wb, explode_order=1)
        contacts += [["chain", "wheel_rear"], ["chain", "frame"]]
        rack = K.Solid.union_all([tube(Rax + [40.0, sy * 75.0, 0], Rax + [60.0, sy * 75.0, Rr + 60.0], 5.0) for sy in (1, -1)]
                                 + [K.box(420.0, 150.0, 8.0).translate(Rax[0] + 40.0, 0, Rr * 2 + 64.0),
                                    tube(ST - 60.0 * st_dir, Rax + [220.0, 0, Rr + 62.0], 5.0)])
        fen_rr = K.revolve([(Rr + 18.0, -30.0), (Rr + 21.0, -30.0), (Rr + 21.0, 30.0), (Rr + 18.0, 30.0)], segments=64, degrees=150.0)
        fen_rr = fen_rr.rotate(0, 0, -165.0).rotate(-90, 0, 0).translate(*Rax)
        stand = tube(BB + [-60.0, 30.0, -10.0], BB + [-380.0, 150.0, -Rr + 110.0], 7.0)
        b.add("rack", "Baga + chắn bùn sau + chân chống", "Rear rack & mudguard", "rack",
              [Shape(rack + stand, "aluminum_dark", 40.0), Shape(fen_rr, "plastic_black", 40.0)], parent_id="frame", required=True,
              aliases=["baga", "chắn bùn", "chắn bùn sau", "chân chống", "rack"], function="Baga chở đồ, chắn bùn sau, chân chống nghiêng.",
              position_tag="rear", explode_dir=(0, 0, 1), explode_distance=0.2 * wb, explode_order=1)
        contacts.append(["rack", "wheel_rear"])

    # ---------- yên ----------
    if ebike:
        post_top = ST + 200.0 * st_dir
        post = tube(ST + 40.0 * st_dir, post_top, 13.0)
        saddle = K.loft([np.column_stack([np.full(32, x), P.superellipse(w, 50.0, 2.2, 32)[:, 0], post_top[2] + 30.0 + P.superellipse(w, 50.0, 2.2, 32)[:, 1]])
                         for x, w in ((post_top[0] + 150.0, 60.0), (post_top[0] + 60.0, 110.0), (post_top[0] - 40.0, 200.0), (post_top[0] - 110.0, 170.0))])
        seat_sh = [Shape(saddle, "leather", 40.0), Shape(post, "aluminum", 40.0)]
        z_seat = post_top[2] + 55.0
    else:
        z_seat = T["seat"]
        xs0, xs1 = (-100.0, -640.0) if moto else (-230.0, -780.0)
        z_base = 740.0 if moto else 760.0
        secs = []
        for t in np.linspace(0, 1, 8):
            x = xs0 + (xs1 - xs0) * t
            w = (240.0 if moto else 300.0) * (0.75 + 0.25 * math.sin(math.pi * min(1.0, t * 1.4)))
            ztop = z_seat - (0.0 if t < 0.55 else 40.0 * (t - 0.55) / 0.45) if moto else z_seat - 20.0 * abs(t - 0.4)
            pr = P.superellipse(w, 2 * (ztop - z_base), 3.0, 40)
            secs.append(np.column_stack([np.full(40, x), pr[:, 0], z_base + np.maximum(pr[:, 1], 0.0)]))
        seat = K.loft(secs)
        seat_sh = [Shape(seat, "leather", 40.0)]
        if moto:
            tl = K.box(12.0, 120.0, 40.0).translate(xs1 - 8.0, 0, z_base + 10.0)
            seat_sh.append(Shape(tl, "led_red", 40.0))
    b.add("seat", "Yên xe", "Seat", "seat", seat_sh, parent_id="frame", required=True, aliases=["yên", "yên xe", "seat", "đèn hậu"] if moto else ["yên", "yên xe", "seat", "cọc yên"],
          function=f"Yên cao ≈ {z_seat:.0f} mm tính từ mặt đất.", position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.25 * wb,
          explode_order=1)
    b.note_stage(1, "Tháo bánh, yên, bình xăng/pin, ống xả, xích")
    b.note_stage(2, "Tháo phuộc trước, càng sau, vỏ")
    if moto:
        b.note_stage(3, "Hạ động cơ khỏi khung")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"bike_type": typ, "wheelbase_mm": wb, "front_tire_d_mm": Df, "rear_tire_d_mm": Dr, "rake_deg": T["rake"],
                       "trail_mm": trail, "seat_height_mm": z_seat,
                       "standard": "Ký hiệu lốp ISO (110/70-17, ETRTO 40-622); hình học lái: caster, offset, trail",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
