"""Chi tiết cơ khí phổ biến: bánh răng trụ răng thẳng thân khai, mặt bích có cổ và lỗ bu-lông, giá đỡ chữ L có gân.

Kích thước lấy đúng từ spec (mm); tham số người dùng không nói được điền theo tỷ lệ thiết kế và ghi vào
spec.defaults_used. Bánh răng: đường kính chia d = m·z, đỉnh d + 2m, chân d − 2,5m (profiles.involute_gear).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

MAT = {"steel": "steel", "stainless": "stainless", "aluminum": "aluminum", "brass": "brass", "plastic": "plastic_white",
       "cast_iron": "steel_black_oxide"}


def gear_solid(p: dict) -> tuple[K.Solid, dict]:
    m, z, bw = float(p["module_mm"]), int(p["teeth"]), float(p["face_width_mm"])
    prof = P.involute_gear(m, z, float(p.get("pressure_angle_deg", 20.0)), flank_samples=12, root_samples=5, tip_samples=4)
    body = K.extrude(prof, bw)
    radii = P.gear_radii(m, z)
    # vát đỉnh răng hai mặt 45° × 0,5m
    c = 0.5 * m
    ra = radii["tip"]
    cham = K.revolve([(0, 0), (ra - c, 0), (ra + 0.01, c + 0.01), (ra + 0.01, bw - c - 0.01), (ra - c, bw), (0, bw)], segments=192)
    body = body & cham
    bore = float(p["bore_mm"])
    cut = K.cylinder(bore / 2, bw + 2, segments=96).translate(0, 0, -1)
    if p.get("keyway", True) and bore >= 6:
        kw = max(2.0, bore * 0.25)
        cut = cut + K.box(kw, bore * 0.35 + 0.5, bw + 2).translate(0, bore / 2, bw / 2)
    body = body - cut
    rim = radii["root"] - 1.2 * m
    hub_r = max(bore * 0.9, bore / 2 + 2 * m)
    if rim - hub_r > 4 * m and bw > 4 * m:
        web = bw * 0.4
        pocket = K.revolve(P.fillet_polygon([(hub_r, 0), (rim, 0), (rim, (bw - web) / 2), (hub_r, (bw - web) / 2)],
                                            [0, 0, m * 0.8, m * 0.8], 6), segments=192)
        body = body - pocket.translate(0, 0, -0.01) - pocket.mirror((0, 0, 1)).translate(0, 0, bw + 0.01)
        holes = [K.cylinder((rim - hub_r) * 0.28, bw + 2, segments=48).translate((hub_r + rim) / 2 * math.cos(a),
                                                                                (hub_r + rim) / 2 * math.sin(a), -1)
                 for a in np.radians(np.arange(0, 360, 60))]
        body = body.subtract_all(holes)
    dims = {"module": m, "teeth": z, "pitch_diameter": round(m * z, 3), "tip_diameter": round(2 * radii["tip"], 3),
            "root_diameter": round(2 * radii["root"], 3), "face_width": bw, "bore": bore}
    return body, dims


def flange_solid(p: dict) -> tuple[K.Solid, dict]:
    od, idd, t = float(p["outer_d_mm"]), float(p["inner_d_mm"]), float(p["thickness_mm"])
    hub_d, hub_h = float(p["hub_d_mm"]), float(p["hub_height_mm"])
    fil = min(t * 0.4, (hub_d - idd) * 0.2, 6.0)
    pts = [(idd / 2, 0), (od / 2, 0), (od / 2, t), (hub_d / 2, t)]
    radii = [0, t * 0.12, t * 0.12, fil]
    if hub_h > 0:
        pts += [(hub_d / 2, t + hub_h), (idd / 2, t + hub_h)]
        radii += [fil * 0.5, 0.3]
    else:
        pts += [(idd / 2, t)]
        radii += [0.3]
    body = K.revolve(P.fillet_polygon(pts, radii, 8), segments=192)
    n, bc, hd = int(p.get("bolt_holes", 4)), float(p["bolt_circle_d_mm"]), float(p["hole_d_mm"])
    holes = [K.cylinder(hd / 2, t + 2, segments=48).translate(bc / 2 * math.cos(a), bc / 2 * math.sin(a), -1)
             for a in np.radians(np.arange(n) * 360.0 / n + 180.0 / n)]
    body = body.subtract_all(holes)
    return body, {"outer_diameter": od, "inner_diameter": idd, "thickness": t, "bolt_holes": n, "bolt_circle": bc,
                  "hole_diameter": hd, "hub_diameter": hub_d, "hub_height": hub_h}


def bracket_solid(p: dict) -> tuple[K.Solid, dict]:
    w, h, d, t = float(p["width_mm"]), float(p["height_mm"]), float(p["depth_mm"]), float(p["thickness_mm"])
    fr = float(p.get("fillet_mm", 6.0))
    # tiết diện chữ L trong mặt XZ, đùn theo Y (bề rộng w)
    prof = P.fillet_polygon([(0, 0), (d, 0), (d, t), (t, t), (t, h), (0, h)], [0, t * 0.3, 0.3, min(fr, h - t, d - t), t * 0.3, 0], 8)
    body = K.extrude(prof, w).rotate(90, 0, 0).translate(0, w / 2, 0)
    if p.get("gusset", True):
        g = min(d, h) * 0.55
        tri = P.fillet_polygon([(t - 0.5, t - 0.5), (t + g, t - 0.5), (t - 0.5, t + g)], [0, t * 0.4, t * 0.4], 6)
        gw = max(t, 3.0)
        body = body + K.extrude(tri, gw).rotate(90, 0, 0).translate(0, gw / 2, 0)
    n, hd = int(p.get("holes", 2)), float(p.get("hole_d_mm", 6.6))
    holes = []
    if n > 0:
        ys = np.linspace(-w / 2 + w / (2 * max(1, n)), w / 2 - w / (2 * max(1, n)), n) if n > 1 else [0.0]
        for yy in ys:
            holes.append(K.cylinder(hd / 2, t + 2, segments=40).translate(t + (d - t) * 0.6, yy, -1))
            holes.append(K.cylinder(hd / 2, t + 2, segments=40).rotate(0, 90, 0).translate(-1, yy, t + (h - t) * 0.6))
    body = body.subtract_all(holes)
    return body, {"width": w, "height": h, "depth": d, "thickness": t, "holes": n * 2, "hole_diameter": hd, "fillet": fr}


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    cat = spec.category
    mats = M.library()
    mid = MAT.get(p.get("material", "steel"), "steel")
    b = AssemblyBuilder(spec.name or cat, cat, mats)
    if cat == "gear":
        body, dims = gear_solid(p)
        b.add("gear", f"Bánh răng m{dims['module']:g} z{dims['teeth']}", f"Spur gear m{dims['module']:g} z{dims['teeth']}", "gear",
              Shape(body, mid, 30.0), required=True, aliases=["bánh răng", "nhông", "gear", "bánh xe răng"],
              function=f"Bánh răng trụ răng thẳng thân khai, module {dims['module']:g}, {dims['teeth']} răng, góc áp lực "
                       f"{p.get('pressure_angle_deg', 20):g}°.", position_tag="center", dimensions=dims)
    elif cat == "flange":
        body, dims = flange_solid(p)
        b.add("flange", "Mặt bích", "Flange", "flange", Shape(body, mid, 30.0), required=True,
              aliases=["mặt bích", "bích", "flange"], function=f"Mặt bích có cổ, {dims['bolt_holes']} lỗ bu-lông để ghép nối ống/trục.",
              position_tag="center", dimensions=dims)
    else:
        body, dims = bracket_solid(p)
        b.add("bracket", "Giá đỡ chữ L", "L bracket", "bracket", Shape(body, mid, 30.0), required=True,
              aliases=["giá đỡ", "ke góc", "bát", "pát", "bracket"], function="Giá đỡ chữ L có gân tăng cứng và lỗ bắt vít.",
              position_tag="center", dimensions=dims)
    b.metadata.update({"dimensionally_specified": True})
    return b.build()
