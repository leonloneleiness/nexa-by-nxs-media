"""Hộp giảm tốc bánh răng trụ răng thẳng 2 hoặc 3 cấp, trục song song (kiểu hộp đúc tách đôi ngang tâm trục).

Bánh răng thân khai α = 20° ăn khớp đúng khoảng cách tâm a = m·(z1 + z2)/2 (pha răng: răng bánh dẫn hướng vào rãnh
bánh bị dẫn, khe hở cạnh răng 0,05m). Bánh dẫn z = 17 (không cắt chân răng), số răng bánh bị dẫn chọn để tỷ số tổng
gần tỷ số yêu cầu; module tăng dần theo cấp (dãy module ISO 54) và được nâng thêm nếu bánh lớn cấp trước chạm trục
sau. Mỗi trục có 2 ổ bi 62xx (ISO 15) nằm trong ụ ổ đúc liền hai nửa vỏ, nắp ổ bắt 4 vít, nắp xuyên có phớt môi;
vỏ tách đôi có gờ bích + bu-lông, chân đế có lỗ bắt nền, gân tăng cứng, nắp thăm + nút thông hơi, mắt thăm dầu,
nút xả, tai cẩu.

Tháo: nắp thăm + vít, nắp ổ, bu-lông mặt ghép → nhấc nửa vỏ trên → nhấc các trục → tháo bánh răng, ổ bi khỏi trục.
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

MODULES = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
BORES_62 = [10, 12, 15, 17, 20, 25, 30, 35, 40, 45, 50, 55, 60]
Z_PINION = 17
TAG_VI = {"in": "vào", "mid": "trung gian", "mid1": "trung gian 1", "mid2": "trung gian 2", "out": "ra"}
SIDE_VI = {"a": "trước", "b": "sau"}


def _next_module(m: float, factor: float = 1.2) -> float:
    return next((x for x in MODULES if x >= m * factor - 1e-9), MODULES[-1])


def _bearing_for(d_min: float) -> str:
    d = next((b for b in BORES_62 if b >= d_min), BORES_62[-1])
    return f"62{BORES_62.index(d):02d}"


def plan(ratio: float, stages: int, m1: float) -> tuple[list[tuple[int, int]], list[float], list[str]]:
    """Số răng, module, mã ổ bi từng trục. Tỷ số cấp đầu lớn hơn (phân phối kiểu hộp tiêu chuẩn), cấp cuối bù sai
    số; module cấp sau tăng tới khi bánh lớn cấp trước không chạm trục kế tiếp (khe ≥ 3 mm)."""
    weights = {2: [0.55, 0.45], 3: [0.38, 0.33, 0.29]}[stages]
    teeth, done = [], 1.0
    for k, w in enumerate(weights):
        i_k = ratio ** w if k < stages - 1 else ratio / done
        z2 = max(Z_PINION + 3, int(round(Z_PINION * i_k)))
        teeth.append((Z_PINION, z2))
        done *= z2 / Z_PINION
    mods = [m1]
    for _ in range(stages - 1):
        mods.append(_next_module(mods[-1]))
    codes: list[str] = []
    for _ in range(12):
        codes = [_bearing_for(4 * mods[0] + 7)] + [_bearing_for(4.5 * mods[min(k, stages - 1)] + 9 + 4 * k) for k in range(1, stages + 1)]
        ok = True
        for k in range(stages - 1):
            ra_wheel = mods[k] * (teeth[k][1] + 2) / 2
            a_next = mods[k + 1] * sum(teeth[k + 1]) / 2
            r_shaft = S.BEARINGS[codes[k + 2]][0] / 2 + 2 + 2.5         # đoạn lắp bánh răng + vai trục
            if ra_wheel + r_shaft + 3 > a_next:
                mods[k + 1] = _next_module(mods[k + 1], 1.01)
                ok = False
        if ok:
            break
    return teeth, mods, codes


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    stages = int(p.get("stages", 2))
    ratio = float(p.get("ratio", 12.0))
    m1 = float(p.get("module_mm", 2.0))
    teeth, mods, bcodes = plan(ratio, stages, m1)
    mats = MC.tech_materials(spec, primary="#3d4b5c")
    housing_mat = "cast_aluminum" if p.get("housing") == "aluminum" else "cast_iron"
    b = AssemblyBuilder(spec.name or f"Hộp số {stages} cấp i = {ratio:g}", "gearbox", mats)
    n_sh = stages + 1
    a = [mods[k] * (teeth[k][0] + teeth[k][1]) / 2 for k in range(stages)]
    xs = [0.0]
    for k in range(stages):
        xs.append(xs[-1] + a[k])
    zc = 0.0
    widths = [10 * m for m in mods]
    c_ax, gap = 4 + 0.8 * m1, 6.0
    ys, y = [], 0.0
    for k in range(stages):
        y += (c_ax if k == 0 else gap) + (widths[k] + mods[k]) / 2
        ys.append(y)
        y += (widths[k] + mods[k]) / 2
    Wi = y + c_ax
    ys = [yy - Wi / 2 for yy in ys]
    bdat = [S.BEARINGS[c] for c in bcodes]
    ra = [[mods[k] * (teeth[k][0] + 2) / 2, mods[k] * (teeth[k][1] + 2) / 2] for k in range(stages)]
    clr = 3 + mods[-1]
    tips = []
    for k in range(stages):
        tips += [(xs[k] - ra[k][0], xs[k] + ra[k][0]), (xs[k + 1] - ra[k][1], xs[k + 1] + ra[k][1])]
    x_min, x_max = min(t_[0] for t_ in tips) - clr, max(t_[1] for t_ in tips) + clr
    r_max = max(max(r) for r in ra)
    z_min, z_max = zc - r_max - clr - 0.35 * r_max, zc + r_max + clr
    tw = max(7.0, 5 + 1.1 * m1)
    Bmax = max(bd[2] for bd in bdat)
    boss_len = Bmax + 4.0
    y_wall = Wi / 2 + tw
    y_boss = Wi / 2 + boss_len
    boss_r = [bd[1] / 2 + 0.55 * tw + 5 for bd in bdat]
    contacts = [("bearing_*", "housing_*"), ("shaft_*", "bearing_*"), ("cap_*", "bearing_*"), ("cap_*", "housing_upper"), ("seal_*", "shaft_*"),
                ("split_bolts", "housing_upper"), ("sight_glass", "housing_lower"), ("drain_plug", "housing_lower")]
    # ---------- trục ----------
    r_up = 3.2 * r_max + 18 * (stages + 1) + 110          # nửa vỏ trên nhấc cao hơn các trục (trục + bánh răng nằm giữa)
    shafts = []
    for i in range(n_sh):
        d, D, B, _ = bdat[i]
        seat = d + 4.0
        ext_in, ext_out = i == 0, i == n_sh - 1
        y_lo = -(y_boss + 2.2 * d + 10) if ext_in else -(Wi / 2 + B - 0.5)
        y_hi = (y_boss + 2.2 * d + 14) if ext_out else (Wi / 2 + B - 0.5)
        prof = [(0, y_lo), (d / 2 - 0.5, y_lo), (d / 2, y_lo + 0.5), (d / 2, -Wi / 2 + 0.01), (seat / 2 + 2.5, -Wi / 2 + 0.01),
                (seat / 2 + 2.5, -Wi / 2 + 3.0), (seat / 2, -Wi / 2 + 3.0), (seat / 2, Wi / 2 - 3.0), (seat / 2 + 2.5, Wi / 2 - 3.0),
                (seat / 2 + 2.5, Wi / 2 - 0.01), (d / 2, Wi / 2 - 0.01), (d / 2, y_hi - 0.5), (d / 2 - 0.5, y_hi), (0, y_hi)]
        sh = K.revolve(prof, segments=48).rotate(-90, 0, 0)            # revolve dọc Z rồi quay −90° quanh X: z → y
        key = None
        if ext_in or ext_out:
            kl = 1.6 * d
            yk = (y_lo + 2 + kl / 2) if ext_in else (y_hi - 2 - kl / 2)
            kw_, kh = max(3.0, 0.28 * d), max(3.0, 0.18 * d)
            slot = K.rounded_box(kw_, kl, kh + 1, kw_ * 0.49).translate(0, yk, d / 2 - kh / 2 + 0.5)
            sh = sh - slot
            key = K.rounded_box(kw_ - 0.04, kl - 0.04, kh * 1.6, kw_ * 0.47).translate(0, yk, d / 2 - kh / 2 + kh * 0.3)
        shafts.append({"solid": sh.translate(xs[i], 0, zc), "key": key.translate(xs[i], 0, zc) if key is not None else None,
                       "d": d, "D": D, "B": B, "seat": seat})
    for i in range(n_sh):
        if i == 0:
            sid, vi, en = "shaft_in", "Trục vào", "Input shaft"
        elif i == n_sh - 1:
            sid, vi, en = "shaft_out", "Trục ra", "Output shaft"
        else:
            sid = "shaft_mid" if stages == 2 else f"shaft_mid{i}"
            vi, en = ("Trục trung gian" if stages == 2 else f"Trục trung gian {i}"), f"Intermediate shaft {i}"
        shafts[i]["id"] = sid
        shapes = [Shape(shafts[i]["solid"], "steel", 35.0)]
        if shafts[i]["key"] is not None:
            shapes.append(Shape(shafts[i]["key"], "steel_black_oxide", 35.0))
        b.add(sid, vi, en, "shaft", shapes, parent_id="housing_lower", required=True,
              aliases=[vi.lower(), "trục", "shaft"] + (["trục đầu vào", "trục sơ cấp"] if i == 0 else []) +
              (["trục đầu ra", "trục thứ cấp"] if i == n_sh - 1 else []),
              function=f"Trục Ø{shafts[i]['d']:g} mm (ngõng ổ bi), đoạn lắp bánh răng Ø{shafts[i]['seat']:g} mm"
                       + (", có then bằng" if shafts[i]["key"] is not None else "") + ".",
              position_tag="center", joint_axis=(0, 1, 0), explode_dir=(0, 0, 1),
              explode_distance=r_max * 1.2 + 30 + 18 * i, explode_order=3)
    # ---------- bánh răng ----------
    for k in range(stages):
        m = mods[k]
        z_a, z_b = teeth[k]
        ph_a, ph_b = MC.mesh_phase(z_a, z_b, 0.0)
        for j, (z_, ph, w_, si) in enumerate(((z_a, ph_a, widths[k] + m, k), (z_b, ph_b, widths[k], k + 1))):
            g = MC.spur_gear(m, z_, w_, shafts[si]["seat"], phase_deg=ph, lighten=True)
            g = g.rotate(-90, 0, 0).translate(xs[si], ys[k], zc)       # trục Z → Y (hướng +X giữ nguyên ↔ góc pha 0)
            role = "bánh dẫn" if j == 0 else "bánh bị dẫn"
            b.add(f"gear_{2 * k + j + 1}", f"Bánh răng cấp {k + 1} ({role}, z = {z_})",
                  f"Stage {k + 1} {'pinion' if j == 0 else 'wheel'} z{z_}", "gear", Shape(g, "steel", 35.0),
                  parent_id=shafts[si]["id"], required=True,
                  aliases=["bánh răng", "nhông", "gear", f"bánh răng cấp {k + 1}", role, "bánh răng nhỏ" if j == 0 else "bánh răng lớn"],
                  function=f"Bánh răng trụ răng thẳng m = {m:g}, z = {z_}, α = 20°, rộng {w_:g} mm.",
                  position_tag="center", joint_axis=(0, 1, 0), explode_dir=(0, 1 if ys[k] >= 0 else -1, 0),
                  explode_distance=Wi * 0.5 + w_ + 20, explode_order=4,
                  dimensions={"module": m, "teeth": z_, "pitch_diameter": round(m * z_, 3)})
    # ---------- ổ bi ----------
    for i, sh in enumerate(shafts):
        rings, rolling, inner = MC.bearing_solid(bcodes[i], seal="ZZ", detail="low")
        B = sh["B"]
        tag = sh["id"].replace("shaft_", "")
        tvi = TAG_VI.get(tag, tag)
        for side, yb in (("a", -(Wi / 2 + B / 2)), ("b", Wi / 2 + B / 2)):
            def tr(s: K.Solid, yb: float = yb, i: int = i) -> K.Solid:
                return s.rotate(-90, 0, 0).translate(xs[i], yb, zc)
            b.add(f"bearing_{tag}_{side}", f"Ổ bi {bcodes[i]} — trục {tvi} ({SIDE_VI[side]})", f"Bearing {bcodes[i]}", "bearing",
                  [Shape(tr(rings), "bearing_steel", 30.0), Shape(tr(inner), "bearing_steel", 30.0)] +
                  ([Shape(tr(rolling), "bearing_steel", 30.0)] if rolling is not None else []),
                  parent_id=sh["id"], required=True, aliases=["ổ bi", "vòng bi", "bạc đạn", "bearing", bcodes[i]],
                  function=f"Ổ bi rãnh sâu {bcodes[i]}-ZZ (ISO 15) đỡ trục.", position_tag="left" if side == "a" else "right",
                  explode_dir=(0, -1 if side == "a" else 1, 0), explode_distance=boss_len + 25, explode_order=4)
    # ---------- vỏ hộp ----------
    ox0, ox1 = x_min - tw, x_max + tw
    oz0, oz1 = z_min - tw, z_max + tw
    env = K.rounded_box(ox1 - ox0, 2 * y_wall, oz1 - oz0, tw * 1.2).translate((ox0 + ox1) / 2, 0, (oz0 + oz1) / 2)
    bosses = [K.cylinder(boss_r[i], 2 * y_boss, segments=96).rotate(-90, 0, 0).translate(xs[i], -y_boss, zc) for i in range(n_sh)]
    tf = 1.1 * tw
    fw = 2.6 * tw + 6
    flange = K.rounded_box(ox1 - ox0 + 2 * fw, 2 * y_wall + 2 * fw, 2 * tf, tf * 0.35).translate((ox0 + ox1) / 2, 0, zc)
    # gờ bích lùi lại quanh ụ ổ: ụ ổ nhô ra ngoài gờ, nắp ổ tựa trên mặt ụ
    flange = flange.subtract_all([K.box(2 * boss_r[i] + 6, fw * 2, 4 * tf).translate(xs[i], sgn * (y_boss + fw), zc)
                                  for i in range(n_sh) for sgn in (1, -1)])
    foot_h = 1.2 * tw
    feet = []
    for sgn in (1, -1):
        yy = sgn * (y_wall + fw * 0.55)
        pad = K.rounded_box(ox1 - ox0 + fw * 0.8, fw * 1.4, foot_h, 2.0).translate((ox0 + ox1) / 2, yy, oz0 + foot_h / 2)
        web = K.box(ox1 - ox0 - 2 * tw, abs(yy), foot_h).translate((ox0 + ox1) / 2, yy / 2, oz0 + foot_h / 2)
        holes = [K.cylinder(0.3 * fw, foot_h + 2, segments=24).translate(xh, yy + sgn * fw * 0.15, oz0 - 1)
                 for xh in (ox0 + 0.1 * fw, ox1 - 0.1 * fw)]
        feet.append((pad + web).subtract_all(holes))
    ribs = []
    for i in range(n_sh):
        for sgn in (1, -1):
            h_r = (zc - boss_r[i] * 0.3) - oz0
            ribs.append(K.box(0.9 * tw, boss_len - tw, h_r).translate(xs[i], sgn * (y_wall + (boss_len - tw) / 2 - 0.5), oz0 + h_r / 2))
    env = K.Solid.union_all([env, flange] + bosses + feet + ribs)
    lug_r = 0.9 * tw + 6
    lugs = []
    for sgn in (-1, 1):
        xl = (ox1 + lug_r * 0.4) if sgn > 0 else (ox0 - lug_r * 0.4)
        zl = oz1 - lug_r * 0.6
        lug = K.hull([K.cylinder(lug_r, 1.2 * tw, segments=48).rotate(-90, 0, 0).translate(xl, -0.6 * tw, zl),
                      K.box(lug_r * 1.8, 1.2 * tw, 1.0).translate(xl - sgn * lug_r * 0.6, 0, zc + tf + 0.5)])
        lugs.append(lug - K.cylinder(lug_r * 0.45, 3 * tw, segments=32).rotate(-90, 0, 0).translate(xl, -1.5 * tw, zl))
    cavity = K.rounded_box(x_max - x_min, Wi, z_max - z_min, min(8.0, tw)).translate((x_min + x_max) / 2, 0, (z_min + z_max) / 2)
    bores = [K.cylinder(bdat[i][1] / 2, 2 * y_boss + 4, segments=96).rotate(-90, 0, 0).translate(xs[i], -y_boss - 2, zc)
             for i in range(n_sh)]
    ins_w, ins_l = Wi * 0.55, (x_max - x_min) * 0.4
    ins_x = (xs[0] + xs[-1]) / 2
    shell = env.subtract_all([cavity] + bores)
    big = 20 * (ox1 - ox0 + y_wall + fw)
    lower = shell & K.box(big, big, big).translate(0, 0, zc - big / 2)
    upper = K.Solid.union_all([shell, *lugs]) & K.box(big, big, big).translate(0, 0, zc + big / 2)
    upper = upper - K.rounded_box(ins_l, ins_w, 3 * tw, 4).translate(ins_x, 0, oz1)
    # bu-lông mặt ghép (hai hàng dọc theo gờ bích, tránh ụ ổ)
    bd_ = 8.0 if m1 < 3 else 10.0
    yf = y_wall + fw * 0.5
    xf0, xf1 = ox0 - fw * 0.2, ox1 + fw * 0.2
    nx = max(2, int((xf1 - xf0) / 70) + 1)
    pts = []
    for xx in np.linspace(xf0, xf1, nx):
        for yy in (-yf, yf):
            if all(abs(xx - xs[i]) > boss_r[i] + 3 + bd_ * 1.4 for i in range(n_sh)):
                pts.append((float(xx), float(yy), zc + tf))
    bolts, nuts, cores = MC.bolt_joint(pts, (0, 0, 1), bd_, 2 * tf)
    lower, upper = lower - cores, upper - cores
    # mắt thăm dầu + nút xả trên vách trước (−Y)
    z_oil = zc - 0.5 * r_max
    xg = (xs[0] + xs[1]) / 2
    sg_r = 9.0 + m1
    to_y = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, 0]])       # trục +Z → −Y
    glass = K.cylinder(sg_r, tw, segments=48).transform(to_y).translate(xg, -Wi / 2, z_oil)
    lower = lower - K.cylinder(sg_r, tw + 2, segments=48).transform(to_y).translate(xg, -Wi / 2 + 1, z_oil)
    ring = (K.cylinder(sg_r + 5, 3.0, segments=48) - K.cylinder(sg_r * 0.8, 10, segments=48).translate(0, 0, -5)).transform(to_y)
    ring = ring.translate(xg, -y_wall, z_oil)
    mark = K.box(sg_r * 1.6, 0.6, 0.9).translate(xg, -y_wall - 0.3, z_oil) & \
        K.cylinder(sg_r * 0.78, 6, segments=48).transform(to_y).translate(xg, -y_wall + 2, z_oil)
    b.add("sight_glass", "Mắt thăm dầu", "Oil sight glass", "sight_glass",
          [Shape(ring, "cast_aluminum", 30.0), Shape(glass, "glass", 30.0), Shape(mark, "paint_red", 30.0)],
          parent_id="housing_lower", aliases=["mắt thăm dầu", "kính thăm dầu", "sight glass", "mắt dầu", "nút thăm dầu"],
          function="Quan sát mức dầu bôi trơn (vạch đỏ = mức chuẩn).", position_tag="front",
          explode_dir=(0, -1, 0), explode_distance=40, explode_order=1)
    xd = (xs[-2] + xs[-1]) / 2
    zd = oz0 + foot_h + 9.0
    plug = K.extrude(P.circle(7.0, 6), 6.0).transform(to_y).translate(xd, -y_wall, zd) + \
        K.cylinder(5.0, tw, segments=24).transform(to_y).translate(xd, -Wi / 2, zd)
    lower = lower - K.cylinder(5.0, tw + 0.02, segments=24).transform(to_y).translate(xd, -Wi / 2 + 0.01, zd)
    b.add("drain_plug", "Nút xả dầu", "Drain plug", "plug", Shape(plug, "steel_zinc", 30.0), parent_id="housing_lower",
          aliases=["nút xả dầu", "ốc xả nhớt", "drain plug"], function="Xả dầu cũ khi thay dầu.", position_tag="front",
          explode_dir=(0, -1, 0), explode_distance=35, explode_order=1)
    # nắp thăm + nút thông hơi
    cov_t = 4.0
    cover = K.rounded_box(ins_l + 18, ins_w + 18, cov_t, 5).translate(ins_x, 0, oz1 + cov_t / 2)
    cpts = [(ins_x + sx * (ins_l + 9) / 2, sy * (ins_w + 9) / 2, oz1 + cov_t) for sx in (1, -1) for sy in (1, -1)]
    scr = K.Solid.union_all([MC.socket_screw(4, 10).translate(*pp) for pp in cpts])
    score = K.Solid.union_all([K.cylinder(2.0, 10.02, segments=14).translate(pp[0], pp[1], pp[2] - 10.01) for pp in cpts])
    cover = cover - score
    upper = upper - score
    vent = K.revolve(P.fillet_polygon([(0, 0), (7, 0), (7, 5), (4, 5), (4, 9), (6, 9), (6, 13), (0, 15)],
                                      [0, 0.5, 0.3, 0, 0, 0.5, 1.5, 0], 3), segments=32).translate(ins_x + ins_l * 0.25, 0, oz1 + cov_t)
    b.add("housing_lower", "Nửa vỏ dưới", "Lower housing", "housing", Shape(lower, housing_mat, 60.0), required=True,
          aliases=["vỏ dưới", "thân hộp số", "đế hộp số", "vỏ hộp", "housing", "chân đế"],
          function="Vỏ đúc nửa dưới: chứa dầu, ụ đỡ ổ bi, chân bắt bu-lông nền.", position_tag="bottom")
    b.add("housing_upper", "Nửa vỏ trên", "Upper housing", "housing", Shape(upper, housing_mat, 60.0), parent_id="housing_lower",
          required=True, aliases=["vỏ trên", "nắp hộp số", "vỏ hộp", "housing", "tai cẩu"],
          function="Vỏ đúc nửa trên, ghép với nửa dưới tại mặt phẳng tâm trục; có tai cẩu.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=r_up, explode_order=2)
    b.add("split_bolts", "Bu-lông mặt ghép", "Split-line bolts", "fastener",
          [Shape(bolts, "steel_black_oxide", 35.0), Shape(nuts, "steel_black_oxide", 35.0)], parent_id="housing_lower",
          required=True, aliases=["bu lông", "bulong", "bu-lông mặt ghép", "ốc", "bolts"],
          function=f"{len(pts)} bu-lông M{bd_:g} ép hai nửa vỏ.", position_tag="center",
          explode_dir=(0, 0, 1), explode_distance=r_up + 80, explode_order=1)
    b.add("inspection_cover", "Nắp thăm + nút thông hơi", "Inspection cover & breather", "cover",
          [Shape(cover, housing_mat, 40.0), Shape(vent, "brass", 40.0)], parent_id="housing_upper",
          aliases=["nắp thăm", "nắp kiểm tra", "nút thông hơi", "que thăm dầu", "cover"],
          function="Nắp thăm để kiểm tra ăn khớp và châm dầu; nút thông hơi cân bằng áp suất.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=40, explode_order=1)
    b.add("cover_screws", "Vít nắp thăm", "Cover screws", "screw", Shape(scr, "steel_black_oxide", 35.0), parent_id="inspection_cover",
          aliases=["vít nắp", "vít"], function="4 vít M4 giữ nắp thăm.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=30, explode_order=1)
    contacts.append(("cover_screws", "housing_upper"))
    # ---------- nắp ổ (mặt bích ngoài ụ ổ, gờ chặn vòng ngoài ổ bi) + phớt ----------
    for i, sh in enumerate(shafts):
        d, D, B = sh["d"], sh["D"], sh["B"]
        tag = sh["id"].replace("shaft_", "")
        tvi = TAG_VI.get(tag, tag)
        for side, sgn in (("a", -1), ("b", 1)):
            through = (i == 0 and side == "a") or (i == n_sh - 1 and side == "b")
            ct = 6.0 + 0.15 * d
            spig = boss_len - B
            cr = boss_r[i] - 1.0
            cap = K.revolve(P.fillet_polygon([(0, -ct), (cr, -ct), (cr, 0), (D / 2, 0), (D / 2, spig), (0, spig)],
                                             [0, 1.0, 0.0, 0.0, 0.3, 0], 3), segments=96)
            if through:
                cap = cap - K.cylinder(d / 2 + 1.5, 400, segments=48).translate(0, 0, -200)
            rs = D / 2 + (cr + 1 - D / 2) / 2
            cpts2 = [(rs * math.cos(t_), rs * math.sin(t_)) for t_ in np.radians([45, 135, 225, 315])]
            cscr = K.Solid.union_all([MC.socket_screw(4, 12).rotate(180, 0, 0).translate(x_, y_, -ct) for x_, y_ in cpts2])
            ccore = K.Solid.union_all([K.cylinder(2.0, 12.02, segments=14).translate(x_, y_, -ct - 0.01) for x_, y_ in cpts2])
            cap = cap - ccore
            # +Z của nắp hướng vào trong hộp: phía b (+Y) → −Y, phía a (−Y) → +Y
            m_in = np.array([[1.0, 0, 0, 0], [0, 0, -sgn * 1.0, 0], [0, sgn * 1.0, 0, 0]])

            def place(s: K.Solid, m_in: np.ndarray = m_in, i: int = i, sgn: int = sgn) -> K.Solid:
                return s.transform(m_in).translate(xs[i], sgn * y_boss, zc)
            cid = f"cap_{tag}_{side}"
            b.add(cid, ("Nắp ổ xuyên" if through else "Nắp ổ kín") + f" — trục {tvi} ({SIDE_VI[side]})", "Bearing cap", "cover",
                  [Shape(place(cap), housing_mat, 40.0), Shape(place(cscr), "steel_black_oxide", 40.0)],
                  parent_id="housing_lower", aliases=["nắp ổ", "nắp ổ bi", "bearing cap", "nắp chặn"],
                  function="Nắp ổ bắt 4 vít M4, chặn vòng ngoài ổ bi theo chiều trục.", position_tag="left" if sgn < 0 else "right",
                  explode_dir=(0, sgn, 0), explode_distance=30 + 5 * i, explode_order=1)
            b.cut("housing_lower", place(ccore))
            b.cut("housing_upper", place(ccore))
            if through:
                seal = K.revolve(P.fillet_polygon([(d / 2, -ct + 0.8), (d / 2 + 1.5, -ct + 0.8), (d / 2 + 1.5, -0.8), (d / 2, -0.8)],
                                                  [0, 0.3, 0.3, 0], 3), segments=64)
                seal = seal + K.revolve([(d / 2, -0.8), (d / 2 + 0.9, -0.8), (d / 2, 1.5)], segments=64)
                b.add(f"seal_{tag}", f"Phớt chặn dầu trục {tvi}", "Lip seal", "seal", Shape(place(seal), "nbr", 40.0), parent_id=cid,
                      aliases=["phớt", "phốt", "phớt chặn dầu", "seal", "phớt môi"],
                      function=f"Phớt môi {d:g}×{d + 3:g} chặn dầu rò theo trục.", position_tag="left" if sgn < 0 else "right",
                      explode_dir=(0, sgn, 0), explode_distance=25, explode_order=1)
    b.note_stage(1, "Tháo nắp thăm, vít, nắp ổ, bu-lông mặt ghép, mắt dầu, nút xả")
    b.note_stage(2, "Nhấc nửa vỏ trên")
    b.note_stage(3, "Nhấc các trục (kèm bánh răng, ổ bi)")
    b.note_stage(4, "Tháo bánh răng và ổ bi khỏi trục")
    b.place_on_ground(center_xy=True)
    actual = 1.0
    for z_a, z_b in teeth:
        actual *= z_b / z_a
    b.metadata.update({"stages": stages, "ratio_target": ratio, "ratio_actual": round(actual, 4), "modules": mods,
                       "teeth": [list(t_) for t_ in teeth], "center_distances_mm": a, "bearings": bcodes,
                       "mesh": [{"driver": f"gear_{2 * k + 1}", "driven": f"gear_{2 * k + 2}", "driver_shaft": shafts[k]["id"],
                                 "driven_shaft": shafts[k + 1]["id"], "module": mods[k]} for k in range(stages)],
                       "standard": "Bánh răng thân khai α=20° (ISO 53), module ISO 54, ổ bi ISO 15",
                       "strict_overlap": True, "contacts": [list(c) for c in contacts]})
    return b.build()
