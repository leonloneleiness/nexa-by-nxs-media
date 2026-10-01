"""Chuyển động thẳng: vít me bi cán SFU + gối đỡ BK/BF, ray dẫn hướng tuyến tính HIWIN HG / MGN + con trượt.

- Vít me bi: trục có rãnh bi xoắn (cung tròn 0,52·d_bi) theo bước (lead); đầu cố định gia công bậc (ngõng lắp ổ, ren
  khóa, đầu truyền động có then), đầu tự do có rãnh phanh; đai ốc SFU mặt bích (DIN 69051 kiểu B: 6 lỗ, một mặt
  vát phẳng), ống hồi bi ngoài + tấm kẹp, phớt gạt hai đầu, vú mỡ. Gối BK (cố định, kèm đai ốc khóa) và BF (tự do).
  Kích thước theo catalogue TBI Motion SFU và THK/HIWIN BK/BF (standards.BALL_SCREWS, SCREW_SUPPORTS).
- Ray dẫn hướng: ray có 4 rãnh bi, lỗ bậc lắp ốc cách đều bước P (cách đầu E), vít lục giác chìm; con trượt thép có
  nắp hồi bi nhựa, phớt chắn bụi, vú mỡ, 4 lỗ ren lắp (B × C). Kích thước catalogue HIWIN (standards.LINEAR_GUIDES).
Trục chuyển động theo X, đáy ở z = 0.
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

TO_X = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])     # Z → X


def rev_x(profile, segments: int = 64) -> K.Solid:
    return K.revolve(profile, segments=segments).transform(TO_X)


# ================================================================== vít me bi
def build_ball_screw(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    d = int(round(float(p.get("diameter_mm", 16))))
    lead = int(round(float(p.get("lead_mm", 5))))
    key = f"{d:02d}{lead:02d}"
    t = S.BALL_SCREWS[key]
    Lt = float(p.get("length_mm", 500.0))
    sup = S.SCREW_SUPPORTS[d]
    jd = float(sup["journal"])                                  # Ø ngõng lắp ổ
    dr = jd - 2.0                                               # Ø đầu truyền động
    mats = MC.tech_materials(spec)
    b = AssemblyBuilder(spec.name or f"Vít me bi SFU{key} dài {Lt:g} mm", "ball_screw", mats)
    zc = float(sup["center_h"])                                 # tâm trục cao hơn đáy gối
    # ---- trục: [đầu truyền động][ren khóa][ngõng BK][đoạn ren bi][ngõng BF] ----
    l_dr, l_th, l_bk = 15.0 + 0.5 * dr, 12.0, float(sup["l"]) + 2.0
    l_bf = float(sup["l"]) * 0.8 + 6.0
    x_thr0 = l_dr + l_th + l_bk
    thr_len = Lt - x_thr0 - l_bf
    rod = MC.ball_screw_rod(d, lead, t["ball"], thr_len, z0=0.0).transform(TO_X).translate(x_thr0, 0, 0)
    ends = rev_x([(0, 0), (dr / 2 - 0.5, 0), (dr / 2, 0.5), (dr / 2, l_dr), (jd / 2 - 0.2, l_dr), (jd / 2 - 0.2, l_dr + l_th),
                  (jd / 2, l_dr + l_th), (jd / 2, x_thr0 + 0.01), (0, x_thr0 + 0.01)], 48)
    rf = jd / 2 - (2.0 if jd > 10 else 1.0)                    # ngõng đầu tự do (ổ BF)
    tail = rev_x([(0, Lt - l_bf - 0.01), (rf, Lt - l_bf - 0.01), (rf, Lt - 0.5), (rf - 0.5, Lt), (0, Lt)], 48)
    groove = rev_x([(rf - 0.8, Lt - 3.5), (rf + 1, Lt - 3.5), (rf + 1, Lt - 2.4), (rf - 0.8, Lt - 2.4)], 48)
    tail = tail - groove
    kw = max(3.0, round(0.3 * dr))
    keyway = K.rounded_box(l_dr * 0.7, kw, kw * 0.6 + 1, kw * 0.49).translate(l_dr * 0.45, 0, dr / 2 - kw * 0.3 + 0.5)
    shaft = (rod + ends + tail) - keyway
    shaft = shaft.translate(0, 0, zc)
    b.add("screw_shaft", f"Trục vít me bi Ø{d} bước {lead}", "Ball screw shaft", "shaft", Shape(shaft, "steel", 35.0),
          parent_id="support_fixed", required=True, aliases=["trục vít", "vít me", "vít me bi", "trục vít me", "ball screw", "screw"],
          function=f"Trục vít me bi cán Ø{d} mm, bước {lead} mm (một vòng quay đai ốc tiến {lead} mm).", position_tag="center",
          joint_axis=(1, 0, 0), dimensions={"diameter": d, "lead": lead, "length": Lt})
    # ---- đai ốc SFU ----
    x_nut = x_thr0 + thr_len * 0.45
    nl, fl, ft = float(t["nut_l"]), float(t["flange_d"]), float(t["flange_t"])
    nut = rev_x([(d / 2 + 0.02, 0), (fl / 2, 0), (fl / 2, ft), (t["nut_d"] / 2, ft + 0.8), (t["nut_d"] / 2, nl - 0.8),
                 (t["nut_d"] / 2 - 0.8, nl), (d / 2 + 0.02, nl)], 96)
    flat = fl / 2 - (fl - t["nut_d"]) * 0.22
    nut = nut - K.box(ft + 2, fl, fl).translate(ft / 2, 0, -(flat + fl / 2))
    holes = [K.cylinder(t["hole_d"] / 2, ft + 2, segments=16).transform(TO_X).translate(-1, t["pcd"] / 2 * math.cos(a), t["pcd"] / 2 * math.sin(a))
             for a in np.radians(np.array([30, 90, 150, 210, 270, 330]))]
    nut = nut.subtract_all(holes)
    wip = []
    for x0 in (-2.0, nl):
        ring = rev_x([(d / 2 + 0.02, 0), (d / 2 + 0.3 * (t["nut_d"] - d) / 2 + 1.0, 0), (d / 2 + 0.3 * (t["nut_d"] - d) / 2 + 1.0, 2.0),
                      (d / 2 + 0.02, 2.0)], 64)
        wip.append(ring.translate(x0, 0, 0))
    # ống hồi bi ngoài: chữ U trên thân đai ốc + tấm kẹp 2 vít
    r_n = t["nut_d"] / 2
    tr = 0.35 * t["ball"] + 1.0
    span = nl - ft - 6.0
    xs0, xs1 = ft + 3.0, ft + 3.0 + span
    tube_pts = np.array([[xs0, 0, r_n - 1.0], [xs0, 0, r_n + tr + 1.5], [xs0 + span * 0.2, 0, r_n + tr * 2 + 1.5],
                         [xs1 - span * 0.2, 0, r_n + tr * 2 + 1.5], [xs1, 0, r_n + tr + 1.5], [xs1, 0, r_n - 1.0]])
    tube = K.tube(P.spline_through(tube_pts, 40), tr, 14)
    clamp = K.rounded_box(span * 0.45, 2.6 * tr + 6, 1.6, 0.6).translate((xs0 + xs1) / 2, 0, r_n + tr * 2 + 1.5 + tr - 0.3)
    clamp_scr = K.Solid.union_all([MC.socket_screw(3.0, 6.0).translate((xs0 + xs1) / 2, sy * (1.3 * tr + 1.8), r_n + tr * 2 + 1.5 + tr + 0.5)
                                   for sy in (1, -1)])
    feet = K.Solid.union_all([K.box(span * 0.45, 2.0, (r_n + tr * 2 + 1.5 + tr - 0.3 - 0.8) - (r_n - 1.0)).translate(
        (xs0 + xs1) / 2, sy * (1.3 * tr + 1.8), ((r_n + tr * 2 + 1.5 + tr - 1.1) + (r_n - 1.0)) / 2) for sy in (1, -1)])
    nipple = K.cylinder(1.8, 5.0, segments=12).transform(TO_X).translate(-5.0 + 0.01, 0, fl / 2 - 5.0) + K.sphere(1.6, 10).translate(-5.0, 0, fl / 2 - 5.0)
    nut_shapes = [Shape(nut, "steel_black_oxide", 35.0), Shape(K.Solid.union_all(wip), "plastic_black", 35.0),
                  Shape(tube + feet, "stainless", 35.0), Shape(clamp, "stainless", 35.0), Shape(clamp_scr, "steel_black_oxide", 35.0),
                  Shape(nipple, "brass", 35.0)]
    for sh in nut_shapes:
        sh.solid = sh.solid.translate(x_nut, 0, zc)
    b.add("ball_nut", f"Đai ốc bi SFU{key}", "Ball nut", "nut", nut_shapes, parent_id="screw_shaft", required=True,
          aliases=["đai ốc bi", "đai ốc", "con chạy", "ball nut", "nut", "ống hồi bi", "vú mỡ"],
          function=f"Đai ốc bi mặt bích Ø{fl:g} (6 lỗ Ø{t['hole_d']:g} trên Ø{t['pcd']:g}), ống hồi bi ngoài, phớt gạt.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=fl * 1.2 + 20, explode_order=2,
          dimensions={"flange_d": fl, "length": nl})
    contacts = [["ball_nut", "screw_shaft"], ["lock_nut", "support_fixed"], ["screw_shaft", "support_floating"]]
    # ---- gối đỡ BK (cố định) + BF (tự do) ----
    W, H, Lb = float(sup["w"]), float(sup["h"]), float(sup["l"])
    for tag, x0, lw, lbl, bearing_note in (("fixed", l_dr + l_th + 1.0, Lb, sup["bk"], "cặp ổ bi đỡ chặn tiếp xúc góc"),
                                           ("floating", Lt - l_bf + 3.0, Lb * 0.8, sup["bk"].replace("BK", "BF"), "ổ bi rãnh sâu")):
        base = K.chamfer_box(lw, W, 0.35 * zc, 0.8).translate(lw / 2, 0, 0.175 * zc)
        tower = K.hull([K.box(lw, W * 0.62, 0.01).translate(lw / 2, 0, 0.35 * zc),
                        K.cylinder(H - zc, lw, segments=64).transform(TO_X).translate(0, 0, zc)])
        blk = base + tower
        blk = blk - K.cylinder(jd / 2 if tag == "fixed" else rf, lw + 2, segments=48).transform(TO_X).translate(-1, 0, zc)
        mh = [K.cylinder(0.055 * W + 1.2, 0.35 * zc + 2, segments=16).translate(lw / 2, sy * W * 0.4, -1) for sy in (1, -1)]
        blk = blk.subtract_all(mh)
        shapes = [Shape(blk.translate(x0, 0, 0), "steel_black_oxide", 35.0)]
        if tag == "fixed":
            cover = rev_x([(jd / 2 + 0.5, 0), (H - zc - 2.0, 0), (H - zc - 2.0, 3.0), (jd / 2 + 0.5, 3.0)], 64).translate(x0 + lw, 0, zc)
            shapes.append(Shape(cover, "steel_black_oxide", 35.0))
            scr = K.Solid.union_all([MC.socket_screw(3.0, 6.0).transform(TO_X).translate(x0 + lw + 3.0, (H - zc - 5.0) * math.cos(a),
                                                                                           zc + (H - zc - 5.0) * math.sin(a))
                                     for a in np.radians([90, 210, 330])])
            shapes.append(Shape(scr, "steel_black_oxide", 35.0))
        b.add(f"support_{tag}", f"Gối đỡ {lbl} ({'cố định' if tag == 'fixed' else 'tự do'})", f"{lbl} support unit", "bearing",
              shapes, parent_id=None if tag == "fixed" else "screw_shaft", required=True,
              aliases=["gối đỡ", f"gối {lbl.lower()}", lbl.lower(), "support", "gối đỡ vít me", "ổ đỡ"],
              function=f"Gối đỡ {lbl}: {bearing_note} đỡ ngõng trục Ø{jd:g} mm.", position_tag="left" if tag == "fixed" else "right",
              explode_dir=(0, 0, -1) if tag == "fixed" else (1, 0, 0), explode_distance=0.0 if tag == "fixed" else 60.0,
              explode_order=3)
    lock = MC._hex_chamfered(jd * 1.6 + 4, 6.0, both=True) - K.cylinder(jd / 2 - 0.2, 20, segments=48).translate(0, 0, -5)
    lock = lock.transform(np.array([[0, 0, -1.0, 0], [1.0, 0, 0, 0], [0, -1.0, 0, 0]])).translate(l_dr + l_th + 1.0 - 0.01, 0, zc)
    b.add("lock_nut", "Đai ốc khóa", "Lock nut", "nut", Shape(lock, "steel_black_oxide", 35.0), parent_id="screw_shaft",
          aliases=["đai ốc khóa", "ê cu hãm", "lock nut"], function="Đai ốc khóa ép cặp ổ bi gối cố định.",
          position_tag="left", explode_dir=(-1, 0, 0), explode_distance=30.0, explode_order=1)
    b.note_stage(1, "Tháo đai ốc khóa")
    b.note_stage(2, "Rút đai ốc bi (giữ bi bằng ống lót)")
    b.note_stage(3, "Tháo gối tự do, rút trục khỏi gối cố định")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"model": f"SFU{key}", "diameter_mm": d, "lead_mm": lead, "length_mm": Lt, "ball_d_mm": t["ball"],
                       "nut_flange_mm": fl, "supports": [sup["bk"], sup["bk"].replace("BK", "BF")],
                       "standard": "TBI Motion SFU (DIN 69051 kiểu B), gối THK/HIWIN BK/BF", "strict_overlap": True,
                       "contacts": contacts})
    return b.build()


# ================================================================== ray dẫn hướng
def build_linear_guide(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    series = p.get("series", "HGR20")
    g = S.LINEAR_GUIDES[series]
    L = float(p.get("length_mm", 400.0))
    n = int(p.get("carriages", 2))
    mats = MC.tech_materials(spec)
    b = AssemblyBuilder(spec.name or f"Ray trượt {series} dài {L:g} mm", "linear_guide", mats)
    rail = MC.linear_rail(g, L)
    b.add("rail", f"Ray {series}", f"{series} rail", "rail", Shape(rail, "steel", 40.0), required=True,
          aliases=["ray", "thanh ray", "ray trượt", "rail", "ray dẫn hướng"],
          function=f"Ray thép tôi rộng {g['rail_w']:g} mm, 4 rãnh bi, lỗ lắp cách {g['pitch']:g} mm.", position_tag="bottom",
          dimensions={"width": g["rail_w"], "height": g["rail_h"], "length": L})
    xs = MC.hole_positions(g, L)
    d_s = float(g["m"])
    scr = K.Solid.union_all([MC.socket_screw(d_s, g["rail_h"] - g["cb_h"]).translate(x, 0, g["rail_h"] - g["cb_h"]) for x in xs])
    b.add("rail_screws", f"Vít lắp ray M{d_s:g}", "Rail bolts", "screw", Shape(scr, "steel_black_oxide", 40.0), parent_id="rail",
          aliases=["vít", "ốc lắp ray", "bu lông ray", "screw"], function=f"{len(xs)} vít M{d_s:g} (ISO 4762) lắp ray xuống bệ.",
          position_tag="bottom", explode_dir=(0, 0, 1), explode_distance=g["h"] * 2.2 + 20, explode_order=2)
    car = MC.carriage(g)
    Lc = car["length"]
    spacing = min(Lc * 1.6, (L - Lc - 2 * g["e"]) / max(1, n - 1)) if n > 1 else 0.0
    for k in range(n):
        xk = (k - (n - 1) / 2) * spacing
        b.add(f"carriage_{k + 1}", f"Con trượt {k + 1}", f"Carriage {k + 1}", "carriage",
              [Shape(car["body"].translate(xk, 0, 0), "steel", 40.0), Shape(car["caps"].translate(xk, 0, 0), "plastic_black", 40.0),
               Shape(car["seals"].translate(xk, 0, 0), "rubber", 40.0), Shape(car["nipple"].translate(xk, 0, 0), "brass", 40.0)],
              parent_id="rail", required=True,
              aliases=["con trượt", "block", "carriage", "xe trượt", "con chạy", f"con trượt {k + 1}"],
              function=f"Con trượt {series.replace('R', 'H', 1)}CA: rộng {g['car_w']:g} mm, cao lắp {g['h']:g} mm, lỗ ren "
                       f"{g['c']:g}×{g['b']:g} M{g['m']:g}; bi tuần hoàn qua nắp đầu.",
              position_tag="top", explode_dir=(1 if xk >= 0 else -1, 0, 0), explode_distance=L * 0.5 + Lc, explode_order=1,
              dimensions={"width": g["car_w"], "length": Lc, "height": g["h"]})
    b.note_stage(1, "Trượt con trượt ra khỏi đầu ray (lắp ray giả giữ bi)")
    b.note_stage(2, "Tháo vít lắp ray")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"series": series, "length_mm": L, "carriages": n, "hole_pitch_mm": g["pitch"], "rail_w_mm": g["rail_w"],
                       "standard": "HIWIN Linear Guideway (HG/MG)", "strict_overlap": True,
                       "contacts": [["carriage_*", "rail"]]})
    return b.build()


def build(spec: ModelSpec) -> BuiltAssembly:
    return build_ball_screw(spec) if spec.category == "ball_screw" else build_linear_guide(spec)
