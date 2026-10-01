"""Nhập GLB từ provider cloud thành bộ phận/vật liệu của NEXA, chuẩn hóa và tạo LOD.

- Kiểm tra định dạng bằng validator trước khi đọc (không URI ngoài, không vượt giới hạn).
- Mỗi node có lưới = một bộ phận (sau segmentation có nhiều node); một node duy nhất = mô hình chưa có assembly.
- Texture nhúng được lưu ra <dự án>/textures, vật liệu PBR giữ nguyên thông số.
- Mô hình cloud thường không có đơn vị thật: co giãn đồng đều để kích thước lớn nhất = kích thước mục tiêu (mm),
  đặt đáy tại y = 0, tâm ngang tại gốc.
- Giảm lưới có kiểm soát (fast-simplification, quadric) khi vượt ngân sách tam giác.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from nexa.three_d.geometry import gltf
from nexa.three_d.geometry.kernel import MeshData
from nexa.three_d.models import Material
from nexa.three_d.validator import AssetError, Limits, validate_glb_bytes


@dataclass
class ImportedPart:
    name: str
    meshes: list[tuple[MeshData, str]]          # (lưới asset mm, id vật liệu)


@dataclass
class ImportedModel:
    parts: list[ImportedPart]
    materials: dict[str, Material]
    scale: float
    warnings: list[str] = field(default_factory=list)
    source_triangles: int = 0


def decimate(mesh: MeshData, target_triangles: int) -> MeshData:
    """Giảm lưới về khoảng target_triangles (giữ hình dạng; pháp tuyến tính lại, UV bị bỏ nếu có)."""
    if mesh.triangle_count <= target_triangles or target_triangles < 16:
        return mesh
    import fast_simplification
    ratio = 1.0 - target_triangles / mesh.triangle_count
    pts, faces = fast_simplification.simplify(mesh.vertices.astype(np.float32), mesh.faces.astype(np.int32),
                                              target_reduction=float(min(0.98, max(0.0, ratio))))
    out = MeshData(np.asarray(pts, np.float64), np.asarray(faces, np.int64))
    return out.compute_normals()


def _submesh(m: MeshData, faces_sel: np.ndarray) -> MeshData:
    """Lưới con gồm các mặt được chọn; đỉnh thu gọn nhưng GIỮ pháp tuyến/UV (texture không hỏng)."""
    f = m.faces[faces_sel]
    used, inv = np.unique(f.ravel(), return_inverse=True)
    return MeshData(m.vertices[used], inv.reshape(-1, 3).astype(np.int64),
                    None if m.normals is None else m.normals[used], None if m.uvs is None else m.uvs[used])


def _face_components(m: MeshData) -> np.ndarray:
    """Nhãn thành phần liên thông cho từng mặt (đỉnh trùng vị trí được gộp — đường nối UV không tách thành phần)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    v = m.vertices
    scale = float(np.ptp(v, axis=0).max()) or 1.0
    q = np.round(v / (scale * 1e-6)).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    f = inv.reshape(-1)[m.faces]
    n = int(f.max()) + 1 if len(f) else 0
    rows = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    cols = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    g = coo_matrix((np.ones(len(rows), np.int8), (rows, cols)), shape=(n, n))
    _, labels = connected_components(g, directed=False)
    return labels[f[:, 0]]


def clean_mesh(m: MeshData, min_component_ratio: float = 0.002) -> tuple[MeshData, dict]:
    """Làm sạch lưới AI (marching cubes/diffusion): bỏ mặt trùng đỉnh, mặt suy biến (diện tích ≈ 0 so với cạnh dài
    nhất — cùng tiêu chí validator), mặt trùng lặp, và mảnh vụn lơ lửng rất nhỏ. Trả (lưới, thống kê)."""
    v, f = m.vertices, m.faces
    stats = {"input_faces": int(len(f))}
    keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    e2 = np.maximum.reduce([np.sum((v[f[:, 1]] - v[f[:, 0]]) ** 2, axis=1), np.sum((v[f[:, 2]] - v[f[:, 1]]) ** 2, axis=1),
                            np.sum((v[f[:, 0]] - v[f[:, 2]]) ** 2, axis=1)])
    keep &= area > 1e-7 * e2 + 1e-30
    stats["degenerate_removed"] = int(len(f) - keep.sum())
    idx = np.nonzero(keep)[0]
    srt = np.sort(f[idx], axis=1)
    _, first = np.unique(srt, axis=0, return_index=True)
    stats["duplicate_removed"] = int(len(idx) - len(first))
    idx = idx[np.sort(first)]
    out = _submesh(m, idx)
    if len(out.faces) and min_component_ratio > 0:
        lab = _face_components(out)
        counts = np.bincount(lab)
        big = counts >= max(8, int(min_component_ratio * len(out.faces)))
        if big.any() and not big.all():
            sel = big[lab]
            stats["floaters_removed"] = int((~sel).sum())
            out = _submesh(out, np.nonzero(sel)[0])
    stats["output_faces"] = int(len(out.faces))
    if out.normals is None:
        out = out.compute_normals()
    return out, stats


