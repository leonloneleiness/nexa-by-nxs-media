"""Robot hút bụi (kiểu Roborock/iRobot): thân tròn Ø250–420 mm, cao ~0,27·D, tháp LiDAR LDS trên nóc, cản trước hình
cung, 2 bánh chủ động trong hốc có lò xo treo, bánh xoay phía trước, chổi cạnh 3 nhánh, chổi chính cao su xoắn trong
khung chắn, khay bụi tháo phía sau có lưới lọc, 4–6 cảm biến chống rơi (hồng ngoại) ở mép đáy, 2 tiếp điểm sạc, nắp pin,
3 nút + đèn trên nóc, tùy chọn tấm lau + bình nước, đế sạc (dốc, tháp có tiếp điểm + cửa sổ hồng ngoại).

Tỷ lệ theo sản phẩm thật: Roborock S7 Ø353 × 96,5 mm, bánh Ø≈70 mm, chổi chính rộng ≈ 170 mm, khe gầm ≈ 9 mm.
Tháo: nhấc nắp trên → tháo tháp LiDAR, khay bụi, nút → gỡ cản trước → tháo chổi cạnh, chổi chính, bánh xoay, bánh chủ động.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import details as D
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    Dm = float(p.get("diameter_mm", 350.0))
    R = Dm / 2
    mats = MC.tech_materials(spec, primary="#eef0f2", secondary="#1b1c1f", accent="#2f9be0")
    b = AssemblyBuilder(spec.name or "Robot hút bụi", "robot_vacuum", mats)
    c = 0.026 * Dm                       # khe gầm
    hb = 0.215 * Dm                      # cao thân (không kể LiDAR)
    z_split = c + 0.7 * hb
    z_top = c + hb
    bt = 0.03 * Dm                       # dày cản
    Rc = R - bt                          # bán kính thân sau cản (vùng phía trước)
    seg = 160
    a_b = math.radians(80)               # cản ôm ±80° phía trước
    # ---------- khung gầm ----------
    body = K.revolve(P.fillet_polygon([(0, c), (R, c), (R, z_split), (0, z_split)], [0, 0.012 * Dm, 0, 0], 4), segments=seg)
    front = K.extrude(np.array([[0, 0]] + [(2 * R * math.cos(a), 2 * R * math.sin(a)) for a in np.linspace(-a_b, a_b, 24)]), z_split + 2).translate(0, 0, -1)
    body = (body - front) + (K.revolve(P.fillet_polygon([(0, c), (Rc, c), (Rc, z_split), (0, z_split)], [0, 0.01 * Dm, 0, 0], 4), segments=seg) & front)
    # hốc bánh chủ động, bánh xoay, chổi chính, khay bụi, cảm biến rơi, tiếp điểm sạc
    rw, ww = 0.1 * Dm, 0.065 * Dm
    xw, yw = -0.02 * Dm, R - 0.13 * Dm
    wells = [K.rounded_box(2 * rw + 0.02 * Dm, ww + 0.02 * Dm, 2 * rw + 0.03 * Dm, 0.01 * Dm).translate(xw, s * yw, rw) for s in (1, -1)]
    rcst = 0.034 * Dm
    xc = 0.33 * Dm
    caster_well = K.cylinder(rcst + 0.012 * Dm, 2 * rcst + 0.03 * Dm, segments=48).translate(xc, 0, -0.01 * Dm)
    xb, wb, rbr = 0.08 * Dm, 0.5 * Dm, 0.045 * Dm
    brush_well = K.rounded_box(2 * rbr + 0.02 * Dm, wb + 0.03 * Dm, 2 * rbr + 0.02 * Dm, 0.01 * Dm).translate(xb, 0, rbr + 0.003 * Dm)
    xd, bin_l, bin_w, bin_h = -0.25 * Dm, 0.22 * Dm, 0.5 * Dm, 0.42 * hb
    bin_pocket = K.rounded_box(bin_l, bin_w, bin_h + 1, 0.02 * Dm).translate(xd, 0, z_split - bin_h / 2 + 0.5)
    body = body.subtract_all(wells + [caster_well, brush_well, bin_pocket])
    body = body - D.panel_lines(body, [("z", c + 0.35 * hb)], width=0.003 * Dm, depth=0.002 * Dm)
    cliff = []
    for ang in (15, -15, 60, -60, 125, -125):
        a = math.radians(ang)
        rr = R - 0.045 * Dm if abs(ang) > 80 else Rc - 0.04 * Dm
        cliff.append(K.rounded_box(0.028 * Dm, 0.014 * Dm, 0.006 * Dm, 0.003 * Dm).rotate(0, 0, ang).translate(rr * math.cos(a), rr * math.sin(a), c + 0.0015 * Dm))
    cliff_s = K.Solid.union_all(cliff)
    body = body - cliff_s.translate(0, 0, 0.0005 * Dm)
    contacts_s = K.Solid.union_all([K.rounded_box(0.05 * Dm, 0.018 * Dm, 0.002 * Dm, 0.001 * Dm).translate(-0.4 * Dm, s * 0.07 * Dm, c - 0.001 * Dm)
                                    for s in (1, -1)])
    batt = K.rounded_box(0.2 * Dm, 0.26 * Dm, 0.004 * Dm, 0.01 * Dm).translate(-0.08 * Dm, 0, c + 0.001 * Dm) - \
        K.rounded_box(0.19 * Dm, 0.25 * Dm, 0.01 * Dm, 0.009 * Dm).translate(-0.08 * Dm, 0, c + 0.001 * Dm)
    body = body - batt
    scr = D.screws_at([(-0.08 * Dm + sx * 0.085 * Dm, sy * 0.11 * Dm, c) for sx in (1, -1) for sy in (1, -1)], (0, 0, -1), 0.008 * Dm)
    b.add("chassis", "Khung gầm (vỏ dưới)", "Chassis", "chassis",
          [Shape(body, "plastic_black", 40.0), Shape(contacts_s, "steel", 40.0), Shape(scr, "steel_black_oxide", 40.0),
           Shape(cliff_s, "glass_tinted", 40.0)], required=True,
          aliases=["khung gầm", "vỏ dưới", "đáy", "chassis", "tiếp điểm sạc", "nắp pin", "cảm biến chống rơi"],
          function="Khung gầm ABS: hốc bánh, chổi chính, bánh xoay, khay bụi; nắp pin 4 vít; 2 tiếp điểm sạc; 6 cảm biến chống rơi.",
          position_tag="bottom", dimensions={"diameter": Dm})
    # ---------- nắp trên (vỏ mỏng) ----------
    outer = K.revolve(P.fillet_polygon([(0, z_split), (R, z_split), (R, z_top - 0.02 * Dm), (R - 0.03 * Dm, z_top), (0, z_top)],
                                       [0, 0, 0.012 * Dm, 0.03 * Dm, 0], 6), segments=seg)
    outer = (outer - front) + (K.revolve(P.fillet_polygon([(0, z_split), (Rc, z_split), (Rc, z_top - 0.02 * Dm), (Rc - 0.03 * Dm, z_top), (0, z_top)],
                                                          [0, 0, 0.012 * Dm, 0.03 * Dm, 0], 6), segments=seg) & front)
    wall = 0.008 * Dm
    inner = K.revolve([(0, z_split - 1), (R - wall, z_split - 1), (R - wall, z_top - wall), (0, z_top - wall)], segments=seg)
    inner = (inner - front) + (K.revolve([(0, z_split - 1), (Rc - wall, z_split - 1), (Rc - wall, z_top - wall), (0, z_top - wall)], segments=seg) & front)
    cover = outer - inner
    xl, rl = 0.1 * Dm, 0.115 * Dm
    cover = cover - K.cylinder(rl + 0.004 * Dm, hb, segments=96).translate(xl, 0, z_split)
    ring_groove = (K.rounded_box(bin_l + 0.04 * Dm, bin_w * 0.9, hb, 0.03 * Dm) - K.rounded_box(bin_l + 0.034 * Dm, bin_w * 0.9 - 0.006 * Dm, hb * 2, 0.027 * Dm)).translate(xd, 0, z_top)
    cover = cover - (ring_groove & K.cylinder(R * 2, hb, segments=16).translate(0, 0, z_top - 0.002 * Dm))
    btn_x = [0.3 * Dm, 0.3 * Dm, 0.3 * Dm]
    btn_y = [0.06 * Dm, 0.0, -0.06 * Dm]
    for x_, y_ in zip(btn_x, btn_y):
        cover = cover - K.cylinder(0.018 * Dm, 0.05 * Dm, segments=32).translate(x_, y_, z_top - 0.03 * Dm)
    b.add("top_cover", "Nắp trên", "Top cover", "shell", Shape(cover, "paint_primary", 50.0), parent_id="chassis", required=True,
          aliases=["nắp trên", "vỏ trên", "vỏ", "top cover", "nắp khay bụi"], function="Vỏ trên sơn bóng, nắp khay bụi, lỗ tháp LiDAR.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.35 * Dm, explode_order=1)
    btn = []
    for x_, y_ in zip(btn_x, btn_y):
        zt = D.surface_at(outer, "z", (x_, y_, 0), True) or z_top
        btn.append(K.revolve(P.fillet_polygon([(0, zt - 0.03 * Dm), (0.0178 * Dm, zt - 0.03 * Dm), (0.0178 * Dm, zt + 0.002 * Dm),
                                               (0, zt + 0.004 * Dm)], [0, 0, 0.003 * Dm, 0], 3), segments=32).translate(x_, y_, 0))
    ledr = K.torus(0.0215 * Dm, 0.0015 * Dm, segments=48, tube_segments=8).translate(btn_x[1], btn_y[1], (D.surface_at(outer, "z", (btn_x[1], btn_y[1] + 0.0215 * Dm, 0), True) or z_top))
    b.add("buttons", "Nút nguồn / về sạc / làm sạch điểm", "Buttons", "button",
          [Shape(K.Solid.union_all(btn), "plastic_gray", 40.0), Shape(ledr & K.Solid.union_all([K.cylinder(0.03 * Dm, Dm, segments=32).translate(btn_x[1], btn_y[1], 0)]), "led_white", 40.0)],
          parent_id="top_cover", required=True, aliases=["nút", "nút nguồn", "nút về sạc", "button", "đèn báo"],
          function="3 nút: nguồn, về đế sạc, làm sạch điểm; vòng đèn trạng thái.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.15 * Dm, explode_order=2)
    # ---------- tháp LiDAR ----------
    if p.get("lidar", True):
        base_z = z_split + 0.2 * hb
        lh = z_top - base_z + 0.032 * Dm
        lds = C.lidar_puck(2 * rl, lh)
        b.add("lidar", "Tháp LiDAR (LDS)", "LiDAR turret", "lidar", [Shape(sh.solid.translate(xl, 0, base_z), sh.material, 40.0) for sh in lds],
              parent_id="lidar_mount", required=True, aliases=["lidar", "tháp lidar", "cảm biến laser", "lds", "mắt đọc"],
              function="Cảm biến laser quay 360° (LDS) lập bản đồ SLAM, tầm ~8 m.", position_tag="top",
              explode_dir=(0, 0, 1), explode_distance=0.55 * Dm, explode_order=2)
        pedestal = K.cylinder(rl * 0.8, base_z - z_split + 0.001, segments=64).translate(xl, 0, z_split - 0.0005)
        b.add("lidar_mount", "Đế tháp LiDAR", "LiDAR mount", "frame", Shape(pedestal, "plastic_black", 40.0), parent_id="chassis",
              aliases=["đế lidar", "trụ lidar"], function="Trụ giảm chấn đỡ LDS.", position_tag="top",
              explode_dir=(0, 0, 1), explode_distance=0.3 * Dm, explode_order=3)
    # ---------- cản trước ----------
    bump = K.revolve([(Rc, c + 0.12 * hb), (R, c + 0.12 * hb), (R, z_split + 0.2 * hb), (Rc, z_split + 0.2 * hb)], segments=seg) & front
    bump = bump & K.revolve([(0, 0), (R, 0), (R, z_top - 0.02 * Dm), (0, z_top)], segments=seg)
    windows = [K.box(0.02 * Dm, 0.05 * Dm, 0.02 * Dm).rotate(0, 0, ang).translate(R * math.cos(math.radians(ang)), R * math.sin(math.radians(ang)), c + 0.4 * hb)
               for ang in (0, 35, -35)]
    win_s = K.Solid.union_all(windows) & bump
    bump = bump - win_s
    b.add("bumper", "Cản trước", "Front bumper", "bumper", [Shape(bump, "plastic_black", 40.0), Shape(win_s, "glass_tinted", 40.0)],
          parent_id="chassis", required=True, aliases=["cản trước", "cản va", "bumper", "cảm biến va chạm", "cửa sổ hồng ngoại"],
          function="Cản trước lò xo + công tắc va chạm, cửa sổ cảm biến tường/chướng ngại.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=0.25 * Dm, explode_order=3)
    # đỉnh cản không được chạm nắp trên: cản thấp hơn mặt phân chia + 0,2hb, nắp trên phía trước bắt đầu ở Rc
    # ---------- bánh chủ động + treo ----------
    contacts = [["bumper", "top_cover"], ["drive_wheel_*", "chassis"]]
    for s, tag, vi in ((1, "left", "trái"), (-1, "right", "phải")):
        tire, rim = C.wheel(2 * rw, ww, spokes=5, rim_material="plastic_gray", tire_material="rubber")
        shapes = [Shape(sh.solid.translate(xw, s * yw, rw), sh.material, 40.0) for sh in tire + rim]
        axle = K.cylinder(0.012 * Dm, 0.02 * Dm, segments=24).rotate(90, 0, 0).translate(xw, s * (yw - s * (ww / 2 + 0.01 * Dm)) + s * 0.01 * Dm, rw)
        arm = K.rounded_box(0.12 * Dm, 0.012 * Dm, 0.03 * Dm, 0.005 * Dm).translate(xw + 0.04 * Dm, s * (yw - ww / 2 - 0.016 * Dm), rw + 0.02 * Dm)
        spring = K.tube(MC.helix_path(0.008 * Dm, [(5, 0.008 * Dm)], z0=0.0), 0.0015 * Dm, 8).translate(xw + 0.09 * Dm, s * (yw - ww / 2 - 0.016 * Dm), rw + 0.035 * Dm)
        shapes.append(Shape(axle, "plastic_gray", 40.0))
        # tay treo + lò xo đứng yên trên khung, tách khỏi bánh để không quay theo bánh
        b.add(f"wheel_arm_{tag}", f"Tay treo bánh {vi}", f"Wheel suspension arm {tag}", "arm",
              [Shape(arm, "plastic_gray", 40.0), Shape(spring, "spring_steel", 40.0)], parent_id="chassis",
              aliases=["tay treo", "lò xo treo", f"treo bánh {vi}", "suspension"],
              function="Tay treo lò xo giữ bánh bám sàn, vượt thảm/bậc 2 cm.", position_tag=tag,
              explode_dir=(0, s, 0.3), explode_distance=0.18 * Dm, explode_order=4)
        b.add(f"drive_wheel_{tag}", f"Bánh chủ động {vi}", f"Drive wheel {tag}", "wheel", shapes, parent_id=f"wheel_arm_{tag}",
              required=True, aliases=["bánh xe", "bánh chủ động", f"bánh {vi}", "wheel"],
              function="Bánh cao su gai + motor hộp số.", position_tag=tag,
              explode_dir=(0, s, -0.3), explode_distance=0.25 * Dm, explode_order=4)
        contacts += [[f"wheel_arm_{tag}", "chassis"], [f"drive_wheel_{tag}", f"wheel_arm_{tag}"]]
    # ---------- bánh xoay ----------
    cw = C.wheel(2 * rcst, 0.03 * Dm, spokes=4, rim_material="plastic_gray", tire_material="rubber_gray", tread=False)
    fork = K.rounded_box(0.012 * Dm, 0.045 * Dm, rcst + 0.02 * Dm, 0.004 * Dm)
    fork = K.Solid.union_all([fork.translate(0, s * 0.022 * Dm, rcst + 0.01 * Dm) for s in (1, -1)]) + \
        K.cylinder(0.02 * Dm, 0.02 * Dm, segments=32).translate(0, 0, 2 * rcst + 0.012 * Dm)
    fork = fork - K.cylinder(rcst * 1.02, 0.04 * Dm, segments=32).rotate(90, 0, 0).translate(0, 0.02 * Dm, rcst)
    cshapes = [Shape(sh.solid.translate(xc, 0, rcst), sh.material, 40.0) for sh in cw[0] + cw[1]] + [Shape(fork.translate(xc, 0, 0), "plastic_black", 40.0)]
    b.add("caster", "Bánh xoay trước", "Front caster", "caster", cshapes, parent_id="chassis", required=True,
          aliases=["bánh xoay", "bánh trước", "caster", "bánh dẫn hướng"], function="Bánh xoay 360° đỡ phía trước.",
          position_tag="front", explode_dir=(0, 0, -1), explode_distance=0.15 * Dm, explode_order=4)
    contacts.append(["caster", "chassis"])
    # ---------- chổi chính ----------
    zb = rbr + 0.004 * Dm
    roller = K.cylinder(rbr * 0.45, wb, segments=32).rotate(90, 0, 0).translate(xb, wb / 2, zb)
    flaps = []
    for k in range(4):
        rfl = rbr - 0.012 * Dm                             # cánh cao su chạm gần sàn (cách ~1,4 mm), không xuyên sàn
        pts = [(xb + rfl * math.cos(math.radians(90 * k) + t * 1.2), -wb / 2 + t * wb * 0.98 + 0.01 * wb,
                zb + rfl * math.sin(math.radians(90 * k) + t * 1.2)) for t in np.linspace(0, 1, 12)]
        flaps.append(K.tube(np.asarray(pts), 0.012 * Dm, 8, rounded_ends=True))
    fl_s = K.Solid.union_all(flaps)
    guard = K.rounded_box(2 * rbr + 0.02 * Dm, wb + 0.03 * Dm, 0.004 * Dm, 0.004 * Dm).translate(xb, 0, c + 0.002 * Dm)
    guard = guard - K.Solid.union_all([K.box(0.018 * Dm, wb * 0.95, 0.02 * Dm).translate(xb + (k - 1.5) * 0.024 * Dm, 0, c) for k in range(4)])
    b.add("main_brush", "Chổi chính cao su", "Main brush", "brush",
          [Shape(roller, "plastic_gray", 40.0), Shape(fl_s, "rubber_gray", 40.0)],
          parent_id="chassis", required=True, aliases=["chổi chính", "chổi cuốn", "main brush"],
          function="Chổi cao su xoắn nổi, cuốn bụi vào khay.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=0.12 * Dm, explode_order=4)
    b.add("brush_guard", "Khung chắn chổi", "Brush guard", "guard", Shape(guard, "plastic_black", 40.0),
          parent_id="chassis", aliases=["khung chắn chổi", "brush guard"], function="Khung chắn đứng yên bảo vệ sàn quanh chổi chính.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.2 * Dm, explode_order=4)
    contacts += [["main_brush", "chassis"], ["brush_guard", "chassis"], ["main_brush", "brush_guard"]]
    # ---------- chổi cạnh ----------
    nsb = int(p.get("side_brushes", 1))
    for k, s in enumerate([-1, 1][:nsb]):
        cx_, cy_ = 0.27 * Dm, s * 0.27 * Dm
        hub = K.cylinder(0.022 * Dm, 0.012 * Dm, segments=32).translate(cx_, cy_, c - 0.012 * Dm)
        arms = []
        for j in range(3):
            a = math.radians(120 * j + 20 * s)
            L_ = 0.2 * Dm
            p0 = np.array([cx_, cy_, c - 0.008 * Dm])
            p1 = p0 + np.array([L_ * math.cos(a), L_ * math.sin(a), -(c - 0.012 * Dm) + 0.004 * Dm])
            arms.append(K.tube(np.array([p0, (p0 + p1) / 2 + [0, 0, 0.003 * Dm], p1]), 0.0035 * Dm, 8, rounded_ends=True))
        b.add(f"side_brush_{k + 1}", "Chổi cạnh" + (f" {k + 1}" if nsb > 1 else ""), "Side brush", "brush",
              [Shape(hub, "plastic_black", 40.0), Shape(K.Solid.union_all(arms), "plastic_gray", 40.0)], parent_id="chassis", required=True,
              aliases=["chổi cạnh", "chổi quét góc", "side brush", "chổi xoay"], function="Chổi 3 nhánh gom bụi ở góc tường vào chổi chính.",
              position_tag="front", joint_axis=(0, 0, 1), explode_dir=(0, 0, -1), explode_distance=0.1 * Dm, explode_order=4)
    # ---------- khay bụi ----------
    bin_s = K.rounded_box(bin_l - 0.004 * Dm, bin_w - 0.004 * Dm, bin_h, 0.018 * Dm).translate(xd, 0, z_split - bin_h / 2)
    filt = K.rounded_box(0.012 * Dm, bin_w * 0.8, bin_h * 0.7, 0.003 * Dm).translate(xd + bin_l / 2 - 0.02 * Dm, 0, z_split - bin_h / 2)
    bin_s = bin_s - filt
    handle = K.rounded_box(0.05 * Dm, 0.12 * Dm, 0.008 * Dm, 0.003 * Dm).translate(xd - 0.02 * Dm, 0, z_split - 0.004 * Dm - 0.001)
    b.add("dustbin", "Khay bụi + lưới lọc", "Dust bin", "dustbin",
          [Shape(bin_s, "glass_tinted", 40.0), Shape(filt, "fabric", 40.0), Shape(handle, "plastic_black", 40.0)], parent_id="chassis",
          required=True, aliases=["khay bụi", "hộp bụi", "dust bin", "lưới lọc", "bộ lọc hepa"],
          function="Khay bụi ~470 ml, lưới lọc HEPA E11, tay kéo.", position_tag="rear",
          explode_dir=(0, 0, 1), explode_distance=0.5 * Dm, explode_order=2)
    # ---------- tấm lau ----------
    if p.get("mop", False):
        tank = K.rounded_box(0.14 * Dm, 0.42 * Dm, 0.03 * Dm, 0.012 * Dm).translate(-0.3 * Dm, 0, c - 0.015 * Dm)
        pad = K.rounded_box(0.13 * Dm, 0.4 * Dm, 0.006 * Dm, 0.006 * Dm).translate(-0.3 * Dm, 0, 0.003 * Dm)
        tank = tank & K.cylinder(R - 0.01 * Dm, Dm, segments=96).translate(0, 0, -Dm / 2)
        pad = pad & K.cylinder(R - 0.015 * Dm, Dm, segments=96).translate(0, 0, -Dm / 2)
        b.add("mop", "Bình nước + tấm lau", "Water tank & mop", "mop", [Shape(tank, "glass_tinted", 40.0), Shape(pad, "fabric", 40.0)],
              parent_id="chassis", aliases=["tấm lau", "giẻ lau", "bình nước", "mop"], function="Bình nước 200 ml nhỏ giọt ra tấm lau microfiber.",
              position_tag="rear", explode_dir=(-1, 0, -0.5), explode_distance=0.3 * Dm, explode_order=3)
        contacts.append(["mop", "chassis"])
    # ---------- đế sạc ----------
    if p.get("dock", True):
        gx = -R - 0.25 * Dm
        dw, dd, dh = 0.45 * Dm, 0.28 * Dm, 0.3 * Dm
        tower = K.rounded_box(0.09 * Dm, dw, dh, 0.03 * Dm).translate(gx - dd + 0.045 * Dm, 0, dh / 2)
        ramp = K.hull([K.box(dd, dw * 0.9, 0.004 * Dm).translate(gx - dd / 2, 0, 0.002 * Dm),
                       K.box(0.02 * Dm, dw * 0.9, 0.02 * Dm).translate(gx - dd + 0.1 * Dm, 0, 0.01 * Dm)])
        ir = K.rounded_box(0.004 * Dm, 0.12 * Dm, 0.03 * Dm, 0.006 * Dm).translate(gx - dd + 0.09 * Dm + 0.001, 0, dh * 0.72)
        pads = K.Solid.union_all([K.rounded_box(0.04 * Dm, 0.02 * Dm, 0.004 * Dm, 0.002 * Dm).translate(gx - 0.1 * Dm, s * 0.07 * Dm, 0.004 * Dm + 0.0019 * Dm)
                                  for s in (1, -1)])
        led = K.sphere(0.006 * Dm, 12).translate(gx - dd + 0.09 * Dm, 0, dh * 0.9)
        b.add("dock", "Đế sạc", "Charging dock", "dock",
              [Shape(tower + ramp, "plastic_white", 40.0), Shape(ir, "glass_tinted", 40.0), Shape(pads, "steel", 40.0), Shape(led, "led_green", 40.0)],
              aliases=["đế sạc", "trạm sạc", "dock", "cục sạc"], function="Đế sạc: 2 tiếp điểm, cửa sổ hồng ngoại dẫn đường về sạc, đèn báo.",
              position_tag="rear", dimensions={"width": dw})
    b.note_stage(1, "Nhấc nắp trên")
    b.note_stage(2, "Tháo tháp LiDAR, khay bụi, nút")
    b.note_stage(3, "Gỡ cản trước, trụ LiDAR, tấm lau")
    b.note_stage(4, "Tháo chổi cạnh, chổi chính, bánh xoay, bánh chủ động")
    b.place_on_ground(center_xy=False)
    b.metadata.update({"diameter_mm": Dm, "height_mm": z_top + (0.032 * Dm if p.get("lidar", True) else 0.0), "clearance_mm": c,
                       "cliff_sensors": 6, "standard": "Tỷ lệ Roborock S7 (Ø353 × 96,5 mm)", "strict_overlap": True,
                       "contacts": contacts})
    return b.build()
