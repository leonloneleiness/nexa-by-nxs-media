"""Xe nâng đối trọng (1–5 t), điện (ắc quy dưới ghế) hoặc dầu (động cơ + ống xả).

- Càng nâng tiết diện theo ISO 2331 (vd. 2,5 t: 122 × 40, dài 1070 mm), giá càng theo cấp ISO 2328 (cấp II cao 407 mm),
  tâm tải 500 mm; cao độ mặt trên càng = tham số fork_height.
- Khung nâng (mast) 2 tầng hoặc 3 tầng (tự thêm tầng khi nâng cao): trụ ngoài chữ C, trụ trong lồng trong rãnh C có con lăn,
  xi lanh nâng giữa (đáy trên dầm dưới trụ ngoài, cần lên xà đầu trụ trong), xích nâng; 2 xi lanh nghiêng từ khung xe tới
  trụ ngoài; mắt xi lanh ôm đúng chốt.
- Khung xe có hốc bánh, cầu chủ động trước (lốp hơi đặc 7.00-12), cầu lái sau (6.00-9), đối trọng gang đuôi,
  khung bảo vệ trên đầu (overhead guard) 4 trụ, ghế, vô-lăng.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# ISO 2331: tiết diện càng (rộng × dày) theo tải; ISO 2328: cấp giá càng → chiều cao giá
FORK_SECTION = [(1500.0, 100.0, 35.0), (2500.0, 122.0, 40.0), (3500.0, 125.0, 45.0), (5000.0, 150.0, 50.0)]
CARRIAGE_CLASS = [(999.0, "I", 331.5), (2500.0, "II", 407.0), (4999.0, "III", 508.0), (1e9, "IV", 635.0)]
# lốp (ký hiệu, đường kính, bề rộng) trước / sau theo tải
TIRES = [(1800.0, ("6.50-10", 590.0, 165.0), ("5.00-8", 470.0, 127.0)), (3000.0, ("7.00-12", 680.0, 178.0), ("6.00-9", 540.0, 152.0)),
         (5000.0, ("8.25-15", 850.0, 210.0), ("7.00-12", 680.0, 178.0))]


def pick(table, q):
    return next(r for r in table if q <= r[0])


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    Q = float(p.get("capacity_kg", 2500.0))
    electric = p.get("power", "electric") == "electric"
    hf_req = float(p.get("fork_height_mm", 150.0))
    s = (Q / 2500.0) ** (1 / 3)
    _, fw, ft = pick(FORK_SECTION, Q)
    hf = max(hf_req, ft + 10.0)                                        # càng hạ hết: mặt dưới càng cách đất 10 mm
    _, cls, hc = pick(CARRIAGE_CLASS, Q)
    _, tf, tr = pick(TIRES, Q)
    Rf, twf = tf[1] / 2, tf[2]
    Rr, twr = tr[1] / 2, tr[2]
    wb = 1600.0 * s
    W = 1150.0 * s
    Lfork = 1070.0 if Q <= 3000 else 1220.0
    mast_h = 2000.0 * s
    H_og = 1080.0 * s ** 0.5 + 1100.0                                  # mái bảo vệ ≈ 1,1 m trên nắp khoang (2,18 m với 2,5 t)
    mats = MC.tech_materials(spec, primary="#f28c28", secondary="#1b1d21", accent="#e63946")
    b = AssemblyBuilder(spec.name or f"Xe nâng {'điện' if electric else 'dầu'} {Q / 1000:g} tấn", "forklift", mats)
    contacts: list[list[str]] = []
    links, ram_info = [], {}

    # ---------- khung xe ----------
    xf, xr = 0.0, -wb
    yf = W / 2 - twf / 2 - 10.0
    yr = W / 2 - twr / 2 - 60.0
    x_front, x_rear = Rf * 0.75, xr - Rr - 420.0 * s
    z0c, z1c = 170.0, 1080.0 * s ** 0.5                                # nắp khoang ≈ 1,08 m (2,5 t), tăng chậm theo tải
    body = K.rounded_box(x_front - x_rear, W, z1c - z0c, 60.0, segments=10).translate((x_front + x_rear) / 2, 0, (z0c + z1c) / 2)
    wells = K.Solid.union_all([K.cylinder(Rf + 35.0, W + 20, segments=48).rotate(90, 0, 0).translate(xf, W / 2 + 10, Rf),
                               K.cylinder(Rr + 35.0, W + 20, segments=48).rotate(90, 0, 0).translate(xr, W / 2 + 10, Rr)])
    body = body - wells
    cw_x0 = xr - Rr - 60.0
    cw = K.rounded_box(cw_x0 - (x_rear - 60.0), W, z1c - z0c + 120.0, 140.0, segments=12).translate((cw_x0 + x_rear - 60.0) / 2, 0, (z0c + z1c + 120.0) / 2)
    cw = cw & box_at(cw_x0, x_rear - 70.0, -W, W, 0, 3000)
    cw = cw - wells
    body = body - box_at(cw_x0, x_rear - 100.0, -W, W, 0, 3000)
    x_bf = -Rf - 60.0                                                  # mặt trước khoang ắc quy/động cơ (sau bánh trước)
    pocket = box_at(-0.75 * wb, x_bf, -0.36 * W, 0.36 * W, 420.0, z1c + 10.0)
    body = body - pocket
    axles = K.cylinder(0.22 * Rf, 2 * yf - 0.4 * twf, segments=24).rotate(90, 0, 0).translate(xf, yf - 0.2 * twf, Rf) + \
        K.cylinder(0.2 * Rr, 2 * yr - 0.4 * twr, segments=24).rotate(90, 0, 0).translate(xr, yr - 0.2 * twr, Rr)
    diff = K.sphere(0.45 * Rf, segments=24).translate(xf, 0, Rf)
    # chốt xi lanh nghiêng trên khung (tai hàn phía trước)
    y_t = 0.17 * W
    z_t = z1c - 120.0
    x_t0 = -0.08 * wb
    tilt_pins = [np.array([x_t0, sy * y_t, z_t]) for sy in (1, -1)]
    lugs = K.Solid.union_all([box_at(x_t0 - 60.0, x_front - 20.0, sy * y_t - 35.0, sy * y_t + 35.0, z_t - 60.0, z1c) for sy in (1, -1)])
    pins_c = K.Solid.union_all([MC.pin(q, (0, 1, 0), 40.0, 110.0) for q in tilt_pins])
    step = box_at(-0.1 * wb, 0.2 * wb, W / 2 - 5.0, W / 2 + 40.0, 360.0, 400.0)
    b.add("chassis", "Khung xe (thân, cầu trước/sau)", "Chassis", "chassis",
          [Shape(body + lugs, "paint_primary", 40.0), Shape(axles + diff, "cast_iron", 40.0), Shape(pins_c, "steel", 40.0),
           Shape(step, "steel_dark", 40.0)], required=True,
          aliases=["khung xe", "thân xe", "cầu trước", "cầu lái", "chassis", "bậc lên xuống"],
          function="Khung thép hàn: cầu chủ động trước (vi sai), cầu lái sau, tai gá xi lanh nghiêng.", position_tag="center",
          dimensions={"wheelbase": wb, "width": W})
    b.add("counterweight", "Đối trọng", "Counterweight", "counterweight", Shape(cw, "cast_iron", 40.0), parent_id="chassis", required=True,
          aliases=["đối trọng", "cục đối trọng", "counterweight"], function="Đối trọng gang cân bằng mô-men tải quanh cầu trước.",
          position_tag="rear", explode_dir=(-1, 0, 0), explode_distance=500.0, explode_order=2)
    if electric:
        batt = box_at(-0.75 * wb + 10.0, x_bf - 10.0, -0.36 * W + 10.0, 0.36 * W - 10.0, 420.0, z1c + 10.0)
        cells = K.Solid.union_all([K.cylinder(25.0, 12.0, segments=16).translate(x, y, z1c + 10.0)
                                   for x in np.linspace(-0.7 * wb, -0.1 * wb, 6) for y in np.linspace(-0.28 * W, 0.28 * W, 4)])
        b.add("battery", "Ắc quy kéo 48 V", "Traction battery", "battery", [Shape(batt, "paint_blue", 40.0), Shape(cells, "steel", 40.0)],
              parent_id="chassis", required=True, aliases=["ắc quy", "pin", "bình điện", "battery"],
              function="Ắc quy chì–axit / lithium 48 V trong khoang dưới ghế (cũng góp phần đối trọng).", position_tag="center",
              explode_dir=(0, 0, 1), explode_distance=900.0, explode_order=2)
        top_z = z1c + 10.0
    else:
        eng = box_at(-0.75 * wb + 10.0, x_bf - 10.0, -0.34 * W, 0.34 * W, 420.0, z1c - 40.0)
        exh = K.tube(np.array([[-0.6 * wb, -0.3 * W, z1c - 100.0], [-0.6 * wb, -W / 2 + 60.0, z1c + 50.0], [-0.6 * wb, -W / 2 + 60.0, H_og - 150.0]]), 35.0, 12)
        b.add("engine", "Động cơ diesel + ống xả", "Diesel engine", "engine", [Shape(eng, "cast_iron", 40.0), Shape(exh, "steel_dark", 40.0)],
              parent_id="chassis", required=True, aliases=["động cơ", "máy dầu", "ống xả", "engine"],
              function="Động cơ diesel 4 xi lanh dưới ghế, ống xả dựng đứng.", position_tag="center",
              explode_dir=(0, 0, 1), explode_distance=900.0, explode_order=2)
        top_z = z1c - 40.0
    hood = box_at(-0.75 * wb, x_bf, -0.37 * W, 0.37 * W, top_z, top_z + 40.0)
    seat = K.rounded_box(420.0, 460.0, 110.0, 40.0, segments=6).translate(-0.5 * wb, 0, top_z + 95.0) + \
        K.rounded_box(90.0, 460.0, 480.0, 40.0, segments=6).rotate(0, -12, 0).translate(-0.5 * wb - 230.0, 0, top_z + 330.0)
    col = K.tube(np.array([[0.02 * wb, 0, z1c], [-0.12 * wb, 0, z1c + 520.0]]), 35.0, 12)
    wheel = MC.orient(K.torus(170.0, 16.0, segments=40, tube_segments=10), [-0.12 * wb - 10.0, 0, z1c + 540.0], (math.sin(math.radians(35)), 0, math.cos(math.radians(35))))
    b.add("operator", "Ghế lái + vô-lăng", "Operator station", "interior",
          [Shape(seat, "plastic_black", 40.0), Shape(hood, "paint_secondary", 40.0), Shape(col + wheel, "plastic_black", 40.0)], parent_id="chassis",
          required=True, aliases=["ghế lái", "ghế", "vô lăng", "tay lái", "nắp ca-pô", "operator"], function="Nắp khoang + ghế có dây an toàn, vô-lăng trợ lực.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=1300.0, explode_order=1)
    contacts.append(["operator", "battery" if electric else "engine"])
    # khung bảo vệ trên đầu
    posts = []
    xs_post = (x_front - 60.0, x_rear + 120.0)
    for xp in xs_post:
        for sy in (1, -1):
            posts.append(K.tube(np.array([[xp, sy * (W / 2 - 50.0), z1c - 20.0], [xp + (-120.0 if xp > 0 else 0.0), sy * (W / 2 - 50.0), H_og - 30.0]]), 35.0, 12))
    roof = box_at(xs_post[1] - 40.0, xs_post[0] - 80.0, -W / 2 + 10.0, W / 2 - 10.0, H_og - 60.0, H_og)
    slots = K.Solid.union_all([box_at(x - 30.0, x + 30.0, -W / 2 + 90.0, W / 2 - 90.0, H_og - 80.0, H_og + 20.0)
                               for x in np.linspace(xs_post[1] + 60.0, xs_post[0] - 180.0, 7)])
    b.add("overhead_guard", "Khung bảo vệ trên đầu", "Overhead guard", "frame", Shape(K.Solid.union_all(posts) + (roof - slots), "paint_secondary", 40.0),
          parent_id="chassis", required=True, aliases=["khung bảo vệ", "mái che", "overhead guard", "khung mui"],
          function="Khung bảo vệ người lái khỏi vật rơi (ISO 6055), mái lưới.", position_tag="top", explode_dir=(0, 0, 1), explode_distance=700.0,
          explode_order=2)
    contacts.append(["overhead_guard", "counterweight"])

    # ---------- bánh ----------
    tires = {}
    for key, (tt, R, tw) in (("front", (tf, Rf, twf)), ("rear", (tr, Rr, twr))):
        ts, rs = C.wheel(2 * R, tw, spokes=6, tread=True)
        tires[key] = (K.Solid.union_all([x.solid for x in ts]), K.Solid.union_all([x.solid for x in rs]))
    for key, xw, yw, R in (("front", xf, yf, Rf), ("rear", xr, yr, Rr)):
        for side, sy in (("left", 1), ("right", -1)):
            t_, r_ = tires[key]
            if sy < 0:
                t_, r_ = t_.mirror((0, 1, 0)), r_.mirror((0, 1, 0))
            b.add(f"wheel_{key}_{side}", f"Bánh {'trước (chủ động)' if key == 'front' else 'sau (lái)'} {'trái' if sy > 0 else 'phải'}",
                  "Wheel", "wheel", [Shape(t_.translate(xw, sy * yw, R), "rubber", 40.0), Shape(r_.translate(xw, sy * yw, R), "paint_secondary", 40.0)],
                  parent_id="chassis", required=True, aliases=["bánh xe", "lốp", "vành", "wheel", f"bánh {'trước' if key == 'front' else 'sau'}"],
                  function=f"Lốp {tf[0] if key == 'front' else tr[0]} (Ø{2 * R:.0f} mm).", position_tag="left" if sy > 0 else "right",
                  joint_axis=(0, 1, 0), explode_dir=(0, sy, 0), explode_distance=350.0, explode_order=1, dimensions={"diameter": 2 * R})

    # ---------- khung nâng ----------
    x0 = Rf + 60.0                                                     # mặt sau trụ ngoài
    d_ch, t_ch, f_ch = 130.0 * s, 14.0, 70.0 * s
    y_m = 0.3 * W                                                      # mép ngoài bụng trụ
    z_mb = 120.0
    carriage_top = hf + 20.0 + hc - 40.0
    need = max(0.0, carriage_top + 60.0 - (mast_h - 40.0))
    n_st = 2 if need <= mast_h - 520.0 else 3
    ext = need / (n_st - 1)

    def channel(y_out: float, z0: float, h: float) -> K.Solid:
        c = box_at(x0, x0 + d_ch, y_out - f_ch, y_out, z0, z0 + h)
        return c - box_at(x0 + t_ch, x0 + d_ch - t_ch, y_out - f_ch - 1.0, y_out - t_ch, z0 - 1.0, z0 + h + 1.0)

    outer = channel(y_m, z_mb, mast_h) + channel(y_m, z_mb, mast_h).mirror((0, 1, 0))
    bottom_x = box_at(x0 - 90.0, x0 + t_ch, -y_m, y_m, z_mb, z_mb + 90.0)
    top_x = box_at(x0 - 40.0, x0 + t_ch, -y_m, y_m, z_mb + mast_h - 80.0, z_mb + mast_h) - box_at(x0 - 200.0, x0 + 200.0, -70.0, 70.0, 0, 5000)
    z_tm = z1c - 20.0
    tilt_m = [np.array([x0 - 45.0, sy * y_t, z_tm]) for sy in (1, -1)]
    brk = K.Solid.union_all([box_at(x0 - 80.0, x0 + t_ch, sy * (y_t - 35.0), sy * (y_m - t_ch + 1.0), z_tm - 60.0, z_tm + 60.0) for sy in (1, -1)])
    piv = K.cylinder(0.2 * Rf, 2 * y_m, segments=24).rotate(90, 0, 0).translate(x0 - 30.0, y_m, Rf)
    piv_blk = K.Solid.union_all([box_at(x0 - 60.0, x0 + t_ch, sy * (y_m - f_ch), sy * y_m, Rf - 70.0, Rf + 70.0) for sy in (1, -1)])
    p_lift0 = np.array([x0 - 60.0, 0, z_mb + 60.0])
    pins_m = K.Solid.union_all([MC.pin(q, (0, 1, 0), 40.0, 110.0) for q in tilt_m] + [MC.pin(p_lift0, (0, 1, 0), 45.0, 160.0)])
    b.add("mast_outer", "Trụ nâng ngoài", "Outer mast", "mast", [Shape(outer + bottom_x + top_x + brk + piv_blk, "paint_secondary", 40.0),
                                                                    Shape(piv, "cast_iron", 40.0), Shape(pins_m, "steel", 40.0)],
          parent_id="chassis", required=True, aliases=["khung nâng", "trụ nâng", "mast", "trụ ngoài", "cột nâng"],
          function=f"Khung nâng {n_st} tầng, trụ thép chữ C, chốt nghiêng ở cầu trước (nghiêng trước/sau).", position_tag="front",
          joint_axis=(0, 1, 0), explode_dir=(1, 0, 0), explode_distance=900.0, explode_order=3, dimensions={"lowered_height": mast_h})
    # tầng trượt: tầng 1 nằm trong rãnh C của trụ ngoài; tầng 2 (khung 3 tầng) nằm phía trong tầng 1
    xa_in, xb_in = x0 + t_ch + 6.0, x0 + d_ch - t_ch - 6.0
    y_c_in = y_m - f_ch                                                # mép trong rãnh C
    ranges = [(y_c_in - 40.0, y_m - t_ch - 6.0), (y_c_in - 100.0, y_c_in - 46.0)]
    stage_ids = ["mast_outer"]
    z_stage, z_head, lo, hi = z_mb, z_mb + mast_h, 0.0, 0.0
    for i in range(1, n_st):
        sid = "mast_inner" if i == n_st - 1 else "mast_middle"
        lo, hi = ranges[i - 1]
        z_stage = z_stage + ext + 30.0
        h = mast_h - 30.0 * i
        xa = xa_in + (26.0 if (n_st == 3 and sid == "mast_inner") else 0.0)    # trụ trong né xà đầu tầng giữa (đặt phía sau)
        up = box_at(xa, xb_in, lo, hi, z_stage, z_stage + h)
        ups = up + up.mirror((0, 1, 0))
        if sid == "mast_inner":
            head = box_at(xa, xb_in, -lo, lo, z_stage + h - 70.0, z_stage + h)
        else:
            head = box_at(xa_in, xa_in + 20.0, -lo, lo, z_stage + h - 70.0, z_stage + h)
        # con lăn: từ mặt ngoài tầng này tì sang mặt của tầng cha (bụng trụ ngoài / mặt trong tầng giữa)
        y_par = y_m - t_ch if i == 1 else ranges[0][0]
        y0r, y1r = hi - 4.0, y_par + 2.0
        rol_l = K.Solid.union_all([K.cylinder(26.0, y1r - y0r, segments=20).rotate(-90, 0, 0).translate((xa + xb_in) / 2, y0r, zz)
                                   for zz in (z_stage + 80.0, z_stage + h - 120.0)])
        rol = rol_l + rol_l.mirror((0, 1, 0))
        sh = [Shape(ups + head, "paint_secondary", 40.0), Shape(rol, "steel", 40.0)]
        if sid == "mast_inner":
            z_head = z_stage + h - 35.0
            sheaves = K.Solid.union_all([K.cylinder(55.0, 30.0, segments=24).rotate(90, 0, 0).translate(x0 + d_ch / 2, sy * (lo - 25.0) + 15.0, z_stage + h + 55.0)
                                         for sy in (1, -1)])
            brk_h = box_at(x0 - 110.0, xa, -60.0, 60.0, z_stage + h - 80.0, z_stage + h)
            sh.append(Shape(sheaves + MC.pin(np.array([x0 - 60.0, 0, z_head]), (0, 1, 0), 45.0, 160.0), "steel", 40.0))
            sh[0] = Shape(ups + head + brk_h, "paint_secondary", 40.0)
        b.add(sid, "Trụ nâng trong" if sid == "mast_inner" else "Trụ nâng giữa", "Inner mast" if sid == "mast_inner" else "Middle mast", "mast", sh,
              parent_id=stage_ids[-1], required=True,
              aliases=["trụ trong", "trụ nâng trong", "mast", "khung nâng"] if sid == "mast_inner" else ["trụ giữa", "mast"],
              function="Trụ trượt lồng trong rãnh chữ C bằng con lăn, nâng bằng xi lanh + xích.", position_tag="front", joint_axis=(0, 0, 1),
              explode_dir=(0, 0, 1), explode_distance=400.0, explode_order=2)
        stage_ids.append(sid)
    # giá càng + càng
    x_c = x0 + d_ch + 10.0
    zc0 = hf - ft - 10.0
    car_plate = box_at(x_c, x_c + 60.0, -0.42 * W, 0.42 * W, zc0, zc0 + hc)
    bars = box_at(x_c + 60.0, x_c + 90.0, -0.42 * W, 0.42 * W, zc0 + hc - 60.0, zc0 + hc) + box_at(x_c + 60.0, x_c + 90.0, -0.42 * W, 0.42 * W, zc0, zc0 + 50.0)
    rest = K.Solid.union_all([box_at(x_c, x_c + 30.0, y - 20.0, y + 20.0, zc0 + hc, zc0 + hc + 900.0 * s) for y in np.linspace(-0.4 * W, 0.4 * W, 7)]
                             + [box_at(x_c, x_c + 30.0, -0.42 * W, 0.42 * W, zc0 + hc + 900.0 * s - 40.0, zc0 + hc + 900.0 * s)])
    r_hi = min(hi, y_c_in - 2.0)
    car_rol = K.Solid.union_all([box_at(xb_in - 30.0, x_c + 1.0, sy * lo, sy * r_hi, zc0 + 40.0, zc0 + 110.0) for sy in (1, -1)])
    chains = K.Solid.union_all([box_at(x0 + d_ch / 2 - 8.0, x0 + d_ch / 2 + 8.0, sy * (lo - 25.0) + 3.0, sy * (lo - 25.0) + 27.0, zc0 + hc - 30.0,
                                       z_head + 40.0) for sy in (1, -1)])
    b.add("carriage", f"Giá càng ISO 2328 cấp {cls} + tấm chắn tải", "Fork carriage & load backrest", "fork_carriage",
          [Shape(car_plate + bars + rest, "paint_secondary", 40.0), Shape(car_rol, "steel", 40.0), Shape(chains, "steel_dark", 40.0)],
          parent_id="mast_inner", required=True, aliases=["giá càng", "giá nâng", "tấm chắn tải", "xích nâng", "carriage"],
          function=f"Giá càng cấp {cls} (cao {hc:g} mm), tấm chắn tải, 2 xích nâng qua puly đầu trụ trong.", position_tag="front",
          joint_axis=(0, 0, 1), explode_dir=(1, 0, 0), explode_distance=500.0, explode_order=2)
    for side, sy in (("left", 1), ("right", -1)):
        yc = sy * 0.3 * W
        shank = box_at(x_c + 90.0, x_c + 90.0 + ft, yc - fw / 2, yc + fw / 2, hf - ft, zc0 + hc + 20.0)
        hook = box_at(x_c + 60.0, x_c + 90.0 + ft, yc - fw / 2, yc + fw / 2, zc0 + hc - 60.0, zc0 + hc + 20.0)
        blade = K.hull([box_at(x_c + 90.0, x_c + 90.0 + ft + 1.0, yc - fw / 2, yc + fw / 2, hf - ft, hf),
                        box_at(x_c + 90.0 + ft + Lfork - 1.0, x_c + 90.0 + ft + Lfork, yc - fw / 2 + 8.0, yc + fw / 2 - 8.0, hf - ft, hf - ft + 8.0),
                        box_at(x_c + 90.0 + ft + Lfork - 150.0, x_c + 90.0 + ft + Lfork - 149.0, yc - fw / 2, yc + fw / 2, hf - ft, hf)])
        b.add(f"fork_{side}", f"Càng nâng {'trái' if sy > 0 else 'phải'}", "Fork", "fork", Shape(shank + hook + blade, "steel_dark", 40.0),
              parent_id="carriage", required=True, aliases=["càng nâng", "càng", "lưỡi nâng", "fork", "chạc nâng"],
              function=f"Càng thép rèn ISO 2331: {fw:g} × {ft:g} mm, dài {Lfork:g} mm, mũi vát.", position_tag="front",
              explode_dir=(1, sy * 0.3, 0), explode_distance=400.0, explode_order=1, dimensions={"width": fw, "thickness": ft, "length": Lfork})
    # xi lanh
    for sy, pa, pb in ((1, tilt_pins[0], tilt_m[0]), (-1, tilt_pins[1], tilt_m[1])):
        rid = f"tilt_cylinder_{'left' if sy > 0 else 'right'}"
        r_ = MC.hyd_ram(pa, pb, 70.0, 40.0, barrel_frac=0.6)
        ram_info[rid] = [r_["closed"], r_["stroke"]]
        b.add(rid, f"Xi lanh nghiêng {'trái' if sy > 0 else 'phải'}", "Tilt cylinder", "hydraulic_cylinder",
              [Shape(r_["barrel"], "paint_secondary", 40.0), Shape(r_["rod"], "chrome", 40.0)], parent_id="chassis", required=True,
              aliases=["xi lanh nghiêng", "xi lanh", "ben nghiêng", "hydraulic cylinder"], function="Xi lanh nghiêng khung nâng (trước 6° / sau 12°).",
              position_tag="front", joint_axis=(0, 1, 0), explode_dir=(0, 0, 1), explode_distance=400.0, explode_order=1)
        contacts.append([rid, "mast_outer"])
        links += [[f"{rid}@chassis", pa, [rid, "chassis"]], [f"{rid}@mast", pb, [rid, "mast_outer"]]]
    pa, pb = p_lift0, np.array([x0 - 60.0, 0, z_head])
    r_ = MC.hyd_ram(pa, pb, 70.0 * s + 10.0, 50.0 * s + 5.0, pin_axis=(0, 1, 0), barrel_frac=0.55 if n_st == 2 else 0.5)
    ram_info["lift_cylinder"] = [r_["closed"], r_["stroke"]]
    b.add("lift_cylinder", "Xi lanh nâng", "Lift cylinder", "hydraulic_cylinder", [Shape(r_["barrel"], "paint_secondary", 40.0), Shape(r_["rod"], "chrome", 40.0)],
          parent_id="mast_outer", required=True, aliases=["xi lanh nâng", "xi lanh", "ben nâng", "lift cylinder"],
          function="Xi lanh nâng giữa khung: đẩy xà đầu trụ trong, xích nhân đôi hành trình cho giá càng.", position_tag="front",
          joint_axis=(0, 0, 1), explode_dir=(-1, 0, 0), explode_distance=300.0, explode_order=1)
    contacts.append(["lift_cylinder", "mast_inner"])
    links += [["lift@outer", pa, ["lift_cylinder", "mast_outer"]], ["lift@inner", pb, ["lift_cylinder", "mast_inner"]]]
    b.note_stage(1, "Tháo càng, bánh, xi lanh, ghế")
    b.note_stage(2, "Tháo giá càng, trụ trong, đối trọng, ắc quy/động cơ")
    b.note_stage(3, "Tháo khung nâng khỏi cầu trước")
    sh_ = np.asarray(b.place_on_ground(center_xy=True), float)
    b.metadata.update({"capacity_kg": Q, "power": "electric" if electric else "diesel", "fork_height_mm": hf, "fork_width_mm": fw,
                       "fork_thickness_mm": ft, "fork_length_mm": Lfork, "carriage_class": cls, "carriage_height_mm": hc, "load_center_mm": 500.0,
                       "mast_stages": n_st, "wheelbase_mm": wb, "front_tire": tf[0], "rear_tire": tr[0], "front_tire_d_mm": 2 * Rf,
                       "pin_links": [[n_, (np.asarray(c_, float) + sh_).tolist(), ids_] for n_, c_, ids_ in links], "rams": ram_info,
                       "standard": "ISO 2331 (càng), ISO 2328 (giá càng), ISO 6055 (khung bảo vệ); tâm tải 500 mm",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
