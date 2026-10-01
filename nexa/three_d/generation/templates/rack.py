"""Tủ rack 19" (EIA-310-E / IEC 60297): khung thép sơn đen 600 mm, 4 cột gấp mép, khung đỉnh/đáy ống hộp, 4 thanh ray
19" có lỗ vuông 9,5 mm cho đai ốc lồng (3 lỗ/U theo bước 15,875–15,875–12,7; 1U = 44,45 mm; khoảng tâm lỗ ngang 465,1 mm,
lọt lòng ≥ 450 mm), cửa trước kính cường lực khung thép, cửa sau tôn đục lỗ thông gió, 2 hông tháo rời có tay nắm,
nóc có 2 quạt hút + khe đi cáp chổi cao su + 4 bu lông vòng, 4 bánh xe + 4 chân tăng chỉnh.
Thiết bị mẫu (tùy chọn): patch panel 24 cổng, thanh quản lý cáp, switch 48 cổng + 4 SFP, máy chủ 1U/2U, UPS 2U đặt đáy,
thanh PDU dọc 0U phía sau. Mặt thiết bị cao n·44,45 − 0,79 mm, tai rộng 482,6 mm, vít M6 + đai ốc lồng.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.enclosure import box_at
from nexa.three_d.generation.templates.fan import fan_parts
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

U = S.RACK["u"]
PW, HS, OP, SQ = S.RACK["panel_width"], S.RACK["hole_spacing"], S.RACK["opening"], S.RACK["square_hole"]
KIND_VI = {"patch": "Patch panel 24 cổng", "cable_mgr": "Thanh quản lý cáp", "switch": "Switch 48 cổng + 4 SFP",
           "server1u": "Máy chủ 1U", "server2u": "Máy chủ 2U", "ups": "Bộ lưu điện UPS 2U"}
KIND_EN = {"patch": "Patch panel", "cable_mgr": "Cable manager", "switch": "48-port switch", "server1u": "1U server",
           "server2u": "2U server", "ups": "2U UPS"}
KIND_DEPTH = {"patch": 90.0, "cable_mgr": 0.0, "switch": 300.0, "server1u": 700.0, "server2u": 740.0, "ups": 560.0}
KIND_ALIASES = {"patch": ["patch panel", "thanh đấu nối", "cổng mạng"], "cable_mgr": ["quản lý cáp", "vòng cáp", "cable manager"],
                "switch": ["switch", "bộ chuyển mạch", "switch mạng", "cổng rj45", "sfp"],
                "server1u": ["máy chủ", "server", "server 1u"], "server2u": ["máy chủ", "server", "server 2u", "ổ cứng"],
                "ups": ["ups", "bộ lưu điện", "lưu điện"]}


def hollow(x0, x1, y0, y1, z0, z1, axis: str, t: float = 1.5) -> K.Solid:
    """Ống hộp thành mỏng dọc `axis` (hở hai đầu)."""
    lo, hi = [x0, y0, z0], [x1, y1, z1]
    ilo, ihi = [a + t for a in lo], [b - t for b in hi]
    i = "xyz".index(axis)
    ilo[i], ihi[i] = lo[i] - 1.0, hi[i] + 1.0
    return box_at(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]) - box_at(ilo[0], ihi[0], ilo[1], ihi[1], ilo[2], ihi[2])


def rail_profile(face: float, dirx: float, sy: float) -> np.ndarray:
    """Mặt cắt ray 19" (mặt bằng XY): cánh bắt thiết bị x ∈ face…face−2·dirx, y ∈ [225, 250]; bụng 42 mm lùi theo −dirx, mép gập."""
    uv = [(0, OP / 2), (0, 250), (42, 250), (42, 238), (40, 238), (40, 248), (2, 248), (2, OP / 2)]
    return P.ensure_ccw(np.array([(face - dirx * u, sy * v) for u, v in uv]))


def hole_z(z_u0: float, n: int) -> list[float]:
    return [z_u0 + i * U + o for i in range(n) for o in S.RACK["hole_offsets"]]


def caster(x: float, y: float, z0: float) -> tuple[K.Solid, K.Solid]:
    """Bánh xe xoay Ø70 (tâm trục z = 35, chạm sàn z = 0): đế 60×60, ổ xoay, càng, trục; trả (kim loại, bánh cao su)."""
    plate = box_at(x - 30, x + 30, y - 30, y + 30, z0 - 4, z0)
    swivel = K.cylinder(20.0, 8.0, segments=32).translate(x, y, z0 - 12)
    bridge = box_at(x - 22, x + 22, y - 19, y + 19, z0 - 16, z0 - 12)
    forks = K.Solid.union_all([box_at(x - 14, x + 14, sy * 15, sy * 19, 23.0, z0 - 16).translate(0, y, 0) for sy in (1, -1)])
    axle = K.cylinder(4.0, 38.0, segments=16).rotate(90, 0, 0).translate(x, y + 19.0, 35.0)
    tire = K.revolve([(22.0, -12.5), (33.0, -12.5), (35.0, -9.0), (35.0, 9.0), (33.0, 12.5), (22.0, 12.5)], segments=48)
    hub = K.revolve([(4.0, -12.5), (22.0, -12.5), (22.0, 12.5), (4.0, 12.5)], segments=32)
    wheel = (tire + hub).rotate(90, 0, 0).translate(x, y, 35.0)
    return plate + swivel + bridge + forks + axle, wheel


