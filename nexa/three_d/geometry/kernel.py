"""Kernel hình học cho CAD tham số: khối đặc (manifold3d) + mặt tham số chính xác (numpy).

- `Solid` bọc `manifold3d.Manifold` (boolean bền vững: union/subtract/intersect, luôn trả về khối kín).
- Mặt tham số: revolve profile có fillet/chamfer, extrude, loft giữa các mặt cắt, sweep theo đường B-spline với
  khung quay tối thiểu (rotation-minimizing frames), ren helix thật theo biên dạng ISO 68-1.
- `MeshData`: lưới tam giác xuất ra viewer/GLB (đỉnh, pháp tuyến, UV). Pháp tuyến tính bởi manifold3d: cạnh sắc
  (góc > sharp_angle) được tách đỉnh để giữ cạnh, mặt cong được làm mượt (smooth shading).

Đơn vị: mm. Hệ trục khi dựng: X trước, Y trái, Z lên (đổi sang glTF ở bước xuất).
Không có exec/eval: DSL do AI tạo chỉ được biên dịch sang các hàm trong file này (xem dsl.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np

import manifold3d as m3d

from nexa.three_d.geometry import profiles as P


class GeometryError(ValueError):
    """Tham số hình học không hợp lệ hoặc phép dựng thất bại."""


# ------------------------------------------------------------------ MeshData
@dataclass
class MeshData:
    vertices: np.ndarray                     # (N, 3) float64
    faces: np.ndarray                        # (M, 3) int64
    normals: np.ndarray | None = None        # (N, 3)
    uvs: np.ndarray | None = None            # (N, 2)

    @property
    def triangle_count(self) -> int:
        return int(len(self.faces))

    @property
    def vertex_count(self) -> int:
        return int(len(self.vertices))

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if len(self.vertices) == 0:
            z = np.zeros(3)
            return z, z
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def transformed(self, matrix: np.ndarray) -> "MeshData":
        """matrix 4x4 (hoặc 3x3). Pháp tuyến biến đổi bằng ma trận nghịch đảo chuyển vị."""
        mtx = np.asarray(matrix, dtype=np.float64)
        lin = mtx[:3, :3]
        t = mtx[:3, 3] if mtx.shape == (4, 4) else np.zeros(3)
        v = self.vertices @ lin.T + t
        n = None
        if self.normals is not None:
            nm = np.linalg.inv(lin).T
            n = self.normals @ nm.T
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        faces = self.faces if np.linalg.det(lin) > 0 else self.faces[:, ::-1].copy()
        return MeshData(v, faces, n, None if self.uvs is None else self.uvs.copy())

    def copy(self) -> "MeshData":
        return MeshData(self.vertices.copy(), self.faces.copy(),
                        None if self.normals is None else self.normals.copy(),
                        None if self.uvs is None else self.uvs.copy())

    @staticmethod
    def concatenate(items: Sequence["MeshData"]) -> "MeshData":
        items = [m for m in items if m is not None and len(m.faces)]
        if not items:
            return MeshData(np.zeros((0, 3)), np.zeros((0, 3), np.int64))
        verts, faces, norms, uvs = [], [], [], []
        off = 0
        has_n = all(m.normals is not None for m in items)
        has_uv = all(m.uvs is not None for m in items)
        for m in items:
            verts.append(m.vertices)
            faces.append(m.faces + off)
            off += len(m.vertices)
            if has_n:
                norms.append(m.normals)
            if has_uv:
                uvs.append(m.uvs)
        return MeshData(np.vstack(verts), np.vstack(faces), np.vstack(norms) if has_n else None,
                        np.vstack(uvs) if has_uv else None)

    def compute_normals(self) -> "MeshData":
        """Pháp tuyến đỉnh trung bình theo diện tích (dùng khi lưới không qua manifold3d)."""
        v, f = self.vertices, self.faces
        fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        n = np.zeros_like(v)
        for k in range(3):
            np.add.at(n, f[:, k], fn)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        self.normals = n
        return self

    def with_box_uv(self, scale: float = 20.0) -> "MeshData":
        """UV chiếu hộp (box projection): mỗi mặt chọn trục trội theo pháp tuyến; đỉnh bị tách ở ranh giới trục.
        scale: mm cho một lần lặp texture."""
        v, f = self.vertices, self.faces
        fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        axis = np.argmax(np.abs(fn), axis=1)                        # 0,1,2
        key = f * 3 + axis[:, None]                                 # (đỉnh, trục) duy nhất
        uniq, inv = np.unique(key.ravel(), return_inverse=True)
        src = uniq // 3
        ax = uniq % 3
        nv = v[src]
        uv = np.empty((len(uniq), 2))
        for a in range(3):
            sel = ax == a
            others = [i for i in range(3) if i != a]
            uv[sel] = nv[sel][:, others] / scale
        normals = self.normals[src] if self.normals is not None else None
        return MeshData(nv, inv.reshape(-1, 3).astype(np.int64), normals, uv)

    def signed_volume(self) -> float:
        v, f = self.vertices, self.faces
        return float(np.einsum("ij,ij->i", v[f[:, 0]], np.cross(v[f[:, 1]], v[f[:, 2]])).sum() / 6.0)


# ------------------------------------------------------------------ biến đổi
def rotation_matrix(axis: Sequence[float], angle_deg: float) -> np.ndarray:
    a = np.asarray(axis, dtype=np.float64)
    n = np.linalg.norm(a)
    if n < 1e-12:
        return np.eye(3)
    x, y, z = a / n
    t = math.radians(angle_deg)
    c, s, C = math.cos(t), math.sin(t), 1 - math.cos(t)
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def align_matrix(src: Sequence[float], dst: Sequence[float]) -> np.ndarray:
    """Ma trận quay 3x3 đưa vector src trùng hướng dst."""
    a = np.asarray(src, float) / max(1e-12, np.linalg.norm(src))
    b = np.asarray(dst, float) / max(1e-12, np.linalg.norm(dst))
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c > 1 - 1e-12:
        return np.eye(3)
    if c < -1 + 1e-12:
        perp = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        return rotation_matrix(np.cross(a, perp), 180.0)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def affine(linear: np.ndarray | None = None, translation: Sequence[float] = (0, 0, 0)) -> np.ndarray:
    m = np.eye(4)
    if linear is not None:
        m[:3, :3] = linear
    m[:3, 3] = translation
    return m


# ------------------------------------------------------------------ Solid
class Solid:
    """Khối đặc kín (manifold). Mọi phép trả về Solid mới."""

    def __init__(self, manifold: m3d.Manifold) -> None:
        self.m = manifold

    # ----- boolean -----
    def __add__(self, other: "Solid") -> "Solid":
        return Solid(self.m + other.m)

    def __sub__(self, other: "Solid") -> "Solid":
        return Solid(self.m - other.m)

    def __and__(self, other: "Solid") -> "Solid":
        return Solid(self.m ^ other.m)

    @staticmethod
    def union_all(items: Iterable["Solid"]) -> "Solid":
        ms = [s.m for s in items if s is not None]
        if not ms:
            return Solid(m3d.Manifold())
        return Solid(m3d.Manifold.batch_boolean(ms, m3d.OpType.Add))

    def subtract_all(self, items: Iterable["Solid"]) -> "Solid":
        ms = [s.m for s in items if s is not None]
        if not ms:
            return self
        return Solid(self.m - m3d.Manifold.batch_boolean(ms, m3d.OpType.Add))

    # ----- biến đổi -----
    def translate(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> "Solid":
        return Solid(self.m.translate((float(x), float(y), float(z))))

    def moved(self, v: Sequence[float]) -> "Solid":
        return self.translate(*v)

    def rotate(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> "Solid":
        """Góc Euler (độ): quanh X rồi Y rồi Z."""
        return Solid(self.m.rotate((float(x), float(y), float(z))))

    def rotate_axis(self, axis: Sequence[float], angle_deg: float, center: Sequence[float] = (0, 0, 0)) -> "Solid":
        r = rotation_matrix(axis, angle_deg)
        c = np.asarray(center, float)
        return self.transform(affine(r, c - r @ c))

    def scale(self, sx: float, sy: float | None = None, sz: float | None = None) -> "Solid":
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        return Solid(self.m.scale((float(sx), float(sy), float(sz))))

    def mirror(self, normal: Sequence[float]) -> "Solid":
        return Solid(self.m.mirror(tuple(float(x) for x in normal)))

    def transform(self, matrix: np.ndarray) -> "Solid":
        mtx = np.asarray(matrix, dtype=np.float64)
        if mtx.shape == (4, 4):
            mtx = mtx[:3, :]
        return Solid(self.m.transform(mtx))

    def align_z(self, direction: Sequence[float], origin: Sequence[float] = (0, 0, 0)) -> "Solid":
        """Quay trục +Z của khối theo `direction` rồi dời gốc tới `origin`."""
        return self.transform(affine(align_matrix((0, 0, 1), direction), origin))

    def warp(self, fn: Callable[[np.ndarray], np.ndarray]) -> "Solid":
        return Solid(self.m.warp_batch(lambda pts: np.asarray(fn(np.asarray(pts)), dtype=np.float64)))

    # ----- làm mượt / đơn giản hóa -----
    def smooth(self, refine: int = 3, sharp_angle: float = 60.0) -> "Solid":
        """Bề mặt chia nhỏ mượt (subdivision theo tiếp tuyến) — biến lồng thô thành vỏ cong liền mạch."""
        return Solid(self.m.smooth_out(sharp_angle, 0.0).refine(max(1, int(refine))))

    def refine_to_length(self, length: float) -> "Solid":
        return Solid(self.m.refine_to_length(float(length)))

    def simplify(self, tolerance: float) -> "Solid":
        return Solid(self.m.simplify(float(tolerance)))

    def hull(self) -> "Solid":
        return Solid(self.m.hull())

    # ----- truy vấn -----
    @property
    def is_empty(self) -> bool:
        return self.m.is_empty()

    @property
    def status_ok(self) -> bool:
        return self.m.status() == m3d.Error.NoError

    def volume(self) -> float:
        return float(self.m.volume())

    def surface_area(self) -> float:
        return float(self.m.surface_area())

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        b = np.asarray(self.m.bounding_box(), dtype=np.float64)
        return b[:3], b[3:]

    @property
    def triangle_count(self) -> int:
        return int(self.m.num_tri())

    def intersection_volume(self, other: "Solid") -> float:
        return float((self.m ^ other.m).volume())

    def split_components(self) -> list["Solid"]:
        return [Solid(x) for x in self.m.decompose()]

    def to_mesh(self, sharp_angle: float = 40.0, simplify: bool = True) -> MeshData:
        """Lưới có pháp tuyến: cạnh có góc nhị diện > sharp_angle được giữ sắc (tách đỉnh).
        simplify=False: bỏ bước gộp tam giác mảnh (khối gồm nhiều chi tiết nhỏ rải rộng như bu-lông của cả giàn — dung sai
        theo kích thước bao sẽ làm méo vát cạnh và rất chậm)."""
        if self.is_empty:
            return MeshData(np.zeros((0, 3)), np.zeros((0, 3), np.int64), np.zeros((0, 3)))
        mm = self.m.set_properties(0, lambda p, old: []) if self.m.num_prop() else self.m
        # Gộp các tam giác mảnh do boolean mặt gần đồng phẳng sinh ra (dung sai ~1/50 000 kích thước: không thấy được).
        lo, hi = self.bounds()
        size = float(np.max(hi - lo)) if np.all(np.isfinite(hi - lo)) else 0.0
        if size > 0 and simplify:
            mm = mm.simplify(size * 2e-5)
        # calculate_normals trên khối gồm rất nhiều mảnh rời (bu-lông cả giàn, tà vẹt…) chậm bất thường (250 mảnh: 19 s);
        # tách mảnh rồi tính riêng từng mảnh: < 1 s
        pieces = mm.decompose() if mm.num_tri() > 2000 else [mm]
        if len(pieces) > 16:
            vps, tvs, off = [], [], 0
            for pc in pieces:
                me = pc.calculate_normals(0, float(sharp_angle)).to_mesh()
                vp_ = np.asarray(me.vert_properties, dtype=np.float64)
                vps.append(vp_)
                tvs.append(np.asarray(me.tri_verts, dtype=np.int64) + off)
                off += len(vp_)
            vp, tv = np.vstack(vps), np.vstack(tvs)
        else:
            mm = mm.calculate_normals(0, float(sharp_angle))
            mesh = mm.to_mesh64() if hasattr(mm, "to_mesh64") else mm.to_mesh()
            vp = np.asarray(mesh.vert_properties, dtype=np.float64)
            tv = np.asarray(mesh.tri_verts, dtype=np.int64)
        n = vp[:, 3:6]
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        v = vp[:, :3].copy()
        # bỏ tam giác thẳng hàng (T-junction của boolean): diện tích ≈ 0, không đóng góp hình dạng hiển thị
        a, b, c = v[tv[:, 0]], v[tv[:, 1]], v[tv[:, 2]]
        area2 = np.linalg.norm(np.cross(b - a, c - a), axis=1)
        e2 = np.maximum.reduce([np.sum((b - a) ** 2, 1), np.sum((c - b) ** 2, 1), np.sum((a - c) ** 2, 1)])
        tv = tv[area2 > 2e-7 * e2 + 1e-30]
        return MeshData(v, tv, n)


def from_mesh(vertices: np.ndarray, faces: np.ndarray) -> Solid:
    """Tạo Solid từ lưới kín đã gộp đỉnh. Tự lật mặt nếu hướng pháp tuyến quay vào trong."""
    v = np.ascontiguousarray(vertices, dtype=np.float64)
    f = np.ascontiguousarray(faces, dtype=np.int64)
    if MeshData(v, f).signed_volume() < 0:
        f = np.ascontiguousarray(f[:, ::-1])
    if hasattr(m3d, "Mesh64"):
        mesh = m3d.Mesh64(vert_properties=v, tri_verts=f.astype(np.uint64))
    else:  # pragma: no cover
        mesh = m3d.Mesh(vert_properties=v.astype(np.float32), tri_verts=f.astype(np.uint32))
    solid = Solid(m3d.Manifold(mesh))
    if not solid.status_ok or solid.is_empty:
        raise GeometryError(f"lưới không kín/không hợp lệ ({solid.m.status()})")
    return solid


# ------------------------------------------------------------------ khối cơ bản
def _seg(radius: float, segments: int | None, fine: float = 1.0) -> int:
    if segments:
        return max(8, int(segments))
    # đủ mịn để không thấy cạnh đa giác ở khoảng cách xem thông thường
    return int(np.clip(24 + radius * 1.6 * fine, 24, 160)) // 4 * 4


def box(sx: float, sy: float, sz: float, center: bool = True) -> Solid:
    if min(sx, sy, sz) <= 0:
        raise GeometryError("kích thước hộp phải dương")
    return Solid(m3d.Manifold.cube((float(sx), float(sy), float(sz)), center))


def rounded_box(sx: float, sy: float, sz: float, radius: float, segments: int | None = None) -> Solid:
    """Hộp bo tròn MỌI cạnh bán kính `radius` (bao lồi của 8 hình cầu)."""
    r = float(min(radius, sx / 2 * 0.999, sy / 2 * 0.999, sz / 2 * 0.999))
    if r <= 1e-6:
        return box(sx, sy, sz)
    seg = segments or _seg(r, None, 3.0)
    s = m3d.Manifold.sphere(r, seg)
    corners = [s.translate((x * (sx / 2 - r), y * (sy / 2 - r), z * (sz / 2 - r)))
               for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    return Solid(m3d.Manifold.batch_hull(corners))


def chamfer_box(sx: float, sy: float, sz: float, chamfer: float) -> Solid:
    """Hộp vát mọi cạnh 45° một khoảng `chamfer`."""
    c = float(min(chamfer, sx / 2 * 0.999, sy / 2 * 0.999, sz / 2 * 0.999))
    pts = []
    for x in (-1, 1):
        for y in (-1, 1):
            for z in (-1, 1):
                pts += [(x * (sx / 2 - c), y * sy / 2, z * sz / 2), (x * sx / 2, y * (sy / 2 - c), z * sz / 2),
                        (x * sx / 2, y * sy / 2, z * (sz / 2 - c))]
                pts += [(x * (sx / 2 - c), y * (sy / 2 - c), z * sz / 2), (x * sx / 2, y * (sy / 2 - c), z * (sz / 2 - c)),
                        (x * (sx / 2 - c), y * sy / 2, z * (sz / 2 - c))]
    return hull_points(pts)


def cylinder(radius: float, height: float, radius_top: float | None = None, segments: int | None = None,
             center: bool = False) -> Solid:
    """Trụ/nón cụt dọc trục Z."""
    if radius <= 0 or height <= 0:
        raise GeometryError("trụ cần bán kính và chiều cao dương")
    rt = radius if radius_top is None else max(0.0, float(radius_top))
    return Solid(m3d.Manifold.cylinder(float(height), float(radius), rt, _seg(max(radius, rt), segments), center))


def cone(radius: float, height: float, radius_top: float = 0.0, segments: int | None = None) -> Solid:
    return cylinder(radius, height, radius_top, segments)


def sphere(radius: float, segments: int | None = None) -> Solid:
    if radius <= 0:
        raise GeometryError("bán kính cầu phải dương")
    return Solid(m3d.Manifold.sphere(float(radius), _seg(radius, segments, 2.0)))


def ellipsoid(rx: float, ry: float, rz: float, segments: int | None = None) -> Solid:
    r = max(rx, ry, rz)
    return sphere(1.0, segments or _seg(r, None, 2.0)).scale(rx, ry, rz)


def capsule(radius: float, length: float, segments: int | None = None) -> Solid:
    """Viên nhộng dọc trục Z, tổng chiều dài `length` (kể cả hai bán cầu), tâm ở gốc."""
    body = max(1e-3, length - 2 * radius)
    seg = _seg(radius, segments, 2.0)
    prof = [(0.0, -body / 2 - radius)]
    for a in np.linspace(-math.pi / 2, 0, seg // 4 + 1)[1:]:
        prof.append((radius * math.cos(a), -body / 2 + radius * math.sin(a)))
    for a in np.linspace(0, math.pi / 2, seg // 4 + 1)[:-1]:
        prof.append((radius * math.cos(a), body / 2 + radius * math.sin(a)))
    prof.append((0.0, body / 2 + radius))
    return revolve(prof, segments=seg)


def torus(major: float, minor: float, segments: int | None = None, tube_segments: int = 24) -> Solid:
    circle_pts = P.circle(minor, tube_segments, center=(major, 0.0))
    return revolve(circle_pts, segments=_seg(major + minor, segments))


def hull_points(points) -> Solid:
    s = Solid(m3d.Manifold.hull_points(np.asarray(points, dtype=np.float64)))
    if s.is_empty:
        raise GeometryError("bao lồi rỗng (điểm đồng phẳng?)")
    return s


def hull(solids: Sequence[Solid]) -> Solid:
    return Solid(m3d.Manifold.batch_hull([s.m for s in solids]))


# ------------------------------------------------------------------ từ profile 2D
def _cross_section(polygons) -> m3d.CrossSection:
    if isinstance(polygons, np.ndarray) and polygons.ndim == 2:
        polygons = [polygons]
    polys = [np.ascontiguousarray(p, dtype=np.float64) for p in polygons]
    if not polys or any(len(p) < 3 for p in polys):
        raise GeometryError("profile cần ít nhất 3 điểm")
    return m3d.CrossSection(polys, m3d.FillRule.EvenOdd)


def revolve(profile, segments: int | None = None, degrees: float = 360.0) -> Solid:
    """Xoay profile [(r, z), …] (r ≥ 0) quanh trục Z. Profile có thể đã bo/vát bằng profiles.fillet_polygon."""
    prof = np.asarray(profile, dtype=np.float64)
    if prof.ndim != 2 or len(prof) < 3:
        raise GeometryError("profile revolve cần ≥ 3 điểm (r, z)")
    prof = prof.copy()
    prof[:, 0] = np.maximum(prof[:, 0], 0.0)
    rmax = float(prof[:, 0].max())
    s = Solid(m3d.Manifold.revolve(_cross_section(P.ensure_ccw(prof)), _seg(rmax, segments), float(degrees)))
    if s.is_empty:
        raise GeometryError("revolve rỗng")
    return s


def extrude(polygons, height: float, twist_deg: float = 0.0, scale_top: Sequence[float] = (1.0, 1.0),
            divisions: int = 0, center: bool = False) -> Solid:
    """Đùn đa giác 2D (có thể nhiều vòng, vòng trong = lỗ theo luật even-odd) dọc +Z."""
    if height <= 0:
        raise GeometryError("chiều cao đùn phải dương")
    s = Solid(m3d.Manifold.extrude(_cross_section(polygons), float(height), int(divisions), float(twist_deg),
                                   (float(scale_top[0]), float(scale_top[1]))))
    if s.is_empty:
        raise GeometryError("extrude rỗng")
    return s.translate(0, 0, -height / 2) if center else s


# ------------------------------------------------------------------ loft / sweep
def _project_loop(pts: np.ndarray) -> np.ndarray:
    c = pts.mean(axis=0)
    q = pts - c
    # pháp tuyến Newell
    n = np.zeros(3)
    for i in range(len(q)):
        a, b = q[i], q[(i + 1) % len(q)]
        n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    if np.linalg.norm(n) < 1e-12:
        _, _, vt = np.linalg.svd(q)
        n = vt[2]
    n /= np.linalg.norm(n)
    u = q[np.argmax(np.linalg.norm(q, axis=1))]
    u = u - n * np.dot(u, n)
    if np.linalg.norm(u) < 1e-12:
        u = np.cross(n, [1, 0, 0]) if abs(n[0]) < 0.9 else np.cross(n, [0, 1, 0])
    u /= np.linalg.norm(u)
    w = np.cross(n, u)
    return np.column_stack([q @ u, q @ w])


def _cap_faces(loop: np.ndarray, pts3: np.ndarray, along_index_order: bool) -> np.ndarray:
    p2 = _project_loop(pts3[loop])
    area = P.signed_area(p2)
    order = loop if area > 0 else loop[::-1]
    p2o = p2 if area > 0 else p2[::-1]
    tris = np.asarray(m3d.triangulate([np.ascontiguousarray(p2o)]), dtype=np.int64)
    if len(tris) == 0:
        raise GeometryError("không tam giác hóa được nắp loft")
    faces = order[tris]
    if (area > 0) != along_index_order:
        faces = faces[:, ::-1]
    return faces


def loft_mesh(sections: Sequence[np.ndarray], cap_start: bool = True, cap_end: bool = True,
              closed: bool = False) -> MeshData:
    """Nối các mặt cắt kín (mỗi mặt cắt (M,3), cùng M, thứ tự điểm tương ứng). Mặt cắt co về một điểm
    (kích thước ≈ 0) trở thành đỉnh nhọn. closed=True: nối mặt cắt cuối về đầu (hình xuyến)."""
    secs = [np.asarray(s, dtype=np.float64) for s in sections]
    if len(secs) < 2:
        raise GeometryError("loft cần ít nhất 2 mặt cắt")
    m = len(secs[0])
    if m < 3 or any(len(s) != m for s in secs):
        raise GeometryError("các mặt cắt loft phải cùng số điểm (≥ 3)")
    verts: list[np.ndarray] = []
    starts: list[int] = []
    apex: list[bool] = []
    off = 0
    for s in secs:
        ext = float(np.ptp(s, axis=0).max())
        is_apex = ext < 1e-7
        starts.append(off)
        apex.append(is_apex)
        verts.append(s[:1] if is_apex else s)
        off += 1 if is_apex else m
    V = np.vstack(verts)
    faces: list[np.ndarray] = []
    j = np.arange(m)
    jn = (j + 1) % m
    pairs = [(i, i + 1) for i in range(len(secs) - 1)]
    if closed:
        pairs.append((len(secs) - 1, 0))
    for i0, i1 in pairs:
        a = np.full(m, starts[i0]) if apex[i0] else starts[i0] + j
        b = np.full(m, starts[i0]) if apex[i0] else starts[i0] + jn
        c = np.full(m, starts[i1]) if apex[i1] else starts[i1] + jn
        d = np.full(m, starts[i1]) if apex[i1] else starts[i1] + j
        if apex[i0] and apex[i1]:
            raise GeometryError("hai mặt cắt nhọn liền nhau")
        if not apex[i0]:
            faces.append(np.column_stack([a, b, c]) if not apex[i1] else np.column_stack([a, b, c]))
        if not apex[i1]:
            faces.append(np.column_stack([a, c, d]))
    if not closed:
        if cap_start and not apex[0]:
            faces.append(_cap_faces(starts[0] + j, V, along_index_order=False))
        if cap_end and not apex[-1]:
            faces.append(_cap_faces(starts[-1] + j, V, along_index_order=True))
    F = np.vstack(faces)
    mesh = MeshData(V, F)
    if mesh.signed_volume() < 0:
        mesh.faces = F[:, ::-1].copy()
    return mesh


def loft(sections: Sequence[np.ndarray], closed: bool = False) -> Solid:
    return from_mesh(*_vf(loft_mesh(sections, closed=closed)))


def _vf(mesh: MeshData) -> tuple[np.ndarray, np.ndarray]:
    return mesh.vertices, mesh.faces


def section_on_plane(profile2d: np.ndarray, origin: Sequence[float], normal_axis: Sequence[float],
                     x_axis: Sequence[float]) -> np.ndarray:
    """Đặt profile 2D (x, y) vào mặt phẳng có gốc `origin`, trục x = x_axis, trục y = normal × x."""
    n = np.asarray(normal_axis, float)
    n /= np.linalg.norm(n)
    xa = np.asarray(x_axis, float)
    xa = xa - n * np.dot(xa, n)
    xa /= np.linalg.norm(xa)
    ya = np.cross(n, xa)
    p = np.asarray(profile2d, float)
    return np.asarray(origin, float) + p[:, :1] * xa + p[:, 1:2] * ya


def rotation_minimizing_frames(path: np.ndarray, up: Sequence[float] = (0, 0, 1)) -> tuple[np.ndarray, np.ndarray,
                                                                                           np.ndarray]:
    """Khung dọc đường (T, N, B) theo phương pháp phản xạ kép (Wang 2008) — không xoắn bất thường."""
    p = np.asarray(path, dtype=np.float64)
    k = len(p)
    if k < 2:
        raise GeometryError("đường sweep cần ≥ 2 điểm")
    T = np.gradient(p, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    upv = np.asarray(up, float)
    n0 = upv - T[0] * np.dot(upv, T[0])
    if np.linalg.norm(n0) < 1e-6:
        alt = np.array([1.0, 0, 0]) if abs(T[0][0]) < 0.9 else np.array([0, 1.0, 0])
        n0 = alt - T[0] * np.dot(alt, T[0])
    N = np.zeros_like(p)
    N[0] = n0 / np.linalg.norm(n0)
    for i in range(k - 1):
        v1 = p[i + 1] - p[i]
        c1 = float(np.dot(v1, v1))
        if c1 < 1e-18:
            N[i + 1] = N[i]
            continue
        rL = N[i] - (2 / c1) * np.dot(v1, N[i]) * v1
        tL = T[i] - (2 / c1) * np.dot(v1, T[i]) * v1
        v2 = T[i + 1] - tL
        c2 = float(np.dot(v2, v2))
        N[i + 1] = rL if c2 < 1e-18 else rL - (2 / c2) * np.dot(v2, rL) * v2
        N[i + 1] /= max(1e-12, np.linalg.norm(N[i + 1]))
    B = np.cross(T, N)
    return T, N, B


def sweep(profile2d: np.ndarray, path: np.ndarray, scales: Sequence[float] | np.ndarray | None = None,
          twist_deg: float = 0.0, up: Sequence[float] = (0, 0, 1), caps: bool = True) -> Solid:
    """Quét profile 2D (kín) dọc đường 3D. scales: hệ số tỷ lệ theo từng điểm đường (thuôn dần)."""
    prof = P.ensure_ccw(profile2d)
    path = np.asarray(path, dtype=np.float64)
    T, N, B = rotation_minimizing_frames(path, up)
    k = len(path)
    sc = np.ones(k) if scales is None else np.asarray(scales, dtype=np.float64)
    secs = []
    for i in range(k):
        ang = math.radians(twist_deg) * i / max(1, k - 1)
        ca, sa = math.cos(ang), math.sin(ang)
        x = (prof[:, 0] * ca - prof[:, 1] * sa) * sc[i]
        y = (prof[:, 0] * sa + prof[:, 1] * ca) * sc[i]
        secs.append(path[i] + x[:, None] * N[i] + y[:, None] * B[i])
    return from_mesh(*_vf(loft_mesh(secs, cap_start=caps, cap_end=caps)))


def tube(path: np.ndarray, radius: float, segments: int = 20, scales=None, rounded_ends: bool = False) -> Solid:
    """Ống tròn đặc dọc đường (càng đáp, thanh treo, dây)."""
    body = sweep(P.circle(radius, segments), path, scales)
    if not rounded_ends:
        return body
    p = np.asarray(path, float)
    s0 = radius * (1 if scales is None else float(np.asarray(scales)[0]))
    s1 = radius * (1 if scales is None else float(np.asarray(scales)[-1]))
    return Solid.union_all([body, sphere(s0, segments).moved(p[0]), sphere(s1, segments).moved(p[-1])])


# ------------------------------------------------------------------ ren helix thật (ISO 68-1)
ISO_THREAD_DEPTH = 0.541266   # chiều sâu ren cơ bản / bước ren: 5H/8 với H = 0,866025·P


def iso_basic_radius(phase: np.ndarray, pitch: float, major_radius: float, depth: float | None = None) -> np.ndarray:
    """Bán kính biên dạng ren ngoài cơ bản ISO 68-1 theo pha dọc trục (mm).

    Đỉnh ren phẳng rộng P/8 tại đường kính lớn, chân ren phẳng rộng P/4 tại đường kính nhỏ cơ bản
    d1 = d − 1,082532·P, sườn ren nghiêng 30° (góc ren 60°).
    """
    d = ISO_THREAD_DEPTH * pitch if depth is None else depth
    u = (np.asarray(phase) + pitch / 2) % pitch - pitch / 2          # ∈ [-P/2, P/2), 0 = tâm đỉnh ren
    x = (np.abs(u) - pitch / 16) / (5 * pitch / 16)
    return major_radius - d * np.clip(x, 0.0, 1.0)


def threaded_rod_mesh(major_d: float, pitch: float, length: float, thread_length: float | None = None,
                      tip_chamfer: bool = True, samples_per_pitch: int = 24, angular_segments: int = 96,
                      runout_pitches: float = 2.0, top_overlap: float = 0.0, left_hand: bool = False) -> MeshData:
    """Thân bu-lông có ren helix thật: trục Z, đầu ren (mút) ở z=0, phía đầu bu-lông ở z=length(+top_overlap).

    Đỉnh ren nằm trên đường xoắn ốc z = k·P + P·θ/2π (ren phải). Đoạn không ren (nếu thread_length < length) có
    đường kính danh nghĩa. Ren thoát dần trong `runout_pitches` bước. Mút ren vát 45° xuống đường kính nhỏ.
    """
    if major_d <= 0 or pitch <= 0 or length <= 0:
        raise GeometryError("đường kính, bước ren và chiều dài phải dương")
    if pitch > major_d / 2:
        raise GeometryError("bước ren quá lớn so với đường kính")
    R = major_d / 2
    depth = ISO_THREAD_DEPTH * pitch
    r_minor = R - depth
    tl = length if thread_length is None else min(length, max(pitch, thread_length))
    z_top = length + top_overlap
    rows = max(8, int(math.ceil(z_top / pitch * samples_per_pitch)) + 1)
    zs = np.linspace(0.0, z_top, rows)
    th = np.linspace(0, 2 * math.pi, angular_segments, endpoint=False)
    Z, TH = np.meshgrid(zs, th, indexing="ij")
    hand = -1.0 if left_hand else 1.0
    phase = Z - hand * pitch * TH / (2 * math.pi)
    r_thread = iso_basic_radius(phase, pitch, R, depth)
    # thoát ren: độ sâu giảm tuyến tính về 0 trong runout, phía trên là thân trơn
    run = max(1e-6, runout_pitches * pitch)
    fade = np.clip((tl - Z) / run + 1.0, 0.0, 1.0) if tl < length else np.ones_like(Z)
    fade = np.where(Z <= tl - run, 1.0, np.clip((tl - Z) / run, 0.0, 1.0)) if tl < length else fade
    r = R - (R - r_thread) * fade
    if tip_chamfer:
        tip_r = r_minor - 0.05 * pitch
        r = np.minimum(r, tip_r + Z)                                   # vát 45°
    X = r * np.cos(TH)
    Y = r * np.sin(TH)
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    n_th = angular_segments
    i = np.arange(rows - 1)[:, None]
    j = np.arange(n_th)[None, :]
    a = i * n_th + j
    b = i * n_th + (j + 1) % n_th
    c = (i + 1) * n_th + (j + 1) % n_th
    d = (i + 1) * n_th + j
    faces = np.vstack([np.column_stack([a.ravel(), b.ravel(), c.ravel()]),
                       np.column_stack([a.ravel(), c.ravel(), d.ravel()])])
    # nắp dưới và nắp trên: quạt về tâm
    c0 = len(verts)
    c1 = c0 + 1
    verts = np.vstack([verts, [0.0, 0.0, 0.0], [0.0, 0.0, z_top]])
    jj = np.arange(n_th)
    bottom = np.column_stack([np.full(n_th, c0), (jj + 1) % n_th, jj])
    top_base = (rows - 1) * n_th
    top = np.column_stack([np.full(n_th, c1), top_base + jj, top_base + (jj + 1) % n_th])
    faces = np.vstack([faces, bottom, top]).astype(np.int64)
    mesh = MeshData(verts, faces)
    if mesh.signed_volume() < 0:
        mesh.faces = faces[:, ::-1].copy()
    return mesh


def threaded_rod(major_d: float, pitch: float, length: float, **kw) -> Solid:
    return from_mesh(*_vf(threaded_rod_mesh(major_d, pitch, length, **kw)))


def internal_thread_cutter(major_d: float, pitch: float, length: float, **kw) -> Solid:
    """Khối dùng để khoét ren trong (đai ốc): ren ngoài nở thêm khe hở nhỏ."""
    kw.setdefault("tip_chamfer", False)
    return threaded_rod(major_d + 0.1 * pitch, pitch, length, **kw)


# ------------------------------------------------------------------ tiện ích
def radial_array(solid: Solid, count: int, axis: Sequence[float] = (0, 0, 1), start_deg: float = 0.0) -> list[Solid]:
    return [solid.rotate_axis(axis, start_deg + 360.0 * k / count) for k in range(count)]


def union_mesh(meshes: Sequence[MeshData]) -> MeshData:
    return MeshData.concatenate(list(meshes))


@dataclass
class Shape:
    """Một primitive của bộ phận: khối đặc + id vật liệu (một bộ phận có thể gồm nhiều Shape)."""
    solid: Solid | None
    material: str
    sharp_angle: float = 40.0
    mesh: MeshData | None = None          # lưới sẵn (khi không qua manifold)
    uv_scale: float = 0.0                 # > 0: tạo UV chiếu hộp (vật liệu có texture)
    extra: dict = field(default_factory=dict)

    def to_mesh(self) -> MeshData:
        mesh = self.mesh if self.mesh is not None else self.solid.to_mesh(self.sharp_angle, self.extra.get("simplify", True))
        if self.uv_scale > 0 and mesh.uvs is None and len(mesh.faces):
            mesh = mesh.with_box_uv(self.uv_scale)
        return mesh
