"""Khối dựng linh kiện cơ khí tiêu chuẩn dùng chung cho các mẫu kỹ thuật (hệ X trước, Y trái, Z lên; mm).

Mọi kích thước lấy từ nexa/three_d/standards.py (ISO 15, NEMA ICS 16, ISO 606, EN 1092-1, ASME B16.9, catalogue
HIWIN/TBI/Gates…). Hàm trả khối đặt tại gốc theo quy ước ghi trong docstring để template chỉ việc dời/xoay.
Chỗ lắp ghép dựng bằng số đo thật: lỗ = đường kính trục (tiếp xúc, không xuyên), ốc đi qua lỗ khoét bằng chính thân ốc.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import manifold3d as m3d
import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.fasteners import socket_dimensions
from nexa.three_d.spec import iso_or_scaled

TAU = 2 * math.pi


def tech_materials(spec: Any, primary: str = "#c4c8cc", secondary: str = "#2b2e33", accent: str = "#22d3ee") -> dict:
    """Bộ vật liệu chuẩn + vật liệu kỹ thuật (thép ổ lăn đánh bóng, gang, nhôm đúc, PTFE, đồng, sơn công nghiệp…)."""
    style = spec.style or {}
    mats = M.object_library(M.color_from_name(style.get("primary_color"), primary),
                            M.color_from_name(style.get("secondary_color"), secondary),
                            M.color_from_name(style.get("accent_color"), accent))
    extra = [
        M.material("bearing_steel", "metal", "#cfd3d8", 1.0, 0.13, name="Thép ổ lăn 100Cr6 đánh bóng"),
        M.material("cage_steel", "metal", "#b89a62", 0.9, 0.35, name="Thép dập phủ phosphat (vòng cách)"),
        M.material("cast_iron", "paint", "#3d4b5c", 0.2, 0.62, name="Gang đúc sơn epoxy"),
        M.material("cast_aluminum", "metal", "#b9bdc2", 1.0, 0.45, name="Nhôm đúc"),
        M.material("ptfe", "plastic", "#f1efe8", 0.0, 0.5, name="PTFE (Teflon)"),
        M.material("nbr", "rubber", "#141414", 0.0, 0.8, name="Cao su NBR"),
        M.material("polyurethane", "rubber", "#e8b923", 0.0, 0.55, name="Polyurethane (đệm đàn hồi)"),
        M.material("bronze", "metal", "#b0773b", 1.0, 0.36, name="Đồng thanh"),
        M.material("spring_steel", "metal", "#5b6068", 1.0, 0.34, name="Thép lò xo 65Mn phosphat"),
        M.material("chrome", "metal", "#e8eaed", 1.0, 0.07, name="Mạ crôm cứng"),
        M.material("paint_blue", "paint", "#1f5aa6", 0.0, 0.35, clearcoat=0.4, name="Sơn xanh công nghiệp"),
        M.material("paint_orange", "paint", "#e86a1a", 0.0, 0.35, clearcoat=0.4, name="Sơn cam công nghiệp"),
        M.material("paint_gray", "paint", "#8a9099", 0.0, 0.45, name="Sơn xám"),
        M.material("wire_red", "plastic", "#b3131b", 0.0, 0.45, name="Dây điện đỏ"),
        M.material("wire_blue", "plastic", "#1647b8", 0.0, 0.45, name="Dây điện xanh dương"),
        M.material("wire_green", "plastic", "#1c8a3a", 0.0, 0.45, name="Dây điện xanh lá"),
        M.material("wire_black", "plastic", "#161616", 0.0, 0.45, name="Dây điện đen"),
        M.material("nylon_white", "plastic", "#ece8dc", 0.0, 0.5, name="Nhựa nylon trắng (đầu nối)"),
        M.material("label_white", "paper", "#f3f3ef", 0.0, 0.6, name="Nhãn in"),
        M.material("cable_black", "rubber", "#151619", 0.0, 0.6, name="Vỏ cáp PUR đen"),
        M.material("plastic_yellow", "plastic", "#f2c200", 0.0, 0.45, name="Nhựa vàng an toàn"),
        M.material("cable_orange", "rubber", "#e8751a", 0.0, 0.6, name="Vỏ cáp cam (servo)"),
    ]
    for m in extra:
        mats[m.id] = m
    for mid, (tex, strength) in {"bearing_steel": ("brushed_normal", 0.12), "cast_iron": ("paint_normal", 0.3),
                                 "cast_aluminum": ("plastic_normal", 0.5), "paint_blue": ("paint_normal", 0.25),
                                 "paint_orange": ("paint_normal", 0.25), "paint_gray": ("paint_normal", 0.3),
                                 "nbr": ("rubber_normal", 0.35), "spring_steel": ("brushed_normal", 0.25)}.items():
        mats[mid].textures["normal"] = f"textures/{tex}.png"
        mats[mid].normal_scale = strength
    return mats


# ------------------------------------------------------------------ 2D (CrossSection) tiện ích
def cs(polys, positive: bool = True) -> m3d.CrossSection:
    if isinstance(polys, np.ndarray) and polys.ndim == 2:
        polys = [polys]
    rule = m3d.FillRule.Positive if positive else m3d.FillRule.EvenOdd
    return m3d.CrossSection([np.ascontiguousarray(P.ensure_ccw(p), dtype=np.float64) for p in polys], rule)


def cs_union(items: Sequence[m3d.CrossSection]) -> m3d.CrossSection:
    out = None
    for c in items:
        out = c if out is None else out + c
    return out if out is not None else m3d.CrossSection()


def extrude_cs(section: m3d.CrossSection, height: float, center: bool = False) -> K.Solid:
    s = K.Solid(m3d.Manifold.extrude(section, float(height)))
    return s.translate(0, 0, -height / 2) if center else s


def _rot2(pts: np.ndarray, ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return pts @ np.array([[c, s], [-s, c]])


# ------------------------------------------------------------------ ốc vít cho assembly (thân trơn, ít tam giác)
def _hex_prism(s: float, h: float) -> K.Solid:
    e = s / math.cos(math.radians(30))
    return K.extrude(P.circle(e / 2, 6, start=math.radians(30)), h)


def _hex_chamfered(s: float, h: float, both: bool = False) -> K.Solid:
    e = s / math.cos(math.radians(30))
    R, rt = e / 2 + 0.3, 0.475 * s
    dz = (R - rt) * math.tan(math.radians(30))
    prof = [(0.0, 0.0)] + ([(rt, 0.0), (R, dz)] if both else [(R, 0.0)]) + [(R, h - dz), (rt, h), (0.0, h)]
    return _hex_prism(s, h) & K.revolve(prof, segments=24)


def hex_bolt(d: float, length: float) -> K.Solid:
    """Bu-lông lục giác ISO 4017 (thân trơn): mặt tựa đầu ở z = 0, đầu ở z ∈ [0, k], thân z ∈ [−length, 0]."""
    iso = iso_or_scaled(d)
    head = _hex_chamfered(iso["s"], iso["k"])
    c = 0.12 * d
    shank = K.revolve([(0, -length), (d / 2 - c, -length), (d / 2, -length + c), (d / 2, 0.02), (0, 0.02)], segments=16)
    return head + shank


def hex_nut(d: float) -> K.Solid:
    """Đai ốc ISO 4032: mặt tựa ở z = 0, z ∈ [0, m], lỗ = d (lồng khít thân bu-lông)."""
    iso = iso_or_scaled(d)
    return _hex_chamfered(iso["s"], iso["m"], both=True) - K.cylinder(d / 2, iso["m"] * 3, segments=16).translate(0, 0, -iso["m"])


def flat_washer(d: float) -> K.Solid:
    """Vòng đệm ISO 7089: z ∈ [0, h]."""
    iso = iso_or_scaled(d)
    return K.cylinder(iso["w2"] / 2, iso["wh"], segments=24) - K.cylinder(iso["w1"] / 2, iso["wh"] * 3, segments=32).translate(0, 0, -iso["wh"])


def socket_screw(d: float, length: float) -> K.Solid:
    """Vít đầu trụ lục giác chìm ISO 4762 (thân trơn): mặt tựa đầu z = 0, đầu z ∈ [0, d], thân z ∈ [−length, 0]."""
    from nexa.three_d.geometry.fasteners import socket_screw as shared_socket_screw
    return shared_socket_screw(d, length)


def orient(solid: K.Solid, origin: Sequence[float], direction: Sequence[float]) -> K.Solid:
    """Đặt khối dựng dọc +Z tại `origin`, trục +Z hướng theo `direction`."""
    return solid.align_z(np.asarray(direction, float), np.asarray(origin, float))


def bolt_joint(points: Sequence[Sequence[float]], normal: Sequence[float], d: float, grip: float,
               washers: bool = True) -> tuple[K.Solid, K.Solid, K.Solid]:
    """Mối ghép bu-lông–đai ốc xuyên qua bề dày `grip`: đầu tựa tại mỗi điểm (mặt có pháp tuyến `normal`), đai ốc ở
    mặt đối diện. Trả (bu-lông + vòng đệm đầu, đai ốc + vòng đệm phía đai ốc, khối thân để khoét lỗ các tấm)."""
    n = np.asarray(normal, float) / np.linalg.norm(normal)
    iso = iso_or_scaled(d)
    wh = iso["wh"] if washers else 0.0
    length = math.ceil((grip + 2 * wh + iso["m"] + 0.6 * d) / 5.0) * 5.0
    bolts, nuts, cores = [], [], []
    for p in points:
        p = np.asarray(p, float)
        head_base = p + n * wh
        bolts.append(orient(hex_bolt(d, length), head_base, n))
        cores.append(orient(K.cylinder(d / 2, grip + 2 * wh + 0.02, segments=16), p - n * (grip + wh + 0.01), n))
        if washers:
            bolts.append(orient(flat_washer(d), p, n))                  # vòng đệm dưới đầu bu-lông đi cùng bu-lông
            nuts.append(orient(flat_washer(d), p - n * grip, -n))
        nuts.append(orient(hex_nut(d), p - n * (grip + wh), -n))
    return K.Solid.union_all(bolts), K.Solid.union_all(nuts), K.Solid.union_all(cores)


# ------------------------------------------------------------------ ổ bi rãnh sâu ISO 15
def bearing_solids(code: str, seal: str = "open", cage: str = "steel") -> dict:
    """Ổ bi rãnh sâu theo mã ISO 15 (vd '6204'): trục Z, tâm ở gốc, bề rộng z ∈ [−B/2, B/2].

    Rãnh lăn bán kính 0,52·Dw (độ ôm 52 % — giá trị điển hình), bi chạm đáy rãnh cả hai vòng. Vòng cách thép dập
    (hai nửa có ổ cầu + đinh tán) hoặc nhựa PA66 kiểu gài. Phớt 2RS (cao su, môi chạm vòng trong) hoặc nắp ZZ (thép,
    có khe hở) nằm trong rãnh của vòng ngoài. Trả dict khối + thông số."""
    d, D, B, rs = S.BEARINGS[code]
    z, dw, dm = S.bearing_balls(code)
    rc, rb = dm / 2, dw / 2
    land_i, land_o = rc - 0.36 * dw, rc + 0.36 * dw
    seg = int(np.clip(64 + D * 0.9, 72, 176)) // 8 * 8
    ch = min(rs * 0.8, B * 0.1)
    inner = K.revolve(P.fillet_polygon([(d / 2, -B / 2), (land_i, -B / 2), (land_i, B / 2), (d / 2, B / 2)],
                                       [ch, ch * 0.5, ch * 0.5, ch], 4), segments=seg)
    inner = inner - K.torus(rc + 0.02 * dw, 0.52 * dw, segments=seg, tube_segments=40)
    outer = K.revolve(P.fillet_polygon([(land_o, -B / 2), (D / 2, -B / 2), (D / 2, B / 2), (land_o, B / 2)],
                                       [ch * 0.5, ch, ch, ch * 0.5], 4), segments=seg)
    outer = outer - K.torus(rc - 0.02 * dw, 0.52 * dw, segments=seg, tube_segments=40)
    angles = [TAU * k / z for k in range(z)]
    ball = K.sphere(rb, 28)
    balls = [ball.translate(rc * math.cos(a), rc * math.sin(a), 0) for a in angles]
    gap = 0.045 + 0.002 * dw                           # khe ổ vòng cách (ổ cầu 48 cạnh: sai số lưới < 0,015 mm)
    rp = rb + gap
    st = min(0.9, 0.08 * B + 0.2)                       # bề dày phớt/nắp
    z_seal = B / 2 - 0.25 - st
    zlim = min(rb * 0.8, z_seal - 0.15)
    if cage == "polyamide":
        body = K.revolve([(rc - 0.27 * dw, -zlim), (rc + 0.27 * dw, -zlim), (rc + 0.27 * dw, zlim * 0.55),
                          (rc - 0.27 * dw, zlim * 0.55)], segments=seg)
        cuts = [K.sphere(rp, 48).translate(rc * math.cos(a), rc * math.sin(a), 0) for a in angles]
        cuts += [K.cylinder(rb * 0.82, zlim * 2, segments=20).translate(rc * math.cos(a), rc * math.sin(a), 0) for a in angles]
        cage_s = body.subtract_all(cuts)
    else:
        t = max(0.25, 0.07 * dw)
        region = K.revolve([(rc - 0.3 * dw, -zlim), (rc + 0.3 * dw, -zlim), (rc + 0.3 * dw, zlim), (rc - 0.3 * dw, zlim)],
                           segments=seg)
        shells = K.Solid.union_all([(K.sphere(rp + t, 32) - K.sphere(rp, 48)).translate(rc * math.cos(a), rc * math.sin(a), 0)
                                    for a in angles])
        web = K.revolve([(rc - 0.24 * dw, -t / 2), (rc + 0.24 * dw, -t / 2), (rc + 0.24 * dw, t / 2), (rc - 0.24 * dw, t / 2)],
                        segments=seg)
        pockets = [K.sphere(rp, 48).translate(rc * math.cos(a), rc * math.sin(a), 0) for a in angles]
        rivets = []
        for a in angles:
            am = a + math.pi / z
            rv = K.cylinder(0.07 * dw, 2.6 * t, segments=10).translate(0, 0, -1.3 * t) + \
                K.sphere(0.12 * dw, 10).scale(1, 1, 0.5).translate(0, 0, 1.3 * t) + \
                K.sphere(0.12 * dw, 10).scale(1, 1, 0.5).translate(0, 0, -1.3 * t)
            rivets.append(rv.translate(rc * math.cos(am), rc * math.sin(am), 0))
        cage_s = (shells & region) + web.subtract_all(pockets) + K.Solid.union_all(rivets)
        cage_s = cage_s & K.cylinder(land_o - 0.02 * dw, 2 * zlim + 2, segments=seg).translate(0, 0, -zlim - 1)
        cage_s = cage_s - K.cylinder(land_i + 0.02 * dw, 2 * zlim + 4, segments=seg).translate(0, 0, -zlim - 2)
    seals = []
    if seal in ("2RS", "ZZ"):
        r_in = land_i if seal == "2RS" else land_i + 0.12 + 0.01 * dw
        r_out = land_o + 0.55 * (D / 2 - land_o)
        for sgn in (1, -1):
            if seal == "2RS":
                prof = [(r_in, 0), (r_out, 0), (r_out, st), (r_in + 0.35 * (r_out - r_in), st), (r_in, st * 0.55)]
            else:
                prof = [(r_in, 0), (r_out, 0), (r_out, st * 0.7), (r_in + 0.2 * (r_out - r_in), st * 0.7),
                        (r_in, st * 0.7)]
            s_ = K.revolve(prof, segments=seg).translate(0, 0, z_seal)
            seals.append(s_ if sgn > 0 else s_.mirror((0, 0, 1)))
    return {"outer": outer, "inner": inner, "balls": balls, "cage": cage_s, "seals": seals, "d": d, "D": D, "B": B,
            "z": z, "dw": dw, "dm": dm, "land_i": land_i, "land_o": land_o, "angles": angles}


def bearing_solid(code: str, seal: str = "2RS", detail: str = "full") -> tuple[K.Solid, K.Solid | None, K.Solid]:
    """Ổ bi gộp gọn cho assembly lớn: (vòng ngoài + phớt/nắp, bi + vòng cách, vòng trong) — trục Z, tâm ở gốc.
    detail="low" với ổ có phớt/nắp: bỏ bi + vòng cách (bị che kín, không nhìn thấy) để tiết kiệm tam giác."""
    if detail == "low" and seal in ("2RS", "ZZ"):
        d, D, B, rs = S.BEARINGS[code]
        _z, dw, dm = S.bearing_balls(code)
        land_i, land_o = dm / 2 - 0.36 * dw, dm / 2 + 0.36 * dw
        ch = min(rs * 0.8, B * 0.1)
        inner = K.revolve(P.fillet_polygon([(d / 2, -B / 2), (land_i, -B / 2), (land_i, B / 2), (d / 2, B / 2)],
                                           [ch, ch * 0.5, ch * 0.5, ch], 3), segments=64)
        outer = K.revolve(P.fillet_polygon([(land_o, -B / 2), (D / 2, -B / 2), (D / 2, B / 2), (land_o, B / 2)],
                                           [ch * 0.5, ch, ch, ch * 0.5], 3), segments=64)
        st = min(0.9, 0.08 * B + 0.2)
        z_seal = B / 2 - 0.25 - st
        shield = K.revolve([(land_i + 0.15, z_seal), (land_o + 0.2, z_seal), (land_o + 0.2, z_seal + st * 0.7),
                            (land_i + 0.15, z_seal + st * 0.7)], segments=64)
        rings = K.Solid.union_all([outer, shield, shield.mirror((0, 0, 1))])
        return rings, None, inner
    b = bearing_solids(code, seal=seal)
    rings = K.Solid.union_all([b["outer"]] + b["seals"])
    return rings, K.Solid.union_all(b["balls"] + [b["cage"]]), b["inner"]


# ------------------------------------------------------------------ bánh răng trụ thân khai
def spur_gear(m: float, z: int, width: float, bore: float, phase_deg: float = 0.0, hub_d: float = 0.0,
              hub_len: float = 0.0, lighten: bool = True, backlash: float = 0.05) -> K.Solid:
    """Bánh răng trụ răng thẳng (α = 20°): trục Z, z ∈ [−width/2, width/2] (+ moay-ơ phía +Z nếu hub_len > 0).
    phase_deg: xoay quanh trục (răng số 0 nằm ở góc phase). Đỉnh răng vát 0,5m hai mặt."""
    prof = P.involute_gear(m, z, 20.0, backlash=backlash * m, flank_samples=9, root_samples=3, tip_samples=3)
    body = K.extrude(prof, width).translate(0, 0, -width / 2)
    radii = P.gear_radii(m, z)
    ra, c = radii["tip"], 0.5 * m
    seg = int(np.clip(z * 4, 96, 320))
    body = body & K.revolve([(0, -width / 2), (ra - c, -width / 2), (ra + 0.02, -width / 2 + c + 0.02),
                             (ra + 0.02, width / 2 - c - 0.02), (ra - c, width / 2), (0, width / 2)], segments=seg)
    rim = radii["root"] - 1.3 * m
    hub_r = max(hub_d / 2, bore / 2 + 1.8 * m, bore * 0.85)
    if lighten and rim - hub_r > 5 * m and width > 3.5 * m:
        web = max(width * 0.35, 2 * m)
        pocket = K.revolve(P.fillet_polygon([(hub_r, 0), (rim, 0), (rim, (width - web) / 2 + 0.01), (hub_r, (width - web) / 2 + 0.01)],
                                            [0, 0, m * 0.6, m * 0.6], 4), segments=seg)
        body = body - pocket.translate(0, 0, -width / 2 - 0.01) - pocket.mirror((0, 0, 1)).translate(0, 0, width / 2 + 0.01)
        nh = 6 if rim > 12 * m else 4
        rr = (rim - hub_r) * 0.27
        body = body.subtract_all([K.cylinder(rr, width + 2, segments=32).translate((hub_r + rim) / 2 * math.cos(a),
                                                                                  (hub_r + rim) / 2 * math.sin(a), -width / 2 - 1)
                                  for a in np.radians(np.arange(nh) * 360.0 / nh + 30)])
    if hub_len > 0:
        hub = K.revolve(P.fillet_polygon([(bore / 2, width / 2 - 0.5), (hub_r, width / 2 - 0.5), (hub_r, width / 2 + hub_len),
                                          (bore / 2, width / 2 + hub_len)], [0, 0, 0.3 * m, 0], 4), segments=96)
        body = body + hub
    body = body - K.cylinder(bore / 2, width + 2 * hub_len + 4, segments=64).translate(0, 0, -width / 2 - hub_len - 2)
    return body.rotate(0, 0, phase_deg) if phase_deg else body


def mesh_phase(z_driver: int, z_driven: int, angle_deg: float) -> tuple[float, float]:
    """Góc xoay (độ) để hai bánh răng ăn khớp khi tâm bánh bị dẫn nằm theo hướng `angle_deg` từ tâm bánh dẫn:
    bánh dẫn có răng hướng về bánh bị dẫn, bánh bị dẫn có rãnh răng hướng về bánh dẫn."""
    return angle_deg, angle_deg + 180.0 + 180.0 / z_driven


# ------------------------------------------------------------------ động cơ bước NEMA
def nema_stepper(size: int, body_len: float, double_shaft: bool = False) -> dict:
    """Động cơ bước lai (hybrid) theo NEMA ICS 16: mặt lắp (mặt bích) tại z = 0, thân kéo về −Z, trục ra +Z.

    Nắp trước nhôm (gờ định tâm + 4 lỗ ren M3 cỡ 17 / 4 lỗ xuyên tai bích cỡ 23–34), khối lá thép stator có rãnh
    lá ghép, nắp sau nhôm có ụ ổ bi, 4 vít xuyên suốt, trục có mặt vát D. Trả dict khối + vị trí."""
    t = S.NEMA[size]
    F, hs = t["flange"], t["hole_spacing"] / 2
    L = float(body_len)
    cap_t = {17: 8.0, 23: 9.0, 34: 12.0}[size]
    fl_t = {17: cap_t, 23: 5.0, 34: 7.5}[size]
    chf = {17: 3.2, 23: 3.0, 34: 4.0}[size]
    stack_chf = {17: 5.5, 23: 9.5, 34: 13.0}[size]

    def square(side: float, cham: float, h: float, z0: float) -> K.Solid:
        pts = P.chamfer_polygon([(-side / 2, -side / 2), (side / 2, -side / 2), (side / 2, side / 2), (-side / 2, side / 2)], cham)
        return K.extrude(pts, h).translate(0, 0, z0)
    body_side = F - (0.0 if size == 17 else 0.4)
    front = square(F, chf, fl_t, -fl_t)
    if fl_t < cap_t:                                              # cỡ 23/34: tai bích mỏng + thân nắp vát góc lớn phía sau
        front = front + square(body_side, stack_chf, cap_t - fl_t + 0.01, -cap_t)
    pilot = K.revolve(P.fillet_polygon([(0, -0.01), (t["pilot_d"] / 2, -0.01), (t["pilot_d"] / 2, t["pilot_h"]),
                                        (0, t["pilot_h"])], [0, 0, 0.3, 0], 3), segments=96)
    front = front + pilot
    holes = []
    for sx in (1, -1):
        for sy in (1, -1):
            if size == 17:
                holes.append(K.cylinder(t["hole_d"] / 2, 4.5, segments=16).translate(sx * hs, sy * hs, -4.5))
            else:
                holes.append(K.cylinder(t["hole_d"] / 2, fl_t + 0.2, segments=20).translate(sx * hs, sy * hs, -fl_t - 0.1))
    front = front.subtract_all(holes)
    stack_len = L - 2 * cap_t
    z_rear = -L
    stack = square(body_side, stack_chf, stack_len, -cap_t - stack_len)
    from nexa.three_d.generation.templates import details as D
    n_g = max(3, int(stack_len / 1.8))
    zs = [(-cap_t - stack_len) + stack_len * (k + 0.5) / n_g for k in range(n_g)]
    stack = stack - D.panel_lines(stack, [("z", zz) for zz in zs], width=0.35, depth=0.28)
    rear = square(body_side, chf, cap_t, z_rear)
    boss = K.cylinder(t["pilot_d"] * 0.42, 1.2, segments=64).translate(0, 0, z_rear - 1.2)
    rear = rear + boss
    # 4 vít xuyên: đầu chìm trong lỗ bậc ở nắp sau, thân tới nắp trước
    sd = {17: 3.0, 23: 4.0, 34: 5.0}[size]
    screw_pts = [(sx * hs, sy * hs) for sx in (1, -1) for sy in (1, -1)]
    if size != 17:
        screw_pts = [(sx * (hs - 0.2 * hs), sy * (hs - 0.2 * hs)) for sx in (1, -1) for sy in (1, -1)]
    screw_len = L - cap_t * 0.4 - 3.0
    screws, cores = [], []
    for (x, y) in screw_pts:
        rec = 0.6 * sd
        sc = socket_screw(sd, screw_len).rotate(180, 0, 0).translate(x, y, z_rear + rec)
        screws.append(sc)
        # Provide clearance, not two differently tessellated surfaces at the same radius.
        cores.append(K.cylinder(sd / 2 + 0.1, screw_len + 0.02, segments=48).translate(x, y, z_rear + rec - 0.01))
        cores.append(K.cylinder(socket_dimensions(sd)["head_diameter"] / 2 + 0.25,
                                rec + 0.1, segments=48).translate(x, y, z_rear - 0.1))
    # trục: xuyên nắp trước (lỗ ổ bi) — phần trong thân khoét khỏi nắp
    sd_ = t["shaft_d"]
    z_tip = t["shaft_len"]
    z_back = z_rear - 1.2 - 12.0 if double_shaft else z_rear + cap_t * 0.5
    shaft = K.revolve([(0, z_back), (sd_ / 2 - 0.3, z_back), (sd_ / 2, z_back + 0.3), (sd_ / 2, z_tip - 0.4),
                       (sd_ / 2 - 0.4, z_tip), (0, z_tip)], segments=32)
    flat_len = min(15.0, t["shaft_len"] - 4.0)
    shaft = shaft - K.box(sd_, sd_ * 2, flat_len + 1).translate(sd_ / 2 + sd_ / 2 - t["flat"], 0, z_tip - flat_len / 2 + 0.5)
    shaft_core = K.cylinder(sd_ / 2, abs(z_back) + t["pilot_h"] + 2, segments=32).translate(0, 0, z_back - 0.01)
    return {"front": front, "stack": stack, "rear": rear, "screws": K.Solid.union_all(screws),
            "screw_cores": K.Solid.union_all(cores), "shaft": shaft, "shaft_core": shaft_core, "flange": F,
            "hole_spacing": 2 * hs, "cap_t": cap_t, "length": L, "z_rear": z_rear, "side": body_side,
            "table": t}


# ------------------------------------------------------------------ đường dẫn đai/xích (2D, mặt phẳng uv)
def open_belt_path(r1: float, r2: float, C: float, step: float = 1.0) -> tuple[np.ndarray, float, float]:
    """Đường tâm đai hở quanh puly 1 (tâm (0,0), bán kính r1) và puly 2 (tâm (C,0), r2), ngược chiều kim đồng hồ.
    Trả (điểm (N,2), chiều dài, góc β của nhánh thẳng)."""
    beta = math.asin((r2 - r1) / C)
    a_top, a_bot = math.pi / 2 + beta, -(math.pi / 2 + beta)
    pts = []
    n2 = max(24, int(r2 * (math.pi + 2 * beta) / step))
    for a in np.linspace(a_bot, a_top, n2, endpoint=False):              # puly 2, phía phải
        pts.append((C + r2 * math.cos(a), r2 * math.sin(a)))
    top2 = np.array([C + r2 * math.cos(a_top), r2 * math.sin(a_top)])
    top1 = np.array([r1 * math.cos(a_top), r1 * math.sin(a_top)])
    ln = float(np.linalg.norm(top1 - top2))
    for s in np.linspace(0, 1, max(2, int(ln / step)), endpoint=False):
        pts.append(tuple(top2 + (top1 - top2) * s))
    n1 = max(24, int(r1 * (math.pi - 2 * beta) / step))
    for a in np.linspace(a_top, a_bot + TAU, n1, endpoint=False):         # puly 1, phía trái
        pts.append((r1 * math.cos(a), r1 * math.sin(a)))
    bot1 = np.array([r1 * math.cos(a_bot), r1 * math.sin(a_bot)])
    bot2 = np.array([C + r2 * math.cos(a_bot), r2 * math.sin(a_bot)])
    for s in np.linspace(0, 1, max(2, int(ln / step)), endpoint=False):
        pts.append(tuple(bot1 + (bot2 - bot1) * s))
    length = 2 * ln + r1 * (math.pi - 2 * beta) + r2 * (math.pi + 2 * beta)
    return np.asarray(pts, float), length, beta


def belt_length(r1: float, r2: float, C: float) -> float:
    beta = math.asin((r2 - r1) / C)
    return 2 * math.sqrt(C * C - (r2 - r1) ** 2) + r1 * (math.pi - 2 * beta) + r2 * (math.pi + 2 * beta)


def solve_center(r1: float, r2: float, length: float, c0: float) -> float:
    """Khoảng cách tâm cho chiều dài đai cho trước (chia đôi)."""
    lo, hi = abs(r2 - r1) + 1e-3, max(c0 * 4, length)
    for _ in range(80):
        mid = (lo + hi) / 2
        if belt_length(r1, r2, mid) < length:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def point_on_path(path: np.ndarray, s: float) -> tuple[np.ndarray, np.ndarray]:
    """Điểm + tiếp tuyến trên đường kín tại độ dài cung s."""
    closed = np.vstack([path, path[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    s = s % cum[-1]
    i = int(np.searchsorted(cum, s, side="right") - 1)
    i = min(i, len(seg) - 1)
    f = (s - cum[i]) / max(seg[i], 1e-12)
    p = closed[i] + (closed[i + 1] - closed[i]) * f
    t = (closed[i + 1] - closed[i]) / max(seg[i], 1e-12)
    return p, t


def path_length(path: np.ndarray) -> float:
    closed = np.vstack([path, path[:1]])
    return float(np.linalg.norm(np.diff(closed, axis=0), axis=1).sum())


def plane_xz(solid_xy: K.Solid) -> K.Solid:
    """Khối dựng trong mặt XY (đùn theo Z) → quay sang mặt XZ (đùn theo −Y... trục puly theo Y)."""
    return solid_xy.rotate(90, 0, 0)


# ------------------------------------------------------------------ puly đai răng
def groove_radius(belt: str) -> float:
    """Bán kính đáy rãnh puly (≈ 0,3·bước: GT2 0,6 mm; HTD 5M 1,5 mm)."""
    return 0.3 * S.BELTS[belt]["pitch"]


def belt_tooth_section(belt: str) -> np.ndarray:
    """Răng đai (mặt cắt cục bộ): u tiếp tuyến, v hướng vào tâm puly tính từ mặt trong lưng đai (v = 0)."""
    b = S.BELTS[belt]
    w = 2 * groove_radius(belt) * 0.84
    h = b["tooth_h"]
    r = min(w / 2 * 0.98, h * 0.9)
    pts = P.fillet_polygon([(-w / 2, -0.05), (w / 2, -0.05), (w / 2, h), (-w / 2, h)], [0, 0, r, r], 6)
    return np.asarray(pts, float)


def timing_pulley_section(teeth: int, belt: str) -> tuple[m3d.CrossSection, float, float]:
    """Mặt cắt puly đai răng GT2/HTD: vòng đỉnh OD = PD − 2·PLD, rãnh răng bán kính đáy ≈ 0,8·chiều cao răng.
    Trả (mặt cắt, bán kính chia r_p, bán kính đỉnh r_o). Răng số 0 (rãnh) ở góc 0."""
    b = S.BELTS[belt]
    p = b["pitch"]
    rp = teeth * p / TAU
    ro = rp - b["pld"]
    depth = b["tooth_h"] * 1.08
    rg = groove_radius(belt)
    grooves = []
    for k in range(teeth):
        a = TAU * k / teeth
        # rãnh cục bộ: u tiếp tuyến, v hướng tâm ra ngoài; đáy bán kính rg
        arc = [(rg * math.cos(t_), -depth + rg + rg * math.sin(t_)) for t_ in np.linspace(math.pi, TAU, 12)]
        loc = [(-rg - 0.05 * p, 0.4)] + arc + [(rg + 0.05 * p, 0.4)]
        loc = np.asarray(loc, float)
        pts = np.column_stack([(ro + loc[:, 1]) * math.cos(a) - loc[:, 0] * math.sin(a),
                               (ro + loc[:, 1]) * math.sin(a) + loc[:, 0] * math.cos(a)])
        grooves.append(cs(pts))
    disk = cs(P.circle(ro, max(96, teeth * 8)))
    return disk - cs_union(grooves), rp, ro


def timing_pulley(teeth: int, belt: str, width: float, bore: float, hub_len: float = 0.0) -> K.Solid:
    """Puly đai răng có hai gờ chặn và moay-ơ + 2 lỗ vít hãm: trục Z, vùng răng z ∈ [−width/2, width/2]."""
    sec, rp, ro = timing_pulley_section(teeth, belt)
    body = extrude_cs(sec, width, center=True)
    flange_r = ro + 1.2 * S.BELTS[belt]["total_h"] + 0.6
    ft = max(0.8, 0.12 * width)
    for sgn in (1, -1):
        fl = K.revolve(P.fillet_polygon([(0, 0), (flange_r, 0), (flange_r, ft * 0.6), (ro, ft), (0, ft)], [0, 0.2, 0.3, 0, 0], 3),
                       segments=96)
        body = body + (fl.translate(0, 0, width / 2) if sgn > 0 else fl.mirror((0, 0, 1)).translate(0, 0, -width / 2))
    if hub_len > 0:
        hub_r = max(bore * 1.1, min(ro * 0.9, bore / 2 + 5.0))
        hub = K.revolve(P.fillet_polygon([(0, width / 2 + ft - 0.01), (hub_r, width / 2 + ft - 0.01), (hub_r, width / 2 + ft + hub_len),
                                          (0, width / 2 + ft + hub_len)], [0, 0, 0.4, 0], 3), segments=64)
        body = body + hub
        zc = width / 2 + ft + hub_len / 2
        for ang in (0, 90):
            body = body - K.cylinder(1.5, hub_r + 1, segments=12).rotate(0, 90, 0).rotate(0, 0, ang).translate(0, 0, zc)
    return body - K.cylinder(bore / 2, width + 2 * hub_len + 20, segments=48).translate(0, 0, -width - 10)


def vbelt_pulley(pitch_d: float, section: str, grooves: int, bore: float) -> tuple[K.Solid, float]:
    """Puly đai thang (ISO 4183): rãnh 38°, bề rộng chuẩn lp tại đường kính chuẩn. Trục Z. Trả (khối, bề rộng)."""
    v = S.VBELTS[section]
    lp, h = v["lp"], v["height"]
    e = lp * 1.4                                                   # bước rãnh
    width = e * (grooves - 1) + 2 * lp * 0.95
    r_o = pitch_d / 2 + 0.28 * h
    r_root = pitch_d / 2 - 0.9 * h
    tan19 = math.tan(math.radians(19))
    prof = [(0, -width / 2), (r_o, -width / 2)]
    for g in range(grooves):
        zc = -width / 2 + lp * 0.95 + g * e
        wt = lp / 2 + (r_o - pitch_d / 2) * tan19
        wb = lp / 2 - (pitch_d / 2 - r_root) * tan19
        prof += [(r_o, zc - wt), (r_root, zc - wb), (r_root, zc + wb), (r_o, zc + wt)]
    prof += [(r_o, width / 2), (0, width / 2)]
    body = K.revolve(prof, segments=128)
    rim_in = r_root - max(4.0, 0.08 * pitch_d)
    hub_r = max(bore * 0.95, bore / 2 + 8)
    if rim_in - hub_r > 12:
        web = width * 0.35
        pocket = K.revolve([(hub_r, -width / 2 - 1), (rim_in, -width / 2 - 1), (rim_in, -web / 2), (hub_r, -web / 2)], segments=128)
        body = body - pocket - pocket.mirror((0, 0, 1))
        body = body.subtract_all([K.cylinder((rim_in - hub_r) * 0.3, width + 2, segments=32).translate(
            (hub_r + rim_in) / 2 * math.cos(a), (hub_r + rim_in) / 2 * math.sin(a), -width / 2 - 1) for a in np.radians(range(0, 360, 60))])
    return body - K.cylinder(bore / 2, width + 4, segments=48).translate(0, 0, -width / 2 - 2), width


# ------------------------------------------------------------------ xích con lăn ISO 606 + đĩa xích
def sprocket(teeth: int, chain: str, bore: float, hub: bool = True) -> tuple[K.Solid, float]:
    """Đĩa xích (ISO 606): đường kính chia PD = p / sin(180°/z), rãnh chỗ ngồi con lăn bán kính nhỏ nhất theo
    ISO 606 r_i,min = 0,505·d1 (con lăn tì đáy rãnh), đường kính đỉnh da ≈ p(0,54 + cot(180°/z)), bề rộng răng
    0,93·b1, vát răng.
    Trục Z, răng z ∈ [−bf/2, bf/2]; chỗ ngồi con lăn số 0 ở góc 0. Trả (khối, bán kính chia)."""
    c = S.CHAINS[chain]
    p, d1, b1 = c["pitch"], c["roller"], c["inner_w"]
    R = p / (2 * math.sin(math.pi / teeth))
    ri = 0.505 * d1
    ra = p * (0.54 + 1 / math.tan(math.pi / teeth)) / 2
    bf = 0.93 * b1 if p <= 12.7 else 0.95 * b1
    gaps = []
    for k in range(teeth):
        a = TAU * k / teeth
        cx, cy = R * math.cos(a), R * math.sin(a)
        seat = P.circle(ri, 24, center=(cx, cy))
        out_r = R + 0.9 * d1
        relief = P.circle(ri * 1.55, 24, center=(out_r * math.cos(a), out_r * math.sin(a)))
        gaps.append(m3d.CrossSection.batch_hull([cs(seat), cs(relief)]))
    sec = cs(P.circle(ra, max(128, teeth * 10))) - cs_union(gaps)
    body = extrude_cs(sec, bf, center=True)
    ch = 0.12 * p
    body = body & K.revolve([(0, -bf / 2), (ra - ch * 1.6, -bf / 2), (ra + 0.1, -bf / 2 + ch), (ra + 0.1, bf / 2 - ch),
                             (ra - ch * 1.6, bf / 2), (0, bf / 2)], segments=max(128, teeth * 8))
    if hub:
        hub_r = min(R - d1 * 0.9, max(bore * 0.95, bore / 2 + 0.5 * p))
        hub_l = max(p * 1.2, bore * 0.9)
        body = body + K.revolve(P.fillet_polygon([(bore / 2, -bf / 2 + 0.01), (hub_r, -bf / 2 + 0.01), (hub_r, -bf / 2 - hub_l),
                                                  (bore / 2, -bf / 2 - hub_l)], [0, 0.6, 0.6, 0], 3), segments=96)
        zc = -bf / 2 - hub_l / 2
        body = body - K.cylinder(0.14 * bore + 1.5, hub_r + 2, segments=14).rotate(0, 90, 0).translate(0, 0, zc)
    rim = R - 0.75 * d1 - 0.4 * p
    if hub and rim > bore / 2 + 1.5 * p + 12:
        hub_r = max(bore * 0.95, bore / 2 + 0.5 * p)
        nh = 5 if teeth < 40 else 6
        rr = (rim - hub_r) * 0.33
        body = body.subtract_all([K.cylinder(rr, bf + 2, segments=32).translate((hub_r + rim) / 2 * math.cos(a), (hub_r + rim) / 2 * math.sin(a),
                                                                                 -bf / 2 - 1) for a in np.radians(np.arange(nh) * 360 / nh + 36)])
    return body - K.cylinder(bore / 2, 6 * p + bf, segments=48).translate(0, 0, -3 * p - bf / 2), R


def chain_rollers(R1: float, R2: float, C: float, p: float) -> list[np.ndarray]:
    """Tâm con lăn (2D) của xích quanh đĩa 1 (tâm 0,0) và đĩa 2 (tâm C,0): nhánh trên căng thẳng (dài đúng số
    nguyên bước), cung ôm theo chỗ ngồi răng, nhánh dưới chùng võng theo cung tròn đủ số bước nguyên.
    Số mắt xích luôn chẵn (không cần mắt nối cong). C phải đã được hiệu chỉnh bằng `chain_center`."""
    beta = math.asin((R2 - R1) / C)
    a_top, a_bot = math.pi / 2 + beta, -(math.pi / 2 + beta)
    step1, step2 = TAU / round(math.pi / math.asin(p / (2 * R1))), TAU / round(math.pi / math.asin(p / (2 * R2)))
    top1 = np.array([R1 * math.cos(a_top), R1 * math.sin(a_top)])
    top2 = np.array([C + R2 * math.cos(a_top), R2 * math.sin(a_top)])
    n_top = int(round(np.linalg.norm(top2 - top1) / p))
    pts: list[np.ndarray] = [top1 + (top2 - top1) * k / n_top for k in range(n_top)]   # nhánh trên: đĩa 1 → đĩa 2
    k2 = 0                                                         # cung ôm đĩa 2, chiều kim đồng hồ (góc giảm)
    while a_top - k2 * step2 >= a_bot - 1e-9:
        a = a_top - k2 * step2
        pts.append(np.array([C + R2 * math.cos(a), R2 * math.sin(a)]))
        k2 += 1
    e_pt = pts[-1]
    seats1 = []                                                    # chỗ ngồi đĩa 1 từ tiếp điểm trên đi ngược về tiếp điểm dưới
    k1 = 1
    while a_top + k1 * step1 <= a_bot + TAU + 1e-9:
        a = a_top + k1 * step1
        seats1.append(np.array([R1 * math.cos(a), R1 * math.sin(a)]))
        k1 += 1
    wrap1 = seats1[::-1]                                           # theo chiều đi: từ dưới lên trên
    d_pt = wrap1[0] if wrap1 else top1
    chord = float(np.linalg.norm(d_pt - e_pt))                     # nhánh dưới chùng: e_pt (đĩa 2) → d_pt (đĩa 1)
    n_bot = int(math.ceil(chord / p - 1e-6))
    if (len(pts) + (n_bot - 1) + len(wrap1)) % 2:
        n_bot += 1
    span = []
    if abs(n_bot * p - chord) < 1e-6:
        span = [e_pt + (d_pt - e_pt) * k / n_bot for k in range(1, n_bot)]
    else:
        lo = p / (2 * math.sin(math.pi / (2 * n_bot)))             # ρ nhỏ nhất: cung nửa vòng tròn
        hi = 1e7 * p
        for _ in range(200):                                       # 2ρ·sin(n·asin(p/2ρ)) = chord
            rho = math.sqrt(lo * hi)
            f = 2 * rho * math.sin(n_bot * math.asin(p / (2 * rho)))
            if f > chord:
                hi = rho
            else:
                lo = rho
        half = n_bot * math.asin(p / (2 * rho))
        mid = (e_pt + d_pt) / 2
        u = (d_pt - e_pt) / chord
        down = np.array([u[1], -u[0]])
        if down[1] > 0:
            down = -down
        ctr = mid - down * rho * math.cos(half)
        a0 = math.atan2(e_pt[1] - ctr[1], e_pt[0] - ctr[0])
        a1 = math.atan2(d_pt[1] - ctr[1], d_pt[0] - ctr[0])
        sweep = (a1 - a0 + math.pi) % TAU - math.pi
        span = [ctr + rho * np.array([math.cos(a0 + sweep * k / n_bot), math.sin(a0 + sweep * k / n_bot)]) for k in range(1, n_bot)]
    return pts + span + wrap1


def chain_center(R1: float, R2: float, C0: float, p: float) -> float:
    """Hiệu chỉnh khoảng cách tâm để nhánh căng dài đúng số nguyên bước xích (thay đổi ≤ p/2)."""
    def tl(C: float) -> float:
        return math.sqrt(C * C - (R2 - R1) ** 2)
    n = max(2, round(tl(C0) / p))
    target = n * p
    return math.sqrt(target ** 2 + (R2 - R1) ** 2)


def roller_chain(centers: Sequence[np.ndarray], chain: str) -> tuple[K.Solid, K.Solid]:
    """Xích con lăn từ danh sách tâm con lăn (mặt phẳng XY, trục con lăn theo Z): má trong/ngoài eo lưng, con lăn,
    chốt tán đầu. Mắt chẵn = mắt trong (má trong + con lăn), mắt lẻ = mắt ngoài (má ngoài + chốt). Trả (má, con lăn+chốt)."""
    c = S.CHAINS[chain]
    p, d1, b1, d2, h2, t = c["pitch"], c["roller"], c["inner_w"], c["pin"], c["plate_h"], c["plate_t"]
    n = len(centers)

    def plate_shape(hh: float) -> K.Solid:
        pl = m3d.CrossSection.batch_hull([cs(P.circle(hh / 2, 20, center=(0, 0))), cs(P.circle(hh / 2, 20, center=(p, 0)))])
        waist = cs(P.circle(p * 0.55, 32, center=(p / 2, hh / 2 + p * 0.55 - hh * 0.08))) + \
            cs(P.circle(p * 0.55, 32, center=(p / 2, -hh / 2 - p * 0.55 + hh * 0.08)))
        return extrude_cs(pl - waist, t)
    shapes = {"in": plate_shape(h2 * 0.92), "out": plate_shape(h2)}

    def plate(a: np.ndarray, b: np.ndarray, kind: str) -> K.Solid:
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        return shapes[kind].rotate(0, 0, ang).translate(a[0], a[1], 0)
    plates, rollers = [], []
    roller = K.cylinder(d1 / 2, b1 - 0.02, segments=20).translate(0, 0, -(b1 - 0.02) / 2)
    pin_len = b1 + 4 * t + 1.2 * t
    pin = K.cylinder(d2 / 2, pin_len, segments=14).translate(0, 0, -pin_len / 2)
    for i in range(n):
        a, b = np.asarray(centers[i]), np.asarray(centers[(i + 1) % n])
        if i % 2 == 0:                                             # mắt trong
            for zc in (b1 / 2 + t / 2, -(b1 / 2 + t / 2)):
                plates.append(plate(a, b, "in").translate(0, 0, zc - t / 2))
        else:                                                      # mắt ngoài
            for zc in (b1 / 2 + 1.5 * t + 0.05, -(b1 / 2 + 1.5 * t + 0.05)):
                plates.append(plate(a, b, "out").translate(0, 0, zc - t / 2))
        rollers.append(roller.translate(a[0], a[1], 0))
        rollers.append(pin.translate(a[0], a[1], 0))
    return K.Solid.union_all(plates), K.Solid.union_all(rollers)


# ------------------------------------------------------------------ ray dẫn hướng + con trượt
def rail_section(g: dict) -> np.ndarray:
    """Mặt cắt ray (mặt YZ): đáy z = 0, đối xứng y; có rãnh bi hai bên (dạng HIWIN HG / MGN)."""
    w, h = g["rail_w"], g["rail_h"]
    c = 0.06 * w
    return np.array(P.chamfer_polygon([(-w / 2, 0), (w / 2, 0), (w / 2, h), (-w / 2, h)], [0.03 * w, 0.03 * w, c, c]))


def linear_rail(g: dict, length: float) -> K.Solid:
    """Ray dọc X, tâm x = 0, đáy z = 0; rãnh bi 4 dãy, lỗ bậc lắp ốc cách đều bước P từ đầu ray E."""
    w, h = g["rail_w"], g["rail_h"]
    sec = cs(rail_section(g))
    rg = 0.12 * w
    grooves = [cs(P.circle(rg, 20, center=(s * w / 2, zc))) for s in (1, -1) for zc in (0.78 * h, 0.5 * h)]
    rail = _yz_extrude(sec - cs_union(grooves), length)
    xs = hole_positions(g, length)
    holes = []
    for x in xs:
        holes.append(K.cylinder(g["hole_d"] / 2, h + 2, segments=20).translate(x, 0, -1))
        holes.append(K.cylinder(g["cb_d"] / 2, g["cb_h"] + 1, segments=24).translate(x, 0, h - g["cb_h"]))
    return rail.subtract_all(holes)


def hole_positions(g: dict, length: float) -> list[float]:
    n = int((length - 2 * g["e"]) // g["pitch"]) + 1
    used = (n - 1) * g["pitch"]
    x0 = -used / 2
    return [x0 + k * g["pitch"] for k in range(n)]


def _yz_extrude(section: m3d.CrossSection, length: float) -> K.Solid:
    """Mặt cắt 2D (u = y, v = z) đùn dọc X, tâm x = 0."""
    s = extrude_cs(section, length, center=True)          # (u, v, w) = (y, z, x)
    m = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])
    return s.transform(m)


def carriage(g: dict) -> dict:
    """Con trượt (block) HGH..CA / MGN..C trên ray: thân thép + nắp đầu nhựa + phớt chắn bụi + vú mỡ.
    Tâm x = 0, ray đáy z = 0; mặt trên con trượt z = H. Rãnh ôm ray chạm mặt đỉnh ray (tiếp xúc qua bi)."""
    w, h = g["rail_w"], g["rail_h"]
    W, L, H = g["car_w"], g["car_l"], g["h"]
    h1 = max(1.0, min(0.17 * H, h - 2.0))                                   # khe đáy con trượt với mặt lắp
    cap_t = max(1.2, 0.08 * L)
    seal_t = max(0.6, 0.025 * L)
    body_l = L - 2 * (cap_t + seal_t)
    outer = P.chamfer_polygon([(-W / 2, h1), (W / 2, h1), (W / 2, H), (-W / 2, H)], [0.04 * W, 0.04 * W, 0.03 * W, 0.03 * W])
    chan = np.array([(-w / 2 - 0.25, h1 - 1), (w / 2 + 0.25, h1 - 1), (w / 2 + 0.25, h), (-w / 2 - 0.25, h)])
    sec = cs(outer) - cs(chan)
    body = _yz_extrude(sec, body_l)
    # lỗ ren lắp trên mặt con trượt (B × C)
    holes = [K.cylinder(g["m"] / 2 * 0.85, H * 0.35, segments=16).translate(sx * g["c"] / 2, sy * g["b"] / 2, H - H * 0.35 + 0.01)
             for sx in (1, -1) for sy in (1, -1)]
    body = body.subtract_all(holes)
    # rãnh tham chiếu dọc hai bên
    zg = h1 + (H - h1) * 0.35
    body = body - (K.box(body_l + 2, W + 2, 0.4) - K.box(body_l + 4, W - 0.8, 1.0)).translate(0, 0, zg)
    cap_sec = cs(P.chamfer_polygon([(-W / 2 + 0.3, h1 + 0.2), (W / 2 - 0.3, h1 + 0.2), (W / 2 - 0.3, H - 0.4), (-W / 2 + 0.3, H - 0.4)],
                                   0.05 * W)) - cs(chan)
    caps, seals = [], []
    for sgn in (1, -1):
        caps.append(_yz_extrude(cap_sec, cap_t).translate(sgn * (body_l / 2 + cap_t / 2), 0, 0))
        seal_sec = cs(P.chamfer_polygon([(-W / 2 + 0.8, h1 + 0.1), (W / 2 - 0.8, h1 + 0.1), (W / 2 - 0.8, H - 1.0), (-W / 2 + 0.8, H - 1.0)],
                                        0.05 * W)) - cs(np.array([(-w / 2, h1 - 1), (w / 2, h1 - 1), (w / 2, h), (-w / 2, h)]))
        seals.append(_yz_extrude(seal_sec, seal_t).translate(sgn * (body_l / 2 + cap_t + seal_t / 2), 0, 0))
    nip_x = body_l / 2 + cap_t + seal_t
    nr = min(0.09 * W, 0.4 * (H - h) - 0.2)                                 # vú mỡ nằm trên đỉnh ray
    nz = h + nr + 0.3 + max(0.0, ((H - h) - 2 * nr - 0.6) / 2)
    nipple = K.cylinder(nr, 0.12 * W, segments=12).rotate(0, 90, 0).translate(nip_x, 0, nz)
    nipple = nipple + K.sphere(0.78 * nr, 10).translate(nip_x + 0.12 * W + 0.3 * nr, 0, nz)
    return {"body": body, "caps": K.Solid.union_all(caps), "seals": K.Solid.union_all(seals), "nipple": nipple,
            "length": L, "height": H, "width": W, "h1": h1}


# ------------------------------------------------------------------ vít me bi
def ball_screw_rod_mesh(d: float, lead: float, ball_d: float, length: float, z0: float = 0.0,
                        max_triangles: int = 110_000, angular: int = 40) -> K.MeshData:
    """Trục vít me bi: rãnh bi xoắn (profile cung tròn bán kính 0,52·d_bi, sâu 0,3·d_bi) theo bước `lead`, trục Z
    từ z0 tới z0 + length. Rãnh thoát dần ở hai đầu (1/4 vòng)."""
    R = d / 2
    rg = 0.52 * ball_d
    depth = 0.3 * ball_d
    leads = max(1.0, length / lead)
    # trục dài: giảm số chia vòng (≥ 20) rồi mẫu/bước (≥ 5) để không vượt ngân sách tam giác
    angular = int(np.clip(max_triangles / (2 * 8 * leads), 20, angular))
    samples_per_lead = int(np.clip(max_triangles / (2 * angular * leads), 5, 32))
    rows = max(8, int(math.ceil(length / lead * samples_per_lead)) + 1)
    zs = np.linspace(0.0, length, rows)
    th = np.linspace(0, TAU, angular, endpoint=False)
    Z, TH = np.meshgrid(zs, th, indexing="ij")
    u = (Z - lead * TH / TAU) % lead - lead / 2                          # khoảng cách dọc trục tới tâm rãnh
    cut = np.sqrt(np.maximum(0.0, rg ** 2 - u ** 2)) - (rg - depth)
    fade = np.clip(np.minimum(Z, length - Z) / (0.25 * lead), 0.0, 1.0)
    r = R - np.maximum(cut, 0.0) * fade
    verts = np.column_stack([(r * np.cos(TH)).ravel(), (r * np.sin(TH)).ravel(), (Z + z0).ravel()])
    i = np.arange(rows - 1)[:, None]
    j = np.arange(angular)[None, :]
    a, b = i * angular + j, i * angular + (j + 1) % angular
    c, dd = (i + 1) * angular + (j + 1) % angular, (i + 1) * angular + j
    faces = np.vstack([np.column_stack([a.ravel(), b.ravel(), c.ravel()]), np.column_stack([a.ravel(), c.ravel(), dd.ravel()])])
    c0 = len(verts)
    verts = np.vstack([verts, [0, 0, z0], [0, 0, z0 + length]])
    jj = np.arange(angular)
    top0 = (rows - 1) * angular
    faces = np.vstack([faces, np.column_stack([np.full(angular, c0), (jj + 1) % angular, jj]),
                       np.column_stack([np.full(angular, c0 + 1), top0 + jj, top0 + (jj + 1) % angular])]).astype(np.int64)
    mesh = K.MeshData(verts, faces)
    if mesh.signed_volume() < 0:
        mesh.faces = faces[:, ::-1].copy()
    return mesh


def ball_screw_rod(d: float, lead: float, ball_d: float, length: float, z0: float = 0.0,
                   max_triangles: int = 110_000) -> K.Solid:
    m = ball_screw_rod_mesh(d, lead, ball_d, length, z0, max_triangles)
    return K.from_mesh(m.vertices, m.faces)


# ------------------------------------------------------------------ lò xo
def helix_path(radius: float, pitches: Sequence[tuple[float, float]], z0: float = 0.0, per_turn: int = 36,
               a0: float = 0.0) -> np.ndarray:
    """Đường xoắn qua các đoạn (số vòng, bước) liên tiếp, chuyển bước mượt trong 1/4 vòng."""
    pts = []
    z, a = z0, a0
    total = sum(n for n, _ in pitches)
    steps = max(8, int(total * per_turn))
    # bước theo vị trí vòng (nội suy mượt giữa các đoạn)
    bounds = np.cumsum([0.0] + [n for n, _ in pitches])
    pvals = [pch for _, pch in pitches]

    def pitch_at(tn: float) -> float:
        for k in range(len(pvals)):
            if tn <= bounds[k + 1] or k == len(pvals) - 1:
                pk = pvals[k]
                if k + 1 < len(pvals) and tn > bounds[k + 1] - 0.25:
                    f = (tn - (bounds[k + 1] - 0.25)) / 0.25
                    return pk + (pvals[k + 1] - pk) * f
                return pk
        return pvals[-1]
    dt = total / steps
    tn = 0.0
    pts.append((radius * math.cos(a), radius * math.sin(a), z))
    for _ in range(steps):
        pch = pitch_at(tn + dt / 2)
        tn += dt
        a += TAU * dt
        z += pch * dt
        pts.append((radius * math.cos(a), radius * math.sin(a), z))
    return np.asarray(pts, float)


# ------------------------------------------------------------------ đường ống
def pipe(od: float, wall: float, length: float, segments: int = 64) -> K.Solid:
    """Ống thẳng dọc +X từ x = 0 tới x = length."""
    return (K.cylinder(od / 2, length, segments=segments) - K.cylinder(od / 2 - wall, length + 2, segments=segments).translate(0, 0, -1)) \
        .rotate(0, 90, 0)


def bend(od: float, wall: float, radius: float, angle_deg: float, segments: int = 64) -> K.Solid:
    """Co (cút) cong trong mặt XY: bắt đầu tại gốc theo hướng +X, cong về phía +Y với bán kính tâm `radius`."""
    outer = K.revolve(P.circle(od / 2, segments, center=(radius, 0.0)), segments=max(24, int(angle_deg / 3)), degrees=angle_deg)
    ext = 2.0
    inner = K.revolve(P.circle(od / 2 - wall, segments, center=(radius, 0.0)), segments=max(24, int(angle_deg / 3)),
                      degrees=angle_deg + 2 * ext).rotate(0, 0, -ext)
    body = outer - inner
    # revolve quanh Z bắt đầu tại (R, 0, 0) đi theo +Y → quay −90° quanh Z rồi dời (0, R, 0): bắt đầu ở gốc theo +X
    return body.rotate(0, 0, -90).translate(0, radius, 0)


def weld_neck_flange(dn: int) -> tuple[K.Solid, dict]:
    """Mặt bích cổ hàn EN 1092-1 PN16 (kiểu 11): trục X, mặt tựa (mặt gờ) tại x = 0 hướng −X, cổ hàn về +X.
    Gờ nổi (raised face) cao 2 mm Ø d1; lỗ bu-lông n × L trên vòng K. Trả (khối, thông số)."""
    D, Kc, Lh, n, M, C2 = S.FLANGE_PN16[dn]
    od = S.PIPE_OD[dn]
    wall = S.PIPE_WALL[dn]
    d1 = S.FLANGE_RF[dn]
    f1 = 2.0
    hub_d = od + 15.0                                   # N1 ≈ OD + 14…16 mm (EN 1092-1 PN16 kiểu 11)
    H = C2 + max(20.0, 0.55 * od)
    prof = [(od / 2 - wall, 0.0), (d1 / 2, 0.0), (d1 / 2, f1), (D / 2, f1), (D / 2, f1 + C2), (hub_d / 2, f1 + C2),
            (od / 2, H), (od / 2 - wall, H)]
    body = K.revolve(P.fillet_polygon(prof, [0, 0.3, 0.3, 0.8, 0.8, min(6.0, 0.08 * od), 0, 0], 4), segments=128)
    holes = [K.cylinder(Lh / 2, C2 + 4, segments=20).translate(Kc / 2 * math.cos(a), Kc / 2 * math.sin(a), f1 - 1)
             for a in np.radians(np.arange(n) * 360.0 / n + 180.0 / n)]
    body = body.subtract_all(holes)
    body = body.rotate(0, 90, 0)          # trục Z → X (mặt tựa tại x = 0, cổ về +X)
    return body, {"D": D, "K": Kc, "L": Lh, "n": n, "M": M, "C2": C2, "d1": d1, "f1": f1, "H": H, "hub_d": hub_d}


def hyd_ram(p0: Sequence[float], p1: Sequence[float], bore: float, rod: float, pin_axis: Sequence[float] = (0, 1, 0),
            barrel_frac: float = 0.62, barrel_len: float | None = None) -> dict:
    """Xi lanh thủy lực giữa hai chốt: đáy xi lanh (mắt đáy) tại p0, đầu cần (mắt cần) tại p1.
    Mắt là đĩa trụ dọc trục chốt (đè lên chốt của bộ phận được nối). Trả {"barrel", "rod", "length", "closed", "stroke"}:
    closed = chiều dài đóng hết (vỏ + mắt), stroke = hành trình thiết kế (≈ vỏ − nắp)."""
    a, c = np.asarray(p0, float), np.asarray(p1, float)
    L = float(np.linalg.norm(c - a))
    d = (c - a) / L
    eye_r = 0.62 * bore
    Lb = barrel_len if barrel_len is not None else barrel_frac * L    # barrel_len: vỏ cố định theo dải làm việc (vd. góc cần 0–80°)
    ro = bore / 2 + 0.12 * bore                                    # bán kính ngoài vỏ
    barrel = orient(K.cylinder(ro, Lb - eye_r, segments=32), a + eye_r * d, d)
    gland = orient(K.cylinder(ro * 0.82, 0.1 * bore, segments=32), a + Lb * d, d)
    cap = orient(K.cylinder(ro * 1.08, 0.12 * bore, segments=32), a + (eye_r - 0.02 * bore) * d, d)
    rod_s = orient(K.cylinder(rod / 2, L - eye_r - 0.35 * Lb, segments=24), a + 0.35 * Lb * d, d)
    ax = np.asarray(pin_axis, float)
    ax = ax / np.linalg.norm(ax)
    eye0 = orient(K.cylinder(eye_r, bore, segments=32).translate(0, 0, -bore / 2), a, ax)
    eye1 = orient(K.cylinder(eye_r * 0.85, 0.8 * bore, segments=32).translate(0, 0, -0.4 * bore), c, ax)
    lug0 = orient(K.cylinder(0.3 * bore, eye_r + 0.02 * bore, segments=20), a, d)
    closed = Lb + 0.1 * bore + 0.25 * bore + eye_r * 0.85
    return {"barrel": barrel + gland + cap + eye0 + lug0, "rod": rod_s + eye1, "length": L, "closed": closed,
            "stroke": Lb - eye_r - 0.2 * bore}


def pin(center: Sequence[float], axis: Sequence[float], d: float, length: float) -> K.Solid:
    """Chốt trụ dọc `axis`, tâm tại `center`."""
    return orient(K.cylinder(d / 2, length, segments=24).translate(0, 0, -length / 2), center, axis)


__all__ = ["cs", "hex_bolt", "hex_nut", "flat_washer", "socket_screw", "bolt_joint", "orient", "bearing_solids",
           "bearing_solid", "spur_gear", "mesh_phase", "nema_stepper", "open_belt_path", "timing_pulley", "vbelt_pulley",
           "sprocket", "chain_rollers", "chain_center", "roller_chain", "linear_rail", "carriage", "ball_screw_rod",
           "helix_path", "pipe", "bend", "weld_neck_flange"]
