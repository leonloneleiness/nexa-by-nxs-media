"""Tiện ích kiểm thử chung cho các mẫu CAD kỹ thuật mở rộng (dựng, chấm, quét giao khối, kiểm tra kế hoạch tách)."""
from __future__ import annotations

import fnmatch
import itertools
import time

import numpy as np

from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.pipeline import ModelBuild
from nexa.three_d.quality import assess
from nexa.three_d.spec import normalize, validate_spec

MAX_TRIANGLES = 450_000


def build(cat: str, **params):
    """(spec, assembly, report, giây dựng)."""
    sp = normalize(validate_spec({"category": cat, "params": params}))
    t0 = time.perf_counter()
    asm = build_parametric(sp)
    dt = time.perf_counter() - t0
    rep = assess(sp, ModelBuild.from_assembly(asm).part_data(), mode="parametric", metadata=asm.metadata)
    return sp, asm, rep, dt


def failed(rep) -> list:
    return [(c["name"], c["detail"]) for c in rep.checks if not c["ok"]]


def measured(rep, name_part: str) -> dict:
    """Kiểm tra kích thước trong báo cáo có tên chứa `name_part` (phải có, và phải đạt)."""
    hits = [c for c in rep.checks if name_part in c["name"]]
    assert hits, f"không có phép đo '{name_part}'"
    return hits[0]


def _allowed(a: str, b: str, contacts) -> bool:
    return any((fnmatch.fnmatchcase(a, x) and fnmatch.fnmatchcase(b, y)) or (fnmatch.fnmatchcase(a, y) and fnmatch.fnmatchcase(b, x))
               for x, y in contacts)


def overlap_pairs(asm, rel: float = 1e-4, abs_mm3: float = 1e-3) -> list:
    """Quét giao khối MỌI cặp bộ phận không phải cha–con; bỏ qua chỗ tiếp xúc có chủ đích (metadata 'contacts')."""
    contacts = [tuple(c) for c in asm.metadata.get("contacts", [])]
    parts = [bp for bp in asm.parts if bp.solid is not None and not bp.solid.is_empty]
    bad = []
    for a, b in itertools.combinations(parts, 2):
        if a.part.parent_id == b.part.id or b.part.parent_id == a.part.id or _allowed(a.part.id, b.part.id, contacts):
            continue
        la, ha = a.solid.bounds()
        lb, hb = b.solid.bounds()
        if np.any(la > hb) or np.any(lb > ha):
            continue
        vol = a.solid.intersection_volume(b.solid)
        if vol > max(abs_mm3, rel * min(abs(a.solid.volume()), abs(b.solid.volume()))):
            bad.append((a.part.id, b.part.id, round(vol, 3)))
    return bad


def check_explosion(asm) -> None:
    """Kế hoạch tách hợp lệ: bước tăng dần, mỗi bước có chú thích, mọi bộ phận tách có hướng đơn vị, cha tồn tại."""
    ids = {bp.part.id for bp in asm.parts}
    orders = [s.order for s in asm.explosion_plan]
    assert orders == sorted(orders) and len(set(orders)) == len(orders)
    one_piece = all(bp.part.explode_distance == 0 for bp in asm.parts) and len(asm.parts) <= 3   # vd lò xo liền một dây
    assert asm.explosion_plan or one_piece, "không có bước tách"
    for s in asm.explosion_plan:
        assert s.description, f"bước {s.order} thiếu chú thích"
        assert set(s.part_ids) <= ids
    for bp in asm.parts:
        p = bp.part
        assert p.parent_id is None or p.parent_id in ids
        if p.explode_distance > 0:
            assert abs(np.linalg.norm(p.explode_vector) - 1) < 1e-6
    roots = [bp for bp in asm.parts if bp.part.parent_id is None]
    assert roots, "không có bộ phận gốc"


def assert_technical(asm, rep, dt: float | None = None, min_score: float = 99.0) -> None:
    gates = [k for k, g in rep.gates.items() if not g["ok"]]
    assert rep.total >= min_score and not gates, (rep.total, gates, failed(rep)[:5])
    assert asm.triangle_count <= MAX_TRIANGLES, asm.triangle_count
    assert not overlap_pairs(asm), overlap_pairs(asm)
    assert asm.metadata.get("strict_overlap") is True
    assert abs(asm.bounds.min[1]) < 1e-3, "đáy mô hình phải ở z = 0"
    check_explosion(asm)
    if dt is not None:
        assert dt < 8.0, f"dựng quá lâu {dt:.1f}s"
    for bp in asm.parts:
        assert bp.part.name_vi and bp.part.aliases, bp.part.id
