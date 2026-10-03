"""CAD tham số cục bộ (chạy offline): template theo nhóm hỗ trợ + DSL whitelist cho vật thể ngoài nhóm.

- Nhóm hỗ trợ (UAV, xe tự hành, robot người, robot chó, trực thăng, ốc vít/cơ khí): template trong templates/.
  Sau khi dựng, mô hình được co giãn đồng đều để kích thước tổng thể khớp đúng thông số người dùng (chiều dài xe,
  chiều cao robot…), rồi đo lại trong quality.py.
- Vật thể khác: Gemini mô tả bằng CAD DSL (geometry/dsl.py) → biên dịch bằng kernel. Đánh dấu best effort.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from nexa.core.safety import Cancelled
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import get_template
from nexa.three_d.geometry import dsl as D
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.models import Bounds
from nexa.three_d.spec import ModelSpec

COUNT_KEYS = {"blades", "teeth", "bolt_holes", "holes", "module", "pitch_count"}
# (thông số spec, trục asset: 0 = rộng X, 1 = cao Y, 2 = dài Z)
FIT_TARGETS = {"rover": ("length_mm", 2), "quadruped": ("length_mm", 2), "humanoid": ("height_mm", 1),
               "helicopter": ("length_mm", 2), "boat": ("length_mm", 2)}


def _scale_meta(value: Any, k: float, key: str = "") -> Any:
    if isinstance(value, dict):
        return {kk: _scale_meta(v, k, kk) for kk, v in value.items()}
    if isinstance(value, list):
        return [_scale_meta(v, k, key) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and (
            key.endswith("_mm") or key in ("center", "radius")):
        return value * k
    return value


def scale_assembly(asm: BuiltAssembly, k: float) -> BuiltAssembly:
    """Co giãn đồng đều cả assembly quanh gốc tọa độ (lưới, khối kiểm tra, bounds, pivot, khoảng tách, kích thước)."""
    if abs(k - 1.0) < 1e-9:
        return asm
    for bp in asm.parts:
        p = bp.part
        for mesh, _ in bp.meshes:
            mesh.vertices = mesh.vertices * k
        if bp.solid is not None:
            bp.solid = bp.solid.scale(k)
        p.bounds = Bounds([x * k for x in p.bounds.min], [x * k for x in p.bounds.max])
        p.pivot = [x * k for x in p.pivot]
        p.explode_distance *= k
        p.dimensions = {n: (v if n in COUNT_KEYS else round(v * k, 3)) for n, v in p.dimensions.items()}
    asm.bounds = Bounds.union([bp.part.bounds for bp in asm.parts])
    asm.metadata = _scale_meta(asm.metadata, k)
    asm.metadata["fit_scale"] = round(k, 5)
    return asm


def fit_to_spec(asm: BuiltAssembly, spec: ModelSpec) -> BuiltAssembly:
    tgt = FIT_TARGETS.get(spec.category)
    if not tgt or tgt[0] not in spec.params:
        return asm
    want = float(spec.params[tgt[0]])
    have = asm.bounds.size[tgt[1]]
    if have <= 0:
        return asm
    return scale_assembly(asm, want / have)


def build_parametric(spec: ModelSpec) -> BuiltAssembly:
    tpl = get_template(spec.category)
    if tpl is None:
        raise ValueError(f"không có template tham số cho nhóm '{spec.category}'")
    return fit_to_spec(tpl(spec), spec)


# ------------------------------------------------------------------ DSL (best effort)
DSL_PART_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["id", "name_vi", "shape"],
    "properties": {
        "id": {"type": "string", "maxLength": 40}, "name_vi": {"type": "string", "maxLength": 80},
        "name_en": {"type": "string", "maxLength": 80}, "category": {"type": "string", "maxLength": 40},
        "material": {"type": "string", "maxLength": 40}, "function": {"type": "string", "maxLength": 200},
        "aliases": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 40}},
        "parent_id": {"type": "string", "maxLength": 40}, "position_tag": {"type": "string", "maxLength": 20},
        "explode_dir": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number", "minimum": -1, "maximum": 1}},
        "explode_distance": {"type": "number", "minimum": 0, "maximum": 20000},
        "color": {"type": "string", "maxLength": 9},
        "shape": {"type": "object", "additionalProperties": True, "properties": {}},
    }}
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class DslBuild:
    asm: BuiltAssembly | None
    errors: dict[str, str] = field(default_factory=dict)      # id bộ phận → lỗi biên dịch/kiểm tra
    compiled: list[str] = field(default_factory=list)


def _clean_part(raw: Any, index: int) -> dict:
    if not isinstance(raw, dict):
        raise D.DslError("bộ phận phải là object")
    part = {k: v for k, v in raw.items() if k in DSL_PART_SCHEMA["properties"]}   # bỏ trường lạ (AI hay thêm "notes")
    if not isinstance(part.get("id"), str) or not part["id"].strip():
        part["id"] = f"part_{index + 1}"
    if not isinstance(part.get("name_vi"), str) or not part["name_vi"].strip():
        part["name_vi"] = part.get("name_en") if isinstance(part.get("name_en"), str) and part.get("name_en") else \
            f"Bộ phận {index + 1}"
    for key, n in (("id", 40), ("name_vi", 80), ("name_en", 80), ("category", 40), ("material", 40), ("function", 200),
                   ("parent_id", 40), ("position_tag", 20)):
        if key in part:
            part[key] = str(part[key])[:n]
    if "aliases" in part:
        part["aliases"] = [str(a)[:40] for a in part["aliases"] if isinstance(a, (str, int, float))][:8] \
            if isinstance(part["aliases"], list) else []
    ed = part.get("explode_dir")
    if ed is not None:
        try:
            v = np.asarray([float(x) for x in ed][:3], float)
            n = float(np.linalg.norm(v))
            part["explode_dir"] = (v / n).tolist() if len(v) == 3 and n > 1e-6 and np.isfinite(v).all() else [0.0, 0.0, 0.0]
        except (TypeError, ValueError):
            part["explode_dir"] = [0.0, 0.0, 0.0]
    if "explode_distance" in part:
        try:
            part["explode_distance"] = float(min(20000.0, max(0.0, float(part["explode_distance"]))))
        except (TypeError, ValueError):
            part.pop("explode_distance")
    if part.get("color") is not None and not _COLOR_RE.match(str(part.get("color"))):
        part.pop("color")
    return part


def compile_dsl_parts(spec: ModelSpec, dsl_parts: list[dict], tolerant: bool = False,
                      check: Callable[[], None] | None = None) -> DslBuild:
    """Dựng assembly từ danh sách bộ phận DSL của AI.

    tolerant=True: bộ phận lỗi được ghi vào `errors` và bỏ qua (để gửi lại cho Gemini sửa) thay vì hủy cả mô hình.
    Mô hình được đặt lên mặt đất (z thấp nhất = 0) và căn tâm ngang; chỉ co giãn khi người dùng nói rõ kích thước.
    """
    from nexa.ai.tool_registry import validate_schema
    if not isinstance(dsl_parts, list) or not (1 <= len(dsl_parts) <= 40):
        raise D.DslError("cần 1–40 bộ phận")
    style = spec.style or {}
    mats = M.object_library(M.color_from_name(style.get("primary_color"), "#c4c8cc"),
                            M.color_from_name(style.get("secondary_color"), "#2b2e33"),
                            M.color_from_name(style.get("accent_color"), "#22d3ee"))
    budget = D._Budget(check=check)
    errors: dict[str, str] = {}
    items: list[tuple[str, dict, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(dsl_parts):
        if check:
            check()
        rid = str(raw.get("id")) if isinstance(raw, dict) and raw.get("id") else f"part_{i + 1}"
        try:
            part = _clean_part(raw, i)
            ok, err, checked = validate_schema({**DSL_PART_SCHEMA, "required": ["id", "name_vi"]},
                                               {k: v for k, v in part.items() if k != "shape"}, "part")
            if not ok:
                raise D.DslError(err)
            if not isinstance(raw.get("shape"), dict):
                raise D.DslError("thiếu 'shape' (cây DSL)")
            pid = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in part["id"])[:40] or f"part_{i + 1}"
            base, suffix = pid, 2
            while pid in seen:
                tail = f"_{suffix}"
                pid = base[:40 - len(tail)] + tail
                suffix += 1
            solid = D.compile_node(raw["shape"], 0, budget)
            if solid.is_empty:
                raise D.DslError("hình rỗng (phép trừ/giao xóa hết khối?)")
            lo, hi = solid.bounds()
            if not (np.isfinite(lo).all() and np.isfinite(hi).all()):
                raise D.DslError("tọa độ không hữu hạn")
        except Cancelled:
            raise
        except D.DslError as exc:
            if not tolerant:
                raise
            errors[rid] = str(exc)[:300]
            continue
        except Exception as exc:            # lỗi kernel ngoài dự kiến (manifold) — coi như bộ phận lỗi, không làm sập
            if not tolerant:
                raise D.DslError(f"{rid}: {type(exc).__name__}: {exc}") from exc
            errors[rid] = f"{type(exc).__name__}: {str(exc)[:200]}"
            continue
        seen.add(pid)
        part["id"] = pid
        items.append((pid, part, solid))
    if not items:
        return DslBuild(None, errors, [])
    # ---- đặt lên mặt đất, căn tâm ngang (khung ROS: X trước, Y trái, Z lên)
    lo = np.min([s.bounds()[0] for _, _, s in items], axis=0)
    hi = np.max([s.bounds()[1] for _, _, s in items], axis=0)
    shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    center = (lo + hi) / 2 + shift
    b = AssemblyBuilder(spec.name or "Mô hình", "generic", mats)
    ids = {pid for pid, _, _ in items}
    orig_ids = {str(p.get("id")): pid for pid, p, _ in items}
    for pid, part, solid in items:
        if check:
            check()
        solid = solid.translate(*shift)
        mat = part.get("material") if part.get("material") in mats else "paint_primary"
        if part.get("color"):
            tid = f"{mat}_{part['color'].lstrip('#').lower()}"
            if tid not in mats:
                mats[tid] = M.tinted(mats[mat], part["color"], tid)
            mat = tid
        parent = orig_ids.get(str(part.get("parent_id"))) if part.get("parent_id") else None
        if parent == pid or parent not in ids:
            parent = None
        plo, phi = solid.bounds()
        ed = np.asarray(part.get("explode_dir") or [0.0, 0.0, 0.0], float)
        if float(np.linalg.norm(ed)) < 1e-6 and parent is not None:
            d = (plo + phi) / 2 - center              # không có hướng tháo: đẩy ra xa tâm mô hình
            ed = d / (np.linalg.norm(d) or 1.0) if np.linalg.norm(d) > 1e-6 else np.array([0.0, 0.0, 1.0])
        dist = float(part.get("explode_distance", 0.0) or 0.0)
        if dist <= 0 and parent is not None:
            dist = 0.3 * float(np.max(phi - plo))
        if float(np.linalg.norm(ed)) < 1e-6:
            ed, dist = np.array([0.0, 0.0, 1.0]), 0.0
        b.add(pid, part["name_vi"], part.get("name_en", ""), part.get("category") or "part", Shape(solid, mat, 40.0),
              parent_id=parent, aliases=list(part.get("aliases") or [part["name_vi"].lower()]),
              function=part.get("function", ""), position_tag=part.get("position_tag", ""),
              explode_dir=tuple(float(x) for x in ed), explode_distance=dist,
              explode_order=1 if parent is None else 2, confidence=0.6)
    b.warnings.append("Vật thể ngoài nhóm hỗ trợ: dựng từ mô tả CAD DSL của AI (best effort, không phải bản vẽ kỹ thuật).")
    asm = b.build()
    asm.materials = {k: v for k, v in asm.materials.items() if any(k == mid for bp in asm.parts for _, mid in bp.meshes)}
    size = spec.params.get("approx_size_mm")
    if size and "approx_size_mm" in (spec.explicit or {}):
        k = float(size) / max(1e-6, max(asm.bounds.size))
        if 0.02 < k < 50 and not math.isclose(k, 1.0, rel_tol=0.02):
            asm = scale_assembly(asm, k)
    return DslBuild(asm, errors, [pid for pid, _, _ in items])


def build_from_dsl(spec: ModelSpec, dsl_parts: list[dict]) -> BuiltAssembly:
    """Dựng chặt chẽ (lỗi đầu tiên → DslError). Giữ cho các nơi gọi cũ."""
    res = compile_dsl_parts(spec, dsl_parts, tolerant=False)
    if res.asm is None:
        raise D.DslError("không có bộ phận nào dựng được")
    return res.asm
