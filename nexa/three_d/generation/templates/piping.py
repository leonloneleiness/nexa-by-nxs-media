"""Van bi tay gạt và phụ kiện đường ống DN15–DN200 (chọn chuẩn châu Âu cho mặt bích, ASME cho phụ kiện hàn).

- Đường kính ngoài ống: EN 10220 / ISO 4200 dãy 1 (trùng ASME B36.10M), dày SCH 40.
- Mặt bích: EN 1092-1 PN16 kiểu 11 (cổ hàn) — D, K, số lỗ × Ø lỗ, bu-lông, gờ nổi d1 × 2 mm.
- Co 90° bán kính dài, co 45°, tê đều: kích thước tâm–mặt ASME B16.9.
- Van bi: toàn lỗ (bore = DN), thân hai mảnh bắt bu-lông, mặt bích EN 1092-1 PN16, dài mặt–mặt ASME B16.10 Class 150
  kiểu ngắn; bi có lỗ + rãnh nhận ngàm trục, 2 vòng đệm PTFE, trục van + nắp ép gioăng, tay gạt thép bọc nhựa.
  Tay gạt dọc ống = mở, vuông góc = đóng.
Trục ống theo +X, đáy mô hình ở z = 0.
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

TO_X = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])     # revolve quanh Z → quanh X (z → x)


def rev_x(profile, segments: int = 128) -> K.Solid:
    """Khối xoay quanh trục X từ profile [(r, x), …]."""
    return K.revolve(profile, segments=segments).transform(TO_X)


def flange_holes(dn: int, x0: float, length: float) -> K.Solid:
    D, Kc, Lh, n, _M, _C2 = S.FLANGE_PN16[dn]
    return K.Solid.union_all([K.cylinder(Lh / 2, length, segments=20).transform(TO_X).translate(x0, Kc / 2 * math.cos(a), Kc / 2 * math.sin(a))
                              for a in np.radians(np.arange(n) * 360.0 / n + 180.0 / n)])


def _weld_bead(od: float, wall: float, x: float, axis: str = "x") -> K.Solid:
    tor = K.torus(od / 2 + 0.05 * wall, 0.55 * wall + 0.4, segments=96, tube_segments=12)
    return tor.transform(TO_X).translate(x, 0, 0) if axis == "x" else tor


# ================================================================== van bi
def build_valve(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    dn = int(p.get("dn", 50))
    closed = p.get("state", "open") == "closed"
    D, Kc, Lh, n, M, C2 = S.FLANGE_PN16[dn]
    d1, f1 = S.FLANGE_RF[dn], 2.0
    ftf = S.VALVE_FTF[dn]
    od = S.PIPE_OD[dn]
    rb = dn / 2                                        # toàn lỗ
    Rb = 0.7 * dn + 3                                  # bán kính bi
    wall = 0.12 * dn + 4
    Rbody = Rb + 0.8 + wall
    xs = Rb * 0.42                                     # mặt ghép thân – nắp đầu
    mats = MC.tech_materials(spec)
    mat = "stainless" if p.get("material") == "stainless" else "cast_iron"
    b = AssemblyBuilder(spec.name or f"Van bi DN{dn}", "ball_valve", mats)
    xa, xb = -ftf / 2, ftf / 2
    r_neck = od / 2 + 0.05 * dn + 3
    rj = Rbody + 0.06 * dn + 6                         # vòng bu-lông ghép thân
    nj = 4 if dn <= 50 else 8
    mj = 8.0 if dn <= 40 else 10.0 if dn <= 80 else 12.0 if dn <= 125 else 16.0
    col_r = rj + 1.3 * mj + 2
    tj = max(8.0, 0.6 * mj + 3)
    # thân: mặt bích A + cổ + vỏ cầu + vành ghép (x ≤ xs)
    prof_a = [(rb - 0.1, xa), (d1 / 2, xa), (d1 / 2, xa + f1), (D / 2, xa + f1), (D / 2, xa + f1 + C2),
              (r_neck, xa + f1 + C2 + 3), (Rbody, -Rb * 0.55), (Rbody, xs - tj), (col_r, xs - tj), (col_r, xs), (rb - 0.1, xs)]
    body = rev_x(P.fillet_polygon(prof_a, [0, 0.3, 0.3, 0.8, 0.8, 4, 0.12 * dn + 3, 2, 1.0, 0.6, 0], 4))
    prof_b = [(rb - 0.1, xs), (col_r, xs), (col_r, xs + tj), (Rbody * 0.93, xs + tj + 2), (r_neck, xb - f1 - C2 - 3),
              (D / 2, xb - f1 - C2), (D / 2, xb - f1), (d1 / 2, xb - f1), (d1 / 2, xb), (rb - 0.1, xb)]
    tail = rev_x(P.fillet_polygon(prof_b, [0, 0.6, 1.0, 3, 4, 0.8, 0.8, 0.3, 0.3, 0], 4))
    cavity = K.sphere(Rb + 0.8, 96)
    bore = K.cylinder(rb, ftf + 10, segments=96).transform(TO_X).translate(xa - 5, 0, 0)
    body, tail = body - cavity - bore, tail - cavity - bore
    body = body - flange_holes(dn, xa - 1, f1 + C2 + 2)
    tail = tail - flange_holes(dn, xb - f1 - C2 - 1, f1 + C2 + 2)
    # cổ trục van (neck) trên thân — cao đủ để tay gạt vượt qua mặt bích
    r_st = 0.1 * dn + 4
    z_neck = max(Rbody + 0.3 * dn + 12, D / 2 + 10)
    neck = K.cylinder(r_st + 0.08 * dn + 6, z_neck, segments=64)
    pad = K.chamfer_box(2.6 * (r_st + 0.08 * dn + 6), 2.6 * (r_st + 0.08 * dn + 6), 4.0, 1.0).translate(0, 0, z_neck - 2)
    body = body + ((neck + pad) - cavity)
    body = body - K.cylinder(r_st, z_neck + 10, segments=48)
    # bi (lỗ theo X khi mở, theo Y khi đóng) + rãnh ngàm
    tang_w, tang_d = 0.75 * r_st, 0.35 * Rb
    ball = K.sphere(Rb, 96) - K.cylinder(rb, 4 * Rb, segments=96).transform(TO_X).translate(-2 * Rb, 0, 0)
    slot = K.box(tang_w * 2.2, tang_w, tang_d + 1).translate(0, 0, Rb - tang_d / 2 + 0.5)
    ball = ball - slot
    if closed:
        ball = ball.rotate(0, 0, 90)
    # đệm PTFE hai bên bi — bề mặt cầu ôm bi, lắp vào hốc trên thân/nắp đầu
    r_s1, r_s2 = rb + 0.6, rb + 0.16 * dn + 2
    rm = (r_s1 + r_s2) / 2
    xc = math.sqrt(max(Rb * Rb - rm * rm, 1.0))
    seats = []
    for sgn in (-1, 1):
        ring = rev_x([(r_s1, 0), (r_s2, 0), (r_s2, 0.14 * dn + 4), (r_s1, 0.14 * dn + 4)], 96)
        ring = ring.translate(xc - 0.07 * dn - 2, 0, 0) if sgn > 0 else ring.mirror((1, 0, 0)).translate(-(xc - 0.07 * dn - 2), 0, 0)
        seats.append(ring - K.sphere(Rb, 96))
    b.add("body", "Thân van", "Valve body", "valve_body", Shape(body, mat, 60.0), required=True,
          aliases=["thân van", "vỏ van", "body", "mặt bích van", "cổ van"],
          function=f"Thân van đúc, mặt bích EN 1092-1 PN16 DN{dn} (Ø{D:g}, {n} lỗ Ø{Lh:g} trên vòng Ø{Kc:g}).",
          position_tag="center", dimensions={"dn": dn, "face_to_face": ftf, "flange_d": D})
    b.add("end_cap", "Nắp đầu van (mảnh thứ hai)", "End piece", "valve_body", Shape(tail, mat, 60.0), parent_id="body",
          required=True, aliases=["nắp đầu", "đầu van", "end cap", "mảnh thân thứ hai"],
          function="Mảnh thân thứ hai bắt bu-lông vào thân, giữ bi và đệm.", position_tag="right",
          explode_dir=(1, 0, 0), explode_distance=0.6 * ftf + 20, explode_order=2)
    b.add("ball", "Bi van", "Ball", "valve_ball", Shape(ball, "chrome", 40.0), parent_id="body", required=True,
          aliases=["bi", "bi van", "quả cầu", "ball"],
          function=f"Bi Ø{2 * Rb:.0f} mm mạ crôm, lỗ toàn phần Ø{dn:g} — xoay 90° để đóng/mở.", position_tag="center",
          joint_axis=(0, 0, 1), explode_dir=(1, 0, 0), explode_distance=0.35 * ftf + 15, explode_order=3)
    for k, s_ in enumerate(seats):
        par = "body" if k == 0 else "end_cap"
        b.add(f"seat_{k + 1}", f"Đệm PTFE {'trái' if k == 0 else 'phải'}", "PTFE seat", "seal", Shape(s_, "ptfe", 40.0),
              parent_id=par, aliases=["đệm", "gioăng", "đệm ptfe", "seat", "vòng làm kín"],
              function="Vòng đệm PTFE ôm bi, làm kín dòng chảy.", position_tag="left" if k == 0 else "right",
              explode_dir=(1, 0, 0) if k else (-1, 0, 0), explode_distance=0.2 * ftf + 10, explode_order=4)
        b.cut(par, s_)
    # trục van: ngàm dưới lọt rãnh bi, lục giác/vát phẳng trên để lắp tay gạt, ren + đai ốc
    z_tang = Rb - tang_d
    z_c0 = Rb + 0.8                                    # đỉnh hốc bi
    stem = K.cylinder(r_st, z_neck + 12 - z_c0, segments=48).translate(0, 0, z_c0)
    tang = K.box(tang_w * 2.2 - 0.1, tang_w - 0.1, z_c0 - z_tang + 0.01).translate(0, 0, (z_tang + z_c0) / 2)
    tang = tang & K.sphere(Rb - 0.05, 96)
    flats = K.box(2 * r_st * 0.72, 4 * r_st, 12).translate(0, 0, z_neck + 6)
    stem = stem - (K.cylinder(r_st + 1, 12, segments=48).translate(0, 0, z_neck) - flats)
    if closed:
        tang = tang.rotate(0, 0, 90)
    stem_top = z_neck + 12
    thread = K.cylinder(r_st * 0.62, 8, segments=32).translate(0, 0, stem_top - 0.01)
    b.add("stem", "Trục van", "Stem", "shaft", [Shape(stem + tang + thread, "stainless", 40.0)], parent_id="body", required=True,
          aliases=["trục van", "cần van", "ty van", "stem"], function="Trục truyền mômen từ tay gạt tới bi (ngàm dẹt).",
          position_tag="top", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=z_neck + 30, explode_order=2)
    b.cut("ball", tang)
    gland = MC._hex_chamfered(2 * r_st + 0.06 * dn + 8, 6.0, both=True).translate(0, 0, z_neck + 2.0) - \
        K.cylinder(r_st, 20, segments=48).translate(0, 0, z_neck)
    b.cut("body", K.cylinder(r_st + 0.06 * dn + 5, 2.01, segments=48).translate(0, 0, z_neck))
    gland = gland + (K.cylinder(r_st + 0.06 * dn + 5, 2.0, segments=48) - K.cylinder(r_st, 3, segments=48).translate(0, 0, -0.5)).translate(0, 0, z_neck)
    b.add("gland_nut", "Nắp ép gioăng", "Gland nut", "nut", Shape(gland, "brass", 40.0), parent_id="body",
          aliases=["nắp ép gioăng", "đai ốc ép tết", "gland", "gioăng trục"],
          function="Ép vòng tết làm kín quanh trục van.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=z_neck * 0.6 + 20, explode_order=1)
    # tay gạt
    Lh_ = max(1.05 * ftf, 140.0 + 0.4 * dn)
    th, wh = 0.05 * dn + 3.0, 0.14 * dn + 14
    z_h = z_neck + 8.0 + 0.5
    lever = K.rounded_box(Lh_ + wh, wh, th, min(th * 0.45, wh * 0.4)).translate((Lh_ + wh) / 2 - wh / 2, 0, z_h + th / 2)
    lever = lever - K.box(2 * r_st * 0.72 + 0.02, 2 * r_st + 0.02, th * 3).translate(0, 0, z_h)
    lever = lever & K.cylinder(4 * Lh_, th + 1, segments=8).translate(0, 0, z_h - 0.5)
    grip = K.rounded_box(Lh_ * 0.45, wh + 3, th + 3, (th + 3) * 0.45).translate(Lh_ * 0.75, 0, z_h + th / 2)
    hnut = MC.hex_nut(r_st * 1.24).translate(0, 0, z_h + th)
    rot = 90.0 if closed else 0.0
    b.add("handle", "Tay gạt", "Lever handle", "handle",
          [Shape(lever.rotate(0, 0, rot), "steel_zinc", 40.0), Shape(grip.rotate(0, 0, rot), "paint_red", 40.0),
           Shape(hnut, "steel_zinc", 40.0)], parent_id="stem", required=True,
          aliases=["tay gạt", "tay van", "cần gạt", "handle", "lever"],
          function="Tay gạt: song song ống = mở, vuông góc ống = đóng.", position_tag="top", joint_axis=(0, 0, 1),
          explode_dir=(0, 0, 1), explode_distance=z_neck * 0.5 + 40, explode_order=1)
    # bu-lông ghép thân – nắp đầu
    pts = [(xs + tj, rj * math.cos(a), rj * math.sin(a)) for a in np.radians(np.arange(nj) * 360.0 / nj + 180.0 / nj)]
    bolts, nuts, cores = MC.bolt_joint(pts, (1, 0, 0), mj, 2 * tj)
    b.cut("body", cores)
    b.cut("end_cap", cores)
    b.add("body_bolts", "Bu-lông ghép thân", "Body bolts", "fastener",
          [Shape(bolts, "steel_zinc", 40.0), Shape(nuts, "steel_zinc", 40.0)], parent_id="end_cap", required=True,
          aliases=["bu lông", "bulong", "bu-lông thân", "ốc", "bolts"], function=f"{nj} bu-lông M{mj:g} ép hai mảnh thân.",
          position_tag="center", explode_dir=(1, 0, 0), explode_distance=0.4 * ftf + 30, explode_order=1)
    b.note_stage(1, "Tháo tay gạt, nắp ép gioăng, bu-lông ghép thân")
    b.note_stage(2, "Tháo nắp đầu van, rút trục van")
    b.note_stage(3, "Lấy bi ra")
    b.note_stage(4, "Tháo đệm PTFE")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"dn": dn, "face_to_face_mm": ftf, "flange": "EN 1092-1 PN16", "flange_d_mm": D, "bolt_circle_mm": Kc,
                       "bolt_holes": n, "state": "closed" if closed else "open",
                       "standard": "EN 1092-1 PN16 (mặt bích), ASME B16.10 Class 150 kiểu ngắn (dài mặt–mặt)",
                       "strict_overlap": True,
                       "contacts": [["seat_*", "ball"], ["stem", "ball"], ["body_bolts", "body"], ["gland_nut", "stem"],
                                    ["ball", "body"], ["seat_2", "body"], ["seat_1", "end_cap"]]})
    return b.build()


# ================================================================== phụ kiện đường ống
def build_fitting(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    dn = int(p.get("dn", 50))
    kind = p.get("fitting", "elbow90")
    od, wall = S.PIPE_OD[dn], S.PIPE_WALL[dn]
    mats = MC.tech_materials(spec)
    mat = "stainless" if p.get("material") == "stainless" else "steel_dark"
    names = {"elbow90": "Co 90°", "elbow45": "Co 45°", "tee": "Tê đều", "flange_joint": "Mối nối mặt bích"}
    b = AssemblyBuilder(spec.name or f"{names[kind]} DN{dn}", "pipe_fitting", mats)
    stubs = p.get("pipe_stubs", True)
    ls = max(1.0 * od, 60.0)
    contacts: list[list[str]] = []

    def stub(pid: str, start: np.ndarray, direction: np.ndarray, parent: str, label: str) -> None:
        d_ = np.asarray(direction, float) / np.linalg.norm(direction)
        tube = MC.pipe(od, wall, ls)                               # dọc +X từ 0
        bead = _weld_bead(od, wall, 0.0)
        mtx = np.eye(4)
        rot = K.align_matrix((1, 0, 0), d_)
        mtx[:3, :3] = rot
        mtx[:3, 3] = start
        b.add(pid, f"Đoạn ống {label}", f"Pipe stub {label}", "pipe",
              [Shape(tube.transform(mtx), mat, 60.0), Shape(bead.transform(mtx), "steel_dark", 60.0)], parent_id=parent,
              aliases=["ống", "đoạn ống", "ống thép", "pipe", "mối hàn"],
              function=f"Ống OD {od:g} × {wall:g} mm (SCH 40) hàn đối đầu.", position_tag=label,
              explode_dir=tuple(d_), explode_distance=0.6 * ls, explode_order=1)

    if kind in ("elbow90", "elbow45"):
        ang = 90.0 if kind == "elbow90" else 45.0
        Rr = S.elbow90_a(dn) if kind == "elbow90" else S.ELBOW45_B[dn] / math.tan(math.radians(22.5))
        el = MC.bend(od, wall, Rr, ang, segments=64)
        b.add("fitting", names[kind], "Elbow", "fitting", Shape(el, mat, 60.0), required=True,
              aliases=["co", "cút", "co hàn", "elbow", "cút hàn"],
              function=f"{names[kind]} hàn đối đầu bán kính dài R = {Rr:.1f} mm (ASME B16.9).", position_tag="center",
              dimensions={"od": od, "radius": Rr})
        if stubs:
            stub("pipe_in", np.array([0.0, 0, 0]), np.array([-1.0, 0, 0]), "fitting", "vào")
            a = math.radians(ang)
            end = np.array([Rr * math.sin(a), Rr * (1 - math.cos(a)), 0.0])
            stub("pipe_out", end, np.array([math.cos(a), math.sin(a), 0.0]), "fitting", "ra")
        meta = {"center_to_end_mm": S.elbow90_a(dn) if kind == "elbow90" else S.ELBOW45_B[dn], "bend_radius_mm": Rr}
    elif kind == "tee":
        C = S.TEE_C[dn]
        run_o = K.cylinder(od / 2, 2 * C, segments=96).transform(TO_X).translate(-C, 0, 0)
        br_o = K.cylinder(od / 2, C, segments=96).rotate(-90, 0, 0)
        big = 4 * C + 2 * od
        crotch = K.sphere(od / 2 * 1.06, 64) & K.box(big, big, big).translate(0, big / 2, 0)
        run_i = K.cylinder(od / 2 - wall, 2 * C + 2, segments=96).transform(TO_X).translate(-C - 1, 0, 0)
        br_i = K.cylinder(od / 2 - wall, C + 1, segments=96).rotate(-90, 0, 0)
        tee = K.Solid.union_all([run_o, br_o, crotch])
        tee = tee - run_i - br_i
        b.add("fitting", names[kind], "Equal tee", "fitting", Shape(tee, mat, 60.0), required=True,
              aliases=["tê", "tê đều", "tee", "ba chạc"],
              function=f"Tê đều hàn đối đầu, tâm–mặt C = {C:g} mm (ASME B16.9).", position_tag="center",
              dimensions={"od": od, "center_to_end": C})
        if stubs:
            stub("pipe_in", np.array([-C, 0, 0]), np.array([-1.0, 0, 0]), "fitting", "vào")
            stub("pipe_out", np.array([C, 0, 0]), np.array([1.0, 0, 0]), "fitting", "ra")
            stub("pipe_branch", np.array([0, C, 0]), np.array([0, 1.0, 0]), "fitting", "nhánh")
        meta = {"center_to_end_mm": C}
    else:                                                               # mối nối mặt bích
        D, Kc, Lh, n, M, C2 = S.FLANGE_PN16[dn]
        g = 2.0
        fl, info = MC.weld_neck_flange(dn)
        fa = fl.mirror((1, 0, 0)).translate(-g / 2, 0, 0)
        fb = fl.translate(g / 2, 0, 0)
        H = info["H"]
        b.add("flange_a", "Mặt bích A", "Flange A", "flange", Shape(fa, mat, 60.0), required=True,
              aliases=["mặt bích", "mặt bích a", "flange", "bích"],
              function=f"Mặt bích cổ hàn EN 1092-1 PN16 DN{dn}: Ø{D:g}, {n} lỗ Ø{Lh:g} trên Ø{Kc:g}.", position_tag="left",
              dimensions={"D": D, "K": Kc, "holes": n})
        b.add("flange_b", "Mặt bích B", "Flange B", "flange", Shape(fb, mat, 60.0), parent_id="flange_a", required=True,
              aliases=["mặt bích", "mặt bích b", "flange", "bích"], function="Mặt bích đối diện.", position_tag="right",
              explode_dir=(1, 0, 0), explode_distance=0.5 * H + 40, explode_order=3)
        gasket = rev_x([(od / 2 - wall, -g / 2), (info["d1"] / 2, -g / 2), (info["d1"] / 2, g / 2), (od / 2 - wall, g / 2)], 128)
        b.add("gasket", "Gioăng làm kín", "Gasket", "seal", Shape(gasket, "nbr", 60.0), parent_id="flange_a", required=True,
              aliases=["gioăng", "ron", "đệm làm kín", "gasket"], function="Gioăng phẳng ép giữa hai mặt gờ nổi.",
              position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.9 * D, explode_order=4)
        grip = 2 * (info["f1"] + C2) + g
        x_back = -(g / 2 + info["f1"] + C2)
        pts = [(x_back, Kc / 2 * math.cos(a), Kc / 2 * math.sin(a)) for a in np.radians(np.arange(n) * 360.0 / n + 180.0 / n)]
        bolts, nuts, _cores = MC.bolt_joint(pts, (-1, 0, 0), M, grip)
        b.add("bolts", f"{n} bu-lông M{M}", "Bolts", "fastener", Shape(bolts, "steel_zinc", 50.0), parent_id="flange_a", required=True,
              aliases=["bu lông", "bulong", "bu-lông mặt bích", "bolts"], function=f"{n} bu-lông M{M} (EN 1092-1 PN16).",
              position_tag="left", explode_dir=(-1, 0, 0), explode_distance=0.5 * H + 60, explode_order=2)
        b.add("nuts", "Đai ốc + vòng đệm", "Nuts & washers", "nut", Shape(nuts, "steel_zinc", 50.0), parent_id="flange_b", required=True,
              aliases=["đai ốc", "ê cu", "vòng đệm", "nuts"], function="Đai ốc + vòng đệm siết mặt bích.", position_tag="right",
              explode_dir=(1, 0, 0), explode_distance=40, explode_order=1)
        contacts += [["bolts", "flange_*"], ["nuts", "bolts"], ["gasket", "flange_b"]]
        if stubs:
            stub("pipe_in", np.array([-(g / 2 + H), 0, 0]), np.array([-1.0, 0, 0]), "flange_a", "vào")
            stub("pipe_out", np.array([g / 2 + H, 0, 0]), np.array([1.0, 0, 0]), "flange_b", "ra")
        meta = {"flange_d_mm": D, "bolt_circle_mm": Kc, "bolt_holes": n, "bolt": f"M{M}"}
    b.note_stage(1, "Cắt/tháo đoạn ống, đai ốc")
    b.note_stage(2, "Rút bu-lông")
    b.note_stage(3, "Tách mặt bích")
    b.note_stage(4, "Lấy gioăng")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"dn": dn, "fitting": kind, "pipe_od_mm": od, "wall_mm": wall,
                       "standard": "EN 10220/ISO 4200 (ống), ASME B16.9 (phụ kiện hàn), EN 1092-1 PN16 (mặt bích)",
                       "strict_overlap": True, "contacts": contacts, **meta})
    return b.build()


def build(spec: ModelSpec) -> BuiltAssembly:
    return build_valve(spec) if spec.category == "ball_valve" else build_fitting(spec)
