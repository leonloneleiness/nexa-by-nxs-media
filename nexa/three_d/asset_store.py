"""Kho asset nội bộ (cache) cho mô hình 3D: mỗi dự án một thư mục trong %LOCALAPPDATA%\\NEXA\\3d_cache\\projects.

<id>/manifest.json   — assembly manifest (models.Model3DProject)
<id>/model.glb       — toàn bộ mô hình (mét, glTF 2.0) — dùng để xuất/đối chiếu
<id>/parts/*.glb     — từng bộ phận (viewer nạp riêng để tách/ẩn/chọn)
<id>/textures/*.png, <id>/renders/*.png, <id>/thumbnail.png, <id>/source/* (tệp gốc từ provider cloud)

Người dùng không phải thao tác tệp. Cache tra theo khóa spec (cùng spec + cùng phiên bản bộ sinh → dùng lại),
dọn theo LRU khi vượt cache_size_mb. Mọi đường dẫn đọc từ manifest đi qua validator.safe_relpath.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from nexa.three_d.manifest import MANIFEST_NAME, load_manifest, save_manifest
from nexa.three_d.models import Model3DProject
from nexa.three_d.validator import AssetError, safe_relpath
from nexa.utils.logging import get_logger

log = get_logger("3d.store")

INDEX_NAME = "index.json"
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")


def default_cache_dir() -> Path:
    from nexa.utils.config import LOCAL_DATA_DIR
    return LOCAL_DATA_DIR / "3d_cache"


class AssetStore:
    def __init__(self, root: Path | None = None, cache_size_mb: float = 4096.0, keep_generated: bool = True) -> None:
        self.root = Path(root) if root else default_cache_dir()
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.cache_size_mb = float(cache_size_mb)
        self.keep_generated = keep_generated
        self._lock = threading.RLock()
        self._index = self._load_index()

    @classmethod
    def from_config(cls, cfg: Any) -> "AssetStore":
        raw = (cfg.get("three_d.cache_dir") or "").strip() if cfg is not None else ""
        root = None
        if raw:
            from nexa.utils.config import expand_path
            root = expand_path(raw)
        return cls(root, float(cfg.get("three_d.cache_size_mb") or 4096) if cfg is not None else 4096,
                   bool(cfg.get("three_d.keep_generated_assets", True)) if cfg is not None else True)

    # ----- chỉ mục -----
    def _load_index(self) -> dict:
        try:
            data = json.loads((self.root / INDEX_NAME).read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("projects"), dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"projects": {}, "by_key": {}}

    def _save_index(self) -> None:
        tmp = self.root / (INDEX_NAME + ".tmp")
        tmp.write_text(json.dumps(self._index, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / INDEX_NAME)

    # ----- đường dẫn -----
    def project_dir(self, project_id: str) -> Path:
        if not _ID_RE.match(project_id or ""):
            raise AssetError(f"id dự án không hợp lệ: {project_id!r}")
        d = (self.projects_dir / project_id).resolve()
        d.relative_to(self.projects_dir.resolve())
        return d

    def new_project_dir(self, project_id: str) -> Path:
        d = self.project_dir(project_id)
        d.mkdir(parents=True, exist_ok=False)
        return d

    def resolve(self, project_id: str, rel: str) -> Path:
        return safe_relpath(self.project_dir(project_id), rel)

    # ----- lưu / đọc -----
    def commit(self, project: Model3DProject) -> None:
        """Ghi manifest và đăng ký dự án vào chỉ mục (sau khi đã ghi đủ asset)."""
        d = self.project_dir(project.id)
        save_manifest(project, d)
        size = _dir_size(d)
        with self._lock:
            self._index["projects"][project.id] = {
                "name": project.name, "category": project.category, "status": project.status,
                "quality_score": project.quality_score, "created_at": project.created_at, "last_used": time.time(),
                "bytes": size, "cache_key": project.cache_key, "thumbnail": project.thumbnail_path,
                "prompt": project.source_prompt[:200], "mode": project.generation_mode}
            if project.cache_key and project.status == "ready":
                self._index["by_key"][project.cache_key] = project.id
            self._save_index()
        self.evict()

    def load(self, project_id: str) -> Model3DProject:
        d = self.project_dir(project_id)
        project = load_manifest(d)
        if project.id != project_id:
            raise AssetError("id trong manifest không khớp thư mục")
        with self._lock:
            if project_id in self._index["projects"]:
                self._index["projects"][project_id]["last_used"] = time.time()
                self._save_index()
        return project

    def find_cached(self, cache_key: str) -> Model3DProject | None:
        with self._lock:
            pid = self._index["by_key"].get(cache_key)
        if not pid:
            return None
        try:
            project = self.load(pid)
        except AssetError:
            with self._lock:
                self._index["by_key"].pop(cache_key, None)
                self._save_index()
            return None
        if project.status != "ready" or not (self.project_dir(pid) / project.asset_path).is_file():
            return None
        return project

    def latest(self, ready_only: bool = True) -> str | None:
        with self._lock:
            items = [(v.get("created_at", 0), k) for k, v in self._index["projects"].items()
                     if not ready_only or v.get("status") == "ready"]
        return max(items)[1] if items else None

    def list_projects(self, limit: int | None = 30) -> list[dict]:
        with self._lock:
            items = sorted(self._index["projects"].items(), key=lambda kv: -kv[1].get("created_at", 0))[:limit]
        return [dict(v, id=k) for k, v in items]

    def delete(self, project_id: str) -> None:
        d = self.project_dir(project_id)
        with self._lock:
            info = self._index["projects"].pop(project_id, None)
            if info and info.get("cache_key") and self._index["by_key"].get(info["cache_key"]) == project_id:
                self._index["by_key"].pop(info["cache_key"], None)
            self._save_index()
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    def discard(self, project_id: str) -> None:
        """Bỏ dự án dở dang (job lỗi/hủy) — không để rác trong cache."""
        try:
            d = self.project_dir(project_id)
        except AssetError:
            return
        with self._lock:
            known = project_id in self._index["projects"]
        if not known and d.exists():
            shutil.rmtree(d, ignore_errors=True)

    def evict(self) -> list[str]:
        """Xóa dự án dùng lâu nhất cho tới khi tổng dung lượng ≤ cache_size_mb (không xóa dự án mới nhất)."""
        removed: list[str] = []
        limit = self.cache_size_mb * 1024 * 1024
        with self._lock:
            items = sorted(self._index["projects"].items(), key=lambda kv: kv[1].get("last_used", 0))
            total = sum(v.get("bytes", 0) for _, v in items)
            newest = max(items, key=lambda kv: kv[1].get("created_at", 0))[0] if items else None
        for pid, info in items:
            if total <= limit:
                break
            if pid == newest:
                continue
            total -= info.get("bytes", 0)
            self.delete(pid)
            removed.append(pid)
        if removed:
            log.info("Dọn cache 3D: xóa %d dự án cũ", len(removed))
        return removed

    def total_bytes(self) -> int:
        with self._lock:
            return sum(v.get("bytes", 0) for v in self._index["projects"].values())


def _dir_size(d: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(d):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def export_project(store: AssetStore, project_id: str, fmt: str, dest_dir: Path) -> Path:
    """Xuất mô hình ra thư mục người dùng: glb | stl | obj | 3mf. Không ghi đè tệp có sẵn."""
    from nexa.three_d.geometry import gltf
    project = store.load(project_id)
    src = store.resolve(project_id, project.asset_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]+", "_", project.name, flags=re.UNICODE).strip("_") or "mo_hinh"
    fmt = fmt.lower()
    target = _unique(dest_dir / f"{safe_name}.{fmt}")
    if fmt == "glb":
        shutil.copy2(src, target)
        return target
    doc = gltf.read_glb(src.read_bytes())
    meshes = [(node.name, prim.mesh) for node in doc.nodes for prim in node.primitives]
    if fmt == "stl":
        _write_stl(target, meshes)
    elif fmt == "obj":
        _write_obj(target, meshes)
    elif fmt == "3mf":
        _write_3mf(target, meshes, project.name)
    else:
        raise AssetError(f"định dạng xuất '{fmt}' chưa hỗ trợ (glb, stl, obj, 3mf)")
    return target


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        p = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not p.exists():
            return p
    raise AssetError("không tìm được tên tệp trống")


def _write_stl(path: Path, meshes) -> None:
    import struct

    import numpy as np
    tris = []
    for _, m in meshes:
        # mm (STL không có đơn vị — quy ước mm cho in 3D), đổi sang Z lên như phần mềm slicer mặc định
        zup = np.column_stack([m.vertices[:, 0], -m.vertices[:, 2], m.vertices[:, 1]])
        v = zup[m.faces]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        tris.append(np.hstack([n, v.reshape(-1, 9)]).astype(np.float32))
    data = np.vstack(tris) if tris else np.zeros((0, 12), np.float32)
    rec = np.zeros(len(data), dtype=[("d", np.float32, (12,)), ("a", np.uint16)])
    rec["d"] = data
    with path.open("wb") as fh:
        fh.write(b"NEXA 3D export (mm)".ljust(80, b" "))
        fh.write(struct.pack("<I", len(data)))
        fh.write(rec.tobytes())


def _write_obj(path: Path, meshes) -> None:
    lines = ["# NEXA 3D export, đơn vị mm"]
    off = 1
    for name, m in meshes:
        lines.append(f"o {re.sub(r'[^A-Za-z0-9_]+', '_', name)}")
        lines += [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in m.vertices]
        lines += [f"f {a + off} {b + off} {c + off}" for a, b, c in m.faces]
        off += len(m.vertices)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_3mf(path: Path, meshes, title: str) -> None:
    import zipfile
    from xml.sax.saxutils import escape
    objs = []
    for i, (name, m) in enumerate(meshes, start=1):
        vs = "".join(f'<vertex x="{x:.5f}" y="{-z:.5f}" z="{y:.5f}"/>' for x, y, z in m.vertices)   # 3MF: Z lên
        ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
        objs.append(f'<object id="{i}" type="model" name="{escape(name)}"><mesh><vertices>{vs}</vertices>'
                    f'<triangles>{ts}</triangles></mesh></object>')
    items = "".join(f'<item objectid="{i}"/>' for i in range(1, len(meshes) + 1))
    model = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="vi" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<metadata name="Title">{escape(title)}</metadata><resources>{"".join(objs)}</resources>'
             f'<build>{items}</build></model>')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
                     'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                     'relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing'
                     '-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanu'
            'facturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


__all__ = ["AssetStore", "export_project", "default_cache_dir", "MANIFEST_NAME"]
