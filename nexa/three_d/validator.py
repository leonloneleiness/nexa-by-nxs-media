"""Kiểm tra deterministic cho asset 3D: định dạng GLB, đường dẫn an toàn, hình học lưới.

- Đường dẫn: chỉ chấp nhận đường dẫn TƯƠNG ĐỐI nằm trong thư mục dự án (chặn "..", đường dẫn tuyệt đối, ổ đĩa,
  UNC, URI, symlink trỏ ra ngoài).
- GLB: magic/phiên bản/độ dài, chunk JSON hợp lệ, không URI ngoài (http/file/đường dẫn), không extension bắt buộc
  chưa hỗ trợ (Draco…), accessor trong phạm vi buffer, chỉ số tam giác hợp lệ, không NaN/Infinity, pháp tuyến đơn
  vị, tỷ lệ tam giác suy biến, số tam giác và kích thước texture trong giới hạn, cây node không vòng lặp.
- Lưới: kín (mỗi cạnh đúng 2 mặt sau khi hàn đỉnh trùng vị trí), hướng pháp tuyến ra ngoài.
"""
from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from nexa.three_d.geometry import gltf
from nexa.three_d.geometry.kernel import MeshData

SUPPORTED_EXTENSIONS = {"KHR_materials_emissive_strength", "KHR_texture_transform", "KHR_materials_clearcoat",
                        "KHR_materials_specular", "KHR_materials_ior", "KHR_materials_transmission",
                        "KHR_materials_unlit", "KHR_mesh_quantization"}


class AssetError(ValueError):
    """Asset không an toàn hoặc sai định dạng."""


@dataclass
class Limits:
    max_asset_mb: float = 200.0
    max_triangles: int = 2_000_000
    max_texture_size: int = 4096
    max_degenerate_ratio: float = 0.02
    max_nodes: int = 5000

    @classmethod
    def from_config(cls, cfg: Any) -> "Limits":
        g = (lambda k, d: cfg.get(f"three_d.{k}", d)) if cfg is not None else (lambda k, d: d)
        return cls(max_asset_mb=float(g("max_asset_mb", 200)), max_triangles=int(g("max_triangles", 2_000_000)),
                   max_texture_size=int(g("max_texture_size", 4096)))


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationReport", prefix: str = "") -> None:
        self.errors += [prefix + e for e in other.errors]
        self.warnings += [prefix + w for w in other.warnings]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings), "stats": dict(self.stats)}


# ------------------------------------------------------------------ đường dẫn
_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def safe_relpath(base: Path, rel: str) -> Path:
    """Đường dẫn tuyệt đối an toàn cho `rel` bên trong `base`; ném AssetError nếu thoát ra ngoài."""
    if not isinstance(rel, str) or not rel.strip():
        raise AssetError("đường dẫn asset rỗng")
    r = rel.strip()
    if "\x00" in r:
        raise AssetError("đường dẫn chứa ký tự NUL")
    if _URI_RE.match(r) or r.startswith(("\\\\", "//")):
        raise AssetError(f"không chấp nhận URI/đường dẫn mạng: {r[:60]}")
    if os.path.isabs(r) or re.match(r"^[a-zA-Z]:", r) or r.startswith(("/", "\\")):
        raise AssetError(f"không chấp nhận đường dẫn tuyệt đối: {r[:60]}")
    parts = re.split(r"[\\/]+", r)
    if any(p == ".." for p in parts):
        raise AssetError(f"đường dẫn chứa '..': {r[:60]}")
    base_res = Path(base).resolve()
    full = (base_res / Path(*parts)).resolve()
    try:
        full.relative_to(base_res)
    except ValueError as exc:
        raise AssetError(f"đường dẫn trỏ ra ngoài thư mục dự án: {r[:60]}") from exc
    return full


