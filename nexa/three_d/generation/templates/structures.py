"""Bộ dựng kết cấu giàn thép phẳng dùng chung (giàn mái, giàn cầu): thanh thép góc đôi (2L) kẹp bản mã, bu-lông xuyên lỗ.

Quy ước (giàn nằm trong mặt phẳng song song XZ tại y = y0, nút cho dưới dạng (x, z)):
- Thanh 2L: hai thép góc đều cạnh L×t quay lưng vào nhau, cách nhau đúng bề dày bản mã g; cánh đứng áp hai mặt bản mã
  (|y − y0| ∈ [g/2, g/2 + t]), cánh ngang ở mép. Thanh cánh (chord): gót thép góc nằm trên đường nút, cánh đứng quay vào
  trong giàn; thanh bụng (web): đối xứng qua đường nút.
- Đầu thanh được cắt lùi (trim) bằng phép thử giao diện tích 2D (manifold CrossSection) cho tới khi không lấn thanh khác
  tại nút — nên các thanh không xuyên nhau mà vẫn cùng kẹp một bản mã.
- Bản mã mỗi nút = bao lồi vùng bu-lông các đầu thanh + mép 1,5d, cắt theo mép gót thanh cánh; bu-lông M(d) + đai ốc +
  vòng đệm xuyên cánh đứng hai thép góc và bản mã; lỗ khoét bằng chính thân bu-lông (không giao khối).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import manifold3d as m3d
import numpy as np

from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K

# (cạnh L, dày t) thép góc đều cạnh TCVN 1656 / EN 10056-1; bản mã g; bu-lông d
SECTIONS = {"light": dict(chord=(75.0, 8.0), web=(63.0, 6.0), g=10.0, d=16.0),
            "medium": dict(chord=(100.0, 10.0), web=(75.0, 8.0), g=12.0, d=20.0),
            "heavy": dict(chord=(125.0, 12.0), web=(90.0, 9.0), g=14.0, d=22.0),
            "bridge": dict(chord=(200.0, 20.0), web=(150.0, 15.0), g=20.0, d=24.0)}


@dataclass
class Member:
    a: int
    b: int
    group: str                      # nhóm bộ phận: "top_chord", "bottom_chord", "web", …
    chord: bool = False
    inward: tuple[float, float] | None = None   # (x, z): phía trong giàn (thanh cánh)
    L: float = 0.0
    t: float = 0.0
    trim_a: float = 0.0
    trim_b: float = 0.0
    # tính sau
    d: np.ndarray = field(default_factory=lambda: np.zeros(2))
    n: np.ndarray = field(default_factory=lambda: np.zeros(2))
    w0: float = 0.0
    h: float = 1.0


def _cs(poly: np.ndarray) -> m3d.CrossSection:
    return MC.cs(np.asarray(poly, float))


def light_bolt(d: float, grip: float) -> tuple[K.Solid, K.Solid, K.Solid]:
    """Bu-lông kết cấu nhẹ lưới (dùng cho hàng trăm bu-lông của giàn/tháp): đầu + đai ốc lục giác ISO 4014/4032 (s, k, m
    theo cỡ), thân Ø d 12 cạnh. Trục +Y, mặt tựa đầu tại y = 0, đai ốc tựa tại y = −grip. Trả (bu-lông, đai ốc, thân khoét lỗ)."""
    iso = MC.iso_or_scaled(d)
    s_, k_, m_ = iso["s"], iso["k"], iso["m"]
    e = s_ / np.cos(np.radians(30))
    hexa = lambda h: K.extrude(MC.P.circle(e / 2, 6, start=np.radians(30)), h)     # noqa: E731
    length = grip + m_ + 0.5 * d
    bolt = hexa(k_) + K.cylinder(d / 2, length + 0.02, segments=12).translate(0, 0, -length)
    nut = hexa(m_) - K.cylinder(d / 2, 3 * m_, segments=12).translate(0, 0, -m_)
    core = K.cylinder(d / 2, grip + 0.02, segments=12).translate(0, 0, -grip - 0.01)
    rot = np.array([[1.0, 0, 0, 0], [0, 0, 1.0, 0], [0, -1.0, 0, 0]])  # +Z → +Y (det = +1)
    return bolt.transform(rot), nut.translate(0, 0, -grip - m_).transform(rot), core.transform(rot)


def bake(s: K.Solid) -> K.Solid:
    """Tính xong cây CSG lười thành lưới lá: các bản sao tịnh tiến không phải tính lại phép boolean của mẫu."""
    return K.Solid(m3d.Manifold(s.m.to_mesh()))


class PlanarTruss:
    def __init__(self, nodes: Sequence[Sequence[float]], members: Sequence[Member], section: dict, y0: float = 0.0,
                 clearance: float = 15.0) -> None:
        self.P = np.array(nodes, float)
        self.M = list(members)
        self.sec = section
        self.y0 = y0
        self.c = clearance
        self.g = section["g"]
        self.bd = section["d"]
        cen = self.P.mean(axis=0)
        for m in self.M:
            m.L, m.t = section["chord"] if m.chord else section["web"]
            v = self.P[m.b] - self.P[m.a]
            m.d = v / np.linalg.norm(v)
            m.n = np.array([-m.d[1], m.d[0]])
            if m.chord:
                q = np.asarray(m.inward if m.inward is not None else cen - self.P[m.a], float)
                m.h = 1.0 if q @ m.n >= 0 else -1.0
                m.w0 = 0.0
            else:
                m.h = 1.0
                m.w0 = -m.L / 2
        self._trim()

    # ------------------------------------------------------------------ hình chiếu trong mặt giàn
    def length(self, m: Member) -> float:
        return float(np.linalg.norm(self.P[m.b] - self.P[m.a]))

    def footprint(self, m: Member, s0: float, s1: float) -> np.ndarray:
        a = self.P[m.a]
        w1 = m.w0 + m.h * m.L
        return np.array([a + m.d * s0 + m.n * m.w0, a + m.d * s1 + m.n * m.w0, a + m.d * s1 + m.n * w1, a + m.d * s0 + m.n * w1])

    def _end_fp(self, m: Member, at_a: bool, trim: float, reach: float) -> np.ndarray:
        Lm = self.length(m)
        return self.footprint(m, trim, min(Lm / 2, trim + reach)) if at_a else self.footprint(m, max(Lm / 2, Lm - trim - reach), Lm - trim)

    def _continuous(self, m: Member, node: int) -> bool:
        """Thanh cánh chạy liên tục qua nút (có thanh cánh cùng nhóm nối tiếp) → không cắt lùi tại nút này."""
        return m.chord and any(o is not m and o.chord and o.group == m.group and node in (o.a, o.b) for o in self.M)

    def _trim(self) -> None:
        for node in range(len(self.P)):
            ends = [(m, m.a == node) for m in self.M if node in (m.a, m.b)]
            fixed = [self._end_fp(m, at_a, 0.0, 1e9) for m, at_a in ends if self._continuous(m, node)]   # tới giữa thanh
            # thanh cánh liên tục + thanh cánh đầu mút dài nhất giữ nguyên, còn lại cắt lùi lần lượt
            rest = [(m, at_a) for m, at_a in ends if not self._continuous(m, node)]
            if not fixed and rest:
                chords = [e for e in rest if e[0].chord]
                keep = max(chords or rest, key=lambda e: (e[0].chord, e[0].group.startswith("bottom"), self.length(e[0])))
                fixed.append(self._end_fp(keep[0], keep[1], 0.0, 1e9))
                rest.remove(keep)
            placed = [_cs(f) for f in fixed]
            for m, at_a in sorted(rest, key=lambda e: -self.length(e[0])):
                trim = 0.0
                while trim < 0.45 * self.length(m):
                    fp = _cs(self._end_fp(m, at_a, trim, 1e9)).offset(self.c / 2, m3d.JoinType.Miter)   # tới giữa thanh
                    if all((fp ^ q).area() < 1e-3 for q in placed):
                        break
                    trim += 5.0
                placed.append(_cs(self._end_fp(m, at_a, trim, 1e9)).offset(self.c / 2, m3d.JoinType.Miter))
                if at_a:
                    m.trim_a = trim
                else:
                    m.trim_b = trim

    # ------------------------------------------------------------------ khối 3D
    def _to3(self, p2: np.ndarray, y: float = 0.0) -> np.ndarray:
        return np.array([p2[0], self.y0 + y, p2[1]])

    def member_solid(self, m: Member) -> K.Solid:
        L, t, g = m.L, m.t, self.g
        Lm = self.length(m)
        s0, s1 = m.trim_a, Lm - m.trim_b
        out = []
        for s in (1, -1):
            h = m.h
            poly = np.array([(s * g / 2, m.w0), (s * (g / 2 + L), m.w0), (s * (g / 2 + L), m.w0 + h * t), (s * (g / 2 + t), m.w0 + h * t),
                             (s * (g / 2 + t), m.w0 + h * L), (s * g / 2, m.w0 + h * L)])
            ex = K.Solid(_cs(poly).extrude(s1 - s0))
            d3 = np.array([m.d[0], 0.0, m.d[1]])
            n3 = np.array([m.n[0], 0.0, m.n[1]])
            mat = np.column_stack([[0, 1.0, 0], n3, d3])
            org = self._to3(self.P[m.a]) + d3 * s0
            out.append(ex.transform(np.hstack([mat, org[:, None]])))
        return out[0] + out[1]

    def gusset_regions(self, bolts: Sequence[tuple[np.ndarray, int]] = ()) -> dict[int, np.ndarray]:
        """Đa giác bản mã (x, z) mỗi nút có ≥ 2 thanh: bao lồi vùng đầu thanh + mọi bu-lông của nút (mép ≥ 1,5d)."""
        e = 1.5 * self.bd
        regs = {}
        for node in range(len(self.P)):
            ends = [(m, m.a == node) for m in self.M if node in (m.a, m.b)]
            if len(ends) < 2:
                continue
            pts = []
            for m, at_a in ends:
                trim = m.trim_a if at_a else m.trim_b
                zone = 2 * 3 * self.bd + 2 * e
                if self._continuous(m, node) or trim == 0.0:
                    fp = self._end_fp(m, at_a, 0.0, zone)
                else:
                    fp = self._end_fp(m, at_a, trim, zone)
                pts.append(fp)
            for q, n_ in bolts:
                if n_ == node:
                    pts.append(np.array([q + (-e, -e), q + (e, -e), q + (e, e), q + (-e, e)]))
            hull = m3d.CrossSection.hull_points(np.vstack(pts).tolist())
            hull = hull.offset(8.0, m3d.JoinType.Round, circular_segments=12)
            for m, at_a in ends:                                            # không vượt ra ngoài gót thanh cánh
                if m.chord:
                    a = self.P[m.a]
                    big = 1e5
                    half = np.array([a - m.d * big + m.n * m.w0, a + m.d * big + m.n * m.w0,
                                     a + m.d * big + m.n * (m.w0 + m.h * big), a - m.d * big + m.n * (m.w0 + m.h * big)])
                    hull = hull ^ _cs(half)
            regs[node] = np.array(hull.to_polygons()[0])
        return regs

    def gusset_solid(self, poly: np.ndarray) -> K.Solid:
        ex = K.Solid(_cs(poly).extrude(self.g))
        mat = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, self.y0 + self.g / 2], [0, 1.0, 0, 0]])
        return ex.transform(mat)

    def bolt_points(self) -> list[tuple[np.ndarray, int]]:
        """(tâm bu-lông (x, z), nút): 2 bu-lông mỗi đầu thanh tại nút có bản mã."""
        e, p = 1.5 * self.bd + 10.0, 3.0 * self.bd
        pts = []
        for node in range(len(self.P)):
            ends = [(m, m.a == node) for m in self.M if node in (m.a, m.b)]
            if len(ends) < 2:
                continue
            here: list[np.ndarray] = []
            for m, at_a in ends:
                # thanh cánh liên tục: mỗi đoạn 2 bu-lông theo phương của chính nó (đổi hướng ở đỉnh kèo vẫn đúng)
                gauge = m.w0 + m.h * (0.55 * m.L if m.chord else 0.5 * m.L + 0.05 * m.L)
                trim = m.trim_a if at_a else m.trim_b
                a = self.P[m.a]
                Lm = self.length(m)
                s_rel = trim + e
                for _k in range(2):
                    while True:                                        # giữ khoảng cách ≥ 2,5d với bu-lông khác tại nút
                        s = s_rel if at_a else Lm - s_rel
                        q = a + m.d * s + m.n * gauge
                        if (all(np.linalg.norm(q - o) >= 2.5 * self.bd for o in here) and self._washer_clear(q)) or s_rel > 0.45 * Lm:
                            break
                        s_rel += 0.5 * p
                    here.append(q)
                    pts.append((q, node))
                    s_rel += p
        return pts

    def _washer_clear(self, q: np.ndarray) -> bool:
        """Vòng đệm/đầu bu-lông (bán kính ≈ 1,05d) không chạm cánh ngang (dải gót) của bất kỳ thanh nào."""
        r = 1.05 * self.bd + 1.0
        for m in self.M:
            Lm = self.length(m)
            rel = q - self.P[m.a]
            s, w = rel @ m.d, rel @ m.n
            if not (m.trim_a - r <= s <= Lm - m.trim_b + r):
                continue
            lo, hi = sorted((m.w0, m.w0 + m.h * m.t))
            if lo - r < w < hi + r:
                return False
        return True

    def _contains(self, m: Member, q: np.ndarray, margin: float = 1.0) -> bool:
        Lm = self.length(m)
        rel = q - self.P[m.a]
        s, w = rel @ m.d, rel @ m.n
        lo, hi = sorted((m.w0, m.w0 + m.h * m.L))
        return m.trim_a - margin <= s <= Lm - m.trim_b + margin and lo - margin <= w <= hi + margin

    def build(self) -> dict:
        """{nhóm: khối thanh (đã khoan lỗ)}, bản mã (đã khoan), bu-lông, đai ốc, số nút có bản mã, số bu-lông.
        Lỗ khoan cục bộ: mỗi thanh / bản mã chỉ trừ thân các bu-lông đi qua nó (nhanh hơn nhiều so với trừ một khối hợp lớn)."""
        proto: dict[float, tuple] = {}
        bolts, nuts, placed = [], [], []                               # placed: (điểm 2D, nút, thân bu-lông)
        for q, node in self.bolt_points():
            owners = [m for m in self.M if self._contains(m, q)]
            tl = max((m.t for m in owners), default=self.sec["web"][1])   # kẹp = bản mã + 2 cánh thép góc
            if tl not in proto:                                        # một bộ mẫu cho mỗi chiều dày kẹp, chỉ tịnh tiến
                proto[tl] = tuple(bake(x) for x in light_bolt(self.bd, self.g + 2 * tl))
            q3 = self._to3(q, self.g / 2 + tl)
            b_, n_, c_ = proto[tl]
            bolts.append(b_.translate(*q3).m)
            nuts.append(n_.translate(*q3).m)
            placed.append((q, node, c_.translate(*q3)))
        groups: dict[str, list[K.Solid]] = {}
        for m in self.M:
            holes = [c for q, _n, c in placed if self._contains(m, q, 0.5 * self.bd + 1.0)]   # thân bu-lông chạm thanh → khoan
            sol = self.member_solid(m)
            groups.setdefault(m.group, []).append(sol.subtract_all(holes) if holes else sol)
        regs = self.gusset_regions([(q, n_) for q, n_, _c in placed])
        gus = []
        for node, poly in regs.items():
            holes = [c for _q, n_, c in placed if n_ == node]
            sol = self.gusset_solid(poly)
            gus.append((sol.subtract_all(holes) if holes else sol).m)
        return {"members": {k: K.Solid.union_all(v) for k, v in groups.items()},
                "gussets": K.Solid(m3d.Manifold.compose(gus)),         # các bản mã rời nhau → ghép không cần boolean
                "bolts": K.Solid(m3d.Manifold.compose(bolts)), "nuts": K.Solid(m3d.Manifold.compose(nuts)),
                "cores": K.Solid(m3d.Manifold.compose([c.m for _q, _n, c in placed])),
                "n_gussets": len(regs), "n_bolts": len(placed)}


__all__ = ["SECTIONS", "Member", "PlanarTruss"]
