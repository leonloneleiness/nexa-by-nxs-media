"""ModelSpec — mô tả có cấu trúc của mô hình cần tạo, kiểm tra bằng schema NGHIÊM NGẶT.

Gemini chỉ được trả JSON đúng schema này (không có mã). Mọi trường lạ bị từ chối, số nằm ngoài giới hạn bị từ chối,
tham số theo từng nhóm được kiểm tra riêng. Sau khi hợp lệ, `normalize()` điền giá trị mặc định có căn cứ
(bảng ISO cho ốc vít) và ghi rõ giá trị nào là mặc định, giá trị nào do người dùng nói.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from nexa.ai.tool_registry import validate_schema
from nexa.three_d import spec_tech as _T

SUPPORTED_GROUPS: dict[str, str] = {
    "uav": "UAV/drone", "rover": "Xe tự hành", "humanoid": "Robot hình người", "quadruped": "Robot hình chó",
    "helicopter": "Trực thăng", "boat": "Thuyền/tàu", "mechanical": "Ốc vít và linh kiện cơ khí phổ biến",
}
CATEGORY_GROUP = {"uav": "uav", "rover": "rover", "humanoid": "humanoid", "quadruped": "quadruped",
                  "helicopter": "helicopter", "boat": "boat", "bolt": "mechanical", "nut": "mechanical", "washer": "mechanical",
                  "gear": "mechanical", "flange": "mechanical", "bracket": "mechanical", "generic": ""}
CATEGORIES = list(CATEGORY_GROUP)
CATEGORY_VI = {"uav": "UAV", "rover": "xe tự hành", "humanoid": "robot hình người", "quadruped": "robot hình chó",
               "helicopter": "trực thăng", "boat": "thuyền", "bolt": "bu-lông", "nut": "đai ốc", "washer": "vòng đệm",
               "gear": "bánh răng", "flange": "mặt bích", "bracket": "giá đỡ", "generic": "mô hình"}
# Nhóm đòi hỏi an toàn khi chế tạo (hiện cảnh báo chưa kiểm chứng)
SAFETY_CRITICAL = {"uav", "rover", "humanoid", "quadruped", "helicopter", "boat"}
# Nhóm CAD kỹ thuật mở rộng (spec_tech.py): linh kiện chuẩn, robot, phương tiện, năng lượng/công trình, máy chế tạo
SUPPORTED_GROUPS.update(_T.TECH_GROUPS)
CATEGORY_GROUP.update(_T.TECH_CATEGORY_GROUP)
CATEGORY_VI.update(_T.TECH_CATEGORY_VI)
SAFETY_CRITICAL |= _T.TECH_SAFETY
CATEGORIES = list(CATEGORY_GROUP)

# ------------------------------------------------------------------ bảng ISO (mm)
# d: (bước ren thô ISO 261, s lục giác ISO 4017, k đầu lục giác, dk đầu trụ ISO 4762, k đầu trụ, s lỗ lục giác,
#     m đai ốc ISO 4032, d1/d2/h vòng đệm ISO 7089)
ISO_METRIC: dict[float, dict[str, float]] = {
    1.6: dict(p=0.35, s=3.2, k=1.1, dk=3.0, kc=1.6, sk=1.5, m=1.3, w1=1.7, w2=4.0, wh=0.3),
    2.0: dict(p=0.4, s=4.0, k=1.4, dk=3.8, kc=2.0, sk=1.5, m=1.6, w1=2.2, w2=5.0, wh=0.3),
    2.5: dict(p=0.45, s=5.0, k=1.7, dk=4.5, kc=2.5, sk=2.0, m=2.0, w1=2.7, w2=6.0, wh=0.5),
    3.0: dict(p=0.5, s=5.5, k=2.0, dk=5.5, kc=3.0, sk=2.5, m=2.4, w1=3.2, w2=7.0, wh=0.5),
    4.0: dict(p=0.7, s=7.0, k=2.8, dk=7.0, kc=4.0, sk=3.0, m=3.2, w1=4.3, w2=9.0, wh=0.8),
    5.0: dict(p=0.8, s=8.0, k=3.5, dk=8.5, kc=5.0, sk=4.0, m=4.7, w1=5.3, w2=10.0, wh=1.0),
    6.0: dict(p=1.0, s=10.0, k=4.0, dk=10.0, kc=6.0, sk=5.0, m=5.2, w1=6.4, w2=12.0, wh=1.6),
    8.0: dict(p=1.25, s=13.0, k=5.3, dk=13.0, kc=8.0, sk=6.0, m=6.8, w1=8.4, w2=16.0, wh=1.6),
    10.0: dict(p=1.5, s=16.0, k=6.4, dk=16.0, kc=10.0, sk=8.0, m=8.4, w1=10.5, w2=20.0, wh=2.0),
    12.0: dict(p=1.75, s=18.0, k=7.5, dk=18.0, kc=12.0, sk=10.0, m=10.8, w1=13.0, w2=24.0, wh=2.5),
    14.0: dict(p=2.0, s=21.0, k=8.8, dk=21.0, kc=14.0, sk=12.0, m=12.8, w1=15.0, w2=28.0, wh=2.5),
    16.0: dict(p=2.0, s=24.0, k=10.0, dk=24.0, kc=16.0, sk=14.0, m=14.8, w1=17.0, w2=30.0, wh=3.0),
    20.0: dict(p=2.5, s=30.0, k=12.5, dk=30.0, kc=20.0, sk=17.0, m=18.0, w1=21.0, w2=37.0, wh=3.0),
    24.0: dict(p=3.0, s=36.0, k=15.0, dk=36.0, kc=24.0, sk=19.0, m=21.5, w1=25.0, w2=44.0, wh=4.0),
    30.0: dict(p=3.5, s=46.0, k=18.7, dk=45.0, kc=30.0, sk=22.0, m=25.6, w1=31.0, w2=56.0, wh=4.0),
    36.0: dict(p=4.0, s=55.0, k=22.5, dk=54.0, kc=36.0, sk=27.0, m=31.0, w1=37.0, w2=66.0, wh=5.0),
}
ISO_FINE_PITCHES: dict[float, list[float]] = {8.0: [1.0], 10.0: [1.25, 1.0], 12.0: [1.5, 1.25], 14.0: [1.5],
                                              16.0: [1.5], 20.0: [1.5, 2.0], 24.0: [2.0], 30.0: [2.0], 36.0: [3.0]}


def iso_row(diameter: float) -> dict[str, float] | None:
    return ISO_METRIC.get(round(float(diameter), 1))


def iso_or_scaled(diameter: float) -> dict[str, float]:
    """Hàng ISO đúng đường kính; nếu không có thì nội suy theo đường kính gần nhất (ghi cảnh báo ở nơi gọi)."""
    row = iso_row(diameter)
    if row is not None:
        return dict(row)
    near = min(ISO_METRIC, key=lambda d: abs(d - diameter))
    k = diameter / near
    return {key: round(v * k, 3) for key, v in ISO_METRIC[near].items()}


# ------------------------------------------------------------------ schema
def _num(lo: float, hi: float, desc: str = "", **kw) -> dict:
    return {"type": "number", "minimum": lo, "maximum": hi, "description": desc, **kw}


def _int(lo: int, hi: int, desc: str = "", **kw) -> dict:
    return {"type": "integer", "minimum": lo, "maximum": hi, "description": desc, **kw}


def _enum(values: list, desc: str = "", **kw) -> dict:
    return {"type": "string", "enum": values, "description": desc, **kw}


def _bool(desc: str = "", **kw) -> dict:
    return {"type": "boolean", "description": desc, **kw}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


FASTENER_MATERIALS = ["zinc", "steel", "stainless", "black_oxide", "brass", "titanium"]
PARAM_SCHEMAS: dict[str, dict] = {
    "bolt": _obj({
        "diameter_mm": _num(1.6, 64, "Đường kính danh nghĩa ren, ví dụ M8 → 8"),
        "length_mm": _num(2, 500, "Chiều dài thân tính từ mặt dưới đầu (đầu chìm: tính cả đầu)"),
        "pitch_mm": _num(0.2, 6, "Bước ren; bỏ trống = ren thô ISO"),
        "head": _enum(["hex", "socket_cap", "countersunk"], "Kiểu đầu", default="hex"),
        "thread": _enum(["technical", "illustrative"], "technical = helix thật; illustrative = ren vẽ bằng texture",
                        default="technical"),
        "thread_length_mm": _num(1, 500, "Chiều dài đoạn ren; bỏ trống = theo tiêu chuẩn"),
        "material": _enum(FASTENER_MATERIALS, default="zinc"),
        "include_nut": _bool("Kèm đai ốc", default=False),
        "include_washer": _bool("Kèm vòng đệm", default=False),
        "grade": {"type": "string", "maxLength": 8, "description": "Cấp bền, ví dụ 8.8"},
    }, ["diameter_mm", "length_mm"]),
    "nut": _obj({
        "diameter_mm": _num(1.6, 64), "pitch_mm": _num(0.2, 6),
        "thread": _enum(["technical", "illustrative"], default="technical"),
        "type": _enum(["hex", "nyloc"], default="hex"), "material": _enum(FASTENER_MATERIALS, default="zinc"),
    }, ["diameter_mm"]),
    "washer": _obj({
        "diameter_mm": _num(1.6, 64, "Đường kính bu-lông đi kèm"), "inner_mm": _num(1, 80), "outer_mm": _num(2, 160),
        "thickness_mm": _num(0.2, 12), "material": _enum(FASTENER_MATERIALS, default="zinc"),
    }, ["diameter_mm"]),
    "gear": _obj({
        "module_mm": _num(0.3, 20), "teeth": _int(8, 200), "face_width_mm": _num(1, 300),
        "bore_mm": _num(0.5, 400), "pressure_angle_deg": _num(14.5, 25, default=20.0),
        "hub": _bool(default=True), "keyway": _bool(default=True),
        "material": _enum(["steel", "brass", "aluminum", "plastic"], default="steel"),
    }, ["module_mm", "teeth"]),
    "flange": _obj({
        "outer_d_mm": _num(10, 2000), "inner_d_mm": _num(1, 1900), "thickness_mm": _num(1, 300),
        "bolt_holes": _int(3, 32, default=4), "bolt_circle_d_mm": _num(5, 1990), "hole_d_mm": _num(1, 100),
        "hub_d_mm": _num(2, 1900), "hub_height_mm": _num(0, 500),
        "material": _enum(["steel", "stainless", "aluminum", "cast_iron"], default="steel"),
    }, ["outer_d_mm"]),
    "bracket": _obj({
        "width_mm": _num(5, 2000), "height_mm": _num(5, 2000), "depth_mm": _num(5, 2000), "thickness_mm": _num(0.5, 100),
        "holes": _int(0, 16, default=2), "hole_d_mm": _num(1, 60), "fillet_mm": _num(0, 200),
        "gusset": _bool(default=True), "material": _enum(["steel", "stainless", "aluminum"], default="aluminum"),
    }, []),
    "uav": _obj({
        "arm_count": _int(3, 8, "Số tay đòn/motor/cánh quạt (3, 4, 6, 8)", default=4),
        "size_class": _enum(["mini", "medium", "large"], default="mini"),
        "wheelbase_mm": _num(100, 2500, "Khoảng cách chéo giữa hai trục motor"),
        "frame_material": _enum(["carbon", "plastic", "aluminum"], default="carbon"),
        "camera": _enum(["front", "bottom", "none"], default="front"),
        "gimbal": _bool(default=True), "landing_gear": _bool(default=True),
        "battery": _enum(["rear", "top", "bottom"], default="rear"),
        "prop_blades": _int(2, 5, default=3), "lights": _bool(default=True),
    }, []),
    "rover": _obj({
        "wheel_count": _int(4, 8, "4, 6 hoặc 8 bánh", default=6), "length_mm": _num(200, 4000, default=700),
        "lidar": _bool(default=True), "camera": _bool(default=True),
        "suspension": _enum(["rocker_bogie", "independent"], default="rocker_bogie"),
        "antenna": _bool(default=True), "solar_panel": _bool(default=False),
    }, []),
    "humanoid": _obj({
        "height_mm": _num(300, 2600, default=1650), "style": _enum(["sleek", "industrial"], default="sleek"),
        "hands": _enum(["simple", "gripper"], default="simple"), "head_sensor": _enum(["visor", "camera"], default="visor"),
    }, []),
    "quadruped": _obj({
        "length_mm": _num(250, 2000, default=700), "joints_per_leg": _int(2, 3, default=3),
        "head_sensor": _enum(["camera", "lidar", "both"], default="both"), "style": _enum(["sleek", "industrial"], default="sleek"),
    }, []),
    "helicopter": _obj({
        "role": _enum(["rescue", "utility", "civil", "medical"], default="rescue"),
        "main_blades": _int(2, 7, default=4), "tail_rotor_blades": _int(2, 6, default=4),
        "landing": _enum(["skids", "wheels"], default="skids"), "length_mm": _num(2000, 30000, default=12500),
        "hoist": _bool(default=True), "searchlight": _bool(default=True),
    }, []),
    "boat": _obj({
        "boat_type": _enum(["speedboat", "fishing", "yacht", "patrol"], "Loại thuyền: ca nô cao tốc, tàu cá, du thuyền, "
                           "tàu tuần tra", default="speedboat"),
        "length_mm": _num(1500, 60000, "Chiều dài toàn bộ (mm)", default=6500),
        "propulsion": _enum(["outboard", "inboard"], "Máy gắn ngoài đuôi hay máy trong + chân vịt (bỏ trống = theo loại tàu)"),
        "engines": _int(1, 3, "Số máy", default=1),
        "cabin": _bool("Có cabin/bàn lái", default=True), "railings": _bool("Lan can mũi", default=True),
    }, []),
    "generic": _obj({
        "description": {"type": "string", "maxLength": 500},
        "approx_size_mm": _num(1, 50000),
    }, []),
}
PARAM_SCHEMAS.update(_T.TECH_SCHEMAS)

MODEL_SPEC_SCHEMA: dict = _obj({
    "category": _enum(CATEGORIES, "Loại mô hình"),
    "name": {"type": "string", "maxLength": 80, "description": "Tên ngắn tiếng Việt"},
    "mode": _enum(["auto", "parametric", "cloud"], default="auto"),
    "quality": _enum(["standard", "high"], default="standard"),
    "units": _enum(["mm"], default="mm"),
    "intended_use": _enum(["visualization", "manufacturing"], default="visualization"),
    "style": _obj({
        "primary_color": {"type": "string", "maxLength": 24},
        "secondary_color": {"type": "string", "maxLength": 24},
        "accent_color": {"type": "string", "maxLength": 24},
        "finish": _enum(["matte", "glossy", "carbon", "metal"]),
    }),
    "params": {"type": "object", "additionalProperties": True, "properties": {}},
    "requested_parts": {"type": "array", "maxItems": 40, "items": {"type": "string", "maxLength": 60}},
    "missing": {"type": "array", "maxItems": 5, "items": _obj({
        "field": {"type": "string", "maxLength": 40}, "question": {"type": "string", "maxLength": 200}},
        ["field", "question"])},
    "notes": {"type": "string", "maxLength": 500},
}, ["category"])

LIMITS = {"max_dimension_mm": 150000.0, "min_dimension_mm": 0.2}     # 150 m: tên lửa 70 m, cầu, đoàn tàu


class SpecError(ValueError):
    pass


@dataclass
class ModelSpec:
    category: str
    name: str = ""
    prompt: str = ""
    mode: str = "auto"
    quality: str = "standard"
    units: str = "mm"
    intended_use: str = "visualization"
    style: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    requested_parts: list[str] = field(default_factory=list)
    missing: list[dict[str, str]] = field(default_factory=list)
    notes: str = ""
    explicit: dict[str, float] = field(default_factory=dict)      # số đo người dùng nói rõ (đối chiếu)
    defaults_used: list[str] = field(default_factory=list)        # tham số lấy theo mặc định/tiêu chuẩn
    source: str = "local"                                         # local | gemini
    warnings: list[str] = field(default_factory=list)
    reference_images: dict[str, tuple[bytes, str]] = field(default_factory=dict, repr=False)

    @property
    def group(self) -> str:
        return CATEGORY_GROUP.get(self.category, "")

    @property
    def supported(self) -> bool:
        return bool(self.group)

    @property
    def safety_critical(self) -> bool:
        return self.category in SAFETY_CRITICAL

    def to_dict(self) -> dict:
        return {"category": self.category, "name": self.name, "prompt": self.prompt, "mode": self.mode,
                "quality": self.quality, "units": self.units, "intended_use": self.intended_use,
                "style": dict(self.style), "params": copy.deepcopy(self.params),
                "requested_parts": list(self.requested_parts), "missing": list(self.missing), "notes": self.notes,
                "explicit": dict(self.explicit), "defaults_used": list(self.defaults_used), "source": self.source,
                "warnings": list(self.warnings)}

    def cache_key(self, generator_version: str) -> str:
        core = {k: v for k, v in self.to_dict().items() if k not in ("prompt", "notes", "source", "warnings", "missing")}
        raw = json.dumps({"v": generator_version, "spec": core}, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def validate_spec(data: Any) -> ModelSpec:
    """Kiểm tra JSON (từ Gemini hoặc planner local) → ModelSpec. Ném SpecError nếu sai schema/giới hạn."""
    if not isinstance(data, dict):
        raise SpecError("ModelSpec phải là object JSON")
    ok, err, clean = validate_schema(MODEL_SPEC_SCHEMA, data, "spec")
    if not ok:
        raise SpecError(err)
    cat = clean["category"]
    params_raw = data.get("params") or {}
    ok, err, params = validate_schema(PARAM_SCHEMAS[cat], params_raw, f"spec.params({cat})")
    if not ok:
        raise SpecError(err)
    spec = ModelSpec(category=cat, name=(clean.get("name") or "").strip(), mode=clean.get("mode", "auto"),
                     quality=clean.get("quality", "standard"), units="mm",
                     intended_use=clean.get("intended_use", "visualization"),
                     style={k: v for k, v in (clean.get("style") or {}).items() if v},
                     params=params, requested_parts=list(clean.get("requested_parts") or []),
                     missing=list(clean.get("missing") or []), notes=clean.get("notes", ""))
    _semantic_checks(spec)
    return spec


def _semantic_checks(spec: ModelSpec) -> None:
    p = spec.params
    c = spec.category
    if c == "bolt":
        d, L = p["diameter_mm"], p["length_mm"]
        if L < d * 0.5:
            raise SpecError(f"chiều dài {L:g} mm quá ngắn so với đường kính M{d:g}")
        if "pitch_mm" in p and not (0.08 * d <= p["pitch_mm"] <= 0.26 * d):
            raise SpecError(f"bước ren {p['pitch_mm']:g} mm không hợp lý cho M{d:g}")
        if p.get("thread_length_mm") and p["thread_length_mm"] > L:
            raise SpecError("chiều dài ren lớn hơn chiều dài bu-lông")
    elif c == "nut":
        if "pitch_mm" in p and not (0.08 * p["diameter_mm"] <= p["pitch_mm"] <= 0.26 * p["diameter_mm"]):
            raise SpecError("bước ren không hợp lý cho đường kính đai ốc")
    elif c == "washer":
        if p.get("inner_mm") and p.get("outer_mm") and p["outer_mm"] <= p["inner_mm"]:
            raise SpecError("đường kính ngoài vòng đệm phải lớn hơn đường kính trong")
    elif c == "gear":
        if p.get("bore_mm") and p["bore_mm"] >= p["module_mm"] * (p["teeth"] - 2.5):
            raise SpecError("lỗ trục lớn hơn vòng chân răng")
    elif c == "flange":
        if p.get("inner_d_mm") and p["inner_d_mm"] >= p["outer_d_mm"]:
            raise SpecError("đường kính trong mặt bích phải nhỏ hơn đường kính ngoài")
    elif c == "uav":
        if p["arm_count"] not in (3, 4, 6, 8):
            raise SpecError("UAV hỗ trợ 3, 4, 6 hoặc 8 tay đòn")
    elif c == "rover":
        if p["wheel_count"] not in (4, 6, 8):
            raise SpecError("xe tự hành hỗ trợ 4, 6 hoặc 8 bánh")
    elif c in _T.TECH_SCHEMAS:
        try:
            _T.semantic_checks(spec)
        except _T.TechSpecError as exc:
            raise SpecError(str(exc)) from exc
    for key, val in p.items():
        if key.endswith("_mm") and isinstance(val, (int, float)) and val > LIMITS["max_dimension_mm"]:
            raise SpecError(f"{key} vượt giới hạn {LIMITS['max_dimension_mm']:g} mm")


def normalize(spec: ModelSpec) -> ModelSpec:
    """Điền tham số dẫn xuất có căn cứ (ISO / tỷ lệ thiết kế) và ghi lại tham số nào là mặc định."""
    p = spec.params
    used = spec.defaults_used
    c = spec.category
    if c in ("bolt", "nut", "washer"):
        d = float(p["diameter_mm"])
        row = iso_row(d)
        if row is None:
            spec.warnings.append(f"M{d:g} không có trong bảng ISO của NEXA — kích thước đầu/đai ốc được nội suy.")
        iso = iso_or_scaled(d)
        if c in ("bolt", "nut") and "pitch_mm" not in p:
            p["pitch_mm"] = iso["p"]
            used.append(f"bước ren thô ISO {iso['p']:g} mm")
        if c in ("bolt", "nut"):
            pitch = p["pitch_mm"]
            fine = ISO_FINE_PITCHES.get(round(d, 1), [])
            if row is not None and abs(pitch - iso["p"]) > 1e-6 and all(abs(pitch - f) > 1e-6 for f in fine):
                spec.warnings.append(f"Bước ren {pitch:g} mm không phải bước ren ISO chuẩn của M{d:g}.")
        if c == "bolt":
            L = float(p["length_mm"])
            if "thread_length_mm" not in p:
                b = 2 * d + 6
                if L <= 6 * d or L <= b + 2 * p["pitch_mm"]:
                    p["thread_length_mm"] = round(L - (0 if p.get("head") == "countersunk" else 0), 3)
                    used.append("ren suốt (ISO 4017)")
                else:
                    p["thread_length_mm"] = round(b, 3)
                    used.append(f"ren lửng b = 2d + 6 = {b:g} mm (ISO 4014)")
        if c == "washer":
            p.setdefault("inner_mm", iso["w1"])
            p.setdefault("outer_mm", iso["w2"])
            p.setdefault("thickness_mm", iso["wh"])
    elif c == "gear":
        m, z = p["module_mm"], p["teeth"]
        if "face_width_mm" not in p:
            p["face_width_mm"] = round(10 * m, 3)
            used.append("bề rộng răng = 10 × module")
        if "bore_mm" not in p:
            p["bore_mm"] = round(max(m * 2, min(m * z * 0.3, m * (z - 2.5) - 6 * m)), 2)
            used.append("lỗ trục theo tỷ lệ")
    elif c == "flange":
        od = p["outer_d_mm"]
        p.setdefault("inner_d_mm", round(od * 0.4, 2))
        p.setdefault("thickness_mm", round(max(4.0, od * 0.1), 2))
        p.setdefault("bolt_circle_d_mm", round((od + p["inner_d_mm"]) / 2 + od * 0.08, 2))
        p.setdefault("hole_d_mm", round(max(3.0, od * 0.08), 2))
        p.setdefault("hub_d_mm", round(p["inner_d_mm"] + (od - p["inner_d_mm"]) * 0.35, 2))
        p.setdefault("hub_height_mm", round(p["thickness_mm"] * 0.8, 2))
        if p["bolt_circle_d_mm"] + p["hole_d_mm"] >= od or p["bolt_circle_d_mm"] - p["hole_d_mm"] <= p["hub_d_mm"]:
            p["bolt_circle_d_mm"] = round((od + p["hub_d_mm"]) / 2, 2)
            spec.warnings.append("Đường kính vòng lỗ bu-lông được chỉnh lại để lỗ nằm giữa mép ngoài và cổ.")
    elif c == "bracket":
        for k, v in (("width_mm", 40.0), ("height_mm", 50.0), ("depth_mm", 50.0), ("thickness_mm", 4.0),
                     ("hole_d_mm", 6.6), ("fillet_mm", 6.0)):
            if k not in p:
                p[k] = v
                used.append(f"{k} = {v:g}")
    elif c == "uav":
        if "wheelbase_mm" not in p:
            p["wheelbase_mm"] = {"mini": 250.0, "medium": 450.0, "large": 900.0}[p.get("size_class", "mini")]
            used.append(f"khoảng cách trục {p['wheelbase_mm']:g} mm theo cỡ {p.get('size_class', 'mini')}")
    elif c == "rover":
        if p["wheel_count"] == 4 and p.get("suspension") == "rocker_bogie":
            p["suspension"] = "independent"
            used.append("xe 4 bánh dùng treo độc lập")
    elif c in _T.TECH_SCHEMAS:
        try:
            _T.normalize(spec)
        except _T.TechSpecError as exc:
            raise SpecError(str(exc)) from exc
    return spec


def is_complete(spec: ModelSpec) -> list[dict[str, str]]:
    """Câu hỏi còn thiếu (chỉ cho thông số BẮT BUỘC; phần còn lại dùng mặc định có ghi chú)."""
    questions = [m for m in spec.missing if m.get("question")]
    p = spec.params
    if spec.category == "bolt":
        if "diameter_mm" not in p:
            questions.append({"field": "diameter_mm", "question": "Anh muốn bu-lông cỡ M mấy (đường kính ren)?"})
        if "length_mm" not in p:
            d = p.get("diameter_mm")
            questions.append({"field": "length_mm",
                              "question": f"Bu-lông M{d:g} dài bao nhiêu mm ạ?" if d else "Bu-lông dài bao nhiêu mm ạ?"})
    elif spec.category in ("nut", "washer") and "diameter_mm" not in p:
        questions.append({"field": "diameter_mm", "question": "Anh cần cỡ M mấy ạ?"})
    elif spec.category == "gear":
        if "module_mm" not in p:
            questions.append({"field": "module_mm", "question": "Bánh răng module bao nhiêu ạ (ví dụ module 2)?"})
        if "teeth" not in p:
            questions.append({"field": "teeth", "question": "Bánh răng có bao nhiêu răng ạ?"})
    elif spec.category == "flange" and "outer_d_mm" not in p:
        questions.append({"field": "outer_d_mm", "question": "Mặt bích đường kính ngoài bao nhiêu mm ạ?"})
    elif spec.category in _T.TECH_SCHEMAS:
        questions += _T.questions(spec)
    return questions
