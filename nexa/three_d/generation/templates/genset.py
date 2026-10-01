"""Tổ máy phát điện diesel (10–1000 kVA), khung trần hoặc vỏ cách âm.

- Khung đế thép chữ C có bồn dầu liền đế (~8 giờ chạy), 4–6 đệm cao su chống rung đỡ cụm động cơ – đầu phát.
- Động cơ diesel thẳng hàng (4/6 xi lanh theo công suất): thân máy, nắp quy-lát + nắp dàn cò có gân, các te, cổ góp hút +
  lọc gió, cổ góp xả + tăng áp, két nước + quạt + lưới che phía trước; vỏ bánh đà (chuông SAE) nối đồng trục với đầu phát.
- Đầu phát (alternator) không chổi than có khe thông gió + hộp cực; tủ điều khiển trên giá (màn hình, nút, nút dừng khẩn);
  ắc quy khởi động; ống xả + bô giảm thanh (trên nóc khi có vỏ).
- Vỏ cách âm: khung + mái + hai đầu (cửa gió vào / cửa gió ra có lá chớp), 4 cửa hông tháo rời có bản lề, móc cẩu.
Kích thước theo công suất S (kVA): dài ≈ 2,4 m × (S/100)^0,33 (khung trần).
"""
from __future__ import annotations

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kva = float(p.get("power_kva", 100.0))
    canopy = p.get("enclosure", "canopy") == "canopy"
    s = (kva / 100.0) ** (1 / 3)
    ncyl = 4 if kva < 60 else (6 if kva < 700 else 12)
    mats = MC.tech_materials(spec, primary="#e8a317", secondary="#2b2d42", accent="#c1121f")
    b = AssemblyBuilder(spec.name or f"Máy phát điện diesel {kva:g} kVA" + (" vỏ cách âm" if canopy else ""), "generator_set", mats)
    contacts: list[list[str]] = []
    L = 2400.0 * s
    W = 850.0 * s
    Hb = 220.0 * s                                                    # cao khung đế (bồn dầu bên trong)
    # ---------- khung đế + bồn dầu ----------
    rails = K.Solid.union_all([box_at(-L / 2, L / 2, sy * W / 2 - sy * 100.0 * s, sy * W / 2, 0, Hb) for sy in (1, -1)]
                              + [box_at(x - 50.0 * s, x + 50.0 * s, -W / 2, W / 2, 0, Hb) for x in (-L / 2 + 50.0 * s, L / 2 - 50.0 * s)])
    tank = box_at(-0.42 * L, 0.42 * L, -W / 2 + 100.0 * s, W / 2 - 100.0 * s, 20.0, Hb)
    cap = K.cylinder(40.0 * s, 25.0 * s, segments=40).translate(-0.02 * L, 0.0, Hb)                 # nắp bồn dầu giữa hai ray phụ
    b.add("base_frame", "Khung đế + bồn dầu liền đế", "Base frame & fuel tank", "base",
          [Shape(rails, "paint_secondary", 35.0), Shape(tank, "paint_secondary", 35.0), Shape(cap, "steel_dark", 35.0)], required=True,
          aliases=["khung đế", "bồn dầu", "thùng nhiên liệu", "base frame", "fuel tank", "nắp bồn dầu"],
          function=f"Khung thép chữ C, bồn dầu liền đế ≈ {0.2 * kva * 8 * 0.27:.0f} lít (≈ 8 giờ chạy 75 % tải).", position_tag="bottom",
          dimensions={"length": L, "width": W})
    # ---------- đệm chống rung ----------
    h_iso = 70.0 * s
    xs_iso = [-0.35 * L, 0.05 * L, 0.3 * L] if kva >= 150 else [-0.3 * L, 0.2 * L]
    iso = K.Solid.union_all([K.cylinder(45.0 * s, h_iso, segments=40).translate(x, sy * 0.3 * W, Hb) for x in xs_iso for sy in (1, -1)])
    b.add("isolators", f"Đệm cao su chống rung ({2 * len(xs_iso)})", "Anti-vibration mounts", "isolator", Shape(iso, "rubber", 35.0),
          parent_id="base_frame", required=True, aliases=["đệm chống rung", "cao su chống rung", "chân đế cao su", "isolator"],
          function="Đệm cao su chống rung giữa cụm máy và khung đế.", position_tag="bottom", explode_dir=(0, 0, 1), explode_distance=150.0, explode_order=2)
    z0 = Hb + h_iso                                                    # mặt đáy khung phụ (bệ máy)
    # ---------- động cơ ----------
    rail2 = K.Solid.union_all([box_at(-0.36 * L, 0.38 * L, sy * 0.3 * W - 40.0 * s, sy * 0.3 * W + 40.0 * s, z0, z0 + 60.0 * s) for sy in (1, -1)])
    ex0, ex1 = -0.05 * L, 0.3 * L                                      # thân máy (x); két nước ở +X
    zc = z0 + 60.0 * s + 0.35 * W                                      # tâm trục khuỷu
    block = K.rounded_box(ex1 - ex0, 0.5 * W, 0.5 * W, 30.0 * s, segments=32).translate((ex0 + ex1) / 2, 0, zc)
    sump = K.hull([box_at(ex0 + 20.0, ex1 - 20.0, -0.2 * W, 0.2 * W, zc - 0.25 * W, zc - 0.25 * W + 1.0),
                   box_at(ex0 + 60.0, ex1 - 60.0, -0.14 * W, 0.14 * W, z0 + 60.0 * s, z0 + 61.0 * s)])
    head = K.rounded_box(ex1 - ex0 - 40.0, 0.36 * W, 0.16 * W, 20.0 * s, segments=32).translate((ex0 + ex1) / 2, 0.02 * W, zc + 0.33 * W)
    cover = K.rounded_box(ex1 - ex0 - 80.0, 0.28 * W, 0.1 * W, 25.0 * s, segments=32).translate((ex0 + ex1) / 2, 0.02 * W, zc + 0.46 * W)
    ribs = K.Solid.union_all([box_at(x - 6.0, x + 6.0, -0.12 * W, 0.16 * W, zc + 0.46 * W, zc + 0.53 * W)
                              for x in np.linspace(ex0 + 80.0, ex1 - 80.0, ncyl)])
    feet_e = K.Solid.union_all([box_at(x - 60.0 * s, x + 60.0 * s, sy * 0.3 * W - 40.0 * s, sy * 0.3 * W + 40.0 * s, z0 + 60.0 * s, zc - 0.2 * W)
                                for x in (ex0 + 80.0 * s, ex1 - 80.0 * s) for sy in (1, -1)])
    # hút: cổ góp + lọc gió; xả: cổ góp + tăng áp (bên trái +Y / phải −Y)
    intake = box_at(ex0 + 60.0, ex1 - 60.0, -0.25 * W - 60.0 * s, -0.25 * W, zc + 0.2 * W, zc + 0.3 * W)
    filt = K.cylinder(0.1 * W, 0.22 * L, segments=48).rotate(0, 90, 0).translate(ex0, -0.2 * W, zc + 0.62 * W) +         K.tube(np.array([[ex0 + 0.1 * L, -0.2 * W, zc + 0.55 * W], [ex0 + 0.1 * L, -0.25 * W - 30.0 * s, zc + 0.3 * W]]), 0.04 * W, 24)
    exman = box_at(ex0 + 60.0, ex1 - 60.0, 0.25 * W, 0.25 * W + 50.0 * s, zc + 0.12 * W, zc + 0.2 * W)
    tx = ex1 - 0.3 * (ex1 - ex0)                                      # tăng áp ở nửa trước (tránh trụ giữa vỏ)
    turbo = K.revolve([(0, 0), (0.09 * W, 0), (0.1 * W, 0.04 * W), (0.08 * W, 0.12 * W), (0, 0.12 * W)], segments=48).rotate(-90, 0, 0).translate(
        tx, 0.25 * W + 50.0 * s - 2.0, zc + 0.26 * W)
    # két nước + quạt + lưới
    xr = ex1 + 0.12 * L
    rad_h = 0.8 * (zc + 0.45 * W - z0)
    core = box_at(xr - 0.035 * L, xr + 0.035 * L, -0.38 * W, 0.38 * W, z0 + 60.0 * s, z0 + 60.0 * s + rad_h)
    fins = K.Solid.union_all([box_at(xr + 0.035 * L, xr + 0.035 * L + 4.0, -0.4 * W, 0.4 * W, z, z + 3.0) for z in np.linspace(z0 + 90.0 * s, z0 + rad_h, 24)])
    tank_r = box_at(xr - 0.04 * L, xr + 0.04 * L, -0.4 * W, 0.4 * W, z0 + 60.0 * s + rad_h, z0 + 60.0 * s + rad_h + 60.0 * s)
    shroud = (K.cylinder(0.33 * rad_h, 0.06 * L, segments=40) - K.cylinder(0.31 * rad_h, 0.07 * L, segments=40).translate(0, 0, -1)).rotate(0, 90, 0).translate(
        xr - 0.035 * L - 0.06 * L, 0, z0 + 60.0 * s + rad_h / 2)
    fan = K.Solid.union_all([K.box(8.0, 0.55 * rad_h, 0.12 * rad_h).rotate(30.0, 0, a).translate(xr - 0.035 * L - 0.03 * L, 0, z0 + 60.0 * s + rad_h / 2)
                             for a in np.arange(0, 360, 60.0)])
    hub_f = K.cylinder(0.04 * rad_h, (xr - 0.035 * L - 0.03 * L) - ex1 + 10.0, segments=24).rotate(0, 90, 0).translate(ex1 - 10.0, 0, z0 + 60.0 * s + rad_h / 2)
    guard = K.Solid.union_all([box_at(xr + 0.035 * L + 20.0, xr + 0.035 * L + 26.0, -0.38 * W, 0.38 * W, z, z + 6.0)
                               for z in np.linspace(z0 + 80.0 * s, z0 + rad_h, 10)] +
                              [box_at(xr + 0.035 * L + 4.0, xr + 0.035 * L + 26.0, sy * 0.38 * W - 6.0, sy * 0.38 * W, z0 + 60.0 * s, z0 + 60.0 * s + rad_h) for sy in (1, -1)])
    rad_sup = K.Solid.union_all([box_at(xr - 0.04 * L, xr + 0.04 * L, sy * 0.3 * W - 40.0 * s, sy * 0.3 * W + 40.0 * s, z0, z0 + 60.0 * s) for sy in (1, -1)])
    b.add("engine", f"Động cơ diesel {ncyl} xi lanh + két nước", "Diesel engine & radiator", "engine",
          [Shape(block + sump + head + feet_e, "paint_primary", 35.0), Shape(cover + ribs, "paint_secondary", 35.0),
           Shape(intake + filt, "steel_dark", 35.0), Shape(exman + turbo, "cast_iron", 35.0),
           Shape(core + tank_r, "aluminum_dark", 35.0), Shape(fins + guard, "steel", 35.0), Shape(shroud + fan + hub_f, "plastic_black", 35.0),
           Shape(rail2 + rad_sup, "paint_secondary", 35.0)], parent_id="isolators", required=True,
          aliases=["động cơ", "máy nổ", "động cơ diesel", "két nước", "quạt két nước", "tăng áp", "lọc gió", "engine", "radiator"],
          function=f"Động cơ diesel 4 kỳ {ncyl} xi lanh thẳng hàng tăng áp, két nước + quạt thổi ra phía trước.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.35 * W, explode_order=3)
    # ---------- vỏ bánh đà + đầu phát ----------
    xb0 = ex0 - 0.05 * L
    bell = K.cylinder(0.3 * W, 0.05 * L, 0.26 * W, segments=48).rotate(0, 90, 0).translate(xb0, 0, zc)
    xa1 = xb0
    xa0 = xa1 - 0.24 * L
    Ra = 0.3 * W
    alt = K.cylinder(Ra, xa1 - xa0, segments=48).rotate(0, 90, 0).translate(xa0, 0, zc)
    slots = K.Solid.union_all([K.box(0.08 * L, 20.0, 0.4 * W).translate(xa0 + 0.08 * L, 0, zc).rotate_axis((1, 0, 0), a, (0, 0, zc))
                               for a in np.arange(0, 180, 30.0)])
    alt = alt - slots
    endcap = K.cylinder(0.26 * W, 0.03 * L, segments=48).rotate(0, 90, 0).translate(xa0 - 0.03 * L, 0, zc)
    tbox = box_at(xa0 + 0.05 * L, xa0 + 0.2 * L, -0.18 * W, 0.18 * W, zc + Ra - 10.0, zc + Ra + 0.25 * W)
    feet_a = K.Solid.union_all([box_at(xa0 + 0.02 * L, xa0 + 0.1 * L, sy * 0.3 * W - 40.0 * s, sy * 0.3 * W + 40.0 * s, z0, zc - Ra * 0.6)
                                for sy in (1, -1)])
    b.add("alternator", "Đầu phát không chổi than + vỏ bánh đà", "Brushless alternator", "alternator",
          [Shape(alt + endcap + feet_a, "paint_blue", 35.0), Shape(bell, "cast_aluminum", 35.0), Shape(tbox, "paint_blue", 35.0)], parent_id="isolators",
          required=True, aliases=["đầu phát", "củ phát", "máy phát", "alternator", "hộp cực", "vỏ bánh đà"],
          function="Đầu phát đồng bộ không chổi than 3 pha 400 V 50 Hz, AVR, nối đồng trục qua chuông SAE.", position_tag="rear",
          joint_axis=(1, 0, 0), explode_dir=(-1, 0, 0), explode_distance=0.25 * L, explode_order=2)
    contacts += [["alternator", "engine"]]
    # ---------- tủ điều khiển + ắc quy ----------
    pan_x = xa0 + 0.1 * L
    post = box_at(pan_x - 25.0, pan_x + 25.0, -25.0, 25.0, zc + Ra + 0.25 * W, zc + Ra + 0.25 * W + 120.0 * s)
    panel = K.rounded_box(0.12 * L, 0.45 * W, 0.4 * W, 15.0, segments=32).translate(pan_x, 0, zc + Ra + 0.25 * W + 120.0 * s + 0.2 * W)
    scr = box_at(pan_x + 0.06 * L, pan_x + 0.06 * L + 2.0, -0.1 * W, 0.1 * W, zc + Ra + 0.25 * W + 120.0 * s + 0.25 * W, zc + Ra + 0.25 * W + 120.0 * s + 0.33 * W)
    es = MC.orient(K.cylinder(0.025 * W, 12.0, segments=20), [pan_x + 0.06 * L, 0.15 * W, zc + Ra + 0.25 * W + 120.0 * s + 0.1 * W], (1, 0, 0))
    b.add("control_panel", "Tủ điều khiển (màn hình + dừng khẩn)", "Control panel", "control_panel",
          [Shape(panel + post, "paint_secondary", 35.0), Shape(scr, "glass_tinted", 35.0), Shape(es, "paint_red", 35.0)], parent_id="alternator",
          required=True, aliases=["tủ điều khiển", "bảng điều khiển", "màn hình", "nút dừng khẩn", "control panel"],
          function="Bộ điều khiển tự động (khởi động/dừng, đo V-A-Hz, bảo vệ), nút dừng khẩn cấp.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.3 * W, explode_order=1)
    bat = box_at(-0.48 * L, -0.39 * L, -0.35 * W, -0.05 * W, Hb, Hb + 0.25 * W)             # đuôi khung đế, sau đầu phát
    b.add("battery", "Ắc quy khởi động 24 V", "Starter battery", "battery", Shape(bat, "plastic_black", 35.0), parent_id="base_frame", required=True,
          aliases=["ắc quy", "bình điện", "battery"], function="2 bình ắc quy 12 V nối tiếp khởi động.", position_tag="rear",
          explode_dir=(0, -1, 0), explode_distance=0.5 * W, explode_order=1)
    # ---------- ống xả ----------
    z_top_c = zc + Ra + 0.25 * W + 120.0 * s + 0.4 * W + 100.0      # đỉnh tủ + khe
    H_c = z_top_c + 60.0 * s if canopy else None
    t_c = np.array([tx, 0.25 * W + 50.0 * s + 0.06 * W, zc + 0.26 * W])            # tâm tăng áp (ống xả bắt đầu trong vỏ tăng áp)
    muff_z = zc + 0.62 * W
    ex_up = K.tube(np.array([t_c, t_c + [0, 0, 0.3 * W], [tx, 0.2 * W, muff_z]]), 0.05 * W, 24)
    x_m0 = tx - 0.3 * L
    muff = K.cylinder(0.08 * W, 0.28 * L, segments=48).rotate(0, 90, 0).translate(x_m0, 0.2 * W, muff_z)
    link = K.tube(np.array([[tx, 0.2 * W, muff_z], [tx - 0.03 * L, 0.2 * W, muff_z]]), 0.05 * W, 24)
    tail = K.tube(np.array([[x_m0 + 20.0, 0.2 * W, muff_z], [x_m0 - 60.0, 0.2 * W, muff_z],
                            [x_m0 - 60.0, 0.2 * W, (H_c + 150.0) if canopy else muff_z + 0.3 * W]]), 0.045 * W, 24)
    b.add("exhaust", "Ống xả + bô giảm thanh", "Exhaust & silencer", "pipe", [Shape(ex_up + link + tail, "steel_dark", 35.0), Shape(muff, "stainless", 35.0)],
          parent_id="engine", required=True, aliases=["ống xả", "bô", "bô giảm thanh", "exhaust", "silencer"],
          function="Ống xả mềm + bô giảm thanh kiểu công nghiệp" + (", thoát lên nóc vỏ." if canopy else "."), position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.4 * W, explode_order=1)
    meta = {}
    if canopy:
        # vỏ: khung (4 trụ góc + dầm mái) + mái + 2 đầu có lá chớp; 4 cửa hông tháo rời
        t = 2.5 * s + 1.0
        Lc, Wc = L + 20.0, W + 20.0
        cx0, cx1, cy = -Lc / 2, Lc / 2, Wc / 2
        zc0 = Hb
        posts = K.Solid.union_all([box_at(x - 40.0, x + 40.0, sy * cy - sy * 40.0, sy * cy, zc0, H_c) for x in (cx0 + 40.0, cx1 - 40.0, 0.0) for sy in (1, -1)])
        roof = box_at(cx0, cx1, -cy, cy, H_c, H_c + t)
        roof = roof - K.cylinder(0.05 * W, 3 * t + 20, segments=24).translate(x_m0 - 60.0, 0.2 * W, H_c - 10.0)
        endf = box_at(cx1 - t, cx1, -cy, cy, zc0, H_c)
        louv = K.Solid.union_all([box_at(cx1 - t - 1.0, cx1 + 1.0, -0.4 * W, 0.4 * W, z, z + 40.0 * s) for z in np.linspace(zc0 + 150.0, H_c - 150.0, 8)])
        endf = endf - louv
        blades = K.Solid.union_all([box_at(cx1 - 30.0, cx1, -0.4 * W, 0.4 * W, z, z + 4.0).rotate_axis((0, 1, 0), -30.0, (cx1, 0, z)) for z in np.linspace(zc0 + 150.0, H_c - 150.0, 8)])
        endr = box_at(cx0, cx0 + t, -cy, cy, zc0, H_c)
        louv_r = K.Solid.union_all([box_at(cx0 - 1.0, cx0 + t + 1.0, -0.4 * W, 0.4 * W, z, z + 40.0 * s) for z in np.linspace(zc0 + 150.0, H_c - 150.0, 8)])
        endr = endr - louv_r
        eyes = K.Solid.union_all([K.torus(40.0, 10.0, segments=20, tube_segments=32).rotate(90, 0, 0).translate(x, 0, H_c + t + 40.0) for x in (cx0 + 0.2 * Lc, cx1 - 0.2 * Lc)])
        b.add("canopy", "Vỏ cách âm (khung, mái, cửa gió)", "Sound-attenuated canopy", "canopy_frame",
              [Shape(posts + roof + endf + endr, "paint_primary", 35.0), Shape(blades, "paint_secondary", 35.0), Shape(eyes, "steel", 35.0)],
              parent_id="base_frame", required=True, aliases=["vỏ cách âm", "vỏ máy", "mái", "cửa gió", "lá chớp", "móc cẩu", "canopy"],
              function="Vỏ thép sơn tĩnh điện lót bông cách âm, cửa gió vào (sau) / ra (trước, trước két nước) có lá chớp, 2 móc cẩu.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.8 * H_c, explode_order=4, dimensions={"height": H_c + t})
        contacts += [["exhaust", "canopy"]]
        doors = []
        for side, sy in (("left", 1), ("right", -1)):
            for pos, (xa, xb) in (("rear", (cx0 + 80.0, -40.0)), ("front", (40.0, cx1 - 80.0))):
                d = box_at(xa + 3.0, xb - 3.0, sy * cy - sy * t, sy * cy, zc0 + 3.0, H_c - 3.0)
                handle = box_at((xa + xb) / 2 - 60.0, (xa + xb) / 2 + 60.0, sy * cy, sy * (cy + 20.0), zc0 + 0.55 * (H_c - zc0), zc0 + 0.55 * (H_c - zc0) + 25.0)
                hinge = box_at(xa - 37.0 if pos == "rear" else xb - 3.0, xa + 3.0 if pos == "rear" else xb + 37.0, sy * cy - sy * t, sy * cy,
                               zc0 + 0.2 * (H_c - zc0), zc0 + 0.2 * (H_c - zc0) + 60.0)
                doors.append((f"door_{pos}_{side}", d + hinge, handle, sy, pos))
        for pid, d, h, sy, pos in doors:
            b.add(pid, f"Cửa hông {'sau' if pos == 'rear' else 'trước'} {'trái' if sy > 0 else 'phải'}", "Service door", "door",
                  [Shape(d, "paint_primary", 35.0), Shape(h, "steel_dark", 35.0)], parent_id="canopy", required=True,
                  aliases=["cửa", "cửa hông", "cửa bảo dưỡng", "door"], function="Cửa bảo dưỡng có khóa, gioăng cao su.", position_tag="left" if sy > 0 else "right",
                  joint_axis=(0, 0, 1), explode_dir=(0, sy, 0), explode_distance=0.3 * W, explode_order=1)
        meta["canopy_height_mm"] = H_c + t
    b.note_stage(1, "Tháo cửa, ống xả, tủ điều khiển, ắc quy")
    b.note_stage(2, "Tháo đầu phát")
    b.note_stage(3, "Nhấc động cơ")
    if canopy:
        b.note_stage(4, "Nhấc vỏ cách âm")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"power_kva": kva, "enclosure": "canopy" if canopy else "open", "cylinders": ncyl, "length_mm": L, "width_mm": W,
                       "crank_axis_z_mm": zc, "isolators": 2 * len(xs_iso), **meta,
                       "standard": "Tổ máy phát diesel ISO 8528 (tỷ lệ tổ 100 kVA ~ 2,4 × 0,85 m khung trần)",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
