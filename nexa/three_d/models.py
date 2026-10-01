"""Kiểu dữ liệu mô hình 3D: dự án, bộ phận, vật liệu, trạng thái job.

Quy ước (ghi trong manifest, viewer dùng trực tiếp):
- Đơn vị manifest: mm. Hệ trục manifest = hệ trục glTF: +Y lên trên, +Z là phía TRƯỚC của vật thể, +X là bên TRÁI
  của vật thể (nhìn từ vật thể). Tệp GLB tính bằng mét theo chuẩn glTF 2.0.
- Template sinh hình trong hệ "kỹ thuật" (X trước, Y trái, Z lên) rồi đổi một lần duy nhất ở `ros_to_asset`.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

import numpy as np

GENERATOR_VERSION = "nexa-3d/1.2-product-studies"


class JobState(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    GENERATING_REFERENCE = "generating_reference"
    GENERATING_GEOMETRY = "generating_geometry"
    TEXTURING = "texturing"
    SEGMENTING = "segmenting"
    VALIDATING = "validating"
    RENDERING = "rendering"
    REVIEWING = "reviewing"
    REFINING = "refining"
    OPTIMIZING = "optimizing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INPUT = "needs_input"      # thiếu thông số bắt buộc: NEXA hỏi lại anh, không đoán


TERMINAL_STATES = {JobState.READY, JobState.FAILED, JobState.CANCELLED, JobState.NEEDS_INPUT}

JOB_STATE_LABELS_VI = {
    JobState.QUEUED: "Đang xếp hàng",
    JobState.PLANNING: "Đang phân tích yêu cầu",
    JobState.GENERATING_REFERENCE: "Đang tạo ảnh tham chiếu",
    JobState.GENERATING_GEOMETRY: "Đang dựng hình học",
    JobState.TEXTURING: "Đang tạo vật liệu",
    JobState.SEGMENTING: "Đang tách bộ phận",
    JobState.VALIDATING: "Đang kiểm tra hình học",
    JobState.RENDERING: "Đang render 6 góc",
    JobState.REVIEWING: "Đang đánh giá chất lượng",
    JobState.REFINING: "Đang sửa phần chưa đạt",
    JobState.OPTIMIZING: "Đang tối ưu LOD",
    JobState.READY: "Đã sẵn sàng",
    JobState.FAILED: "Thất bại",
    JobState.CANCELLED: "Đã hủy",
    JobState.NEEDS_INPUT: "Cần thêm thông tin",
}

# Trục: kỹ thuật (X trước, Y trái, Z lên) → asset/glTF (X trái, Y lên, Z trước). Hoán vị vòng nên giữ chiều trục.
_ROS_TO_ASSET = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])


def ros_to_asset(v: Any) -> np.ndarray:
    """Đổi điểm/vector (…,3) từ hệ kỹ thuật sang hệ asset."""
    return np.asarray(v, dtype=np.float64) @ _ROS_TO_ASSET.T


def asset_to_ros(v: Any) -> np.ndarray:
    return np.asarray(v, dtype=np.float64) @ _ROS_TO_ASSET


def _vec(v: Any, n: int = 3) -> list[float]:
    arr = [float(x) for x in (v if v is not None else [0.0] * n)]
    if len(arr) != n:
        raise ValueError(f"vector cần {n} phần tử")
    return arr


@dataclass
class Material:
    id: str
    name: str = ""
    kind: str = "plastic"              # plastic | metal | carbon | rubber | glass | paint | emissive | fabric
    base_color: list[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])   # linear RGBA
    metallic: float = 0.0
    roughness: float = 0.5
    emissive: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    clearcoat: float = 0.0
    normal_scale: float = 1.0
    textures: dict[str, str] = field(default_factory=dict)   # base_color|normal|metallic_roughness → đường dẫn tương đối

    @property
    def transparent(self) -> bool:
        return self.base_color[3] < 0.999

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Material":
        return cls(id=str(d["id"]), name=str(d.get("name", "")), kind=str(d.get("kind", "plastic")),
                   base_color=_vec(d.get("base_color", [0.8, 0.8, 0.8, 1.0]), 4),
                   metallic=float(d.get("metallic", 0.0)), roughness=float(d.get("roughness", 0.5)),
                   emissive=_vec(d.get("emissive", [0, 0, 0])), clearcoat=float(d.get("clearcoat", 0.0)),
                   normal_scale=float(d.get("normal_scale", 1.0)),
                   textures={str(k): str(v) for k, v in (d.get("textures") or {}).items()})


@dataclass
class Transform:
    translation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])   # quaternion x, y, z, w
    scale: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Transform":
        d = d or {}
        return cls(_vec(d.get("translation", [0, 0, 0])), _vec(d.get("rotation", [0, 0, 0, 1]), 4),
                   _vec(d.get("scale", [1, 1, 1])))


@dataclass
class Bounds:
    min: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    max: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    @property
    def size(self) -> list[float]:
        return [b - a for a, b in zip(self.min, self.max)]

    @property
    def center(self) -> list[float]:
        return [(a + b) / 2 for a, b in zip(self.min, self.max)]

    @property
    def radius(self) -> float:
        s = self.size
        return 0.5 * float(np.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2))

    def to_dict(self) -> dict:
        return {"min": list(self.min), "max": list(self.max)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Bounds":
        d = d or {}
        return cls(_vec(d.get("min", [0, 0, 0])), _vec(d.get("max", [0, 0, 0])))

    @classmethod
    def of_points(cls, pts: np.ndarray) -> "Bounds":
        if pts is None or len(pts) == 0:
            return cls()
        return cls([float(x) for x in pts.min(axis=0)], [float(x) for x in pts.max(axis=0)])

    @classmethod
    def union(cls, items: list["Bounds"]) -> "Bounds":
        items = [b for b in items if b is not None]
        if not items:
            return cls()
        return cls([min(b.min[i] for b in items) for i in range(3)], [max(b.max[i] for b in items) for i in range(3)])


@dataclass
class Part3D:
    id: str
    name_vi: str
    name_en: str = ""
    aliases: list[str] = field(default_factory=list)
    category: str = "part"                  # propeller, motor, arm, shell, wheel, joint, rotor_blade…
    parent_id: str | None = None
    transform: Transform = field(default_factory=Transform)
    pivot: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bounds: Bounds = field(default_factory=Bounds)
    dimensions: dict[str, float] = field(default_factory=dict)      # mm
    material: str = ""                      # id vật liệu chính (bộ phận có thể có nhiều primitive)
    function: str = ""                      # chức năng (tiếng Việt)
    position_tag: str = ""                  # front_left, rear_right, left, right, front, rear, top, bottom, center…
    joint_axis: list[float] | None = None
    explode_vector: list[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    explode_distance: float = 0.0           # mm
    explode_order: int = 0
    confidence: float = 1.0
    group: str = ""                         # cụm (ví dụ arm_front_left) để "xem cả cụm"
    required: bool = False
    asset: str = ""                         # đường dẫn tương đối tới GLB riêng của bộ phận
    triangles: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transform"] = self.transform.to_dict()
        d["bounds"] = self.bounds.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Part3D":
        return cls(id=str(d["id"]), name_vi=str(d.get("name_vi", d["id"])), name_en=str(d.get("name_en", "")),
                   aliases=[str(a) for a in d.get("aliases") or []], category=str(d.get("category", "part")),
                   parent_id=(str(d["parent_id"]) if d.get("parent_id") else None),
                   transform=Transform.from_dict(d.get("transform")), pivot=_vec(d.get("pivot", [0, 0, 0])),
                   bounds=Bounds.from_dict(d.get("bounds")),
                   dimensions={str(k): float(v) for k, v in (d.get("dimensions") or {}).items()},
                   material=str(d.get("material", "")), function=str(d.get("function", "")),
                   position_tag=str(d.get("position_tag", "")),
                   joint_axis=_vec(d["joint_axis"]) if d.get("joint_axis") is not None else None,
                   explode_vector=_vec(d.get("explode_vector", [0, 1, 0])),
                   explode_distance=float(d.get("explode_distance", 0.0)), explode_order=int(d.get("explode_order", 0)),
                   confidence=float(d.get("confidence", 1.0)), group=str(d.get("group", "")),
                   required=bool(d.get("required", False)), asset=str(d.get("asset", "")),
                   triangles=int(d.get("triangles", 0)))


@dataclass
class ExplosionStep:
    order: int
    part_ids: list[str]
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExplosionStep":
        return cls(int(d["order"]), [str(x) for x in d.get("part_ids") or []], str(d.get("description", "")))


@dataclass
class Model3DProject:
    id: str
    name: str
    source_prompt: str = ""
    generation_mode: str = "parametric"       # parametric | cloud | dsl
    provider: str = "local"                   # local | tripo | meshy
    units: str = "mm"
    status: str = "draft"                     # draft | ready | rejected
    asset_path: str = "model.glb"             # tương đối trong thư mục dự án
    thumbnail_path: str = ""
    bounds: Bounds = field(default_factory=Bounds)
    quality_score: float = 0.0
    validation_status: str = "pending"        # pending | passed | failed
    warnings: list[str] = field(default_factory=list)
    parts: list[Part3D] = field(default_factory=list)
    explosion_plan: list[ExplosionStep] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    category: str = "generic"
    supported_category: bool = True           # False = best effort (ngoài nhóm hỗ trợ)
    spec: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)   # conceptual, dimensionally_specified, …
    quality_report: dict[str, Any] = field(default_factory=dict)
    renders: dict[str, str] = field(default_factory=dict)    # front/back/left/right/top/bottom → đường dẫn
    has_assembly: bool = True
    created_at: float = field(default_factory=time.time)
    generator_version: str = GENERATOR_VERSION
    cache_key: str = ""

    @staticmethod
    def new_id() -> str:
        return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

    def part(self, part_id: str) -> Part3D | None:
        return next((p for p in self.parts if p.id == part_id), None)

    def material(self, material_id: str) -> Material | None:
        return next((m for m in self.materials if m.id == material_id), None)

    @property
    def triangle_count(self) -> int:
        return sum(p.triangles for p in self.parts)

    def to_dict(self) -> dict:
        return {
            "format": "nexa-assembly-manifest", "format_version": 1,
            "id": self.id, "name": self.name, "source_prompt": self.source_prompt,
            "generation_mode": self.generation_mode, "provider": self.provider, "units": self.units,
            "status": self.status, "asset_path": self.asset_path, "thumbnail_path": self.thumbnail_path,
            "bounds": self.bounds.to_dict(), "quality_score": self.quality_score,
            "validation_status": self.validation_status, "warnings": list(self.warnings),
            "parts": [p.to_dict() for p in self.parts],
            "explosion_plan": [s.to_dict() for s in self.explosion_plan],
            "materials": [m.to_dict() for m in self.materials],
            "category": self.category, "supported_category": self.supported_category, "spec": self.spec,
            "metadata": self.metadata, "quality_report": self.quality_report, "renders": dict(self.renders),
            "has_assembly": self.has_assembly, "created_at": self.created_at,
            "generator_version": self.generator_version, "cache_key": self.cache_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Model3DProject":
        return cls(id=str(d["id"]), name=str(d.get("name", "")), source_prompt=str(d.get("source_prompt", "")),
                   generation_mode=str(d.get("generation_mode", "parametric")), provider=str(d.get("provider", "local")),
                   units=str(d.get("units", "mm")), status=str(d.get("status", "draft")),
                   asset_path=str(d.get("asset_path", "model.glb")), thumbnail_path=str(d.get("thumbnail_path", "")),
                   bounds=Bounds.from_dict(d.get("bounds")), quality_score=float(d.get("quality_score", 0.0)),
                   validation_status=str(d.get("validation_status", "pending")),
                   warnings=[str(w) for w in d.get("warnings") or []],
                   parts=[Part3D.from_dict(p) for p in d.get("parts") or []],
                   explosion_plan=[ExplosionStep.from_dict(s) for s in d.get("explosion_plan") or []],
                   materials=[Material.from_dict(m) for m in d.get("materials") or []],
                   category=str(d.get("category", "generic")), supported_category=bool(d.get("supported_category", True)),
                   spec=dict(d.get("spec") or {}), metadata=dict(d.get("metadata") or {}),
                   quality_report=dict(d.get("quality_report") or {}),
                   renders={str(k): str(v) for k, v in (d.get("renders") or {}).items()},
                   has_assembly=bool(d.get("has_assembly", True)), created_at=float(d.get("created_at", time.time())),
                   generator_version=str(d.get("generator_version", GENERATOR_VERSION)),
                   cache_key=str(d.get("cache_key", "")))