def level_foot(x: float, y: float, z0: float) -> tuple[K.Solid, K.Solid]:
    rod = K.cylinder(6.0, z0 - 12.0, segments=20).translate(x, y, 12.0)
    nut = K.cylinder(10.0, 8.0, segments=6).translate(x, y, z0 - 8.0)
    pad = K.revolve([(0, 0), (22.5, 0), (22.5, 6), (12, 12), (0, 12)], segments=40).translate(x, y, 0)
    return rod + nut, pad


def device(kind: str, u: int, nU: int, x_f: float, z_u0: float, depth: float) -> dict[str, list[K.Solid]]:
    """Thiết bị 19": mặt trước + tai 482,6 mm tựa mặt ray trước (x = x_f), thân rộng 434 mm lọt giữa hai ray.
    Trả khối theo vật liệu: plate, body, dark, metal, accent, led, glass."""
    z0 = z_u0 + (u - 1) * U + 0.395
    h = nU * U - 0.79
    z1 = z0 + h
    zc = (z0 + z1) / 2
    out: dict[str, list[K.Solid]] = {k: [] for k in ("plate", "body", "dark", "metal", "accent", "led", "glass")}
    plate = box_at(x_f, x_f + 3.0, -PW / 2, PW / 2, z0, z1)
    body = box_at(x_f - depth, x_f, -217.0, 217.0, z0 + 0.5, z1 - 0.5) if depth > 0 else None
    cuts: list[K.Solid] = []
    # vít M6 đầu tròn + đai ốc lồng sau cánh ray: lỗ 1 và 3 mỗi U
    for k in range(nU):
        for o in (S.RACK["hole_offsets"][0], S.RACK["hole_offsets"][2]):
            zh = z_u0 + (u - 1 + k) * U + o
            for sy in (1, -1):
                y = sy * HS / 2
                out["metal"].append(K.cylinder(5.0, 4.0, segments=20).rotate(0, 90, 0).translate(x_f + 3.0, y, zh) +
                                    K.cylinder(3.0, 7.0, segments=12).rotate(0, 90, 0).translate(x_f - 4.0, y, zh) +
                                    box_at(x_f - 5.0, x_f - 2.0, y - 6.0, y + 6.0, zh - 6.0, zh + 6.0))
    if kind in ("server1u", "server2u", "ups"):
        for sy in (1, -1):                                             # tay kéo trên tai
            za, zb = (z0 + 15.6, z0 + 27.6) if nU == 1 else (z0 + 16.0, z1 - 16.0)
            y = sy * 229.0
            out["metal"].append(K.Solid.union_all([
                MC.orient(K.cylinder(3.0, 25.0, segments=12), (x_f + 2.0, y, za), (1, 0, 0)),
                MC.orient(K.cylinder(3.0, 25.0, segments=12), (x_f + 2.0, y, zb), (1, 0, 0)),
                K.cylinder(3.0, zb - za, segments=12).translate(x_f + 27.0, y, za),
                K.sphere(3.0, 12).translate(x_f + 27.0, y, za), K.sphere(3.0, 12).translate(x_f + 27.0, y, zb)]))
    if kind in ("server1u", "server2u"):
        rows = 1 if nU == 1 else 3
        bh = 26.0
        zs = [zc] if rows == 1 else [zc + (r - 1) * 28.0 for r in range(rows)]
        for zb_ in zs:
            for yc in (-150.0, -50.0, 50.0, 150.0):                    # khay ổ 3,5" (LFF) 96 × 26
                cuts.append(box_at(x_f - 20.0, x_f + 4.0, yc - 48.0, yc + 48.0, zb_ - bh / 2, zb_ + bh / 2))
                out["dark"].append(box_at(x_f - 20.0, x_f + 1.5, yc - 47.0, yc + 47.0, zb_ - bh / 2 + 1.0, zb_ + bh / 2 - 1.0) -
                                   K.Solid.union_all([box_at(x_f - 1.0, x_f + 2.0, yc - 40.0 + 6.0 * j, yc - 37.0 + 6.0 * j, zb_ - 8.0, zb_ + 8.0) for j in range(8)]))
                out["metal"].append(box_at(x_f + 1.5, x_f + 3.5, yc + 30.0, yc + 44.0, zb_ - 10.0, zb_ + 10.0))   # lẫy khay
                out["led"].append(K.cylinder(1.2, 1.0, segments=10).rotate(0, 90, 0).translate(x_f + 1.5, yc + 37.0, zb_ + 11.0))
        out["accent"].append(K.cylinder(3.5, 2.0, segments=20).rotate(0, 90, 0).translate(x_f + 3.0, 208.0, zc))    # nút nguồn
        out["led"].append(K.cylinder(1.5, 1.0, segments=10).rotate(0, 90, 0).translate(x_f + 3.0, -208.0, zc))
    elif kind == "switch":
        for r, zr in enumerate((zc + 7.5, zc - 7.5)):
            for i in range(24):
                yc = -198.0 + i * 14.0 + (i // 6) * 6.0
                cuts.append(box_at(x_f - 12.0, x_f + 4.0, yc - 5.8, yc + 5.8, zr - 6.0, zr + 6.0))
                out["dark"].append(box_at(x_f - 12.0, x_f - 9.0, yc - 5.8, yc + 5.8, zr - 6.0, zr + 6.0))
                out["led"].append(box_at(x_f + 3.0, x_f + 3.6, yc + 3.5, yc + 5.0, zr + 6.6 if r == 0 else zr - 8.1, zr + 8.1 if r == 0 else zr - 6.6))
        for i in range(4):
            yc = 158.0 + i * 15.0
            cuts.append(box_at(x_f - 30.0, x_f + 4.0, yc - 7.0, yc + 7.0, zc - 5.0, zc + 5.0))
            out["metal"].append(box_at(x_f - 30.0, x_f + 1.0, yc - 7.0, yc + 7.0, zc - 5.0, zc + 5.0) -
                                box_at(x_f - 25.0, x_f + 2.0, yc - 6.0, yc + 6.0, zc - 4.0, zc + 4.0))
        out["led"].append(box_at(x_f + 3.0, x_f + 3.6, 210.0, 213.0, zc + 10.0, zc + 13.0))
    elif kind == "patch":
        for i in range(24):
            yc = -198.0 + i * 16.5 + (i // 6) * 3.0
            cuts.append(box_at(x_f - 20.0, x_f + 4.0, yc - 7.2, yc + 7.2, zc - 11.0, zc + 5.0))
            out["dark"].append(box_at(x_f - 20.0, x_f - 17.0, yc - 7.2, yc + 7.2, zc - 11.0, zc + 5.0))
        out["accent"].append(box_at(x_f + 3.0, x_f + 3.4, -200.0, 200.0, zc + 7.0, zc + 15.0))    # dải nhãn số cổng
    elif kind == "cable_mgr":
        for yc in np.linspace(-190.0, 190.0, 5):
            path = [(x_f + 2.0, yc, z0 + 7.0), (x_f + 40.0, yc, z0 + 7.0)]
            path += [(x_f + 40.0 + 14.0 * math.sin(a), yc, zc - 14.0 * math.cos(a)) for a in np.linspace(0, math.pi, 12)[1:-1]]
            path += [(x_f + 40.0, yc, z1 - 7.0), (x_f + 2.0, yc, z1 - 7.0)]
            out["dark"].append(K.tube(np.array(path), 3.0, 10))
    elif kind == "ups":
        cuts.append(box_at(x_f + 1.0, x_f + 4.0, -180.0, -110.0, zc + 2.0, zc + 30.0))
        out["glass"].append(box_at(x_f + 1.0, x_f + 2.5, -180.0, -110.0, zc + 2.0, zc + 30.0))
        for i in range(4):
            out["accent" if i == 0 else "dark"].append(K.cylinder(4.0, 3.0, segments=20).rotate(0, 90, 0).translate(x_f + 3.0, -170.0 + 20.0 * i, zc - 18.0))
        for i in range(3):
            out["led"].append(K.cylinder(1.5, 1.0, segments=10).rotate(0, 90, 0).translate(x_f + 3.0, -95.0, zc + 24.0 - 10.0 * i))
        for i in range(20):                                            # khe gió mặt trước
            yc = -40.0 + i * 12.0
            cuts.append(box_at(x_f + 1.5, x_f + 4.0, yc - 2.5, yc + 2.5, z0 + 10.0, z1 - 10.0))
    solid = plate if body is None else plate + body
    if cuts:
        solid = solid.subtract_all(cuts)
    out["plate"].append(solid)
    return out


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    n = int(p.get("rack_units", 42))
    D = float(p.get("depth_mm", 1000.0))
    equipment = bool(p.get("equipment", True))
    W = 600.0
    mats = MC.tech_materials(spec, primary="#1e2024", secondary="#2b2e33", accent="#22d3ee")
    b = AssemblyBuilder(spec.name or f"Tủ rack 19\" {n}U", "server_rack", mats)
    td = 20.0                                                          # bề dày cửa
    Df, Wf = D - 2 * td, W - 3.0                                       # khung (hông tôn 1,5 mỗi bên)
    z0 = 90.0                                                          # đáy khung (bánh xe Ø70 + đế xoay)
    z_u0 = z0 + 40.0
    zt = z_u0 + n * U
    top = zt + 40.0
    x_f = D / 2 - 100.0                                                # mặt ray trước
    x_b = x_f - (D - 250.0)                                            # mặt ray sau (chiều sâu lắp D − 250)

    # ---------- khung: 4 cột gấp mép + khung đỉnh/đáy ống hộp 40×40 + thanh đỡ ray
    ring = []
    for zlo in (z0, zt):
        for sy in (1, -1):
            ring.append(hollow(-Df / 2, Df / 2, sy * (Wf / 2 - 40), sy * Wf / 2, zlo, zlo + 40, "x"))
        for sx in (1, -1):
            ring.append(hollow(sx * (Df / 2 - 40), sx * Df / 2, -(Wf / 2 - 40), Wf / 2 - 40, zlo, zlo + 40, "y"))
        for xa in (x_f - 42.0, x_b):
            ring.append(hollow(xa, xa + 42.0, -(Wf / 2 - 40), Wf / 2 - 40, zlo, zlo + 40, "y"))
    lprof = [(0, 0), (-40, 0), (-40, -10), (-38, -10), (-38, -2), (-2, -2), (-2, -38), (-10, -38), (-10, -40), (0, -40)]
    posts = [K.extrude(P.ensure_ccw(np.array([(sx * (Df / 2 + u_), sy * (Wf / 2 + v_)) for u_, v_ in lprof])), zt - z_u0).translate(0, 0, z_u0)
             for sx in (1, -1) for sy in (1, -1)]
    eye_xy = [(sx * (Df / 2 - 20), sy * (Wf / 2 - 20)) for sx in (1, -1) for sy in (1, -1)]
    frame = K.Solid.union_all(ring + posts).subtract_all([K.cylinder(5.25, 10.0, segments=20).translate(x, y, top - 5.0) for x, y in eye_xy])
    b.add("frame", "Khung tủ thép (cột + khung đỉnh/đáy)", "Rack frame", "frame", Shape(frame, "paint_primary", 35.0), required=True,
          aliases=["khung tủ", "khung rack", "cột tủ", "frame"], function="4 cột thép gấp mép + khung đỉnh/đáy ống hộp 40×40, thanh đỡ ray.",
          position_tag="center", dimensions={"width": W, "depth": D, "height": top + 1.5})

    # ---------- 4 ray 19" lỗ vuông
    rails = []
    for face, dirx in ((x_f, 1.0), (x_b, -1.0)):
        for sy in (1, -1):
            r = K.extrude(rail_profile(face, dirx, sy), n * U).translate(0, 0, z_u0)
            holes = [box_at(face - dirx * 4.0, face + dirx * 2.0, sy * HS / 2 - SQ / 2, sy * HS / 2 + SQ / 2, z - SQ / 2, z + SQ / 2) for z in hole_z(z_u0, n)]
            rails.append(r.subtract_all(holes))
    b.add("rails", "Ray 19\" lỗ vuông (4)", "19-inch mounting rails", "rail", Shape(K.Solid.union_all(rails), "steel_zinc", 35.0), parent_id="frame",
          required=True, aliases=["ray 19 inch", "thanh ray", "ray tủ", "lỗ vuông", "rail"],
          function=f"Ray thép mạ kẽm 2 mm, lỗ vuông 9,5 mm bước EIA-310 (3 lỗ/U), {n}U, khoảng tâm ngang 465,1 mm, lọt lòng 450 mm.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.3 * top, explode_order=4,
          dimensions={"hole_spacing": HS, "opening": OP, "units": n})

    # ---------- cửa trước kính (bản lề +Y, tay khóa −Y)
    Wd, z_d0, z_d1 = W - 2.0, z0 + 1.0, top - 1.0
    door = box_at(Df / 2, D / 2, -Wd / 2, Wd / 2, z_d0, z_d1)
    opening = box_at(Df / 2 - 1, D / 2 + 1, -Wd / 2 + 50, Wd / 2 - 50, z_d0 + 50, z_d1 - 50)
    rebate = box_at(Df / 2 - 1, Df / 2 + 6, -Wd / 2 + 40, Wd / 2 - 40, z_d0 + 40, z_d1 - 40)
    zm = (z_d0 + z_d1) / 2
    pocket = box_at(D / 2 - 10, D / 2 + 1, -Wd / 2 + 10, -Wd / 2 + 40, zm - 75, zm + 75)
    notches = [box_at(Df / 2 - 1, D / 2 - 8, Wd / 2 - 12, Wd / 2 + 1, z - 30, z + 30) for z in (z_d0 + 0.12 * (z_d1 - z_d0), z_d1 - 0.12 * (z_d1 - z_d0))]
    door = door.subtract_all([opening, rebate, pocket] + notches)
    glass = box_at(Df / 2 + 1, Df / 2 + 6, -Wd / 2 + 41, Wd / 2 - 41, z_d0 + 41, z_d1 - 41)

    def handle(xs: float, sgn: float) -> tuple[K.Solid, K.Solid]:
        base = box_at(xs, xs - sgn * 4, -Wd / 2 + 10, -Wd / 2 + 40, zm - 75, zm + 75)
        lever = box_at(xs - sgn * 4, xs - sgn * 9, -Wd / 2 + 16, -Wd / 2 + 34, zm - 65, zm + 40)
        lock = K.cylinder(7.0, 5.0, segments=20).rotate(0, 90, 0).translate(min(xs - sgn * 4, xs - sgn * 9), -Wd / 2 + 25, zm + 55)
        return base + lever, lock - box_at(xs - sgn * 12, xs + sgn * 2, -Wd / 2 + 24, -Wd / 2 + 26, zm + 51, zm + 59)

    def hinges(xc: float) -> K.Solid:
        return K.Solid.union_all([K.cylinder(6.0, 60.0, segments=20).translate(xc, Wd / 2 - 6, z - 30) for z in (z_d0 + 0.12 * (z_d1 - z_d0), z_d1 - 0.12 * (z_d1 - z_d0))])

    hb, hl = handle(D / 2 - 10, -1.0)
    b.add("front_door", "Cửa trước kính cường lực", "Front glass door", "door",
          [Shape(door, "paint_primary", 35.0), Shape(glass, "glass_tinted", 35.0), Shape(hb, "plastic_black", 35.0), Shape(hl, "chrome", 35.0),
           Shape(hinges(Df / 2 + 6), "steel", 35.0)], parent_id="frame", required=True,
          aliases=["cửa trước", "cửa kính", "cửa tủ", "tay khóa", "front door"], function="Khung thép 20 mm, kính cường lực 5 mm, tay khóa xoay, 2 bản lề.",
          position_tag="front", joint_axis=(0, 0, 1), pivot=(Df / 2 + 6, Wd / 2 - 6, zm), explode_dir=(1, 0, 0), explode_distance=0.6 * D, explode_order=1)

    # ---------- cửa sau tôn đục lỗ (khay 20 mm)
    rdoor = box_at(-D / 2, -Df / 2, -Wd / 2, Wd / 2, z_d0, z_d1) - box_at(-D / 2 + 1.5, -Df / 2 + 1, -Wd / 2 + 1.5, Wd / 2 - 1.5, z_d0 + 1.5, z_d1 - 1.5)
    slots = [box_at(-D / 2 - 1, -D / 2 + 2.5, y - 3, y + 3, z - 40, z + 40)
             for y in np.arange(-Wd / 2 + 60, Wd / 2 - 59, 15.0) for z in np.arange(z_d0 + 120, z_d1 - 119, 100.0)]
    rpocket = box_at(-D / 2 - 1, -D / 2 + 10, -Wd / 2 + 10, -Wd / 2 + 40, zm - 75, zm + 75)
    rdoor = rdoor.subtract_all(slots + [rpocket])
    rpocket_box = rpocket & box_at(-D / 2, -D / 2 + 11.5, -Wd / 2 + 8.5, -Wd / 2 + 41.5, zm - 76.5, zm + 76.5)
    tray = box_at(-D / 2 + 10, -D / 2 + 11.5, -Wd / 2 + 8.5, -Wd / 2 + 41.5, zm - 76.5, zm + 76.5)   # đáy hốc tay khóa
    rhb, rhl = handle(-D / 2 + 10, 1.0)
    b.add("rear_door", "Cửa sau tôn đục lỗ thông gió", "Rear perforated door", "door",
          [Shape(rdoor + tray - (rpocket_box - tray), "paint_primary", 35.0), Shape(rhb, "plastic_black", 35.0), Shape(rhl, "chrome", 35.0),
           Shape(hinges(-Df / 2 - 6), "steel", 35.0)], parent_id="frame", required=True,
          aliases=["cửa sau", "cửa lưới", "cửa thông gió", "rear door"], function="Tôn 1,5 mm gấp khay, khe thông gió dọc, tay khóa xoay.",
          position_tag="rear", joint_axis=(0, 0, 1), pivot=(-Df / 2 - 6, Wd / 2 - 6, zm), explode_dir=(-1, 0, 0), explode_distance=0.6 * D, explode_order=1)

    # ---------- 2 hông tháo rời
    for sy, pid, vi in ((1, "side_left", "trái"), (-1, "side_right", "phải")):
        yo, yi = sy * W / 2, sy * Wf / 2
        skin = box_at(-Df / 2 + 1, Df / 2 - 1, yi, yo, z_d0, z_d1)
        cups, cup_open, louv = [], [], []
        x_cup_r = x_b + 90.0                                           # hốc sau lùi vào: nhường khe cột–ray sau cho PDU 0U
        for xc in (max(Df / 2 - 150, x_cup_r + 60.0), x_cup_r):
            cup_open.append(box_at(xc - 18.5, xc + 18.5, yi - 1, yo + 1, zm - 48.5, zm + 48.5))
            cups.append(box_at(xc - 20, xc + 20, yi - sy * 15, yi, zm - 50, zm + 50) - box_at(xc - 18.5, xc + 18.5, yi - sy * 13.5, yo + sy, zm - 48.5, zm + 48.5))
        for zz in (z_d1 - 120, z_d0 + 120):
            louv += [box_at(x - 40, x + 40, yi - 1, yo + 1, zz - 2.5, zz + 2.5) for x in np.linspace(-Df / 2 + 150, Df / 2 - 150, max(2, int((Df - 300) / 120)))]
        panel = skin.subtract_all(cup_open + louv) + K.Solid.union_all(cups)
        lock = K.cylinder(9.0, 10.0, segments=24).rotate(-90 * sy, 0, 0).translate(0, yi - sy * 8.5, zm + 150) - \
            box_at(-1.0, 1.0, yo - sy * 2, yo + sy, zm + 146, zm + 154)
        panel = panel - K.cylinder(9.0, 3.0, segments=24).rotate(-90 * sy, 0, 0).translate(0, yi - sy * 1.0, zm + 150)
        b.add(pid, f"Tấm hông {vi}", f"Side panel {'left' if sy > 0 else 'right'}", "cover",
              [Shape(panel, "paint_primary", 35.0), Shape(lock, "chrome", 35.0)], parent_id="frame", required=True,
              aliases=["hông tủ", "tấm hông", f"hông {vi}", "side panel"], function="Tôn 1,5 mm tháo rời, 2 hốc tay nắm, khóa, khe thoát nhiệt.",
              position_tag="left" if sy > 0 else "right", explode_dir=(0, sy, 0), explode_distance=0.5 * W, explode_order=1)

    # ---------- nóc: 2 quạt, khe đi cáp chổi cao su, bu lông vòng
    gap = (x_f - 42.0) - (x_b + 42.0)
    fs = 120 if gap >= 130.0 else 80
    F = fan_parts(fs, 7)
    A, T = F["A"], F["T"]
    xfc = (x_f + x_b) / 2
    fan_c = [(xfc, sy * (A / 2 + 15.0)) for sy in (1, -1)]
    roof = box_at(-Df / 2, Df / 2, -Wf / 2, Wf / 2, top, top + 1.5)
    xs0 = -Df / 2 + 85.0
    cable_slot = box_at(xs0 - 25, xs0 + 25, -125, 125, top - 1, top + 3)
    screw_xy = [(x + sx * F["hole_spacing"] / 2, y + sy * F["hole_spacing"] / 2) for x, y in fan_c for sx in (1, -1) for sy in (1, -1)]
    roof = roof.subtract_all([K.cylinder(F["r_v"], 4.0, segments=64).translate(x, y, top - 1) for x, y in fan_c] + [cable_slot] +
                             [K.cylinder(2.25, 4.0, segments=12).translate(x, y, top - 1) for x, y in screw_xy] +
                             [K.cylinder(5.25, 4.0, segments=20).translate(x, y, top - 1) for x, y in eye_xy])
    brush = K.Solid.union_all([box_at(xs0 - 25, xs0 - 1, -125, 125, top, top + 1.5), box_at(xs0 + 1, xs0 + 25, -125, 125, top, top + 1.5)]) - \
        K.Solid.union_all([box_at(xs0 - 26 + 0.0, xs0 - 1.5, y - 0.4, y + 0.4, top - 1, top + 3) for y in np.arange(-120, 121, 6.0)] +
                          [box_at(xs0 + 1.5, xs0 + 26, y - 0.4, y + 0.4, top - 1, top + 3) for y in np.arange(-117, 121, 6.0)])
    b.add("roof", "Nóc tủ (lỗ quạt + khe đi cáp)", "Roof panel", "cover", [Shape(roof, "paint_primary", 35.0), Shape(brush, "rubber", 35.0)],
          parent_id="frame", required=True, aliases=["nóc tủ", "mái tủ", "khe đi cáp", "chổi cao su", "roof"],
          function="Tôn 1,5 mm, 2 lỗ quạt, khe đi cáp có chổi cao su.", position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.25 * top,
          explode_order=1)
    fan_frames = K.Solid.union_all([(F["frame"] + F["support"]).translate(x, y, top - T) for x, y in fan_c])
    fan_screws = K.Solid.union_all([K.cylinder(3.8, 2.5, segments=16).translate(x, y, top + 1.5) + K.cylinder(1.9, 12.0, segments=10).translate(x, y, top - 10.5)
                                    for x, y in screw_xy])
    b.add("roof_fans", f"Quạt nóc {fs} mm (2)", "Roof fans", "fan_frame",
          [Shape(fan_frames, "plastic_black", 35.0), Shape(K.Solid.union_all([F["label"].translate(x, y, top - T) for x, y in fan_c]), "label_white", 35.0),
           Shape(fan_screws, "steel_black_oxide", 35.0)], parent_id="roof", required=True,
          aliases=["quạt tủ", "quạt nóc", "quạt hút", "fan"], function=f"2 quạt {fs} mm hút gió nóng ra nóc.", position_tag="top",
          explode_dir=(0, 0, -1), explode_distance=0.12 * top, explode_order=2)
    for k, (x, y) in enumerate(fan_c, 1):                              # mỗi cánh một bộ phận: quay quanh trục riêng
        b.add(f"fan_rotor_{k}", f"Cánh quạt nóc {k}", f"Roof fan impeller {k}", "rotor",
              Shape(F["rotor"].translate(x, y, top - T), "plastic_black", 35.0), parent_id="roof_fans",
              aliases=["cánh quạt"], function="Cánh 7 lá quay quanh trục đứng.", position_tag="top", joint_axis=(0, 0, 1),
              pivot=(x, y, top - T / 2), explode_dir=(0, 0, -1), explode_distance=0.2 * top, explode_order=3)
    eyes = []
    for x, y in eye_xy:
        eyes.append(K.cylinder(12.0, 4.0, segments=24).translate(x, y, top + 1.5) + K.cylinder(5.0, 11.5, segments=16).translate(x, y, top - 6.0) +
                    K.torus(15.0, 4.0, segments=32, tube_segments=12).rotate(90, 0, 0).translate(x, y, top + 5.5 + 18.0) +
                    K.cylinder(8.5, 6.0, segments=6).translate(x, y, top - 1.5 - 6.0))
    b.add("lifting_eyes", "Bu lông vòng M10 (4)", "Lifting eye bolts", "bolt", Shape(K.Solid.union_all(eyes), "steel_zinc", 35.0), parent_id="roof",
          aliases=["bu lông vòng", "tai cẩu", "eye bolt"], function="4 bu lông vòng M10 để cẩu tủ, siết vào khung đỉnh.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.35 * top, explode_order=1)

    # ---------- bánh xe + chân tăng chỉnh
    cm, cw, fm, fp = [], [], [], []
    for sx in (1, -1):
        for sy in (1, -1):
            yb = sy * (Wf / 2 - 20)
            m_, w_ = caster(sx * (Df / 2 - 60), yb, z0)
            cm.append(m_)
            cw.append(w_)
            r_, p_ = level_foot(sx * (Df / 2 - 125), yb, z0)
            fm.append(r_)
            fp.append(p_)
    b.add("casters", "Bánh xe xoay Ø70 (4)", "Swivel casters", "caster", [Shape(K.Solid.union_all(cm), "steel_zinc", 35.0), Shape(K.Solid.union_all(cw), "rubber", 35.0)],
          parent_id="frame", required=True, aliases=["bánh xe", "bánh xe tủ", "caster"], function="4 bánh xe xoay Ø70 để di chuyển tủ.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=150.0, explode_order=2)
    b.add("feet", "Chân tăng chỉnh M12 (4)", "Levelling feet", "foot", [Shape(K.Solid.union_all(fp), "rubber", 35.0), Shape(K.Solid.union_all(fm), "steel_zinc", 35.0)],
          parent_id="frame", required=True, aliases=["chân tủ", "chân tăng chỉnh", "chân đế", "levelling feet"], function="Chân ren M12 đế cao su để cố định tủ.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=220.0, explode_order=2)

    # ---------- thiết bị
    layout: list[tuple[str, int, int]] = []
    if equipment:
        top_stack = [("patch", 1), ("cable_mgr", 1), ("switch", 1)] if n >= 8 else [("patch", 1), ("switch", 1)]
        uu = n
        for kind, s in top_stack:
            layout.append((kind, uu - s + 1, s))
            uu -= s
        lo_u = 1
        if n >= 8:
            layout.append(("ups", 1, 2))
            lo_u = 3
        for kind, s in [("server1u", 1), ("server1u", 1), ("server2u", 2)] * 12:
            used = sum(q[2] for q in layout)
            if lo_u + s - 1 >= uu or used + s > 0.75 * n:              # chừa ≥ 1U trống dưới cụm mạng
                break
            layout.append((kind, lo_u, s))
            lo_u += s
        max_depth = x_f - (-Df / 2 + 30.0)
        for kind, u, s in sorted(layout, key=lambda q: q[1]):
            dep = min(KIND_DEPTH[kind], max_depth)
            g = device(kind, u, s, x_f, z_u0, dep)
            plate_mat = "aluminum" if kind in ("server1u", "server2u") else "paint_primary"
            shapes = [Shape(K.Solid.union_all(g["plate"]), plate_mat, 35.0)]
            for key, mat in (("dark", "plastic_black"), ("metal", "steel"), ("accent", "label_white" if kind == "patch" else "paint_accent"),
                             ("led", "led_green"), ("glass", "glass_tinted")):
                if g[key]:
                    shapes.append(Shape(K.Solid.union_all(g[key]), mat, 35.0))
            b.add(f"eq_u{u:02d}_{kind}", f"{KIND_VI[kind]} (U{u}{'–' + str(u + s - 1) if s > 1 else ''})", KIND_EN[kind], "rack_device", shapes,
                  parent_id="rails", required=True, aliases=KIND_ALIASES[kind] + [f"u{u}"],
                  function=f"Thiết bị 19\" {s}U, tai 482,6 mm bắt 4·{s} vít M6 + đai ốc lồng; sâu {dep:.0f} mm.", position_tag="front",
                  explode_dir=(1, 0, 0), explode_distance=0.9 * D + 40.0 * (u % 3), explode_order=2, dimensions={"units": s, "depth": dep})
        # PDU dọc 0U: áp mặt ngoài bụng ray sau bên phải
        ph0, ph1 = z_u0 + 50.0, zt - 50.0
        pdu = box_at(x_b + 2.0, x_b + 50.0, -295.0, -250.0, ph0, ph1)
        n_out = max(2, int((ph1 - ph0 - 120.0) / 45.0))
        outs = [box_at(x_b + 1.0, x_b + 10.0, -279.0, -266.0, z - 6.0, z + 6.0) for z in np.linspace(ph0 + 80.0, ph1 - 40.0, n_out)]
        pins = [box_at(x_b + 7.0, x_b + 10.0, -279.0, -266.0, z - 6.0, z + 6.0) for z in np.linspace(ph0 + 80.0, ph1 - 40.0, n_out)]
        breaker_ = box_at(x_b + 0.5, x_b + 2.0, -284.0, -261.0, ph0 + 15.0, ph0 + 45.0)
        b.add("pdu", f"Thanh PDU dọc {n_out} ổ C13", "Vertical PDU", "rack_device",
              [Shape(pdu.subtract_all(outs), "aluminum_dark", 35.0), Shape(K.Solid.union_all(pins), "plastic_black", 35.0), Shape(breaker_, "paint_accent", 35.0)],
              parent_id="rails", required=True, aliases=["pdu", "ổ cắm tủ rack", "thanh nguồn", "ổ điện"],
              function=f"PDU 0U {n_out} ổ IEC C13, aptomat bảo vệ, bắt vào bụng ray sau.", position_tag="rear",
              explode_dir=(-1, 0, 0), explode_distance=0.7 * D, explode_order=2)
    b.note_stage(1, "Mở cửa trước/sau, tháo hông, nóc")
    b.note_stage(2, "Kéo thiết bị ra phía trước, tháo PDU, quạt, bánh xe")
    b.note_stage(3, "Tháo cánh quạt")
    b.note_stage(4, "Tháo ray 19\"")
    b.place_on_ground(center_xy=True)
    b.metadata.update({
        "rack_units": n, "u_mm": U, "panel_width_mm": PW, "hole_spacing_mm": HS, "opening_mm": OP, "square_hole_mm": SQ,
        "width_mm": W, "depth_mm": D, "height_mm": top + 1.5, "mounting_depth_mm": x_f - x_b, "fan_mm": fs,
        "equipment": [{"id": f"eq_u{u:02d}_{k}", "kind": k, "u": u, "units": s} for k, u, s in sorted(layout, key=lambda q: q[1])],
        "standard": "EIA-310-E / IEC 60297-3-100: 19\" = 482,6 mm, 1U = 44,45 mm, lỗ 15,875/15,875/12,7, khoảng tâm 465,1 mm",
        "strict_overlap": True, "contacts": [],
    })
    return b.build()
