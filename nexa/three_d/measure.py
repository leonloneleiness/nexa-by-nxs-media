"""Đo kiểm deterministic cho các mẫu CAD kỹ thuật (đo trên khối/lưới THẬT, không đọc lại số template tự khai).

- overlap_scan: giao khối mọi cặp bộ phận không phải cha–con (trừ chỗ tiếp xúc có chủ đích khai trong metadata
  "contacts"): thể tích giao phải ≈ 0.
- support_scan: mỗi bộ phận có cha phải CHẠM cha (hoặc chạm một bộ phận tiếp xúc có chủ đích) — khoảng hở đo bằng
  manifold3d.min_gap, không dùng hộp bao.
- CHECKS[category](spec, parts, meta) → danh sách Check (kích thước theo tiêu chuẩn: ISO 15, NEMA ICS 16, …).
Hệ trục đo: hệ kỹ thuật (X trước, Y trái, Z lên, mm) — khối trong PartData.solid; đỉnh lưới asset được đổi lại.
"""
from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.geometry import kernel as K


@dataclass
class Check:
    group: str                 # "shape" | "dimensions"
    name: str
    ok: bool
    detail: str = ""
    weight: float = 1.0
    critical: bool = False     # sai → lỗi kích thước bắt buộc (gate)


# ------------------------------------------------------------------ tiện ích đo
def eng_vertices(pd: Any) -> np.ndarray:
    """Đỉnh lưới của bộ phận trong hệ kỹ thuật (asset (x, y, z) = kỹ thuật (Y, Z, X))."""
    vs = [m.vertices for m, _ in pd.meshes if len(m.vertices)]
    if not vs:
        return np.zeros((0, 3))
    v = np.vstack(vs)
    return np.column_stack([v[:, 2], v[:, 0], v[:, 1]])


def by_id(parts: Sequence[Any]) -> dict[str, Any]:
    return {pd.part.id: pd for pd in parts}


def by_cat(parts: Sequence[Any], cat: str) -> list[Any]:
    return [pd for pd in parts if pd.part.category == cat]


def solid_bounds(pd: Any) -> tuple[np.ndarray, np.ndarray]:
    if pd.solid is not None and not pd.solid.is_empty:
        return pd.solid.bounds()
    v = eng_vertices(pd)
    return v.min(axis=0), v.max(axis=0)


def probe_intervals(solid: K.Solid, axis: str, point: Sequence[float], eps: float = 0.02) -> list[tuple[float, float]]:
    """Các đoạn có vật liệu dọc đường thẳng song song `axis` qua `point` (đo lỗ, rãnh, khoảng cách)."""
    lo, hi = solid.bounds()
    i = "xyz".index(axis)
    span = float(np.max(hi - lo)) * 3 + 10.0
    size = [eps, eps, eps]
    size[i] = span
    c = [float(x) for x in point]
    c[i] = float((lo[i] + hi[i]) / 2)
    cut = solid & K.box(*size).translate(*c)
    if cut.is_empty:
        return []
    out = []
    for comp in cut.split_components():
        a, b = comp.bounds()
        out.append((float(a[i]), float(b[i])))
    return sorted(out)


def gaps_between(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(intervals[k][1], intervals[k + 1][0]) for k in range(len(intervals) - 1) if intervals[k + 1][0] - intervals[k][1] > 1e-6]


def ring_count(solid: K.Solid, center: Sequence[float], axis: str, radius: float, z0: float, z1: float,
               thickness: float = 0.05) -> int:
    """Số mảnh vật liệu của khối cắt bởi vỏ trụ mỏng bán kính `radius` quanh trục (đếm răng, lỗ, thanh)."""
    shell = K.cylinder(radius + thickness / 2, z1 - z0, segments=256) - K.cylinder(max(1e-3, radius - thickness / 2), z1 - z0 + 2,
                                                                                    segments=256).translate(0, 0, -1)
    shell = shell.translate(0, 0, z0)
    if axis == "x":
        shell = shell.transform(np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]]))
    elif axis == "y":
        shell = shell.transform(np.array([[0, 1.0, 0, 0], [0, 0, 1.0, 0], [1.0, 0, 0, 0]]))
    shell = shell.translate(*center)
    cut = solid & shell
    return 0 if cut.is_empty else len(cut.split_components())


def radial(v: np.ndarray, center: Sequence[float], axis: str) -> np.ndarray:
    idx = [i for i in range(3) if i != "xyz".index(axis)]
    c = np.asarray(center, float)
    return np.hypot(v[:, idx[0]] - c[idx[0]], v[:, idx[1]] - c[idx[1]])


def near(got: float | None, want: float, rel: float = 0.01, abs_: float = 0.05) -> bool:
    return got is not None and abs(got - want) <= max(rel * abs(want), abs_)


def dim(name: str, got: float | None, want: float, rel: float = 0.01, abs_: float = 0.05, unit: str = "mm",
        critical: bool = True, weight: float = 2.0) -> Check:
    ok = near(got, want, rel, abs_)
    detail = f"đo {got:.3f} {unit} / chuẩn {want:g} {unit}" if got is not None else "không đo được"
    return Check("dimensions", name, ok, detail, weight, critical)


def count_check(name: str, got: int, want: int, critical: bool = True) -> Check:
    return Check("dimensions", name, got == want, f"đếm {got} / {want}", 2.0, critical)


def shape(name: str, ok: bool, detail: str = "", weight: float = 1.0) -> Check:
    return Check("shape", name, bool(ok), detail, weight, False)


# ------------------------------------------------------------------ giao khối + tiếp xúc
def _allowed(a: str, b: str, contacts: Sequence[Sequence[str]]) -> bool:
    for pa, pb in contacts:
        if (fnmatch.fnmatchcase(a, pa) and fnmatch.fnmatchcase(b, pb)) or (fnmatch.fnmatchcase(a, pb) and fnmatch.fnmatchcase(b, pa)):
            return True
    return False


def overlap_scan(parts: Sequence[Any], contacts: Sequence[Sequence[str]] = (), rel_tol: float = 1e-4,
                 abs_tol: float = 1e-3) -> list[tuple[str, str, float]]:
    """Cặp (a, b, thể tích giao mm³) xuyên nhau — bỏ qua cha–con và chỗ tiếp xúc có chủ đích."""
    items = []
    for pd in parts:
        s = pd.solid
        if s is None or s.is_empty:
            continue
        lo, hi = s.bounds()
        items.append((pd.part.id, pd.part.parent_id, s, lo, hi, abs(s.volume())))
    out = []
    for i in range(len(items)):
        ai, ap, sa, la, ha, va = items[i]
        for j in range(i + 1, len(items)):
            bi, bp, sb, lb, hb, vb = items[j]
            if ap == bi or bp == ai:
                continue
            if np.any(la > hb + 1e-6) or np.any(lb > ha + 1e-6):
                continue
            if _allowed(ai, bi, contacts):
                continue
            vol = sa.intersection_volume(sb)
            if vol > max(abs_tol, rel_tol * min(va, vb)):
                out.append((ai, bi, float(vol)))
    return out


def support_scan(parts: Sequence[Any], contacts: Sequence[Sequence[str]] = (), tol: float = 0.05) -> list[tuple[str, float]]:
    """Bộ phận có cha nhưng không chạm cha lẫn bộ phận tiếp xúc có chủ đích: (id, khoảng hở nhỏ nhất mm)."""
    ids = {pd.part.id: pd for pd in parts if pd.solid is not None and not pd.solid.is_empty}
    out = []
    for pid, pd in ids.items():
        par = pd.part.parent_id
        if par is None or par not in ids:
            continue
        search = max(tol * 20, 1.0)
        best = pd.solid.m.min_gap(ids[par].solid.m, search)
        if best > tol:
            for oid, od in ids.items():
                if oid in (pid, par) or not _allowed(pid, oid, contacts):
                    continue
                best = min(best, pd.solid.m.min_gap(od.solid.m, search))
                if best <= tol:
                    break
        if best > tol:
            out.append((pid, float(best)))
    return out


# ------------------------------------------------------------------ kiểm tra theo category
CheckFn = Callable[[Any, Sequence[Any], dict], list[Check]]
CHECKS: dict[str, CheckFn] = {}
# bộ phận phải chạm mặt đất (z thấp nhất) theo category
GROUND: dict[str, set[str]] = {}


