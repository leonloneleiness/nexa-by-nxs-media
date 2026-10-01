"""Hệ điện mặt trời mặt đất góc nghiêng cố định: tấm pin 400 Wp (1722 × 1134 × 30 mm, 108 cell nửa 182 mm, khung nhôm,
kính cường lực 3,2 mm, hộp nối + cáp MC4), giá đỡ thép mạ kẽm (cột chữ C trên móng bê tông, xà nghiêng, 2 xà gồ mỗi
hàng, kẹp giữa/kẹp biên), biến tần treo trên giá + tủ điện AC/DC trên bệ, ống luồn cáp.

Tấm pin đặt dọc (chiều dài theo dốc), mặt quay về hướng Nam (+X), mép dưới cao ≥ 500 mm; khoảng cách hàng tránh bóng
đổ khi mặt trời cao 45°.
"""
from __future__ import annotations

import math

import manifold3d as m3d
import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.structures import bake
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

PL, PW, PT = 1722.0, 1134.0, 30.0                                     # tấm 400 Wp (kiểu 108 cell nửa M10)
FRAME_W = 33.0


def panel_proto() -> dict:
    """Tấm pin nằm phẳng trong XY (dài theo X, rộng theo Y), mặt kính hướng +Z, đáy khung z = 0."""
    L, W, T = PL, PW, PT
    frame = K.box(L, W, T).translate(0, 0, T / 2) - K.box(L - 2 * FRAME_W, W - 2 * FRAME_W, T + 2).translate(0, 0, T / 2)
    lip = K.box(L - 2 * FRAME_W + 2 * 12.0, W - 2 * FRAME_W + 2 * 12.0, 4.0).translate(0, 0, T - 2.0) - \
        K.box(L - 2 * FRAME_W - 2.0, W - 2 * FRAME_W - 2.0, 10.0).translate(0, 0, T - 2.0)
    zc = T - 7.0
    back = K.box(L - 2 * FRAME_W, W - 2 * FRAME_W, 1.0).translate(0, 0, zc - 2.5)
    cells = K.box(L - 2 * FRAME_W - 30.0, W - 2 * FRAME_W - 30.0, 1.0).translate(0, 0, zc - 1.5)
    nx, ny = 18, 6                                                    # 18 × 6 nửa cell (91 × 182)
    gx = [(-(L - 2 * FRAME_W - 30.0) / 2 + i * (L - 2 * FRAME_W - 30.0) / nx) for i in range(1, nx)]
    gy = [(-(W - 2 * FRAME_W - 30.0) / 2 + j * (W - 2 * FRAME_W - 30.0) / ny) for j in range(1, ny)]
    slots = [K.box(2.0, W, 3.0).translate(x, 0, zc - 1.5) for x in gx] + [K.box(L, 2.0, 3.0).translate(0, y, zc - 1.5) for y in gy]
    cells = cells.subtract_all(slots)
    bus = K.Solid.union_all([K.box(L - 2 * FRAME_W - 40.0, 1.5, 0.3).translate(0, y + dy, zc - 0.85)
                             for y in np.linspace(-(W - 2 * FRAME_W - 30.0) / 2 + (W - 2 * FRAME_W - 30.0) / 12, (W - 2 * FRAME_W - 30.0) / 2 - (W - 2 * FRAME_W - 30.0) / 12, 6)
                             for dy in (-40.0, 0.0, 40.0)])
    glass = K.box(L - 2 * FRAME_W - 1.0, W - 2 * FRAME_W - 1.0, 3.2).translate(0, 0, zc + 1.6)
    jbox = K.rounded_box(150.0, 110.0, 22.0, 6.0, segments=6).translate(0.3 * L, 0, zc - 3.0 - 11.0)
    cab = [K.tube(np.array([[0.3 * L + 60.0, s * 40.0, zc - 14.0], [0.3 * L + 200.0, s * 150.0, zc - 16.0], [0.3 * L + 320.0, s * 150.0, zc - 16.0]]), 3.0, 8)
           for s in (1, -1)]
    mc4 = [K.cylinder(8.0, 60.0, segments=12).rotate(0, 90, 0).translate(0.3 * L + 320.0, s * 150.0, zc - 16.0) for s in (1, -1)]
    return {"frame": bake(frame + lip), "back": bake(back), "cells": bake(cells), "bus": bake(bus), "glass": bake(glass),
            "jbox": bake(jbox + K.Solid.union_all(mc4)), "cable": bake(K.Solid.union_all(cab))}