# ------------------------------------------------------------------ ảnh
def image_size(data: bytes) -> tuple[int, int] | None:
    """(rộng, cao) của PNG/JPEG từ header; None nếu không nhận ra."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return int(w), int(h)
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    return None


# ------------------------------------------------------------------ lưới
def mesh_report(mesh: MeshData, name: str = "", check_watertight: bool = True) -> ValidationReport:
    rep = ValidationReport()
    v, f = mesh.vertices, mesh.faces
    rep.stats.update({"triangles": int(len(f)), "vertices": int(len(v))})
    if len(f) == 0:
        rep.errors.append(f"{name}: lưới rỗng")
        return rep
    if not np.isfinite(v).all():
        rep.errors.append(f"{name}: có tọa độ NaN/Infinity")
        return rep
    if f.min() < 0 or f.max() >= len(v):
        rep.errors.append(f"{name}: chỉ số tam giác vượt số đỉnh")
        return rep
    if mesh.normals is not None:
        if not np.isfinite(mesh.normals).all():
            rep.errors.append(f"{name}: pháp tuyến NaN/Infinity")
        else:
            ln = np.linalg.norm(mesh.normals, axis=1)
            bad = float(np.mean(np.abs(ln - 1) > 0.02))
            rep.stats["bad_normal_ratio"] = bad
            if bad > 0.001:
                rep.errors.append(f"{name}: {bad:.1%} pháp tuyến không phải vector đơn vị")
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    e2 = np.maximum.reduce([np.sum((v[f[:, 1]] - v[f[:, 0]]) ** 2, axis=1), np.sum((v[f[:, 2]] - v[f[:, 1]]) ** 2, axis=1),
                            np.sum((v[f[:, 0]] - v[f[:, 2]]) ** 2, axis=1)])
    # suy biến = gần thẳng hàng/trùng đỉnh: diện tích ≈ 0 so với bình phương cạnh dài nhất (không phụ thuộc đơn vị,
    # bền với lượng tử hóa float32 của GLB); tam giác mảnh nhưng có diện tích vẫn hiển thị đúng nên không tính.
    n_degen = int(np.sum(area <= 1e-7 * e2 + 1e-30))
    degen = n_degen / len(f)
    rep.stats["degenerate_ratio"] = degen
    rep.stats["degenerate"] = n_degen
    # lưới nhỏ có vài tam giác thẳng hàng (T-junction của boolean) là vô hại — chỉ lỗi khi nhiều và đáng kể
    if degen > 0.05 and n_degen >= 20:
        rep.errors.append(f"{name}: {degen:.1%} tam giác suy biến")
    elif degen > 0.002:
        rep.warnings.append(f"{name}: {degen:.2%} tam giác suy biến")
    lo, hi = v.min(axis=0), v.max(axis=0)
    rep.stats["bounds"] = {"min": lo.tolist(), "max": hi.tolist()}
    if float(np.ptp(v, axis=0).max()) <= 0:
        rep.errors.append(f"{name}: hộp bao có kích thước 0")
    if check_watertight:
        wt, open_edges, nonmanifold = watertight(mesh)
        rep.stats.update({"watertight": wt, "open_edges": open_edges, "nonmanifold_edges": nonmanifold})
        if not wt:
            rep.warnings.append(f"{name}: lưới hở ({open_edges} cạnh hở, {nonmanifold} cạnh không đa tạp)")
        else:
            vol = MeshData(*weld(mesh)).signed_volume()
            rep.stats["volume"] = vol
            if vol < 0:
                rep.errors.append(f"{name}: pháp tuyến quay vào trong (thể tích âm)")
    return rep


def weld(mesh: MeshData, tol: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Gộp đỉnh trùng vị trí (lưới xuất có tách đỉnh ở cạnh sắc/đường nối UV)."""
    v = mesh.vertices
    scale = float(np.ptp(v, axis=0).max()) or 1.0
    q = np.round(v / (tol or scale * 1e-6)).astype(np.int64)
    _, idx, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return v[idx], inv.reshape(-1)[mesh.faces]


def watertight(mesh: MeshData) -> tuple[bool, int, int]:
    _, f = weld(mesh)
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    e = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    open_edges = int((counts == 1).sum())
    nonman = int((counts > 2).sum())
    return open_edges == 0 and nonman == 0, open_edges, nonman


