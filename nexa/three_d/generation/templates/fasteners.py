"""Ốc vít theo ISO: bu-lông (đầu lục giác ISO 4017/4014, đầu trụ lục giác chìm ISO 4762, đầu côn ISO 10642),
đai ốc ISO 4032 (ren trong helix thật), vòng đệm ISO 7089.

Ren "technical": hình học helix thật theo biên dạng cơ bản ISO 68-1 (kernel.threaded_rod_mesh).
Ren "illustrative": trụ trơn + normal map ren (KHÔNG được đánh dấu là mô hình kỹ thuật).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import MeshData, Shape
from nexa.three_d.models import Material
from nexa.three_d.spec import ModelSpec, iso_or_scaled

MATERIAL_IDS = {"zinc": "steel_zinc", "steel": "steel", "stainless": "stainless", "black_oxide": "steel_black_oxide",
                "brass": "brass", "titanium": "titanium"}
MATERIAL_VI = {"zinc": "thép mạ kẽm", "steel": "thép", "stainless": "inox", "black_oxide": "thép nhuộm đen",
               "brass": "đồng thau", "titanium": "titan"}


def _hex_prism(s: float, h: float) -> K.Solid:
    e = s / math.cos(math.radians(30))
    return K.extrude(P.circle(e / 2, 6, start=math.radians(30)), h)


def _chamfer_cone(s: float, h: float, top: bool = True, bottom: bool = False, angle: float = 30.0) -> K.Solid:
    """Khối xoay dùng để vát góc lục giác 30° ở mặt trên/dưới (giao với lăng trụ)."""
    e = s / math.cos(math.radians(30))
    R = e / 2 + 0.5
    rt = 0.475 * s
    dz = (R - rt) * math.tan(math.radians(angle))
    prof = [(0.0, 0.0)]
    if bottom:
        prof += [(rt, 0.0), (R, dz)]
    else:
        prof += [(R, 0.0)]
    if top:
        prof += [(R, h - dz), (rt, h)]
    else:
        prof += [(R, h)]
    prof += [(0.0, h)]
    return K.revolve(prof, segments=96)


def hex_head(s: float, k: float) -> K.Solid:
    return _hex_prism(s, k) & _chamfer_cone(s, k, top=True, bottom=False)


def socket_cap_head(dk: float, k: float, s: float, knurl: bool = True) -> K.Solid:
    r = dk / 2
    fil = max(0.2, 0.08 * dk)
    prof = P.fillet_polygon([(0, 0), (r - 0.1 * k * 0.3, 0), (r, 0.08 * k), (r, k), (0, k)], [0, 0, 0, fil, 0], 8)
    head = K.revolve(prof, segments=128)
    if knurl:
        n = int(np.clip(round(dk * 3), 24, 72))
        gw = math.pi * dk / n * 0.4                    # rãnh khía nhám thẳng
        gd = max(0.08, 0.03 * dk)
        groove = K.box(gd * 2, gw, k * 0.66).translate(r, 0, 0.5 * k)
        head = head.subtract_all([groove.rotate(0, 0, 360 * i / n) for i in range(n)])
    depth = 0.6 * k
    socket = _hex_prism(s, depth + 0.01).translate(0, 0, k - depth) + K.cone(s / 2, s * 0.3).rotate(180, 0, 0).translate(0, 0, k - depth)
    return head - socket


def countersunk_head(d: float, dk: float, s: float) -> tuple[K.Solid, float]:
    k = (dk - d) / 2 / math.tan(math.radians(45))
    prof = [(0, 0), (d / 2, 0), (dk / 2, k - 0.05 * k), (dk / 2, k), (0, k)]
    head = K.revolve(prof, segments=128)
    depth = 0.55 * k
    socket = _hex_prism(s, depth + 0.01).translate(0, 0, k - depth)
    return head - socket, k


def _fillet_ring(r_shank: float, z: float, rad: float) -> K.Solid:
    """Bo cung chuyển tiếp giữa thân và mặt dưới đầu bu-lông."""
    pts = [(r_shank - 0.2, z - rad), (r_shank, z - rad)]
    cx, cz = r_shank + rad, z - rad
    for a in np.linspace(math.pi, math.pi / 2, 9)[1:]:
        pts.append((cx + rad * math.cos(a), cz + rad * math.sin(a)))
    pts += [(r_shank + rad, z + 0.1), (r_shank - 0.2, z + 0.1)]
    return K.revolve(pts, segments=96)


def _uv_cylinder(radius: float, z0: float, z1: float, pitch: float, segments: int = 96) -> MeshData:
    """Trụ có UV u = θ/2π, v = z/P (ren minh họa bằng normal map). Đường nối UV có đỉnh nhân đôi."""
    rows = 2
    th = np.linspace(0, 2 * math.pi, segments + 1)
    zs = np.array([z0, z1])
    Z, TH = np.meshgrid(zs, th, indexing="ij")
    verts = np.column_stack([(radius * np.cos(TH)).ravel(), (radius * np.sin(TH)).ravel(), Z.ravel()])
    normals = np.column_stack([np.cos(TH).ravel(), np.sin(TH).ravel(), np.zeros(TH.size)])
    uvs = np.column_stack([(TH / (2 * math.pi)).ravel(), (Z / pitch).ravel()])
    n = segments + 1
    j = np.arange(segments)
    a, b, c, d = j, j + 1, n + j + 1, n + j
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    del rows
    return MeshData(verts, faces.astype(np.int64), normals, uvs)


def bolt_shapes(p: dict, mat_id: str) -> tuple[list[Shape], dict[str, float], bool]:
    d = float(p["diameter_mm"])
    L = float(p["length_mm"])
    pitch = float(p["pitch_mm"])
    iso = iso_or_scaled(d)
    head_type = p.get("head", "hex")
    technical = p.get("thread", "technical") == "technical"
    shapes: list[Shape] = []
    dims = {"diameter": d, "length": L, "pitch": pitch}
    if head_type == "countersunk":
        dk = 2.0 * d
        head, k = countersunk_head(d, dk, iso["sk"])
        shank_len = L - k
        head = head.translate(0, 0, shank_len)
        dims.update({"head_diameter": dk, "head_height": round(k, 3)})
    elif head_type == "socket_cap":
        head = socket_cap_head(iso["dk"], iso["kc"], iso["sk"]).translate(0, 0, L)
        shank_len = L
        dims.update({"head_diameter": iso["dk"], "head_height": iso["kc"], "socket_size": iso["sk"]})
    else:
        c = min(0.6, max(0.15, 0.04 * iso["s"]))
        head = hex_head(iso["s"], iso["k"]).translate(0, 0, L + c)
        head = head + K.cylinder(0.45 * iso["s"], c + 0.05, segments=96).translate(0, 0, L)
        shank_len = L
        dims.update({"across_flats": iso["s"], "head_height": iso["k"]})
    tl = min(float(p.get("thread_length_mm") or shank_len), shank_len)
    dims["thread_length"] = round(tl, 3)
    fillet = _fillet_ring(d / 2, shank_len, max(0.1, 0.05 * d)) if head_type != "countersunk" else None
    if technical:
        spp = int(np.clip(round(18 + 6 * (8 / max(d, 2)) ** 0.5), 18, 32))
        ang = int(np.clip(round(64 + d * 4), 72, 160)) // 8 * 8
        rod = K.threaded_rod(d, pitch, shank_len, thread_length=tl, samples_per_pitch=spp, angular_segments=ang,
                             runout_pitches=1.5, top_overlap=0.3)
        body = K.Solid.union_all([rod, head] + ([fillet] if fillet is not None else []))
        shapes.append(Shape(body, mat_id, sharp_angle=38.0))
    else:
        depth = K.ISO_THREAD_DEPTH * pitch
        r_thread = d / 2 - 0.35 * depth
        core = K.cylinder(r_thread, tl, segments=96)
        chamfer = K.cone(r_thread, depth, r_thread + depth, segments=96)
        core = (core & (chamfer + K.cylinder(r_thread + depth, tl, segments=96).translate(0, 0, depth)))
        shank = K.cylinder(d / 2, shank_len - tl + 0.3, segments=96).translate(0, 0, tl) if shank_len > tl else None
        solid = K.Solid.union_all([core, head] + ([shank] if shank else []) + ([fillet] if fillet is not None else []))
        head_mesh = K.Solid.union_all([head] + ([shank] if shank else []) + ([fillet] if fillet is not None else []))
        shapes.append(Shape(head_mesh, mat_id, sharp_angle=38.0))
        vis = _uv_cylinder(r_thread, depth, tl, pitch)
        tip = K.cone(r_thread - depth, depth, r_thread, segments=96)
        shapes.append(Shape(tip, mat_id + "_thread", sharp_angle=38.0))
        shapes.append(Shape(solid & K.cylinder(r_thread + 0.01, tl, segments=8).translate(0, 0, depth),
                            mat_id + "_thread", mesh=vis))
    return shapes, dims, technical


def nut_solid(p: dict, technical: bool) -> tuple[K.Solid, dict[str, float]]:
    d = float(p["diameter_mm"])
    pitch = float(p["pitch_mm"])
    iso = iso_or_scaled(d)
    s, m = iso["s"], iso["m"] * (1.3 if p.get("type") == "nyloc" else 1.0)
    body = _hex_prism(s, m) & _chamfer_cone(s, m, top=True, bottom=True)
    if technical:
        spp = 20
        cutter = K.internal_thread_cutter(d, pitch, m + 2 * pitch, samples_per_pitch=spp,
                                          angular_segments=int(np.clip(round(64 + d * 4), 72, 160)) // 8 * 8)
        cutter = cutter.translate(0, 0, -pitch)
        minor = d - 2 * K.ISO_THREAD_DEPTH * pitch
        core = K.cylinder(minor / 2, m + 2, segments=96).translate(0, 0, -1)
        body = body - (cutter + core)
    else:
        body = body - K.cylinder(d / 2 - 0.4 * K.ISO_THREAD_DEPTH * pitch, m + 2, segments=96).translate(0, 0, -1)
    cs = K.cone(d / 2 + 0.6 * pitch, 0.6 * pitch + 0.01, d / 2 - 0.01, segments=96)
    body = body - cs.translate(0, 0, -0.01) - cs.rotate(180, 0, 0).translate(0, 0, m + 0.01)
    return body, {"diameter": d, "pitch": pitch, "across_flats": s, "height": round(m, 3)}


def washer_solid(p: dict) -> tuple[K.Solid, dict[str, float]]:
    d1, d2, h = float(p["inner_mm"]), float(p["outer_mm"]), float(p["thickness_mm"])
    ch = min(0.25 * h, 0.4)
    prof = P.chamfer_polygon([(d1 / 2, 0), (d2 / 2, 0), (d2 / 2, h), (d1 / 2, h)], [0, ch, ch, 0])
    return K.revolve(prof, segments=128), {"inner_diameter": d1, "outer_diameter": d2, "thickness": h}


def _materials(spec: ModelSpec) -> dict[str, Material]:
    lib = M.library()
    for key in list(MATERIAL_IDS.values()):
        base = lib[key]
        lib[key + "_thread"] = Material(id=key + "_thread", name=base.name + " (ren minh họa)", kind="metal",
                                        base_color=list(base.base_color), metallic=base.metallic,
                                        roughness=base.roughness, textures={"normal": "textures/thread_normal.png"},
                                        normal_scale=1.0)
    return lib


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    cat = spec.category
    mat_key = p.get("material", "zinc")
    mat_id = MATERIAL_IDS.get(mat_key, "steel_zinc")
    mats = _materials(spec)
    d = float(p.get("diameter_mm", 8))
    b = AssemblyBuilder(spec.name or f"{cat} M{d:g}", cat, mats)
    aliases_bolt = ["bu lông", "bu-lông", "bulong", "bolt", "ốc", "con ốc", "thân ốc"]
    if cat == "bolt":
        shapes, dims, technical = bolt_shapes(p, mat_id)
        L = float(p["length_mm"])
        head = {"hex": "đầu lục giác", "socket_cap": "đầu trụ lục giác chìm", "countersunk": "đầu côn"}[p.get("head", "hex")]
        b.add("bolt", f"Bu-lông M{d:g}×{L:g} {head}", f"M{d:g}x{L:g} bolt", "bolt", shapes, aliases=aliases_bolt,
              function=f"Chi tiết kẹp chặt ren ngoài M{d:g} bước {p['pitch_mm']:g} mm, vật liệu {MATERIAL_VI.get(mat_key, '')}"
                       + (f", cấp bền {p['grade']}" if p.get("grade") else "") + ".",
              position_tag="center", dimensions=dims, required=True, explode_dir=(0, 0, 1), explode_distance=0.0)
        z_nut = max(0.0, min(L * 0.25, L - iso_or_scaled(d)["m"] * 2.5))
        if p.get("include_nut"):
            nut, ndims = nut_solid({"diameter_mm": d, "pitch_mm": p["pitch_mm"]}, technical)
            b.add("nut", f"Đai ốc M{d:g}", f"M{d:g} nut", "nut", Shape(nut.translate(0, 0, z_nut), mat_id, 38.0),
                  parent_id="bolt", aliases=["đai ốc", "tán", "con tán", "nut", "ê cu"], function="Đai ốc ăn khớp ren để siết chặt mối ghép.",
                  position_tag="bottom", dimensions=ndims, explode_dir=(0, 0, -1), explode_distance=L * 0.55, explode_order=1)
            z_nut += ndims["height"]
        if p.get("include_washer"):
            iso = iso_or_scaled(d)
            w, wdims = washer_solid({"inner_mm": iso["w1"], "outer_mm": iso["w2"], "thickness_mm": iso["wh"]})
            b.add("washer", f"Vòng đệm M{d:g}", f"M{d:g} washer", "washer", Shape(w.translate(0, 0, z_nut), mat_id, 38.0),
                  parent_id="bolt", aliases=["vòng đệm", "long đền", "lông đền", "washer"],
                  function="Phân bố lực siết và bảo vệ bề mặt chi tiết.", position_tag="bottom", dimensions=wdims,
                  explode_dir=(0, 0, -1), explode_distance=L * 0.3, explode_order=2)
        b.note_stage(1, "Tháo đai ốc ra khỏi đầu ren")
        b.note_stage(2, "Tháo vòng đệm")
        b.metadata.update({"thread_mode": "technical" if technical else "illustrative",
                           "thread_standard": "ISO 68-1 (biên dạng cơ bản)", "dimensionally_specified": True})
    elif cat == "nut":
        technical = p.get("thread", "technical") == "technical"
        nut, ndims = nut_solid(p, technical)
        shapes = [Shape(nut, mat_id, 38.0)]
        if p.get("type") == "nyloc":
            m = ndims["height"]
            ring = K.revolve([(d / 2 - 0.3, m), (iso_or_scaled(d)["s"] * 0.42, m), (iso_or_scaled(d)["s"] * 0.42, m + 0.25 * m),
                              (d / 2 - 0.3, m + 0.25 * m)], segments=96)
            shapes.append(Shape(ring, "plastic_white", 38.0))
        b.add("nut", f"Đai ốc M{d:g}", f"M{d:g} nut", "nut", shapes, aliases=["đai ốc", "tán", "nut", "ê cu"],
              function="Đai ốc ren trong ăn khớp với bu-lông.", position_tag="center", dimensions=ndims, required=True)
        b.metadata.update({"thread_mode": "technical" if technical else "illustrative", "dimensionally_specified": True})
    else:  # washer
        w, wdims = washer_solid(p)
        b.add("washer", f"Vòng đệm M{d:g}", f"M{d:g} washer", "washer", Shape(w, mat_id, 38.0),
              aliases=["vòng đệm", "long đền", "lông đền", "washer"], function="Phân bố lực siết, chống lún bề mặt.",
              position_tag="center", dimensions=wdims, required=True)
        b.metadata.update({"dimensionally_specified": True})
    return b.build()
