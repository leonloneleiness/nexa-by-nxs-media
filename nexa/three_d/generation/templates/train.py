"""Đầu máy + toa xe trên đoạn đường ray khổ 1000 mm (đường sắt Việt Nam) hoặc 1435 mm.

- Đường ray: nền đá ba lát hình thang, tà vẹt bê tông cách 600 mm, ray P43 (khổ mét) / UIC 60 (khổ chuẩn) có đệm ray;
  khổ đường = khoảng cách mép trong hai nấm ray (standards.RAIL_GAUGE).
- Bộ trục bánh: bánh thép mặt lăn côn 1:20 + gờ bánh cao 28 mm phía trong, cự ly lưng bánh = khổ − 70 mm; mặt lăn tì
  đúng đỉnh ray, gờ bánh nằm trong mép trong nấm ray (không xuyên ray); hộp trục ổ lăn hai đầu.
- Giá chuyển hướng (bogie) hai trục: khung chữ H, lò xo trục (hệ treo 1), đệm khí (hệ treo 2), guốc hãm + quang treo,
  động cơ kéo treo trục (đầu máy).
- Đầu máy: thân thùng vỏ mỏng, cabin lái mũi dốc + kính chắn gió, đèn pha, lưới tản nhiệt, ống xả + quạt mái (diesel)
  hoặc cần lấy điện (pantograph) tì lên dây tiếp xúc treo trên 2 cột (tàu điện), thùng nhiên liệu, lan can.
- Toa khách: dãy cửa sổ kính, viền cửa lên xuống hai đầu, điều hòa trên mái; toa hàng kín: vách gân, viền cửa lùa.
- Móc nối tự động kiểu AAR (đường sắt Việt Nam dùng móc nối tự động), đầu móc hai toa chạm nhau ở giữa khe hở.

Tỷ lệ theo đầu máy D19E (dài 16,5 m, rộng 2,75 m, bánh Ø1016) và toa khách khổ mét (20 m).
Tháo: thiết bị mái + móc nối → thân xe nhấc lên → khung bogie nhấc khỏi bộ trục bánh (bộ trục bánh nằm lại trên ray).
"""
from __future__ import annotations

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import details as D
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

TO_X = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])      # đùn theo Z → dọc X (mặt cắt (u, v) → (y, z))


def rail_section(prof: dict) -> np.ndarray:
    """Mặt cắt ray chữ I (đế rộng, thân mảnh, nấm ray bo tròn) — mặt (y, z), đáy z = 0, tâm y = 0."""
    h, hw, fw, web = prof["height"], prof["head"], prof["foot"], prof["web"]
    pts = [(-fw / 2, 0), (fw / 2, 0), (fw / 2, 0.08 * h), (web / 2, 0.22 * h), (web / 2, 0.66 * h), (hw / 2, 0.72 * h),
           (hw / 2, 0.95 * h), (hw / 2 - 0.08 * hw, h), (-hw / 2 + 0.08 * hw, h), (-hw / 2, 0.95 * h), (-hw / 2, 0.72 * h),
           (-web / 2, 0.66 * h), (-web / 2, 0.22 * h), (-fw / 2, 0.08 * h)]
    return P.fillet_polygon(pts, [0, 0, 1.0, 6.0, 6.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, 6.0, 6.0, 1.0], 3)


