"""Tên lửa đẩy nhiều tầng (2–3 tầng), tỷ lệ theo Falcon 9 (cao 70 m, Ø3,7 m, 9 động cơ tầng 1, 1 động cơ chân không
tầng 2, chóp bảo vệ tải Ø5,2 m… được thu về cùng đường kính thân cho gọn).

Mỗi tầng: vỏ bồn nhôm–liti có vòng gân, bồn ôxy lỏng + bồn nhiên liệu tách bằng vách chung (dải sơn), ống cáp chạy dọc
(raceway), khoang động cơ + tấm chắn nhiệt; tầng 1: cụm 9 động cơ (8 vòng ngoài + 1 giữa) với vòi phun chuông, 4 cánh
ổn định ở đuôi (tùy chọn); vòng nối tầng rỗng bao lấy vòi phun tầng trên; tầng trên cùng: động cơ chân không vòi phun
lớn, bộ gá tải, vệ tinh tải trọng trong chóp mũi hai nửa (dạng ogive). Đứng thẳng trên bệ, đáy vòi phun ở z = 0.

Tách theo đúng trình tự bay: (1) tách tầng 1 (+ vòng nối tầng) khỏi phần trên, (2) tách tầng 2 (nếu 3 tầng),
(3) bung hai nửa chóp mũi sang hai bên, (4) nhả vệ tinh khỏi bộ gá.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def engine(throat_r: float, exit_r: float, length: float, vacuum: bool = False) -> tuple[K.Solid, K.Solid]:
    """Động cơ tên lửa (trục Z, mặt gá ở z = length, miệng vòi phun ở z = 0): (buồng đốt + tua-bin, vòi phun chuông)."""
    Lb = length * (0.7 if vacuum else 0.55)                         # chiều dài chuông
    prof = [(exit_r, 0.0)]
    for t in np.linspace(0, 1, 16)[1:]:
        z = Lb * t
        r = throat_r + (exit_r - throat_r) * (1 - t) ** 1.9          # đường cong chuông (xấp xỉ Rao)
        prof.append((r, z))
    prof += [(throat_r * 0.9, Lb + 0.02 * length), (throat_r * 0.9 - 0.02 * exit_r, Lb + 0.02 * length)]
    outer = K.revolve(prof + [(r * 0.97 - 0.004 * exit_r, z) for r, z in reversed(prof[1:-1])] + [(exit_r * 0.97, 0.0)], segments=64)
    chamber = K.revolve(P.fillet_polygon([(0, Lb), (throat_r * 1.6, Lb + 0.05 * length), (throat_r * 1.7, length * 0.9), (throat_r * 1.2, length),
                                          (0, length)], [0, throat_r * 0.4, throat_r * 0.3, throat_r * 0.2, 0], 3), segments=48)
    pump = K.rounded_box(throat_r * 1.4, throat_r * 1.4, 0.2 * length, throat_r * 0.3).translate(throat_r * 2.2, 0, length * 0.78)
    feed = K.tube(np.array([[throat_r * 1.6, 0, length * 0.72], [throat_r * 2.2, 0, length * 0.7], [throat_r * 2.2, 0, length * 0.88]]),
                  throat_r * 0.18, 10)
    exhaust = K.tube(np.array([[throat_r * 2.4, 0, length * 0.7], [throat_r * 2.8, 0, length * 0.4], [throat_r * 2.9, 0, length * 0.2]]),
                     throat_r * 0.14, 10)
    return chamber + pump + feed + exhaust, outer


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    n_st = int(p.get("stages", 2))
    Ht = float(p.get("height_mm", 70000.0))
    Dm = float(p.get("diameter_mm", 3700.0))
    R = Dm / 2
    mats = MC.tech_materials(spec, primary="#eef0f2", secondary="#1d1f24", accent="#c1121f")
    mats["niobium"] = M.material("niobium", "metal", "#2a2b30", 0.9, 0.35, name="Hợp kim niobi (vòi phun chân không)")
    b = AssemblyBuilder(spec.name or f"Tên lửa {n_st} tầng", "launch_vehicle", mats)
    # phân bổ chiều cao (Falcon 9: tầng 1 ≈ 0,6; nối tầng 0,09; tầng 2 ≈ 0,19; chóp 0,19 tổng)
    fr = {2: [0.575, 0.085, 0.18, 0.16], 3: [0.47, 0.07, 0.17, 0.06, 0.1, 0.13]}[n_st]
    eng_L1 = 0.045 * Ht
    f1n = fr[0] / sum(fr)
    z = (eng_L1 + 0.02 * f1n * Ht) / (1 + 0.02 * f1n)              # đáy thân tầng 1: miệng vòi phun chạm z = 0
    lengths = [f / sum(fr) * (Ht - z) for f in fr]                  # tổng = chiều cao yêu cầu
    # ---------- tầng 1 ----------
    L1 = lengths[0]
    z1_0, z1_1 = z, z + L1

    def tank(z0: float, L: float, stripes: list[float]) -> K.Solid:
        body = K.cylinder(R, L, segments=128).translate(0, 0, z0)
        rings = K.Solid.union_all([K.torus(R, 0.004 * Dm, segments=128, tube_segments=8).translate(0, 0, z0 + L * t) for t in np.linspace(0.05, 0.95, 9)])
        return body + rings
    t1 = tank(z1_0, L1, [])
    band1 = (K.cylinder(R + 0.002 * Dm, 0.02 * L1, segments=128) - K.cylinder(R - 0.01 * Dm, 0.02 * L1 + 2, segments=128).translate(0, 0, -1)).translate(0, 0, z1_0 + 0.38 * L1)
    race = K.rounded_box(0.06 * Dm, 0.05 * Dm, 0.92 * L1, 0.02 * Dm).translate(R + 0.01 * Dm, 0, z1_0 + L1 / 2)
    skirt = K.revolve([(R * 0.98, z1_0 - 0.02 * L1), (R, z1_0 - 0.02 * L1), (R, z1_0 + 0.001), (R * 0.98, z1_0 + 0.001)], segments=128)
    heat = K.cylinder(R * 0.98, 0.01 * L1, segments=128).translate(0, 0, z1_0 - 0.02 * L1)
    shapes1 = [Shape(t1 + skirt, "paint_primary", 60.0), Shape(band1, "paint_secondary", 60.0), Shape(race, "paint_primary", 60.0),
               Shape(heat, "steel_dark", 60.0)]
    logo = K.box(0.004 * Dm, 0.35 * Dm, 0.08 * L1).translate(-R - 0.001 * Dm, 0, z1_0 + 0.7 * L1) & K.cylinder(R + 0.004 * Dm, Ht, segments=128)
    shapes1.append(Shape(logo - K.cylinder(R - 0.001, Ht, segments=128), "paint_accent", 60.0))
    b.add("stage_1", "Tầng 1 (tầng đẩy)", "First stage", "stage", shapes1, required=True,
          aliases=["tầng 1", "tầng đẩy", "first stage", "booster", "bồn nhiên liệu tầng 1", "bồn ôxy lỏng"],
          function="Tầng 1: bồn ôxy lỏng (trên) + bồn dầu RP-1 (dưới) tách bằng vách chung; ống cáp dọc thân.",
          position_tag="bottom", dimensions={"length": L1, "diameter": Dm})
    # cụm 9 động cơ: 8 vòng ngoài + 1 giữa (octaweb)
    thr, ex_r = 0.045 * Dm, 0.12 * Dm
    ch, bell = engine(thr, ex_r, eng_L1)
    pos = [(0.0, 0.0)] + [(0.33 * Dm * math.cos(a), 0.33 * Dm * math.sin(a)) for a in np.radians(np.arange(8) * 45.0 + 22.5)]
    top_z = z1_0 - 0.02 * L1
    chs, bells = [], []
    for x, y in pos:
        chs.append(ch.translate(x, y, top_z - eng_L1))
        bells.append(bell.translate(x, y, top_z - eng_L1))
    b.add("engines_1", "Cụm 9 động cơ tầng 1", "First-stage engines (9)", "engine",
          [Shape(K.Solid.union_all(chs), "steel_dark", 60.0), Shape(K.Solid.union_all(bells), "copper", 60.0)], parent_id="stage_1",
          required=True, aliases=["động cơ", "vòi phun", "cụm động cơ", "engine", "nozzle", "động cơ tầng 1"],
          function="9 động cơ dầu–ôxy lỏng, bố trí 8 vòng ngoài + 1 giữa, vòi phun chuông điều hướng được (gimbal).",
          position_tag="bottom")
    # cánh ổn định
    contacts = [["engines_1", "stage_1"]]
    if p.get("fins", True):
        fins = []
        for a in (0, 90, 180, 270):
            fin = K.hull([K.box(0.14 * L1, 0.012 * Dm, 0.001).translate(0.07 * L1, 0, 0), K.box(0.06 * L1, 0.006 * Dm, 0.001).translate(0.1 * L1, 0, 0.55 * Dm)])
            fin = fin.rotate(0, -90, 0)                                  # dây cung dọc Z, sải ra +X
            fin = fin.translate(R - 0.002 * Dm, 0, z1_0 - 0.01 * L1).rotate(0, 0, a + 45)
            fins.append(fin)
        b.add("fins", "4 cánh ổn định", "Stabilizing fins", "fin", Shape(K.Solid.union_all(fins), "paint_secondary", 60.0),
              parent_id="stage_1", required=True, aliases=["cánh ổn định", "cánh đuôi", "fins", "cánh"],
              function="4 cánh ổn định khí động ở đuôi tầng 1.", position_tag="bottom")
    # vòng nối tầng (rỗng, bao vòi phun tầng 2)
    Li = lengths[1]
    zi0, zi1 = z1_1, z1_1 + Li
    inter = K.cylinder(R, Li, segments=128) - K.cylinder(R - 0.015 * Dm, Li + 2, segments=128).translate(0, 0, -1)
    inter = inter.translate(0, 0, zi0)
    grid = []
    for a in (0, 90, 180, 270):
        g = K.box(0.02 * Dm, 0.25 * Dm, 0.2 * Dm) - K.Solid.union_all([K.box(0.03 * Dm, 0.05 * Dm, 0.05 * Dm).translate(0, (i - 1.5) * 0.06 * Dm, (j - 1.5) * 0.045 * Dm)
                                                                    for i in range(4) for j in range(4)])
        grid.append(g.translate(R + 0.01 * Dm - 0.001, 0, zi0 + 0.7 * Li).rotate(0, 0, a))
    b.add("interstage", "Vòng nối tầng + cánh lưới", "Interstage & grid fins", "interstage",
          [Shape(inter, "carbon", 60.0), Shape(K.Solid.union_all(grid), "titanium", 60.0)], parent_id="stage_1", required=True,
          aliases=["vòng nối tầng", "khoang nối tầng", "interstage", "cánh lưới", "grid fin"],
          function="Vòng nối tầng composite carbon (bao vòi phun tầng trên), cơ cấu tách khí nén, 4 cánh lưới titan.",
          position_tag="middle")
    # ---------- tầng trên ----------
    upper_ids = []
    zc = zi1
    for s in range(1, n_st):
        Ls = lengths[2] if s == 1 else lengths[4]
        sid = f"stage_{s + 1}"
        tk = tank(zc, Ls, [])
        band = (K.cylinder(R + 0.002 * Dm, 0.03 * Ls, segments=128) - K.cylinder(R - 0.01 * Dm, 0.03 * Ls + 2, segments=128).translate(0, 0, -1)).translate(0, 0, zc + 0.5 * Ls)
        eL = 0.8 * Li
        che, bel = engine(0.05 * Dm, 0.36 * Dm if s == n_st - 1 else 0.28 * Dm, eL, vacuum=True)
        che = che.translate(0, 0, zc - eL)
        bel = bel.translate(0, 0, zc - eL)
        parent = "interstage" if s == 1 else "interstage_2"         # tầng trên gá trên vòng nối tầng của tầng dưới
        b.add(sid, f"Tầng {s + 1}", f"Stage {s + 1}", "stage",
              [Shape(tk, "paint_primary", 60.0), Shape(band, "paint_secondary", 60.0)], parent_id=parent, required=True,
              aliases=[f"tầng {s + 1}", "tầng trên", f"stage {s + 1}", "bồn nhiên liệu"],
              function=f"Tầng {s + 1}: bồn ôxy lỏng + nhiên liệu, đưa tải lên quỹ đạo.", position_tag="middle",
              explode_dir=(0, 0, 1), explode_distance=0.25 * Ht * (1.2 if s == 1 else 0.8), explode_order=s,
              dimensions={"length": Ls, "diameter": Dm})
        b.add(f"engine_{s + 1}", f"Động cơ chân không tầng {s + 1}", f"Stage {s + 1} vacuum engine", "engine",
              [Shape(che, "steel_dark", 60.0), Shape(bel, "niobium", 60.0)], parent_id=sid, required=True,
              aliases=["động cơ chân không", "vòi phun", "engine", f"động cơ tầng {s + 1}"],
              function="Động cơ tối ưu chân không, vòi phun tỷ lệ giãn nở lớn.", position_tag="middle")
        contacts.append([f"engine_{s + 1}", sid])
        upper_ids.append(sid)
        zc += Ls
        if n_st == 3 and s == 1:                                   # vòng nối tầng 2–3
            L23 = lengths[3]
            ring = (K.cylinder(R, L23, segments=128) - K.cylinder(R - 0.012 * Dm, L23 + 2, segments=128).translate(0, 0, -1)).translate(0, 0, zc)
            b.add("interstage_2", "Vòng nối tầng 2–3", "Interstage 2", "interstage", Shape(ring, "carbon", 60.0), parent_id=sid,
                  required=True, aliases=["vòng nối tầng 2", "interstage"], function="Vòng nối tầng 2 và tầng 3.", position_tag="middle")
            zc += L23
    top_stage = upper_ids[-1]
    # ---------- bộ gá + vệ tinh + chóp mũi ----------
    Lf = lengths[-1]
    adapter = K.cylinder(R * 0.55, 0.02 * Lf, R * 0.4, segments=96).translate(0, 0, zc)
    sat_h, sat_w = 0.42 * Lf, 1.1 * R
    sat = K.rounded_box(sat_w, sat_w * 0.8, sat_h, 0.03 * sat_w).translate(0, 0, zc + 0.02 * Lf + sat_h / 2)
    panels = K.Solid.union_all([K.box(0.02 * sat_w, sat_w * 0.7, sat_h * 0.9).translate(s_ * (sat_w / 2 + 0.01 * sat_w), 0, zc + 0.02 * Lf + sat_h / 2)
                                for s_ in (1, -1)])
    dish = K.revolve([(0, 0), (0.25 * sat_w, 0.06 * sat_w), (0.25 * sat_w, 0.075 * sat_w), (0, 0.015 * sat_w)], segments=48).translate(0, 0, zc + 0.02 * Lf + sat_h)
    b.add("payload", "Vệ tinh (tải trọng)", "Payload satellite", "payload",
          [Shape(adapter, "aluminum", 60.0), Shape(sat, "gold", 60.0),
           Shape(panels, "pcb", 60.0), Shape(dish, "plastic_white", 60.0)], parent_id=top_stage, required=True,
          aliases=["vệ tinh", "tải trọng", "payload", "bộ gá tải"], function="Vệ tinh + bộ gá tách (vòng kẹp), nhả ra sau khi bung chóp.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.12 * Ht, explode_order=n_st + 1)
    # chóp mũi ogive (2 nửa vỏ mỏng)
    rho = (R ** 2 + Lf ** 2) / (2 * R)
    prof = []
    for t in np.linspace(0, 1, 28):
        zz = t * Lf
        r = math.sqrt(max(0.0, rho ** 2 - (zz) ** 2)) + R - rho
        prof.append((max(r, 0.0), zz))
    prof = [(R, -0.001)] + [(r, zz) for r, zz in prof if r > 0.02 * R] + [(0.0, Lf * 0.999)]
    outer = K.revolve(prof + [(0.0, -0.001)], segments=128).translate(0, 0, zc)
    inner = K.revolve([(r - 0.01 * Dm, zz) for r, zz in prof[:-1] if r - 0.01 * Dm > 0] + [(0.0, prof[-2][1] - 0.02 * Dm), (0.0, -1)],
                      segments=128).translate(0, 0, zc - 0.5)
    shell = outer - inner
    for side, sy in (("a", 1), ("b", -1)):
        half = shell & K.box(3 * Dm, 3 * Dm, 3 * Lf).translate(0, sy * 1.5 * Dm, zc + Lf / 2)
        b.add(f"fairing_{side}", f"Nửa chóp mũi {'trái' if sy > 0 else 'phải'}", "Payload fairing half", "fairing",
              Shape(half, "paint_primary", 60.0), parent_id=top_stage, required=True,
              aliases=["chóp mũi", "nửa chóp", "fairing", "mũi tên lửa", "chóp bảo vệ tải"],
              function="Nửa chóp bảo vệ tải bằng composite, tách đôi bằng khí nén sau khi ra khỏi khí quyển.",
              position_tag="top", explode_dir=(0, sy, 0.25), explode_distance=1.6 * Dm, explode_order=n_st)
    contacts += [["fairing_a", "fairing_b"], ["payload", "fairing_*"]]
    b.note_stage(1, "Tách tầng 1 (cùng vòng nối tầng) — tầng trên đánh lửa")
    if n_st == 3:
        b.note_stage(2, "Tách tầng 2 — tầng 3 đánh lửa")
    b.note_stage(n_st, "Bung hai nửa chóp mũi")
    b.note_stage(n_st + 1, "Nhả vệ tinh khỏi bộ gá")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"stages": n_st, "height_mm": Ht, "diameter_mm": Dm, "engines_stage1": 9,
                       "standard": "Tỷ lệ Falcon 9 Block 5 (70 m, Ø3,66 m, 9 + 1 động cơ)", "strict_overlap": True,
                       "contacts": contacts})
    return b.build()
