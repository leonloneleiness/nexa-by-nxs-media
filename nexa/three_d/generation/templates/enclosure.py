"""Tủ điện treo tường thép sơn tĩnh điện (IP66): thân hộp tôn 1,5 mm có gờ mép + rãnh gioăng, cửa gấp mép có gioăng xốp,
2 bản lề trái, khóa vặn 1/4 vòng (1–2 bộ), ô kính polycarbonat tùy chọn; bên trong: tấm lắp thiết bị mạ kẽm trên 4 trụ,
thanh ray DIN TH35-7,5 (EN 60715), aptomat tổng + RCD + các aptomat tép 1 cực 18 mm (DIN 43880), cầu đấu, máng cáp có
khe, thanh tiếp địa; đáy có ốc siết cáp; 4 tai treo tường.
"""
from __future__ import annotations

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def din_rail(x0: float, x1: float, y_face: float, zc: float) -> K.Solid:
    """Ray DIN TH35-7,5: mặt cắt mũ (rộng 35, cao 7,5, dày 1), dọc X, lưng áp mặt y = y_face, nhô về −Y (phía cửa)."""
    Wr, Hr, tr = S.DIN_RAIL["w"], S.DIN_RAIL["h"], S.DIN_RAIL["t"]
    # mặt cắt (y, z) cục bộ: lưng tại y = 0, mũ nhô ra −y tới −Hr
    prof = np.array([(0.0, -Wr / 2), (-tr, -Wr / 2), (-tr, -12.5), (-Hr, -12.5), (-Hr, 12.5), (-tr, 12.5), (-tr, Wr / 2), (0.0, Wr / 2),
                     (0.0, 12.5 - tr), (-Hr + tr, 12.5 - tr), (-Hr + tr, -12.5 + tr), (0.0, -12.5 + tr)])
    ex = K.extrude(P.ensure_ccw(prof), x1 - x0)                        # (y, z) đùn theo Z → X
    rail = ex.transform(np.array([[0, 0, 1.0, x0], [1.0, 0, 0, y_face], [0, 1.0, 0, zc]]))
    slots = K.Solid.union_all([box_at(x - 3.0, x + 3.0, y_face - 2.0, y_face + 1.0, zc - 2.6, zc + 2.6) for x in np.arange(x0 + 12.5, x1 - 5.0, 25.0)])
    return rail - slots