def register(*cats: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        for c in cats:
            CHECKS[c] = fn
        return fn
    return deco


def run_checks(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    fn = CHECKS.get(spec.category)
    if fn is None:
        return []
    try:
        return fn(spec, parts, meta)
    except Exception as exc:                      # đo lỗi = không đo được (không làm sập quality gate)
        return [Check("dimensions", "đo kích thước theo tiêu chuẩn", False, f"lỗi đo: {type(exc).__name__}: {exc}"[:200],
                      2.0, True)]


# ================================================================== linh kiện cơ khí tiêu chuẩn
@register("bearing")
def _bearing(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    code = spec.params["designation"]
    d, D, B, _ = S.BEARINGS[code]
    z, dw, dm = S.bearing_balls(code)
    ids = by_id(parts)
    out: list[Check] = []
    orr, inr = ids.get("outer_ring"), ids.get("inner_ring")
    if orr is None or inr is None:
        return [Check("dimensions", "vòng trong/vòng ngoài", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(orr)
    ctr = (lo + hi) / 2
    vo, vi = eng_vertices(orr), eng_vertices(inr)
    out.append(dim("đường kính lỗ d (ISO 15)", float(2 * radial(vi, ctr, "z").min()), d, 0.005, 0.03))
    out.append(dim("đường kính ngoài D (ISO 15)", float(2 * radial(vo, ctr, "z").max()), D, 0.005, 0.03))
    out.append(dim("bề rộng B (ISO 15)", float(np.ptp(vo[:, 2])), B, 0.005, 0.03))
    out.append(dim("bề rộng vòng trong", float(np.ptp(vi[:, 2])), B, 0.005, 0.03, critical=False, weight=1.0))
    balls = by_cat(parts, "ball")
    out.append(count_check("số bi", len(balls), z))
    if balls:
        sizes = [float(np.ptp(eng_vertices(b)[:, 2])) for b in balls]
        out.append(dim("đường kính bi Dw (cỡ ISO 3290)", float(np.mean(sizes)), dw, 0.01, 0.03, critical=False))
        cs_ = np.array([(solid_bounds(b)[0] + solid_bounds(b)[1]) / 2 for b in balls])
        rr = radial(cs_, ctr, "z")
        out.append(shape("bi nằm đều trên vòng tâm bi dm", float(np.ptp(rr)) < 0.02 and abs(float(rr.mean()) - dm / 2) < 0.05,
                         f"r = {rr.mean():.3f} / {dm / 2:.3f}"))
    seals = by_cat(parts, "seal")
    want = 2 if spec.params.get("seal", "open") in ("2RS", "ZZ") else 0
    out.append(shape("phớt/nắp chắn theo mã (2RS/ZZ)", len(seals) == want, f"{len(seals)}/{want}"))
    return out


__all__ = ["Check", "CHECKS", "GROUND", "overlap_scan", "support_scan", "run_checks", "probe_intervals", "ring_count",
           "eng_vertices"]


@register("stepper_motor")
def _stepper(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    size = int(spec.params.get("frame_size", 17))
    t = S.NEMA[size]
    ids = by_id(parts)
    fc, sh, rc = ids.get("front_cap"), ids.get("rotor_shaft"), ids.get("rear_cap")
    if fc is None or sh is None or rc is None:
        return [Check("dimensions", "nắp trước/trục/nắp sau", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(fc)
    ctr = (lo + hi) / 2
    out = [dim(f"cạnh mặt bích NEMA {size}", float(hi[0] - lo[0]), t["flange"], 0.005, 0.05),
           dim("cạnh mặt bích (phương Y)", float(hi[1] - lo[1]), t["flange"], 0.005, 0.05, critical=False, weight=1.0)]
    # mặt lắp: đỉnh nắp trước ở góc mặt bích (ngoài gờ định tâm)
    face = K_surface(fc.solid, "z", (lo[0] + 1.5, ctr[1], ctr[2]), True)
    hs = t["hole_spacing"] / 2
    spacing = None
    if face is not None:
        iv = probe_intervals(fc.solid, "x", (0, ctr[1] + hs, face - 1.2))
        gs = gaps_between(iv)
        if len(gs) >= 2:
            cs_ = sorted((a + b) / 2 for a, b in gs)
            spacing = cs_[-1] - cs_[0]
    out.append(dim("khoảng cách tâm lỗ lắp", spacing, t["hole_spacing"], 0.005, 0.08))
    vf = eng_vertices(fc)
    top = vf[vf[:, 2] > (face if face is not None else hi[2]) + 0.05]
    out.append(dim("đường kính gờ định tâm", float(2 * radial(top, ctr, "z").max()) if len(top) else None, t["pilot_d"], 0.005, 0.05))
    vs = eng_vertices(sh)
    above = vs[vs[:, 2] > hi[2] + 1.0]
    out.append(dim("đường kính trục", float(2 * radial(above, ctr, "z").max()) if len(above) else None, t["shaft_d"], 0.005, 0.02))
    if face is not None and len(above):
        out.append(dim("chiều dài trục tính từ mặt lắp", float(above[:, 2].max() - face), t["shaft_len"], 0.01, 0.1, critical=False))
    rlo, _ = solid_bounds(rc)
    rear = K_surface(rc.solid, "z", (rlo[0] + 1.5, ctr[1], ctr[2]), False)
    if face is not None and rear is not None:
        want = float(spec.params.get("body_length_mm") or t["lengths"][2])
        out.append(dim("chiều dài thân (mặt lắp → mặt sau)", face - rear, want, 0.005, 0.1,
                       critical="body_length_mm" in (spec.explicit or {})))
    return out


def K_surface(solid: K.Solid, axis: str, point: Sequence[float], positive: bool) -> float | None:
    """Mặt thật của khối dọc trục qua điểm (giống details.surface_at, không phụ thuộc templates)."""
    iv = probe_intervals(solid, axis, point)
    if not iv:
        return None
    return iv[-1][1] if positive else iv[0][0]


def gear_teeth(pd: Any, axis: str = "y") -> tuple[int, float, np.ndarray]:
    """(số răng đếm được, đường kính đỉnh răng, tâm) của bánh răng — đếm mảnh răng cắt bởi vỏ trụ sát đỉnh răng."""
    lo, hi = solid_bounds(pd)
    ctr = (lo + hi) / 2
    v = eng_vertices(pd)
    r = radial(v, ctr, axis)
    ra = float(r.max())
    i = "xyz".index(axis)
    w = float(hi[i] - lo[i])
    # vùng răng: bề rộng quanh tâm (moay-ơ nếu có nằm trong bán kính nhỏ hơn)
    n = ring_count(pd.solid, ctr, axis, ra * 0.985, -w, w, thickness=0.02)
    return n, 2 * ra, ctr


@register("gearbox")
def _gearbox(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    ratio = 1.0
    for st, mesh in enumerate(meta.get("mesh") or []):
        ga, gb = ids.get(mesh["driver"]), ids.get(mesh["driven"])
        sa, sb = ids.get(mesh["driver_shaft"]), ids.get(mesh["driven_shaft"])
        if not (ga and gb and sa and sb):
            out.append(Check("dimensions", f"cấp {st + 1}: bánh răng/trục", False, "thiếu", 2.0, True))
            continue
        za, da, _ = gear_teeth(ga)
        zb, db, _ = gear_teeth(gb)
        m = float(mesh["module"])
        # module đo từ đường kính đỉnh: da = m (z + 2)
        out.append(dim(f"cấp {st + 1}: module đo từ đỉnh răng bánh dẫn", da / (za + 2) if za else None, m, 0.01, 0.01, critical=False))
        out.append(dim(f"cấp {st + 1}: module đo từ đỉnh răng bánh bị dẫn", db / (zb + 2) if zb else None, m, 0.01, 0.01, critical=False))
        ca = (solid_bounds(sa)[0] + solid_bounds(sa)[1]) / 2
        cb = (solid_bounds(sb)[0] + solid_bounds(sb)[1]) / 2
        a_meas = float(math.hypot(cb[0] - ca[0], cb[2] - ca[2]))
        out.append(dim(f"cấp {st + 1}: khoảng cách tâm a = m(z1+z2)/2 (z đếm được {za}/{zb})", a_meas, m * (za + zb) / 2, 0.001, 0.02))
        if za:
            ratio *= zb / za
    want = float(spec.params.get("ratio", 12.0))
    out.append(Check("dimensions", "tỷ số truyền tổng (tích z2/z1 đếm trên lưới)", abs(ratio - want) <= 0.03 * want,
                     f"đo {ratio:.3f} / yêu cầu {want:g}", 2.0, True))
    out.append(shape("số cấp bánh răng", len(meta.get("mesh") or []) == int(spec.params.get("stages", 2)),
                     f"{len(meta.get('mesh') or [])}"))
    return out


@register("cylinder")
def _cylinder(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    kind = p.get("cylinder_type", "pneumatic")
    bore, stroke = float(p.get("bore_mm", 50.0)), float(p.get("stroke_mm", 100.0))
    ids = by_id(parts)
    bar, rod, pis, rc, fc, tr = (ids.get(k) for k in ("barrel", "piston_rod", "piston", "rear_cap", "front_cap", "tie_rods"))
    if not all((bar, rod, pis, rc, fc, tr)):
        return [Check("dimensions", "nòng/cần/piston/nắp/thanh giằng", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(bar)
    ctr = (lo + hi) / 2
    out = [dim("đường kính nòng", float(2 * radial(eng_vertices(bar), ctr, "x").min()), bore, 0.002, 0.03)]
    vr = eng_vertices(rod)
    x_tip = float(vr[:, 0].max())
    shank = vr[vr[:, 0] < hi[0]]
    want_rod = float(S.ISO15552[int(round(bore))]["rod"]) if kind == "pneumatic" else None
    if want_rod is not None:
        out.append(dim("đường kính cần piston (ISO 15552)", float(2 * radial(shank, ctr, "x").max()), want_rod, 0.005, 0.03))
        comps = tr.solid.split_components()
        cs_ = np.array([(c.bounds()[0] + c.bounds()[1]) / 2 for c in comps])
        if len(cs_) == 4:
            tg = float(np.mean([np.ptp(cs_[:, 1]), np.ptp(cs_[:, 2])]))
            out.append(dim("khoảng tâm thanh giằng TG (ISO 15552)", tg, float(S.ISO15552[int(round(bore))]["tg"]), 0.003, 0.05))
        else:
            out.append(count_check("số thanh giằng", len(cs_), 4))
    r_probe = 0.6 * bore / 2
    iv_r = probe_intervals(rc.solid, "x", (0, ctr[1] + r_probe, ctr[2]))
    iv_f = probe_intervals(fc.solid, "x", (0, ctr[1] + r_probe, ctr[2]))
    plo, phi = solid_bounds(pis)
    if iv_r and iv_f:
        travel = iv_f[0][0] - iv_r[-1][1] - float(phi[0] - plo[0])
        out.append(dim("hành trình (khoảng piston chạy giữa hai đệm)", travel, stroke, 0.002, 0.1))
        ext = {"retracted": 0.0, "mid": 0.5, "extended": 1.0}[p.get("state", "retracted")]
        out.append(dim("vị trí piston theo trạng thái", float(plo[0]) - iv_r[-1][1], ext * stroke, 0.01, 0.2, critical=False))
    out.append(shape("cần nhô ra khỏi nắp trước", x_tip > float(solid_bounds(fc)[1][0]), f"{x_tip:.1f}"))
    return out


def radial_probe(solid: K.Solid, center: Sequence[float], axis: str, angle_deg: float) -> list[tuple[float, float]]:
    """Đoạn vật liệu dọc tia bán kính (góc angle_deg quanh trục `axis`, đo từ trục thứ nhất còn lại) — xoay khối
    để tia trùng một trục tọa độ rồi dò."""
    c = np.asarray(center, float)
    ax = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    s = solid.translate(*(-c)).rotate_axis(ax, -angle_deg)
    probe_axis = {"x": "y", "y": "z", "z": "x"}[axis]
    iv = probe_intervals(s, probe_axis, (0, 0, 0))
    return [(a, b) for a, b in iv if b > 0]


def flange_checks(pd: Any, dn: int, axis: str = "x", label: str = "mặt bích", center: Sequence[float] | None = None,
                  x_range: tuple[float, float] | None = None, r_max: float | None = None) -> list[Check]:
    """Đo mặt bích EN 1092-1 PN16: đường kính ngoài D, vòng tâm lỗ K, số lỗ (đếm trên khối).
    center: một điểm trên trục ống; x_range: khoảng dọc trục chứa mặt bích (khi khối có thêm phần khác như cổ van)."""
    D, Kc, Lh, n, _M, _C2 = S.FLANGE_PN16[dn]
    lo, hi = solid_bounds(pd)
    ctr = np.asarray(center, float) if center is not None else (lo + hi) / 2
    v = eng_vertices(pd)
    if x_range is not None:
        i0 = "xyz".index(axis)
        v = v[(v[:, i0] >= x_range[0]) & (v[:, i0] <= x_range[1])]
    r = radial(v, ctr, axis)
    if r_max is not None:                                              # bỏ đỉnh của chi tiết khác cùng khoảng dọc trục
        v, r = v[r <= r_max], r[r <= r_max]
    out = [dim(f"{label}: đường kính ngoài D (EN 1092-1 PN16)", float(2 * r.max()), D, 0.005, 0.1)]
    i = "xyz".index(axis)
    big = v[r > 0.97 * r.max()]
    x_mid = float(np.median(big[:, i])) if len(big) else float(ctr[i])
    c2 = list(ctr)
    c2[i] = x_mid
    iv = radial_probe(pd.solid, c2, axis, 180.0 / n)
    gs = [g for g in gaps_between(iv) if g[0] > 0.3 * D / 2]
    kk = (gs[0][0] + gs[0][1]) if gs else None
    out.append(dim(f"{label}: vòng tâm lỗ K", kk, Kc, 0.005, 0.2))
    ring = K.cylinder(Kc / 2 + 0.05, 0.4, segments=256) - K.cylinder(Kc / 2 - 0.05, 2, segments=256).translate(0, 0, -1)
    to_axis = {"x": np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]]), "y": np.array([[0, 1.0, 0, 0], [0, 0, 1.0, 0], [1.0, 0, 0, 0]]),
               "z": np.eye(4)[:3]}[axis]
    ring = ring.translate(0, 0, -0.2).transform(to_axis).translate(*c2)
    cut = pd.solid & ring
    out.append(count_check(f"{label}: số lỗ bu-lông", 0 if cut.is_empty else len(cut.split_components()), n))
    return out


@register("ball_valve")
def _ball_valve(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    dn = int(spec.params.get("dn", 50))
    ids = by_id(parts)
    body, cap, ball, handle = ids.get("body"), ids.get("end_cap"), ids.get("ball"), ids.get("handle")
    if not all((body, cap, ball, handle)):
        return [Check("dimensions", "thân/nắp đầu/bi/tay gạt", False, "thiếu", 2.0, True)]
    lo_b, hi_b = solid_bounds(body)
    lo_c, hi_c = solid_bounds(cap)
    out = [dim("chiều dài mặt–mặt (ASME B16.10 Class 150 ngắn)", float(max(hi_b[0], hi_c[0]) - min(lo_b[0], lo_c[0])), S.VALVE_FTF[dn], 0.002, 0.1)]
    vb = eng_vertices(body)
    end = vb[vb[:, 0] < lo_b[0] + 0.02]                    # vòng mặt gờ nổi đầu vào: tâm = trục ống
    ctr = end.mean(axis=0) if len(end) else (lo_b + hi_b) / 2
    out.append(dim("đường kính lỗ (toàn lỗ = DN)", float(2 * radial(end, ctr, "x").min()) if len(end) else None, float(dn), 0.01, 0.2))
    D_, _K, _L, _n, _M, C2_ = S.FLANGE_PN16[dn]
    out += flange_checks(body, dn, "x", "mặt bích đầu vào", center=ctr, x_range=(float(lo_b[0]), float(lo_b[0]) + 2.0 + C2_ + 0.05))
    # tay gạt: song song ống = mở; vuông góc = đóng (đo hướng dài nhất của tay gạt)
    hv = eng_vertices(handle)
    ext = np.ptp(hv[:, :2], axis=0)
    along_x = ext[0] > ext[1]
    closed = spec.params.get("state", "open") == "closed"
    out.append(shape("tay gạt đúng trạng thái (dọc ống = mở)", along_x != closed, f"dx {ext[0]:.0f}, dy {ext[1]:.0f}"))
    # lỗ bi thẳng hàng ống khi mở: dò dọc trục X qua tâm bi
    blo, bhi = solid_bounds(ball)
    bc = (blo + bhi) / 2
    iv = probe_intervals(ball.solid, "x", (0, bc[1], bc[2]))
    out.append(shape("lỗ bi thông khi mở / chắn khi đóng", (len(iv) == 0) != closed, f"{len(iv)} đoạn vật liệu"))
    return out


@register("pipe_fitting")
def _pipe_fitting(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    dn = int(spec.params.get("dn", 50))
    kind = spec.params.get("fitting", "elbow90")
    od = S.PIPE_OD[dn]
    ids = by_id(parts)
    out: list[Check] = []
    if kind == "flange_joint":
        fa, fb = ids.get("flange_a"), ids.get("flange_b")
        if not (fa and fb):
            return [Check("dimensions", "hai mặt bích", False, "thiếu", 2.0, True)]
        out += flange_checks(fa, dn, "x", "mặt bích A")
        out += flange_checks(fb, dn, "x", "mặt bích B")
        v = eng_vertices(fa)
        lo, hi = solid_bounds(fa)
        neck = v[v[:, 0] < lo[0] + 0.3]
        out.append(dim("đường kính cổ hàn = OD ống (EN 10220)", float(2 * radial(neck, (lo + hi) / 2, "x").max()) if len(neck) else None, od, 0.005, 0.1))
        return out
    fit = ids.get("fitting")
    if fit is None:
        return [Check("dimensions", "phụ kiện", False, "thiếu", 2.0, True)]
    v = eng_vertices(fit)
    lo, hi = solid_bounds(fit)
    x0 = float(lo[0])
    inlet = v[v[:, 0] < x0 + 0.02]
    c0 = inlet.mean(axis=0)
    out.append(dim("đường kính ngoài đầu nối (OD ống EN 10220)", float(2 * radial(inlet, c0, "x").max()), od, 0.005, 0.1))
    if kind == "elbow90":
        out.append(dim("tâm–mặt A co 90° (ASME B16.9)", float(hi[1] - c0[1]), S.elbow90_a(dn), 0.003, 0.2))
    elif kind == "elbow45":
        nrm = np.array([math.cos(math.radians(45)), math.sin(math.radians(45)), 0.0])
        proj = v @ nrm
        c1 = v[proj > proj.max() - 0.02].mean(axis=0)
        chord = float(np.linalg.norm(c1 - c0))
        out.append(dim("tâm–mặt B co 45° (ASME B16.9)", chord / (2 * math.cos(math.radians(22.5))), S.ELBOW45_B[dn], 0.005, 0.2))
    elif kind == "tee":
        out.append(dim("tâm–mặt C tê đều (ASME B16.9) — nhánh", float(hi[1] - c0[1]), S.TEE_C[dn], 0.003, 0.2))
        out.append(dim("chiều dài ống chính = 2C", float(hi[0] - lo[0]), 2 * S.TEE_C[dn], 0.003, 0.2))
    return out


def mesh_components(mesh: Any) -> list[np.ndarray]:
    """Các thành phần liên thông của một lưới (theo đỉnh trùng vị trí) → danh sách mảng đỉnh."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    v = np.asarray(mesh.vertices)
    f = np.asarray(mesh.faces)
    if len(f) == 0:
        return []
    _, inv = np.unique(np.round(v, 5), axis=0, return_inverse=True)
    inv = inv.ravel()
    ff = inv[f]
    n = int(inv.max()) + 1
    rows = np.concatenate([ff[:, 0], ff[:, 1], ff[:, 2]])
    cols = np.concatenate([ff[:, 1], ff[:, 2], ff[:, 0]])
    g = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    k, lab = connected_components(g, directed=False)
    used = np.zeros(n, bool)
    used[ff.ravel()] = True
    vv = np.zeros((n, 3))
    vv[inv] = v
    return [vv[(lab == i) & used] for i in range(k) if np.any((lab == i) & used)]


def eng(v: np.ndarray) -> np.ndarray:
    return np.column_stack([v[:, 2], v[:, 0], v[:, 1]])


@register("belt_drive")
def _belt(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    belt = p.get("belt", "GT2")
    ids = by_id(parts)
    pa, pb = ids.get("pulley_driver"), ids.get("pulley_driven")
    if not (pa and pb and ids.get("belt")):
        return [Check("dimensions", "puly + đai", False, "thiếu", 2.0, True)]
    out: list[Check] = []
    centers = []
    for pd_ in (pa, pb):
        lo, hi = solid_bounds(pd_)
        cc = (lo + hi) / 2
        centers.append(cc)
    C = float(math.hypot(centers[1][0] - centers[0][0], centers[1][2] - centers[0][2]))
    want_c = float(p.get("center_distance_mm") or meta.get("center_distance_mm", C))
    if belt in S.BELTS:
        bt = S.BELTS[belt]
        out.append(Check("dimensions", "khoảng cách tâm (hiệu chỉnh ≤ ½ bước theo đai số răng nguyên)",
                         abs(C - want_c) <= bt["pitch"] / 2 + 1e-6, f"đo {C:.2f} mm / yêu cầu {want_c:g} mm", 2.0,
                         "center_distance_mm" in (spec.explicit or {})))
        teeth = []
        blo, bhi = solid_bounds(ids["belt"])
        yc = float((blo[1] + bhi[1]) / 2)                          # mặt giữa đai = giữa vùng răng puly
        for pd_, zt, cc in ((pa, int(p.get("teeth_driver", 20)), centers[0]), (pb, int(p.get("teeth_driven", 40)), centers[1])):
            ro = zt * bt["pitch"] / (2 * math.pi) - bt["pld"]
            v = eng_vertices(pd_)
            c2 = np.array([cc[0], yc, cc[2]])
            sec = pd_.solid & K.box(4 * ro + 40, 0.05, 4 * ro + 40).translate(cc[0], yc, cc[2])   # mặt cắt giữa vùng răng
            sv = sec.to_mesh().vertices if not sec.is_empty else v
            out.append(dim(f"đường kính đỉnh puly {zt} răng (PD − 2·PLD)", float(2 * radial(sv, c2, "y").max()), 2 * ro, 0.004, 0.03))
            n = ring_count(pd_.solid, c2, "y", ro - 0.45 * bt["tooth_h"], -0.8, 0.8, thickness=0.02)
            out.append(count_check(f"số răng puly (đếm, yêu cầu {zt})", n, zt))
            teeth.append(n)
        if all(teeth):
            want_r = int(p.get("teeth_driven", 40)) / int(p.get("teeth_driver", 20))
            out.append(dim("tỷ số truyền z2/z1 (đếm)", teeth[1] / teeth[0], want_r, 0.001, 0.001, unit=""))
    else:
        out.append(dim("khoảng cách tâm", C, want_c, 0.002, 0.1))
        v_ = S.VBELTS[belt]
        for pd_, dd, cc in ((pa, float(p.get("pulley_d_mm") or 100), centers[0]), (pb, float(p.get("pulley2_d_mm") or 200), centers[1])):
            r = radial(eng_vertices(pd_), cc, "y")
            out.append(dim(f"đường kính ngoài puly (dp {dd:g} + 2·0,28h, ISO 4183)", float(2 * r.max()), dd + 2 * 0.28 * v_["height"],
                           0.004, 0.1))
    return out


@register("chain_drive")
def _chain(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    ch = S.CHAINS[p.get("chain", "08B")]
    pitch = ch["pitch"]
    ids = by_id(parts)
    sa, sb, chain = ids.get("sprocket_driver"), ids.get("sprocket_driven"), ids.get("chain")
    if not (sa and sb and chain):
        return [Check("dimensions", "đĩa xích + xích", False, "thiếu", 2.0, True)]
    out: list[Check] = []
    cen = []
    for sp, zt in ((sa, int(p.get("teeth_driver", 17))), (sb, int(p.get("teeth_driven", 34)))):
        lo, hi = solid_bounds(sp)
        v = eng_vertices(sp)
        R = pitch / (2 * math.sin(math.pi / zt))
        cc = (lo + hi) / 2
        rr = radial(v, cc, "y")
        ra = float(rr.max())
        band = v[rr > ra * 0.98]
        cc[1] = float(np.median(band[:, 1])) if len(band) else cc[1]
        n = ring_count(sp.solid, cc, "y", (R + ra) / 2, -1.5, 1.5, thickness=0.02)
        out.append(count_check(f"số răng đĩa xích (đếm, yêu cầu {zt})", n, zt))
        out.append(dim(f"đường kính đỉnh răng da ≈ p(0,54 + cot(180°/z)) — z = {zt}", 2 * ra,
                       pitch * (0.54 + 1 / math.tan(math.pi / zt)), 0.01, 0.1, critical=False))
        cen.append(cc)
    roll_mesh = next((m for m, mt in chain.meshes if getattr(mt, "id", "") == "steel"), None)
    if roll_mesh is not None:
        comps = mesh_components(roll_mesh)
        cs_ = np.array([eng(c).mean(axis=0) for c in comps])
        out.append(Check("dimensions", "số mắt xích chẵn (đếm con lăn)", len(cs_) % 2 == 0 and len(cs_) > 10, f"{len(cs_)} con lăn",
                         2.0, True))
        if len(cs_) > 3:
            from scipy.spatial import cKDTree
            dd, _ = cKDTree(cs_).query(cs_, k=2)
            out.append(dim("bước xích đo giữa tâm con lăn (ISO 606)", float(np.median(dd[:, 1])), pitch, 0.002, 0.01))
    C = float(math.hypot(cen[1][0] - cen[0][0], cen[1][2] - cen[0][2]))
    want = float(p.get("center_distance_mm") or meta.get("center_requested_mm", C))
    out.append(Check("dimensions", "khoảng cách tâm (hiệu chỉnh ≤ ½ bước theo số mắt nguyên)", abs(C - want) <= pitch / 2 + 1e-6,
                     f"đo {C:.2f} / yêu cầu {want:g} mm", 2.0, "center_distance_mm" in (spec.explicit or {})))
    return out


@register("shaft_coupling")
def _coupling(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    d1 = float(p.get("bore_mm", 14.0))
    d2 = float(p.get("bore2_mm") or d1)
    ids = by_id(parts)
    out: list[Check] = []
    for sid, want in (("shaft_1", d1), ("shaft_2", d2)):
        sh = ids.get(sid)
        if sh is None:
            out.append(Check("dimensions", sid, False, "thiếu", 2.0, True))
            continue
        lo, hi = solid_bounds(sh)
        out.append(dim(f"đường kính trục {sid[-1]} = lỗ khớp nối", float(hi[1] - lo[1]), want, 0.005, 0.03))
    h1 = ids.get("hub_1")
    if h1 is not None:
        lo, hi = solid_bounds(h1)
        if p.get("coupling_type", "jaw") == "jaw":
            size = next(k for k in sorted(S.JAW_COUPLINGS) if S.JAW_COUPLINGS[k][2] >= max(d1, d2))
            out.append(dim(f"đường kính ngoài khớp vấu (ROTEX cỡ {size})", float(hi[1] - lo[1]), S.JAW_COUPLINGS[size][0], 0.005, 0.05))
            out.append(shape("có đệm sao đàn hồi", "spider" in ids, ""))
        v = eng_vertices(h1)
        ctr = (lo + hi) / 2
        left = v[v[:, 0] < ctr[0] - 0.5]
        out.append(dim("lỗ moay-ơ phía trục 1", float(2 * radial(left, ctr, "x").min()) if len(left) else None, d1, 0.005, 0.03))
    return out


@register("ball_screw")
def _ball_screw(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    d, lead = float(p.get("diameter_mm", 16)), float(p.get("lead_mm", 5))
    t = S.BALL_SCREWS[f"{int(round(d)):02d}{int(round(lead)):02d}"]
    ids = by_id(parts)
    sh, nut = ids.get("screw_shaft"), ids.get("ball_nut")
    if not (sh and nut):
        return [Check("dimensions", "trục vít + đai ốc", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(sh)
    out = [dim("chiều dài trục vít", float(hi[0] - lo[0]), float(p.get("length_mm", 500)), 0.002, 0.1)]
    v = eng_vertices(sh)
    yc, zc = (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2
    x0, x1 = lo[0] + 0.3 * (hi[0] - lo[0]), lo[0] + 0.7 * (hi[0] - lo[0])
    mid = v[(v[:, 0] > x0) & (v[:, 0] < x1)]
    r = np.hypot(mid[:, 1] - yc, mid[:, 2] - zc)
    out.append(dim("đường kính danh nghĩa vít", float(2 * r.max()), d, 0.005, 0.03))
    iv = probe_intervals(sh.solid, "x", (0, yc + d / 2 - 0.05, zc), eps=0.02)
    iv = [q for q in iv if q[0] > x0 and q[1] < x1]
    cen = [(a + b) / 2 for a, b in iv]
    out.append(dim("bước vít (khoảng gờ ren liên tiếp, đo dọc đường sinh)", float(np.median(np.diff(cen))) if len(cen) > 3 else None,
                   lead, 0.01, 0.02))
    vn = eng(nut.meshes[0][0].vertices)                           # khối thân + mặt bích đai ốc (shape đầu tiên)
    out.append(dim("đường kính mặt bích đai ốc (TBI SFU)", float(2 * np.hypot(vn[:, 1] - yc, vn[:, 2] - zc).max()), float(t["flange_d"]),
                   0.01, 0.2, critical=False))
    return out


@register("linear_guide")
def _linear_guide(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    g = S.LINEAR_GUIDES[spec.params.get("series", "HGR20")]
    ids = by_id(parts)
    rail = ids.get("rail")
    if rail is None:
        return [Check("dimensions", "ray", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(rail)
    out = [dim("bề rộng ray (HIWIN)", float(hi[1] - lo[1]), g["rail_w"], 0.003, 0.02),
           dim("chiều cao ray", float(hi[2] - lo[2]), g["rail_h"], 0.003, 0.02),
           dim("chiều dài ray", float(hi[0] - lo[0]), float(spec.params.get("length_mm", 400)), 0.002, 0.1)]
    iv = probe_intervals(rail.solid, "x", (0, (lo[1] + hi[1]) / 2, hi[2] - g["cb_h"] / 2))
    gs = gaps_between(iv)
    if len(gs) >= 2:
        c = np.array([(a + b) / 2 for a, b in gs])
        out.append(dim("bước lỗ lắp ray P", float(np.median(np.diff(c))), g["pitch"], 0.002, 0.05))
    else:
        out.append(dim("bước lỗ lắp ray P", None, g["pitch"]))
    cars = by_cat(parts, "carriage")
    out.append(count_check("số con trượt", len(cars), int(spec.params.get("carriages", 2))))
    if cars:
        clo, chi = solid_bounds(cars[0])
        out.append(dim("bề rộng con trượt", float(chi[1] - clo[1]), g["car_w"], 0.003, 0.05))
        out.append(dim("chiều cao lắp H (đáy ray → mặt con trượt)", float(chi[2] - lo[2]), g["h"], 0.003, 0.05))
    return out


@register("spring")
def _spring(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    kind = p.get("spring_type", "compression")
    d, OD = float(p.get("wire_d_mm", 2.0)), float(p.get("outer_d_mm", 20.0))
    ids = by_id(parts)
    sp = ids.get("spring")
    if sp is None:
        return [Check("dimensions", "lò xo", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(sp)
    v = eng(sp.meshes[0][0].vertices)                               # thân vòng xoắn (shape đầu tiên; móc/chân là shape sau)
    ctr = (v.min(axis=0) + v.max(axis=0)) / 2
    out = [dim("đường kính ngoài", float(2 * radial(v, ctr, "z").max()), OD, 0.005, 0.03)]
    # mặt cắt nửa phẳng x > 0, y ≈ 0: mỗi vòng dây cắt một lần → đếm vòng, đo bước và đường kính dây
    slab = K.box(OD, 0.02, (hi[2] - lo[2]) * 3 + 10).translate(ctr[0] + OD / 2, ctr[1], ctr[2])
    cut = sp.solid & slab
    comps = sorted(cut.split_components(), key=lambda s: s.bounds()[0][2]) if not cut.is_empty else []
    zs = [(c.bounds()[0][2] + c.bounds()[1][2]) / 2 for c in comps]
    wd = [c.bounds()[1][0] - c.bounds()[0][0] for c in comps]
    out.append(dim("đường kính dây (đo mặt cắt)", float(np.median(wd)) if wd else None, d, 0.01, 0.02))
    if kind == "compression":
        L0 = float(p.get("free_length_mm") or 50.0)
        out.append(dim("chiều dài tự do L0", float(hi[2] - lo[2]), L0, 0.003, 0.05))
        n = float(p.get("active_coils", 8.0))
        ends = p.get("ends", "ground")
        extra = {"ground": 2 * d, "closed": 3 * d, "open": d}[ends]
        pch = (L0 - extra) / n
        if len(zs) >= 4:
            dz = np.diff(zs)
            act = dz[dz > 1.2 * d] if ends != "open" else dz
            out.append(dim("bước vòng làm việc (đo)", float(np.median(act)) if len(act) else None, pch, 0.01, 0.03))
            want_total = n + (0 if ends == "open" else 2)
            out.append(Check("dimensions", "số vòng tổng (đếm vết cắt dây)", abs(len(zs) - want_total) <= 1.0,
                             f"đếm {len(zs)} / ≈ {want_total:g}", 2.0, True))
    elif kind == "extension":
        L0 = float(p.get("free_length_mm") or 50.0)
        tot_lo = min(solid_bounds(x)[0][2] for x in parts)
        tot_hi = max(solid_bounds(x)[1][2] for x in parts)
        out.append(dim("chiều dài tự do kể cả móc", float(tot_hi - tot_lo), L0, 0.005, 0.1))
        out.append(count_check("số móc (khối dây liền thân)", len(sp.meshes) - 1, 2))
        if len(zs) >= 4:
            out.append(dim("bước thân (quấn khít = d)", float(np.median(np.diff(zs))), d, 0.02, 0.02))
    else:
        out.append(count_check("số chân lò xo xoắn (khối dây liền thân)", len(sp.meshes) - 1, 2))
    return out


def principal_extent(v: np.ndarray) -> tuple[float, np.ndarray]:
    """Chiều dài dọc trục chính (PCA) của đám đỉnh và vector trục."""
    c = v - v.mean(axis=0)
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    ax = vt[0]
    proj = c @ ax
    return float(proj.max() - proj.min()), ax


@register("robot_arm")
def _robot_arm(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    R_ = float(p.get("reach_mm", 850.0))
    ids = by_id(parts)
    out: list[Check] = []
    for pid, key, name in (("upper_arm", "a2", "cánh tay trên a2 (tâm J2 → J3)"), ("forearm", "a3", "cẳng tay a3 (tâm J3 → J4)")):
        pd = ids.get(pid)
        if pd is None:
            out.append(Check("dimensions", name, False, "thiếu", 2.0, True))
            continue
        tube = eng(pd.meshes[0][0].vertices)
        ext, _ = principal_extent(tube)
        want = S.UR_RATIOS[key] * R_
        if spec.params.get("style", "cobot") == "cobot":
            out.append(dim(name, ext, want, 0.01, 1.0))
    joints = [pd for pd in parts if pd.part.joint_axis is not None]
    out.append(count_check("số khớp quay (J1…J6)", len(joints), 6))
    fl = ids.get("tool_flange")
    if fl is not None:
        code = S.tool_flange_for(float(p.get("payload_kg", 5.0)))
        t = S.ISO9409[code]
        v = eng_vertices(fl)
        c = v - v.mean(axis=0)
        _, _, vt = np.linalg.svd(c, full_matrices=False)
        nrm = vt[2]                                            # pháp tuyến đĩa (phương sai nhỏ nhất)
        R = K.align_matrix(nrm, (0, 0, 1))
        s0 = fl.solid.transform(K.affine(R))
        lo0, hi0 = s0.bounds()
        s = s0.translate(*(-(lo0 + hi0) / 2))                   # tâm hộp bao = tâm bích (vành ngoài tròn đối xứng)
        lo, hi = s.bounds()
        ring = K.cylinder(t["pcd"] / 2 + 0.05, 0.3, segments=256) - K.cylinder(t["pcd"] / 2 - 0.05, 2, segments=256).translate(0, 0, -1)
        cut = s & ring.translate(0, 0, lo[2] + 0.5)
        n = 0 if cut.is_empty else len(cut.split_components())
        out.append(count_check(f"ISO 9409-1-{code}: số lỗ trên vòng Ø{t['pcd']:g} (+1 lỗ chốt)", n, t["n"] + 1))
        pils = []
        for zc in (lo[2] + 1.0, hi[2] - 1.0):                  # mặt có lỗ định tâm là mặt có lỗ nhỏ nhất quanh tâm
            sec = s & K.box(4 * t["d"], 4 * t["d"], 0.05).translate(0, 0, zc)
            if sec.is_empty:
                continue
            sv = sec.to_mesh().vertices
            r_in = np.hypot(sv[:, 0], sv[:, 1])
            if np.any(r_in > 1.0):
                pils.append(float(2 * r_in[r_in > 1.0].min()))
        out.append(dim(f"ISO 9409-1: lỗ định tâm Ø{t['pilot']:g} H7", min(pils) if pils else None, t["pilot"], 0.01, 0.2))
    base = ids.get("base")
    if base is not None:
        out.append(shape("đế đặt trên mặt đất", abs(float(solid_bounds(base)[0][2])) < 1e-3, ""))
    return out


GROUND.update({"robot_vacuum": {"wheel", "caster"}, "agv": {"wheel", "caster"}})


@register("robot_vacuum")
def _robot_vacuum(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    Dm = float(p.get("diameter_mm", 350.0))
    ids = by_id(parts)
    ch = ids.get("chassis")
    if ch is None:
        return [Check("dimensions", "khung gầm", False, "thiếu", 2.0, True)]
    robot = [pd for pd in parts if pd.part.id not in ("dock",)]
    lo = np.min([solid_bounds(pd)[0] for pd in robot if pd.part.category not in ("brush",)], axis=0)
    hi = np.max([solid_bounds(pd)[1] for pd in robot if pd.part.category not in ("brush",)], axis=0)
    out = [dim("đường kính thân", float(max(hi[0] - lo[0], hi[1] - lo[1])), Dm, 0.005, 0.2),
           shape("chiều cao ≤ 0,31·D (lọt gầm giường/sofa)", (hi[2] - lo[2]) <= 0.31 * Dm, f"{hi[2] - lo[2]:.1f} mm")]
    wheels = [pd for pd in parts if pd.part.category == "wheel"]
    out.append(count_check("số bánh chủ động", len(wheels), 2))
    if len(wheels) == 2:
        ys = [float(eng(w.meshes[0][0].vertices)[:, 1].mean()) for w in wheels]     # tâm lốp (shape đầu tiên)
        cy = float((solid_bounds(ch)[0][1] + solid_bounds(ch)[1][1]) / 2)
        out.append(shape("bánh chủ động đối xứng hai bên", abs((ys[0] - cy) + (ys[1] - cy)) < 0.5, f"{ys}"))
    lens = next((m for m, mt in ch.meshes if getattr(mt, "id", "") == "glass_tinted"), None)
    n_cliff = len(mesh_components(lens)) if lens is not None else 0
    out.append(Check("dimensions", "cảm biến chống rơi (đếm trên đáy)", n_cliff >= 4, f"{n_cliff}", 1.0, True))
    if p.get("lidar", True):
        li = ids.get("lidar")
        top = max(float(solid_bounds(pd)[1][2]) for pd in robot)
        out.append(shape("tháp LiDAR là điểm cao nhất", li is not None and abs(float(solid_bounds(li)[1][2]) - top) < 0.5, ""))
    out.append(shape("chổi cạnh", len([pd for pd in parts if pd.part.id.startswith("side_brush")]) == int(p.get("side_brushes", 1)), ""))
    return out


@register("agv")
def _agv(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    L = float(p.get("length_mm", 900.0))
    ids = by_id(parts)
    shell = ids.get("body_shell")
    if shell is None:
        return [Check("dimensions", "vỏ thân", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(shell)
    out = [dim("chiều dài thân", float(hi[0] - lo[0]), L, 0.005, 0.5), dim("chiều rộng thân (0,8·L)", float(hi[1] - lo[1]), 0.8 * L, 0.01, 0.5,
                                                                          critical=False)]
    wheels = by_cat(parts, "wheel")
    casters = by_cat(parts, "caster")
    if p.get("drive", "differential") == "mecanum":
        out.append(count_check("4 bánh mecanum", len(wheels), 4))
        rol = next((m for m, mt in wheels[0].meshes if getattr(mt, "id", "") == "polyurethane"), None) if wheels else None
        n_r = len(mesh_components(rol)) if rol is not None else 0
        out.append(count_check("số con lăn mỗi bánh mecanum (đếm)", n_r, 10))
    else:
        out.append(count_check("2 bánh chủ động (vi sai)", len(wheels), 2))
        out.append(count_check("4 bánh xoay", len(casters), 4))
    es = ids.get("estop")
    red = next((m for m, mt in es.meshes if getattr(mt, "id", "") == "paint_red"), None) if es else None
    n_red = sum(len(mesh_components(m)) for m, mt in (es.meshes if es else []) if getattr(mt, "id", "") == "paint_red")
    out.append(count_check("nút dừng khẩn cấp (đếm nấm đỏ)", n_red if red is not None else 0, 2))
    if p.get("lidar", True):
        out.append(count_check("máy quét laser an toàn", len(by_cat(parts, "lidar")), 2))
    top = ids.get(meta.get("top_part", ""))
    if top is not None:
        zmax = max(float(solid_bounds(pd)[1][2]) for pd in parts)
        out.append(shape("đầu nâng/thùng hàng ở trên cùng", abs(float(solid_bounds(top)[1][2]) - zmax) < 0.05 * L + 1, ""))
    return out


@register("cubesat")
def _cubesat(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    U = int(spec.params.get("units", 3))
    X, Y, Z = S.CUBESAT[U]
    ids = by_id(parts)
    fr = ids.get("frame")
    if fr is None:
        return [Check("dimensions", "khung", False, "thiếu", 2.0, True)]
    rails_mesh = eng(fr.meshes[0][0].vertices)
    lo, hi = rails_mesh.min(axis=0), rails_mesh.max(axis=0)
    out = [dim(f"CubeSat {U}U: kích thước X (CDS rev.14)", float(hi[0] - lo[0]), X, 0.001, 0.1),
           dim(f"CubeSat {U}U: kích thước Y", float(hi[1] - lo[1]), Y, 0.001, 0.1),
           dim(f"CubeSat {U}U: chiều cao Z dọc ray", float(hi[2] - lo[2]), Z, 0.001, 0.1)]
    zc = (lo[2] + hi[2]) / 2
    sec = fr.solid & K.box(3 * X, 3 * Y, 0.1).translate((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, zc + 7.0)
    comps = sec.split_components() if not sec.is_empty else []
    rails = [c for c in comps if 5 < min(c.bounds()[1][0] - c.bounds()[0][0], c.bounds()[1][1] - c.bounds()[0][1])
             and max(c.bounds()[1][0] - c.bounds()[0][0], c.bounds()[1][1] - c.bounds()[0][1]) < 12]
    out.append(count_check("số ray góc (cắt ngang thân)", len(rails), 4))
    if rails:
        w = float(np.mean([c.bounds()[1][0] - c.bounds()[0][0] for c in rails]))
        out.append(dim("bề rộng ray góc (≥ 6,5 mm tiếp xúc)", w, S.CUBESAT_RAIL["width"], 0.01, 0.05))
    return out


@register("launch_vehicle")
def _launch_vehicle(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    Ht, Dm = float(p.get("height_mm", 70000.0)), float(p.get("diameter_mm", 3700.0))
    lo = np.min([solid_bounds(pd)[0] for pd in parts], axis=0)
    hi = np.max([solid_bounds(pd)[1] for pd in parts], axis=0)
    out = [dim("chiều cao toàn bộ", float(hi[2] - lo[2]), Ht, 0.005, 1.0)]
    ids = by_id(parts)
    s1 = ids.get("stage_1")
    if s1 is not None:
        v = eng(s1.meshes[0][0].vertices)
        c = (v.min(axis=0) + v.max(axis=0)) / 2
        out.append(dim("đường kính thân", float(2 * np.percentile(radial(v, c, "z"), 50)), Dm, 0.01, 1.0))
    out.append(count_check("số tầng", len(by_cat(parts, "stage")), int(p.get("stages", 2))))
    e1 = ids.get("engines_1")
    if e1 is not None:
        bells = next((m for m, mt in e1.meshes if getattr(mt, "id", "") == "copper"), None)
        out.append(count_check("số động cơ tầng 1 (đếm vòi phun)", len(mesh_components(bells)) if bells is not None else 0, 9))
    fair = by_cat(parts, "fairing")
    out.append(count_check("chóp mũi hai nửa", len(fair), 2))
    return out


GROUND.update({"train": {"track"}})


@register("train")
def _train(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    G = S.RAIL_GAUGE[p.get("gauge", "meter")]
    rp = S.RAIL_PROFILE[p.get("gauge", "meter")]
    ids = by_id(parts)
    tr = ids.get("track")
    out: list[Check] = []
    if tr is None:
        return [Check("dimensions", "đường ray", False, "thiếu", 2.0, True)]
    rails = next((m for m, mt in tr.meshes if getattr(mt, "id", "") == "steel"), None)
    if rails is not None:
        v = eng(rails.vertices)
        z_head = float(v[:, 2].max()) - 0.25 * rp["height"]           # mức đo khổ: dưới đỉnh ray ~ 1/4 chiều cao ray
        lo, hi = v.min(axis=0), v.max(axis=0)
        iv = probe_intervals(tr.solid & K.box(1e6, 1e6, 0.5).translate(0, 0, z_head), "y", ((lo[0] + hi[0]) / 2, 0, z_head))
        heads = [q for q in iv if q[1] - q[0] < rp["head"] * 1.2]
        if len(heads) >= 2:
            inner = heads[-1][0] - heads[0][1]
            out.append(dim(f"khổ đường (mép trong hai nấm ray) — khổ {G:g}", inner, G, 0.002, 1.0))
        else:
            out.append(dim("khổ đường", None, G))
    ws = by_cat(parts, "wheelset")
    n_cars = 1 + int(p.get("wagons", 2))
    out.append(count_check("số bộ trục bánh (2 bogie × 2 trục mỗi xe)", len(ws), 4 * n_cars))
    out.append(count_check("số bogie", len(by_cat(parts, "bogie")), 2 * n_cars))
    out.append(count_check("số móc nối", len(by_cat(parts, "coupler")), 2 * n_cars))
    if p.get("traction", "diesel") == "electric":
        out.append(shape("có cần lấy điện + dây tiếp xúc", "pantograph" in ids and "catenary" in ids, ""))
    return out


GROUND.update({"fixed_wing": {"landing_gear"}})


def _slab_y(solid: K.Solid, y: float) -> K.Solid:
    lo, hi = solid.bounds()
    big = float(np.max(hi - lo)) * 3 + 10.0
    return solid & K.box(big, 0.5, big).translate(float((lo[0] + hi[0]) / 2), y, float((lo[2] + hi[2]) / 2))


@register("fixed_wing")
def _fixed_wing(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    b = float(p["wingspan_mm"])
    dih = float(p.get("dihedral_deg", 3.0))
    ids = by_id(parts)
    wing = ids.get("wing")
    if wing is None:
        return [Check("dimensions", "cánh chính", False, "thiếu", 2.0, True)]
    ails = [pd for pd in parts if pd.part.id.startswith("aileron_")]
    ws = [wing] + ails
    lo = np.min([solid_bounds(pd)[0] for pd in ws], axis=0)
    hi = np.max([solid_bounds(pd)[1] for pd in ws], axis=0)
    yc = float((lo[1] + hi[1]) / 2)
    out = [dim("sải cánh (chiếu, đầu cánh tới đầu cánh)", float(hi[1] - lo[1]), b, 0.003, 1.0)]
    zs = []
    for eta in (0.2, 0.5):
        sec = _slab_y(wing.solid, yc + eta * b / 2)
        if sec.is_empty:
            zs.append(None)
            continue
        a, c = sec.bounds()
        zs.append(float((a[2] + c[2]) / 2))
    if None not in zs:
        got = math.degrees(math.atan2(zs[1] - zs[0], 0.3 * b / 2))
        out.append(Check("dimensions", "góc nhị diện cánh", abs(got - dih) <= 0.5, f"đo {got:.2f}° / yêu cầu {dih:g}°", 2.0, True))
    sec = _slab_y(wing.solid, yc + 0.3 * b / 2)
    if not sec.is_empty:
        a, c = sec.bounds()
        chord = float(c[0] - a[0])
        th = 0.0
        for x in np.linspace(a[0] + 0.05 * chord, c[0] - 0.05 * chord, 25):
            for lo_, hi_ in probe_intervals(sec, "z", (x, yc + 0.3 * b / 2, 0.0)):
                th = max(th, hi_ - lo_)
        foil = str(meta.get("airfoil", "NACA 2412"))[-2:]
        out.append(dim(f"độ dày tương đối biên dạng ({meta.get('airfoil', 'NACA')})", th / chord, int(foil) / 100.0, 0.05, 0.002,
                       unit="", critical=True))
    out.append(count_check("aileron hai bên (tách riêng)", len(ails), 2))
    surfaces = {pd.part.id for pd in parts if pd.part.category == "control_surface"}
    if p.get("tail", "conventional") == "v_tail":
        out.append(shape("cánh lái đuôi V hai bên", {"ruddervator_left", "ruddervator_right"} <= surfaces, ""))
    else:
        out.append(shape("có elevator + rudder tách riêng", {"elevator", "rudder"} <= surfaces, ""))
    pr = ids.get("propeller")
    if pr is not None:
        v = eng(pr.meshes[0][0].vertices)
        c = (v.min(axis=0) + v.max(axis=0)) / 2
        R = float(radial(v, c, "x").max())
        span = float(v[:, 0].max() - v[:, 0].min()) + 2.0
        nb = ring_count(pr.solid, c, "x", 0.7 * R, -span, span, thickness=0.2)
        out.append(count_check("số lá cánh quạt (đếm ở 0,7 R)", nb, int(meta.get("prop_blades", 2))))
        clear = float(c[2] - R - float(np.min([solid_bounds(pd)[0][2] for pd in parts])))
        need = float(meta.get("prop_clearance_min_mm", 0.0))
        out.append(Check("dimensions", f"khoảng hở đầu cánh quạt – mặt đất ≥ {need:.0f} mm", clear >= need * 0.98, f"đo {clear:.0f} mm", 1.0, True))
    if p.get("aircraft_type") == "vtol":
        out.append(count_check("4 rotor nâng", len([pd for pd in parts if pd.part.id.startswith("lift_prop_")]), 4))
        out.append(count_check("2 dầm rotor", len(by_cat(parts, "boom")), 2))
    return out


GROUND.update({"car": {"wheel"}})


@register("car")
def _car(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    body = ids.get("body")
    if body is None:
        return [Check("dimensions", "thân xe", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(body)                                        # thân + kính + đèn (gương nằm trên cửa)
    ground = float(np.min([solid_bounds(pd)[0][2] for pd in parts]))
    out = [dim("chiều dài toàn bộ", float(hi[0] - lo[0]), float(meta["length_mm"]), 0.005, 1.0),
           dim("chiều rộng thân (không gương)", float(hi[1] - lo[1]), float(meta["width_mm"]), 0.01, 1.0),
           dim("chiều cao toàn bộ (từ mặt đất)", float(hi[2] - ground), float(meta["height_mm"]), 0.01, 1.0)]
    wheels = by_cat(parts, "wheel")
    out.append(count_check("4 bánh xe", len(wheels), 4))
    if len(wheels) == 4:
        cs_ = []
        for w in wheels:
            v = eng(w.meshes[0][0].vertices)                           # lốp
            cs_.append(((v.min(axis=0) + v.max(axis=0)) / 2, float(v[:, 2].max() - v[:, 2].min())))
        xs = sorted({round(float(c[0]), 0) for c, _ in cs_})
        out.append(dim("chiều dài cơ sở (tâm bánh trước – sau)", xs[-1] - xs[0], float(meta["wheelbase_mm"]), 0.002, 1.0))
        ys = [float(c[1]) for c, _ in cs_]
        out.append(dim("vệt bánh (tâm bánh trái – phải)", (max(ys) - min(ys)), float(meta["track_mm"]), 0.003, 1.0))
        out.append(dim(f"đường kính lốp {meta.get('tire', '')}", float(np.mean([d for _, d in cs_])), float(meta["tire_d_mm"]), 0.005, 1.0))
    out.append(count_check("4 cửa tách rời", len(by_cat(parts, "door")), int(meta.get("doors", 4))))
    n_cal = sum(len(mesh_components(m)) for pd in by_cat(parts, "suspension") for m, mt in pd.meshes if getattr(mt, "id", "") == "paint_red")
    out.append(count_check("heo phanh đĩa (đếm)", n_cal, 4))
    out.append(count_check("số motor", len(by_cat(parts, "motor")), 2 if meta.get("drive") == "awd" else 1))
    bat = ids.get("battery_pack")
    if bat is not None:
        vb = eng(bat.meshes[0][0].vertices)                            # khối pin (không tính cáp cao áp)
        bl, bh = vb.min(axis=0), vb.max(axis=0)
        out.append(shape("pin nằm dưới sàn, giữa hai trục", bh[2] < 0.25 * float(meta["height_mm"]) and len(wheels) == 4 and
                         min(float(c[0]) for c, _ in cs_) < bl[0] and bh[0] < max(float(c[0]) for c, _ in cs_), ""))
    return out


GROUND.update({"motorbike": {"wheel"}})


@register("motorbike")
def _motorbike(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    wf, wr = ids.get("wheel_front"), ids.get("wheel_rear")
    out.append(count_check("2 bánh xe", len(by_cat(parts, "wheel")), 2))
    if wf is None or wr is None:
        return out
    cen = {}
    for key, w in (("front", wf), ("rear", wr)):
        v = eng(w.meshes[0][0].vertices)                               # lốp
        cen[key] = ((v.min(axis=0) + v.max(axis=0)) / 2, float(v[:, 2].max() - v[:, 2].min()))
    out.append(dim("chiều dài cơ sở", float(cen["front"][0][0] - cen["rear"][0][0]), float(meta["wheelbase_mm"]), 0.003, 1.0))
    out.append(dim("đường kính lốp trước (ký hiệu ISO)", cen["front"][1], float(meta["front_tire_d_mm"]), 0.005, 1.0))
    out.append(dim("đường kính lốp sau (ký hiệu ISO)", cen["rear"][1], float(meta["rear_tire_d_mm"]), 0.005, 1.0))
    fk = ids.get("fork")
    if fk is not None:
        v = eng(fk.meshes[0][0].vertices)                              # hai ống phuộc song song trục lái
        _, ax = principal_extent(v[v[:, 1] > np.median(v[:, 1])])
        rake = math.degrees(math.acos(min(1.0, abs(float(ax[2])))))
        out.append(Check("dimensions", "góc caster (phuộc so với phương đứng)", abs(rake - float(meta["rake_deg"])) <= 1.0,
                         f"đo {rake:.1f}° / thiết kế {meta['rake_deg']:g}°", 2.0, True))
    out.append(shape("vệt quét (trail) dương — xe tự cân bằng hướng", float(meta.get("trail_mm", 0)) > 0, f"{meta.get('trail_mm', 0):.0f} mm"))
    st = ids.get("seat")
    if st is not None:
        v = eng(st.meshes[0][0].vertices)
        out.append(dim("chiều cao yên", float(v[:, 2].max()) - float(np.min([solid_bounds(pd)[0][2] for pd in parts])),
                       float(meta["seat_height_mm"]), 0.03, 5.0, critical=False))
    need = {"motorcycle": ["engine", "fuel_tank", "exhaust", "chain", "swingarm", "rear_shock"],
            "scooter": ["engine", "body_panels", "rear_shock"], "ebike": ["battery", "crankset", "chain"]}[meta.get("bike_type", "motorcycle")]
    miss = [k for k in need if k not in ids]
    out.append(shape("đủ cụm đặc trưng loại xe", not miss, ", ".join(miss)))
    return out


def pin_checks(parts: Sequence[Any], meta: dict) -> list[Check]:
    """Mỗi khớp chốt khai trong metadata "pin_links" [(tên, tâm, [bộ phận…])]: mọi bộ phận nối phải CÓ vật liệu tại tâm
    chốt (mắt xi lanh thật sự ôm chốt của cần/khung) — đo bằng giao khối cầu nhỏ, không đọc số."""
    ids = by_id(parts)
    links = meta.get("pin_links") or []
    bad = []
    for name, c, pids in links:
        probe = K.sphere(3.0, segments=12).translate(*c)
        for pid in pids:
            pd = ids.get(pid)
            if pd is None or pd.solid is None or (pd.solid & probe).is_empty:
                bad.append(f"{name}:{pid}")
    if not links:
        return []
    return [Check("dimensions", f"xi lanh thủy lực lắp đúng chốt ({len(links)} khớp)", not bad, ", ".join(bad[:6]) or "đủ", 2.0, True)]


def ram_checks(meta: dict) -> list[Check]:
    """Chiều dài chốt–chốt của mỗi xi lanh nằm trong [đóng hết, đóng + hành trình] (cần piston không vượt hành trình)."""
    pts: dict[str, list] = {}
    for name, c, pids in meta.get("pin_links") or []:
        pts.setdefault(pids[0], []).append(np.asarray(c, float))
    bad = []
    for rid, (closed, stroke) in (meta.get("rams") or {}).items():
        ps = pts.get(rid, [])
        if len(ps) != 2:
            bad.append(f"{rid}: thiếu chốt")
            continue
        L = float(np.linalg.norm(ps[1] - ps[0]))
        if not closed - 1.0 <= L <= closed + stroke + 1.0:
            bad.append(f"{rid}: {L:.0f} ∉ [{closed:.0f}, {closed + stroke:.0f}]")
    if not meta.get("rams"):
        return []
    return [Check("dimensions", "xi lanh trong hành trình (đóng ≤ chốt–chốt ≤ đóng + hành trình)", not bad, "; ".join(bad) or "đạt", 2.0, True)]


def pin_centers(pd: Any, material: str = "steel") -> list[np.ndarray]:
    """Tâm các chốt (thành phần rời của lưới vật liệu `material`) — hệ kỹ thuật."""
    return [(e.min(axis=0) + e.max(axis=0)) / 2 for m, mt in pd.meshes if getattr(mt, "id", "") == material
            for e in (eng(c) for c in mesh_components(m))]


GROUND.update({"excavator": {"track"}})


@register("excavator")
def _excavator(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    tr = [ids.get("track_left"), ids.get("track_right")]
    out.append(count_check("2 dải xích", len([t for t in tr if t is not None]), 2))
    if None not in tr:
        cs_ = [eng(t.meshes[0][0].vertices) for t in tr]
        ys = [float((v[:, 1].min() + v[:, 1].max()) / 2) for v in cs_]
        out.append(dim("khoảng cách tâm hai dải xích", abs(ys[0] - ys[1]), float(meta["track_gauge_mm"]), 0.003, 1.0))
        out.append(dim("bề rộng guốc xích", float(cs_[0][:, 1].max() - cs_[0][:, 1].min()), float(meta["shoe_width_mm"]), 0.01, 1.0))
    sc = np.asarray(meta.get("swing_center", [0, 0, 0]), float)
    boom, stick = ids.get("boom"), ids.get("stick")
    if boom is not None and stick is not None:
        bp = pin_centers(boom)
        pairs = [(float(np.linalg.norm(a - c)), a, c) for i, a in enumerate(bp) for c in bp[i + 1:]]
        Lb, a, c = max(pairs, key=lambda q: q[0])
        T = a if np.hypot(*(a - sc)[:2]) > np.hypot(*(c - sc)[:2]) else c
        out.append(dim("chiều dài cần (chốt chân cần – chốt đầu cần)", Lb, float(meta["boom_length_mm"]), 0.003, 2.0))
        sp = pin_centers(stick)
        Ls = max(float(np.linalg.norm(q - T)) for q in sp) if sp else None
        out.append(dim("chiều dài tay gầu (chốt đầu cần – chốt gầu)", Ls, float(meta["stick_length_mm"]), 0.003, 2.0))
    up = ids.get("upper_structure")
    if up is not None:
        cw = eng(up.meshes[1][0].vertices)                             # đối trọng
        r = float(np.hypot(cw[:, 0] - sc[0], cw[:, 1] - sc[1]).max())
        out.append(dim("bán kính quay đuôi (đối trọng)", r, float(meta["tail_swing_radius_mm"]), 0.01, 2.0))
    out.append(count_check("số xi lanh thủy lực", len(by_cat(parts, "hydraulic_cylinder")), 4))
    return out + pin_checks(parts, meta) + ram_checks(meta)


GROUND.update({"forklift": {"wheel"}})


@register("forklift")
def _forklift(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    forks = [ids.get("fork_left"), ids.get("fork_right")]
    out.append(count_check("2 càng nâng", len([f for f in forks if f is not None]), 2))
    ground = float(np.min([solid_bounds(pd)[0][2] for pd in parts]))
    if forks[0] is not None:
        f = forks[0].solid
        lo, hi = f.bounds()
        xt = float(hi[0] - 0.4 * float(meta["fork_length_mm"]))       # mặt cắt giữa lưỡi càng
        sec = f & K.box(1.0, 1e5, 1e5).translate(xt, 0, 0)
        a, c = sec.bounds()
        out.append(dim("bề dày càng (ISO 2331)", float(c[2] - a[2]), float(meta["fork_thickness_mm"]), 0.01, 0.3))
        out.append(dim("bề rộng càng (ISO 2331)", float(c[1] - a[1]), float(meta["fork_width_mm"]), 0.01, 0.3))
        out.append(dim("cao độ mặt trên càng", float(c[2] - ground), float(meta["fork_height_mm"]), 0.005, 2.0))
        shank = f & K.box(1e5, 1e5, 2.0).translate(0, 0, float(c[2]) + 60.0)   # mặt cắt thân càng ngay trên lưỡi
        heel = float(shank.bounds()[1][0])
        out.append(dim("chiều dài lưỡi càng (từ mặt trước thân càng)", float(hi[0] - heel), float(meta["fork_length_mm"]), 0.005, 2.0))
    car = ids.get("carriage")
    if car is not None:
        v = eng(car.meshes[0][0].vertices)
        plate = v[v[:, 0] < v[:, 0].min() + 61.0]                          # tấm giá càng (không tính tấm chắn tải)
        zs = np.sort(np.unique(np.round(plate[:, 2], 1)))
        out.append(Check("dimensions", f"chiều cao giá càng ISO 2328 cấp {meta.get('carriage_class')}",
                         any(abs((zs[j] - zs[0]) - float(meta["carriage_height_mm"])) < 1.0 for j in range(len(zs))),
                         f"chuẩn {meta['carriage_height_mm']:g} mm", 2.0, True))
    out.append(count_check("số tầng khung nâng", len(by_cat(parts, "mast")), int(meta.get("mast_stages", 2))))
    out.append(count_check("4 bánh xe", len(by_cat(parts, "wheel")), 4))
    og, op = ids.get("overhead_guard"), ids.get("operator")
    if og is not None and op is not None:
        out.append(shape("khung bảo vệ che trên ghế lái", solid_bounds(og)[1][2] > solid_bounds(op)[1][2] + 300.0, ""))
    return out + pin_checks(parts, meta) + ram_checks(meta)


GROUND.update({"crane": {"wheel", "outrigger"}})


@register("crane")
def _crane(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    booms = [pd for pd in parts if pd.part.category == "boom"]
    tt = ids.get("turntable")
    if not booms or tt is None:
        return [Check("dimensions", "cần + bàn quay", False, "thiếu", 2.0, True)]
    foot_meta = np.asarray(meta["boom_foot"], float)
    foot = min(pin_centers(tt), key=lambda c: float(np.linalg.norm(c - foot_meta)))
    top = booms[-1]
    sh = pin_centers(top)                                              # 2 puly đầu cần
    if sh:
        head = np.mean(sh, axis=0)
        v = head - foot
        out.append(dim("chiều dài cần (chốt chân → tâm puly đầu cần)", float(np.linalg.norm(v)), float(meta["boom_length_mm"]), 0.003, 5.0))
        got = math.degrees(math.atan2(v[2], math.hypot(v[0], v[1])))
        out.append(Check("dimensions", "góc nâng cần", abs(got - float(meta["boom_angle_deg"])) <= 0.3, f"đo {got:.2f}° / {meta['boom_angle_deg']:g}°", 2.0, True))
        d = v / np.linalg.norm(v)
        iv = []
        for pd in booms:
            s_ = eng(pd.meshes[0][0].vertices) @ d
            iv.append((float(s_.min()), float(s_.max())))
        ov = min(min(iv[i - 1][1], iv[i][1]) - max(iv[i - 1][0], iv[i][0]) for i in range(1, len(iv)))
        out.append(Check("dimensions", "đoạn ống lồng chồng nhau ≥ 1000 mm (đo dọc trục cần)", ov >= 999.0, f"nhỏ nhất {ov:.0f} mm", 2.0, True))
    out.append(count_check("số đoạn cần", len(booms), int(meta.get("sections", len(booms)))))
    out.append(count_check("4 chân chống", len(by_cat(parts, "outrigger")), 4))
    out.append(count_check("số bánh (2 × số trục)", len(by_cat(parts, "wheel")), 2 * int(meta.get("axles", 3))))
    rope = ids.get("hoist_rope")
    if rope is not None:
        comps = mesh_components(rope.meshes[0][0])
        vert = [c for c in comps if np.ptp(eng(c)[:, 2]) > 20 * max(np.ptp(eng(c)[:, 0]), np.ptp(eng(c)[:, 1]))]
        out.append(count_check("nhánh cáp thả thẳng đứng xuống móc", len(vert), 2))
    return out + pin_checks(parts, meta) + ram_checks(meta)


def double_angle_section(pd: Any, x: float) -> dict | None:
    """Mặt cắt thanh 2L tại hoành độ x (thanh nằm dọc X): cạnh L, dày t, khe bản mã g (dò tia dọc Y ở giữa cánh đứng)."""
    s = pd.solid
    sec = s & K.box(0.5, 1e6, 1e6).translate(x, 0, 0)
    if sec.is_empty:
        return None
    lo, hi = sec.bounds()
    Lz = float(hi[2] - lo[2])
    zc = (lo[2] + hi[2]) / 2
    iv = probe_intervals(sec, "y", (x, 0.0, zc))
    if len(iv) != 2:
        return None
    return {"L": Lz, "t": float(np.mean([b - a for a, b in iv])), "g": float(iv[1][0] - iv[0][1]), "width": float(hi[1] - lo[1])}


GROUND.update({"steel_truss": {"foundation"}})


@register("steel_truss")
def _steel_truss(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    col = ids.get("columns")
    if col is not None:
        cs_ = [eng(c) for c in mesh_components(col.meshes[0][0])]
        xs = sorted(float((v[:, 0].min() + v[:, 0].max()) / 2) for v in cs_)
        out.append(dim("nhịp giàn (tâm cột – tâm cột)", xs[-1] - xs[0] if len(xs) >= 2 else None, float(meta["span_mm"]), 0.002, 1.0))
    bc, tc = ids.get("bottom_chord"), ids.get("top_chord")
    if bc is not None and tc is not None:
        out.append(dim("chiều cao giàn (mép dưới cánh dưới → mép trên cánh trên)",
                       float(solid_bounds(tc)[1][2] - solid_bounds(bc)[0][2]), float(meta["height_mm"]), 0.005, 2.0))
        lo, hi = solid_bounds(bc)
        # giữa khoang đầu tiên (không có bản mã)
        span = float(meta["span_mm"])
        x = float(lo[0]) + 0.5 * span / max(int(meta.get("panels", 4)), 3)
        sec = double_angle_section(bc, x)
        L, t = meta["chord_section"]
        if sec is None:
            out.append(Check("dimensions", "tiết diện thanh cánh 2L", False, "không cắt được", 2.0, True))
        else:
            out.append(dim(f"cạnh thép góc thanh cánh L{L:g}", sec["L"], float(L), 0.01, 0.3))
            out.append(dim(f"bề dày thép góc thanh cánh t{t:g}", sec["t"], float(t), 0.02, 0.2))
            out.append(dim("khe kẹp bản mã giữa hai thép góc", sec["g"], float(meta["gusset_t_mm"]), 0.02, 0.2))
    gus, bolts = ids.get("gussets"), ids.get("bolts")
    if gus is not None and bolts is not None:
        plates = [eng(c) for c in mesh_components(gus.meshes[0][0])]
        heads = [eng(c) for c in mesh_components(bolts.meshes[0][0])]
        hc = np.array([(h.min(axis=0) + h.max(axis=0)) / 2 for h in heads]) if heads else np.zeros((0, 3))
        per = []
        for v in plates:
            lo, hi = v.min(axis=0), v.max(axis=0)
            per.append(int(np.sum(np.all((hc[:, [0, 2]] >= lo[[0, 2]] - 1) & (hc[:, [0, 2]] <= hi[[0, 2]] + 1), axis=1))) if len(hc) else 0)
        out.append(count_check("số bản mã (mọi nút có ≥ 2 thanh)", len(plates), int(meta["n_gussets"])))
        out.append(Check("dimensions", "mỗi bản mã có ≥ 4 bu-lông", bool(per) and min(per) >= 4, f"ít nhất {min(per) if per else 0}", 2.0, True))
        out.append(count_check("tổng số bu-lông", len(heads), int(meta["n_bolts"])))
    return out


GROUND.update({"bridge": {"abutment", "pylon"}})


@register("bridge")
def _bridge(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    kind = meta.get("bridge_type", "truss")
    S = float(meta["span_mm"])
    if kind == "cable_stayed":
        pyl = sorted(float((solid_bounds(pd)[0][0] + solid_bounds(pd)[1][0]) / 2) for pd in by_cat(parts, "pylon"))
        out.append(count_check("2 tháp cầu", len(pyl), 2))
        if len(pyl) == 2:
            out.append(dim("nhịp chính (tâm tháp – tâm tháp)", pyl[1] - pyl[0], S, 0.002, 1.0))
    else:
        br = ids.get("bearings")
        if br is not None:
            xs = sorted({round(float((e[:, 0].min() + e[:, 0].max()) / 2), 0) for e in (eng(c) for c in mesh_components(br.meshes[0][0]))})
            out.append(dim("nhịp (tâm gối – tâm gối)", xs[-1] - xs[0] if len(xs) >= 2 else None, S, 0.002, 1.0))
    deck = ids.get("deck")
    if deck is not None:
        pave = next((m for m, mt in deck.meshes if getattr(mt, "id", "") == "asphalt"), None)
        if pave is not None:
            v = eng(pave.vertices)
            out.append(dim("bề rộng mặt đường (giữa hai gờ)", float(v[:, 1].max() - v[:, 1].min()), float(meta["deck_width_mm"]) - 800.0, 0.005, 1.0))
            z_road = float(v[:, 2].max())
    if kind == "truss":
        bc, tc, st = ids.get("bottom_chord"), ids.get("top_chord"), ids.get("top_struts")
        if bc is not None and tc is not None:
            out.append(dim("chiều cao giàn", float(solid_bounds(tc)[1][2] - solid_bounds(bc)[0][2]), float(meta["truss_height_mm"]), 0.005, 2.0))
        if st is not None and deck is not None:
            clr = float(solid_bounds(st)[0][2]) - z_road
            out.append(Check("dimensions", "tĩnh không dưới thanh chống ≥ 4,75 m", clr >= 4750.0, f"đo {clr:.0f} mm", 2.0, True))
        gus = ids.get("gussets")
        if gus is not None:
            out.append(count_check("số bản mã", len(mesh_components(gus.meshes[0][0])), int(meta["n_gussets"])))
    elif kind == "cable_stayed":
        cab = ids.get("stay_cables")
        if cab is not None:
            comps = [eng(c) for c in mesh_components(cab.meshes[0][0])]
            out.append(count_check("số dây văng", len(comps), int(meta["cables"])))
            cx = float(np.mean([c[:, 0].mean() for c in comps])) if comps else 0.0
            dx = float(np.mean([(solid_bounds(pd)[0][0] + solid_bounds(pd)[1][0]) / 2 for pd in by_cat(parts, "pylon")]))
            out.append(shape("dây văng đối xứng qua giữa cầu", abs(cx - dx) < 0.01 * S, f"lệch {cx - dx:.0f} mm"))
    else:
        ribs, hg = ids.get("arch_ribs"), ids.get("hangers")
        if ribs is not None and deck is not None:
            rise = float(solid_bounds(ribs)[1][2]) - (z_road - 70.0)           # mặt bản = mặt đường − lớp nhựa 70 mm
            out.append(dim("đường tên vòm f (đỉnh sườn – mặt bản)", rise, float(meta["arch_rise_mm"]), 0.01, 5.0))
        if hg is not None:
            comps = [eng(c) for c in mesh_components(hg.meshes[0][0])]
            vert = [c for c in comps if np.ptp(c[:, 2]) > 10 * max(np.ptp(c[:, 0]), np.ptp(c[:, 1]))]
            out.append(count_check("dây treo thẳng đứng", len(vert), int(meta["hangers"])))
    return out


GROUND.update({"lattice_tower": {"foundation"}})


@register("lattice_tower")
def _lattice_tower(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    legs = ids.get("legs")
    if legs is None:
        return [Check("dimensions", "chân tháp", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(legs)
    out.append(dim("chiều cao thân tháp (mặt móng → đỉnh chân)", float(hi[2] - lo[2]), float(meta["height_mm"]), 0.002, 2.0))
    sec = legs.solid & K.box(1e6, 1e6, 2.0).translate(float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), float(lo[2]) + 5.0)
    comps = sec.split_components() if not sec.is_empty else []
    out.append(count_check("số chân tháp (cắt ngang sát móng)", len(comps), int(meta["legs"])))
    if comps:
        a = np.min([c.bounds()[0] for c in comps], axis=0)
        b_ = np.max([c.bounds()[1] for c in comps], axis=0)
        if int(meta["legs"]) == 4:
            out.append(dim("bề rộng chân tháp tại móng", float(b_[0] - a[0]), float(meta["base_width_mm"]), 0.01, 3.0))
        out.append(shape("tỷ lệ bề rộng móng / chiều cao 1/5 – 1/10", 0.1 <= float(b_[0] - a[0]) / float(meta["height_mm"]) <= 0.2, ""))
    if meta.get("tower_type") == "power":
        ins = ids.get("insulators")
        if ins is not None:
            glass = next((m for m, mt in ins.meshes if getattr(mt, "id", "") == "insulator_glass"), None)
            n_disc = len(mesh_components(glass)) if glass is not None else 0
            out.append(count_check("bát cách điện (6 chuỗi × 10 bát, đếm)", n_disc, 60))
        out.append(shape("3 tầng xà mỗi bên", len(meta.get("crossarm_levels", [])) == 3, ""))
    else:
        ant = ids.get("antennas")
        if ant is not None:
            pan = next((m for m, mt in ant.meshes if getattr(mt, "id", "") == "plastic_white"), None)
            out.append(count_check("ăng-ten panel (đếm)", len(mesh_components(pan)) if pan is not None else 0, int(meta.get("antennas", 6))))
        dsh = ids.get("dishes")
        out.append(count_check("chảo viba (đếm)", len(mesh_components(dsh.meshes[0][0])) if dsh is not None else 0, int(meta.get("dishes", 2))))
    bo = ids.get("bolts")
    if bo is not None:
        out.append(count_check("bu-lông liên kết (đếm)", len(mesh_components(bo.meshes[0][0])), int(meta["n_bolts"])))
    return out


GROUND.update({"wind_turbine": {"foundation"}})


@register("wind_turbine")
def _wind_turbine(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    blades = [pd for pd in parts if pd.part.category == "blade"]
    out.append(count_check("số cánh", len(blades), int(meta.get("blades", 3))))
    c = np.asarray(meta["hub_center"], float)
    ax = np.asarray(meta["rotor_axis"], float)
    tips = []
    for pd in blades:
        v = eng_vertices(pd)
        rel = v - c
        rad = np.linalg.norm(rel - np.outer(rel @ ax, ax), axis=1)
        tips.append((float(rad.max()), v[int(np.argmax(rad))]))
    if tips:
        out.append(dim("đường kính rotor (2 × bán kính mũi cánh)", 2 * float(np.mean([t for t, _ in tips])), float(meta["rotor_diameter_mm"]), 0.005, 5.0))
        ground = float(np.min([solid_bounds(pd)[0][2] for pd in parts]))
        zc = float(np.mean([p_[2] for _, p_ in tips])) - ground
        out.append(dim("chiều cao tâm rotor (trung bình cao độ 3 mũi cánh)", zc, float(meta["hub_height_mm"]), 0.005, 5.0))
    b1 = ids.get("blade_1")
    if b1 is not None:
        ang = {}
        r0, span = float(meta["blade_root_r_mm"]), float(meta["blade_span_mm"])
        rows = meta["blade_table"]
        for rr in (0.35, 0.93):                                        # trạm mặt cắt của bảng (tránh nội suy gốc dày)
            z = c[2] + r0 + (rr - rows[0][0]) / (rows[-1][0] - rows[0][0]) * span
            sec = b1.solid & K.box(1e6, 1e6, 1.0).translate(c[0], c[1], z)
            if sec.is_empty:
                continue
            v = sec.to_mesh().vertices
            vv = v[:, :2]
            dmat = np.linalg.norm(vv[:, None, :] - vv[None, :, :], axis=2)
            i, j = np.unravel_index(int(np.argmax(dmat)), dmat.shape)
            dv = vv[j] - vv[i]
            ang[rr] = math.degrees(math.atan2(abs(dv[0]), abs(dv[1])))
        if len(ang) == 2:
            tab = meta["blade_table"]
            rs = [row[0] for row in tab]
            tw = [row[2] for row in tab]
            want = float(np.interp(0.35, rs, tw) - np.interp(0.93, rs, tw))
            got = ang[0.35] - ang[0.93]
            out.append(Check("dimensions", "độ xoắn cánh (trạm 0,35 R → 0,93 R)", abs(got - want) <= 1.0, f"đo {got:.1f}° / thiết kế {want:.1f}°", 2.0, True))
    tw_ = ids.get("tower")
    if tw_ is not None:
        v = eng(tw_.meshes[0][0].vertices)
        zlo, zhi = v[:, 2].min(), v[:, 2].max()
        cx, cy = 0.0, 0.0
        r_all = np.hypot(v[:, 0] - cx, v[:, 1] - cy)
        base = r_all[v[:, 2] < zlo + 1.0].max() * 2
        top = r_all[v[:, 2] > zhi - 1.0].max() * 2
        out.append(dim("Ø chân tháp", float(base), float(meta["tower_base_d_mm"]), 0.01, 5.0))
        out.append(dim("Ø đỉnh tháp", float(top), float(meta["tower_top_d_mm"]), 0.01, 5.0))
        if blades:
            gap = min(pd.solid.m.min_gap(tw_.solid.m, 0.5 * float(meta["rotor_diameter_mm"])) for pd in blades)
            need = 0.1 * float(meta["rotor_diameter_mm"]) / 2
            out.append(Check("dimensions", "khoảng hở mũi cánh – tháp ≥ 0,1 R", gap >= need, f"đo {gap:.0f} mm / tối thiểu {need:.0f}", 2.0, True))
    return out


GROUND.update({"solar_array": {"foundation"}})


@register("solar_array")
def _solar_array(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    out: list[Check] = []
    pans = [pd for pd in parts if pd.part.category == "solar_panel"]
    out.append(count_check("số tấm pin", len(pans), int(meta["panels"])))
    if not pans:
        return out
    fr = next((m for m, mt in pans[0].meshes if getattr(mt, "id", "") == "aluminum"), None)
    if fr is not None:
        v = eng(fr.vertices)
        c = v.mean(axis=0)
        w, vec = np.linalg.eigh(np.cov((v - c).T))
        tt = math.radians(float(meta["tilt_deg"]))
        axes = (np.array([math.sin(tt), 0.0, math.cos(tt)]), np.array([0.0, 1.0, 0.0]), np.array([math.cos(tt), 0.0, -math.sin(tt)]))
        ext = [float(np.ptp(v @ a_)) for a_ in axes]                    # dày, rộng, dài theo hệ trục tấm
        L, W, T = meta["panel_mm"]
        out.append(dim("chiều dài tấm pin", ext[2], float(L), 0.002, 1.0))
        out.append(dim("chiều rộng tấm pin", ext[1], float(W), 0.002, 1.0))
        out.append(dim("bề dày khung tấm pin", ext[0], float(T), 0.02, 0.5))
        n = vec[:, int(np.argmin([np.ptp((v - c) @ vec[:, i]) for i in range(3)]))]
        tilt = math.degrees(math.acos(min(1.0, abs(float(n[2])))))
        out.append(Check("dimensions", "góc nghiêng tấm pin", abs(tilt - float(meta["tilt_deg"])) <= 0.3, f"đo {tilt:.2f}° / {meta['tilt_deg']:g}°", 2.0, True))
        out.append(shape("tấm pin quay về hướng Nam (+X)", float(meta["tilt_deg"]) < 0.5 or float(n[0] * np.sign(n[2])) > 0, ""))
    ground = float(np.min([solid_bounds(pd)[0][2] for pd in parts]))
    low = min(float(solid_bounds(pd)[0][2]) for pd in pans) - ground
    out.append(Check("dimensions", "mép dưới tấm pin cách đất ≥ 500 mm", low >= 499.0, f"đo {low:.0f} mm", 1.0, True))
    if int(meta["rows"]) > 1:
        xs = sorted({round(float((solid_bounds(pd)[0][0] + solid_bounds(pd)[1][0]) / 2), 0) for pd in pans})
        pitch = xs[1] - xs[0] if len(xs) > 1 else 0.0
        L = float(meta["panel_mm"][0])
        t = math.radians(float(meta["tilt_deg"]))
        need = L * math.cos(t) + L * math.sin(t) / math.tan(math.radians(45.0))
        out.append(Check("dimensions", "khoảng cách hàng không bị bóng đổ (mặt trời cao 45°)", pitch >= need, f"đo {pitch:.0f} / cần ≥ {need:.0f} mm", 1.0, True))
    return out


GROUND.update({"centrifugal_pump": {"base"}})


@register("centrifugal_pump")
def _centrifugal_pump(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    cas = ids.get("casing")
    if cas is None:
        return [Check("dimensions", "vỏ bơm", False, "thiếu", 2.0, True)]
    v = eng_vertices(cas)
    sh_ = ids.get("shaft")
    z_axis = float(np.mean(solid_bounds(sh_)[0][[2]] + solid_bounds(sh_)[1][[2]]) / 2) if sh_ is not None else float(v[:, 2].mean())
    for dn, axis, label in ((int(meta["dn_suction"]), "x", "mặt bích hút"), (int(meta["dn_discharge"]), "z", "mặt bích đẩy")):
        i = "xyz".index(axis)
        C2 = S.FLANGE_PN16[dn][5]
        vv = v if axis == "z" else v[np.abs(v[:, 2] - z_axis) < S.FLANGE_PN16[dn][0] / 2 + 5.0]   # họng hút: quanh tâm trục
        top = float(vv[:, i].max())
        sel = vv[vv[:, i] > top - C2 - 1.0]
        ctr = (sel.min(axis=0) + sel.max(axis=0)) / 2
        ctr[i] = top - C2 / 2 - 1.0
        out += flange_checks(cas, dn, axis, f"{label} DN{dn}", center=ctr, x_range=(top - C2 - 2.5, top + 0.5),
                             r_max=S.FLANGE_PN16[dn][0] / 2 + 5.0)
    sh, mo = ids.get("shaft"), ids.get("motor")
    if sh is not None and mo is not None:
        vs = eng(sh.meshes[0][0].vertices)
        vm = eng(next(m for m, mt in mo.meshes if getattr(mt, "id", "") == "steel").vertices)
        cs_, cm = (vs.min(axis=0) + vs.max(axis=0)) / 2, (vm.min(axis=0) + vm.max(axis=0)) / 2
        off = float(np.hypot(cs_[1] - cm[1], cs_[2] - cm[2]))
        out.append(Check("dimensions", "trục bơm và trục động cơ đồng tâm", off < 0.1, f"lệch {off:.3f} mm", 2.0, True))
        out.append(dim("EN 733 h1: tâm trục → đáy chân bơm", float(cs_[2] - v[:, 2].min()), float(meta["en733"]["h1"]), 0.002, 0.5))
        body = eng(mo.meshes[0][0].vertices)
        out.append(dim(f"IEC 60072 chiều cao tâm trục H{meta['iec_frame']:g}", float(cm[2] - body[:, 2].min()), float(meta["iec_frame"]), 0.002, 0.5))
    imp = ids.get("impeller")
    if imp is not None:
        lo, hi = solid_bounds(imp)
        out.append(dim("đường kính cánh bơm", float(hi[1] - lo[1]), float(meta["impeller_d_mm"]), 0.005, 0.5))
    return out


GROUND.update({"generator_set": {"base"}})


@register("generator_set")
def _generator_set(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    bf = ids.get("base_frame")
    if bf is not None:
        lo, hi = solid_bounds(bf)
        out.append(dim("chiều dài khung đế", float(hi[0] - lo[0]), float(meta["length_mm"]), 0.002, 1.0))
    alt, eng_ = ids.get("alternator"), ids.get("engine")
    if alt is not None:
        bell = next((m for m, mt in alt.meshes if getattr(mt, "id", "") == "cast_aluminum"), None)
        if bell is not None:
            vb = eng(bell.vertices)
            cb = (vb.min(axis=0) + vb.max(axis=0)) / 2
            x_cut = float(vb[:, 0].min()) - 0.02 * float(meta["length_mm"])     # thân đầu phát sát chuông (không chân/hộp cực/khe)
            sec = alt.solid & K.box(1.0, 1e5, 1e5).translate(x_cut, 0, 0)
            if not sec.is_empty:
                a, c = sec.bounds()
                ca = (a + c) / 2
                off = float(np.hypot(ca[1] - cb[1], ca[2] - cb[2]))
                out.append(Check("dimensions", "đầu phát đồng trục với chuông bánh đà", off < 0.5, f"lệch {off:.2f} mm", 2.0, True))
    iso = ids.get("isolators")
    if iso is not None:
        out.append(count_check("đệm chống rung (đếm)", len(mesh_components(iso.meshes[0][0])), int(meta["isolators"])))
    if eng_ is not None:
        core = next((m for m, mt in eng_.meshes if getattr(mt, "id", "") == "aluminum_dark"), None)
        blk = eng(eng_.meshes[0][0].vertices)
        if core is not None:
            out.append(shape("két nước ở phía trước động cơ (+X)", float(eng(core.vertices)[:, 0].mean()) > float(blk[:, 0].mean()), ""))
    if meta.get("enclosure") == "canopy":
        can, ex = ids.get("canopy"), ids.get("exhaust")
        if can is not None and ex is not None:
            out.append(shape("ống xả thoát lên trên mái vỏ", float(solid_bounds(ex)[1][2]) > float(solid_bounds(can)[1][2]) - 60.0, ""))
        out.append(count_check("cửa hông bảo dưỡng", len(by_cat(parts, "door")), 4))
    return out


GROUND.update({"storage_tank": {"foundation"}})


@register("storage_tank")
def _storage_tank(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    sh = ids.get("shell")
    if sh is None:
        return [Check("dimensions", "thân bồn", False, "thiếu", 2.0, True)]
    body = eng(sh.meshes[0][0].vertices)
    lo, hi = body.min(axis=0), body.max(axis=0)
    c = (lo + hi) / 2
    V_want = float(meta["capacity_m3"]) * 1e9
    if meta.get("orientation") == "vertical":
        z_mid = float(lo[2] + 0.37 * (hi[2] - lo[2]))
        iv = probe_intervals(sh.solid, "y", (float(c[0]), 0.0, z_mid))
        gaps = gaps_between(iv)
        r_in = max((g[1] - g[0]) for g in gaps) / 2 if gaps else None
        H = float(hi[2] - lo[2]) - 8.0                                  # thân (trừ thép góc mép trên dày 8)
        if r_in:
            V = math.pi * r_in * r_in * H
            out.append(dim("dung tích trong lòng thân (đo bán kính trong × chiều cao)", V / 1e9, V_want / 1e9, 0.02, 0.05, unit="m³"))
    else:
        iv = probe_intervals(sh.solid, "y", (float(c[0]), 0.0, float(c[2])))
        gaps = gaps_between(iv)
        r_in = max((g[1] - g[0]) for g in gaps) / 2 if gaps else None
        if r_in:
            hh = r_in / 2
            t = float(meta["shell_t_mm"])
            Lc = float(hi[0] - lo[0]) - 2 * (hh + t)
            V = math.pi * r_in * r_in * Lc + 2 * (2.0 / 3.0) * math.pi * r_in * r_in * hh
            out.append(dim("dung tích trong (trụ + 2 đáy elip 2:1, đo)", V / 1e9, V_want / 1e9, 0.02, 0.05, unit="m³"))
    lad = ids.get("ladder")
    if lad is not None:
        out.append(count_check("số bậc thang (cách 300 mm)", int(meta.get("rungs", 0)), int(meta.get("rungs", 0))))
        climb = float(meta.get("shell_height_mm", 0.0))
        out.append(shape("có lồng bảo vệ khi leo > 3 m (ISO 14122-4)", (climb <= 3000.0) or bool(meta.get("has_cage")), ""))
    vals = ids.get("valves")
    if vals is not None:
        out.append(count_check("van trên vòi (đếm)", len(mesh_components(vals.meshes[0][0])), 3 if meta.get("orientation") == "vertical" else 2))
    return out


@register("axial_fan")
def _axial_fan(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    fr, ro = ids.get("frame"), ids.get("rotor")
    if fr is None or ro is None:
        return [Check("dimensions", "khung + cánh quạt", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(fr)
    A, T, hs = float(meta["size_mm"]), float(meta["thickness_mm"]), float(meta["hole_spacing_mm"])
    c = (lo + hi) / 2
    out = [dim("cạnh khung quạt", float(hi[0] - lo[0]), A, 0.003, 0.2), dim("bề dày quạt", float(hi[2] - lo[2]), T, 0.01, 0.2)]
    iv = probe_intervals(fr.solid, "x", (float(c[0]), float(c[1]) + hs / 2, float(lo[2]) + 0.05 * T))
    holes = [((a + b_) / 2) for a, b_ in gaps_between(iv) if (b_ - a) < 0.15 * A]
    got = (max(holes) - min(holes)) if len(holes) >= 2 else None
    out.append(dim("khoảng tâm lỗ vít", got, hs, 0.005, 0.2))
    rl, rh = solid_bounds(ro)
    rc = (rl + rh) / 2
    n = ring_count(ro.solid, rc, "z", 0.8 * (rh[0] - rl[0]) / 2, -A, A, thickness=0.3)
    out.append(count_check("số lá cánh (đếm ở 0,8 R)", n, int(meta["blades"])))
    ivc = probe_intervals(fr.solid, "y", (float(c[0]), float(c[1]), float(lo[2]) + 0.5 * T))
    gc = [b_ - a for a, b_ in gaps_between(ivc)]
    r_v = max(gc) / 2 if gc else 0.0
    vr = eng_vertices(ro)
    r_tip = float(radial(vr, c, "z").max())                            # trục quạt = tâm khung (lá lẻ làm lệch hộp bao cánh)
    out.append(Check("dimensions", "khe hở đầu lá – miệng loe ≥ 0,9 mm", r_v - r_tip >= 0.9, f"đo {r_v - r_tip:.2f} mm", 1.0, True))
    return out


@register("heatsink")
def _heatsink(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    out: list[Check] = []
    if meta.get("heatsink_type") == "tower":
        fins, hp = ids.get("fins"), ids.get("heat_pipes")
        if fins is None or hp is None:
            return [Check("dimensions", "chồng lá + ống", False, "thiếu", 2.0, True)]
        v = eng(fins.meshes[0][0].vertices)
        lo, hi = v.min(axis=0), v.max(axis=0)
        iv = probe_intervals(fins.solid, "z", (float(hi[0]) - 20.0, float((lo[1] + hi[1]) / 2), 0.0))
        iv = [q for q in iv if q[1] - q[0] < 1.0]
        out.append(count_check("số lá tản nhiệt (dò tia)", len(iv), int(meta["fins"])))
        if len(iv) > 2:
            pitch = float(np.mean(np.diff([a for a, _ in iv])))
            out.append(dim("bước lá", pitch, float(meta["fin_pitch_mm"]), 0.01, 0.02))
            out.append(dim("bề dày lá", float(np.mean([b_ - a for a, b_ in iv])), float(meta["fin_t_mm"]), 0.03, 0.02))
        hl, hh = solid_bounds(hp)
        z = float(meta["fin_z0_mm"]) + 20.0 + float(hl[2]) - 0.0
        sec = hp.solid & K.box(1e4, 1e4, 0.5).translate(float((hl[0] + hh[0]) / 2), float((hl[1] + hh[1]) / 2), float(hl[2]) + (z - float(hl[2])))
        comps = sec.split_components() if not sec.is_empty else []
        out.append(count_check("số nhánh ống dẫn nhiệt xuyên lá (2 × số ống)", len(comps), 2 * int(meta["heat_pipes"])))
        if comps:
            a, c = comps[0].bounds()
            out.append(dim("đường kính ống dẫn nhiệt", float(c[0] - a[0]), float(meta["pipe_d_mm"]), 0.02, 0.1))
    else:
        base = ids.get("base")
        if base is None:
            return [Check("dimensions", "tản nhôm", False, "thiếu", 2.0, True)]
        v = eng(base.meshes[0][0].vertices)
        lo, hi = v.min(axis=0), v.max(axis=0)
        z = float(lo[2]) + float(meta["base_t_mm"]) + 0.5 * float(meta["fin_h_mm"])
        iv = probe_intervals(base.solid, "y", (float((lo[0] + hi[0]) / 2), 0.0, z))
        out.append(count_check("số lá tản nhiệt (dò tia)", len(iv), int(meta["fins"])))
        if len(iv) > 2:
            out.append(dim("bước lá", float(np.mean(np.diff([a for a, _ in iv]))), float(meta["fin_pitch_mm"]), 0.01, 0.02))
            out.append(dim("bề dày lá", float(np.mean([b_ - a for a, b_ in iv])), float(meta["fin_t_mm"]), 0.02, 0.02))
    return out


@register("dev_board")
def _dev_board(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    pcb, hd = ids.get("pcb"), ids.get("headers")
    if pcb is None:
        return [Check("dimensions", "PCB", False, "thiếu", 2.0, True)]
    v = eng(pcb.meshes[0][0].vertices)
    lo, hi = v.min(axis=0), v.max(axis=0)
    out = [dim("chiều dài bo", float(hi[0] - lo[0]), float(meta["width_mm"]), 0.002, 0.05),
           dim("chiều rộng bo", float(hi[1] - lo[1]), float(meta["height_mm"]), 0.002, 0.05),
           dim("bề dày PCB", float(hi[2] - lo[2]), float(meta["pcb_t_mm"]), 0.02, 0.02)]
    zc = float((lo[2] + hi[2]) / 2)
    errs = []
    for hx, hy in meta["holes"]:
        ivx = probe_intervals(pcb.solid, "x", (0.0, float(lo[1]) + hy, zc))
        gx = [((a + b_) / 2) for a, b_ in gaps_between(ivx) if b_ - a < 5.0]
        ivy = probe_intervals(pcb.solid, "y", (float(lo[0]) + hx, 0.0, zc))
        gy = [((a + b_) / 2) for a, b_ in gaps_between(ivy) if b_ - a < 5.0]
        mx = min(gx, key=lambda q: abs(q - (float(lo[0]) + hx))) if gx else None
        my = min(gy, key=lambda q: abs(q - (float(lo[1]) + hy))) if gy else None
        if mx is None or my is None or abs(mx - lo[0] - hx) > 0.1 or abs(my - lo[1] - hy) > 0.1:
            errs.append(f"({hx},{hy})")
    out.append(Check("dimensions", f"{len(meta['holes'])} lỗ bắt đúng tọa độ bản vẽ (dò tia)", not errs, ", ".join(errs) or "đạt", 2.0, True))
    if hd is not None:
        gold = next((m for m, mt in hd.meshes if getattr(mt, "id", "") == "gold"), None)
        comps = [eng(c) for c in mesh_components(gold)] if gold is not None else []
        out.append(count_check("số chân header (đếm)", len(comps), int(meta["pins_total"])))
        cen = np.array([(c.min(axis=0) + c.max(axis=0)) / 2 for c in comps]) if comps else np.zeros((0, 3))
        if len(cen) > 3:
            rows: dict[float, list[float]] = {}
            for c in cen:
                rows.setdefault(round(float(c[1]), 1), []).append(float(c[0]))
            steps = [d for xs in rows.values() if len(xs) > 2 for d in np.diff(sorted(xs))]
            out.append(dim("bước chân header", float(np.median(steps)) if steps else None, float(meta["pitch_mm"]), 0.002, 0.01))
    return out


@register("server_rack")
def _server_rack(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    frame, rails = ids.get("frame"), ids.get("rails")
    if frame is None or rails is None:
        return [Check("dimensions", "khung + ray 19\"", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(frame)
    n, U = int(meta["rack_units"]), float(meta["u_mm"])
    out = [dim("chiều sâu khung (trừ 2 cửa 20 mm)", float(hi[0] - lo[0]), float(meta["depth_mm"]) - 40.0, 0.002, 0.5),
           dim("bề rộng khung (trừ 2 hông 1,5 mm)", float(hi[1] - lo[1]), float(meta["width_mm"]) - 3.0, 0.002, 0.5)]
    rl, rh = solid_bounds(rails)
    yc = float((rl[1] + rh[1]) / 2)
    x_face = float(rh[0]) - 1.0                                        # giữa bề dày cánh ray trước
    holes = gaps_between(probe_intervals(rails.solid, "z", (x_face, yc + float(meta["hole_spacing_mm"]) / 2, 0.0)))
    out.append(count_check(f"số lỗ vuông trên ray ({n}U × 3, dò tia)", len(holes), 3 * n))
    if holes:
        out.append(dim("cạnh lỗ vuông", float(np.median([b_ - a for a, b_ in holes])), float(meta["square_hole_mm"]), 0.0, 0.05))
    if len(holes) >= 4:
        cz = [(a + b_) / 2 for a, b_ in holes]
        out.append(dim("bước 1U (lỗ 1 → lỗ 1 kế tiếp)", cz[3] - cz[0], U, 0.0, 0.05))
        out.append(dim("bước lỗ trong 1U (15,875)", cz[1] - cz[0], 15.875, 0.0, 0.05))
        gy = gaps_between(probe_intervals(rails.solid, "y", (x_face, 0.0, cz[0])))
        if gy:
            op = max(gy, key=lambda g: g[1] - g[0])
            out.append(dim("lọt lòng giữa hai ray (≥ 450)", op[1] - op[0], float(meta["opening_mm"]), 0.0, 0.1))
            hc = [(a + b_) / 2 for a, b_ in gy if b_ - a < 20.0]
            out.append(dim("khoảng tâm lỗ ngang (465,1)", (max(hc) - min(hc)) if len(hc) == 2 else None, float(meta["hole_spacing_mm"]), 0.0, 0.1))
    bad = []
    for eq in meta.get("equipment", []):
        pd = ids.get(eq["id"])
        if pd is None:
            bad.append(f"{eq['id']}: thiếu")
            continue
        el, eh = solid_bounds(pd)
        h_want = eq["units"] * U - 0.79
        if abs(float(eh[2] - el[2]) - h_want) > 0.1 or abs(float(eh[1] - el[1]) - float(meta["panel_width_mm"])) > 0.1:
            bad.append(f"{eq['id']}: {eh[1] - el[1]:.1f}×{eh[2] - el[2]:.2f}")
    if meta.get("equipment"):
        out.append(Check("dimensions", "mặt thiết bị 482,6 × (n·44,45 − 0,79) mm", not bad, ", ".join(bad) or "đạt", 2.0, True))
    return out


@register("electrical_enclosure")
def _electrical_enclosure(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    body, door, rails, dev = ids.get("body"), ids.get("door"), ids.get("din_rails"), ids.get("devices")
    if body is None or door is None or rails is None:
        return [Check("dimensions", "thân + cửa + ray DIN", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(body)
    out = [dim("bề rộng tủ", float(hi[1] - lo[1]), float(meta["width_mm"]), 0.002, 0.5),
           dim("chiều cao tủ", float(hi[2] - lo[2]), float(meta["height_mm"]), 0.002, 0.5),
           dim("chiều sâu thân tủ", float(hi[0] - lo[0]), float(meta["depth_mm"]), 0.002, 0.5)]
    dl, dh = solid_bounds(door)
    out.append(shape("cửa tủ ở mặt trước (+X)", dl[0] >= hi[0] - 1.0, f"cửa x ∈ [{dl[0]:.0f}, {dh[0]:.0f}], thân x ≤ {hi[0]:.0f}"))
    comps = rails.solid.split_components()
    out.append(count_check("số thanh ray DIN", len(comps), int(meta["din_rows"])))
    hats, pitches, n_mcb = [], [], 0
    for c in comps:
        a, b_ = c.bounds()
        out.append(dim("chiều cao ray TH35 (7,5)", float(b_[0] - a[0]), 7.5, 0.0, 0.05))
        out.append(dim("bề rộng ray TH35 (35)", float(b_[2] - a[2]), 35.0, 0.0, 0.05))
        zc = float((a[2] + b_[2]) / 2)
        iv = probe_intervals(c, "z", (float(b_[0]) - 0.5, float((a[1] + b_[1]) / 2), zc))
        hats += [q[1] - q[0] for q in iv]
        if dev is not None and dev.solid is not None:
            ivd = probe_intervals(dev.solid, "y", (float(a[0]) + 7.5 + 60.0, 0.0, zc))
            mods = [q for q in ivd if 17.0 < q[1] - q[0] < 18.0]
            n_mcb += len(mods)
            pitches += list(np.diff(sorted(q[0] for q in mods)))
    out.append(dim("bề rộng mũ ray (25)", float(np.mean(hats)) if hats else None, 25.0, 0.0, 0.05))
    out.append(count_check("số aptomat tép 1 mô-đun (dò tia)", n_mcb, int(meta["mcb_count"])))
    if pitches:
        out.append(dim("bước mô-đun DIN 43880", float(np.median(pitches)), 18.0, 0.0, 0.05))
    gl = ids.get("glands")
    if gl is not None:
        out.append(count_check("số ốc siết cáp", len(gl.solid.split_components()), int(meta["glands"])))
        gl_lo, gl_hi = solid_bounds(gl)
        out.append(shape("ốc siết cáp ở đáy tủ", gl_hi[2] < lo[2] + 0.1 * (hi[2] - lo[2]), f"z ≤ {gl_hi[2]:.0f}"))
    return out


def _extent(pd: Any, axis: int) -> float:
    lo, hi = solid_bounds(pd)
    return float(hi[axis] - lo[axis])


@register("fdm_printer")
def _fdm_printer(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    plate, hot, fr = ids.get("build_plate"), ids.get("hotend"), ids.get("frame")
    if plate is None or hot is None or fr is None:
        return [Check("dimensions", "khung + tấm in + hotend", False, "thiếu", 2.0, True)]
    Bx, By, Bz = (float(v) for v in meta["build_mm"])
    pl, ph = solid_bounds(plate)
    hl, hh = solid_bounds(hot)
    fl, fh = solid_bounds(fr)
    out = [Check("dimensions", f"tấm in phủ vùng in {Bx:g}×{By:g}", float(ph[0] - pl[0]) >= Bx - 0.1 and float(ph[1] - pl[1]) >= By - 0.1,
                 f"tấm {ph[0] - pl[0]:.1f}×{ph[1] - pl[1]:.1f} mm", 2.0, True),
           dim("khe mũi phun – mặt tấm in ở gốc Z", float(hl[2] - ph[2]), float(meta["tip_gap_mm"]), 0.0, 0.05),
           (Check("dimensions", f"khung cao hơn mặt in + {Bz:g} mm", float(fh[2] - ph[2]) >= Bz, f"đo {fh[2] - ph[2]:.1f} mm", 2.0, True)
            if meta.get("kinematics") != "corexy" else    # CoreXY: bàn hạ dần theo Z từ sát mũi phun
            Check("dimensions", f"bàn hạ được {Bz:g} mm trong khung", float(ph[2] - fl[2]) >= Bz, f"đo {ph[2] - fl[2]:.1f} mm", 2.0, True)),
           shape("mũi phun nằm trên vùng tấm in", pl[0] <= (hl[0] + hh[0]) / 2 <= ph[0] and pl[1] <= (hl[1] + hh[1]) / 2 <= ph[1],
                 f"mũi ({(hl[0] + hh[0]) / 2:.0f}, {(hl[1] + hh[1]) / 2:.0f})")]
    for pid, key, ax in (("y_rail", "y_rail_mm", 0), ("y_rails", "y_rail_mm", 0), ("x_rail", "x_rail_mm", 1)):
        pd = ids.get(pid)
        if pd is not None:
            comps = pd.solid.split_components()
            out.append(dim(f"chiều dài ray {pid}", float(max(c.bounds()[1][ax] - c.bounds()[0][ax] for c in comps)), float(meta[key]), 0.0, 0.1))
    return out


@register("cnc_router")
def _cnc_router(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    ids = by_id(parts)
    need = ("table", "tool", "gantry_beam", "spindle", "x_screw", "y_screws", "z_screw", "y_rails")
    if any(ids.get(k) is None for k in need):
        return [Check("dimensions", "bàn + giàn + trục chính + 3 vít me", False, "thiếu", 2.0, True)]
    Tx, Ty, Tz = (float(v) for v in meta["travel_mm"])
    tl, th = solid_bounds(ids["table"])
    tol, toh = solid_bounds(ids["tool"])
    gl, _ = solid_bounds(ids["gantry_beam"])
    out = [dim("chiều dài bàn máy", float(th[0] - tl[0]), float(meta["table_mm"][0]), 0.0, 0.2),
           dim("bề rộng bàn máy", float(th[1] - tl[1]), float(meta["table_mm"][1]), 0.0, 0.2),
           dim("mũi dao trên mặt bàn ở gốc Z", float(tol[2] - th[2]), float(meta["tip_home_above_table_mm"]), 0.0, 0.1),
           Check("dimensions", "mũi dao chạm được mặt bàn khi hạ hết Z", float(tol[2] - th[2]) - Tz <= 15.0 and float(tol[2] - th[2]) > Tz,
                 f"mũi cao {tol[2] - th[2]:.1f} mm, hành trình Z {Tz:g}", 2.0, True),
           dim("khe hở dầm giàn – mặt bàn", float(gl[2] - th[2]), float(meta["gantry_clearance_mm"]), 0.0, 0.1),
           Check("dimensions", "khe hở dưới dầm giàn > hành trình Z", float(gl[2] - th[2]) > Tz, f"đo {gl[2] - th[2]:.1f} mm", 2.0, True),
           dim("Ø thân trục chính", _extent(ids["spindle"], 1), float(meta["spindle_d_mm"]), 0.0, 0.2),
           dim("Ø dao phay", _extent(ids["tool"], 0), float(meta["tool_d_mm"]), 0.0, 0.05)]
    sl = meta["screw_len_mm"]
    ys = ids["y_screws"].solid.split_components()
    out.append(count_check("số vít me trục Y (dẫn động kép)", len(ys), 2))
    out.append(dim("chiều dài vít me Y", float(max(c.bounds()[1][0] - c.bounds()[0][0] for c in ys)), float(sl["y"]), 0.0, 0.2))
    out.append(dim("chiều dài vít me X", _extent(ids["x_screw"], 1), float(sl["x"]), 0.0, 0.2))
    out.append(dim("chiều dài vít me Z", _extent(ids["z_screw"], 2), float(sl["z"]), 0.0, 0.2))
    tcx = (tol[0] + toh[0]) / 2
    out.append(shape("dao nằm trong vùng bàn (± nửa hành trình Y máy)", tl[0] + 45 <= tcx - Ty / 2 and tcx + Ty / 2 <= th[0] - 45,
                     f"tâm dao x = {tcx:.0f}, bàn [{tl[0]:.0f}, {th[0]:.0f}]"))
    rl = meta["rail_len_mm"]
    out.append(Check("dimensions", "ray Y đủ hành trình + 2 con trượt", float(rl["y"]) >= Ty + 2 * 77.0, f"ray {rl['y']:.0f} mm", 1.0, True))
    out.append(Check("dimensions", "ray X đủ hành trình", float(rl["x"]) >= Tx + 2 * 77.0, f"ray {rl['x']:.0f} mm", 1.0, True))
    return out
