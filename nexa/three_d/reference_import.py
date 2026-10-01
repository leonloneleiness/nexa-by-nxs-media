"""Offline conversion of licensed MJCF reference geometry to NEXA assemblies.

MuJoCo is an optional maintenance dependency, not needed to view the resulting GLB.
Preserves metric scale and source joint transforms. Simulation visuals are not manufacturing CAD.
"""
from pathlib import Path
import numpy as np

from nexa.three_d.geometry.kernel import MeshData
from nexa.three_d.models import Bounds, ExplosionStep, Material, Part3D, ros_to_asset
from nexa.three_d.pipeline import ModelBuild


def import_mjcf(path: Path) -> ModelBuild:
    import mujoco as mj
    m = mj.MjModel.from_xml_path(str(path.resolve()))
    d = mj.MjData(m)
    if m.nkey:
        mj.mj_resetDataKeyframe(m, d, 0)
    mj.mj_forward(m, d)
    meshes, materials, pivots, axes, body_ids = {}, {}, {}, {}, {}
    for gid in range(m.ngeom):
        if int(m.geom_group[gid]) != 2 or int(m.geom_type[gid]) != int(mj.mjtGeom.mjGEOM_MESH):
            continue
        bid = int(m.geom_bodyid[gid])
        if bid == 0:
            continue
        name = mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, bid) or f"body_{bid}"
        body_ids[name] = bid
        mesh_id = int(m.geom_dataid[gid])
        va, vn = int(m.mesh_vertadr[mesh_id]), int(m.mesh_vertnum[mesh_id])
        fa, fn = int(m.mesh_faceadr[mesh_id]), int(m.mesh_facenum[mesh_id])
        vertices = np.asarray(m.mesh_vert[va:va + vn], dtype=float)
        faces = np.asarray(m.mesh_face[fa:fa + fn], dtype=np.int64).copy()
        # Preserve source corner normals. Recomputing averaged normals cancels on
        # double-sided thin panels and loses the sharp edges supplied by the source.
        na = int(m.mesh_normaladr[mesh_id])
        nn = int(m.mesh_normalnum[mesh_id])
        normals = np.asarray(m.mesh_normal[na:na + nn], dtype=float)
        face_normals = np.asarray(m.mesh_facenormal[fa:fa + fn], dtype=np.int64)
        pairs, inverse = np.unique(np.column_stack([faces.ravel(), face_normals.ravel()]), axis=0, return_inverse=True)
        vertices = vertices[pairs[:, 0]]
        normals = normals[pairs[:, 1]]
        rotation = d.geom_xmat[gid].reshape(3, 3)
        vertices = (vertices @ rotation.T + d.geom_xpos[gid]) * 1000
        normals = normals @ rotation.T
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        if np.any(norms < 1e-8):
            raise ValueError("Source contains invalid corner normals: " + name)
        mesh = MeshData(ros_to_asset(vertices), inverse.reshape(-1, 3), ros_to_asset(normals / norms))
        midx = int(m.geom_matid[gid])
        mid = f"ref_mat_{midx}" if midx >= 0 else f"ref_geom_{gid}"
        rgba = list(map(float, m.mat_rgba[midx] if midx >= 0 else m.geom_rgba[gid]))
        materials[mid] = Material(id=mid, name=(mj.mj_id2name(m, mj.mjtObj.mjOBJ_MATERIAL, midx) if midx >= 0 else mid) or mid,
                                 base_color=rgba, metallic=0.15, roughness=0.6)
        meshes.setdefault(name, []).append((mesh, mid))
        jid = int(m.body_jntadr[bid])
        hinge = jid >= 0 and int(m.jnt_type[jid]) == int(mj.mjtJoint.mjJNT_HINGE)
        pivots[name] = ros_to_asset((d.xanchor[jid] if hinge else d.xpos[bid])[None] * 1000)[0]
        axes[name] = ros_to_asset(d.xaxis[jid][None])[0].tolist() if hinge else None
    if not meshes:
        raise ValueError("Không tìm thấy lưới hiển thị nhóm 2 trong MJCF.")
    allv = np.vstack([mesh.vertices for group in meshes.values() for mesh, _ in group])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    shift = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    by_bid = {bid: name for name, bid in body_ids.items()}
    parts = []
    for name, group in meshes.items():
        bid = body_ids[name]
        pb = int(m.body_parentid[bid])
        while pb and pb not in by_bid:
            pb = int(m.body_parentid[pb])
        parent = by_bid.get(pb)
        for mesh, _ in group:
            mesh.vertices -= shift
        bounds = Bounds.of_points(np.vstack([mesh.vertices for mesh, _ in group]))
        pivot = pivots[name] - shift
        direction = np.asarray(bounds.center) - (lo + hi) / 2 + shift
        length = float(np.linalg.norm(direction))
        direction = direction / length if length > 1e-8 else np.array([0., 1., 0.])
        parts.append(Part3D(id=name, name_vi=name.replace("_", " "), name_en=name, parent_id=parent,
                            category="joint" if axes[name] else "part", material=group[0][1], bounds=bounds,
                            pivot=pivot.tolist(), joint_axis=axes[name], triangles=sum(x.triangle_count for x, _ in group),
                            function="Hình học và vị trí khớp từ mô hình tham chiếu MJCF; không mô tả chi tiết chế tạo bên trong.",
                            explode_vector=direction.tolist(), explode_distance=80 if parent else 0,
                            explode_order=1, confidence=1.0))
    plan = [ExplosionStep(1, [p.id for p in parts if p.explode_distance], "Tách minh họa theo cây khớp; không phải quy trình tháo thật")]
    return ModelBuild(parts, meshes, materials, plan, has_assembly=True,
                      metadata={"source_format": "MJCF", "source_scale": "meters_to_mm_no_rescale",
                                "source_joint_count": int(m.njnt), "reference_visuals": True,
                                "explosion": "heuristic_radial", "manufacturing_unverified": True},
                      warnings=["Mô hình mô phỏng có nguồn: đúng lưới/vị trí khớp nguồn, không có đầy đủ chi tiết chế tạo bên trong."])