def breaker(xc: float, wmod: int, y_face: float, zc: float, color: str = "white") -> tuple[K.Solid, K.Solid]:
    """Thiết bị mô-đun DIN (aptomat/RCD): rộng wmod × 18, cao 90, sâu 70 từ mặt ray; cần gạt ở giữa."""
    w = wmod * S.DIN_MODULE - 0.4
    body = K.hull([box_at(xc - w / 2, xc + w / 2, y_face - 7.5 - 0.0, y_face - 7.5 - 44.0, zc - 45.0, zc + 45.0),
                   box_at(xc - w / 2, xc + w / 2, y_face - 7.5 - 44.0, y_face - 7.5 - 70.0, zc - 22.5, zc + 22.5)])
    clip = box_at(xc - w / 2 + 1.0, xc + w / 2 - 1.0, y_face - 7.5, y_face - 7.5 - 1.0, zc - 17.5, zc + 17.5)   # ngàm kẹp vào mũ ray
    lever = box_at(xc - min(w, 18.0) * 0.3, xc + min(w, 18.0) * 0.3, y_face - 7.5 - 70.0, y_face - 7.5 - 80.0, zc - 4.0, zc + 8.0)
    return body + clip, lever


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    W = float(p.get("width_mm", 600.0))
    H = float(p.get("height_mm", 800.0))
    D = float(p.get("depth_mm", 250.0))
    window = bool(p.get("window", False))
    mats = MC.tech_materials(spec, primary="#d9dcdf", secondary="#2b2d42", accent="#f2b705")
    mats["galvanized"] = M.material("galvanized", "metal", "#b3b9bf", 0.85, 0.42, name="Thép mạ kẽm")
    mats["polycarb"] = M.material("polycarb", "glass", "#d8e4ee", 0.0, 0.05, alpha=0.3, name="Kính polycarbonat")
    mats["copper_bar"] = M.material("copper_bar", "metal", "#b87333", 0.95, 0.3, name="Thanh đồng")
    b = AssemblyBuilder(spec.name or f"Tủ điện {W:g}×{H:g}×{D:g}", "electrical_enclosure", mats)
    t = 1.5
    # hệ tọa độ: X ngang (rộng), Z đứng (cao), Y sâu — mặt cửa ở y = 0, lưng tủ ở y = D
    body = box_at(-W / 2, W / 2, 0.0, D, 0.0, H) - box_at(-W / 2 + t, W / 2 - t, -1.0, D - t, t, H - t)
    lip = box_at(-W / 2, W / 2, 0.0, 20.0, 0.0, H) - box_at(-W / 2 + 20.0, W / 2 - 20.0, -1.0, 21.0, 20.0, H - 20.0)
    body = body + (lip - box_at(-W / 2 + t, W / 2 - t, t, 21.0, t, H - t)) + (lip & box_at(-W / 2, W / 2, 0, t, 0, H))
    glands_n = max(2, int(W / 100.0))
    gx = np.linspace(-W / 2 + 60.0, W / 2 - 60.0, glands_n)
    gland_holes = K.Solid.union_all([K.cylinder(10.0 if i % 2 else 12.5, 10.0, segments=32).translate(x, D * 0.55, -5.0) for i, x in enumerate(gx)])
    body = body - gland_holes
    brackets = K.Solid.union_all([box_at(sx * (W / 2 - 40.0) - 20.0, sx * (W / 2 - 40.0) + 20.0, D, D + 3.0, z - 40.0, z + 40.0) +
                                  box_at(sx * (W / 2 - 40.0) - 20.0, sx * (W / 2 - 40.0) + 20.0, D, D + 25.0, z + sz * 40.0 - 3.0 * sz, z + sz * 40.0)
                                  for sx in (1, -1) for z, sz in ((H + 30.0, 1), (-30.0, -1))])
    brackets = brackets + K.Solid.union_all([box_at(sx * (W / 2 - 40.0) - 20.0, sx * (W / 2 - 40.0) + 20.0, D, D + 3.0, zz - 10.0, zz + 10.0)
                                             for sx in (1, -1) for zz in (H - 10.0, 10.0)])
    stud = K.cylinder(4.0, 20.0, segments=16).rotate(90, 0, 0).translate(W / 2 - 50.0, 20.0 + 1.0, 60.0)
    b.add("body", f"Thân tủ tôn {t:g} mm", "Enclosure body", "enclosure_body", [Shape(body, "paint_primary", 35.0), Shape(stud, "steel", 35.0)], required=True,
          aliases=["thân tủ", "vỏ tủ", "hộp tủ điện", "enclosure", "tủ điện"], function=f"Hộp thép tôn {t:g} mm sơn tĩnh điện, gờ mép 20 mm + rãnh gioăng, lỗ ốc siết cáp ở đáy.",
          position_tag="center", dimensions={"width": W, "height": H, "depth": D})
    b.add("brackets", "Tai treo tường (4)", "Wall brackets", "bracket", Shape(brackets, "galvanized", 35.0), parent_id="body", required=True,
          aliases=["tai treo", "pát treo", "bracket"], function="4 tai treo tường thép mạ kẽm.", position_tag="rear", explode_dir=(0, 1, 0), explode_distance=80.0,
          explode_order=1)
    # cửa: tấm gấp mép 20 mm, gioăng, bản lề trái, khóa phải
    gap = 2.0
    door = box_at(-W / 2 + gap, W / 2 - gap, -20.0, -20.0 + t, gap, H - gap)
    door = door + (box_at(-W / 2 + gap, W / 2 - gap, -20.0, -gap, gap, H - gap) - box_at(-W / 2 + gap + t, W / 2 - gap - t, -21.0, 0.0, gap + t, H - gap - t))
    gasket = (box_at(-W / 2 + 24.0, W / 2 - 24.0, -gap - 6.0, -gap, 24.0, H - 24.0) - box_at(-W / 2 + 34.0, W / 2 - 34.0, -gap - 7.0, 1.0, 34.0, H - 34.0))
    win_shapes = []
    if window:
        ww, wh = 0.6 * W, 0.45 * H
        cut = box_at(-ww / 2, ww / 2, -25.0, 0.0, 0.5 * H - wh / 2 + 0.1 * H, 0.5 * H + wh / 2 + 0.1 * H)
        door = door - cut
        pane = box_at(-ww / 2 - 10.0, ww / 2 + 10.0, -20.0 + t, -20.0 + t + 4.0, 0.6 * H - wh / 2 - 10.0, 0.6 * H + wh / 2 + 10.0)
        frame_w = pane - box_at(-ww / 2, ww / 2, -30.0, 0.0, 0.6 * H - wh / 2, 0.6 * H + wh / 2)
        glass = pane - frame_w
        win_shapes = [Shape(glass, "polycarb", 35.0), Shape(frame_w.translate(0, 4.0, 0) & box_at(-W, W, -20.0 + t + 4.0, -20.0 + t + 7.0, 0, H), "plastic_black", 35.0)]
    n_lock = 1 if H < 1000 else 2
    locks = K.Solid.union_all([K.cylinder(11.0, 14.0, segments=24).rotate(90, 0, 0).translate(W / 2 - 40.0, -20.0 + 0.0, z) +
                               box_at(W / 2 - 44.0, W / 2 - 36.0, -26.0, -20.0, z - 6.0, z + 6.0)
                               for z in ([0.5 * H] if n_lock == 1 else [0.3 * H, 0.7 * H])])
    hinges = K.Solid.union_all([K.cylinder(6.0, 60.0, segments=20).translate(-W / 2 - 1.0, -12.0, z) +
                                box_at(-W / 2 - 1.0, -W / 2 + 12.0, -16.0, -8.0, z + 5.0, z + 55.0) + box_at(-W / 2 - 6.0, -W / 2 + 2.0, -8.0, 1.0, z + 5.0, z + 55.0)
                                for z in (0.12 * H, 0.82 * H)])
    b.add("door", "Cửa tủ (gấp mép + gioăng)" + (" + ô kính" if window else ""), "Door", "door",
          [Shape(door, "paint_primary", 35.0), Shape(gasket, "rubber", 35.0), Shape(locks, "plastic_black", 35.0), Shape(hinges, "steel", 35.0)] + win_shapes,
          parent_id="body", required=True, aliases=["cửa tủ", "cánh tủ", "gioăng", "khóa tủ", "bản lề", "door"] + (["ô kính", "cửa sổ"] if window else []),
          function=f"Cửa tôn gấp mép, gioăng xốp PU, {n_lock} khóa vặn, 2 bản lề trái" + (", ô kính polycarbonat" if window else "") + ".",
          position_tag="front", joint_axis=(0, 0, 1), pivot=(-W / 2 - 1.0, -12.0, H / 2),     # trục bản lề trái
          explode_dir=(0, -1, 0), explode_distance=0.6 * D + 150.0, explode_order=1)
    # tấm lắp thiết bị trên 4 trụ, ray DIN, thiết bị, máng cáp
    y_mp = D - t - 15.0                                                # mặt trước tấm lắp (dày 2)
    mp = box_at(-W / 2 + 40.0, W / 2 - 40.0, y_mp, y_mp + 2.0, 40.0, H - 40.0)
    studs = K.Solid.union_all([K.cylinder(5.0, 15.0 - 0.0, segments=16).rotate(-90, 0, 0).translate(sx * (W / 2 - 60.0), y_mp + 2.0, z)
                               for sx in (1, -1) for z in (60.0, H - 60.0)])
    b.add("mounting_plate", "Tấm lắp thiết bị mạ kẽm", "Mounting plate", "mounting_plate", [Shape(mp, "galvanized", 35.0), Shape(studs, "steel", 35.0)],
          parent_id="body", required=True, aliases=["tấm lắp", "tấm đế", "mounting plate"], function="Tấm thép mạ kẽm 2 mm bắt trên 4 trụ ren.",
          position_tag="rear", explode_dir=(0, -1, 0), explode_distance=0.9 * D + 300.0, explode_order=3)
    side_ducts = W >= 400.0                                            # tủ nhỏ: không đủ chỗ máng đứng hai bên
    x0r, x1r = (-W / 2 + 90.0, W / 2 - 90.0) if side_ducts else (-W / 2 + 50.0, W / 2 - 50.0)
    n_rows = max(1, min(4, int((H - 200.0) / 180.0)))
    zr = [H - 150.0 - i * ((H - 250.0) / n_rows) for i in range(n_rows)] if n_rows > 1 else [max(H - 150.0, H / 2)]
    rails = K.Solid.union_all([din_rail(x0r, x1r, y_mp, z) for z in zr])
    b.add("din_rails", f"Ray DIN TH35-7,5 ({n_rows})", "DIN rails", "din_rail", Shape(rails, "galvanized", 35.0), parent_id="mounting_plate", required=True,
          aliases=["ray din", "thanh ray", "din rail"], function="Ray mũ TH35-7,5 EN 60715 có lỗ oval.", position_tag="center",
          explode_dir=(0, -1, 0), explode_distance=0.9 * D + 200.0, explode_order=2, dimensions={"rail_width": 35.0})
    dev_b, dev_l, term = [], [], []
    n_mod = int((x1r - x0r - 20.0) / S.DIN_MODULE)
    mcb_count = 0
    for ri, z in enumerate(zr):
        x = x0r + 10.0
        plan = [4, 4] + [1] * (n_mod - 14) if ri == 0 and n_mod >= 14 else [1] * max(1, n_mod - 6)
        for wm in plan:
            if x + wm * S.DIN_MODULE > x1r - 6 * 5.2 - 5.0:
                break
            body_d, lev = breaker(x + wm * S.DIN_MODULE / 2, wm, y_mp, z)
            dev_b.append(body_d)
            dev_l.append(lev)
            if wm == 1:
                mcb_count += 1
            x += wm * S.DIN_MODULE
        for k in range(6):
            xt = x1r - 6 * 5.2 + k * 5.2 + 2.6
            term.append(box_at(xt - 2.5, xt + 2.5, y_mp - 7.5 - 0.0, y_mp - 7.5 - 48.0, z - 30.0, z + 30.0))
    b.add("devices", f"Aptomat tổng + RCD + {mcb_count} aptomat tép + cầu đấu", "Breakers & terminals", "breaker",
          [Shape(K.Solid.union_all(dev_b), "plastic_white", 35.0), Shape(K.Solid.union_all(dev_l), "plastic_black", 35.0),
           Shape(K.Solid.union_all(term), "plastic_gray", 35.0)], parent_id="din_rails", required=True,
          aliases=["aptomat", "cầu dao", "mcb", "rcd", "chống giật", "cầu đấu", "thiết bị đóng cắt", "breaker"],
          function=f"Aptomat tổng 4P + RCD 4P + {mcb_count} MCB 1P rộng 18 mm (DIN 43880), cầu đấu 5,2 mm.", position_tag="center",
          explode_dir=(0, -1, 0), explode_distance=0.9 * D + 100.0, explode_order=1)
    ducts = []
    for i in range(len(zr) - 1):
        zm = (zr[i] + zr[i + 1]) / 2
        ducts.append(box_at(x0r, x1r, y_mp - 60.0, y_mp, zm - 20.0, zm + 20.0) - box_at(x0r - 1, x1r + 1, y_mp - 58.0, y_mp - 1.0, zm - 18.0, zm + 22.0))
    for sx in ((1, -1) if side_ducts else ()):
        xd = sx * (W / 2 - 60.0)
        ducts.append(box_at(xd - 20.0, xd + 20.0, y_mp - 60.0, y_mp, 60.0 + 20.0, H - 60.0 - 20.0) -
                     box_at(xd - 18.0, xd + 18.0, y_mp - 58.0, y_mp - 1.0, 60.0 + 19.0, H - 60.0 - 19.0))
    duct_shapes = [Shape(K.Solid.union_all(ducts), "plastic_gray", 35.0)] if ducts else []
    if min(zr) - 45.0 >= 80.0:                                         # thanh tiếp địa dưới hàng thiết bị thấp nhất
        L = min(150.0, W - 120.0)
        ebar = box_at(-W / 2 + 60.0, -W / 2 + 60.0 + L, y_mp - 25.0, y_mp - 10.0, 60.0, 72.0) + \
            K.Solid.union_all([box_at(-W / 2 + 60.0 + a, -W / 2 + 66.0 + a, y_mp - 10.0, y_mp, 60.0, 72.0) for a in (10.0, L - 16.0)])
        duct_shapes.append(Shape(ebar, "copper_bar", 35.0))
    if duct_shapes:
        b.add("cable_ducts", "Máng cáp có khe + thanh tiếp địa", "Cable ducts & earth bar", "duct", duct_shapes, parent_id="mounting_plate", required=True,
              aliases=["máng cáp", "máng điện", "thanh tiếp địa", "duct"], function="Máng nhựa có khe 40×60, thanh tiếp địa đồng.", position_tag="center",
              explode_dir=(0, -1, 0), explode_distance=0.9 * D + 150.0, explode_order=2)
    glands = []
    for i, x in enumerate(gx):
        r = 10.0 if i % 2 else 12.5
        glands.append(K.cylinder(r - 0.0, t + 0.02, segments=32).translate(x, D * 0.55, -0.01) + K.cylinder(r + 5.0, 12.0, segments=6).translate(x, D * 0.55, -12.0) +
                      K.cylinder(r + 3.0, 14.0, r * 0.7, segments=24).translate(x, D * 0.55, -26.0) + K.cylinder(r + 4.0, 5.0, segments=6).translate(x, D * 0.55, t))
    b.add("glands", f"Ốc siết cáp ({glands_n})", "Cable glands", "gland", Shape(K.Solid.union_all(glands), "plastic_black", 35.0), parent_id="body", required=True,
          aliases=["ốc siết cáp", "đầu cosse", "gland", "ốc xiết cáp"], function="Ốc siết cáp nhựa PA IP68 M20/M25 ở đáy tủ.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=80.0, explode_order=1)
    b.note_stage(1, "Mở cửa, tháo ốc siết cáp, thiết bị, tai treo")
    b.note_stage(2, "Tháo ray DIN, máng cáp")
    b.note_stage(3, "Rút tấm lắp thiết bị")
    b.rotate_all_z(90.0)                                               # dựng với cửa ở −Y → quay để cửa hướng +X (mặt trước)
    b.place_on_ground(center_xy=True)
    b.metadata.update({"width_mm": W, "height_mm": H, "depth_mm": D, "din_rows": n_rows, "mcb_count": mcb_count, "glands": glands_n, "window": window,
                       "standard": "Ray DIN EN 60715 TH35-7,5, mô-đun DIN 43880 (18 mm), tủ IP66 (IEC 60529)",
                       "strict_overlap": True, "contacts": []})
    return b.build()
