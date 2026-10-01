"""Truyền động cơ khí: bộ truyền đai răng (GT2 / HTD 5M) hoặc đai thang (SPZ / SPA), bộ truyền xích con lăn
ISO 606 (dãy B), khớp nối trục (mềm kiểu vấu + đệm sao PU, hoặc cứng ống kẹp).

- Đai răng: puly răng theo bước đai (PD = z·p/π, OD = PD − 2·PLD), răng đai ăn đúng rãnh puly; chiều dài đai là số
  nguyên răng nên khoảng cách tâm được hiệu chỉnh (≤ nửa bước) như khi chọn đai chuẩn. Động cơ bước NEMA 17 (GT2) /
  NEMA 23 (HTD) dẫn động qua tấm đỡ chữ L, trục bị dẫn trên gối đỡ mặt bích.
- Đai thang: puly rãnh 38° (ISO 4183), đai hình thang tì hai sườn rãnh (ISO 4184).
- Xích: đĩa xích chỗ ngồi con lăn theo ISO 606, mắt trong/ngoài xen kẽ, nhánh căng thẳng, nhánh chùng võng tự nhiên,
  số mắt chẵn; khoảng cách tâm hiệu chỉnh theo số mắt nguyên.
- Khớp nối vấu: hai moay-ơ nhôm 3 vấu + đệm sao PU 6 cánh (kiểu ROTEX/Lovejoy), vít hãm; khớp cứng: ống nhôm xẻ
  rãnh + 2 vít kẹp tiếp tuyến.
Trục puly/đĩa xích theo Y, mặt phẳng truyền động XZ, đáy mô hình ở z = 0.
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

TO_XZ = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, 0]])   # dựng 2D XY (trục Z) → mặt XZ, trục Z → −Y
TO_X = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])     # Z → X
TO_Y = np.array([[1.0, 0, 0, 0], [0, 0, 1.0, 0], [0, -1.0, 0, 0]])    # Z → +Y
TO_NY = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, 0]])   # Z → −Y
PLATE_T = 6.0


def _xz(s: K.Solid) -> K.Solid:
    return s.transform(TO_XZ)


def _flanged_bearing(d: float) -> tuple[K.Solid, K.Solid, float, float]:
    """Gối đỡ ổ bi mặt bích vuông kiểu UCF/KFL: trục +Z, mặt tựa z = 0, bích + vòm ổ + vòng khóa lệch tâm.
    Trả (thân, 4 vít đầu trụ (thân vít đi xuống −Z qua tấm), cạnh bích, chiều cao tổng)."""
    a = 2.4 * d + 30
    h = 0.55 * d + 8
    tf = 0.35 * h
    body = K.chamfer_box(a, a, tf, 0.12 * a).translate(0, 0, tf / 2)
    dome = K.revolve(P.fillet_polygon([(0, 0), (0.4 * a, 0), (0.37 * a, h), (0, h)], [0, 0, 2, 0], 3), segments=64)
    body = body + dome
    collar = K.cylinder(0.85 * d + 3, 0.4 * h, segments=48).translate(0, 0, h - 0.01)
    body = (body + collar) - K.cylinder(d / 2, 4 * h, segments=48).translate(0, 0, -h)
    e = 0.36 * a
    pts = [(sx * e, sy * e) for sx in (1, -1) for sy in (1, -1)]
    sd = max(4.0, round(0.1 * a))
    body = body.subtract_all([K.cylinder(sd / 2 + 0.3, tf + 2, segments=16).translate(x, y, -1) for x, y in pts])
    screws = K.Solid.union_all([MC.socket_screw(sd, tf + PLATE_T).translate(x, y, tf) for x, y in pts])
    return body, screws, a, 1.4 * h


def _frame(xs: list[float], radii: list[float], y_front: float, depth: float) -> tuple[K.Solid, float]:
    """Tấm đỡ chữ L: tấm đứng (mặt trước y = y_front) + tấm đế nằm ngang + 2 gân. Trả (khối, z đáy tấm đứng)."""
    t = PLATE_T
    r_max = max(radii)
    x0 = min(x - r for x, r in zip(xs, radii)) - 25
    x1 = max(x + r for x, r in zip(xs, radii)) + 25
    z0, z1 = -r_max - 20, r_max + 12
    plate = K.rounded_box(x1 - x0, t, z1 - z0, 1.5).translate((x0 + x1) / 2, y_front - t / 2, (z0 + z1) / 2)
    base = K.rounded_box(x1 - x0, depth, t, 1.5).translate((x0 + x1) / 2, y_front - depth / 2, z0 - t / 2 + 0.01)
    gus = []
    for xg in (x0 + 10, x1 - 14):
        tri = K.extrude(np.array([[0, 0], [depth * 0.5, 0], [0, (z1 - z0) * 0.35]]), 4).rotate(90, 0, 0).rotate(0, 0, -90)
        gus.append(tri.translate(xg + 4, y_front - t + 0.01, z0))
    holes = [K.cylinder(3.3, 3 * t, segments=16).translate(xh, y_front - depth + 12, z0 - 2 * t) for xh in (x0 + 12, x1 - 12)]
    return K.Solid.union_all([plate, base] + gus).subtract_all(holes), z0


def _shaft_unit(b: AssemblyBuilder, tag: str, label: str, cx: float, bore: float, y_front: float, y_end: float,
                frame: K.Solid) -> K.Solid:
    """Gối đỡ mặt bích bắt sau tấm đứng + trục xuyên qua tấm tới y_end. Trả khối tấm đã khoét lỗ."""
    t = PLATE_T
    body, screws, a, h_tot = _flanged_bearing(bore)
    place = lambda s: s.transform(TO_NY).translate(cx, y_front - t, 0)  # noqa: E731
    frame = frame - K.cylinder(bore / 2 + 3, 3 * t, segments=48).transform(TO_Y).translate(cx, y_front - 2 * t, 0)
    frame = frame - K.Solid.union_all([K.cylinder(max(4.0, round(0.1 * a)) / 2 + 0.3, t + 0.02, segments=16).transform(TO_Y)
                                       .translate(cx + sx * 0.36 * a, y_front - t - 0.01, sz * 0.36 * a) for sx in (1, -1) for sz in (1, -1)])
    y0 = y_front - t - h_tot
    shaft = K.revolve([(0, 0), (bore / 2 - 0.4, 0), (bore / 2, 0.4), (bore / 2, y_end - y0 - 0.4), (bore / 2 - 0.4, y_end - y0),
                       (0, y_end - y0)], segments=32).transform(TO_Y).translate(cx, y0, 0)
    b.add(f"bearing_{tag}", f"Gối đỡ trục {label}", "Flanged bearing unit", "bearing",
          [Shape(place(body), "cast_iron", 35.0), Shape(place(screws), "steel_black_oxide", 35.0)], parent_id="frame",
          required=True, aliases=["gối đỡ", "ổ bi", "gối đỡ mặt bích", "bearing", "ucf"],
          function=f"Gối đỡ ổ bi mặt bích (UCF/KFL) cho trục Ø{bore:g} mm.", position_tag="rear",
          explode_dir=(0, -1, 0), explode_distance=h_tot + 40, explode_order=3)
    b.add(f"shaft_{tag}", f"Trục {label}", "Shaft", "shaft", Shape(shaft, "steel", 35.0), parent_id=f"bearing_{tag}",
          required=True, aliases=["trục", "shaft", f"trục {label}"], function=f"Trục Ø{bore:g} mm.", position_tag="center",
          joint_axis=(0, 1, 0))
    return frame


# ================================================================== bộ truyền đai
def build_belt(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    belt = p.get("belt", "GT2")
    mats = MC.tech_materials(spec)
    b = AssemblyBuilder(spec.name or f"Bộ truyền đai {belt}", "belt_drive", mats)
    contacts: list[list[str]] = [["belt", "pulley_*"], ["motor_screws", "motor"], ["motor", "frame"]]
    timing = belt in S.BELTS
    if timing:
        bt = S.BELTS[belt]
        pitch, pld = bt["pitch"], bt["pld"]
        z1, z2 = int(p.get("teeth_driver", 20)), int(p.get("teeth_driven", 40))
        r1, r2 = z1 * pitch / (2 * math.pi), z2 * pitch / (2 * math.pi)
        C0 = float(p.get("center_distance_mm") or 1.2 * (2 * r1 + 2 * r2))
        n_teeth = int(round(MC.belt_length(r1, r2, C0) / pitch))
        C = MC.solve_center(r1, r2, n_teeth * pitch, C0)
        width = float(p.get("width_mm") or bt["widths"][0])
    else:
        v = S.VBELTS[belt]
        r1, r2 = float(p.get("pulley_d_mm") or 100.0) / 2, float(p.get("pulley2_d_mm") or 200.0) / 2
        C0 = C = float(p.get("center_distance_mm") or 1.2 * (2 * r1 + 2 * r2))
        width = v["lp"]
    path, L, _beta = MC.open_belt_path(r1, r2, C, step=0.5 if timing else 1.5)
    # ---------- đai ----------
    if timing:
        back = bt["total_h"] - bt["tooth_h"]
        tooth = MC.belt_tooth_section(belt)
        pitch_eff = MC.path_length(path) / n_teeth
        teeth_cs, tooth_pts = [], []
        for k in range(n_teeth):
            pk, tk = MC.point_on_path(path, k * pitch_eff)
            nk = np.array([-tk[1], tk[0]])                          # hướng vào trong vòng đai (đường CCW)
            teeth_cs.append(MC.cs(pk + np.outer(pld + tooth[:, 1], nk) + np.outer(tooth[:, 0], tk)))
            tooth_pts.append(pk)
        section = (MC.cs(P.offset_polygon(path, -pld + back)) - MC.cs(P.offset_polygon(path, -pld))) + MC.cs_union(teeth_cs)
        belt_s = MC.extrude_cs(section, width, center=True)
        tooth_pts = np.asarray(tooth_pts)
    else:
        h = v["height"]
        top = v["lp"] + 2 * 0.28 * h * math.tan(math.radians(19))  # rộng đúng lp tại đường chuẩn → tì hai sườn rãnh
        bot = top - 2 * h * math.tan(math.radians(19))
        prof = [(-top / 2, 0.28 * h), (top / 2, 0.28 * h), (bot / 2, 0.28 * h - h), (-bot / 2, 0.28 * h - h)]
        secs = []
        for i in range(len(path)):
            tk = path[(i + 1) % len(path)] - path[i - 1]
            tk = tk / np.linalg.norm(tk)
            nk = np.array([tk[1], -tk[0]])                          # ra ngoài vòng
            secs.append(np.array([[path[i][0] + nk[0] * vv, path[i][1] + nk[1] * vv, uu] for uu, vv in prof]))
        mesh = K.loft_mesh(secs, closed=True)
        belt_s = K.from_mesh(mesh.vertices, mesh.faces)
    b.add("belt", f"Dây đai {belt}", f"{belt} belt", "belt", Shape(_xz(belt_s), "rubber", 20.0), parent_id="pulley_driven",
          required=True, aliases=["dây đai", "đai", "curoa", "dây curoa", "belt", "đai răng" if timing else "đai thang"],
          function=(f"Đai răng {belt} bước {pitch:g} mm, {n_teeth} răng (dài {n_teeth * pitch:g} mm), rộng {width:g} mm." if timing
                    else f"Đai thang hẹp {belt} (ISO 4184), dài chuẩn {L:.0f} mm."),
          position_tag="center", explode_dir=(0, 1, 0), explode_distance=4 * width + 40, explode_order=1,
          dimensions={"length": round(L, 1)})
    # ---------- puly ----------
    if timing:
        motor_size = 17 if belt == "GT2" else 23
        bores = (S.NEMA[motor_size]["shaft_d"], 8.0 if belt == "GT2" else 12.0)
        hub_len = max(6.0, 0.45 * width + 3)
        ft = max(0.8, 0.12 * (width + 1.0))
        pulleys = []
        for idx, (zt, rr, cx, ang_ref) in enumerate(((z1, r1, 0.0, math.pi), (z2, r2, C, 0.0))):
            ang = np.arctan2(tooth_pts[:, 1], tooth_pts[:, 0] - cx)
            dist = np.hypot(tooth_pts[:, 0] - cx, tooth_pts[:, 1])
            cand = np.where(np.abs(dist - rr) < 0.02 * rr + 0.05)[0]
            k = cand[np.argmin(np.abs((ang[cand] - ang_ref + math.pi) % (2 * math.pi) - math.pi))]
            ps = MC.timing_pulley(zt, belt, width + 1.0, bores[idx], hub_len=hub_len)
            pulleys.append(ps.rotate(0, 0, math.degrees(ang[k])).translate(cx, 0, 0))
        y_front = -((width + 1.0) / 2 + ft + hub_len + 3.0)
        y_end = (width + 1.0) / 2 + ft
    else:
        bores = (19.0 if r1 < 60 else 24.0, 24.0 if r2 < 110 else 32.0)
        pulleys, w_p = [], 0.0
        for rr, cx, bore in ((r1, 0.0, bores[0]), (r2, C, bores[1])):
            ps, w_p = MC.vbelt_pulley(2 * rr, belt, 1, bore)
            pulleys.append(ps.translate(cx, 0, 0))
        y_front = -(w_p / 2 + 8.0)
        y_end = w_p / 2
    for idx, ps in enumerate(pulleys):
        tag = "driver" if idx == 0 else "driven"
        nm = "dẫn" if idx == 0 else "bị dẫn"
        desc = (f"Puly răng {belt} {(z1, z2)[idx]} răng, PD {2 * (r1, r2)[idx]:.2f} mm, lỗ Ø{bores[idx]:g}." if timing else
                f"Puly rãnh {belt} đường kính chuẩn {2 * (r1, r2)[idx]:g} mm, lỗ Ø{bores[idx]:g}.")
        b.add(f"pulley_{tag}", f"Puly {nm}", f"{tag.capitalize()} pulley", "pulley", Shape(_xz(ps), "aluminum", 30.0),
              parent_id=f"shaft_{tag}", required=True, aliases=["puly", "pu li", "bánh đai", "pulley", f"puly {nm}"],
              function=desc, position_tag="left" if idx == 0 else "right", joint_axis=(0, 1, 0),
              explode_dir=(0, 1, 0), explode_distance=2.5 * width + 25, explode_order=2)
    # ---------- tấm đỡ, động cơ, gối đỡ, trục ----------
    t = PLATE_T
    if timing:
        L_m = S.NEMA[motor_size]["lengths"][1]
        frame, _z0 = _frame([0.0, C], [max(r1 + 10, S.NEMA[motor_size]["flange"] / 2), r2 + 10], y_front, L_m + 45)
        nema = MC.nema_stepper(motor_size, L_m)
        face_y = y_front - t
        mt = lambda s: s.transform(TO_Y).translate(0, face_y, 0)    # noqa: E731
        cores = mt(nema["shaft_core"] + nema["screw_cores"])
        motor_shapes = [Shape(mt(nema["front"]) - cores, "cast_aluminum", 30.0), Shape(mt(nema["stack"]) - cores, "steel_dark", 30.0),
                        Shape(mt(nema["rear"]) - cores, "cast_aluminum", 30.0), Shape(mt(nema["screws"]), "steel_black_oxide", 30.0)]
        frame = frame - K.cylinder(S.NEMA[motor_size]["pilot_d"] / 2 + 0.2, 3 * t, segments=64).transform(TO_Y).translate(0, y_front - 2 * t, 0)
        hs = S.NEMA[motor_size]["hole_spacing"] / 2
        sd = 3.0 if motor_size == 17 else 5.0
        m_scr = K.Solid.union_all([MC.socket_screw(sd, t + 4.0).transform(TO_Y).translate(sx * hs, y_front, sz * hs)
                                   for sx in (1, -1) for sz in (1, -1)])
        frame = frame - K.Solid.union_all([K.cylinder(sd / 2 + 0.3, t + 0.02, segments=16).transform(TO_Y).translate(sx * hs, y_front - t - 0.01, sz * hs)
                                           for sx in (1, -1) for sz in (1, -1)])
        frame = _shaft_unit(b, "driven", "bị dẫn", C, bores[1], y_front, y_end, frame)
        b.add("frame", "Tấm đỡ chữ L", "L mounting plate", "frame", Shape(frame, "aluminum", 40.0), required=True,
              aliases=["tấm đỡ", "giá đỡ", "tấm gá", "frame", "bracket"], function="Tấm nhôm 6 mm bắt động cơ và gối đỡ.",
              position_tag="rear")
        b.add("motor", f"Động cơ bước NEMA {motor_size}", f"NEMA {motor_size} stepper", "motor", motor_shapes, parent_id="frame",
              required=True, aliases=["động cơ", "motor", "động cơ bước", "step"], function="Động cơ dẫn động puly dẫn.",
              position_tag="rear", explode_dir=(0, -1, 0), explode_distance=L_m + 30, explode_order=3)
        b.add("motor_screws", "Vít bắt động cơ", "Motor screws", "screw", Shape(m_scr, "steel_black_oxide", 35.0), parent_id="frame",
              aliases=["vít", "vít động cơ"], function=f"4 vít M{sd:g} bắt động cơ vào tấm.", position_tag="rear",
              explode_dir=(0, 1, 0), explode_distance=5 * width + 50, explode_order=2)
        b.add("shaft_driver", "Trục động cơ", "Motor shaft", "shaft", Shape(mt(nema["shaft"]), "stainless", 35.0), parent_id="motor",
              required=True, aliases=["trục", "trục động cơ", "trục dẫn", "shaft"],
              function=f"Trục Ø{bores[0]:g} mm có mặt vát D của động cơ.", position_tag="left", joint_axis=(0, 1, 0))
    else:
        frame, _z0 = _frame([0.0, C], [r1 + 12, r2 + 12], y_front, 150.0)
        frame = _shaft_unit(b, "driver", "dẫn", 0.0, bores[0], y_front, y_end, frame)
        frame = _shaft_unit(b, "driven", "bị dẫn", C, bores[1], y_front, y_end, frame)
        b.add("frame", "Tấm đỡ chữ L", "L mounting plate", "frame", Shape(frame, "steel_dark", 40.0), required=True,
              aliases=["tấm đỡ", "giá đỡ", "khung", "frame"], function="Tấm thép đỡ hai gối trục.", position_tag="rear")
    b.note_stage(1, "Nới căng, tháo dây đai")
    b.note_stage(2, "Tháo puly (và vít động cơ)")
    b.note_stage(3, "Tháo động cơ / gối đỡ khỏi tấm")
    b.place_on_ground(center_xy=True)
    meta = {"belt": belt, "center_distance_mm": C, "center_requested_mm": C0, "belt_length_mm": L, "strict_overlap": True,
            "contacts": contacts}
    if timing:
        meta.update({"teeth_driver": z1, "teeth_driven": z2, "belt_teeth": n_teeth, "ratio": z2 / z1, "pitch_mm": pitch,
                     "standard": "Gates PowerGrip GT2 / HTD (bước, PLD, chiều cao răng)"})
    else:
        meta.update({"pitch_d1_mm": 2 * r1, "pitch_d2_mm": 2 * r2, "ratio": r2 / r1, "standard": "ISO 4183/4184 (đai thang hẹp)"})
    b.metadata.update(meta)
    return b.build()


# ================================================================== bộ truyền xích
def build_chain(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    ch = p.get("chain", "08B")
    c = S.CHAINS[ch]
    pitch = c["pitch"]
    z1, z2 = int(p.get("teeth_driver", 17)), int(p.get("teeth_driven", 34))
    mats = MC.tech_materials(spec)
    b = AssemblyBuilder(spec.name or f"Bộ truyền xích {ch}", "chain_drive", mats)
    R1g, R2g = pitch / (2 * math.sin(math.pi / z1)), pitch / (2 * math.sin(math.pi / z2))
    bore1 = float(min(max(12.0, round(0.35 * R1g)), 2 * (R1g - 0.9 * c["roller"] - 0.6 * pitch) - 6))
    bore2 = float(min(max(16.0, round(0.3 * R2g)), 50.0))
    s1, R1 = MC.sprocket(z1, ch, bore1)
    s2, R2 = MC.sprocket(z2, ch, bore2)
    C0 = float(p.get("center_distance_mm") or 35 * pitch)
    C = MC.chain_center(R1, R2, C0, pitch)
    rollers = MC.chain_rollers(R1, R2, C, pitch)
    plates, rolls = MC.roller_chain(rollers, ch)
    a_top = math.degrees(math.pi / 2 + math.asin((R2 - R1) / C))
    s1 = s1.mirror((0, 0, 1)).rotate(0, 0, a_top)                    # moay-ơ quay về phía tấm đỡ
    s2 = s2.mirror((0, 0, 1)).rotate(0, 0, a_top).translate(C, 0, 0)
    free = [q for q in rollers if abs(math.hypot(q[0], q[1]) - R1) > 1e-3 and abs(math.hypot(q[0] - C, q[1]) - R2) > 1e-3]
    clear = K.Solid.union_all([K.cylinder(c["roller"] / 2 + 0.25, 3 * c["inner_w"], segments=24).translate(q[0], q[1], -1.5 * c["inner_w"])
                               for q in free])
    s1, s2 = s1 - clear, s2 - clear                                  # khe hở răng cho con lăn nhánh vào/ra đĩa
    bf = 0.93 * c["inner_w"] if pitch <= 12.7 else 0.95 * c["inner_w"]
    hub_l = max(max(pitch * 1.2, bore1 * 0.9), max(pitch * 1.2, bore2 * 0.9))
    b.add("chain", f"Xích con lăn {ch}", f"Roller chain {ch}", "chain",
          [Shape(_xz(plates), "steel_dark", 30.0), Shape(_xz(rolls), "steel", 30.0)], parent_id="sprocket_driven", required=True,
          aliases=["xích", "sên", "dây xích", "chain", "mắt xích"],
          function=f"Xích con lăn ISO 606 {ch} bước {pitch:g} mm, {len(rollers)} mắt (số chẵn, không cần mắt nối cong).",
          position_tag="center", explode_dir=(0, 1, 0), explode_distance=60 + 4 * c["inner_w"], explode_order=1,
          dimensions={"links": len(rollers), "pitch": pitch})
    for idx, (sol, zt, Rp, tag, nm) in enumerate(((s1, z1, R1, "driver", "dẫn"), (s2, z2, R2, "driven", "bị dẫn"))):
        b.add(f"sprocket_{tag}", f"Đĩa xích {nm} z = {zt}", f"{tag.capitalize()} sprocket", "sprocket", Shape(_xz(sol), "steel", 30.0),
              parent_id=f"shaft_{tag}", required=True,
              aliases=["đĩa xích", "nhông", "líp", "sprocket", f"đĩa xích {nm}", "nhông trước" if idx == 0 else "nhông sau"],
              function=f"Đĩa xích {zt} răng, đường kính chia {2 * Rp:.2f} mm (ISO 606).", position_tag="left" if idx == 0 else "right",
              joint_axis=(0, 1, 0), explode_dir=(0, 1, 0), explode_distance=40 + 3 * c["inner_w"], explode_order=2)
    y_front = -(bf / 2 + hub_l + 4.0)
    frame, _z0 = _frame([0.0, C], [R1 + pitch, R2 + pitch], y_front, 150.0)
    frame = _shaft_unit(b, "driver", "dẫn", 0.0, bore1, y_front, bf / 2, frame)
    frame = _shaft_unit(b, "driven", "bị dẫn", C, bore2, y_front, bf / 2, frame)
    b.add("frame", "Tấm đỡ chữ L", "L mounting plate", "frame", Shape(frame, "steel_dark", 40.0), required=True,
          aliases=["tấm đỡ", "giá đỡ", "khung", "frame"], function="Tấm thép đỡ hai gối trục.", position_tag="rear")
    b.note_stage(1, "Tháo mắt nối, gỡ xích")
    b.note_stage(2, "Tháo đĩa xích khỏi trục")
    b.note_stage(3, "Tháo gối đỡ")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"chain": ch, "teeth_driver": z1, "teeth_driven": z2, "links": len(rollers), "center_distance_mm": C,
                       "center_requested_mm": C0, "ratio": z2 / z1, "pitch_mm": pitch, "standard": "ISO 606 dãy B",
                       "strict_overlap": True, "contacts": [["chain", "sprocket_*"]]})
    return b.build()


# ================================================================== khớp nối trục
def _sector(r0: float, r1: float, a0: float, a1: float, n: int = 20) -> np.ndarray:
    outer = [(r1 * math.cos(a), r1 * math.sin(a)) for a in np.linspace(a0, a1, n)]
    inner = [(r0 * math.cos(a), r0 * math.sin(a)) for a in np.linspace(a1, a0, n)]
    return np.array(outer + inner)


def build_coupling(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("coupling_type", "jaw")
    d1 = float(p.get("bore_mm", 14.0))
    d2 = float(p.get("bore2_mm") or d1)
    mats = MC.tech_materials(spec)
    b = AssemblyBuilder(spec.name or ("Khớp nối mềm vấu" if kind == "jaw" else "Khớp nối cứng") + f" Ø{d1:g}/{d2:g}",
                        "shaft_coupling", mats)
    contacts: list[list[str]] = [["shaft_*", "set_screws"]]
    if kind == "jaw":
        size = next(k for k in sorted(S.JAW_COUPLINGS) if S.JAW_COUPLINGS[k][2] >= max(d1, d2))
        OD, L, _mb = S.JAW_COUPLINGS[size]
        R = OD / 2
        jl = 0.3 * L
        hub_l = (L - jl) / 2
        r_in = max(d1, d2) / 2 + 0.12 * OD
        half = math.radians(22.5)
        hubs = []
        for bore, a_off in ((d1, 0.0), (d2, 60.0)):
            body = K.revolve(P.fillet_polygon([(0, 0), (R, 0), (R, hub_l), (0, hub_l)], [0, 1.0, 0.0, 0], 3), segments=128)
            jaws = [K.extrude(_sector(r_in, R, math.radians(a_off + 120 * k) - half, math.radians(a_off + 120 * k) + half), jl - 0.5 + 0.01)
                    .translate(0, 0, hub_l - 0.01) for k in range(3)]
            hub = K.Solid.union_all([body] + jaws)
            hub = hub & K.revolve([(0, 0), (R, 0), (R, hub_l + jl - 1.3), (R - 0.8, hub_l + jl - 0.5), (0, hub_l + jl - 0.5)], segments=128)
            hubs.append(hub - K.cylinder(bore / 2, 3 * L, segments=48).translate(0, 0, -L))
        h1 = hubs[0].transform(TO_X).translate(-L / 2, 0, 0)
        h2 = hubs[1].mirror((0, 0, 1)).transform(TO_X).translate(L / 2, 0, 0)
        legs = [K.extrude(_sector(r_in, R - 0.6, math.radians(30 + 60 * k - 7.5), math.radians(30 + 60 * k + 7.5)), jl) for k in range(6)]
        ring = K.cylinder(r_in, jl, segments=128) - K.cylinder(r_in - 0.08 * OD, jl + 2, segments=128).translate(0, 0, -1)
        spider = K.Solid.union_all(legs + [ring]).transform(TO_X).translate(-jl / 2, 0, 0)
        sd = 4.0 if OD <= 40 else 5.0 if OD <= 65 else 6.0 if OD <= 80 else 8.0
        screws, cores = [], []
        for sx, bore in ((-1, d1), (1, d2)):
            xc = sx * (L / 2 - hub_l / 2)
            scr = K.cylinder(sd / 2, R - bore / 2 - 0.3, segments=16).translate(0, 0, bore / 2)
            scr = scr - K.extrude(P.circle(sd * 0.28, 6), 2.0).translate(0, 0, R - 2.29)
            screws.append(scr.translate(xc, 0, 0))
            cores.append(K.cylinder(sd / 2, R - bore / 2 + 1, segments=16).translate(xc, 0, bore / 2))
        core = K.Solid.union_all(cores)
        h1, h2 = h1 - core, h2 - core
        b.add("hub_1", "Moay-ơ 1", "Hub 1", "coupling_hub", Shape(h1, "aluminum", 40.0), required=True,
              aliases=["moay ơ", "nửa khớp", "vấu", "hub", "moay-ơ 1"], function=f"Moay-ơ nhôm 3 vấu, lỗ Ø{d1:g} mm (kiểu ROTEX cỡ {size}).",
              position_tag="left", dimensions={"od": OD, "bore": d1})
        b.add("spider", "Đệm sao PU", "PU spider", "spider", Shape(spider, "polyurethane", 40.0), parent_id="hub_1", required=True,
              aliases=["đệm sao", "cao su khớp nối", "spider", "đệm đàn hồi", "hình sao"],
              function="Đệm sao polyurethane 92 Shore A: giảm chấn, bù lệch trục nhỏ.", position_tag="center",
              explode_dir=(0, 0, 1), explode_distance=OD * 1.1, explode_order=2)
        b.add("hub_2", "Moay-ơ 2", "Hub 2", "coupling_hub", Shape(h2, "aluminum", 40.0), parent_id="hub_1", required=True,
              aliases=["moay ơ", "nửa khớp", "vấu", "hub", "moay-ơ 2"], function=f"Moay-ơ nhôm 3 vấu, lỗ Ø{d2:g} mm.",
              position_tag="right", explode_dir=(1, 0, 0), explode_distance=L * 0.9, explode_order=1, dimensions={"od": OD, "bore": d2})
        b.add("set_screws", "Vít hãm", "Set screws", "screw", Shape(K.Solid.union_all(screws), "steel_black_oxide", 40.0),
              parent_id="hub_1", aliases=["vít hãm", "vít trí", "set screw"], function=f"Vít hãm M{sd:g} kẹp moay-ơ lên trục.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=OD * 0.7, explode_order=1)
        contacts += [["spider", "hub_2"], ["set_screws", "hub_2"]]
        ends = (0.2 * L + 1.0, 0.2 * L + 1.0)
    else:
        OD = max(d1, d2) * 1.8 + 12
        L = max(d1, d2) * 2.4 + 16
        R = OD / 2
        body = K.revolve(P.fillet_polygon([(0, -L / 2), (R, -L / 2), (R, L / 2), (0, L / 2)], [0, 0.8, 0.8, 0], 3), segments=128)
        body = body - K.cylinder(d1 / 2, L / 2 + 1, segments=48).translate(0, 0, -L / 2 - 1) - K.cylinder(d2 / 2, L / 2 + 1, segments=48)
        zc_s = (-L / 4 - 0.02 * L, L / 4 + 0.02 * L)
        for zc, dd in zip(zc_s, (d1, d2)):
            body = body - K.box(1.0, R - dd / 2 + 2, 0.42 * L).translate(0, (R + dd / 2) / 2, zc)
        body = body - (K.cylinder(R + 1, 1.0, segments=128) - K.cylinder(max(d1, d2) / 2 + 2.5, 3, segments=128).translate(0, 0, -1)).translate(0, 0, -0.5)
        sd = 3.0 if OD < 30 else 4.0 if OD < 45 else 5.0 if OD < 60 else 6.0
        screws, cores = [], []
        for zc, dd in zip(zc_s, (d1, d2)):
            yc = max(0.58 * R, dd / 2 + sd / 2 + 1.2)
            screws.append(MC.socket_screw(sd, 1.2 * R).rotate(0, 90, 0).translate(0.55 * R, yc, zc))
            cores.append(K.cylinder(sd / 2, 1.2 * R + 0.02, segments=16).rotate(0, 90, 0).translate(0.55 * R - 1.2 * R - 0.01, yc, zc))
            cores.append(K.cylinder(0.75 * sd + 0.6, R, segments=20).rotate(0, 90, 0).translate(0.55 * R, yc, zc))
        body = body.subtract_all(cores)
        b.add("hub_1", "Ống kẹp khớp nối cứng", "Rigid clamp coupling", "coupling_hub", Shape(body.transform(TO_X), "aluminum", 40.0),
              required=True, aliases=["khớp nối cứng", "ống nối", "ống kẹp", "coupling", "hub"],
              function=f"Khớp nối cứng một khối xẻ rãnh, kẹp trục Ø{d1:g} / Ø{d2:g} mm.", position_tag="center",
              dimensions={"od": OD, "bore": d1})
        b.add("set_screws", "Vít kẹp", "Clamp screws", "screw", Shape(K.Solid.union_all(screws).transform(TO_X), "steel_black_oxide", 40.0),
              parent_id="hub_1", aliases=["vít kẹp", "vít", "clamp screw"], function=f"2 vít M{sd:g} kẹp ống lên trục.",
              position_tag="top", explode_dir=(0, 1, 0), explode_distance=OD * 0.9, explode_order=1)
        contacts = [["shaft_*", "hub_1"]]
        ends = (1.0, 1.0)
    for idx, (bore, sx) in enumerate(((d1, -1), (d2, 1))):
        ls = max(3.0 * bore, 40.0)
        x_in, x_out = sx * ends[idx], sx * (L / 2 + ls)
        x0, x1 = min(x_in, x_out), max(x_in, x_out)
        sh = K.revolve([(0, 0), (bore / 2 - 0.4, 0), (bore / 2, 0.4), (bore / 2, x1 - x0 - 0.4), (bore / 2 - 0.4, x1 - x0), (0, x1 - x0)],
                       segments=48).transform(TO_X).translate(x0, 0, 0)
        b.add(f"shaft_{idx + 1}", f"Trục {'động cơ' if idx == 0 else 'tải'}", f"Shaft {idx + 1}", "shaft", Shape(sh, "steel", 35.0),
              parent_id="hub_1" if (idx == 0 or kind != "jaw") else "hub_2", required=True,
              aliases=["trục", "shaft", "trục động cơ" if idx == 0 else "trục tải"], function=f"Đầu trục Ø{bore:g} mm.",
              position_tag="left" if idx == 0 else "right", joint_axis=(1, 0, 0),
              explode_dir=(-1 if idx == 0 else 1, 0, 0), explode_distance=ls + 20, explode_order=3)
    b.note_stage(1, "Nới vít, tách moay-ơ")
    b.note_stage(2, "Lấy đệm sao")
    b.note_stage(3, "Rút trục")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"coupling_type": kind, "bore1_mm": d1, "bore2_mm": d2, "od_mm": OD, "length_total_mm": L,
                       "standard": "KTR ROTEX (khớp vấu)" if kind == "jaw" else "khớp nối cứng ống kẹp (kiểu Ruland)",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()


def build(spec: ModelSpec) -> BuiltAssembly:
    return {"belt_drive": build_belt, "chain_drive": build_chain, "shaft_coupling": build_coupling}[spec.category](spec)
