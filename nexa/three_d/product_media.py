"""Local PNG / MP4 product renders. Frames stream to disk with constant framing."""
from __future__ import annotations

import math
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from nexa.three_d.geometry import gltf
from nexa.three_d.models import Material
from nexa.three_d.render import render, png_bytes


@dataclass(frozen=True)
class MediaOptions:
    kind: str = "png"
    size: int = 768
    background: str = "light"
    seconds: int = 6
    yaw: float = 35
    pitch: float = 20
    fps: int = 24

    def validate(self):
        if self.kind not in ("png", "mp4") or self.background not in ("light", "dark"):
            raise ValueError("Định dạng hoặc nền không hợp lệ.")
        if self.size not in (256, 512, 768, 1024) or self.seconds not in (3, 6, 10) or self.fps != 24:
            raise ValueError("Kích thước hoặc thời lượng không hợp lệ.")
        if not math.isfinite(self.yaw) or not math.isfinite(self.pitch) or not -80 <= self.pitch <= 80:
            raise ValueError("Góc nhìn không hợp lệ.")


class MediaCancelled(Exception):
    pass


def export_media(store, project_id: str, destination: Path, options: MediaOptions,
                 cancel: threading.Event, progress=lambda value: None) -> Path:
    options.validate()

    def check():
        if cancel.is_set():
            raise MediaCancelled("Đã hủy xuất ảnh/video.")

    check()
    project = store.load(project_id)
    doc = gltf.read_glb(store.resolve(project_id, project.asset_path).read_bytes())
    destination.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w-]+", "_", project.name).strip("_")[:80] or "product"
    target = destination / f"{name}_{uuid.uuid4().hex[:12]}.{options.kind}"
    # Temporary files stay on the same volume; only completed media is published.
    with tempfile.TemporaryDirectory(prefix=".nexa-media-", dir=destination) as tmp:
        root = Path(tmp)
        saved = {}
        for i, tex in enumerate(doc.textures):
            source = tex.get("source")
            if isinstance(source, int) and 0 <= source < len(doc.images):
                raw, _mime = doc.images[source]
                rel = f"texture_{i}.png"
                (root / rel).write_bytes(raw)
                saved[i] = rel
        mats = [gltf.material_from_gltf(i, m, saved) for i, m in enumerate(doc.materials)]
        meshes = [(p.mesh, mats[p.material] if p.material is not None and 0 <= p.material < len(mats)
                   else Material(id="default", name="Default"))
                  for n in doc.nodes for p in n.primitives if p.mesh.triangle_count]
        if not meshes:
            raise ValueError("Mô hình không có bề mặt để xuất.")
        lo = np.min([m.vertices.min(axis=0) for m, _ in meshes], axis=0)
        hi = np.max([m.vertices.max(axis=0) for m, _ in meshes], axis=0)
        extent = float(np.linalg.norm(hi - lo) / 2)
        count = options.seconds * options.fps if options.kind == "mp4" else 1
        partial = root / f"output.{options.kind}"
        writer = None
        try:
            if options.kind == "mp4":
                import cv2
                writer = cv2.VideoWriter(str(partial), cv2.VideoWriter_fourcc(*"mp4v"),
                                         options.fps, (options.size, options.size))
                if not writer.isOpened():
                    raise RuntimeError("Không mở được bộ mã hóa MP4 trên máy này.")
            for i in range(count):
                check()
                yaw = math.radians(options.yaw + 360 * i / count if count > 1 else options.yaw)
                pitch = math.radians(options.pitch)
                camera = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
                frame = render(meshes, view=camera, size=options.size, background=options.background,
                               bounds=(lo, hi), fixed_extent=extent, ssaa=1, outline=False,
                               texture_root=root).image
                check()
                if writer is None:
                    partial.write_bytes(png_bytes(frame))
                else:
                    writer.write(np.ascontiguousarray(frame[:, :, ::-1]))
                progress(round((i + 1) * 100 / count))
        finally:
            if writer is not None:
                writer.release()
        check()
        if options.kind == "mp4":
            cap = cv2.VideoCapture(str(partial))
            try:
                ok, _ = cap.read()
                if not ok or int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) != count:
                    raise RuntimeError("Video xuất chưa đầy đủ; vui lòng thử lại.")
            finally:
                cap.release()
        if not partial.exists() or partial.stat().st_size == 0:
            raise RuntimeError("Không tạo được file ảnh/video.")
        partial.rename(target)
    return target
