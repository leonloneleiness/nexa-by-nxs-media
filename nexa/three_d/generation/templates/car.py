"""Ô tô điện (sedan / SUV / hatchback) — thân vỏ liền khối rỗng (unibody), sàn pin, motor đặt ngang trên trục.

- Thân: loft các mặt cắt ngang dọc trục X (mũi +X); mỗi mặt cắt = thân dưới + nhà kính (greenhouse) hẹp dần lên mái
  (tumblehome), bo góc bằng cắt góc Chaikin (không vọt lố). Vỏ dày 22 mm = loft ngoài − loft trong (tính giải tích).
- Hốc bánh khoét sâu + ốp lòng dè; kính chắn gió / kính sau / mái kính / kính cửa là lớp vỏ trong suốt (mỏng, không mặt trùng);
  đèn LED là lớp da mỏng trong hốc lõm (không nhiễu sọc).
- 4 cửa tách rời (khe 4 mm, bản lề ăn vào thân), tay nắm âm, gương chiếu hậu; nắp capô, nắp cốp / cửa hậu.
- Bánh: lốp theo ký hiệu ISO (vd. 235/45R18 → Ø669 mm), la-zăng, đĩa phanh + heo phanh; hệ treo mỗi bánh: cam lái,
  càng A dưới, giảm chấn + lò xo lên tháp trong hốc bánh; khung phụ trước/sau.
- Pin sàn (skateboard) giữa hai trục, motor + hộp số một cấp đồng trục bánh, bán trục; cầu sau (RWD) hoặc hai motor (AWD).
Tỷ lệ tham khảo: sedan ~ Tesla Model 3 / VinFast VF 6–7 (dài 4,7 m, cơ sở 2,88 m).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import details as D
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# tỷ lệ theo chiều dài L; lốp (bề rộng, tỷ lệ thành, vành inch); mốc u: chân kính trước, đầu mái, cuối mái, đầu cốp
TYPES = {
    "sedan": dict(W=0.394, H=0.305, wb=0.612, fo=0.19, tire=(235, 45, 18), clr=140.0, u=(0.28, 0.45, 0.66, 0.82),
                  top=[(0, .50), (.02, .58), (.06, .63), (.28, .68), (.45, 1.0), (.56, 1.0), (.66, .97), (.82, .72), (.95, .71),
                       (.99, .64), (1.0, .52)]),
    "suv": dict(W=0.413, H=0.359, wb=0.609, fo=0.19, tire=(255, 50, 19), clr=190.0, u=(0.25, 0.40, 0.88, 0.97),
                top=[(0, .55), (.02, .63), (.07, .69), (.25, .73), (.40, 1.0), (.64, 1.0), (.88, .98), (.97, .84), (.995, .72),
                     (1.0, .60)]),
    "hatchback": dict(W=0.437, H=0.361, wb=0.634, fo=0.2, tire=(215, 55, 17), clr=150.0, u=(0.27, 0.43, 0.82, 0.96),
                      top=[(0, .52), (.02, .60), (.07, .66), (.27, .70), (.43, 1.0), (.62, 1.0), (.82, .97), (.96, .78), (.995, .68),
                           (1.0, .56)]),
}
T_SH = 22.0                                                          # chiều dày vỏ thân (mm)


def chaikin(pts: np.ndarray, iters: int = 3, closed: bool = True) -> np.ndarray:
    """Bo góc bằng cắt góc Chaikin: số điểm cố định (×2 mỗi lần), luôn nằm trong bao lồi (không vọt lố như spline)."""
    p = np.asarray(pts, float)
    for _ in range(iters):
        q = np.roll(p, -1, axis=0) if closed else p[1:]
        a = p if closed else p[:-1]
        new = np.empty((2 * len(a), p.shape[1]))
        new[0::2] = 0.75 * a + 0.25 * q
        new[1::2] = 0.25 * a + 0.75 * q
        p = new if closed else np.vstack([p[:1], new, p[-1:]])
    return p


def tire_size(tw: float, ar: float, rim_in: float) -> float:
    """Đường kính ngoài lốp theo ký hiệu ISO: Ø = vành × 25,4 + 2 × bề rộng × tỷ lệ thành."""
    return rim_in * 25.4 + 2 * tw * ar / 100.0


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    typ = p.get("body_type", "sedan")
    T = TYPES[typ]
    L = float(p["length_mm"])
    W, H = T["W"] * L, T["H"] * L
    W = min(max(W, 1550.0), 2050.0)
    H = max(H, 1400.0)                                                # xe ngắn (cỡ A, vd. VF 3 dài 3,19 m) vẫn cao ≥ 1,4 m
    wb, fo = T["wb"] * L, T["fo"] * L
    tw, ar, rim_in = T["tire"]
    Dt = tire_size(tw, ar, rim_in)
    R = Dt / 2
    clr = T["clr"]
    track = 0.86 * W
    y_c = track / 2
    u_ws0, u_r0, u_r1, u_t = T["u"]
    awd = p.get("drive", "rwd") == "awd"
    mats = MC.tech_materials(spec, primary="#1f3b73", secondary="#15171a", accent="#d7263d")
    mats["leather"] = M.material("leather", "plastic", "#2a2b2e", 0.0, 0.62, name="Da bọc ghế")
    b = AssemblyBuilder(spec.name or {"sedan": "Ô tô điện sedan", "suv": "Ô tô điện SUV", "hatchback": "Ô tô điện hatchback"}[typ],
                        "car", mats)
    x_of = lambda u: L / 2 - u * L                                   # noqa: E731
    x_f = L / 2 - fo
    x_r = x_f - wb
    Ra = R + 45.0                                                     # bán kính hốc bánh

    # ---------- đường bao ----------
    tp = chaikin(np.array(T["top"], float), 3, closed=False)
    top = lambda u: float(np.interp(u, tp[:, 0], tp[:, 1])) * H       # noqa: E731
    belt = lambda u: H * (0.66 + (0.04 if typ == "suv" else 0.05) * u)  # noqa: E731

    def bottom(u: float) -> float:
        ramp = max(0.0, 1 - u / 0.07) ** 1.5 + max(0.0, (u - 0.93) / 0.07) ** 1.5
        return clr + (0.22 * H - clr) * ramp

    def width(u: float) -> float:
        if u < 0.5:
            return W * (0.88 + 0.12 * math.sin(math.pi / 2 * min(u / 0.2, 1.0)))
        return W * (0.92 + 0.08 * math.sin(math.pi / 2 * min((1 - u) / 0.15, 1.0)))

    def section(u: float, inset: float, x: float) -> np.ndarray:
        w, zb, zt = width(u), bottom(u), top(u)
        f = 1.0
        if u < 0.02:
            f = 0.8 + 0.2 * math.sqrt(max(0.0, 1 - (1 - u / 0.02) ** 2))
        elif u > 0.985:
            f = 0.8 + 0.2 * math.sqrt(max(0.0, 1 - (1 - (1 - u) / 0.015) ** 2))
        zc = (zb + zt) / 2
        zb, zt = zc - (zc - zb) * f, zc + (zt - zc) * f
        w *= f
        zbe = min(belt(u), zt - 0.03 * H)
        gh = min(1.0, max(0.0, (zt - zbe) / (0.12 * H)))
        w_top = w * (0.9 - 0.1 * gh)
        zs = max(zbe - 0.1 * H, zb + 0.12 * H)
        w, zb, zt, w_top = w - 2 * inset, zb + inset, zt - inset, w_top - 2 * inset
        half = [(0.0, zb), (0.40 * w, zb), (0.485 * w, zb + 0.07 * H), (0.5 * w, zs), (0.49 * w, zbe),
                (0.49 * w * 0.3 + 0.5 * w_top * 0.7, zbe + 0.6 * (zt - zbe)), (0.5 * w_top - 0.035 * W, zt), (0.0, zt)]
        ring = half + [(-y, z) for y, z in half[-2:0:-1]]
        pts = chaikin(np.array(ring), 3)
        return np.column_stack([np.full(len(pts), x), pts[:, 0], pts[:, 1]])

    us = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, 46))
    outer = K.loft([section(u, 0.0, x_of(u)) for u in us])
    inner = K.loft([section(u, T_SH, (L / 2 - T_SH) - u * (L - 2 * T_SH)) for u in us])
    body = outer - inner

    # ---------- hốc bánh + ốp lòng dè ----------
    y_well = y_c - tw / 2 - 170.0
    wells, liners = [], []
    for xw in (x_f, x_r):
        for sy in (1, -1):
            cyl = K.cylinder(Ra, W, segments=72).rotate(-90, 0, 0).translate(xw, y_well, R)
            ring = (K.cylinder(Ra + T_SH, W, segments=72) - K.cylinder(Ra, W + 2, segments=72).translate(0, 0, -1)).rotate(-90, 0, 0).translate(xw, y_well, R)
            if sy < 0:
                cyl, ring = cyl.mirror((0, 1, 0)), ring.mirror((0, 1, 0))
            wells.append(cyl)
            liners.append(ring)
    body = body - K.Solid.union_all(wells)
    liner = K.Solid.union_all(liners) & outer
    # ---------- hốc pin dưới sàn ----------
    hb = max(0.085 * H + 10.0, 125.0)                                 # chiều dày pin (≥ 125 mm: cell + khay làm mát)
    bx0, bx1 = x_r + Ra + 80.0, x_f - Ra - 80.0
    by = W / 2 - 100.0
    pocket = K.box(bx1 - bx0, 2 * by, clr + hb + 10.0).translate((bx0 + bx1) / 2, 0, (clr + hb + 10.0) / 2 - 10.0)
    body = body - pocket
    floor = (K.box(bx1 - bx0, 2 * by, 15.0).translate((bx0 + bx1) / 2, 0, clr + hb + 7.5)) & inner

    # ---------- vùng kính / cửa / nắp ----------
    u_b = u_r0 + 0.38 * (u_r1 - u_r0)
    x_b = x_of(u_b)                                                   # trụ B
    w_top_mid = width(0.5) * 0.8
    y_split = 0.5 * w_top_mid - 40.0
    z_bm = belt(0.5)
    zt_max = H
    x_fd = min(x_of(u_ws0 + 0.02), x_f - Ra - 60.0)                    # mép trước cửa trước (sau hốc bánh trước)
    x_c = x_r + Ra + 60.0                                             # mép sau cửa sau (trước hốc bánh sau)
    z_db = clr + 0.12 * H + 40.0                                      # đáy cửa (trên bậu cửa)
    z_dt = zt_max - 70.0
    g = 4.0

    def xbox(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> K.Solid:
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        z0, z1 = sorted((z0, z1))
        return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)

    ws_box = xbox(x_of(u_ws0 + 0.01), x_of(u_r0 - 0.004), -(y_split - 20), y_split - 20, belt(u_ws0) + 20.0, zt_max + 50)
    roof_box = xbox(x_of(u_r0 + 0.02), x_of(u_r1 - 0.03), -(y_split - 110), y_split - 110, H - 80.0, zt_max + 50)
    sedan = typ == "sedan"
    rear_box = (xbox(x_of(u_r1 + 0.006), x_of(u_t - 0.01), -(y_split - 30), y_split - 30, belt(u_t) + 30.0, zt_max + 50) if sedan else
                xbox(x_of(u_r1 + 0.012), x_of(u_t + 0.006), -(y_split - 50), y_split - 50, belt(u_t) + 30.0, zt_max + 50))
    doors = [("front", x_b - 0.5 * g, x_fd), ("rear", x_c, x_b + 0.5 * g)]
    door_boxes, door_full = {}, []
    for pos, xa, xb_ in doors:
        for side, sy in (("left", 1), ("right", -1)):
            full = xbox(xa - 0.5 * g, xb_ + 0.5 * g, sy * y_split, sy * (W + 100), z_db - 0.5 * g, z_dt + 0.5 * g)
            door_full.append(full)
            door_boxes[(pos, side)] = (xbox(xa + 0.5 * g, xb_ - 0.5 * g, sy * y_split, sy * (W + 100), z_db + 0.5 * g, z_dt - 0.5 * g), xa, xb_, sy)
    hood_full = xbox(x_of(u_ws0 - 0.004), x_of(0.06), -0.42 * W, 0.42 * W, 0.56 * H, zt_max)
    hood_in = xbox(x_of(u_ws0 - 0.004) + g, x_of(0.06) - g, -0.42 * W + g, 0.42 * W - g, 0.56 * H, zt_max)
    if sedan:
        tg_full = xbox(x_of(u_t + 0.004), x_of(0.985), -0.42 * W, 0.42 * W, 0.62 * H, zt_max)
        tg_in = xbox(x_of(u_t + 0.004) - g, x_of(0.985) + g, -0.42 * W + g, 0.42 * W - g, 0.62 * H, zt_max)
    else:
        tg_full = xbox(x_of(u_r1 + 0.004), -L, -0.42 * W, 0.42 * W, 0.58 * H, zt_max + 50)
        tg_in = xbox(x_of(u_r1 + 0.004) - g, -L, -0.42 * W + g, 0.42 * W - g, 0.58 * H + g, zt_max + 50)

    # ---------- đèn: lớp da mỏng trong hốc lõm ----------
    lamps_f = K.Solid.union_all([xbox(L / 2 + 50, x_of(0.045), sy * 0.22 * W, sy * 0.48 * W, 0.535 * H, 0.585 * H) for sy in (1, -1)])
    lamp_r = xbox(-L / 2 - 50, x_of(0.99), -0.47 * W, 0.47 * W, 0.51 * H, 0.555 * H)
    head = (lamps_f & outer) - outer.translate(-8.0, 0, 0)
    tail = (lamp_r & outer) - outer.translate(8.0, 0, 0)
    body = body - (lamps_f - outer.translate(-25.0, 0, 0)) - (lamp_r - outer.translate(25.0, 0, 0))
    body = body + liner

    # ---------- tách bộ phận ----------
    # kính hông sau (sau cửa sau, trước trụ C/D) — SUV/hatchback có ô kính cố định
    x_q1 = x_of(u_r1 - 0.03) if not sedan else x_of(u_r1 - 0.015)
    fixed = ws_box + roof_box + (rear_box if sedan else K.box(1, 1, 1).translate(0, 0, -1e5))
    if x_c - 60.0 - x_q1 > 150.0:
        fixed = fixed + K.Solid.union_all([xbox(x_q1, x_c - 60.0, sy * y_split, sy * (W + 100), z_bm + 30.0, z_dt - 40.0) for sy in (1, -1)])
    glass_fix = body & fixed
    door_solids = {k: body & v[0] for k, v in door_boxes.items()}
    hood = body & hood_in
    tg = body & tg_in
    cut_all = fixed + K.Solid.union_all(door_full) + hood_full + tg_full
    body = body - cut_all
    plates = []
    for sx in (1, -1):                                               # biển số trước/sau
        xs = D.surface_at(outer, "x", (0, 0, 0.42 * H if sx > 0 else 0.46 * H), positive=sx > 0)
        if xs is not None:
            plates.append(K.rounded_box(10.0, 520.0, 110.0, 4.0, segments=6).translate(xs + sx * 3.0, 0, 0.42 * H if sx > 0 else 0.46 * H))
    body_shapes = [Shape(body, "paint_primary", 40.0), Shape(glass_fix, "glass_tinted", 40.0), Shape(head, "led_white", 40.0),
                   Shape(tail, "led_red", 40.0), Shape(floor, "plastic_black", 40.0)]
    if plates:
        body_shapes.append(Shape(K.Solid.union_all(plates), "label_white", 40.0))
    b.add("body", "Thân vỏ xe (unibody)", "Body-in-white", "car_body", body_shapes, required=True,
          aliases=["thân xe", "vỏ xe", "khung xe", "body", "kính chắn gió", "đèn pha", "đèn hậu", "mái kính", "sàn xe"],
          function="Thân vỏ liền khối rỗng: trụ A/B/C, hốc bánh + ốp lòng dè, kính chắn gió, mái kính, đèn LED trước/sau.",
          position_tag="center", dimensions={"length": L, "width": W, "height": H, "wheelbase": wb})
    contacts: list[list[str]] = [["suspension_*", "body"], ["battery_pack", "motor_*"], ["motor_*", "suspension_*"]]

    # ---------- cửa ----------
    for (pos, side), dsol in door_solids.items():
        _, xa, xb_, sy = door_boxes[(pos, side)]
        wx0, wx1 = (xa + 50.0, xb_ - 40.0) if pos == "front" else (xa + 40.0, xb_ - 50.0)
        win = xbox(wx0, wx1, sy * y_split, sy * (W + 100), z_bm + 30.0, z_dt - 40.0)
        glass = dsol & win
        panel = dsol - win
        extra = []
        x_h = xa + 90.0 if pos == "front" else xa + 80.0
        z_h = z_bm - 70.0
        ys = D.surface_at(outer, "y", (x_h, 0, z_h), positive=sy > 0)
        if ys is not None:
            extra.append(K.rounded_box(160.0, 16.0, 32.0, 7.0, segments=6).translate(x_h + 60.0, ys + sy * 4.0, z_h))
        hinges = []                                                  # nằm trong bề dày vỏ, ăn vào thân (không lấn khoang lái)
        if pos == "front":                                           # bản lề mép trước (vè trước)
            x_hinge = xb_ - 20.0
            for zz in (z_bm - 250.0, z_bm - 60.0):
                yh = D.surface_at(inner, "y", (x_hinge, 0, zz), positive=sy > 0)
                if yh is not None:
                    hinges.append(K.box(60.0, 14.0, 60.0).translate(x_hinge + 25.0, yh + sy * 11.0, zz))
        else:                                                        # cửa sau: chốt/bản lề tì xuống bậu cửa
            for xx in (xa + 150.0, xb_ - 150.0):
                yh = D.surface_at(inner, "y", (xx, 0, z_db + 40.0), positive=sy > 0)
                if yh is not None:
                    hinges.append(K.box(60.0, 14.0, 70.0).translate(xx, yh + sy * 11.0, z_db))
        shapes = [Shape(panel, "paint_primary", 40.0), Shape(glass, "glass_tinted", 40.0)]
        if extra:
            shapes.append(Shape(K.Solid.union_all(extra), "chrome", 40.0))
        if hinges:
            shapes.append(Shape(K.Solid.union_all(hinges), "steel_dark", 40.0))
        if pos == "front":
            xm = xb_ - 120.0
            ym = D.surface_at(outer, "y", (xm, 0, z_bm + 60.0), positive=sy > 0) or sy * W / 2
            housing = K.ellipsoid(110.0, 120.0, 65.0, segments=24).translate(xm - 30.0, ym + sy * 150.0, z_bm + 90.0)
            glass_m = K.box(8.0, 180.0, 90.0).translate(xm - 136.0, ym + sy * 150.0, z_bm + 90.0) & K.ellipsoid(112.0, 112.0, 60.0, segments=24).translate(
                xm - 30.0, ym + sy * 150.0, z_bm + 90.0)
            stalk = K.box(50.0, 160.0, 34.0).translate(xm, ym + sy * 60.0, z_bm + 70.0)
            shapes += [Shape(housing - glass_m.translate(3.0, 0, 0) + stalk, "paint_secondary", 40.0), Shape(glass_m, "chrome", 40.0)]
        vi_pos, vi_side = ("trước" if pos == "front" else "sau"), ("trái" if sy > 0 else "phải")
        b.add(f"door_{pos}_{side}", f"Cửa {vi_pos} {vi_side}", f"{pos.title()} {side} door", "door", shapes, parent_id="body", required=True,
              aliases=["cửa", f"cửa {vi_pos}", f"cửa {vi_pos} {vi_side}", "cánh cửa", "door", "tay nắm cửa", "kính cửa"]
              + (["gương chiếu hậu", "gương"] if pos == "front" else []),
              function="Cửa vỏ thép: kính không khung, tay nắm âm, bản lề trước" + (", gương chiếu hậu." if pos == "front" else "."),
              position_tag="left" if sy > 0 else "right", joint_axis=(0, 0, 1), explode_dir=(0, sy, 0), explode_distance=0.35 * W,
              explode_order=1)
    x_hh = x_of(u_ws0 - 0.004)                                        # mép sau capô: 2 bản lề ăn vào thân
    h_hinges = []
    for sy in (1, -1):
        zi = D.surface_at(inner, "z", (x_hh, sy * 0.3 * W, 0), positive=True)
        if zi is not None:
            h_hinges.append(K.box(50.0, 40.0, 14.0).translate(x_hh + 20.0, sy * 0.3 * W, zi + 11.0))
    hood_shapes = [Shape(hood, "paint_primary", 40.0)]
    if h_hinges:
        hood_shapes.append(Shape(K.Solid.union_all(h_hinges), "steel_dark", 40.0))
    b.add("hood", "Nắp capô", "Hood", "hood", hood_shapes, parent_id="body", required=True,
          aliases=["nắp capô", "capô", "nắp máy", "hood", "cốp trước"], function="Nắp capô (khoang hành lý trước — xe điện không có động cơ đốt trong).",
          position_tag="front", joint_axis=(0, 1, 0), explode_dir=(0.2, 0, 1), explode_distance=0.25 * H, explode_order=1)
    tg_shapes = [Shape(tg - rear_box if not sedan else tg, "paint_primary", 40.0)]
    if not sedan:
        tg_shapes.append(Shape(tg & rear_box, "glass_tinted", 40.0))
    x_th = x_of((u_t if sedan else u_r1) + 0.004)                    # mép trước nắp cốp / cửa hậu: 2 bản lề ăn vào thân
    t_hinges = []
    for sy in (1, -1):
        zi = D.surface_at(inner, "z", (x_th, sy * 0.3 * W, 0), positive=True)
        if zi is not None:
            t_hinges.append(K.box(50.0, 40.0, 14.0).translate(x_th - 20.0, sy * 0.3 * W, zi + 11.0))
    if t_hinges:
        tg_shapes.append(Shape(K.Solid.union_all(t_hinges), "steel_dark", 40.0))
    b.add("trunk", "Nắp cốp" if sedan else "Cửa hậu", "Trunk lid" if sedan else "Tailgate", "trunk", tg_shapes, parent_id="body",
          required=True, aliases=["nắp cốp", "cốp", "cốp sau", "cửa hậu", "trunk", "tailgate"] + ([] if sedan else ["kính hậu"]),
          function="Nắp cốp sau." if sedan else "Cửa hậu mở lên, kính hậu liền cửa.", position_tag="rear", joint_axis=(0, 1, 0),
          explode_dir=(-0.3, 0, 1), explode_distance=0.25 * H, explode_order=1)

    # ---------- nội thất ----------
    z_fl = clr + hb + 15.0
    seats = []
    for sy in (1, -1):
        cush = K.rounded_box(0.11 * L, 0.26 * W, 0.075 * H, 30.0, segments=8).translate(x_b + 0.06 * L, sy * 0.22 * W, z_fl + 0.1 * H)
        base = K.box(0.08 * L, 0.2 * W, 0.07 * H).translate(x_b + 0.06 * L, sy * 0.22 * W, z_fl + 0.035 * H)
        back = K.rounded_box(0.03 * L, 0.26 * W, 0.26 * H, 30.0, segments=8).rotate(0, -14, 0).translate(x_b - 0.005 * L, sy * 0.22 * W, z_fl + 0.25 * H)
        seats += [cush, base, back]
    bench = K.rounded_box(0.11 * L, 0.72 * W, 0.08 * H, 30.0, segments=8).translate(x_b - 0.13 * L, 0, z_fl + 0.06 * H)
    bench_b = K.rounded_box(0.03 * L, 0.72 * W, 0.24 * H, 30.0, segments=8).rotate(0, -18, 0).translate(x_b - 0.2 * L, 0, z_fl + 0.2 * H)
    seats += [bench, bench_b]
    dash = xbox(x_of(u_ws0 + 0.1), x_of(u_ws0), -(W / 2), W / 2, belt(u_ws0) - 0.14 * H, belt(u_ws0) + 0.02 * H)
    x_dash = x_of(u_ws0 + 0.1)
    screen = K.rounded_box(20.0, 380.0, 230.0, 10.0, segments=6).rotate(0, -10, 0).translate(x_dash - 15.0, 0, belt(u_ws0) + 0.07 * H)
    wheel_c = np.array([x_dash - 0.05 * L, 0.22 * W, belt(u_ws0) + 0.0 * H])
    steer = MC.orient(K.torus(185.0, 17.0, segments=48, tube_segments=12), wheel_c, (math.cos(math.radians(68)), 0, math.sin(math.radians(68))))
    spokes_s = MC.orient(K.box(340.0, 40.0, 20.0), wheel_c, (math.cos(math.radians(68)), 0, math.sin(math.radians(68))))
    col = K.tube(np.array([wheel_c, wheel_c + np.array([0.08 * L, 0, 0.03 * H])]), 30.0, 12)
    cav = inner - K.box(L * 2, W * 2, z_fl * 2)                       # chỉ giữ phần trong khoang, trên sàn
    y_keep = y_c - tw / 2 - 80.0 - 0.2 * R - 40.0                      # chừa tháp giảm chấn + hốc bánh hai bên
    for xw_ in (x_f, x_r):
        for sy in (1, -1):
            cav = cav - xbox(xw_ - Ra - 80.0, xw_ + Ra + 80.0, sy * y_keep, sy * W, 0.0, H * 2)
    b.add("interior", "Nội thất (ghế, taplô, vô-lăng)", "Interior", "interior",
          [Shape(K.Solid.union_all(seats) & cav, "leather", 40.0), Shape((dash & cav) + (col & cav), "plastic_black", 40.0),
           Shape(screen & cav, "glass_tinted", 40.0), Shape((steer + spokes_s) & cav, "plastic_black", 40.0)], parent_id="body",
          required=True, aliases=["nội thất", "ghế", "ghế lái", "taplô", "vô lăng", "màn hình", "interior", "khoang lái"],
          function="Ghế trước + băng ghế sau bọc da, taplô, màn hình trung tâm, vô-lăng (tay lái thuận — bên trái).",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.9 * H, explode_order=2)

    # ---------- pin sàn ----------
    batt = K.rounded_box(bx1 - bx0, 2 * by, hb, 25.0, segments=8).translate((bx0 + bx1) / 2, 0, clr + hb / 2)
    batt = batt & xbox(bx0 - 1, bx1 + 1, -by - 1, by + 1, clr, clr + hb)
    seams = K.Solid.union_all([K.box(12.0, 2 * by + 10, 8.0).translate(x, 0, clr + hb - 3.0) for x in np.linspace(bx0 + 300.0, bx1 - 300.0, 5)])
    x_hv = x_r if not awd else x_f
    hv_x0 = bx0 if x_hv < bx0 else bx1
    sx_hv = 1 if x_hv > bx1 else -1
    hv = K.tube(np.array([[hv_x0 - sx_hv * 30.0, 0.02 * W, clr + hb - 25.0], [hv_x0 + sx_hv * 180.0, 0.02 * W, clr + hb - 25.0],
                          [x_hv - sx_hv * 0.25 * R, 0.02 * W, 0.8 * R]]), 14.0, 12)       # cáp đi dưới sàn vào mặt trước motor
    b.add("battery_pack", "Pin sàn (lithium-ion)", "Floor battery pack", "battery",
          [Shape(batt - seams, "aluminum_dark", 40.0), Shape(seams, "steel_dark", 40.0), Shape(hv, "cable_orange", 40.0)], parent_id="body",
          required=True, aliases=["pin", "pin sàn", "bộ pin", "ắc quy", "battery", "cáp cao áp"],
          function=f"Bộ pin lithium-ion dạng tấm phẳng dưới sàn ({(bx1 - bx0) / 1000:.2f} × {2 * by / 1000:.2f} m), cáp cao áp màu cam tới motor.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.35 * H, explode_order=2)

    # ---------- khung phụ, motor, hệ treo, bánh ----------
    y_sub = y_c - 0.62 * tw - 0.9 * R
    z_arm = max(0.6 * R, clr + T_SH + 45.0)
    z_sf0 = clr + T_SH
    tire_s, rim_s = C.wheel(Dt, tw, spokes=5, tread=True)
    tire0 = K.Solid.union_all([s_.solid for s_ in tire_s])
    rim0 = K.Solid.union_all([s_.solid for s_ in rim_s])
    lz = lambda s_: s_.rotate(-90, 0, 0)                               # noqa: E731  hệ bánh (trục Z, mặt ngoài +Z) → trục Y
    holes = K.Solid.union_all([K.cylinder(0.012 * R, tw, segments=8).translate(0.4 * R * math.cos(a), 0.4 * R * math.sin(a), -tw / 2)
                               for a in np.radians(np.arange(0, 360, 20))])        # lỗ khoan tản nhiệt đĩa phanh
    disc = lz(K.cylinder(0.515 * R, 0.1 * tw, segments=64).translate(0, 0, -0.38 * tw) - K.cylinder(0.22 * R, tw, segments=48).translate(0, 0, -tw / 2)
              - holes)
    hat = lz(K.cylinder(0.25 * R, 0.12 * tw, segments=48).translate(0, 0, -0.32 * tw))
    prof_cal = [(0.40 * R, -0.44 * tw), (0.545 * R, -0.44 * tw), (0.545 * R, -0.22 * tw), (0.40 * R, -0.22 * tw), (0.40 * R, -0.27 * tw),
                (0.525 * R, -0.27 * tw), (0.525 * R, -0.39 * tw), (0.40 * R, -0.39 * tw)]
    caliper0 = lz(K.revolve(prof_cal, segments=12, degrees=45.0).rotate(0, 0, 217.5))
    for axle, xw in (("front", x_f), ("rear", x_r)):
        sid = f"subframe_{axle}"
        rails = K.Solid.union_all([K.box(2.0 * R, 60.0, z_arm + 25.0 - z_sf0).translate(xw, sy * (abs(y_sub) - 10.0), (z_arm + 25.0 + z_sf0) / 2)
                                   for sy in (1, -1)])
        cross = K.Solid.union_all([K.box(60.0, 2 * abs(y_sub), 60.0).translate(xw + sx * (R - 30.0), 0, z_sf0 + 30.0) for sx in (1, -1)])
        b.add(sid, f"Khung phụ {'trước' if axle == 'front' else 'sau'}", f"{axle.title()} subframe", "subframe",
              Shape(rails + cross, "steel_dark", 40.0), parent_id="body", required=True, aliases=["khung phụ", "subframe", "giá đỡ động cơ"],
              function="Khung phụ bắt vào thân: gá càng A và motor.", position_tag="front" if axle == "front" else "rear",
              explode_dir=(0, 0, -1), explode_distance=0.55 * H, explode_order=3)
        if axle == "rear" or awd:
            rm = 0.36 * R
            mot = K.cylinder(rm, 0.28 * W, segments=48).rotate(90, 0, 0).translate(xw, 0.14 * W, R)
            fins = K.Solid.union_all([K.torus(rm, 6.0, segments=48, tube_segments=8).rotate(90, 0, 0).translate(xw, y, R)
                                      for y in np.linspace(-0.1 * W, 0.1 * W, 7)])
            gear = K.rounded_box(0.9 * rm, 0.12 * W, 1.6 * rm, 20.0, segments=8).translate(xw - 0.4 * rm, -0.2 * W, R + 0.1 * rm)
            y_k = y_c - 0.62 * tw
            shafts = K.Solid.union_all([K.cylinder(0.07 * R, y_k - 0.14 * W, segments=20).rotate(-90 * sy, 0, 0)
                                        .translate(xw, sy * 0.14 * W, R) for sy in (1, -1)])
            b.add(f"motor_{axle}", f"Motor điện {'trước' if axle == 'front' else 'sau'} + hộp số", f"{axle.title()} drive unit", "motor",
                  [Shape(mot + fins, "cast_aluminum", 40.0), Shape(gear, "cast_aluminum", 40.0), Shape(shafts, "steel", 40.0)], parent_id=sid,
                  required=True, aliases=["motor", "động cơ điện", "mô tơ", "hộp số", "bán trục", "drive unit"],
                  function="Motor điện nam châm vĩnh cửu + hộp số giảm tốc 1 cấp + vi sai, hai bán trục tới bánh.",
                  position_tag="front" if axle == "front" else "rear", joint_axis=(0, 1, 0), explode_dir=(0, 0, -1),
                  explode_distance=0.2 * H, explode_order=2)
        for side, sy in (("left", 1), ("right", -1)):
            cid = f"suspension_{axle}_{side}"
            kn = K.box(0.24 * R, 0.18 * tw, 0.9 * R).translate(0, y_c - 0.53 * tw, R)
            stub = K.cylinder(0.16 * R, 0.06 * tw, segments=24).rotate(-90, 0, 0).translate(0, y_c - 0.45 * tw, R)
            cal = caliper0.translate(0, y_c, R)
            brk = K.box(0.2 * R, 0.07 * tw, 0.15 * R).translate(-0.2 * R, y_c - 0.465 * tw, R + 0.375 * R)
            arms = K.Solid.union_all([K.tube(np.array([[0.0, y_c - 0.6 * tw, 0.6 * R], [dx, y_sub, z_arm]]), 0.05 * R, 12) for dx in (-0.9 * R, 0.9 * R)])
            z_tm = R + Ra
            y_st = y_c - tw / 2 - 80.0
            a_ = np.array([0.0, y_c - 0.53 * tw, R + 0.42 * R])
            b_ = np.array([0.0, y_st, z_tm - 15.0])
            damper = K.tube(np.array([a_, b_]), 0.07 * R, 16)
            top_m = K.cylinder(70.0, 15.0, segments=24).translate(0, y_st, z_tm - 15.0)
            dvec = (b_ - a_) / np.linalg.norm(b_ - a_)
            Ls = 0.3 * R
            spring = MC.orient(K.tube(MC.helix_path(0.16 * R, [(5.0, Ls / 5.0)], z0=0.0, per_turn=16), 0.025 * R, 8),
                               b_ - dvec * (Ls + 25.0), dvec)
            corner = [Shape(kn + stub + brk + arms, "cast_aluminum", 40.0), Shape(cal, "paint_red", 40.0),
                      Shape(damper + top_m, "steel_dark", 40.0), Shape(spring, "spring_steel", 40.0)]
            if sy < 0:
                corner = [Shape(s_.solid.mirror((0, 1, 0)), s_.material, 40.0) for s_ in corner]
            corner = [Shape(s_.solid.translate(xw, 0, 0), s_.material, 40.0) for s_ in corner]
            vi = f"{'trước' if axle == 'front' else 'sau'} {'trái' if sy > 0 else 'phải'}"
            b.add(cid, f"Hệ treo + phanh {vi}", "Suspension corner", "suspension", corner, parent_id=sid, required=True,
                  aliases=["hệ treo", "giảm xóc", "lò xo", "càng A", "heo phanh", "phanh", "cam lái", f"hệ treo {vi}"],
                  function="Cam lái nhôm đúc, càng A dưới, giảm chấn + lò xo lên tháp trong hốc bánh, heo phanh đĩa.",
                  position_tag="left" if sy > 0 else "right", explode_dir=(0, sy, 0), explode_distance=0.12 * W, explode_order=2)
            wparts = [tire0, rim0, disc + hat]
            wparts = [s_.translate(0, y_c, R) for s_ in wparts]
            if sy < 0:
                wparts = [s_.mirror((0, 1, 0)) for s_ in wparts]
            wparts = [s_.translate(xw, 0, 0) for s_ in wparts]
            b.add(f"wheel_{axle}_{side}", f"Bánh xe {vi}", "Wheel", "wheel",
                  [Shape(wparts[0], "rubber", 40.0), Shape(wparts[1], "aluminum", 40.0), Shape(wparts[2], "cast_iron", 40.0)],
                  parent_id=cid, required=True, aliases=["bánh xe", "lốp", "la-zăng", "mâm xe", "đĩa phanh", "wheel", f"bánh {vi}"],
                  function=f"Lốp {tw}/{ar}R{rim_in} (Ø{Dt:.0f} mm), la-zăng hợp kim 5 chấu, đĩa phanh thông gió.",
                  position_tag="left" if sy > 0 else "right", joint_axis=(0, 1, 0), explode_dir=(0, sy, 0), explode_distance=0.18 * W,
                  explode_order=1, dimensions={"diameter": Dt, "width": tw})
    b.note_stage(1, "Mở cửa, capô, cốp; tháo bánh xe")
    b.note_stage(2, "Tháo pin sàn, motor, hệ treo; nhấc nội thất")
    b.note_stage(3, "Hạ khung phụ khỏi thân xe")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"body_type": typ, "length_mm": L, "width_mm": W, "height_mm": H, "wheelbase_mm": wb, "track_mm": track,
                       "tire": f"{tw}/{ar}R{rim_in}", "tire_d_mm": Dt, "drive": "awd" if awd else "rwd", "doors": 4,
                       "standard": "Ký hiệu lốp ISO 4000 (bề rộng/tỷ lệ thành R vành); tỷ lệ sedan điện cỡ D",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
