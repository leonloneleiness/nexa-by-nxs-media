"""Chi tiết kỹ thuật dùng chung cho template (hệ X trước, Y trái, Z lên; mm): làm mô hình trông như thiết bị thật.

- Rãnh ghép tấm khắc vào vỏ (panel line), ốc đầu tròn lục giác chìm, khe tản nhiệt, dây cáp có đầu nối, tay cầm,
  nút dừng khẩn cấp, dải đèn, cổng sạc, cảm biến siêu âm, tấm nhãn.
- Hàm "cutter" trả khối để TRỪ khỏi vỏ; hàm còn lại trả khối/Shape để thêm vào bộ phận.
Kích thước lấy theo linh kiện phổ biến (ốc M3–M8 ISO 7380, nút E-stop Ø40, cảm biến siêu âm Ø16…), nhân theo tỷ lệ.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P


def shrink(solid: K.Solid, depth: float) -> K.Solid:
    """Thu nhỏ khối quanh tâm hộp bao sao cho mỗi mặt lùi vào ~depth (xấp xỉ offset trong, đủ cho rãnh nông)."""
    lo, hi = solid.bounds()
    size = np.maximum(hi - lo, 1e-6)
    k = np.clip(1 - 2 * depth / size, 0.05, 1.0)
    c = (lo + hi) / 2
    m = np.array([[k[0], 0, 0, c[0] * (1 - k[0])], [0, k[1], 0, c[1] * (1 - k[1])], [0, 0, k[2], c[2] * (1 - k[2])]])
    return solid.transform(m)


def panel_lines(outer: K.Solid, cuts: Sequence[tuple[str, float]], width: float, depth: float,
                keep_below: float | None = None) -> K.Solid:
    """Khối rãnh ghép tấm: lớp da ngoài dày `depth` của `outer` giao với các lát phẳng mỏng.

    cuts: [("x", 120.0), ("z", 300.0), …] — mặt phẳng cắt vuông góc trục. keep_below: chỉ tạo rãnh phía trên z này."""
    lo, hi = outer.bounds()
    span = hi - lo
    skin = outer - shrink(outer, depth)
    slabs = []
    for axis, value in cuts:
        size = [span[0] * 1.2, span[1] * 1.2, span[2] * 1.2]
        center = list((lo + hi) / 2)
        i = "xyz".index(axis)
        size[i] = width
        center[i] = value
        slabs.append(K.box(*size).translate(*center))
    if not slabs:
        return K.Solid.union_all([])
    grooves = skin & K.Solid.union_all(slabs)
    if keep_below is not None:
        grooves = grooves & K.box(span[0] * 2, span[1] * 2, span[2] * 2).translate(
            (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, keep_below + span[2])
    return grooves


def outline_groove(outer: K.Solid, center: Sequence[float], size_x: float, size_z: float, width: float, depth: float,
                   corner: float = 0.0) -> K.Solid:
    """Rãnh viền chữ nhật (cửa, nắp bảo dưỡng) khắc trên HAI mặt bên (±Y) của `outer`, tâm (x, z) = center[0], center[2]."""
    lo, hi = outer.bounds()
    span_y = float(hi[1] - lo[1]) * 1.3
    c = np.asarray(center, float)
    r = corner or min(size_x, size_z) * 0.08
    ring = K.rounded_box(size_x, span_y, size_z, r) - K.rounded_box(size_x - 2 * width, span_y * 1.1, size_z - 2 * width,
                                                                     max(r - width, r * 0.3))
    ring = ring.translate(c[0], (lo[1] + hi[1]) / 2, c[2])
    return (outer - shrink(outer, depth)) & ring


def surface_at(solid: K.Solid, axis: str, point: Sequence[float], positive: bool = True) -> float | None:
    """Tọa độ bề mặt thật của khối dọc `axis` qua điểm (hai tọa độ còn lại lấy từ `point`) — đo, không đoán.

    positive=True: mặt xa nhất theo chiều dương; False: theo chiều âm. None nếu đường không cắt khối."""
    lo, hi = solid.bounds()
    i = "xyz".index(axis)
    span = float(np.max(hi - lo)) * 3 + 1.0
    eps = max(1e-3, float(np.max(hi - lo)) * 1e-4)
    size = [eps, eps, eps]
    size[i] = span
    c = list(map(float, point))
    c[i] = float((lo[i] + hi[i]) / 2)
    probe = solid & K.box(*size).translate(*c)
    if probe.is_empty:
        return None
    b_lo, b_hi = probe.bounds()
    return float(b_hi[i] if positive else b_lo[i])


def button_screw(d: float) -> K.Solid:
    """Ốc đầu tròn lục giác chìm (ISO 7380): đầu vòm Ø1,9d cao 0,55d, lỗ lục giác 0,6d. Đáy đầu ở z=0, trục +Z."""
    dk, k = 1.9 * d, 0.55 * d
    head = K.revolve(P.fillet_polygon([(0, 0), (dk / 2, 0), (dk / 2, k * 0.25), (dk * 0.3, k), (0, k)],
                                      [0, 0.05 * d, 0.35 * d, 0.3 * d, 0], 4), segments=24)
    s = 0.6 * d
    sock = K.extrude(P.circle(s / 2 / math.cos(math.radians(30)), 6), k).translate(0, 0, k * 0.45)
    return head - sock


def screws_at(points: Sequence[Sequence[float]], normal: Sequence[float], d: float, sink: float = 0.15) -> K.Solid:
    """Nhiều ốc đầu tròn đặt tại các điểm trên mặt có pháp tuyến `normal` (lún nhẹ vào mặt để không lơ lửng)."""
    nrm = np.asarray(normal, float)
    nrm /= np.linalg.norm(nrm)
    one = button_screw(d).translate(0, 0, -sink * d)
    return K.Solid.union_all([one.align_z(nrm, np.asarray(p, float)) for p in points])


def corner_points(cx: float, cy: float, sx: float, sy: float, z: float, inset: float) -> list[tuple[float, float, float]]:
    """4 điểm gần góc của hình chữ nhật tâm (cx, cy) kích thước sx×sy trên mặt z (cách mép `inset`)."""
    hx, hy = sx / 2 - inset, sy / 2 - inset
    return [(cx + a * hx, cy + b * hy, z) for a in (1, -1) for b in (1, -1)]


def vent_cutter(center: Sequence[float], normal: Sequence[float], along: Sequence[float], length: float, height: float,
                slots: int, depth: float, slot_ratio: float = 0.45, segments: int | None = None) -> K.Solid:
    """Khe tản nhiệt: `slots` rãnh bo tròn song song, trải dọc `along` trên mặt có pháp tuyến `normal`."""
    nrm = np.asarray(normal, float) / np.linalg.norm(normal)
    a = np.asarray(along, float)
    a = a - nrm * (a @ nrm)
    a /= np.linalg.norm(a)
    pitch = length / max(1, slots)
    w = pitch * slot_ratio
    cut = []
    for i in range(slots):
        off = (i - (slots - 1) / 2) * pitch
        slot = K.rounded_box(w, height, depth * 2, min(w, height) * 0.45, segments=segments)   # rãnh nằm trong mặt XY, sâu theo Z
        rot = K.align_matrix([0, 0, 1], nrm)
        # trục X của khe phải trùng `along`: xoay quanh pháp tuyến cho khớp
        x_after = rot @ np.array([1.0, 0, 0])
        ang = math.degrees(math.atan2(np.cross(x_after, a) @ nrm, x_after @ a))
        s = slot.transform(K.affine(rot)).rotate_axis(nrm, ang)
        cut.append(s.moved(np.asarray(center, float) + a * off))
    return K.Solid.union_all(cut)


def cable(points: Sequence[Sequence[float]], radius: float, connectors: bool = True) -> tuple[K.Solid, K.Solid | None]:
    """Dây cáp mềm (spline qua các điểm) + đầu nối ở hai đầu. Trả (vỏ dây, đầu nối)."""
    pts = np.asarray(points, float)
    path = P.spline_through(pts, max(24, len(pts) * 12)) if len(pts) >= 3 else pts
    wire = K.tube(path, radius, 14, rounded_ends=True)
    if not connectors:
        return wire, None
    ends = []
    for i, j in ((0, 1), (-1, -2)):
        d = path[i] - path[j]
        d /= max(np.linalg.norm(d), 1e-9)
        plug = K.rounded_box(radius * 3.2, radius * 3.2, radius * 4.2, radius * 0.8)
        ends.append(plug.align_z(d, path[i] - d * radius * 1.6))
    return wire, K.Solid.union_all(ends)


def handle_bar(p0: Sequence[float], p1: Sequence[float], up: Sequence[float], standoff: float, radius: float) -> K.Solid:
    """Tay cầm hình chữ U: hai chân vuông góc mặt (theo `up`) và thanh ngang bo tròn."""
    a, b = np.asarray(p0, float), np.asarray(p1, float)
    u = np.asarray(up, float) / np.linalg.norm(up)
    r = standoff * 0.35
    d = (b - a) / max(np.linalg.norm(b - a), 1e-9)
    pts = [a - u * radius, a + u * (standoff - r), a + u * standoff + d * r, b + u * standoff - d * r,
           b + u * (standoff - r), b - u * radius]
    path = P.spline_through(np.asarray(pts), 48)
    feet = [K.cylinder(radius * 1.9, radius * 0.8, segments=24).align_z(u, q) for q in (a, b)]
    return K.Solid.union_all([K.tube(path, radius, 16, rounded_ends=True)] + feet)


def estop_button(radius: float) -> tuple[K.Solid, K.Solid]:
    """Nút dừng khẩn cấp: đế vàng + nấm đỏ. Đáy ở z=0. Trả (đế, nấm)."""
    base = K.revolve(P.fillet_polygon([(0, 0), (radius, 0), (radius, radius * 0.45), (0, radius * 0.45)],
                                      [0, radius * 0.1, radius * 0.12, 0], 4), segments=40)
    stem = K.cylinder(radius * 0.45, radius * 0.4, segments=32).translate(0, 0, radius * 0.4)
    cap = K.revolve(P.fillet_polygon([(0, radius * 0.75), (radius * 0.78, radius * 0.75), (radius * 0.78, radius * 1.0),
                                      (radius * 0.55, radius * 1.18), (0, radius * 1.2)],
                                     [0, 0.05 * radius, 0.15 * radius, 0.2 * radius, 0], 4), segments=40)
    return base, stem + cap


def light_bar(length: float, height: float, depth: float) -> tuple[K.Solid, K.Solid]:
    """Dải đèn LED: vỏ bo tròn + mặt kính phát sáng. Mặt kính nhìn +X, tâm ở gốc. Trả (vỏ, kính)."""
    housing = K.rounded_box(depth, length, height, min(height, depth) * 0.35)
    lens = K.rounded_box(depth * 0.3, length * 0.92, height * 0.62, height * 0.25).translate(depth * 0.4, 0, 0)
    return housing - lens.translate(depth * 0.05, 0, 0), lens


def ultrasonic_sensor(d: float) -> tuple[K.Solid, K.Solid]:
    """Cảm biến siêu âm đỗ xe: vòng viền + màng. Nhìn +X, tâm ở gốc. Trả (viền, màng)."""
    ring = K.cylinder(d * 0.62, d * 0.35, segments=32).rotate(0, 90, 0).translate(-d * 0.2, 0, 0)
    ring = ring - K.cylinder(d * 0.5, d * 0.4, segments=32).rotate(0, 90, 0).translate(-d * 0.05, 0, 0)
    face = K.cylinder(d * 0.5, d * 0.08, segments=32).rotate(0, 90, 0).translate(-d * 0.05, 0, 0)
    return ring, face


def charge_port(d: float) -> tuple[K.Solid, K.Solid]:
    """Cổng sạc tròn có nắp cao su (kiểu XLR/GX16). Nhìn +X, tâm ở gốc. Trả (thân kim loại, nắp)."""
    body = K.cylinder(d * 0.5, d * 0.35, segments=32).rotate(0, 90, 0).translate(-d * 0.15, 0, 0)
    body = body - K.cylinder(d * 0.34, d * 0.3, segments=32).rotate(0, 90, 0).translate(0.02 * d, 0, 0)
    flange = K.rounded_box(d * 0.08, d * 1.2, d * 1.2, d * 0.2).translate(-d * 0.16, 0, 0)
    cap = K.cylinder(d * 0.3, d * 0.12, segments=24).rotate(0, 90, 0).translate(d * 0.05, 0, 0)
    return body + flange, cap


def label_plate(width: float, height: float, thickness: float) -> K.Solid:
    """Tấm nhãn/biển tên mỏng bo góc, mặt nhìn +X, tâm ở gốc."""
    return K.rounded_box(thickness, width, height, min(width, height) * 0.1)


def cooling_fins(radius: float, length: float, count: int, fin_h: float, fin_t: float) -> K.Solid:
    """Vây tản nhiệt hướng kính quanh trục Z (vỏ động cơ), đáy z = −length/2."""
    fins = [K.box(fin_h, fin_t, length).translate(radius + fin_h / 2 - fin_h * 0.2, 0, 0).rotate(0, 0, 360.0 * i / count)
            for i in range(count)]
    return K.Solid.union_all(fins)


def rivet_row(p0: Sequence[float], p1: Sequence[float], normal: Sequence[float], count: int, d: float) -> K.Solid:
    """Hàng đinh tán đầu tròn trên mặt (thân trực thăng, tàu)."""
    a, b = np.asarray(p0, float), np.asarray(p1, float)
    nrm = np.asarray(normal, float) / np.linalg.norm(normal)
    dome = K.sphere(d / 2, 10).scale(1, 1, 0.45)
    return K.Solid.union_all([dome.align_z(nrm, a + (b - a) * t) for t in np.linspace(0, 1, count)])


__all__ = ["shrink", "panel_lines", "button_screw", "screws_at", "corner_points", "vent_cutter", "cable", "handle_bar",
           "estop_button", "light_bar", "ultrasonic_sensor", "charge_port", "label_plate", "cooling_fins", "rivet_row"]
