"""Robot AGV/AMR kho hàng và robot giao hàng: khung thép hàn + vỏ sơn, dẫn động vi sai (2 bánh PU chủ động + 4 bánh
xoay) hoặc 4 bánh mecanum (con lăn 45°), đầu nâng kệ xoay (kiểu Kiva) hoặc thùng hàng có nắp, 2 máy quét laser an toàn
(góc chéo với dẫn động vi sai, trước/sau với mecanum), camera 3D phía trước + camera đọc mã sàn, dải đèn trạng thái,
2 nút dừng khẩn cấp, cản cao su trước/sau (không có đèn tháp nhô cao — kệ hàng trùm lên robot), tiếp điểm sạc, khối pin tháo bên hông.

Tỷ lệ theo sản phẩm thật: Amazon/Kiva Drive Unit ≈ 760 × 640 × 300 mm; bánh chủ động Ø ≈ 0,2·L; khe gầm ≈ 3,5 % L.
Tháo: thùng/đầu nâng, nút, đèn, camera → vỏ → pin, máy quét, cản → bánh, bánh xoay khỏi khung.
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


def mecanum_wheel(R: float, width: float, n: int = 10, left_hand: bool = False) -> tuple[K.Solid, K.Solid]:
    """Bánh mecanum (trục Y, tâm ở gốc): moay-ơ + giá đỡ + n con lăn tang trống nghiêng 45°, con lăn 0 ở đáy.
    Trả (moay-ơ + giá, con lăn)."""
    r_max = 0.2 * R
    Rc = R - r_max
    Lr = min(0.9 * width / math.cos(math.radians(45)), 0.62 * (2 * math.pi * Rc / n) / math.sin(math.radians(45)))
    prof = [(0.0, -Lr / 2)] + [(r_max * math.sqrt(max(0.05, 1 - 0.55 * (t / (Lr / 2)) ** 2)), t)
                               for t in np.linspace(-Lr / 2, Lr / 2, 13)] + [(0.0, Lr / 2)]
    roller = K.revolve(prof, segments=20)
    pin = K.cylinder(0.12 * r_max, Lr + 0.5 * r_max, segments=10).translate(0, 0, -(Lr + 0.5 * r_max) / 2)
    rollers, brackets = [], []
    sg = -1.0 if left_hand else 1.0
    for k in range(n):
        phi = -math.pi / 2 + 2 * math.pi * k / n
        radial = np.array([math.cos(phi), 0.0, math.sin(phi)])
        tang = np.array([-math.sin(phi), 0.0, math.cos(phi)])
        axis = tang * math.cos(math.radians(45)) + np.array([0, sg, 0]) * math.sin(math.radians(45))
        c = radial * Rc
        rollers.append(roller.align_z(axis, c))
        brackets.append(pin.align_z(axis, c))
        for end in (-1, 1):
            e = c + axis * end * (Lr / 2 + 0.2 * r_max)
            brackets.append(K.hull([K.sphere(0.2 * r_max, 10).translate(*e),
                                    K.sphere(0.25 * r_max, 10).translate(*(radial * (Rc - 1.1 * r_max) + np.array([0, e[1], 0])))]))
    hub = K.cylinder(Rc - 1.05 * r_max, width * 1.05, segments=48).rotate(90, 0, 0).translate(0, width * 0.525, 0)
    return K.Solid.union_all([hub] + brackets), K.Solid.union_all(rollers)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    L = float(p.get("length_mm", 900.0))
    mecanum = p.get("drive", "differential") == "mecanum"
    cargo = p.get("top", "lift") == "cargo"
    W, H = 0.8 * L, 0.34 * L
    mats = MC.tech_materials(spec, primary="#f2b705" if not cargo else "#e9ecef", secondary="#26292e", accent="#1f7ae0")
    b = AssemblyBuilder(spec.name or ("Robot giao hàng" if cargo else "Robot AGV nâng kệ"), "agv", mats)
    c = 0.035 * L                          # khe gầm
    fh = 0.075 * L                         # cao khung thép
    z_f = c + fh                           # mặt trên khung = đáy vỏ
    rad = 0.06 * L
    tube = 0.05 * L
    contacts: list[list[str]] = [["body_shell", "chassis"]]
    # ---------- bố trí bánh ----------
    if mecanum:
        Rw, ww = 0.13 * L, 0.1 * L
        wheel_pos = [(sx * (L / 2 - 0.2 * L), sy * (W / 2 - ww / 2 - 0.02 * L), "front" if sx > 0 else "rear", "left" if sy > 0 else "right")
                     for sx in (1, -1) for sy in (1, -1)]
    else:
        Rw, ww = 0.1 * L, 0.07 * L
        wheel_pos = [(0.0, sy * (W / 2 - ww / 2 - 0.06 * L), "middle", "left" if sy > 0 else "right") for sy in (1, -1)]
    rc_ = 0.028 * L
    caster_pos = [] if mecanum else [(sx * (L / 2 - 0.12 * L), sy * (W / 2 - 0.12 * L)) for sx in (1, -1) for sy in (1, -1)]
    z_tp = 2 * rc_ + 0.025 * L             # mặt dưới cầu đỡ bánh xoay
    # ---------- khung thép ----------
    ring = K.box(L - 0.02 * L, W - 0.02 * L, fh) - K.box(L - 0.02 * L - 2 * tube, W - 0.02 * L - 2 * tube, fh + 2)
    floor = K.box(L - 0.04 * L, W - 0.04 * L, 0.01 * L).translate(0, 0, -fh / 2 + 0.005 * L)
    cross = K.Solid.union_all([K.box(tube * 0.8, W - 0.03 * L, fh * 0.8).translate(x, 0, -fh * 0.1) for x in (-0.18 * L, 0.18 * L)])
    frame = (ring + floor + cross).translate(0, 0, c + fh / 2)
    wells, brackets = [], []
    for x, y, *_ in wheel_pos:
        sgn = 1 if y > 0 else -1
        wells.append(K.rounded_box(2 * Rw + 0.04 * L, ww + 0.04 * L, 2 * Rw + 0.06 * L, 0.01 * L).translate(x, y, Rw))
        y_wall = y - sgn * (ww / 2 + 0.02 * L)
        brackets.append(K.box(0.16 * L, 0.03 * L, Rw + 0.06 * L - c).translate(x, y_wall - sgn * 0.015 * L, c + (Rw + 0.06 * L - c) / 2))
    for x, y in caster_pos:
        wells.append(K.cylinder(rc_ + 0.025 * L, z_tp + 1, segments=40).translate(x, y, -1))
        brackets.append(K.box(0.09 * L, 0.09 * L, 0.012 * L).translate(x, y, z_tp + 0.006 * L))
    frame = frame.subtract_all(wells) + K.Solid.union_all(brackets)
    qr = K.cylinder(0.02 * L, 0.012 * L, segments=32).translate(0.0, 0.14 * L, c - 0.002 * L)
    charge = K.Solid.union_all([K.rounded_box(0.012 * L, 0.06 * L, 0.03 * L, 0.004 * L).translate(-L / 2 + 0.01 * L - 0.006 * L, sy * 0.08 * L, c + fh * 0.4)
                                for sy in (1, -1)])
    b.add("chassis", "Khung gầm thép", "Welded steel chassis", "frame",
          [Shape(frame, "steel_dark", 40.0), Shape(qr, "lens", 40.0), Shape(charge, "copper", 40.0)], required=True,
          aliases=["khung", "khung gầm", "chassis", "khung thép", "tiếp điểm sạc", "camera đọc mã sàn"],
          function="Khung thép hộp hàn chịu tải, giá động cơ, sàn đỡ pin; camera đọc mã QR sàn; tiếp điểm sạc phía sau.",
          position_tag="bottom", dimensions={"length": L - 0.02 * L})
    # ---------- vỏ ----------
    top_h = H - z_f
    outer = K.rounded_box(L, W, top_h + rad, rad).translate(0, 0, z_f + (top_h + rad) / 2 - rad) & K.box(2 * L, 2 * W, top_h).translate(0, 0, z_f + top_h / 2)
    wall = 0.012 * L
    inner = K.rounded_box(L - 2 * wall, W - 2 * wall, top_h + rad, rad - wall).translate(0, 0, z_f + (top_h + rad) / 2 - rad - wall)
    shell = (outer - inner).subtract_all(wells)
    lidar_on = p.get("lidar", True)
    if mecanum:
        scan_pts = [(L / 2 - 0.07 * L, 0.0, "front"), (-L / 2 + 0.07 * L, 0.0, "rear")]
    else:
        scan_pts = [(L / 2 - 0.07 * L, W / 2 - 0.07 * L, "front_left"), (-L / 2 + 0.07 * L, -W / 2 + 0.07 * L, "rear_right")]
    if lidar_on:
        for x, y, _t in scan_pts:
            shell = shell - K.cylinder(0.085 * L, 0.11 * L, segments=48).translate(x, y, z_f - 0.001 * L)
    shell = shell - D.panel_lines(outer, [("z", z_f + top_h * 0.55)], width=0.004 * L, depth=0.003 * L)
    vents = D.vent_cutter((-0.2 * L, W / 2, z_f + top_h * 0.3), (0, 1, 0), (1, 0, 0), 0.25 * L, 0.05 * L, 8, wall * 1.5) + \
        D.vent_cutter((-0.2 * L, -W / 2, z_f + top_h * 0.3), (0, -1, 0), (1, 0, 0), 0.25 * L, 0.05 * L, 8, wall * 1.5)
    shell = shell - vents
    b.add("body_shell", "Vỏ thân", "Body shell", "shell", Shape(shell, "paint_primary", 60.0), parent_id="chassis", required=True,
          aliases=["vỏ", "vỏ thân", "thân xe", "body", "shell", "khe gió"], function="Vỏ composite sơn, rãnh ghép, khe gió tản nhiệt pin.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.55 * L, explode_order=2)
    # ---------- bánh xe ----------
    for x, y, fb, lr in wheel_pos:
        vi = {"front": "trước", "rear": "sau", "middle": "giữa"}[fb] + " " + {"left": "trái", "right": "phải"}[lr]
        sgn = 1 if y > 0 else -1
        y_wall = y - sgn * (ww / 2 + 0.02 * L)
        if mecanum:
            hub, rol = mecanum_wheel(Rw, ww, 10, left_hand=(fb == "front") == (lr == "left"))
            shapes = [Shape(hub.translate(x, y, Rw), "aluminum_dark", 40.0), Shape(rol.translate(x, y, Rw), "polyurethane", 40.0)]
            name, alias = f"Bánh mecanum {vi}", ["bánh mecanum", "bánh xe", "bánh đa hướng", "wheel"]
            func = "Bánh mecanum 10 con lăn PU nghiêng 45°: đi ngang, đi chéo, xoay tại chỗ."
            face = y - sgn * ww * 0.525
        else:
            tire, rim = C.wheel(2 * Rw, ww, spokes=6, rim_material="aluminum", tire_material="polyurethane", tread=False)
            shapes = [Shape(sh.solid.translate(x, y, Rw), sh.material, 40.0) for sh in tire + rim]
            name, alias = f"Bánh chủ động {vi}", ["bánh chủ động", "bánh xe", "wheel", "motor bánh"]
            func = "Bánh PU chủ động + động cơ BLDC hộp số hành tinh (dẫn động vi sai)."
            face = y - sgn * ww * 0.45
        gm_len = abs(face - y_wall)
        motor = K.cylinder(0.045 * L, gm_len + 0.001 * L, segments=40).align_z((0, -sgn, 0), (x, face + sgn * 0.0005 * L, Rw))
        shapes.append(Shape(motor, "steel_black_oxide", 40.0))
        b.add(f"wheel_{fb}_{lr}", name, "Wheel", "wheel", shapes, parent_id="chassis", required=True, aliases=alias, function=func,
              position_tag=f"{fb}_{lr}" if fb != "middle" else lr, joint_axis=(0, 1, 0),
              explode_dir=(0, sgn, -0.2), explode_distance=0.3 * L, explode_order=4)
    for x, y in caster_pos:
        tire, rim = C.wheel(2 * rc_, 0.03 * L, spokes=4, rim_material="steel", tire_material="polyurethane", tread=False)
        fork = K.Solid.union_all([K.rounded_box(0.008 * L, 0.006 * L, z_tp - rc_ - 0.006 * L, 0.002 * L).translate(0, s * 0.02 * L, (z_tp - 0.006 * L + rc_) / 2)
                                  for s in (1, -1)])
        top = K.box(0.07 * L, 0.07 * L, 0.006 * L).translate(0, 0, z_tp - 0.003 * L)
        axle = K.cylinder(0.004 * L, 0.046 * L, segments=12).rotate(90, 0, 0).translate(0, 0.023 * L, rc_)
        cs_ = [Shape(sh.solid.translate(0, 0, rc_), sh.material, 40.0) for sh in tire + rim] + \
            [Shape(fork + top + axle, "steel_zinc", 40.0)]
        for sh in cs_:
            sh.solid = sh.solid.translate(x, y, 0)
        tag = f"{'front' if x > 0 else 'rear'}_{'left' if y > 0 else 'right'}"
        b.add(f"caster_{tag}", "Bánh xoay " + ("trước" if x > 0 else "sau") + (" trái" if y > 0 else " phải"), "Caster", "caster",
              cs_, parent_id="chassis", required=True, aliases=["bánh xoay", "bánh tự lựa", "caster"],
              function="Bánh xoay giảm chấn đỡ tải ở bốn góc.", position_tag=tag, explode_dir=(0, 0, -1),
              explode_distance=0.2 * L, explode_order=4)
    # ---------- cản cao su ----------
    for sx, tag, vi in ((1, "front", "trước"), (-1, "rear", "sau")):
        bum = K.rounded_box(0.035 * L, W * 0.62, fh * 0.7, 0.012 * L).translate(sx * (L / 2 - 0.01 * L + 0.0175 * L), 0, c + fh * 0.45)
        if sx < 0:
            bum = bum - K.Solid.union_all([K.box(0.05 * L, 0.07 * L, 0.04 * L).translate(-L / 2, sy * 0.08 * L, c + fh * 0.4) for sy in (1, -1)])
        b.add(f"bumper_{tag}", f"Cản cao su {vi}", f"{tag} bumper", "bumper", Shape(bum, "rubber", 40.0), parent_id="chassis", required=True,
              aliases=["cản", "cản cao su", "bumper", "cạnh an toàn"], function="Cản cao su có công tắc an toàn (safety edge).",
              position_tag=tag, explode_dir=(sx, 0, 0), explode_distance=0.15 * L, explode_order=3)
    # ---------- pin ----------
    xb = -0.215 * L
    batt = K.rounded_box(0.26 * L, 0.3 * W, 0.12 * L, 0.01 * L).translate(xb, 0, c + 0.01 * L + 0.06 * L)
    lbl = D.label_plate(0.1 * L, 0.05 * L, 0.002 * L).translate(xb + 0.13 * L + 0.001 * L, 0, c + 0.01 * L + 0.07 * L)
    b.add("battery", "Khối pin LiFePO4", "Battery pack", "battery", [Shape(batt, "battery_wrap", 40.0), Shape(lbl, "label_yellow", 40.0)],
          parent_id="chassis", required=True, aliases=["pin", "ắc quy", "battery", "khối pin"],
          function="Pin LiFePO4 48 V tháo nhanh, sạc tự động qua tiếp điểm.", position_tag="center",
          explode_dir=(0, -1, 0.2), explode_distance=0.7 * W, explode_order=3)
    # ---------- máy quét laser an toàn ----------
    if lidar_on:
        for x, y, tag in scan_pts:
            hous = K.cylinder(0.065 * L, 0.09 * L, segments=48).translate(x, y, z_f + 0.005 * L)
            win = K.cylinder(0.066 * L, 0.035 * L, segments=48).translate(x, y, z_f + 0.02 * L)
            sgn_x = 1 if x > 0 else -1
            sgn_y = (1 if y > 0 else -1) if abs(y) > 1e-6 else 0
            back = K.box(0.1 * L, 0.1 * L if sgn_y else 0.14 * L, 0.2 * L).translate(x - sgn_x * 0.05 * L, y - sgn_y * 0.05 * L, z_f)
            win = win - back
            hous = hous - win
            bracket = K.box(0.05 * L, 0.05 * L, 0.006 * L).translate(x, y, z_f + 0.002 * L)
            nm = {"front_left": "trước trái", "rear_right": "sau phải", "front": "trước", "rear": "sau"}[tag]
            b.add(f"scanner_{tag}", f"Máy quét laser an toàn {nm}", "Safety laser scanner",
                  "lidar", [Shape(hous + bracket, "plastic_yellow", 40.0), Shape(win, "glass_tinted", 40.0)], parent_id="chassis", required=True,
                  aliases=["lidar", "máy quét laser", "cảm biến an toàn", "safety scanner", "laser scanner"],
                  function="Máy quét laser an toàn PLd (kiểu SICK nanoScan3), trường nhìn 275°: vùng cảnh báo/dừng.",
                  position_tag=tag, explode_dir=(sgn_x, sgn_y, 0.5), explode_distance=0.25 * L, explode_order=3)
            contacts.append([f"scanner_{tag}", "body_shell"])
    # ---------- đầu nâng kệ / thùng hàng ----------
    z_top = H
    xs_lift = 0.05 * L
    if not cargo:
        Rl = 0.3 * W
        plate = K.revolve(P.fillet_polygon([(0, 0), (Rl, 0), (Rl, 0.025 * L), (0, 0.025 * L)], [0, 0.004 * L, 0.006 * L, 0], 4), segments=128)
        pad = K.cylinder(Rl * 0.92, 0.006 * L, segments=128).translate(0, 0, 0.025 * L - 0.001)
        pad = pad - K.Solid.union_all([K.box(0.004 * L, 2 * Rl, 0.01 * L).translate(dx, 0, 0.025 * L) for dx in np.linspace(-Rl * 0.8, Rl * 0.8, 9)])
        z_pl = z_top + 0.02 * L
        col = K.cylinder(0.12 * L, z_pl - (c + 0.01 * L), segments=64).translate(xs_lift, 0, c + 0.01 * L)
        b.add("lift_unit", "Đầu nâng kệ xoay", "Lift & rotate unit", "lift",
              [Shape(plate.translate(xs_lift, 0, z_pl), "aluminum_dark", 40.0), Shape(pad.translate(xs_lift, 0, z_pl), "rubber", 40.0),
               Shape(col, "steel", 40.0)], parent_id="chassis", required=True,
              aliases=["đầu nâng", "mâm nâng", "nâng kệ", "lift", "mâm xoay", "kích nâng"],
              function="Mâm nâng vít me + xoay: nâng kệ hàng 50 mm, giữ kệ đứng yên khi robot xoay.", position_tag="top",
              joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=0.9 * L, explode_order=1)
        b.cut("body_shell", K.cylinder(0.125 * L, H, segments=64).translate(xs_lift, 0, z_f + 0.001))
        top_part = "lift_unit"
        ctrl_parent = "body_shell"
        e_pts = [(L / 2 - 0.1 * L, -W / 2 + 0.1 * L, None), (-L / 2 + 0.1 * L, W / 2 - 0.1 * L, None)]
    else:
        bh = 0.5 * L
        bl, bw = L * 0.9, W * 0.9
        box = K.rounded_box(bl, bw, bh, 0.03 * L).translate(0, 0, z_top + bh / 2)
        box = box - K.rounded_box(bl - 0.03 * L, bw - 0.03 * L, bh, 0.02 * L).translate(0, 0, z_top + bh / 2 + 0.015 * L)
        lid = K.rounded_box(bl, bw, 0.03 * L, 0.012 * L).translate(0, 0, z_top + bh + 0.015 * L)
        hinge = K.Solid.union_all([K.cylinder(0.01 * L, 0.1 * L, segments=16).rotate(90, 0, 0).translate(-bl / 2 + 0.012 * L, y + 0.05 * L, z_top + bh + 0.001 * L)
                                   for y in (-0.25 * W, 0.25 * W)])
        handle = D.handle_bar((bl / 2 - 0.03 * L, -0.15 * W, z_top + bh + 0.03 * L), (bl / 2 - 0.03 * L, 0.15 * W, z_top + bh + 0.03 * L),
                              (0, 0, 1), 0.03 * L, 0.006 * L)
        hmi = K.rounded_box(0.012 * L, 0.3 * W, 0.16 * L, 0.01 * L).translate(bl / 2 + 0.006 * L, 0, z_top + bh * 0.55)
        screen = K.rounded_box(0.004 * L, 0.26 * W, 0.12 * L, 0.006 * L).translate(bl / 2 + 0.013 * L, 0, z_top + bh * 0.55)
        b.add("cargo_box", "Thùng hàng", "Cargo box", "cargo", [Shape(box, "paint_primary", 50.0), Shape(hmi, "plastic_black", 40.0),
                                                                Shape(screen, "glass_tinted", 40.0)], parent_id="body_shell", required=True,
              aliases=["thùng hàng", "hộp hàng", "khoang chứa", "cargo", "màn hình"], function="Thùng chứa hàng có khóa điện tử, màn hình nhập mã.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.6 * L, explode_order=1)
        b.add("cargo_lid", "Nắp thùng", "Cargo lid", "cover", [Shape(lid, "paint_primary", 50.0), Shape(hinge, "stainless", 40.0),
                                                              Shape(handle, "plastic_black", 40.0)], parent_id="cargo_box", required=True,
              aliases=["nắp thùng", "nắp", "lid", "tay nắm"], function="Nắp thùng bản lề, tay nắm.", position_tag="top",
              explode_dir=(0, 0, 1), explode_distance=0.3 * L, explode_order=1)
        top_part = "cargo_lid"
        ctrl_parent = "cargo_box"
        e_pts = [(bl / 2, -bw / 2 + 0.07 * L, z_top + bh * 0.85), (bl / 2, bw / 2 - 0.07 * L, z_top + bh * 0.85)]
    # ---------- nút dừng khẩn cấp ----------
    ez = []
    for x, y, zz in e_pts:
        base, cap = D.estop_button(0.03 * L)
        if zz is None:
            zt = D.surface_at(outer, "z", (x, y, 0), True) or z_top
            ez += [Shape(base.translate(x, y, zt - 0.002 * L), "paint_yellow", 40.0), Shape(cap.translate(x, y, zt - 0.002 * L), "paint_red", 40.0)]
        else:                                                      # gắn mặt trước thùng hàng
            for sh, mid in ((base, "paint_yellow"), (cap, "paint_red")):
                ez.append(Shape(sh.rotate(0, 90, 0).translate(x - 0.002 * L, y, zz), mid, 40.0))
    b.add("estop", "2 nút dừng khẩn cấp", "Emergency stops", "estop", ez, parent_id=ctrl_parent, required=True,
          aliases=["nút dừng khẩn cấp", "e-stop", "nút khẩn cấp", "estop", "nút đỏ"], function="Nút nấm dừng khẩn cấp (cắt nguồn động cơ, PLd).",
          position_tag="top", explode_dir=(0, 0, 1) if not cargo else (1, 0, 0), explode_distance=0.25 * L, explode_order=1)
    # ---------- đèn, camera, đèn tháp ----------
    lights = []
    for sy in (1, -1):
        hsg, lens = D.light_bar(0.55 * L, 0.02 * L, 0.012 * L)
        ys = sy * abs(D.surface_at(outer, "y", (0, 0, z_f + top_h * 0.78), sy > 0) or W / 2)
        for sh, mid in ((hsg, "plastic_black"), (lens, "led_green")):
            lights.append(Shape(sh.rotate(0, 0, 90 * sy).translate(0, ys + sy * 0.006 * L, z_f + top_h * 0.78), mid, 40.0))
    hsg, lens = D.light_bar(0.4 * W, 0.02 * L, 0.012 * L)
    xf = D.surface_at(outer, "x", (0, 0, z_f + top_h * 0.78), True) or L / 2
    lights += [Shape(hsg.translate(xf + 0.006 * L, 0, z_f + top_h * 0.78), "plastic_black", 40.0),
               Shape(lens.translate(xf + 0.006 * L, 0, z_f + top_h * 0.78), "led_white", 40.0)]
    b.add("light_bars", "Dải đèn trạng thái", "Status light bars", "light", lights, parent_id="body_shell", required=True,
          aliases=["đèn", "dải đèn", "đèn trạng thái", "đèn led", "light"], function="Dải LED báo trạng thái (xanh: chạy, vàng: chờ, đỏ: lỗi) + đèn pha trước.",
          position_tag="side", explode_dir=(0, 0, 1), explode_distance=0.2 * L, explode_order=1)
    zc_cam = z_f + top_h * 0.45
    cam = K.rounded_box(0.03 * L, 0.12 * L, 0.03 * L, 0.006 * L).translate(xf + 0.015 * L - 0.0005 * L, 0, zc_cam)
    lens_s = K.Solid.union_all([K.cylinder(0.008 * L, 0.004 * L, segments=24).rotate(0, 90, 0).translate(xf + 0.03 * L - 0.0015 * L, y, zc_cam)
                                for y in (-0.04 * L, 0.04 * L)])
    b.add("camera", "Camera 3D phía trước", "Front 3D camera", "camera", [Shape(cam, "plastic_black", 40.0), Shape(lens_s, "lens", 40.0)],
          parent_id="body_shell", required=True, aliases=["camera", "camera 3d", "camera độ sâu", "depth camera"],
          function="Camera độ sâu stereo phát hiện chướng ngại ngoài mặt phẳng quét laser.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=0.15 * L, explode_order=1)
    b.note_stage(1, "Tháo thùng hàng/đầu nâng, nút khẩn cấp, đèn, camera")
    b.note_stage(2, "Nhấc vỏ thân")
    b.note_stage(3, "Tháo pin, máy quét laser, cản")
    b.note_stage(4, "Tháo bánh xe, bánh xoay")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"length_mm": L, "width_mm": W, "height_mm": H, "drive": "mecanum" if mecanum else "differential",
                       "top": "cargo" if cargo else "lift", "top_part": top_part,
                       "standard": "Tỷ lệ Amazon/Kiva Drive Unit (760 × 640 × 300 mm), máy quét an toàn kiểu SICK nanoScan3",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
