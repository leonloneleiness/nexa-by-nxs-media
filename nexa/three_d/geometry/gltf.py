"""Đọc/ghi GLB (glTF 2.0 nhị phân) tối giản, không phụ thuộc thư viện ngoài.

Ghi: mỗi bộ phận là một node (tên = id bộ phận, `extras` = metadata), mỗi vật liệu là một primitive. Vật liệu PBR
metallic-roughness, texture nhúng trong buffer (không có URI ngoài). Đỉnh đổi mm → m theo chuẩn glTF.
Đọc: hỗ trợ accessor float/uint8/uint16/uint32, byteStride, cây node với matrix hoặc TRS, texture nhúng.
Không hỗ trợ sparse accessor, Draco/meshopt (validator báo lỗi rõ ràng thay vì đọc sai).
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from nexa.three_d.geometry.kernel import MeshData
from nexa.three_d.models import Material

MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
MM_PER_M = 1000.0

COMPONENT_DTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
TYPE_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class GlbError(ValueError):
    pass


@dataclass
class GlbPrimitive:
    mesh: MeshData
    material: int | None


@dataclass
class GlbNode:
    name: str
    primitives: list[GlbPrimitive] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class GlbDocument:
    nodes: list[GlbNode]
    materials: list[dict]
    images: list[tuple[bytes, str]]           # (dữ liệu, mime)
    textures: list[dict]
    extras: dict[str, Any]
    json: dict


# ------------------------------------------------------------------ ghi
class _BinBuilder:
    def __init__(self) -> None:
        self.data = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def _align(self) -> None:
        while len(self.data) % 4:
            self.data.append(0)

    def view(self, raw: bytes, target: int | None = None) -> int:
        self._align()
        v = {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(raw)}
        if target:
            v["target"] = target
        self.data.extend(raw)
        self.views.append(v)
        return len(self.views) - 1

    def accessor(self, arr: np.ndarray, kind: str, component: int, target: int | None, minmax: bool = False) -> int:
        raw = np.ascontiguousarray(arr).tobytes()
        view = self.view(raw, target)
        acc = {"bufferView": view, "componentType": component, "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = [float(x) for x in arr.min(axis=0)]
            acc["max"] = [float(x) for x in arr.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def _material_json(m: Material, texture_index: dict[str, int]) -> dict:
    pbr: dict[str, Any] = {"baseColorFactor": [float(x) for x in m.base_color], "metallicFactor": float(m.metallic),
                           "roughnessFactor": float(m.roughness)}
    out: dict[str, Any] = {"name": m.name or m.id, "pbrMetallicRoughness": pbr,
                           "extras": {"nexa_id": m.id, "kind": m.kind, "clearcoat": m.clearcoat}}
    if m.textures.get("base_color") in texture_index:
        pbr["baseColorTexture"] = {"index": texture_index[m.textures["base_color"]]}
    if m.textures.get("metallic_roughness") in texture_index:
        pbr["metallicRoughnessTexture"] = {"index": texture_index[m.textures["metallic_roughness"]]}
    if m.textures.get("normal") in texture_index:
        out["normalTexture"] = {"index": texture_index[m.textures["normal"]], "scale": float(m.normal_scale)}
    if any(x > 0 for x in m.emissive):
        out["emissiveFactor"] = [float(x) for x in m.emissive]
    if m.transparent:
        out["alphaMode"] = "BLEND"
        out["doubleSided"] = True
    return out


def write_glb(path: Path, nodes: list[tuple[str, list[tuple[MeshData, str]], dict]], materials: list[Material],
              texture_root: Path | None = None, extras: dict | None = None) -> int:
    """nodes: [(tên, [(lưới mm, id vật liệu)], extras)]. Trả số byte đã ghi."""
    b = _BinBuilder()
    mat_index = {m.id: i for i, m in enumerate(materials)}
    images: list[dict] = []
    textures: list[dict] = []
    texture_index: dict[str, int] = {}
    used_mats = {mid for _, prims, _ in nodes for _, mid in prims}
    for m in materials:
        if m.id not in used_mats:
            continue
        for rel in m.textures.values():
            if rel in texture_index or texture_root is None:
                continue
            f = (texture_root / rel)
            if not f.is_file():
                continue
            view = b.view(f.read_bytes())
            images.append({"bufferView": view, "mimeType": "image/png" if rel.lower().endswith(".png") else "image/jpeg"})
            textures.append({"source": len(images) - 1, "sampler": 0})
            texture_index[rel] = len(textures) - 1
    gl_meshes: list[dict] = []
    gl_nodes: list[dict] = []
    for name, prims, node_extras in nodes:
        gl_prims = []
        for mesh, mid in prims:
            if mesh.triangle_count == 0:
                continue
            pos = (mesh.vertices / MM_PER_M).astype(np.float32)
            attrs = {"POSITION": b.accessor(pos, "VEC3", 5126, 34962, minmax=True)}
            if mesh.normals is not None:
                attrs["NORMAL"] = b.accessor(mesh.normals.astype(np.float32), "VEC3", 5126, 34962)
            if mesh.uvs is not None:
                attrs["TEXCOORD_0"] = b.accessor(mesh.uvs.astype(np.float32), "VEC2", 5126, 34962)
            idx = mesh.faces.astype(np.uint32).reshape(-1)
            prim = {"attributes": attrs, "indices": b.accessor(idx, "SCALAR", 5125, 34963), "mode": 4}
            if mid in mat_index:
                prim["material"] = mat_index[mid]
            gl_prims.append(prim)
        node: dict[str, Any] = {"name": name, "extras": node_extras or {}}
        if gl_prims:
            gl_meshes.append({"name": name, "primitives": gl_prims})
            node["mesh"] = len(gl_meshes) - 1
        gl_nodes.append(node)
    doc: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "NEXA 3D (nexa.three_d)"},
        "scene": 0, "scenes": [{"nodes": list(range(len(gl_nodes))), "extras": extras or {}}],
        "nodes": gl_nodes, "meshes": gl_meshes,
        "materials": [_material_json(m, texture_index) for m in materials],
        "buffers": [{"byteLength": 0}], "bufferViews": b.views, "accessors": b.accessors,
    }
    if images:
        doc["images"] = images
        doc["textures"] = textures
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
    while len(b.data) % 4:
        b.data.append(0)
    doc["buffers"][0]["byteLength"] = len(b.data)
    js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(b.data)
    out = bytearray()
    out += struct.pack("<4sII", MAGIC, 2, total)
    out += struct.pack("<II", len(js), CHUNK_JSON) + js
    out += struct.pack("<II", len(b.data), CHUNK_BIN) + bytes(b.data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(out)
    tmp.replace(path)
    return total


# ------------------------------------------------------------------ đọc
def parse_container(data: bytes) -> tuple[dict, bytes]:
    """Tách JSON + BIN của GLB, kiểm tra magic/phiên bản/độ dài. Ném GlbError nếu sai định dạng."""
    if len(data) < 20:
        raise GlbError("tệp quá ngắn, không phải GLB")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != MAGIC:
        raise GlbError("sai magic header (không phải GLB)")
    if version != 2:
        raise GlbError(f"glTF phiên bản {version} không được hỗ trợ (cần 2)")
    if length != len(data):
        raise GlbError(f"độ dài khai báo {length} ≠ kích thước tệp {len(data)}")
    off = 12
    js: dict | None = None
    bin_chunk = b""
    first = True
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        if off + clen > len(data):
            raise GlbError("chunk vượt quá cuối tệp")
        chunk = data[off:off + clen]
        off += clen
        if first:
            if ctype != CHUNK_JSON:
                raise GlbError("chunk đầu tiên phải là JSON")
            try:
                js = json.loads(chunk.decode("utf-8").rstrip(" \x00"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GlbError(f"JSON trong GLB hỏng: {exc}") from exc
            first = False
        elif ctype == CHUNK_BIN and not bin_chunk:
            bin_chunk = chunk
    if js is None or not isinstance(js, dict):
        raise GlbError("thiếu chunk JSON")
    return js, bin_chunk


def read_accessor(js: dict, bin_chunk: bytes, index: int) -> np.ndarray:
    accs = js.get("accessors") or []
    if not (0 <= index < len(accs)):
        raise GlbError(f"accessor {index} không tồn tại")
    acc = accs[index]
    if "sparse" in acc:
        raise GlbError("sparse accessor chưa được hỗ trợ")
    comp = COMPONENT_DTYPES.get(acc.get("componentType"))
    ncomp = TYPE_SIZES.get(acc.get("type"))
    if comp is None or ncomp is None:
        raise GlbError("accessor có kiểu không hợp lệ")
    count = int(acc.get("count", 0))
    if count < 0:
        raise GlbError("accessor count âm")
    if "bufferView" not in acc:
        return np.zeros((count, ncomp), dtype=comp)
    views = js.get("bufferViews") or []
    vi = acc["bufferView"]
    if not (0 <= vi < len(views)):
        raise GlbError("bufferView không tồn tại")
    view = views[vi]
    if int(view.get("buffer", 0)) != 0:
        raise GlbError("chỉ hỗ trợ buffer nhúng số 0")
    item = np.dtype(comp).itemsize * ncomp
    stride = int(view.get("byteStride") or item)
    start = int(view.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
    vlen = int(view.get("byteLength", 0))
    need = (count - 1) * stride + item if count else 0
    if start < 0 or int(view.get("byteOffset", 0)) + vlen > len(bin_chunk) or \
            int(acc.get("byteOffset", 0)) + need > vlen:
        raise GlbError("accessor đọc vượt ra ngoài buffer")
    if count == 0:
        return np.zeros((0, ncomp), dtype=comp)
    if stride == item:
        arr = np.frombuffer(bin_chunk, dtype=comp, count=count * ncomp, offset=start).reshape(count, ncomp)
    else:
        raw = np.frombuffer(bin_chunk, dtype=np.uint8, count=need, offset=start)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(count, item), strides=(stride, 1))
        arr = np.frombuffer(np.ascontiguousarray(rows).tobytes(), dtype=comp).reshape(count, ncomp)
    if acc.get("normalized") and comp in (np.uint8, np.uint16, np.int8, np.int16):
        arr = arr.astype(np.float32) / float(np.iinfo(comp).max)
    return arr


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.asarray(node.get("translation", [0, 0, 0]), float)
    x, y, z, w = [float(v) for v in node.get("rotation", [0, 0, 0, 1])]
    s = np.asarray(node.get("scale", [1, 1, 1]), float)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def read_glb(data: bytes, to_mm: bool = True, max_depth: int = 64) -> GlbDocument:
    """Đọc toàn bộ GLB thành các node đã áp biến đổi thế giới (đơn vị mm nếu to_mm)."""
    js, bin_chunk = parse_container(data)
    if js.get("extensionsRequired"):
        raise GlbError(f"GLB yêu cầu extension chưa hỗ trợ: {js['extensionsRequired']}")
    nodes_js = js.get("nodes") or []
    meshes_js = js.get("meshes") or []
    scale = MM_PER_M if to_mm else 1.0
    out_nodes: list[GlbNode] = []
    scenes = js.get("scenes") or [{"nodes": list(range(len(nodes_js)))}]
    roots = scenes[int(js.get("scene", 0)) if scenes else 0].get("nodes", [])
    seen: set[int] = set()

    def visit(ni: int, parent: np.ndarray, depth: int) -> None:
        if depth > max_depth or ni in seen or not (0 <= ni < len(nodes_js)):
            raise GlbError("cây node có vòng lặp hoặc quá sâu")
        seen.add(ni)
        node = nodes_js[ni]
        world = parent @ _node_matrix(node)
        if "mesh" in node:
            mi = node["mesh"]
            if not (0 <= mi < len(meshes_js)):
                raise GlbError("node trỏ tới mesh không tồn tại")
            prims = []
            for prim in meshes_js[mi].get("primitives", []):
                if prim.get("mode", 4) != 4:
                    continue                                    # chỉ đọc tam giác
                attrs = prim.get("attributes", {})
                if "POSITION" not in attrs:
                    continue
                if "extensions" in prim and "KHR_draco_mesh_compression" in prim["extensions"]:
                    raise GlbError("lưới nén Draco chưa được hỗ trợ")
                pos = read_accessor(js, bin_chunk, attrs["POSITION"]).astype(np.float64)
                nrm = read_accessor(js, bin_chunk, attrs["NORMAL"]).astype(np.float64) if "NORMAL" in attrs else None
                uv = read_accessor(js, bin_chunk, attrs["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in attrs else None
                if "indices" in prim:
                    idx = read_accessor(js, bin_chunk, prim["indices"]).reshape(-1).astype(np.int64)
                else:
                    idx = np.arange(len(pos), dtype=np.int64)
                if len(idx) % 3:
                    raise GlbError("số chỉ số tam giác không chia hết cho 3")
                if len(idx) and (idx.max() >= len(pos) or idx.min() < 0):
                    raise GlbError("chỉ số tam giác vượt số đỉnh")
                mesh = MeshData(pos, idx.reshape(-1, 3), nrm, uv).transformed(world)
                mesh.vertices = mesh.vertices * scale
                prims.append(GlbPrimitive(mesh, prim.get("material")))
            out_nodes.append(GlbNode(str(node.get("name") or f"node_{ni}"), prims, dict(node.get("extras") or {})))
        for child in node.get("children", []):
            visit(child, world, depth + 1)

    for r in roots:
        visit(r, np.eye(4), 0)
    images: list[tuple[bytes, str]] = []
    for img in js.get("images") or []:
        if "bufferView" in img:
            view = (js.get("bufferViews") or [])[img["bufferView"]]
            s = int(view.get("byteOffset", 0))
            images.append((bytes(bin_chunk[s:s + int(view["byteLength"])]), str(img.get("mimeType", "image/png"))))
        else:
            images.append((b"", "external"))
    scene_extras = (scenes[0].get("extras") if scenes else None) or {}
    return GlbDocument(out_nodes, list(js.get("materials") or []), images, list(js.get("textures") or []),
                       dict(scene_extras), js)


def material_from_gltf(index: int, mat: dict, textures_saved: dict[int, str]) -> Material:
    """Vật liệu glTF → Material của NEXA (texture đã được lưu ra tệp theo chỉ số texture)."""
    pbr = mat.get("pbrMetallicRoughness") or {}
    base = [float(x) for x in pbr.get("baseColorFactor", [1, 1, 1, 1])]
    extras = mat.get("extras") or {}
    textures = {}
    for key, gl in (("base_color", pbr.get("baseColorTexture")), ("metallic_roughness", pbr.get("metallicRoughnessTexture")),
                    ("normal", mat.get("normalTexture"))):
        if gl and gl.get("index") in textures_saved:
            textures[key] = textures_saved[gl["index"]]
    metallic = float(pbr.get("metallicFactor", 1.0))
    return Material(id=str(extras.get("nexa_id") or f"mat_{index}"), name=str(mat.get("name") or f"Vật liệu {index + 1}"),
                    kind=str(extras.get("kind") or ("metal" if metallic > 0.5 else "plastic")), base_color=base,
                    metallic=metallic, roughness=float(pbr.get("roughnessFactor", 1.0)),
                    emissive=[float(x) for x in mat.get("emissiveFactor", [0, 0, 0])],
                    clearcoat=float(extras.get("clearcoat", 0.0)),
                    normal_scale=float((mat.get("normalTexture") or {}).get("scale", 1.0)), textures=textures)