def split_components(m: MeshData, max_parts: int = 24, min_ratio: float = 0.01) -> list[MeshData]:
    """Tách lưới một khối thành các thành phần liên thông lớn (bộ phận tách rời thật trong mesh AI).

    Thành phần nhỏ hơn min_ratio số mặt được gộp vào thành phần lớn nhất. Trả [m] nếu chỉ có một thành phần đáng kể."""
    if not len(m.faces):
        return [m]
    lab = _face_components(m)
    counts = np.bincount(lab)
    order = np.argsort(-counts)
    big = [c for c in order if counts[c] >= min_ratio * len(m.faces)][:max_parts]
    if len(big) <= 1:
        return [m]
    target = np.full(len(counts), big[0])
    for c in big:
        target[c] = c
    fl = target[lab]
    return [_submesh(m, np.nonzero(fl == c)[0]) for c in big]


def import_glb(path: Path, project_dir: Path, *, target_size_mm: float | None, limits: Limits,
               max_triangles: int, clean: bool = False, split: bool = False) -> ImportedModel:
    """clean/split: dành cho mesh AI (cloud/HF Space) — làm sạch rồi tách thành phần liên thông thành bộ phận."""
    data = path.read_bytes()
    rep = validate_glb_bytes(data, limits, path.name, mesh_quality=not clean)
    if not rep.ok:
        raise AssetError("; ".join(rep.errors[:3]))
    doc = gltf.read_glb(data, to_mm=True)
    tex_dir = project_dir / "textures"
    saved: dict[int, str] = {}
    for ti, tex in enumerate(doc.textures):
        src = tex.get("source")
        if src is None or not (0 <= src < len(doc.images)):
            continue
        img, mime = doc.images[src]
        if not img or mime == "external":
            continue
        tex_dir.mkdir(parents=True, exist_ok=True)
        ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
        rel = f"textures/src_{ti}{ext}"
        (project_dir / rel).write_bytes(img)
        saved[ti] = rel
    materials: dict[str, Material] = {}
    ids: list[str] = []
    for i, mj in enumerate(doc.materials):
        m = gltf.material_from_gltf(i, mj, saved)
        pbr = (mj.get("pbrMetallicRoughness") or {}) if isinstance(mj, dict) else {}
        if clean and "metallicFactor" not in pbr and "metallicRoughnessTexture" not in pbr:
            # Mesh AI (TRELLIS…) hay bỏ trống metallicFactor → chuẩn glTF hiểu là 1,0 (kim loại hoàn toàn), khiến gốm/nhựa
            # trông tối và bóng như kim loại. Không có bản đồ kim loại thì coi là phi kim.
            m.metallic = 0.0
        m.id = f"mat_{i}"
        materials[m.id] = m
        ids.append(m.id)
    if "mat_default" not in materials:
        materials["mat_default"] = Material(id="mat_default", name="Mặc định", kind="plastic",
                                            base_color=[0.7, 0.7, 0.72, 1.0], metallic=0.0, roughness=0.5)
    parts: list[ImportedPart] = []
    for k, node in enumerate(doc.nodes):
        meshes = []
        for prim in node.primitives:
            m = prim.mesh
            if m.normals is None or not np.isfinite(m.normals).all():
                m = m.compute_normals()
            else:
                n = np.linalg.norm(m.normals, axis=1, keepdims=True)
                m.normals = m.normals / np.maximum(n, 1e-12)
            mid = ids[prim.material] if prim.material is not None and 0 <= prim.material < len(ids) else "mat_default"
            meshes.append((m, mid))
        if meshes:
            parts.append(ImportedPart(node.name or f"Phần {k + 1}", meshes))
    if not parts:
        raise AssetError("GLB không có lưới nào")
    warnings = list(rep.warnings[:5])
    if clean:
        removed = 0
        for p in parts:
            cleaned = []
            for m, mid in p.meshes:
                cm, st = clean_mesh(m)
                removed += st["input_faces"] - st["output_faces"]
                if cm.triangle_count:
                    cleaned.append((cm, mid))
            p.meshes = cleaned
        parts = [p for p in parts if p.meshes]
        if not parts:
            raise AssetError("GLB chỉ gồm tam giác suy biến")
        if removed:
            warnings.append(f"Đã làm sạch lưới AI: bỏ {removed:,} tam giác suy biến/trùng/mảnh vụn.")
    if split and len(parts) == 1 and len(parts[0].meshes) == 1:
        m, mid = parts[0].meshes[0]
        comps = split_components(m)
        if len(comps) > 1:
            parts = [ImportedPart(f"Phần {i + 1}", [(c, mid)]) for i, c in enumerate(comps)]
            warnings.append(f"Tách {len(comps)} bộ phận theo thành phần liên thông của lưới (ước lượng, không phải "
                            "logic lắp ráp).")
    total = sum(m.triangle_count for p in parts for m, _ in p.meshes)
    if total > max_triangles:
        keep = max_triangles / total
        for p in parts:
            p.meshes = [(decimate(m, int(m.triangle_count * keep)), mid) for m, mid in p.meshes]
        warnings.append(f"Đã giảm lưới {total:,} → ~{int(total * keep):,} tam giác để vừa ngân sách.")
    allv = np.vstack([m.vertices for p in parts for m, _ in p.meshes])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    size = float((hi - lo).max()) or 1.0
    k = (float(target_size_mm) / size) if target_size_mm else 1.0
    shift = np.array([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    for p in parts:
        for m, _ in p.meshes:
            m.vertices = (m.vertices + shift) * k
    return ImportedModel(parts, materials, k, warnings, total)