def wheel_profile(Rw: float) -> tuple[np.ndarray, float, float]:
    """Mặt cắt bánh xe (r, t) — t đo từ mặt lưng bánh (phía trong) ra ngoài; gờ bánh ở phía trong.
    Trả (profile, t điểm lăn danh nghĩa, bề rộng bánh)."""
    wf, hf, W = 32.0, 28.0, 130.0
    t_c = wf + 40.0
    pts = [(Rw * 0.62, 0.0), (Rw + hf - 4.0, 0.0), (Rw + hf, wf * 0.35), (Rw + hf - 6.0, wf * 0.8), (Rw + 1.6, wf)]
    for t in np.linspace(wf + 2, W - 6, 10):
        pts.append((Rw - (t - t_c) / 20.0, t))                        # mặt lăn côn 1:20
    pts += [(Rw - (W - 6 - t_c) / 20.0 - 4.0, W), (Rw * 0.62, W)]
    return np.array(pts), t_c, W


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    gk = p.get("gauge", "meter")
    G = S.RAIL_GAUGE[gk]
    rp = S.RAIL_PROFILE[gk]
    electric = p.get("traction", "diesel") == "electric"
    n_wag = int(p.get("wagons", 2))
    freight = p.get("wagon_type", "passenger") == "freight"
    k = 1.0 if gk == "meter" else 1.15                                # khổ chuẩn: xe to hơn
    mats = MC.tech_materials(spec, primary="#1f4e8c" if not electric else "#e9ecef", secondary="#e9ecef" if not electric else "#1f4e8c",
                             accent="#e63946")
    mats["concrete"] = M.material("concrete", "stone", "#9a9a94", 0.0, 0.85, name="Bê tông (tà vẹt, cột)")
    mats["ballast"] = M.material("ballast", "stone", "#6f6a62", 0.0, 0.95, name="Đá ba lát")
    b = AssemblyBuilder(spec.name or ("Tàu điện" if electric else "Đầu máy diesel") + (f" + {n_wag} toa" if n_wag else ""), "train", mats)
    L_loco = 16500.0 * k
    L_wag = (14000.0 if freight else 20000.0) * k
    gap = 900.0
    cars = [("loco", L_loco)] + [(f"wagon_{i + 1}", L_wag) for i in range(n_wag)]
    total = sum(L for _, L in cars) + gap * (len(cars) - 1)
    # ---------- đường ray ----------
    z_bal, z_sl = 250.0, 300.0
    rail_top = z_sl + 10.0 + rp["height"]
    L_tr = total + 6000.0
    x_tr0 = L_loco / 2 + 3000.0 - L_tr                                 # đầu máy ở +X, các toa kéo về −X
    bal = K.extrude(np.array([[-G / 2 - 1400, 0], [G / 2 + 1400, 0], [G / 2 + 900, z_bal], [-G / 2 - 900, z_bal]]), L_tr)
    bal = bal.transform(TO_X).translate(x_tr0, 0, 0)
    sleeper = K.chamfer_box(250.0, G + 1000.0, 200.0, 15.0).translate(0, 0, z_sl - 100.0)
    xs_sl = np.arange(x_tr0 + 300.0, x_tr0 + L_tr - 300.0, 600.0)
    sleepers = K.Solid.union_all([sleeper.translate(x, 0, 0) for x in xs_sl])
    y_head = G / 2 + rp["head"] / 2                                   # tâm nấm ray (mép trong nấm ray = khổ/2)
    rsec = MC.cs(rail_section(rp))
    rails, pads = [], []
    for sy in (1, -1):
        rails.append(MC.extrude_cs(rsec, L_tr - 200.0).transform(TO_X).translate(x_tr0 + 100.0, sy * y_head, z_sl + 10.0))
        pads.append(K.Solid.union_all([K.box(180.0, rp["foot"] + 20, 10.0).translate(x, sy * y_head, z_sl + 5.0) for x in xs_sl]))
    b.add("track", f"Đường ray khổ {G:g} mm", f"Track, gauge {G:g} mm", "track",
          [Shape(bal, "ballast", 35.0), Shape(sleepers, "concrete", 35.0), Shape(K.Solid.union_all(rails), "steel", 35.0),
           Shape(K.Solid.union_all(pads), "rubber", 35.0)], required=True,
          aliases=["đường ray", "ray", "tà vẹt", "đá ba lát", "track", "rail", "khổ đường"],
          function=f"Ray {'P43' if gk == 'meter' else 'UIC 60'} trên tà vẹt bê tông cách 600 mm, nền đá ba lát; khổ {G:g} mm.",
          position_tag="bottom", dimensions={"gauge": G})
    contacts: list[list[str]] = [["*wheelset*", "track"]]
    prof_cache: dict = {}
    bb = G - 70.0                                                      # cự ly lưng bánh

    def wheelset(pid: str, x: float, Rw: float) -> float:
        if Rw not in prof_cache:
            pr, t_c, W = wheel_profile(Rw)
            web = K.revolve([(Rw * 0.2, 20), (Rw * 0.62, 5), (Rw * 0.62, W - 5), (Rw * 0.2, W - 20)], segments=48)
            prof_cache[Rw] = (K.revolve(pr, segments=72) + web, t_c, W)
        wheel, t_c, W = prof_cache[Rw]
        back = y_head - t_c                                            # lưng bánh sao cho điểm lăn trùng tâm nấm ray
        zc = rail_top + Rw
        ws = []
        for sy in (1, -1):
            rot = np.array([[1.0, 0, 0], [0, 0, sy * 1.0], [0, -sy * 1.0, 0]])      # trục revolve (Z) → ±Y, lưng bánh phía trong
            ws.append(wheel.transform(K.affine(rot, (x, sy * back, zc))))
        axle_l = 2 * (back + W) + 360.0
        axle = K.cylinder(0.16 * Rw, axle_l, segments=32).rotate(90, 0, 0).translate(x, axle_l / 2, zc)
        boxes = K.Solid.union_all([K.rounded_box(260.0, 170.0, 240.0, 30.0, segments=16).translate(x, sy * (axle_l / 2 - 85.0), zc) for sy in (1, -1)])
        b.add(pid, "Bộ trục bánh", "Wheelset", "wheelset",
              [Shape(K.Solid.union_all(ws), "steel", 60.0), Shape(axle, "steel_dark", 60.0), Shape(boxes, "cast_iron", 60.0)],
              parent_id="track", required=True, aliases=["bộ trục bánh", "bánh xe", "bánh sắt", "trục bánh", "wheelset", "hộp trục"],
              function=f"Bánh thép Ø{2 * Rw:.0f} mặt lăn côn 1:20 + gờ bánh, cự ly lưng bánh {bb:g} mm, hộp trục ổ lăn.",
              position_tag="bottom", joint_axis=(0, 1, 0))
        return axle_l

    def bogie(pid: str, x: float, Rw: float, wb: float, motor: bool, ws1: str, ws2: str) -> float:
        axle_l = 0.0
        for wid, dx in ((ws1, -wb / 2), (ws2, wb / 2)):
            axle_l = wheelset(wid, x + dx, Rw)
        zc = rail_top + Rw
        y_sf = axle_l / 2 - 85.0
        z0 = zc + 120.0                                                # đỉnh hộp trục
        spr_h = 150.0
        frame_z = z0 + 20.0 + spr_h
        sides = [K.rounded_box(wb + 900.0, 170.0, 200.0, 40.0, segments=16).translate(x, sy * y_sf, frame_z + 100.0) for sy in (1, -1)]
        transom = K.box(700.0, 2 * y_sf - 150.0, 180.0).translate(x, 0, frame_z + 100.0)
        frame = K.Solid.union_all(sides + [transom])
        springs, seats = [], []
        for dx in (-wb / 2, wb / 2):
            for sy in (1, -1):
                seats.append(K.box(520.0, 170.0, 20.0).translate(x + dx, sy * y_sf, z0 + 10.0))
                for off in (-150.0, 150.0):
                    path = MC.helix_path(55.0, [(4.0, spr_h / 4.0)], z0=0.0, per_turn=12)
                    springs.append(K.tube(path, 14.0, 8).translate(x + dx + off, sy * y_sf, z0 + 20.0))
        brakes, hangers = [], []
        for dx in (-wb / 2, wb / 2):
            for sx in (1, -1):
                for sy in (1, -1):
                    xb = x + dx + sx * (Rw + 36.0)
                    brakes.append(K.rounded_box(60.0, 110.0, 300.0, 10.0, segments=16).translate(xb, sy * y_head, zc))
                    y0, y1 = sorted((sy * y_head, sy * y_sf))
                    hangers.append(K.box(40.0, (y1 - y0) + 60.0, 50.0).translate(xb, (y0 + y1) / 2, frame_z + 25.0))
                    hangers.append(K.box(40.0, 60.0, frame_z + 50.0 - (zc + 150.0)).translate(xb, sy * y_head, (frame_z + 50.0 + zc + 150.0) / 2))
        bolster_z = frame_z + 200.0
        airs = K.Solid.union_all([K.cylinder(230.0, 150.0, segments=40).translate(x, sy * (y_sf - 60.0), bolster_z) for sy in (1, -1)])
        shapes = [Shape(frame, "steel_dark", 60.0), Shape(K.Solid.union_all(springs), "spring_steel", 60.0),
                  Shape(K.Solid.union_all(seats), "steel_dark", 60.0), Shape(K.Solid.union_all(brakes + hangers), "cast_iron", 60.0),
                  Shape(airs, "rubber", 60.0)]
        if motor:
            ml = 0.8 * (2 * y_sf - 700.0)
            rm, zm = 0.45 * Rw, zc + 30.0                               # động cơ treo trục, đỉnh thấp hơn khung bogie
            mot = K.Solid.union_all([K.cylinder(rm, ml, segments=40).rotate(90, 0, 0).translate(x + dx - np.sign(dx) * 0.85 * Rw, ml / 2, zm)
                                     for dx in (-wb / 2, wb / 2)])
            h_m = frame_z + 30.0 - (zm + rm - 20.0)
            mounts = K.Solid.union_all([K.box(300.0, 300.0, h_m).translate(x + dx - np.sign(dx) * 0.85 * Rw, 0, zm + rm - 20.0 + h_m / 2)
                                        for dx in (-wb / 2, wb / 2)])
            shapes.append(Shape(mot + mounts, "steel_black_oxide", 60.0))
        b.add(pid, "Giá chuyển hướng (bogie)", "Bogie", "bogie", shapes, parent_id=ws1, required=True,
              aliases=["giá chuyển hướng", "bogie", "khung bogie", "lò xo", "hệ treo", "guốc hãm", "động cơ kéo"],
              function="Bogie 2 trục: khung chữ H, lò xo trục (treo 1), đệm khí (treo 2), guốc hãm" + (", động cơ kéo treo trục." if motor else "."),
              position_tag="bottom", explode_dir=(0, 0, 1), explode_distance=1.6 * Rw + 600.0, explode_order=3)
        contacts.append([pid, ws2])
        return bolster_z + 150.0                                       # mặt trên đệm khí = đáy thân xe (≈ 1,1 m trên đỉnh ray)

    W_body = 2750.0 * k
    H_body = 2700.0 * k                                               # cao thân ≈ 4,1 m trên đỉnh ray kể cả mái (khổ giới hạn VN ≈ 4,2 m)
    x_cur = 0.0
    couplers = []
    for ci, (cid, Lc) in enumerate(cars):
        is_loco = cid == "loco"
        xc = x_cur
        Rw = (508.0 if is_loco else 420.0) * k
        wb = (2600.0 if is_loco else 2400.0) * k
        b_off = 0.3 * Lc
        zb0 = 0.0
        for j, sx in enumerate((1, -1)):
            zb0 = bogie(f"{cid}_bogie_{j + 1}", xc + sx * b_off, Rw, wb, is_loco, f"{cid}_wheelset_{2 * j + 1}", f"{cid}_wheelset_{2 * j + 2}")
        outer = K.rounded_box(Lc, W_body, H_body, 180.0, segments=24).translate(xc, 0, zb0 + H_body / 2)
        outer = outer + K.hull([K.box(Lc - 400.0, W_body - 300.0, 1.0).translate(xc, 0, zb0 + H_body - 0.5),
                                K.box(Lc - 800.0, W_body * 0.55, 1.0).translate(xc, 0, zb0 + H_body + 260.0)])
        if is_loco:
            cut = K.box(1500.0, W_body * 2, H_body).translate(xc + Lc / 2 - 750.0 + 1.0, 0, zb0 + H_body * 0.55 + H_body / 2)
            nose = K.hull([K.box(1.0, W_body - 100.0, H_body * 0.55).translate(xc + Lc / 2 - 0.5, 0, zb0 + H_body * 0.28),
                           K.box(1.0, W_body - 300.0, 1.0).translate(xc + Lc / 2 - 1500.0, 0, zb0 + H_body + 200.0),
                           K.box(1.0, W_body - 100.0, 1.0).translate(xc + Lc / 2 - 0.5, 0, zb0 + H_body * 0.55)])
            outer = (outer - cut) + (nose & K.box(1e6, W_body, 1e6))
        shell_t = 60.0
        body = outer                                                   # thân đặc: kính là lớp mặt ngoài trong hốc cửa (không nhìn xuyên)
        glass = []
        if is_loco:
            # mặt dốc mũi: từ (Lc/2, 0,55H) lên (Lc/2 − 1500, H + 200); hộp ô kính đặt tâm trên mặt dốc, dày đều ±150 mm theo pháp tuyến
            rise = 0.45 * H_body + 200.0
            nose_n = np.array([rise, 0.0, 1500.0]) / np.hypot(rise, 1500.0)
            t_w = 0.18 * H_body / rise
            glass.append((K.box(300.0, W_body * 0.68, H_body * 0.22).rotate(0, -np.degrees(np.arctan2(nose_n[2], nose_n[0])), 0)
                          .translate(xc + Lc / 2 - 1500.0 * t_w, 0, zb0 + 0.55 * H_body + rise * t_w), nose_n))
            for sy in (1, -1):
                glass.append((K.box(900.0, 400.0, 700.0).translate(xc + Lc / 2 - 2200.0, sy * W_body / 2, zb0 + H_body * 0.72),
                              np.array([0.0, sy, 0.0])))
        elif not freight:
            for xx in np.linspace(-Lc / 2 + 2500.0, Lc / 2 - 2500.0, 10):
                for sy in (1, -1):
                    glass.append((K.rounded_box(1100.0, 400.0, 800.0, 80.0, segments=16).translate(xc + xx, sy * W_body / 2, zb0 + H_body * 0.62),
                                  np.array([0.0, sy, 0.0])))
        glass_s = None
        if glass:
            # kính = lớp ngoài 10 mm trong ô cửa, hốc cửa sâu 45 mm: mặt kính trùng mặt vỏ, sau kính cách đáy hốc 35 mm
            # (không mặt nào trùng mặt nào → không nhiễu sọc; không khoét thủng vỏ)
            clip = K.box(1e6, 1e6, 0.88 * H_body).translate(xc, 0, zb0 + 0.44 * H_body)
            recs, panes = [], []
            for box_, n_ in glass:                                     # lệch đúng theo pháp tuyến ô cửa (không co giãn)
                w_ = box_ & outer & clip
                recs.append((box_ & clip) - outer.translate(*(-n_ * 45.0)))    # hốc nhô ra ngoài vỏ → phép trừ không có mặt trùng
                panes.append(w_ - outer.translate(*(-n_ * 10.0)))
            body = body - K.Solid.union_all(recs)
            glass_s = K.Solid.union_all(panes)
        if is_loco and not electric:
            body = body - K.Solid.union_all([D.vent_cutter((xc - Lc * 0.15, sy * W_body / 2, zb0 + H_body * 0.62), (0, sy, 0), (1, 0, 0),
                                                           0.35 * Lc, 450.0, 18, 2 * shell_t, segments=8) for sy in (1, -1)])
        body = body - D.panel_lines(outer, [("z", zb0 + H_body * 0.35)], width=12.0, depth=8.0)
        if not is_loco:
            for dx in ((-Lc / 2 + 1100.0, Lc / 2 - 1100.0) if not freight else (0.0,)):
                body = body - D.outline_groove(outer, (xc + dx, 0, zb0 + H_body * 0.48), 800.0 if not freight else 2200.0,
                                               H_body * 0.82, 14.0, 10.0)
        else:
            body = body - D.outline_groove(outer, (xc + Lc / 2 - 3000.0, 0, zb0 + H_body * 0.5), 700.0, H_body * 0.8, 14.0, 10.0)
        if freight and not is_loco:
            ribs = K.Solid.union_all([K.box(60.0, W_body + 40.0, H_body * 0.92).translate(xc + xx, 0, zb0 + H_body * 0.48)
                                      for xx in np.linspace(-Lc / 2 + 600.0, Lc / 2 - 600.0, 13)])
            body = body + (ribs - K.box(Lc * 2, W_body - 2.0, H_body * 3).translate(xc, 0, zb0))
        shapes = [Shape(body, "paint_primary", 35.0)]
        band = K.rounded_box(Lc + 4.0, W_body + 4.0, 180.0, 60.0, segments=16).translate(xc, 0, zb0 + H_body * 0.35) - \
            K.rounded_box(Lc - 1.0, W_body - 1.0, 400.0, 60.0, segments=16).translate(xc, 0, zb0 + H_body * 0.35)
        shapes.append(Shape(band & K.box(1e6, 1e6, 1e6).translate(xc, 0, 0) - (glass_s if glass_s is not None else K.box(1, 1, 1).translate(0, 0, -1e5)),
                            "paint_secondary", 35.0))
        if glass_s is not None:
            shapes.append(Shape(glass_s, "glass_tinted", 35.0))
        uf = K.box(Lc - 600.0, W_body - 400.0, 300.0).translate(xc, 0, zb0 - 150.0 + 0.5)
        uf = uf.subtract_all([K.box(2 * Rw + wb + 900.0, W_body * 2, 700.0).translate(xc + sx * b_off, 0, zb0 - 150.0) for sx in (1, -1)])
        z_cp = rail_top + 880.0 * k                                     # chiều cao tâm móc nối (AAR 876 mm)
        sills = K.Solid.union_all([K.box(260.0, W_body - 300.0, zb0 + 1.0 - (z_cp - 260.0)).translate(
            xc + sx * (Lc / 2 - 130.0), 0, (zb0 + 1.0 + z_cp - 260.0) / 2) for sx in (1, -1)])
        uf = uf + sills
        shapes.append(Shape(uf, "steel_dark", 35.0))
        if is_loco:
            lamp = K.Solid.union_all([K.cylinder(90.0, 40.0, segments=32).rotate(0, 90, 0).translate(xc + Lc / 2 - 30.0, sy * W_body * 0.3, zb0 + H_body * 0.3)
                                      for sy in (1, -1)])
            shapes.append(Shape(lamp, "led_white", 35.0))
            if not electric:
                shapes.append(Shape(K.rounded_box(Lc * 0.28, W_body - 600.0, 700.0, 120.0, segments=16).translate(xc, 0, zb0 - 650.0 + 1.0), "steel_dark", 35.0))
        hand = K.Solid.union_all([K.tube(np.array([[xc - Lc * 0.4, sy * (W_body / 2 + 40.0), zb0 + 1200.0],
                                                   [xc + Lc * 0.35, sy * (W_body / 2 + 40.0), zb0 + 1200.0]]), 18.0, 10) for sy in (1, -1)])
        posts = K.Solid.union_all([K.box(30.0, 42.0, 60.0).translate(xc + xx, sy * (W_body / 2 + 20.0), zb0 + 1200.0)
                                   for xx in np.linspace(-Lc * 0.4, Lc * 0.35, 6) for sy in (1, -1)])
        shapes.append(Shape(hand + posts, "paint_yellow", 35.0))
        name = ("Thân đầu máy " + ("điện" if electric else "diesel")) if is_loco else f"Toa {'hàng kín' if freight else 'khách'} {ci}"
        b.add(f"{cid}_body", name, "Car body", "car_body", shapes, parent_id=f"{cid}_bogie_1", required=True,
              aliases=(["thân đầu máy", "đầu máy", "cabin lái", "buồng lái", "locomotive"] if is_loco else
                       [f"toa {ci}", "toa xe", "toa", "wagon", "coach"] + (["toa hàng"] if freight else ["toa khách", "cửa sổ"])),
              function=("Thân đầu máy: cabin lái kính chắn gió dốc, đèn pha" + ("" if electric else ", lưới tản nhiệt két nước, thùng dầu") + ".")
              if is_loco else ("Toa hàng kín vách gân, cửa lùa." if freight else "Toa khách: dãy cửa sổ kính, cửa lên xuống hai đầu."),
              position_tag="center", explode_dir=(0, 0, 1), explode_distance=H_body * 0.9 + 800.0, explode_order=2,
              dimensions={"length": Lc, "width": W_body})
        contacts.append([f"{cid}_body", f"{cid}_bogie_2"])
        roof_top = zb0 + H_body + 260.0
        if is_loco and electric:
            bx = xc - Lc * 0.15
            ins = K.Solid.union_all([K.cylinder(60.0, 300.0, segments=16).translate(bx + dx, dy, roof_top - 1.0) for dx in (-500.0, 500.0) for dy in (-400.0, 400.0)])
            frame_p = K.box(1300.0, 1000.0, 60.0).translate(bx, 0, roof_top + 329.0)
            wire_z = roof_top + 1900.0
            knee = np.array([bx + 900.0, 0.0, roof_top + 1100.0])
            lower = K.tube(np.array([[bx - 400.0, 0, roof_top + 360.0], knee]), 45.0, 12)
            upper = K.tube(np.array([knee, [bx - 200.0, 0, wire_z - 120.0]]), 35.0, 12)
            head = K.box(300.0, 1900.0, 60.0).translate(bx - 200.0, 0, wire_z - 60.0)
            strip = K.box(80.0, 1500.0, 30.0).translate(bx - 200.0, 0, wire_z - 15.0)
            b.add("pantograph", "Cần lấy điện (pantograph)", "Pantograph", "pantograph",
                  [Shape(ins, "ceramic", 35.0), Shape(frame_p + lower + upper + head, "steel", 35.0), Shape(strip, "carbon", 35.0)],
                  parent_id=f"{cid}_body", required=True, aliases=["cần lấy điện", "pantograph", "cần vẹt", "bộ lấy điện"],
                  function="Cần lấy điện một tay đòn, trượt than chì tì lên dây tiếp xúc 25 kV.", position_tag="top",
                  explode_dir=(0, 0, 1), explode_distance=1500.0, explode_order=1)
            mast_x = [x_tr0 + 1500.0, x_tr0 + L_tr - 1500.0]
            y_m = G / 2 + 2200.0
            masts = K.Solid.union_all([K.box(300.0, 300.0, wire_z + 500.0).translate(mx, y_m, (wire_z + 500.0) / 2) for mx in mast_x])
            arms = K.Solid.union_all([K.tube(np.array([[mx, y_m - 150.0, wire_z + 300.0], [mx, 0.0, wire_z + 300.0]]), 50.0, 12) for mx in mast_x])
            droppers = K.Solid.union_all([K.cylinder(8.0, 290.0, segments=8).translate(mx, 0.0, wire_z + 12.0) for mx in mast_x])
            wire = K.cylinder(7.0, L_tr - 3000.0, segments=12).rotate(0, 90, 0).translate(x_tr0 + 1500.0, 0.0, wire_z + 7.0)
            b.add("catenary", "Dây tiếp xúc + cột điện", "Overhead catenary", "catenary",
                  [Shape(masts, "concrete", 35.0), Shape(arms + droppers, "steel", 35.0), Shape(wire, "copper", 35.0)],
                  parent_id="track", required=True, aliases=["dây tiếp xúc", "lưới điện", "cột điện", "catenary", "dây điện trên cao"],
                  function="Dây tiếp xúc đồng treo trên cột bê tông; cần lấy điện tì lên dây.", position_tag="top")
            contacts += [["pantograph", "catenary"], ["catenary", "track"]]
        elif is_loco:
            stack = K.Solid.union_all([K.cylinder(160.0, 450.0, segments=24).translate(xc - Lc * 0.05 + dx, 0, roof_top - 60.0) for dx in (0.0, 500.0)])
            fans = K.Solid.union_all([K.cylinder(600.0, 120.0, segments=48).translate(xc - Lc * 0.28 + dx, 0, roof_top - 60.0) for dx in (0.0, 1500.0)])
            fans = fans - K.Solid.union_all([K.box(1300.0, 40.0, 60.0).rotate(0, 0, a).translate(xc - Lc * 0.28 + dx, 0, roof_top + 60.0)
                                             for dx in (0.0, 1500.0) for a in (0, 45, 90, 135)])
            b.add("roof_equipment", "Ống xả + quạt két nước", "Exhaust & radiator fans", "roof",
                  [Shape(stack, "steel_dark", 35.0), Shape(fans, "steel", 35.0)], parent_id=f"{cid}_body", required=True,
                  aliases=["ống xả", "ống khói", "quạt két nước", "mái", "exhaust"], function="Ống xả động cơ diesel và 2 quạt tản nhiệt két nước trên mái.",
                  position_tag="top", explode_dir=(0, 0, 1), explode_distance=1200.0, explode_order=1)
        elif not freight:
            b.add(f"{cid}_ac", f"Điều hòa trên mái toa {ci}", "Roof A/C unit", "roof",
                  Shape(K.rounded_box(2400.0, 1500.0, 350.0, 80.0, segments=16).translate(xc, 0, roof_top + 173.0), "plastic_white", 35.0),
                  parent_id=f"{cid}_body", aliases=["điều hòa", "máy lạnh", "mái toa"], function="Cụm điều hòa không khí trên mái.",
                  position_tag="top", explode_dir=(0, 0, 1), explode_distance=1000.0, explode_order=1)
        # móc nối: thân móc gá trên dầm đầu, đầu móc chạm đầu móc toa kế bên ở giữa khe hở
        for end, sx in (("front", 1), ("rear", -1)):
            outer_end = (ci == 0 and end == "front") or (ci == len(cars) - 1 and end == "rear")
            reach = 250.0 if outer_end else gap / 2
            xf = xc + sx * Lc / 2
            x_in, x_tip = xf - sx * 300.0, xf + sx * reach
            shank = K.box(abs(x_tip - x_in) - 280.0, 180.0, 160.0).translate((x_in + x_tip - sx * 280.0) / 2, 0, z_cp)
            head = K.rounded_box(300.0, 300.0, 280.0, 50.0, segments=16).translate(x_tip - sx * 150.0, 0, z_cp)
            knuckle = K.cylinder(90.0, 280.0, segments=24).translate(x_tip - sx * 110.0, -70.0 * sx, z_cp - 140.0)
            couplers.append((f"{cid}_coupler_{end}", shank + head + knuckle, f"{cid}_body", sx))
        if ci + 1 < len(cars):
            x_cur = xc - (Lc / 2 + gap + cars[ci + 1][1] / 2)
    for pid, solid, par, sx in couplers:
        b.add(pid, "Móc nối tự động", "Automatic coupler", "coupler", Shape(solid, "cast_iron", 60.0), parent_id=par, required=True,
              aliases=["móc nối", "đầu đấm móc", "móc nối tự động", "coupler", "khớp nối toa"],
              function="Móc nối tự động kiểu AAR (đường sắt Việt Nam) nối các toa.", position_tag="front" if sx > 0 else "rear",
              explode_dir=(sx, 0, 0), explode_distance=400.0, explode_order=1)
    contacts.append(["*_coupler_*", "*_coupler_*"])
    b.note_stage(1, "Tháo thiết bị mái, móc nối")
    b.note_stage(2, "Nhấc thân xe khỏi bogie")
    b.note_stage(3, "Nhấc khung bogie khỏi bộ trục bánh")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"gauge_mm": G, "traction": "electric" if electric else "diesel", "wagons": n_wag, "train_length_mm": total,
                       "rail_top_mm": rail_top, "wheel_d_loco_mm": 2 * 508.0 * k, "back_to_back_mm": bb,
                       "standard": "Khổ ray 1000/1435 mm, ray P43/UIC 60, móc nối tự động AAR, tỷ lệ đầu máy D19E",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
