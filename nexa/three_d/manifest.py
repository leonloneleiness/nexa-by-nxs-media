"""Assembly manifest (manifest.json cạnh model.glb): lưu/đọc và kiểm tra tính hợp lệ.

Kiểm tra: id bộ phận duy nhất, cha tồn tại, cây không vòng lặp, biến đổi/pivot/bounds hữu hạn, quaternion chuẩn hóa,
vector tách là vector đơn vị, explosion plan đầy đủ (mọi bộ phận có khoảng tách > 0 nằm trong đúng một bước), vật
liệu được tham chiếu tồn tại, đường dẫn asset an toàn (không thoát khỏi thư mục dự án).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from nexa.three_d.models import Model3DProject
from nexa.three_d.validator import AssetError, ValidationReport, safe_relpath

MANIFEST_NAME = "manifest.json"
MAX_PARTS = 400


def _finite(vals) -> bool:
    try:
        return all(math.isfinite(float(x)) for x in vals)
    except (TypeError, ValueError):
        return False


def validate_manifest(project: Model3DProject, project_dir: Path | None = None,
                      require_explosion: bool = True) -> ValidationReport:
    rep = ValidationReport()
    parts = project.parts
    if project.units != "mm":
        rep.errors.append(f"đơn vị '{project.units}' không hợp lệ (cần mm)")
    if not parts:
        rep.errors.append("manifest không có bộ phận nào")
        return rep
    if len(parts) > MAX_PARTS:
        rep.errors.append(f"quá nhiều bộ phận ({len(parts)} > {MAX_PARTS})")
    ids = [p.id for p in parts]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        rep.errors.append(f"trùng id bộ phận: {sorted(dup)[:5]}")
    idset = set(ids)
    mats = {m.id for m in project.materials}
    parent = {p.id: p.parent_id for p in parts}
    for p in parts:
        if p.parent_id is not None and p.parent_id not in idset:
            rep.errors.append(f"{p.id}: cha '{p.parent_id}' không tồn tại")
        if p.parent_id == p.id:
            rep.errors.append(f"{p.id}: tự làm cha của chính nó")
        t = p.transform
        if not (_finite(t.translation) and _finite(t.rotation) and _finite(t.scale)):
            rep.errors.append(f"{p.id}: transform có giá trị không hữu hạn")
        else:
            qn = math.sqrt(sum(float(x) ** 2 for x in t.rotation))
            if abs(qn - 1) > 1e-3:
                rep.errors.append(f"{p.id}: quaternion chưa chuẩn hóa (|q|={qn:.3f})")
            if any(abs(float(s)) < 1e-9 for s in t.scale):
                rep.errors.append(f"{p.id}: scale bằng 0")
        if not (_finite(p.pivot) and _finite(p.bounds.min) and _finite(p.bounds.max)):
            rep.errors.append(f"{p.id}: pivot/bounds không hữu hạn")
        elif any(a > b for a, b in zip(p.bounds.min, p.bounds.max)):
            rep.errors.append(f"{p.id}: bounds min > max")
        if not _finite(p.explode_vector) or not math.isfinite(p.explode_distance) or p.explode_distance < 0:
            rep.errors.append(f"{p.id}: explode_vector/explode_distance không hợp lệ")
        elif p.explode_distance > 0 and abs(math.sqrt(sum(x * x for x in p.explode_vector)) - 1) > 1e-3:
            rep.errors.append(f"{p.id}: explode_vector không phải vector đơn vị")
        if p.joint_axis is not None and not _finite(p.joint_axis):
            rep.errors.append(f"{p.id}: joint_axis không hữu hạn")
        if p.material and mats and p.material not in mats:
            rep.errors.append(f"{p.id}: vật liệu '{p.material}' không tồn tại")
        if not p.name_vi.strip():
            rep.errors.append(f"{p.id}: thiếu tên tiếng Việt")
        if not p.aliases:
            rep.warnings.append(f"{p.id}: chưa có tên gọi khác (aliases)")
        if p.asset and project_dir is not None:
            try:
                safe_relpath(project_dir, p.asset)
            except AssetError as exc:
                rep.errors.append(f"{p.id}: {exc}")
    # vòng lặp trong cây cha–con
    for pid in ids:
        seen = set()
        cur: str | None = pid
        while cur is not None:
            if cur in seen:
                rep.errors.append(f"cây bộ phận có vòng lặp tại '{pid}'")
                break
            seen.add(cur)
            cur = parent.get(cur)
        else:
            continue
        break
    if project_dir is not None:
        for rel in [project.asset_path, project.thumbnail_path, *project.renders.values(),
                    *[t for m in project.materials for t in m.textures.values()]]:
            if rel:
                try:
                    safe_relpath(project_dir, rel)
                except AssetError as exc:
                    rep.errors.append(str(exc))
    # explosion plan
    if require_explosion and project.has_assembly:
        movable = {p.id for p in parts if p.explode_distance > 0}
        planned: list[str] = [pid for step in project.explosion_plan for pid in step.part_ids]
        unknown = [pid for pid in planned if pid not in idset]
        if unknown:
            rep.errors.append(f"explosion plan tham chiếu bộ phận không tồn tại: {unknown[:5]}")
        missing = movable - set(planned)
        if missing:
            rep.errors.append(f"explosion plan thiếu {len(missing)} bộ phận: {sorted(missing)[:5]}")
        twice = {pid for pid in planned if planned.count(pid) > 1}
        if twice:
            rep.errors.append(f"bộ phận xuất hiện ở nhiều bước tách: {sorted(twice)[:5]}")
        if not movable and len(parts) > 1:
            rep.errors.append("mô hình nhiều bộ phận nhưng không bộ phận nào có hướng tách")
    rep.stats.update({"parts": len(parts), "movable": sum(1 for p in parts if p.explode_distance > 0),
                      "steps": len(project.explosion_plan)})
    return rep


def save_manifest(project: Model3DProject, project_dir: Path) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / MANIFEST_NAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(project.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load_manifest(project_dir: Path) -> Model3DProject:
    path = project_dir / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetError(f"không đọc được manifest: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != "nexa-assembly-manifest":
        raise AssetError("manifest không đúng định dạng NEXA")
    if int(data.get("format_version", 0)) > 1:
        raise AssetError("manifest được tạo bởi phiên bản NEXA mới hơn")
    try:
        return Model3DProject.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetError(f"manifest hỏng: {exc}") from exc
