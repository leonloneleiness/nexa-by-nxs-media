"""Bộ dựng assembly dùng chung cho các template tham số.

Template khai báo bộ phận trong hệ kỹ thuật (X trước, Y trái, Z lên; mm) kèm metadata lắp ráp: cha, trục khớp,
hướng/khoảng/thứ tự tách. `build()` tạo lưới có pháp tuyến, đổi sang hệ asset (glTF) và giữ khối đặc (hệ kỹ thuật)
để kiểm tra giao nhau/khoảng hở trong quality.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from nexa.three_d.geometry.kernel import MeshData, Shape, Solid
from nexa.three_d.models import Bounds, ExplosionStep, Material, Part3D, ros_to_asset

_ROS_TO_ASSET4 = np.eye(4)
_ROS_TO_ASSET4[:3, :3] = ros_to_asset(np.eye(3)).T   # cột = ảnh của các trục kỹ thuật


def _unit(v: Sequence[float]) -> np.ndarray:
    a = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(a)
    return a / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])


@dataclass
class PartDraft:
    id: str
    name_vi: str
    name_en: str
    category: str
    shapes: list[Shape]
    parent_id: str | None = None
    aliases: list[str] = field(default_factory=list)
    function: str = ""
    position_tag: str = ""
    group: str = ""
    joint_axis: Sequence[float] | None = None     # hệ kỹ thuật
    explode_dir: Sequence[float] = (0, 0, 1)      # hệ kỹ thuật
    explode_distance: float = 0.0
    explode_order: int = 0
    pivot: Sequence[float] | None = None          # hệ kỹ thuật; None = tâm hộp bao
    dimensions: dict[str, float] = field(default_factory=dict)
    required: bool = False
    confidence: float = 1.0
    no_clash_with: list[str] = field(default_factory=list)   # bộ phận không được giao nhau (vd cánh quạt ↔ thân)


@dataclass
class BuiltPart:
    part: Part3D
    meshes: list[tuple[MeshData, str]]            # hệ asset, mm
    solid: Solid | None                           # hệ kỹ thuật (hợp các shape), để kiểm tra
    no_clash_with: list[str]


@dataclass
class BuiltAssembly:
    name: str
    category: str
    parts: list[BuiltPart]
    materials: dict[str, Material]
    explosion_plan: list[ExplosionStep]
    bounds: Bounds
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def part(self, pid: str) -> BuiltPart | None:
        return next((p for p in self.parts if p.part.id == pid), None)

    @property
    def triangle_count(self) -> int:
        return sum(p.part.triangles for p in self.parts)


class AssemblyBuilder:
    def __init__(self, name: str, category: str, materials: dict[str, Material]) -> None:
        self.name = name
        self.category = category
        self.materials = materials
        self.drafts: list[PartDraft] = []
        self.plan_notes: dict[int, str] = {}
        self.metadata: dict = {}
        self.warnings: list[str] = []

    def add(self, pid: str, name_vi: str, name_en: str, category: str, shapes: Sequence[Shape] | Shape,
            **kw) -> PartDraft:
        if any(d.id == pid for d in self.drafts):
            raise ValueError(f"trùng id bộ phận {pid}")
        shapes = [shapes] if isinstance(shapes, Shape) else list(shapes)
        for s in shapes:
            if s.material not in self.materials:
                raise ValueError(f"vật liệu {s.material} chưa khai báo")
        d = PartDraft(pid, name_vi, name_en, category, shapes, **kw)
        self.drafts.append(d)
        return d

    def cut(self, pid: str, cutter: Solid) -> None:
        """Khoét `cutter` khỏi mọi khối của bộ phận đã thêm (vd. lỗ trên vỏ cho chân càng đi xuyên)."""
        d = next((x for x in self.drafts if x.id == pid), None)
        if d is None:
            return
        for s in d.shapes:
            if s.solid is not None:
                s.solid = s.solid - cutter

    def note_stage(self, order: int, text: str) -> None:
        self.plan_notes[order] = text

    def translate_all(self, dx: float, dy: float, dz: float) -> None:
        for d in self.drafts:
            for s in d.shapes:
                if s.solid is not None:
                    s.solid = s.solid.translate(dx, dy, dz)
                elif s.mesh is not None:
                    s.mesh = s.mesh.transformed(np.array([[1, 0, 0, dx], [0, 1, 0, dy], [0, 0, 1, dz], [0, 0, 0, 1.0]]))
            if d.pivot is not None:
                d.pivot = tuple(float(a + b) for a, b in zip(d.pivot, (dx, dy, dz)))

    def rotate_all_z(self, deg: float) -> None:
        """Quay toàn bộ assembly quanh trục Z (khối, tâm xoay, hướng tách, trục khớp) — dùng khi template dựng theo hệ
        trục tiện cho hình học rồi đưa về quy ước X là mặt trước."""
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        rz = lambda v: (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])   # noqa: E731
        for d in self.drafts:
            for sh in d.shapes:
                if sh.solid is not None:
                    sh.solid = sh.solid.rotate(0, 0, deg)
                elif sh.mesh is not None:
                    sh.mesh = sh.mesh.transformed(np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]))
            d.explode_dir = tuple(float(x) for x in rz(d.explode_dir))
            if d.joint_axis is not None:
                d.joint_axis = tuple(float(x) for x in rz(d.joint_axis))
            if d.pivot is not None:
                d.pivot = tuple(float(x) for x in rz(d.pivot))

    def place_on_ground(self, center_xy: bool = True) -> tuple[float, float, float]:
        """Dời cả assembly để điểm thấp nhất nằm ở z = 0 (và căn giữa X/Y). Trả vector đã dời."""
        los, his = [], []
        for d in self.drafts:
            for s in d.shapes:
                if s.solid is not None and not s.solid.is_empty:
                    lo, hi = s.solid.bounds()
                    los.append(lo)
                    his.append(hi)
        if not los:
            return 0.0, 0.0, 0.0
        lo, hi = np.min(los, axis=0), np.max(his, axis=0)
        shift = (-(lo[0] + hi[0]) / 2 if center_xy else 0.0, -(lo[1] + hi[1]) / 2 if center_xy else 0.0, -lo[2])
        self.translate_all(*shift)
        return shift

    def build(self) -> BuiltAssembly:
        built: list[BuiltPart] = []
        ids = {d.id for d in self.drafts}
        for d in self.drafts:
            if d.parent_id is not None and d.parent_id not in ids:
                raise ValueError(f"bộ phận {d.id} có cha không tồn tại {d.parent_id}")
            meshes: list[tuple[MeshData, str]] = []
            solids: list[Solid] = []
            for s in d.shapes:
                mesh = s.to_mesh()
                if mesh.triangle_count == 0:
                    continue
                mat = self.materials[s.material]
                if mesh.uvs is None and mat.textures:
                    # vật liệu có texture (vân kim loại chải, sơn, cao su…) → UV chiếu hộp theo kích thước thật
                    from nexa.three_d.geometry.materials import texture_tile_mm
                    mesh = mesh.with_box_uv(texture_tile_mm(mat))
                meshes.append((mesh.transformed(_ROS_TO_ASSET4), s.material))
                if s.solid is not None:
                    solids.append(s.solid)
            if not meshes:
                raise ValueError(f"bộ phận {d.id} rỗng")
            allv = np.vstack([m.vertices for m, _ in meshes])
            bounds = Bounds.of_points(allv)
            pivot = ros_to_asset(d.pivot).tolist() if d.pivot is not None else bounds.center
            part = Part3D(
                id=d.id, name_vi=d.name_vi, name_en=d.name_en, aliases=list(d.aliases), category=d.category,
                parent_id=d.parent_id, pivot=[float(x) for x in pivot], bounds=bounds,
                dimensions={k: round(float(v), 3) for k, v in d.dimensions.items()},
                material=d.shapes[0].material, function=d.function, position_tag=d.position_tag,
                joint_axis=ros_to_asset(_unit(d.joint_axis)).tolist() if d.joint_axis is not None else None,
                explode_vector=ros_to_asset(_unit(d.explode_dir)).tolist(),
                explode_distance=float(d.explode_distance), explode_order=int(d.explode_order),
                confidence=float(d.confidence), group=d.group, required=bool(d.required),
                triangles=sum(m.triangle_count for m, _ in meshes))
            size = bounds.size
            # kích thước hộp bao: length = trước-sau (asset Z), width = trái-phải (asset X), height = cao (asset Y)
            for key, val in (("length", size[2]), ("width", size[0]), ("height", size[1])):
                part.dimensions.setdefault(key, round(float(val), 2))
            solid = Solid.union_all(solids) if solids else None
            built.append(BuiltPart(part, meshes, solid, list(d.no_clash_with)))
        orders = sorted({b.part.explode_order for b in built if b.part.explode_distance > 0})
        plan = [ExplosionStep(o, [b.part.id for b in built if b.part.explode_order == o and b.part.explode_distance > 0],
                              self.plan_notes.get(o, "")) for o in orders]
        total = Bounds.union([b.part.bounds for b in built])
        used = {m for b in built for _, m in b.meshes}
        mats = {k: v for k, v in self.materials.items() if k in used}
        return BuiltAssembly(self.name, self.category, built, mats, plan, total, dict(self.metadata),
                             list(self.warnings))


# ------------------------------------------------------------------ vị trí theo góc
def position_tag_for_angle(deg: float, n: int) -> str:
    """Góc quanh trục Z (0° = phía trước, 90° = bên trái) → nhãn vị trí."""
    a = deg % 360
    names = [(0, "front"), (45, "front_left"), (90, "left"), (135, "rear_left"), (180, "rear"), (225, "rear_right"),
             (270, "right"), (315, "front_right"), (360, "front")]
    best = min(names, key=lambda x: abs(x[0] - a))
    return best[1]


POSITION_VI = {
    "front": "trước", "rear": "sau", "left": "trái", "right": "phải", "front_left": "trước trái",
    "front_right": "trước phải", "rear_left": "sau trái", "rear_right": "sau phải", "top": "trên", "bottom": "dưới",
    "center": "giữa", "middle_left": "giữa trái", "middle_right": "giữa phải",
}
POSITION_EN = {
    "front": "front", "rear": "rear", "left": "left", "right": "right", "front_left": "front left",
    "front_right": "front right", "rear_left": "rear left", "rear_right": "rear right", "top": "top",
    "bottom": "bottom", "center": "center", "middle_left": "middle left", "middle_right": "middle right",
}