# ------------------------------------------------------------------ GLB
def validate_glb_bytes(data: bytes, limits: Limits | None = None, name: str = "GLB",
                       mesh_quality: bool = True) -> ValidationReport:
    """mesh_quality=False: chỉ kiểm tra cấu trúc/an toàn (URI ngoài, giới hạn, NaN) — dùng cho mesh AI trước khi làm
    sạch; tỷ lệ tam giác suy biến và số tam giác được kiểm lại trên lưới đã làm sạch."""
    lim = limits or Limits()
    rep = ValidationReport()
    rep.stats["bytes"] = len(data)
    if len(data) > lim.max_asset_mb * 1024 * 1024:
        rep.errors.append(f"{name}: dung lượng {len(data) / 1e6:.1f} MB vượt giới hạn {lim.max_asset_mb:g} MB")
        return rep
    try:
        js, bin_chunk = gltf.parse_container(data)
    except gltf.GlbError as exc:
        rep.errors.append(f"{name}: {exc}")
        return rep
    asset = js.get("asset") or {}
    if str(asset.get("version", "")) != "2.0":
        rep.errors.append(f"{name}: asset.version phải là 2.0")
    unsupported = [e for e in js.get("extensionsRequired") or [] if e not in SUPPORTED_EXTENSIONS]
    if unsupported:
        rep.errors.append(f"{name}: yêu cầu extension chưa hỗ trợ {unsupported}")
    for i, buf in enumerate(js.get("buffers") or []):
        if "uri" in buf:
            rep.errors.append(f"{name}: buffer {i} dùng URI ngoài ({str(buf['uri'])[:40]}) — chỉ chấp nhận buffer nhúng")
    for i, img in enumerate(js.get("images") or []):
        if "uri" in img:
            uri = str(img["uri"])
            if not uri.startswith("data:image/"):
                rep.errors.append(f"{name}: ảnh {i} dùng URI ngoài ({uri[:40]}) — không được phép")
    if len(js.get("nodes") or []) > lim.max_nodes:
        rep.errors.append(f"{name}: quá nhiều node ({len(js['nodes'])})")
    for i, bv in enumerate(js.get("bufferViews") or []):
        if int(bv.get("byteOffset", 0)) + int(bv.get("byteLength", 0)) > len(bin_chunk):
            rep.errors.append(f"{name}: bufferView {i} vượt ra ngoài buffer")
    if rep.errors:
        return rep
    try:
        doc = gltf.read_glb(data)
    except gltf.GlbError as exc:
        rep.errors.append(f"{name}: {exc}")
        return rep
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        rep.errors.append(f"{name}: cấu trúc glTF hỏng ({type(exc).__name__})")
        return rep
    tris = 0
    degen = 0
    allv = []
    for node in doc.nodes:
        for prim in node.primitives:
            m = prim.mesh
            tris += m.triangle_count
            r = mesh_report(m, f"{name}/{node.name}", check_watertight=False)
            rep.errors += [e for e in r.errors if "suy biến" not in e]
            degen += int(r.stats.get("degenerate", 0))
            if len(m.vertices):
                allv.append(m.vertices)
    rep.stats["triangles"] = tris
    rep.stats["degenerate_ratio"] = degen / max(1, tris)
    if mesh_quality and degen / max(1, tris) > lim.max_degenerate_ratio:
        rep.errors.append(f"{name}: {degen / tris:.1%} tam giác suy biến trên toàn mô hình")
    elif degen:
        rep.warnings.append(f"{name}: {degen} tam giác suy biến ({degen / tris:.2%}, vô hại khi hiển thị)")
    rep.stats["nodes"] = len(doc.nodes)
    if tris == 0:
        rep.errors.append(f"{name}: không có tam giác nào")
    if tris > lim.max_triangles * (1 if mesh_quality else 5):
        rep.errors.append(f"{name}: {tris:,} tam giác vượt giới hạn {lim.max_triangles:,}")
    sizes = []
    for i, (img, mime) in enumerate(doc.images):
        if mime == "external":
            continue
        sz = image_size(img)
        if sz is None:
            rep.warnings.append(f"{name}: không đọc được kích thước ảnh {i}")
            continue
        sizes.append(sz)
        if max(sz) > lim.max_texture_size:
            rep.errors.append(f"{name}: texture {i} {sz[0]}×{sz[1]} vượt {lim.max_texture_size}")
    rep.stats["textures"] = sizes
    if allv:
        v = np.vstack(allv)
        rep.stats["bounds_mm"] = {"min": v.min(axis=0).tolist(), "max": v.max(axis=0).tolist()}
    return rep


def validate_glb_file(path: Path, limits: Limits | None = None) -> ValidationReport:
    lim = limits or Limits()
    try:
        size = path.stat().st_size
    except OSError as exc:
        rep = ValidationReport()
        rep.errors.append(f"không đọc được tệp {path.name}: {exc}")
        return rep
    if size > lim.max_asset_mb * 1024 * 1024:
        rep = ValidationReport()
        rep.errors.append(f"{path.name}: {size / 1e6:.1f} MB vượt giới hạn {lim.max_asset_mb:g} MB")
        return rep
    return validate_glb_bytes(path.read_bytes(), lim, path.name)
