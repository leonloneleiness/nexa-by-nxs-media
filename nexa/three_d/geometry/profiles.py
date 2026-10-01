"""Đường cong 2D cho CAD tham số: fillet/chamfer góc, siêu elip, airfoil NACA, bánh răng involute, B-spline.

Mọi hàm trả mảng numpy (N, 2) đơn vị mm. Đa giác kín KHÔNG lặp lại điểm đầu ở cuối.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def _arr(points) -> np.ndarray:
    a = np.asarray(points, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != 2:
        raise ValueError("cần mảng điểm (N, 2)")
    return a


def signed_area(poly) -> float:
    p = _arr(poly)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def ensure_ccw(poly) -> np.ndarray:
    p = _arr(poly)
    return p if signed_area(p) > 0 else p[::-1].copy()


def arc(center, radius: float, a0: float, a1: float, segments: int) -> np.ndarray:
    """Cung tròn từ góc a0 tới a1 (radian), gồm cả hai đầu mút."""
    t = np.linspace(a0, a1, max(2, segments + 1))
    return np.column_stack([center[0] + radius * np.cos(t), center[1] + radius * np.sin(t)])


def fillet_polygon(points, radii, segments_per_90: int = 8, closed: bool = True) -> np.ndarray:
    """Bo tròn các đỉnh của đa giác. radii: số (mọi đỉnh) hoặc danh sách theo từng đỉnh (0 = giữ góc nhọn).

    Bán kính tự thu nhỏ để cung không vượt quá nửa cạnh kề. Với đường hở, hai đầu mút không bị bo.
    """
    p = _arr(points)
    n = len(p)
    r = np.full(n, float(radii)) if np.isscalar(radii) else np.asarray(radii, dtype=np.float64)
    if len(r) != n:
        raise ValueError("số bán kính phải bằng số đỉnh")
    out: list[np.ndarray] = []
    for i in range(n):
        if not closed and (i == 0 or i == n - 1):
            out.append(p[i:i + 1])
            continue
        prev_pt, cur, nxt = p[i - 1], p[i], p[(i + 1) % n]
        v1, v2 = prev_pt - cur, nxt - cur
        l1, l2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
        if r[i] <= 0 or l1 < 1e-9 or l2 < 1e-9:
            out.append(cur[None])
            continue
        u1, u2 = v1 / l1, v2 / l2
        cosang = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
        ang = math.acos(cosang)                      # góc trong tại đỉnh
        if ang < 1e-3 or abs(ang - math.pi) < 1e-3:
            out.append(cur[None])
            continue
        tan_half = math.tan(ang / 2)
        rad = min(r[i], 0.5 * min(l1, l2) * tan_half * 0.999)
        d = rad / tan_half                           # khoảng từ đỉnh tới điểm tiếp xúc
        t1, t2 = cur + u1 * d, cur + u2 * d
        bis = u1 + u2
        bis /= np.linalg.norm(bis)
        center = cur + bis * (rad / math.sin(ang / 2))
        a0 = math.atan2(t1[1] - center[1], t1[0] - center[0])
        a1 = math.atan2(t2[1] - center[1], t2[0] - center[0])
        sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi   # luôn đi đường ngắn
        seg = max(2, int(math.ceil(abs(sweep) / (math.pi / 2) * segments_per_90 - 1e-6)))
        out.append(arc(center, rad, a0, a0 + sweep, seg))
    return np.vstack(out)


def chamfer_polygon(points, distances, closed: bool = True) -> np.ndarray:
    """Vát các đỉnh một khoảng `distances` dọc theo hai cạnh kề (0 = giữ nguyên)."""
    p = _arr(points)
    n = len(p)
    dist = np.full(n, float(distances)) if np.isscalar(distances) else np.asarray(distances, dtype=np.float64)
    out = []
    for i in range(n):
        if (not closed and (i == 0 or i == n - 1)) or dist[i] <= 0:
            out.append(p[i])
            continue
        prev_pt, cur, nxt = p[i - 1], p[i], p[(i + 1) % n]
        v1, v2 = prev_pt - cur, nxt - cur
        l1, l2 = np.linalg.norm(v1), np.linalg.norm(v2)
        d = min(dist[i], 0.49 * l1, 0.49 * l2)
        out.append(cur + v1 / l1 * d)
        out.append(cur + v2 / l2 * d)
    return np.array(out)


def rounded_rect(width: float, height: float, radius: float, segments_per_90: int = 8,
                 center=(0.0, 0.0)) -> np.ndarray:
    w, h = width / 2, height / 2
    pts = np.array([[-w, -h], [w, -h], [w, h], [-w, h]]) + np.asarray(center)
    return fillet_polygon(pts, min(radius, w * 0.999, h * 0.999), segments_per_90)


def circle(radius: float, segments: int = 64, center=(0.0, 0.0), start: float = 0.0) -> np.ndarray:
    t = start + np.linspace(0, 2 * math.pi, segments, endpoint=False)
    return np.column_stack([center[0] + radius * np.cos(t), center[1] + radius * np.sin(t)])


def superellipse(width: float, height: float, exponent: float = 2.5, samples: int = 64,
                 center=(0.0, 0.0), bottom_flat: float = 0.0) -> np.ndarray:
    """|x/a|^n + |y/b|^n = 1. n=2: elip, n>2: gần chữ nhật bo tròn (thân máy bay, vỏ robot).

    bottom_flat ∈ [0,1): làm phẳng nửa dưới (sàn cabin trực thăng). Điểm đầu ở góc 0 (phía +x).
    """
    a, b = width / 2, height / 2
    t = np.linspace(0, 2 * math.pi, samples, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    e = 2.0 / max(0.5, exponent)
    x = a * np.sign(c) * np.abs(c) ** e
    y = b * np.sign(s) * np.abs(s) ** e
    if bottom_flat > 0:
        y = np.where(y < 0, y * (1 - bottom_flat), y)
    return np.column_stack([x + center[0], y + center[1]])


def naca4(code: str = "2412", chord: float = 1.0, samples: int = 48, closed_te: bool = True) -> np.ndarray:
    """Airfoil NACA 4 chữ số (m p tt), x ∈ [0, chord], vòng kín bắt đầu từ mép sau, đi mặt trên rồi mặt dưới.

    Mép sau có độ dày tối thiểu nhỏ để lưới không suy biến.
    """
    if len(code) != 4 or not code.isdigit():
        raise ValueError("mã NACA 4 chữ số, ví dụ '2412'")
    m, p, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    half = max(8, samples // 2)
    beta = np.linspace(0, math.pi, half)
    x = (1 - np.cos(beta)) / 2                        # dồn điểm về mép trước/mép sau
    a4 = -0.1036 if closed_te else -0.1015
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 + a4 * x ** 4)
    if m > 0 and p > 0:
        yc = np.where(x < p, m / p ** 2 * (2 * p * x - x ** 2), m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x ** 2))
        dyc = np.where(x < p, 2 * m / p ** 2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    else:
        yc = np.zeros_like(x)
        dyc = np.zeros_like(x)
    th = np.arctan(dyc)
    yt = np.maximum(yt, 0.0015)                       # mép sau dày tối thiểu 0,15 % dây cung
    xu, yu = x - yt * np.sin(th), yc + yt * np.cos(th)
    xl, yl = x + yt * np.sin(th), yc - yt * np.cos(th)
    upper = np.column_stack([xu, yu])[::-1]           # mép sau → mép trước (mặt trên)
    lower = np.column_stack([xl, yl])[1:-1]           # mép trước → mép sau (mặt dưới), bỏ điểm trùng
    loop = np.vstack([upper, lower]) * chord
    return ensure_ccw(loop)


def involute_gear(module: float, teeth: int, pressure_angle_deg: float = 20.0, backlash: float = 0.0,
                  flank_samples: int = 10, root_samples: int = 4, tip_samples: int = 3) -> np.ndarray:
    """Biên dạng bánh răng trụ răng thẳng thân khai (involute) chuẩn: đường kính chia d = m·z,
    đỉnh răng d + 2m, chân răng d − 2,5m. Trả về đa giác kín CCW.
    """
    if teeth < 6 or module <= 0:
        raise ValueError("bánh răng cần ≥ 6 răng và module > 0")
    alpha = math.radians(pressure_angle_deg)
    r_p = module * teeth / 2
    r_b = r_p * math.cos(alpha)
    r_a = r_p + module
    r_f = max(r_p - 1.25 * module, 0.2 * r_p)

    def inv(a: float) -> float:
        return math.tan(a) - a

    # Nửa độ dày góc của răng tại vòng cơ sở.
    s_p = math.pi * module / 2 - backlash / 2
    half_base = s_p / (2 * r_p) + inv(alpha)
    r_start = max(r_b, r_f)
    radii = np.linspace(r_start, r_a, flank_samples)
    flank = []
    for r in radii:
        a_r = math.acos(min(1.0, r_b / r))
        flank.append((r, half_base - inv(a_r)))       # (bán kính, nửa góc răng tại bán kính r)
    pitch_ang = 2 * math.pi / teeth
    h0 = flank[0][1]
    pts: list[tuple[float, float]] = []
    for k in range(teeth):
        c = k * pitch_ang
        # cung chân răng giữa răng k-1 (kết thúc ở góc c - pitch + h0) và răng k (bắt đầu ở c - h0)
        for a in np.linspace(c - pitch_ang + h0, c - h0, root_samples + 2)[1:-1]:
            pts.append((r_f * math.cos(a), r_f * math.sin(a)))
        # dưới vòng cơ sở sườn răng là đoạn hướng tâm (không mô phỏng cắt chân răng)
        pts.append((r_f * math.cos(c - h0), r_f * math.sin(c - h0)))
        for r, h in flank:                              # sườn phải (đi lên)
            pts.append((r * math.cos(c - h), r * math.sin(c - h)))
        tip_h = flank[-1][1]
        for a in np.linspace(c - tip_h, c + tip_h, tip_samples + 2)[1:-1]:
            pts.append((r_a * math.cos(a), r_a * math.sin(a)))
        for r, h in reversed(flank):                    # sườn trái (đi xuống)
            pts.append((r * math.cos(c + h), r * math.sin(c + h)))
        pts.append((r_f * math.cos(c + h0), r_f * math.sin(c + h0)))
    poly = np.array(pts)
    # bỏ điểm trùng liên tiếp
    keep = np.ones(len(poly), bool)
    keep[1:] = np.linalg.norm(np.diff(poly, axis=0), axis=1) > 1e-7
    poly = poly[keep]
    return ensure_ccw(poly)


def gear_radii(module: float, teeth: int) -> dict[str, float]:
    r_p = module * teeth / 2
    return {"pitch": r_p, "tip": r_p + module, "root": max(r_p - 1.25 * module, 0.2 * r_p)}


def spline_through(points: Sequence, samples: int = 64, closed: bool = False) -> np.ndarray:
    """Đường cong B-spline bậc 3 (nội suy) đi qua các điểm điều khiển, tham số theo độ dài dây cung. N chiều."""
    from scipy.interpolate import make_interp_spline
    p = np.asarray(points, dtype=np.float64)
    if closed:
        p = np.vstack([p, p[:1]])
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(np.maximum(d, 1e-9))])
    t /= t[-1]
    k = min(3, len(p) - 1)
    bc = "periodic" if closed and len(p) > 3 else None
    spl = make_interp_spline(t, p, k=k, bc_type=bc)
    u = np.linspace(0, 1, samples, endpoint=not closed)
    return spl(u)


def bspline(control_points: Sequence, samples: int = 64, degree: int = 3) -> np.ndarray:
    """B-spline kẹp (clamped) theo điểm điều khiển — đi qua điểm đầu/cuối, mượt ở giữa (không đi qua điểm giữa)."""
    from scipy.interpolate import BSpline
    c = np.asarray(control_points, dtype=np.float64)
    n = len(c)
    k = min(degree, n - 1)
    knots = np.concatenate([np.zeros(k), np.linspace(0, 1, n - k + 1), np.ones(k)])
    spl = BSpline(knots, c, k)
    return spl(np.linspace(0, 1, samples))


def resample_closed(poly, count: int, start_angle: float | None = 0.0) -> np.ndarray:
    """Lấy mẫu lại đa giác kín thành `count` điểm cách đều theo độ dài, bắt đầu gần tia `start_angle` (từ tâm)
    để các mặt cắt của loft thẳng hàng với nhau."""
    p = ensure_ccw(poly)
    if start_angle is not None:
        c = p.mean(axis=0)
        ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])
        diff = np.abs((ang - start_angle + math.pi) % (2 * math.pi) - math.pi)
        p = np.roll(p, -int(np.argmin(diff)), axis=0)
    closed = np.vstack([p, p[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.linspace(0, s[-1], count, endpoint=False)
    x = np.interp(targets, s, closed[:, 0])
    y = np.interp(targets, s, closed[:, 1])
    return np.column_stack([x, y])


def offset_polygon(poly, delta: float) -> np.ndarray:
    """Offset đa giác (dương = nở ra) bằng Clipper của manifold3d, góc tròn."""
    import manifold3d as m3d
    cs = m3d.CrossSection([ensure_ccw(poly)]).offset(delta, m3d.JoinType.Round)
    polys = cs.to_polygons()
    if not polys:
        raise ValueError("offset làm biến mất đa giác")
    best = max(polys, key=lambda q: abs(signed_area(q)))
    return ensure_ccw(np.asarray(best, dtype=np.float64))
