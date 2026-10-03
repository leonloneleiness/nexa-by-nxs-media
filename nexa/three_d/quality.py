"""Chấm điểm chất lượng và quality gate (docs/three_d.md §Chất lượng).

Thang điểm mặc định (100):
  30 hình dáng & tỷ lệ tổng thể   — kiểm tra tỷ lệ/đối xứng deterministic (70%) + AI chấm ảnh 6 góc (30%)
  25 đầy đủ linh kiện             — checklist do mã tính từ ModelSpec + tên/alias bộ phận
  20 kích thước & vị trí lắp      — đo trực tiếp trên lưới so với thông số bắt buộc, va chạm, tiếp đất, liên kết
  15 lưới/topology                — hữu hạn, pháp tuyến, kín, suy biến, lỗ (từ render), faceting, ngân sách tam giác
  10 vật liệu & hình thức         — vật liệu hợp lệ/hợp loại bộ phận (70%) + AI (30%)

AI không bao giờ là bằng chứng duy nhất: khi không có AI, mô hình tham số dùng điểm deterministic (có căn cứ hình
học từ template), còn mô hình cloud/DSL bị giới hạn phần điểm AI nên KHÔNG thể đạt ngưỡng nếu thiếu đánh giá ảnh.
Mô hình đạt khi: tổng ≥ ngưỡng, không thiếu bộ phận bắt buộc, không lỗi hình học nghiêm trọng, không lỗi asset/đường
dẫn, không sai kích thước bắt buộc, manifest hợp lệ (nếu có assembly).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from nexa.three_d import measure as MS
from nexa.three_d.checklist import canonical_checklist, evaluate
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import MeshData, Solid
from nexa.three_d.models import Material, Part3D
from nexa.three_d.spec import ModelSpec, iso_or_scaled

WEIGHTS = {"shape": 30.0, "completeness": 25.0, "dimensions": 20.0, "mesh": 15.0, "material": 10.0}
GROUND_CATEGORIES = {"rover", "quadruped", "humanoid", "helicopter"}


@dataclass
class PartData:
    part: Part3D
    meshes: list[tuple[MeshData, Material]]
    solid: Solid | None = None            # hệ kỹ thuật (chỉ có với mô hình tham số)
    no_clash_with: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    scores: dict[str, float]
    total: float
    gates: dict[str, dict]
    passed: bool
    status: str                            # passed | failed | best_effort
    checks: list[dict] = field(default_factory=list)
    missing_parts: list[str] = field(default_factory=list)
    dimension_errors: list[str] = field(default_factory=list)
    geometry_errors: list[str] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    ai_review: dict | None = None
    notes: list[str] = field(default_factory=list)
    fixes: list[dict] = field(default_factory=list)      # gợi ý sửa riêng phần chưa đạt (cho vòng refinement)

    def to_dict(self) -> dict:
        return {"scores": {k: round(v, 2) for k, v in self.scores.items()}, "total": round(self.total, 2),
                "gates": self.gates, "passed": self.passed, "status": self.status, "checks": self.checks,
                "missing_parts": self.missing_parts, "dimension_errors": self.dimension_errors,
                "geometry_errors": self.geometry_errors, "measurements": self.measurements,
                "metadata": self.metadata, "ai_review": self.ai_review, "notes": self.notes, "fixes": self.fixes,
                "weights": WEIGHTS}


class _Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, group: str, name: str, ok: bool, detail: str = "", weight: float = 1.0) -> bool:
        self.items.append({"group": group, "name": name, "ok": bool(ok), "detail": detail, "weight": weight})
        return ok

    def ratio(self, group: str) -> float | None:
        its = [c for c in self.items if c["group"] == group]
        if not its:
            return None
        w = sum(c["weight"] for c in its)
        return sum(c["weight"] for c in its if c["ok"]) / w if w else None


# ------------------------------------------------------------------ đo đạc
def _all_vertices(pd: PartData) -> np.ndarray:
    vs = [m.vertices for m, _ in pd.meshes if len(m.vertices)]
    return np.vstack(vs) if vs else np.zeros((0, 3))


def _crest_centers(y: np.ndarray, r: np.ndarray, r_major: float, depth: float) -> list[float]:
    """Tâm các đỉnh ren (đoạn liên tiếp có bán kính gần đường kính lớn) dọc một đường sinh, bỏ đoạn cụt hai đầu."""
    order = np.argsort(y)
    y, r = y[order], r[order]
    crest = r > r_major - 0.3 * depth
    centers = []
    start = None
    for i, c in enumerate(crest):
        if c and start is None:
            start = i
        if (not c or i == len(crest) - 1) and start is not None:
            end = i if c else i - 1
            centers.append(0.5 * (y[start] + y[end]))
            start = None
    return centers[1:-1] if len(centers) > 2 else []


def _crest_pitch(y: np.ndarray, r: np.ndarray, r_major: float, depth: float) -> float | None:
    """Bước ren đo từ khoảng cách giữa các đỉnh ren liên tiếp dọc một đường sinh."""
    centers = _crest_centers(y, r, r_major, depth)
    if len(centers) < 3:
        return None
    return float(np.median(np.diff(centers)))


def _crest_phase(y: np.ndarray, r: np.ndarray, r_major: float, depth: float, pitch: float) -> float | None:
    centers = _crest_centers(y, r, r_major, depth)
    if len(centers) < 2:
        return None
    ang = 2 * math.pi * (np.asarray(centers) % pitch) / pitch
    return float((math.atan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * math.pi)) / (2 * math.pi) * pitch)


def measure_bolt(pd: PartData, spec: ModelSpec) -> dict[str, float]:
    p = spec.params
    d, L = float(p["diameter_mm"]), float(p["length_mm"])
    v = _all_vertices(pd)
    y = v[:, 1]
    r = np.hypot(v[:, 0], v[:, 2])
    out: dict[str, float] = {}
    tip = float(y.min())
    wide = y[r > d / 2 * 1.15]
    if p.get("head") == "countersunk":
        out["length"] = float(y.max() - tip)
        shank_top = tip + L - (2.0 * d - d) / 2
    else:
        shank_top = float(wide.min()) if len(wide) else float(y.max())
        out["length"] = shank_top - tip
    shank = (y > tip + 0.2 * d) & (y < shank_top - 0.05 * d)
    if shank.any():
        out["major_diameter"] = float(2 * r[shank].max())
    if p.get("thread", "technical") == "technical":
        pitch = float(p["pitch_mm"])
        depth = 0.541266 * pitch
        tl = float(p.get("thread_length_mm") or L)
        theta = np.arctan2(v[:, 0], v[:, 2])
        zone = (y > tip + 2 * pitch) & (y < tip + tl - 2.5 * pitch)
        col0 = zone & (np.abs(theta) < 1e-3) & (r > 0.1)
        colpi = zone & (np.abs(np.abs(theta) - math.pi) < 1e-3) & (r > 0.1)
        m0 = _crest_pitch(y[col0], r[col0], d / 2, depth) if col0.sum() > 10 else None
        if m0 is not None:
            out["pitch"] = m0
        if col0.sum() > 10 and colpi.sum() > 10:
            # helix thật: đỉnh ren ở θ=π lệch đúng nửa bước so với θ=0 (pha = trung bình vòng của tâm đỉnh ren mod P)
            p0, ppi = _crest_phase(y[col0], r[col0], d / 2, depth, pitch), _crest_phase(y[colpi], r[colpi], d / 2, depth, pitch)
            if p0 is not None and ppi is not None:
                out["helix_phase_offset"] = float(((ppi - p0) % pitch) / pitch)
    if p.get("head", "hex") == "hex":
        hv = v[y > shank_top + 0.5]
        if len(hv) > 12:
            xz = hv[:, [0, 2]]
            widths = []
            for ang in np.radians(np.arange(0, 180, 0.5)):
                proj = xz @ np.array([math.cos(ang), math.sin(ang)])
                widths.append(proj.max() - proj.min())
            out["across_flats"] = float(min(widths))
    return out


def measure_gear(pd: PartData) -> dict[str, float]:
    v = _all_vertices(pd)
    r = np.hypot(v[:, 0], v[:, 2])
    out = {"tip_diameter": float(2 * r.max()), "face_width": float(np.ptp(v[:, 1]))}
    tipband = r > r.max() * 0.985
    ang = np.sort(np.degrees(np.arctan2(v[tipband, 0], v[tipband, 2])) % 360)
    if len(ang) > 3:
        gaps = np.diff(np.concatenate([ang, [ang[0] + 360]]))
        out["teeth_count"] = float((gaps > 3.0).sum()) if (gaps > 3.0).sum() else float("nan")
    return out


def _center(pd: PartData) -> np.ndarray:
    b = pd.part.bounds
    return np.array([(a + c) / 2 for a, c in zip(b.min, b.max)])


def _aabb_gap(a: Part3D, b: Part3D) -> float:
    gap = 0.0
    for i in range(3):
        d = max(a.bounds.min[i] - b.bounds.max[i], b.bounds.min[i] - a.bounds.max[i], 0.0)
        gap = max(gap, d)
    return gap


def smooth_faceting_ratio(mesh: MeshData, model_size: float, px: float = 1000.0) -> float:
    """Tỷ lệ (theo chiều dài) các cạnh tô mượt có "độ võng" thấy được: cạnh dùng chung đỉnh/pháp tuyến (bề mặt cong)
    giữa hai mặt lệch góc θ trên đoạn dài L tạo sai lệch viền ≈ L·θ/8. Khi mô hình chiếm ~px pixel, sai lệch lớn hơn
    1 pixel (model_size/px) là thấy được cạnh đa giác. Linh kiện nhỏ ít phân đoạn không bị phạt vô lý."""
    f = mesh.faces
    if len(f) < 8 or model_size <= 0:
        return 0.0
    v = mesh.vertices
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    ln = np.linalg.norm(fn, axis=1)
    ok = ln > 1e-12
    fn = fn / np.maximum(ln, 1e-12)[:, None]
    e = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    fid = np.tile(np.arange(len(f)), 3)
    key = np.sort(e, axis=1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks, fs = key[order], fid[order]
    same = np.all(ks[1:] == ks[:-1], axis=1)
    a, b = fs[:-1][same], fs[1:][same]
    edges = ks[:-1][same]
    good = ok[a] & ok[b]
    if not good.any():
        return 0.0
    theta = np.arccos(np.clip(np.einsum("ij,ij->i", fn[a[good]], fn[b[good]]), -1, 1))
    elen = np.maximum(np.linalg.norm(v[edges[good, 0]] - v[edges[good, 1]], axis=1), 1e-12)
    # bề rộng mặt vuông góc với cạnh chung = chiều cao tam giác trên cạnh đó (trung bình hai mặt)
    width = 0.5 * (ln[a[good]] + ln[b[good]]) / elen
    visible = width * theta / 8.0 > model_size / px
    return float((elen * visible).sum() / max(1e-12, elen.sum()))


# ------------------------------------------------------------------ chấm điểm
def assess(spec: ModelSpec, parts: list[PartData], *, mode: str, metadata: dict | None = None,
           renders: dict | None = None, validation: Any = None, manifest_report: Any = None,
           ai_review: dict | None = None, threshold: float = 90.0, max_triangles: int = 2_000_000,
           require_assembly: bool = True) -> QualityReport:
    from nexa.three_d.validator import mesh_report
    meta = dict(metadata or {})
    C = _Checks()
    missing: list[str] = []
    dim_errors: list[str] = []
    geo_errors: list[str] = []
    meas: dict[str, Any] = {}
    notes: list[str] = []
    fixes: list[dict] = []
    cat = spec.category
    all_v = [v for pd in parts for v in [_all_vertices(pd)] if len(v)]
    V = np.vstack(all_v) if all_v else np.zeros((1, 3))
    size = np.ptp(V, axis=0)
    diag = float(np.linalg.norm(size)) or 1.0
    by_cat: dict[str, list[PartData]] = {}
    for pd in parts:
        by_cat.setdefault(pd.part.category, []).append(pd)

    # ---------- 25: đầy đủ linh kiện ----------
    checklist = canonical_checklist(spec)
    frac, missing = evaluate(checklist, [pd.part.category for pd in parts])
    for item in checklist:
        have = len(by_cat.get(item.category, []))
        C.add("completeness", f"{item.label_vi}", have >= item.count, f"{have}/{item.count}", weight=item.count)
    named = sum(1 for pd in parts if pd.part.name_vi.strip() and pd.part.aliases) / max(1, len(parts))
    if not checklist:
        frac = 1.0 if parts else 0.0
    score_complete = 22.0 * frac + 3.0 * named
    for m in missing:
        fixes.append({"kind": "missing_part", "detail": m})

    # ---------- 30: hình dáng & tỷ lệ (deterministic) ----------
    def ratio_in(name: str, val: float, lo: float, hi: float) -> None:
        C.add("shape", name, lo <= val <= hi, f"{val:.3f} (chuẩn {lo:g}–{hi:g})")

    if cat == "uav":
        motors = by_cat.get("motor", [])
        n = int(spec.params.get("arm_count", 4))
        if motors:
            cs = np.array([_center(m) for m in motors])
            rad = np.hypot(cs[:, 0], cs[:, 2])
            meas["wheelbase_measured"] = float(2 * rad.mean())
            C.add("shape", "motor cách đều tâm", float(rad.std() / max(rad.mean(), 1e-9)) < 0.01, f"lệch {rad.std():.2f} mm")
            ang = np.sort(np.degrees(np.arctan2(cs[:, 0], cs[:, 2])) % 360)
            gaps = np.diff(np.concatenate([ang, [ang[0] + 360]]))
            C.add("shape", "motor phân bố đều quanh trục", bool(np.all(np.abs(gaps - 360 / max(1, len(ang))) < 2.0)),
                  f"khoảng góc {np.round(gaps, 1).tolist()}")
            C.add("shape", "số motor = số tay đòn", len(motors) == n, f"{len(motors)}/{n}")
        ratio_in("tỷ lệ rộng/dài", size[0] / max(size[2], 1e-9), 0.75, 1.33)
        ratio_in("tỷ lệ cao/rộng", size[1] / max(size[0], 1e-9), 0.15, 0.7)
    elif cat == "rover":
        ratio_in("tỷ lệ dài/rộng", size[2] / max(size[0], 1e-9), 0.9, 2.4)
        wheels = by_cat.get("wheel", [])
        if wheels:
            dia = np.array([max(w.part.bounds.size[1], w.part.bounds.size[2]) for w in wheels])
            C.add("shape", "các bánh cùng đường kính", float(np.ptp(dia)) < 0.01 * float(dia.mean()), f"{np.round(dia, 1).tolist()}")
            xs = np.array([_center(w)[0] for w in wheels])
            C.add("shape", "bánh đối xứng trái/phải", abs(float(xs.sum())) < 0.01 * float(size[0]) * len(xs), f"tổng x = {xs.sum():.2f}")
    elif cat == "humanoid":
        ratio_in("tỷ lệ rộng vai/cao", size[0] / max(size[1], 1e-9), 0.3, 0.7)
        heads = by_cat.get("head", [])
        if heads:
            C.add("shape", "đầu ở trên cùng", heads[0].part.bounds.max[1] >= float(V[:, 1].max()) - 0.005 * size[1],
                  f"đỉnh đầu {heads[0].part.bounds.max[1]:.0f}")
        for c2 in ("hand", "foot"):
            its = by_cat.get(c2, [])
            if len(its) == 2:
                x = sorted(_center(i)[0] for i in its)
                C.add("shape", f"{c2} đối xứng", abs(x[0] + x[1]) < 0.01 * size[0] + 1.0, f"x = {np.round(x, 1).tolist()}")
    elif cat == "quadruped":
        ratio_in("tỷ lệ cao/dài", size[1] / max(size[2], 1e-9), 0.4, 1.3)
        feet = by_cat.get("foot", [])
        if feet:
            xs = sorted(_center(f)[0] for f in feet)
            C.add("shape", "chân đối xứng trái/phải", abs(sum(xs)) < 0.02 * size[0] * len(xs) + 1.0, f"{np.round(xs, 1).tolist()}")
    elif cat == "helicopter":
        disk = meta.get("rotor_disk") or {}
        fus = by_cat.get("fuselage", [])
        if disk and fus:
            ratio_in("đường kính rotor/dài thân", 2 * float(disk.get("radius", 0)) / max(fus[0].part.bounds.size[2], 1e-9), 0.8, 2.2)
        hubs = sorted(by_cat.get("rotor_hub", []), key=lambda h: _center(h)[2], reverse=True)
        if len(hubs) >= 2:
            C.add("shape", "rotor đuôi nằm sau rotor chính", _center(hubs[-1])[2] < _center(hubs[0])[2], "")
    elif cat == "boat":
        hulls = by_cat.get("hull", [])
        if hulls:
            hb = hulls[0].part.bounds.size
            ratio_in("thân tàu: dài/rộng", hb[2] / max(hb[0], 1e-9), 2.3, 6.0)
            ratio_in("thân tàu: rộng/cao mạn", hb[0] / max(hb[1], 1e-9), 1.5, 3.5)
            hc = _center(hulls[0])
            props = by_cat.get("propeller", [])
            if props:
                C.add("shape", "chân vịt ở phía đuôi", all(_center(pp)[2] < hc[2] for pp in props), "")
                C.add("shape", "chân vịt dưới đường mạn", all(pp.part.bounds.max[1] < hulls[0].part.bounds.max[1] for pp in props), "")
            ys = [_center(mm)[0] for mm in by_cat.get("motor", [])]     # nắp máy/trục đối xứng (chân vịt 3 lá thì không)
            if len(ys) > 1:
                C.add("shape", "các máy đối xứng hai mạn", abs(sum(ys)) < 0.01 * size[0] * len(ys) + 1.0, f"{np.round(ys, 1).tolist()}")
    elif cat in ("bolt", "nut", "washer", "gear", "flange", "bracket"):
        C.add("shape", "khối liền (một vật thể)", all(len(pd.meshes) > 0 for pd in parts), "")
        if cat == "bolt":
            ratio_in("tỷ lệ dài/đường kính", size[1] / max(float(spec.params["diameter_mm"]), 1e-9), 0.5, 60)
    elif cat in MS.CHECKS:
        C.add("shape", "có hình học", len(parts) > 0, "")        # hình dáng theo tiêu chuẩn: measure.run_checks bên dưới
    else:
        approx = spec.params.get("approx_size_mm")
        if approx:
            ratio_in("kích thước so với mô tả", float(size.max()) / float(approx), 0.8, 1.25)
        C.add("shape", "có hình học", len(parts) > 0, "")
        if len(parts) > 1:
            # vật thể tự do: mọi bộ phận phải chạm/lồng vào ít nhất một bộ phận khác (không lơ lửng giữa không trung)
            loose = [pd.part.id for pd in parts
                     if min(_aabb_gap(pd.part, o.part) for o in parts if o is not pd) > 0.01 * diag]
            C.add("shape", "mọi bộ phận gắn vào mô hình", not loose, f"{loose[:5]}", weight=2.0)
            if loose:
                fixes.append({"kind": "floating", "parts": loose})

    # ---------- 20: kích thước & vị trí lắp ----------
    tol = 0.01
    p = spec.params
    if cat == "bolt" and by_cat.get("bolt"):
        mb = measure_bolt(by_cat["bolt"][0], spec)
        meas.update({f"bolt_{k}": round(v, 4) for k, v in mb.items()})
        d, L = float(p["diameter_mm"]), float(p["length_mm"])
        checks = [("đường kính ren", mb.get("major_diameter"), d, 0.01), ("chiều dài", mb.get("length"), L, 0.01)]
        if p.get("thread", "technical") == "technical":
            checks.append(("bước ren", mb.get("pitch"), float(p["pitch_mm"]), 0.02))
            ph = mb.get("helix_phase_offset")
            if ph is not None:
                ok = abs(ph - 0.5) < 0.06
                C.add("dimensions", "ren helix thật (lệch pha nửa bước ở θ = π)", ok, f"lệch pha {ph:.3f} bước")
                if not ok:
                    dim_errors.append("ren không phải đường xoắn ốc chuẩn")
        if p.get("head", "hex") == "hex":
            checks.append(("cạnh lục giác (s)", mb.get("across_flats"), iso_or_scaled(d)["s"], 0.02))
        for name, got, want, t in checks:
            if got is None:
                C.add("dimensions", name, False, "không đo được")
                dim_errors.append(f"không đo được {name}")
                continue
            ok = abs(got - want) <= max(t * want, 0.02)
            C.add("dimensions", name, ok, f"đo {got:.3f} mm / yêu cầu {want:g} mm", weight=2.0)
            if not ok:
                dim_errors.append(f"{name}: đo {got:.3f} mm ≠ {want:g} mm")
    elif cat == "gear" and by_cat.get("gear"):
        mg = measure_gear(by_cat["gear"][0])
        meas.update({f"gear_{k}": round(v, 4) for k, v in mg.items() if math.isfinite(v)})
        want = float(p["module_mm"]) * (int(p["teeth"]) + 2)
        ok = abs(mg["tip_diameter"] - want) <= 0.01 * want
        C.add("dimensions", "đường kính đỉnh răng", ok, f"đo {mg['tip_diameter']:.3f} / {want:g}", weight=2.0)
        if not ok:
            dim_errors.append("đường kính đỉnh răng sai")
        tc = mg.get("teeth_count")
        if tc is not None and math.isfinite(tc):
            ok = int(round(tc)) == int(p["teeth"])
            C.add("dimensions", "số răng", ok, f"đếm {int(round(tc))} / {p['teeth']}", weight=2.0)
            if not ok:
                dim_errors.append("số răng sai")
        ok = abs(mg["face_width"] - float(p["face_width_mm"])) <= 0.01 * float(p["face_width_mm"]) + 0.02
        C.add("dimensions", "bề rộng răng", ok, f"{mg['face_width']:.3f}")
    elif cat in ("flange", "washer", "nut") and parts:
        v = _all_vertices(parts[0])
        r = np.hypot(v[:, 0], v[:, 2])
        want = {"flange": p.get("outer_d_mm"), "washer": p.get("outer_mm"), "nut": None}[cat]
        if want:
            ok = abs(2 * r.max() - float(want)) <= 0.01 * float(want)
            C.add("dimensions", "đường kính ngoài", ok, f"đo {2 * r.max():.3f} / {want:g}", weight=2.0)
            if not ok:
                dim_errors.append("đường kính ngoài sai")
        if cat == "nut":
            s = iso_or_scaled(float(p["diameter_mm"]))["s"]
            widths = [float(np.ptp(v[:, [0, 2]] @ np.array([math.cos(a), math.sin(a)]))) for a in np.radians(np.arange(0, 180, 0.5))]
            ok = abs(min(widths) - s) <= 0.02 * s
            C.add("dimensions", "cạnh lục giác đai ốc", ok, f"{min(widths):.3f} / {s:g}", weight=2.0)
            if not ok:
                dim_errors.append("cạnh lục giác đai ốc sai")
    elif cat == "bracket" and parts:
        want = (float(p["width_mm"]), float(p["height_mm"]), float(p["depth_mm"]))
        got = (size[0], size[1], size[2])
        for nm, g, w in zip(("rộng", "cao", "sâu"), got, want):
            ok = abs(g - w) <= 0.01 * w + 0.05
            C.add("dimensions", f"kích thước {nm}", ok, f"{g:.2f} / {w:g}")
            if not ok:
                dim_errors.append(f"kích thước {nm} sai")
    elif cat == "uav" and "wheelbase_measured" in meas:
        want = float(p["wheelbase_mm"])
        ok = abs(meas["wheelbase_measured"] - want) <= tol * want
        C.add("dimensions", "khoảng cách trục motor (wheelbase)", ok, f"{meas['wheelbase_measured']:.1f} / {want:g} mm", weight=2.0)
        if not ok:
            dim_errors.append("wheelbase sai")
    elif cat in ("rover", "quadruped", "helicopter", "humanoid", "boat"):
        key, axis = {"rover": ("length_mm", 2), "quadruped": ("length_mm", 2), "helicopter": ("length_mm", 2),
                     "humanoid": ("height_mm", 1), "boat": ("length_mm", 2)}[cat]
        if key in p:
            want = float(p[key])
            ok = abs(float(size[axis]) - want) <= 0.005 * want
            C.add("dimensions", "kích thước tổng thể", ok, f"{size[axis]:.1f} / {want:g} mm", weight=2.0)
            if not ok and key in spec.explicit:
                dim_errors.append("kích thước tổng thể sai")
    # mẫu kỹ thuật mở rộng: đo theo tiêu chuẩn trên khối thật (measure.py)
    for chk in MS.run_checks(spec, parts, meta):
        C.add(chk.group, chk.name, chk.ok, chk.detail, weight=chk.weight)
        if not chk.ok and chk.critical:
            dim_errors.append(f"{chk.name}: {chk.detail}")
    # tiếp đất
    if cat in GROUND_CATEGORIES or cat in MS.GROUND:
        ground_cats = {"rover": {"wheel"}, "quadruped": {"foot"}, "humanoid": {"foot"},
                       "helicopter": {"landing_gear"}}.get(cat) or MS.GROUND[cat]
        gp = [pd for pd in parts if pd.part.category in ground_cats]
        ymin = float(V[:, 1].min())
        if gp:
            lows = [pd.part.bounds.min[1] for pd in gp]
            ok = all(abs(lv - ymin) <= 0.01 * size[1] + 0.5 for lv in lows)
            C.add("dimensions", "bộ phận tiếp đất chạm mặt đất", ok, f"thấp nhất {np.round(lows, 1).tolist()} vs {ymin:.1f}")
            if not ok:
                fixes.append({"kind": "ground_contact", "detail": "không phải mọi bánh/chân chạm đất"})
    # liên kết cha–con (không có bộ phận lơ lửng)
    by_id = {pd.part.id: pd for pd in parts}
    floating = [pd.part.id for pd in parts if pd.part.parent_id and pd.part.parent_id in by_id and
                _aabb_gap(pd.part, by_id[pd.part.parent_id].part) > 0.02 * diag]
    C.add("dimensions", "không có bộ phận lơ lửng", not floating, f"{floating[:5]}", weight=2.0)
    if floating:
        fixes.append({"kind": "floating", "parts": floating})
    # va chạm bất hợp lý (chỉ các cặp template khai báo, đo bằng giao khối)
    clashes = []
    for pd in parts:
        if pd.solid is None:
            continue
        for other in pd.no_clash_with:
            od = by_id.get(other)
            if od is None or od.solid is None:
                continue
            vol = pd.solid.intersection_volume(od.solid)
            ref = min(abs(pd.solid.volume()), abs(od.solid.volume())) or 1.0
            if vol > 1e-3 * ref:
                clashes.append(f"{pd.part.id}×{other} ({vol:.1f} mm³)")
    disks = meta.get("prop_disks") or []
    for i in range(len(disks)):
        for j in range(i + 1, len(disks)):
            a, b2 = disks[i], disks[j]
            dist = float(np.linalg.norm(np.array(a["center"][:2]) - np.array(b2["center"][:2])))
            if abs(a["center"][2] - b2["center"][2]) < 1.0 and dist < a["radius"] + b2["radius"] - 0.5:
                clashes.append(f"vùng quét {a['part']}×{b2['part']}")
    C.add("dimensions", "không va chạm bất hợp lý", not clashes, "; ".join(clashes[:4]), weight=2.0)
    if clashes:
        fixes.append({"kind": "clash", "pairs": clashes})
        geo_errors.append("va chạm: " + "; ".join(clashes[:3]))
    if meta.get("strict_overlap") and mode == "parametric":
        # mẫu kỹ thuật: quét giao khối MỌI cặp không cha–con + mỗi bộ phận phải chạm bộ phận đỡ (min_gap thật)
        contacts = [tuple(c) for c in (meta.get("contacts") or [])]
        over = MS.overlap_scan(parts, contacts)
        meas["overlap_pairs"] = len(over)
        C.add("dimensions", "không cặp bộ phận nào xuyên nhau (quét mọi cặp)", not over,
              "; ".join(f"{a}×{b} {v:.2f} mm³" for a, b, v in over[:4]), weight=3.0)
        if over:
            fixes.append({"kind": "clash", "pairs": [f"{a}×{b}" for a, b, _ in over]})
            geo_errors.append("xuyên nhau: " + "; ".join(f"{a}×{b} ({v:.1f} mm³)" for a, b, v in over[:3]))
        tol = max(0.05, 1e-4 * diag)
        loose = MS.support_scan(parts, contacts, tol)
        meas["unsupported_parts"] = len(loose)
        C.add("dimensions", "mọi bộ phận chạm bộ phận đỡ (không lơ lửng)", not loose,
              "; ".join(f"{a} hở {g:.2f} mm" for a, g in loose[:4]), weight=3.0)
        if loose:
            fixes.append({"kind": "floating", "parts": [a for a, _ in loose]})
            geo_errors.append("lơ lửng: " + "; ".join(f"{a} ({g:.2f} mm)" for a, g in loose[:3]))

    # ---------- 15: lưới/topology ----------
    total_tris = sum(m.triangle_count for pd in parts for m, _ in pd.meshes)
    meas["triangles"] = total_tris
    mesh_errs = []
    fac = []
    for pd in parts:
        for m, _ in pd.meshes:
            r = mesh_report(m, pd.part.id, check_watertight=False)
            mesh_errs += r.errors
            if m.normals is not None and m.triangle_count > 200:
                fac.append(smooth_faceting_ratio(m, diag))
    C.add("mesh", "tọa độ/pháp tuyến hợp lệ, không suy biến nghiêm trọng", not mesh_errs, "; ".join(mesh_errs[:3]), weight=5.0)
    geo_errors += mesh_errs
    solids = [pd.solid for pd in parts if pd.solid is not None]
    if mode == "parametric" and solids:
        bad = [pd.part.id for pd in parts if pd.solid is not None and (not pd.solid.status_ok or pd.solid.is_empty)]
        C.add("mesh", "khối đặc kín (manifold)", not bad, f"{bad[:5]}", weight=4.0)
    else:
        from nexa.three_d.validator import watertight
        wt = [watertight(m)[0] for pd in parts for m, _ in pd.meshes if m.triangle_count]
        C.add("mesh", "lưới kín", bool(wt) and np.mean(wt) >= 0.8, f"{np.mean(wt) if wt else 0:.0%} lưới kín", weight=4.0)
    C.add("mesh", "trong ngân sách tam giác", 0 < total_tris <= max_triangles, f"{total_tris:,}/{max_triangles:,}", weight=1.5)
    meas["faceting_ratio"] = round(float(np.mean(fac)) if fac else 0.0, 4)
    C.add("mesh", "không lộ cạnh đa giác trên mặt cong", (float(np.mean(fac)) if fac else 0.0) < 0.03,
          f"{meas['faceting_ratio']:.2%} chiều dài cạnh mượt có độ võng > 1 px", weight=1.5)
    holes = max((r.backface_ratio for r in (renders or {}).values()), default=0.0)
    meas["hole_ratio"] = round(holes, 5)
    if renders:
        C.add("mesh", "không thiếu mặt khuất/lỗ (render 6 góc)", holes <= 0.003, f"{holes:.3%}", weight=3.0)
        if holes > 0.02:
            geo_errors.append(f"lưới thủng/thiếu mặt ({holes:.1%} diện tích)")

    # ---------- 10: vật liệu ----------
    mat_ok = all(pd.meshes and all(mt is not None for _, mt in pd.meshes) for pd in parts)
    C.add("material", "mọi bộ phận có vật liệu", mat_ok, "", weight=3.0)
    pbr_ok = all(0 <= mt.metallic <= 1 and 0 <= mt.roughness <= 1 and all(0 <= c <= 1 for c in mt.base_color)
                 for pd in parts for _, mt in pd.meshes)
    C.add("material", "thông số PBR hợp lệ", pbr_ok, "", weight=2.0)
    fit, cnt = 0, 0
    for pd in parts:
        exp = M.expected_kinds(pd.part.category)
        if not exp:
            continue
        cnt += 1
        main = pd.meshes[0][1] if pd.meshes else None
        if main is not None and main.kind in exp:
            fit += 1
    C.add("material", "vật liệu hợp loại bộ phận", cnt == 0 or fit / cnt >= 0.85, f"{fit}/{cnt}", weight=2.0)

    # ---------- tổng hợp điểm ----------
    ai = ai_review if isinstance(ai_review, dict) and ai_review.get("ok") else None
    det_shape = C.ratio("shape")
    det_shape = 1.0 if det_shape is None else det_shape
    # Nhóm hỗ trợ: hình dáng đo được bằng template (AI tối đa 30%). Vật thể tự do: kiểm tra tất định chỉ có kích thước/
    # liên kết, nên đánh giá ảnh chiếm 70% điểm hình dáng và 50% điểm vật liệu (tránh điểm cao "ảo").
    ai_w_shape, ai_w_mat = (0.3, 0.3) if spec.supported else (0.7, 0.5)
    if ai is not None:
        shape = WEIGHTS["shape"] * ((1 - ai_w_shape) * det_shape + ai_w_shape * float(ai.get("shape_score", 0)) / 10.0)
        if ai.get("category_match") is False:
            shape *= 0.5
    elif mode == "parametric":
        shape = WEIGHTS["shape"] * det_shape
        notes.append("Chưa có đánh giá ảnh bằng AI: điểm hình dáng dựa trên kiểm tra hình học của template.")
    else:
        shape = WEIGHTS["shape"] * (1 - ai_w_shape) * det_shape
        notes.append(f"Mô hình không phải tham số và chưa có đánh giá ảnh: phần điểm AI ({ai_w_shape:.0%}) bị bỏ trống.")
    dim_r = C.ratio("dimensions")
    dims = WEIGHTS["dimensions"] * (1.0 if dim_r is None else dim_r)
    mesh_r = C.ratio("mesh")
    mesh_s = WEIGHTS["mesh"] * (1.0 if mesh_r is None else mesh_r)
    mat_r = C.ratio("material") or 0.0
    if ai is not None:
        material = WEIGHTS["material"] * ((1 - ai_w_mat) * mat_r + ai_w_mat * float(ai.get("appearance_score", 0)) / 10.0)
    elif mode == "parametric":
        material = WEIGHTS["material"] * mat_r
    else:
        material = WEIGHTS["material"] * (1 - ai_w_mat) * mat_r
    if not spec.supported:
        # Vật thể tự do: không có checklist tất định → "đủ bộ phận" theo danh sách bộ phận thiết yếu do người chấm (AI)
        # liệt kê; lỗi nghiêm trọng người chấm chỉ ra bị trừ vào hình dáng. Không có AI → chỉ tính 40% phần này.
        if ai is not None:
            vis = [bool(x.get("visible")) for x in ai.get("parts_visible", []) if isinstance(x, dict)]
            vis_frac = (sum(vis) / len(vis)) if vis else float(ai.get("shape_score", 0)) / 10.0
            score_complete = WEIGHTS["completeness"] * (0.2 * named + 0.8 * vis_frac)
            sev = [i.get("severity") for i in ai.get("issues", []) if isinstance(i, dict)]
            penalty = min(12.0, 3.0 * sev.count("major") + 6.0 * sev.count("critical"))
            if penalty:
                shape = max(0.0, shape - penalty)
                notes.append(f"Trừ {penalty:g} điểm hình dáng vì người chấm chỉ ra lỗi nghiêm trọng.")
        else:
            score_complete = WEIGHTS["completeness"] * 0.4 * named
    scores = {"shape": shape, "completeness": score_complete, "dimensions": dims, "mesh": mesh_s, "material": material}
    total = float(sum(scores.values()))
    if ai is not None and ai.get("category_match") is False:
        notes.append("AI nhận xét ảnh render không giống loại vật thể yêu cầu.")
        fixes.append({"kind": "category_mismatch", "detail": ai.get("summary", "")})
    val_errors = list(getattr(validation, "errors", []) or [])
    man_errors = list(getattr(manifest_report, "errors", []) or [])
    gates = {
        "score": {"ok": total >= threshold, "detail": f"{total:.1f} / ngưỡng {threshold:g}"},
        "required_parts": {"ok": not missing, "detail": "; ".join(missing) or "đủ"},
        "geometry": {"ok": not geo_errors, "detail": "; ".join(geo_errors[:4]) or "không lỗi nghiêm trọng"},
        "asset": {"ok": not val_errors, "detail": "; ".join(val_errors[:4]) or "hợp lệ"},
        "dimensions": {"ok": not dim_errors, "detail": "; ".join(dim_errors[:4]) or "đúng"},
        "manifest": {"ok": not man_errors, "detail": "; ".join(man_errors[:4]) or "hợp lệ"},
    }
    if spec.reference_images:
        per_view = {x.get("view"): x.get("shape_score", 0) for x in (ai or {}).get("reference_views", [])}
        similar = (ai is not None and ai.get("category_match") is True
                   and all(ai.get(k) is True for k in ("object_only", "structure_preserved", "text_preserved"))
                   and float(ai.get("shape_score", 0)) >= 8
                   and float(ai.get("appearance_score", 0)) >= 7
                   and all(float(per_view.get(v, 0)) >= 7.5 for v in spec.reference_images)
                   and not any(i.get("severity") in ("major", "critical") for i in ai.get("issues", [])))
        reasons = []
        if ai is None:
            reasons.append("chưa có đánh giá ảnh hợp lệ")
        else:
            for key, label in (("category_match", "loại vật thể chưa khớp"),
                               ("object_only", "còn hậu cảnh hoặc chưa xác nhận loại hết hậu cảnh"),
                               ("structure_preserved", "kết cấu/khoảng gãy chưa khớp hoặc chưa được xác nhận"),
                               ("text_preserved", "chữ trên biển chưa khớp hoặc chưa đọc được")):
                if ai.get(key) is not True:
                    reasons.append(label)
            if float(ai.get("shape_score", 0)) < 8:
                reasons.append(f"hình dáng {ai.get('shape_score', 0):g}/10, cần ít nhất 8")
            if float(ai.get("appearance_score", 0)) < 7:
                reasons.append(f"màu/vật liệu {ai.get('appearance_score', 0):g}/10, cần ít nhất 7")
            from nexa.three_d.reference_images import VIEWS
            for view in spec.reference_images:
                if float(per_view.get(view, 0)) < 7.5:
                    reasons.append(f"góc {VIEWS[view]} chưa đạt 7,5/10" if view in per_view else f"chưa chấm góc {VIEWS[view]}")
            reasons.extend(str(i.get("issue", "còn lỗi lớn")) for i in ai.get("issues", [])
                           if i.get("severity") in ("major", "critical"))
        gates["reference_similarity"] = {"ok": bool(similar), "detail":
            "Đạt đối chiếu ảnh từng góc" if similar else "Cần hoàn thiện: " + "; ".join(reasons)}
    passed = all(g["ok"] for g in gates.values())
    supported = spec.supported and mode != "dsl"
    status = ("passed" if passed else "failed") if supported else ("best_effort" if all(
        g["ok"] for k, g in gates.items() if k != "score") else "failed")
    thread_technical = cat == "bolt" and p.get("thread", "technical") == "technical" and not any("ren" in e for e in dim_errors)
    dimensionally = cat in ("bolt", "nut", "washer", "gear", "flange", "bracket") or spec.group == "components" or bool(spec.explicit)
    meta_flags = {
        "conceptual": not dimensionally, "dimensionally_specified": dimensionally,
        "geometry_validated": gates["geometry"]["ok"] and gates["asset"]["ok"],
        "manufacturing_unverified": True,
        "assembly_confidence": float(meta.get("assembly_confidence", 1.0 if mode == "parametric" else 0.0)),
        "segmentation_confidence": meta.get("segmentation_confidence"),
        "quality_score": round(total, 2),
        "technical_thread": thread_technical if cat == "bolt" else None,
        "ai_review_used": ai is not None,
        "quality_target_applicable": supported,
    }
    return QualityReport(scores=scores, total=total, gates=gates, passed=passed and supported, status=status,
                         checks=C.items, missing_parts=missing, dimension_errors=dim_errors, geometry_errors=geo_errors,
                         measurements=meas, metadata=meta_flags, ai_review=ai_review, notes=notes, fixes=fixes)