def c_channel(h: float, b: float, t: float, length: float) -> K.Solid:
    """Thép chữ C cán nguội (C h × b × t), đùn theo Z."""
    prof = np.array([(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + t), (-b / 2 + t, -h / 2 + t), (-b / 2 + t, h / 2 - t), (b / 2, h / 2 - t),
                     (b / 2, h / 2), (-b / 2, h / 2)])
    return K.extrude(P.ensure_ccw(prof), length)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    n_pan = int(p.get("panels", 12))
    rows = int(p.get("rows", 2))
    tilt = float(p.get("tilt_deg", 15.0))
    inv = bool(p.get("inverter", True))
    mats = MC.tech_materials(spec, primary="#1b3a6b", secondary="#8d99ae", accent="#f2b705")
    mats["pv_cell"] = M.material("pv_cell", "glass", "#16244a", 0.3, 0.25, name="Cell pin silicon")
    mats["pv_glass"] = M.material("pv_glass", "glass", "#cfd8e3", 0.0, 0.04, alpha=0.25, name="Kính cường lực phủ chống phản xạ")
    mats["backsheet"] = M.material("backsheet", "plastic", "#f1f2f3", 0.0, 0.6, name="Tấm nền trắng")
    mats["galvanized"] = M.material("galvanized", "metal", "#b3b9bf", 0.85, 0.42, name="Thép mạ kẽm nhúng nóng")
    mats["concrete"] = M.material("concrete", "stone", "#a3a39b", 0.0, 0.85, name="Bê tông móng")
    b = AssemblyBuilder(spec.name or f"Hệ điện mặt trời {n_pan} tấm × 400 Wp ({n_pan * 0.4:g} kWp)", "solar_array", mats)
    per_row = math.ceil(n_pan / rows)
    t = math.radians(tilt)
    gap = 20.0                                                        # khe giữa hai tấm (kẹp giữa)
    row_len = per_row * PW + (per_row - 1) * gap
    z_low = 600.0                                                     # mép dưới tấm
    run = PL * math.cos(t)
    rise = PL * math.sin(t)
    pitch = run + (rise + z_low * 0) / math.tan(math.radians(45.0)) + 1200.0     # tránh bóng khi mặt trời cao 45° + lối đi
    proto = panel_proto()
    h_p, b_p = 100.0, 50.0                                             # xà gồ C100×50
    h_r = 120.0                                                        # xà nghiêng C120
    footings, posts, rafters, purlins, braces = [], [], [], [], []
    clamps, panels = [], []
    xs_rows = [-(rows - 1) * pitch / 2 + i * pitch for i in range(rows)]
    n_frames = max(2, math.ceil(row_len / 3500.0) + 1)
    y_frames = np.linspace(-row_len / 2 + 300.0, row_len / 2 - 300.0, n_frames)
    k_idx = 0
    for ri, xr in enumerate(xs_rows):
        # tấm: tâm tấm ở (xr, y), mép dưới (phía Nam, +X) cao z_low
        x_front = xr + run / 2
        # mặt dưới khung tấm nằm trên xà gồ; xà gồ trên xà nghiêng
        def slope_point(s: float, above: float) -> np.ndarray:
            """Điểm trên mặt dốc: s dọc dốc từ mép dưới (m), `above` theo pháp tuyến mặt tấm."""
            base = np.array([x_front - s * math.cos(t), 0.0, z_low + s * math.sin(t)])
            n = np.array([math.sin(t), 0.0, math.cos(t)])
            return base + n * above
        for j in range(per_row):
            if k_idx >= n_pan:
                break
            y = -row_len / 2 + PW / 2 + j * (PW + gap)
            c = slope_point(PL / 2, 0.0)
            mat = K.affine(K.rotation_matrix((0, 1, 0), tilt), (c[0], y, c[2]))
            pan = {k: v.transform(mat) for k, v in proto.items()}
            panels.append((k_idx, pan))
            k_idx += 1
        # xà gồ (2 thanh dọc hàng) ngay dưới khung tấm, ở 1/4 và 3/4 chiều dài tấm
        for s in (0.22 * PL, 0.78 * PL):
            c = slope_point(s, -h_p / 2)
            pur = K.box(b_p, row_len + 200.0, h_p) - K.box(b_p - 6.0, row_len + 400.0, h_p - 6.0).translate(2.0, 0, 0)
            purlins.append(pur.transform(K.affine(K.rotation_matrix((0, 1, 0), tilt), (c[0], 0.0, c[2]))))
            # kẹp giữa / kẹp biên tại khe tấm
            for j in range(per_row + 1):
                y = -row_len / 2 - gap / 2 + j * (PW + gap)
                yc = min(max(y, -row_len / 2 - 20.0), row_len / 2 + 20.0)
                cp = slope_point(s, PT + 4.0)
                cl = K.box(60.0, 40.0 if 0 < j < per_row else 30.0, 8.0) + K.cylinder(4.0, PT + 6.0, segments=10).translate(0, 0, -PT - 2.0)
                clamps.append(cl.transform(K.affine(K.rotation_matrix((0, 1, 0), tilt), (cp[0], yc + (0 if 0 < j < per_row else (15.0 if j == 0 else -15.0)), cp[2]))))
        # khung: xà nghiêng dưới xà gồ, cột trước/sau xuống móng
        for yf in y_frames:
            a0 = slope_point(-60.0, -h_p - h_r / 2)
            a1 = slope_point(PL + 60.0, -h_p - h_r / 2)
            raf = c_channel(h_r, 55.0, 3.0, float(np.linalg.norm(a1 - a0)))
            dirv = (a1 - a0) / np.linalg.norm(a1 - a0)
            rafters.append(MC.orient(raf, [a0[0], yf, a0[2]], dirv))
            for s_post, xo in ((0.12 * PL, 0.0), (0.88 * PL, 0.0)):
                top = slope_point(s_post, -h_p - h_r)
                col = c_channel(100.0, 50.0, 3.0, top[2] - 300.0).rotate(0, 0, 90).translate(top[0], yf, 300.0)
                posts.append(col)
                footings.append(K.chamfer_box(400.0, 400.0, 300.0, 20.0).translate(top[0], yf, 150.0))
            # thanh chống chéo từ chân cột sau lên xà
            pb = slope_point(0.88 * PL, -h_p - h_r)
            pa = np.array([pb[0] + 0.45 * PL * math.cos(t), yf, 700.0])
            braces.append(K.tube(np.array([pa, slope_point(0.55 * PL, -h_p - h_r) + np.array([0, yf, 0])]), 22.0, 10))
    b.add("footings", f"Móng bê tông ({len(footings)})", "Concrete footings", "foundation", Shape(K.Solid.union_all(footings), "concrete", 35.0),
          required=True, aliases=["móng", "móng trụ", "foundation"], function="Móng bê tông đúc tại chỗ cho từng cột.", position_tag="bottom")
    b.add("structure", "Giá đỡ thép mạ kẽm (cột, xà nghiêng, xà gồ, chống)", "Mounting structure", "rack",
          [Shape(K.Solid.union_all(posts + rafters + braces), "galvanized", 35.0), Shape(K.Solid.union_all(purlins), "galvanized", 35.0)],
          parent_id="footings", required=True, aliases=["giá đỡ", "khung giá", "xà gồ", "cột giá", "rack", "kết cấu đỡ"],
          function=f"Cột C100 + xà nghiêng C120 nghiêng {tilt:g}°, 2 xà gồ C100×50 mỗi hàng, thanh chống chéo.", position_tag="center",
          explode_dir=(0, 0, -1), explode_distance=800.0, explode_order=3)
    for idx, pan in panels:
        b.add(f"panel_{idx + 1}", f"Tấm pin {idx + 1} (400 Wp)", "PV module", "solar_panel",
              [Shape(pan["cells"], "pv_cell", 35.0), Shape(pan["glass"], "pv_glass", 35.0), Shape(pan["frame"], "aluminum", 35.0),
               Shape(pan["back"], "backsheet", 35.0), Shape(pan["bus"], "stainless", 35.0), Shape(pan["jbox"], "plastic_black", 35.0),
               Shape(pan["cable"], "cable_black", 35.0)], parent_id="structure", required=True,
              aliases=["tấm pin", "pin mặt trời", "tấm pin năng lượng mặt trời", "module", "cell", "khung nhôm", "hộp nối", f"tấm {idx + 1}"],
              function="Tấm pin đơn tinh thể 108 cell nửa, khung nhôm, kính cường lực 3,2 mm, hộp nối IP68 + cáp MC4.",
              position_tag="top", explode_dir=(math.sin(t), 0, math.cos(t)), explode_distance=500.0, explode_order=2,
              dimensions={"length": PL, "width": PW, "thickness": PT})
    b.add("clamps", f"Kẹp giữa / kẹp biên ({len(clamps)})", "Module clamps", "clamp", Shape(K.Solid(m3d.Manifold.compose([c.m for c in clamps])), "aluminum", 35.0),
          parent_id="structure", required=True, aliases=["kẹp pin", "kẹp giữa", "kẹp biên", "clamp"], function="Kẹp nhôm + bu-lông M8 giữ khung tấm trên xà gồ.",
          position_tag="top", explode_dir=(math.sin(t), 0, math.cos(t)), explode_distance=900.0, explode_order=1)
    contacts = [["clamps", "panel_*"]]
    if inv:
        x_inv = min(xs_rows) - run / 2 - 1500.0                        # trước hàng pin đầu tiên (phía Nam)
        y_inv = -row_len / 2 + 600.0
        stand = K.Solid.union_all([c_channel(80.0, 40.0, 3.0, 1700.0).rotate(0, 0, 90).translate(x_inv, y_inv + dy, 300.0) for dy in (-300.0, 300.0)]
                                  + [K.box(80.0, 700.0, 60.0).translate(x_inv, y_inv, 300.0 + 1100.0)])
        pads = K.Solid.union_all([K.chamfer_box(300.0, 300.0, 300.0, 15.0).translate(x_inv, y_inv + dy, 150.0) for dy in (-300.0, 300.0)])
        invb = K.rounded_box(220.0, 560.0, 680.0, 30.0, segments=8).translate(x_inv - 40.0 - 110.0, y_inv, 300.0 + 1100.0)
        fins = K.Solid.union_all([K.box(30.0, 500.0, 6.0).translate(x_inv - 40.0 - 220.0 - 15.0, y_inv, 300.0 + 800.0 + i * 50.0) for i in range(12)])
        disp = K.box(3.0, 140.0, 80.0).translate(x_inv - 40.0 - 220.0 - 1.5, y_inv, 300.0 + 1350.0)
        cab_x, cab_y = x_inv, y_inv + 1400.0
        plinth = K.box(700.0, 500.0, 200.0).translate(cab_x, cab_y, 100.0)
        cab = K.rounded_box(600.0, 400.0, 1200.0, 15.0, segments=6).translate(cab_x, cab_y, 200.0 + 600.0)
        handle = K.box(15.0, 30.0, 150.0).translate(cab_x - 300.0 - 7.5, cab_y + 120.0, 200.0 + 700.0)
        b.add("inverter", "Biến tần hòa lưới + giá treo", "Grid-tie inverter", "inverter",
              [Shape(invb + fins, "aluminum_dark", 35.0), Shape(disp, "glass_tinted", 35.0), Shape(stand, "galvanized", 35.0), Shape(pads, "concrete", 35.0)],
              parent_id=None, required=True, aliases=["biến tần", "inverter", "bộ hòa lưới", "inverter hòa lưới"],
              function=f"Biến tần hòa lưới 3 pha ~{n_pan * 0.4 * 0.9:.1f} kW, tản nhiệt nhôm, màn hình.", position_tag="front",
              explode_dir=(-1, 0, 0), explode_distance=800.0, explode_order=1)
        b.add("cabinet", "Tủ điện AC/DC + bệ", "AC/DC cabinet", "cabinet",
              [Shape(cab, "paint_secondary", 35.0), Shape(handle, "steel_dark", 35.0), Shape(plinth, "concrete", 35.0)], parent_id=None, required=True,
              aliases=["tủ điện", "tủ AC DC", "tủ phân phối", "cabinet"], function="Tủ điện có cầu dao DC/AC, chống sét lan truyền, đồng hồ đo đếm.",
              position_tag="front", explode_dir=(-1, 0, 0), explode_distance=800.0, explode_order=1)
        cond = []
        for xr in xs_rows:
            pa = np.array([xr, -row_len / 2 - 150.0, 300.0])
            cond.append(K.tube(np.array([pa, [x_inv + 100.0, -row_len / 2 - 150.0, 300.0], [x_inv + 100.0, y_inv - 150.0, 300.0]]), 20.0, 10))
        cond.append(K.tube(np.array([[x_inv + 100.0, y_inv + 150.0, 300.0], [x_inv + 100.0, cab_y - 150.0, 300.0], [cab_x - 50.0, cab_y - 150.0, 250.0]]), 20.0, 10))
        b.add("conduits", "Ống luồn cáp DC/AC", "Cable conduits", "conduit", Shape(K.Solid.union_all(cond), "cable_black", 35.0), parent_id="inverter",
              required=True, aliases=["ống luồn cáp", "cáp", "dây cáp", "conduit"], function="Ống HDPE luồn cáp DC từ các hàng pin tới biến tần, cáp AC tới tủ.",
              position_tag="bottom", explode_dir=(0, 0, 1), explode_distance=300.0, explode_order=1)
        contacts += [["conduits", "cabinet"]]
    b.note_stage(1, "Tháo kẹp, biến tần, tủ điện, ống cáp")
    b.note_stage(2, "Nhấc tấm pin")
    b.note_stage(3, "Tháo giá đỡ khỏi móng")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"panels": n_pan, "rows": rows, "per_row": per_row, "tilt_deg": tilt, "panel_mm": [PL, PW, PT], "row_pitch_mm": pitch,
                       "z_low_mm": z_low, "kwp": n_pan * 0.4,
                       "standard": "Tấm 400 Wp 1722 × 1134 × 30 mm (IEC 61215/61730), giá thép mạ kẽm; góc nghiêng tối ưu VN 10–20°",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
