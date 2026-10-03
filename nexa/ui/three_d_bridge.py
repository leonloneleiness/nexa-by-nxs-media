"""Cầu nối Python ⇄ QML cho mô hình 3D (context property `nexa3d`) và kiểu QML `NexaMesh` (Nexa3D 1.0).

- Lưới của từng bộ phận được đọc từ GLB trong cache và đóng gói (float32 xen kẽ: vị trí, pháp tuyến, UV) ở LUỒNG NỀN;
  luồng GUI chỉ gán QByteArray cho QQuick3DGeometry — không khóa giao diện, không chặn camera cử chỉ.
- Tọa độ gửi QML là "đơn vị xem": (mm − tâm mô hình) × (100 / bán kính) để bu-lông 30 mm và trực thăng 12 m đều hiển
  thị ở cùng cỡ; kích thước thật (mm) vẫn hiện trong bảng thông tin.
- Nhận sự kiện controller qua post(kind, data) (luồng bất kỳ) → tín hiệu queued về luồng GUI.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Property, QByteArray, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QVector3D
from PySide6.QtQuick3D import QQuick3DGeometry

from nexa.utils.logging import get_logger

log = get_logger("ui.3d")
VIEW_RADIUS = 100.0


@dataclass
class PackedMesh:
    vertices: bytes
    indices: bytes
    stride: int
    has_uv: bool
    bmin: tuple[float, float, float]
    bmax: tuple[float, float, float]
    lines: bool = False


class MeshStore:
    """Kho lưới đã đóng gói (key → PackedMesh), dùng chung giữa luồng nạp và NexaMesh."""
    _lock = threading.Lock()
    _data: dict[str, PackedMesh] = {}

    @classmethod
    def put(cls, key: str, mesh: PackedMesh) -> None:
        with cls._lock:
            cls._data[key] = mesh

    @classmethod
    def get(cls, key: str) -> PackedMesh | None:
        with cls._lock:
            return cls._data.get(key)

    @classmethod
    def clear(cls, prefix: str = "") -> None:
        with cls._lock:
            for k in [k for k in cls._data if k.startswith(prefix)]:
                cls._data.pop(k, None)


def _tangents(v: np.ndarray, f: np.ndarray, n: np.ndarray, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Tangent/binormal theo đỉnh (cộng dồn theo tam giác rồi trực chuẩn hóa Gram–Schmidt với pháp tuyến)."""
    e1, e2 = v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]
    d1, d2 = uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]
    r = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(r) < 1e-12, 1.0, r)
    tf = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / r[:, None]
    bf = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / r[:, None]
    t = np.zeros_like(v)
    b = np.zeros_like(v)
    for k in range(3):
        np.add.at(t, f[:, k], tf)
        np.add.at(b, f[:, k], bf)
    t -= n * np.einsum("ij,ij->i", n, t)[:, None]
    bad = np.linalg.norm(t, axis=1) < 1e-12
    if bad.any():                                    # đỉnh suy biến: chọn trục bất kỳ vuông góc pháp tuyến
        alt = np.where(np.abs(n[bad, 0:1]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
        t[bad] = alt - n[bad] * np.einsum("ij,ij->i", n[bad], alt)[:, None]
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    bn = np.cross(n, t)
    sign = np.where(np.einsum("ij,ij->i", bn, b) < 0, -1.0, 1.0)
    return t, bn * sign[:, None]


def pack_mesh(vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray | None, uvs: np.ndarray | None,
              center: np.ndarray, k: float) -> PackedMesh:
    v = ((vertices - center) * k).astype(np.float32)
    if normals is None:
        from nexa.three_d.geometry.kernel import MeshData
        normals = MeshData(vertices, faces).compute_normals().normals
    n = normals.astype(np.float32)
    cols = [v, n]
    if uvs is not None:
        uv = uvs.astype(np.float32).copy()
        uv[:, 1] = 1.0 - uv[:, 1]                    # glTF (v xuống) → Qt (v lên)
        t, bt = _tangents(vertices, faces, n.astype(np.float64), uv.astype(np.float64))
        cols += [uv, t.astype(np.float32), bt.astype(np.float32)]   # normal map cần tangent + binormal
    inter = np.ascontiguousarray(np.hstack(cols), dtype=np.float32)
    return PackedMesh(inter.tobytes(), np.ascontiguousarray(faces, dtype=np.uint32).tobytes(), inter.shape[1] * 4,
                      uvs is not None, tuple(float(x) for x in v.min(axis=0)), tuple(float(x) for x in v.max(axis=0)))


def pack_edges(vertices: np.ndarray, faces: np.ndarray, center: np.ndarray, k: float, max_edges: int = 200_000) -> PackedMesh:
    """Cạnh đặc trưng (góc nhị diện > 8° hoặc cạnh biên) cho chế độ khung dây — bỏ đường chéo của mặt phẳng."""
    from nexa.three_d.validator import weld
    from nexa.three_d.geometry.kernel import MeshData
    wv, wf = weld(MeshData(vertices, faces))
    fn = np.cross(wv[wf[:, 1]] - wv[wf[:, 0]], wv[wf[:, 2]] - wv[wf[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    e = np.vstack([wf[:, [0, 1]], wf[:, [1, 2]], wf[:, [2, 0]]])
    fid = np.tile(np.arange(len(wf)), 3)
    key = np.sort(e, axis=1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks, fs = key[order], fid[order]
    same = np.zeros(len(ks), bool)
    same[1:] = np.all(ks[1:] == ks[:-1], axis=1)
    first = np.nonzero(~same)[0]
    nxt = first + 1
    paired = np.zeros(len(first), bool)
    ok = nxt < len(ks)
    paired[ok] = same[nxt[ok]]
    cos = np.ones(len(first))
    cos[paired] = np.einsum("ij,ij->i", fn[fs[first[paired]]], fn[fs[first[paired] + 1]])
    edges = ks[first][(~paired) | (cos < 0.99)][:max_edges]
    v = ((wv - center) * k).astype(np.float32)
    inter = np.ascontiguousarray(np.hstack([v, np.zeros_like(v)]), dtype=np.float32)
    return PackedMesh(inter.tobytes(), np.ascontiguousarray(edges, dtype=np.uint32).tobytes(), 24, False,
                      tuple(float(x) for x in v.min(axis=0)), tuple(float(x) for x in v.max(axis=0)), lines=True)


class MeshGeometry(QQuick3DGeometry):
    """QML: NexaMesh { source: "<key>" } — lấy dữ liệu từ MeshStore."""
    sourceChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source = ""

    def _get_source(self) -> str:
        return self._source

    def _set_source(self, key: str) -> None:
        if key == self._source:
            return
        self._source = key
        self._rebuild()
        self.sourceChanged.emit()

    source = Property(str, _get_source, _set_source, notify=sourceChanged)

    def _rebuild(self) -> None:
        self.clear()
        mesh = MeshStore.get(self._source) if self._source else None
        if mesh is None:
            self.update()
            return
        self.setVertexData(QByteArray(mesh.vertices))
        self.setIndexData(QByteArray(mesh.indices))
        self.setStride(mesh.stride)
        A = QQuick3DGeometry.Attribute
        self.addAttribute(A.Semantic.PositionSemantic, 0, A.ComponentType.F32Type)
        if mesh.lines:
            self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Lines)
        else:
            self.addAttribute(A.Semantic.NormalSemantic, 12, A.ComponentType.F32Type)
            if mesh.has_uv:
                self.addAttribute(A.Semantic.TexCoord0Semantic, 24, A.ComponentType.F32Type)
                if mesh.stride >= 56:
                    self.addAttribute(A.Semantic.TangentSemantic, 32, A.ComponentType.F32Type)
                    self.addAttribute(A.Semantic.BinormalSemantic, 44, A.ComponentType.F32Type)
            self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(A.Semantic.IndexSemantic, 0, A.ComponentType.U32Type)
        self.setBounds(QVector3D(*mesh.bmin), QVector3D(*mesh.bmax))
        self.update()


def register_qml_types() -> None:
    from PySide6.QtQml import qmlRegisterType
    qmlRegisterType(MeshGeometry, "Nexa3D", 1, 0, "NexaMesh")


def _prop(type_, name: str, signal):
    def getter(self):
        return self._vals[name]
    return Property(type_, getter, notify=signal)


class ThreeDBridge(QObject):
    _incoming = Signal(str, object)
    _loaded = Signal(object)
    modelChanged = Signal()
    stateChanged = Signal()
    cameraChanged = Signal()
    gestureChanged = Signal()
    jobsChanged = Signal()
    miscChanged = Signal()
    toast = Signal(str, bool)

    def __init__(self, controller: Any) -> None:
        super().__init__()
        self.controller = controller
        self.svc = controller.three_d
        self._vals: dict[str, Any] = {"viewerOpen": False, "model": {}, "viewState": {}, "camera": {}, "gesture": {},
                                      "jobs": [], "activeJob": {}, "models": [], "loading": False, "loadError": "",
                                      "mode3d": {"on": False, "camera": False}, "perf": {}, "workspace": False}
        self._scale = 1.0
        self._vals["media"] = {"busy": False, "progress": 0, "path": "", "error": ""}
        self._vals["buildDossier"] = {}
        self._center = np.zeros(3)
        self._load_seq = 0
        self._fps_t = time.monotonic()
        self._incoming.connect(self._handle)
        self._loaded.connect(self._on_loaded)

    # ----- nhận từ controller (mọi luồng) -----
    def post(self, kind: str, data: dict) -> None:
        self._incoming.emit(kind, data)

    def _to_view(self, p) -> list[float]:
        return [float(x) for x in (np.asarray(p, float) - self._center) * self._scale]

    @Slot(str, object)
    def _handle(self, kind: str, data: dict) -> None:
        v = self._vals
        if kind == "3d_media":
            v["media"] = dict(data)
            self.miscChanged.emit()
        elif kind == "3d_viewer":
            self._vals["buildDossier"] = {}
            self.miscChanged.emit()
            if data.get("open"):
                self._start_load(data)
            else:
                v["viewerOpen"] = False
                v["model"] = {}
                MeshStore.clear("m:")
                self.modelChanged.emit()
        elif kind == "3d_state":
            st = dict(data)
            st["part_rot"] = {k: list(r) for k, r in (data.get("part_rot") or {}).items()}
            v["viewState"] = st
            self.stateChanged.emit()
        elif kind == "3d_camera":
            v["camera"] = {"yaw": data["yaw"], "pitch": data["pitch"], "zoom": data["zoom"],
                           "target": self._to_view(data["target"]), "radius": float(data["radius"]) * self._scale}
            self.cameraChanged.emit()
        elif kind == "3d_gesture":
            v["gesture"] = dict(data, time=time.monotonic())
            self.gestureChanged.emit()
        elif kind == "3d_job":
            jobs = [j for j in v["jobs"] if j.get("id") != data.get("id")]
            v["jobs"] = ([data] + jobs)[:12]
            pending = [j for j in v["jobs"] if not j.get("terminal")]
            v["activeJob"] = min(pending, key=lambda j: (j.get("state") == "queued", j.get("created", 0))) if pending else data
            if data.get("terminal"):
                v["models"] = self._model_list()
            self.jobsChanged.emit()
        elif kind == "3d_workspace":
            self.workspace = bool(data.get("open"))
        elif kind == "3d_mode":
            v["mode3d"] = dict(data)
            self.miscChanged.emit()
        elif kind == "3d_toast":
            self.toast.emit(str(data.get("text") or ""), bool(data.get("error")))

    def _model_list(self) -> list[dict]:
        out = []
        for m in self.svc.store.list_projects(None):
            item = dict(m)
            try:
                if m.get("thumbnail"):
                    item["thumb_url"] = QUrl.fromLocalFile(str(self.svc.store.project_dir(m["id"]) / m["thumbnail"])).toString()
            except Exception:
                pass
            out.append(item)
        return out

    # ----- nạp lưới nền -----
    def _start_load(self, data: dict) -> None:
        self._load_seq += 1
        seq = self._load_seq
        self._vals["loading"] = True
        self._vals["loadError"] = ""
        self._vals["viewerOpen"] = True
        self._vals["workspace"] = True
        self.miscChanged.emit()
        self.modelChanged.emit()
        threading.Thread(target=self._load_worker, args=(seq, data), name="nexa-3d-load", daemon=True).start()

    def _load_worker(self, seq: int, data: dict) -> None:
        from nexa.three_d.geometry import gltf
        from nexa.three_d.validator import AssetError, Limits, safe_relpath, validate_glb_bytes
        t0 = time.monotonic()
        pdir = Path(data["dir"])
        b = data["bounds"]
        center = (np.asarray(b["min"], float) + np.asarray(b["max"], float)) / 2
        radius = max(1e-6, float(data.get("radius") or 1.0))
        k = VIEW_RADIUS / radius
        mats = {m["id"]: m for m in data.get("materials", [])}
        errors: list[str] = []
        budget = int(self.controller.config.get("three_d.viewer_triangle_budget") or 1_500_000)
        use_lod = int(data.get("triangles") or 0) > budget
        limits = Limits.from_config(self.controller.config)
        parts_out = []
        for p in data["parts"]:
            if seq != self._load_seq:
                return
            rel = p.get("lod1") if (use_lod and p.get("lod1")) else p.get("asset")
            prims = []
            try:
                path = safe_relpath(pdir, rel)
                raw = path.read_bytes()
                rep = validate_glb_bytes(raw, limits, path.name)
                if not rep.ok:
                    raise AssetError("; ".join(rep.errors[:2]))
                doc = gltf.read_glb(raw)
                for ni, node in enumerate(doc.nodes):
                    for pi, prim in enumerate(node.primitives):
                        key = f"m:{data['id']}:{p['id']}:{ni}:{pi}"
                        m = prim.mesh
                        MeshStore.put(key, pack_mesh(m.vertices, m.faces, m.normals, m.uvs, center, k))
                        mj = doc.materials[prim.material] if prim.material is not None and prim.material < len(doc.materials) else {}
                        mid = (mj.get("extras") or {}).get("nexa_id") or p.get("material")
                        mview = self._material_view(mats.get(mid) or {}, pdir, mj)
                        if m.uvs is None:          # lưới không UV (vd. LOD) → không gắn texture (tránh bóng sai)
                            mview = {**mview, "baseColorMap": "", "normalMap": ""}
                        prims.append({"key": key, "material": mview})
            except (OSError, AssetError, gltf.GlbError, ValueError) as exc:
                errors.append(f"{p['name']}: {exc}")
                log.warning("Không nạp được bộ phận %s: %s", p.get("id"), exc)
            parts_out.append({
                "id": p["id"], "name": p["name"], "parent": p["parent"], "category": p["category"], "prims": prims,
                "pivot": self._np_view(p["pivot"], center, k),
                # đáy bộ phận (hệ hiển thị) — viewer nâng mô hình khi tách để bộ phận tháo xuống không chui dưới sàn
                "min_y": float((p["bounds"]["min"][1] - center[1]) * k) if p.get("bounds") else float((b["min"][1] - center[1]) * k),
                "explode": [{"order": c["order"], "v": [float(x) * k for x in c["v"]]} for c in p.get("explode", [])],
                "position": p.get("position", ""), "group": p.get("group", ""), "depth": 0, "triangles": p.get("triangles", 0),
                "motion": [self._motion_view(m, center, k) for m in p.get("motion", [])]})
        depth = {x["id"]: 0 for x in parts_out}
        byid = {x["id"]: x for x in parts_out}
        for x in parts_out:
            d, cur, guard = 0, x, 0
            while cur.get("parent") and cur["parent"] in byid and guard < 32:
                d += 1
                cur = byid[cur["parent"]]
                guard += 1
            depth[x["id"]] = d
            x["depth"] = d
        ordered = _tree_order(parts_out)
        model = dict({k2: v2 for k2, v2 in data.items() if k2 not in ("parts", "materials")},
                     parts=ordered, bottom=float((b["min"][1] - center[1]) * k), view_radius=VIEW_RADIUS,
                     load_ms=round((time.monotonic() - t0) * 1000), lod=use_lod,
                     thumbnail_url=QUrl.fromLocalFile(str(pdir / data["thumbnail"])).toString() if data.get("thumbnail") else "")
        self._loaded.emit({"seq": seq, "model": model, "errors": errors, "center": center, "k": k})

    @classmethod
    def _motion_view(cls, m: dict, center, k) -> dict:
        out = dict(m)
        if "c" in m:
            out["c"] = cls._np_view(m["c"], center, k)
        if m.get("t") == "slide":
            out["amp"] = float(m["amp"]) * k
            out["off"] = float(m.get("off", 0.0)) * k
        return out

    @staticmethod
    def _np_view(p, center, k) -> list[float]:
        return [float(x) for x in (np.asarray(p, float) - center) * k]

    @staticmethod
    def _material_view(m: dict, pdir: Path, mj: dict) -> dict:
        from nexa.three_d.validator import AssetError, safe_relpath
        base = m.get("base_color") or ((mj.get("pbrMetallicRoughness") or {}).get("baseColorFactor")) or [0.8, 0.8, 0.8, 1.0]

        def lin_to_srgb(c: float) -> float:
            c = max(0.0, min(1.0, float(c)))
            return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

        out = {"color": "#%02x%02x%02x" % tuple(int(round(lin_to_srgb(c) * 255)) for c in base[:3]),
               "opacity": float(base[3]) if len(base) > 3 else 1.0, "metalness": float(m.get("metallic", 0.0)),
               "roughness": float(m.get("roughness", 0.5)), "clearcoat": float(m.get("clearcoat", 0.0)),
               "emissive": [float(x) for x in (m.get("emissive") or [0, 0, 0])], "kind": m.get("kind", "plastic"),
               "baseColorMap": "", "normalMap": "", "normalScale": float(m.get("normal_scale", 1.0))}
        for key, qkey in (("base_color", "baseColorMap"), ("normal", "normalMap")):
            rel = (m.get("textures") or {}).get(key)
            if rel:
                try:
                    out[qkey] = QUrl.fromLocalFile(str(safe_relpath(pdir, rel))).toString()
                except AssetError:
                    pass
        return out

    @Slot(object)
    def _on_loaded(self, res: dict) -> None:
        if res["seq"] != self._load_seq:
            return
        self._center, self._scale = res["center"], res["k"]
        v = self._vals
        v["model"] = res["model"]
        v["loading"] = False
        v["loadError"] = "; ".join(res["errors"][:3])
        if res["errors"]:
            self.toast.emit("Một số bộ phận không nạp được: " + v["loadError"], True)
        self.modelChanged.emit()
        self.miscChanged.emit()
        self.svc.viewer._push_camera()            # camera theo đơn vị xem mới
        self.svc.viewer._push_state()

    # ----- thuộc tính QML -----
    viewerOpen = _prop(bool, "viewerOpen", modelChanged)
    model = _prop("QVariantMap", "model", modelChanged)
    viewState = _prop("QVariantMap", "viewState", stateChanged)
    camera = _prop("QVariantMap", "camera", cameraChanged)
    gesture = _prop("QVariantMap", "gesture", gestureChanged)
    jobs = _prop("QVariantList", "jobs", jobsChanged)
    activeJob = _prop("QVariantMap", "activeJob", jobsChanged)
    models = _prop("QVariantList", "models", jobsChanged)
    loading = _prop(bool, "loading", miscChanged)
    loadError = _prop(str, "loadError", miscChanged)
    mode3d = _prop("QVariantMap", "mode3d", miscChanged)
    perf = _prop("QVariantMap", "perf", miscChanged)
    media = _prop("QVariantMap", "media", miscChanged)
    buildDossier = _prop("QVariantMap", "buildDossier", miscChanged)

    def _get_ws(self) -> bool:
        return self._vals["workspace"]

    def _set_ws(self, on: bool) -> None:
        if self._vals["workspace"] != bool(on):
            self._vals["workspace"] = bool(on)
            if on:
                self._vals["models"] = self._model_list()
                self.jobsChanged.emit()
            self.miscChanged.emit()

    workspace = Property(bool, _get_ws, _set_ws, notify=miscChanged)

    @Property(str, constant=True)
    def studioHdr(self) -> str:
        from nexa.utils.config import ASSETS_DIR
        f = ASSETS_DIR / "3d" / "studio.hdr"
        return QUrl.fromLocalFile(str(f)).toString() if f.exists() else ""

    @Property("QVariantMap", notify=miscChanged)
    def providerStatus(self) -> dict:
        return self.svc.provider_status()

    # ----- hành động -----
    def _bg(self, fn, *args) -> None:
        def run():
            try:
                res = fn(*args)
                msg = res[1] if isinstance(res, tuple) and len(res) >= 2 else ""
                ok = res[0] if isinstance(res, tuple) else True
                if msg and not ok:
                    self.toast.emit(msg, True)
            except Exception as exc:
                log.exception("Thao tác 3D lỗi")
                self.toast.emit(f"Lỗi: {exc}", True)
        threading.Thread(target=run, daemon=True).start()

    @Slot(str, str, str)
    def generate(self, prompt: str, mode: str, quality: str) -> None:
        text = prompt.strip()
        if not text:
            return
        try:
            self.svc.submit(text, mode=mode, quality=quality, source="keyboard")
        except (ValueError, RuntimeError) as exc:
            self.toast.emit(str(exc), True)

    @Slot(str, str, "QVariantMap")
    @Slot(str, str, "QVariantMap", str)
    def generateFromReferences(self, prompt: str, quality: str, references: dict, method: str = "auto") -> None:
        if method not in ("auto", "cad"):
            self.toast.emit("Cách dựng từ ảnh không hợp lệ.", True)
            return
        if not self.svc.enabled or self.svc.locked:
            self.toast.emit("NEXA đang khóa hoặc tính năng 3D chưa bật.", True)
            return
        paths = {}
        for view, value in references.items():
            url = QUrl(str(value))
            if not url.isLocalFile():
                self.toast.emit("Hãy chọn ảnh từ máy tính.", True)
                return
            paths[str(view)] = url.toLocalFile()
        if not paths:
            self.toast.emit("Hãy chọn ít nhất một ảnh tham chiếu.", True)
            return
        try:
            self.svc.submit(prompt.strip() or "Tạo mô hình giống vật thể trong ảnh tham chiếu",
                            mode="reference_cad" if method == "cad" else "auto", quality=quality, reference_images=paths)
        except (ValueError, RuntimeError) as exc:
            self.toast.emit(str(exc), True)

    @Slot(str)
    def cancelJob(self, job_id: str) -> None:
        if job_id:
            self.svc.jobs.cancel(job_id, "Người dùng hủy")
        else:
            self.svc.cancel_jobs("Người dùng hủy")

    @Slot(str)
    def openModel(self, project_id: str) -> None:
        self._bg(self.svc.viewer.open, project_id)

    @Slot()
    def closeViewer(self) -> None:
        self.svc.viewer.close()
        self.workspace = False

    @Slot(str, "QVariantList")
    def partAction(self, action: str, ids: list) -> None:
        self.svc.viewer.apply_ids(action, [str(i) for i in ids])

    @Slot(str)
    def selectPart(self, pid: str) -> None:
        self.svc.viewer.select(pid)

    @Slot()
    def showAll(self) -> None:
        self.svc.viewer.show_all()

    @Slot()
    def explode(self) -> None:
        ok, msg = self.svc.viewer.explode()
        if not ok:
            self.toast.emit(msg, True)

    @Slot()
    def collapse(self) -> None:
        self.svc.viewer.collapse()

    @Slot()
    def toggleMotion(self) -> None:
        ok, msg = self.svc.toggle_animation()
        self.toast.emit(msg, not ok)

    @Slot()
    def resetView(self) -> None:
        self.svc.viewer.reset_view()

    @Slot(str)
    def setRenderMode(self, mode: str) -> None:
        if mode == "wireframe":
            self._ensure_wireframe()
        self.svc.viewer.set_render_mode(mode)

    def _ensure_wireframe(self) -> None:
        model = self._vals.get("model") or {}
        todo = [pr for p in model.get("parts", []) for pr in p.get("prims", []) if MeshStore.get("w" + pr["key"]) is None]
        if not todo:
            return

        def run():
            for pr in todo:
                m = MeshStore.get(pr["key"])
                if m is None:
                    continue
                arr = np.frombuffer(m.vertices, dtype=np.float32).reshape(-1, m.stride // 4)
                faces = np.frombuffer(m.indices, dtype=np.uint32).reshape(-1, 3).astype(np.int64)
                MeshStore.put("w" + pr["key"], pack_edges(arr[:, :3].astype(np.float64), faces, np.zeros(3), 1.0))
            self._incoming.emit("3d_state", self.svc.viewer.state())
        threading.Thread(target=run, daemon=True).start()

    @Slot(float, float)
    def orbit(self, dyaw: float, dpitch: float) -> None:
        self.svc.viewer.rotate_view(dyaw, dpitch, source="gesture")

    @Slot(float)
    def zoomBy(self, factor: float) -> None:
        self.svc.viewer.zoom_view(factor)

    @Slot(float)
    def reportFps(self, fps: float) -> None:
        self.svc.viewer.fps = float(fps)
        now = time.monotonic()
        if now - self._fps_t > 1.0:
            self._fps_t = now
            self._vals["perf"] = dict(self.svc.viewer.perf(), load_ms=(self._vals.get("model") or {}).get("load_ms", 0))
            self.miscChanged.emit()

    @Slot()
    def toggleCamera(self) -> None:
        target = not self.controller.gestures.running

        def run():
            r = self.controller.set_gesture_mode(target)
            self.toast.emit(r.message, not r.ok)
            self._vals["mode3d"] = {"on": self.svc.viewer_active, "camera": self.controller.gestures.running}
            self.miscChanged.emit()
        threading.Thread(target=run, daemon=True).start()

    @Slot()
    def refreshModels(self) -> None:
        self._vals["models"] = self._model_list()
        self.jobsChanged.emit()

    @Slot(str)
    def exportModel(self, fmt: str) -> None:
        self._bg(self._export, fmt)

    @Slot()
    def refreshBuildDossier(self):
        from nexa.three_d.build_dossier import build_dossier, load_records
        self._vals["buildDossier"] = {}
        project = self.svc.viewer.project
        if project is not None:
            try:
                records, _ = load_records(project)
                self._vals["buildDossier"] = build_dossier(project, records)
            except Exception as exc:
                self._vals["buildDossier"] = {"error": str(exc)}
        self.miscChanged.emit()

    @Slot(str, str, "QVariantMap", result=bool)
    def saveBuildRecord(self, project_id, part_id, record):
        from nexa.three_d.build_dossier import save_record
        project = self.svc.viewer.project
        if project is None or project.id != project_id:
            self.toast.emit("Mô hình đã thay đổi; mở lại hồ sơ trước khi lưu.", True)
            return False
        try:
            save_record(project, part_id, record)
            self.refreshBuildDossier()
            self.toast.emit("Đã lưu ghi chú linh kiện. Nguồn và độ tương thích chưa được xác minh.", False)
            return True
        except Exception as exc:
            self.toast.emit(str(exc), True)
            return False

    @Slot(str)
    def exportBuildDossier(self, project_id):
        from nexa.three_d.build_dossier import build_dossier, load_records, export_dossier
        from nexa.utils.config import known_folder
        project = self.svc.viewer.project
        if project is None or project.id != project_id:
            self.toast.emit("Mô hình đã thay đổi; mở lại hồ sơ trước khi xuất.", True)
            return
        def run():
            records, _ = load_records(project)
            path = export_dossier(build_dossier(project, records), known_folder("Documents") / "NEXA 3D" / "Build")
            self.toast.emit(f"Đã xuất hồ sơ HTML và JSON: {path.parent}", False)
            return True, ""
        self._bg(run)

    @Slot()
    def openBuildDossierFolder(self):
        from PySide6.QtGui import QDesktopServices
        from nexa.utils.config import known_folder
        path = known_folder("Documents") / "NEXA 3D" / "Build"
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot(str, int, str, int, float, float)
    def exportProductMedia(self, kind, size, background, seconds, yaw, pitch):
        from nexa.three_d.product_media import MediaOptions, export_media, MediaCancelled
        from nexa.utils.config import known_folder
        if self._vals["media"]["busy"]:
            return
        project = self.svc.viewer.project
        if project is None or self.svc.locked:
            self.toast.emit("Hãy mở mô hình và bật điều khiển trước khi xuất.", True)
            return
        options = MediaOptions(kind, size, background, seconds, yaw, pitch)
        try:
            options.validate()
        except ValueError as exc:
            self.toast.emit(str(exc), True)
            return
        self.svc.media_cancel.clear()
        state = {"busy": True, "progress": 0, "path": "", "error": ""}
        self._vals["media"] = dict(state)
        self.miscChanged.emit()
        pid = project.id

        def run():
            def progress(value):
                state["progress"] = value
                self.post("3d_media", dict(state))
            try:
                path = export_media(self.svc.store, pid, known_folder("Documents") / "NEXA 3D" / "Media",
                                    options, self.svc.media_cancel, progress)
                state["path"] = str(path)
                self.toast.emit(f"Đã xuất {path.name} vào Tài liệu/NEXA 3D/Media.", False)
            except MediaCancelled as exc:
                state["error"] = str(exc)
            except Exception as exc:
                log.exception("Xuất ảnh/video sản phẩm thất bại")
                state["error"] = str(exc)
            finally:
                state["busy"] = False
                self.post("3d_media", dict(state))
        threading.Thread(target=run, name="nexa-product-media", daemon=True).start()

    @Slot()
    def cancelProductMedia(self):
        self.svc.media_cancel.set()

    @Slot()
    def openProductMediaFolder(self):
        from PySide6.QtGui import QDesktopServices
        path = self._vals["media"].get("path")
        if path and Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _export(self, fmt: str) -> tuple[bool, str]:
        from nexa.three_d.asset_store import export_project
        from nexa.utils.config import known_folder
        pid = self.svc.viewer.project.id if self.svc.viewer.project else None
        if not pid:
            return False, "Chưa mở mô hình."
        path = export_project(self.svc.store, pid, fmt, known_folder("Documents") / "NEXA 3D")
        self.toast.emit(f"Đã xuất {path.name} vào Tài liệu/NEXA 3D.", False)
        return True, ""


def _tree_order(parts: list[dict]) -> list[dict]:
    """Sắp bộ phận theo cây (cha trước, con sau) cho bảng cây bộ phận."""
    children: dict[str, list[dict]] = {}
    roots = []
    ids = {p["id"] for p in parts}
    for p in parts:
        if p.get("parent") and p["parent"] in ids:
            children.setdefault(p["parent"], []).append(p)
        else:
            roots.append(p)
    out: list[dict] = []

    def walk(p: dict, guard: int = 0) -> None:
        out.append(p)
        if guard < 32:
            for c in children.get(p["id"], []):
                walk(c, guard + 1)
    for r in roots:
        walk(r)
    seen = {p["id"] for p in out}
    out += [p for p in parts if p["id"] not in seen]
    return out
