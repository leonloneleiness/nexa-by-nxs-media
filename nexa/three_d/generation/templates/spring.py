"""Lò xo xoắn trụ: nén (đầu mài phẳng / khép kín / hở), kéo (móc tròn kiểu máy — crossover center hook), xoắn
(hai chân tiếp tuyến). Dây tròn quét dọc đường xoắn ốc thật (bước thay đổi mượt ở vòng đầu), không phải texture.

Công thức hình học theo EN 13906-1 / Shigley (Mechanical Engineering Design, ch. 10):
- nén mài phẳng: L0 = n·p + 2d; khép kín không mài: L0 = n·p + 3d; hở: L0 = n·p + d (n = số vòng làm việc,
  tổng số vòng = n + 2 với đầu khép kín);
- kéo: thân quấn khít (bước = d), móc tròn đường kính = đường kính trung bình;
- xoắn: vòng quấn gần khít (bước 1,05d), hai chân thẳng dài ≈ 1,5·D.
Lò xo đứng thẳng, trục Z, đáy z = 0.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def compression_pitch(L0: float, n: float, d: float, ends: str) -> float:
    extra = {"ground": 2 * d, "closed": 3 * d, "open": d}[ends]
    return (L0 - extra) / n


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("spring_type", "compression")
    d = float(p.get("wire_d_mm", 2.0))
    OD = float(p.get("outer_d_mm", 20.0))
    Dm = OD - d
    R = Dm / 2
    n = float(p.get("active_coils", 8.0))
    L0 = float(p.get("free_length_mm") or 50.0)
    mats = MC.tech_materials(spec)
    mat = "stainless" if p.get("material") == "stainless" else "spring_steel"
    names = {"compression": "Lò xo nén", "extension": "Lò xo kéo", "torsion": "Lò xo xoắn"}
    b = AssemblyBuilder(spec.name or f"{names[kind]} Ø{OD:g}×{d:g}", "spring", mats)
    seg = 16 if d > 1.2 else 12
    meta: dict = {"spring_type": kind, "wire_d_mm": d, "outer_d_mm": OD, "active_coils": n}
    if kind == "compression":
        ends = p.get("ends", "ground")
        pch = compression_pitch(L0, n, d, ends)
        if ends == "open":
            path = MC.helix_path(R, [(n, pch)], z0=d / 2, per_turn=40)
            coil = K.tube(path, d / 2, seg, rounded_ends=True)
        elif ends == "closed":
            path = MC.helix_path(R, [(1.0, d), (n, pch), (1.0, d)], z0=d / 2, per_turn=40)
            coil = K.tube(path, d / 2, seg, rounded_ends=True)
        else:
            # đầu mài: đường tâm vòng cuối nằm ở z = 0 và z = L0, cắt phẳng (mài) còn đúng chiều dài tự do
            path = MC.helix_path(R, [(1.0, d), (n, pch), (1.0, d)], z0=0.0, per_turn=40)
            scale = L0 / (path[-1, 2] - path[0, 2])
            path[:, 2] *= scale
            coil = K.tube(path, d / 2, seg, rounded_ends=True)
            coil = coil & K.box(4 * OD, 4 * OD, L0).translate(0, 0, L0 / 2)
        b.add("spring", names[kind], "Compression spring", "spring", Shape(coil, mat, 30.0), required=True,
              aliases=["lò xo", "lò xo nén", "spring", "vòng lò xo"],
              function=f"Lò xo nén dây Ø{d:g}, Ø ngoài {OD:g}, {n:g} vòng làm việc, bước {pch:.2f} mm, dài tự do {L0:g} mm, "
                       f"đầu {'mài phẳng' if ends == 'ground' else 'khép kín' if ends == 'closed' else 'hở'}.",
              position_tag="center", dimensions={"wire_d": d, "outer_d": OD, "free_length": L0, "pitch": round(pch, 3)})
        meta.update({"pitch_mm": pch, "ends": ends, "free_length_mm": L0, "total_coils": n + (0 if ends == "open" else 2)})
        b.metadata["contacts"] = []
    elif kind == "extension":
        hook_h = 2 * R + 1.4 * d                                   # từ đầu thân tới đỉnh ngoài móc (0,9d + 2R + d/2)
        n_body = max(3.0, (L0 - 2 * hook_h) / d)
        path = MC.helix_path(R, [(n_body, d)], z0=hook_h, per_turn=36)
        body = K.tube(path, d / 2, seg, rounded_ends=True)
        hooks = []
        for end_pt, sgn in ((path[-1], 1), (path[0], -1)):
            ang = math.atan2(end_pt[1], end_pt[0])
            u = np.array([math.cos(ang), math.sin(ang), 0.0])
            ez = np.array([0.0, 0.0, float(sgn)])
            base = np.array(end_pt)
            start = np.array([0.0, 0.0, base[2]]) + ez * (0.9 * d)
            ctr = start + ez * R
            pts = [base, base + ez * 0.3 * d - u * 0.25 * R, start - u * 0.02 * R]
            for phi in np.linspace(0.12 * math.pi, 1.88 * math.pi, 22):
                pts.append(ctr - ez * R * math.cos(phi) + u * R * math.sin(phi))
            hooks.append(Shape(K.tube(P.spline_through(np.asarray(pts), 70), d / 2, seg, rounded_ends=True), mat, 30.0))
        # một sợi dây liền: thân + 2 móc là một bộ phận (không tháo rời được)
        b.add("spring", "Lò xo kéo (thân + 2 móc)", "Extension spring", "spring", [Shape(body, mat, 30.0)] + hooks, required=True,
              aliases=["lò xo", "lò xo kéo", "thân lò xo", "móc", "móc lò xo", "spring", "hook"],
              function=f"Thân quấn khít {n_body:.1f} vòng (có lực căng ban đầu), dây Ø{d:g}, Ø ngoài {OD:g}, hai móc tròn kiểu "
                       "máy uốn qua tâm để treo.", position_tag="center", dimensions={"wire_d": d, "outer_d": OD, "free_length": L0})
        meta.update({"body_coils": n_body, "free_length_mm": L0})
        b.metadata["contacts"] = []
    else:
        pch = 1.05 * d
        path = MC.helix_path(R, [(n, pch)], z0=d / 2, per_turn=36)
        body = K.tube(path, d / 2, seg, rounded_ends=True)
        leg_len = 1.5 * OD
        legs = []
        for i0, i1 in ((-1, -2), (0, 1)):
            e = path[i0]
            tng = e - path[i1]
            tng[2] = 0.0
            tng /= np.linalg.norm(tng)
            legs.append(Shape(K.tube(np.array([e - tng * 0.5 * d, e + tng * leg_len]), d / 2, seg, rounded_ends=True), mat, 30.0))
        b.add("spring", "Lò xo xoắn (thân + 2 chân)", "Torsion spring", "spring", [Shape(body, mat, 30.0)] + legs, required=True,
              aliases=["lò xo", "lò xo xoắn", "thân lò xo", "chân lò xo", "chân", "spring", "leg"],
              function=f"Lò xo xoắn {n:g} vòng, dây Ø{d:g}, Ø ngoài {OD:g}; hai chân thẳng dài {leg_len:.0f} mm truyền mômen.",
              position_tag="center", dimensions={"wire_d": d, "outer_d": OD})
        meta.update({"pitch_mm": pch, "leg_len_mm": leg_len})
        b.metadata["contacts"] = []
    b.place_on_ground(center_xy=True)
    b.metadata.update(meta)
    b.metadata.update({"standard": "EN 13906-1 (hình học lò xo trụ)", "strict_overlap": True})
    return b.build()
