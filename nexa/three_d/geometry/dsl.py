"""CAD DSL (JSON) — định dạng DUY NHẤT mà AI được dùng để mô tả hình học tự do. KHÔNG có exec/eval.

Mỗi nút là object có "op" thuộc danh sách trắng; tham số được kiểm tra kiểu/giới hạn nghiêm ngặt, trường lạ bị từ
chối, độ sâu và số nút có giới hạn. Trình biên dịch chỉ gọi các hàm trong kernel.py.

Phép được phép: box, cylinder, sphere, ellipsoid, cone, capsule, torus, extrude, revolve, sweep, tube, loft, hull (bao
lồi), union, subtract, intersect, translate, rotate, mirror, scale, array (lặp quanh trục), linear_array, hole, thread,
smooth (chia nhỏ mượt).
Fillet/chamfer: tham số của box/cylinder và của đỉnh profile (kernel mesh không bo được cạnh tùy chọn — giới hạn đã
ghi trong docs/three_d.md).
Hệ trục: X trước, Y trái, Z lên; đơn vị mm.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P

MAX_DEPTH = 10
MAX_NODES = 250
MAX_COORD = 20000.0
MAX_POINTS = 400


class DslError(ValueError):
    pass


class _Budget:
    def __init__(self, check: Callable[[], None] | None = None) -> None:
        self.nodes = 0
        self.check = check


def _num(node: dict, key: str, lo: float, hi: float, default: float | None = None, required: bool = True) -> float:
    if key not in node:
        if default is not None or not required:
            return default  # type: ignore[return-value]
        raise DslError(f"thiếu '{key}' trong {node.get('op', 'profile')}")
    v = node[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        raise DslError(f"'{key}' phải là số hữu hạn")
    v = float(v)
    if not (lo <= v <= hi):
        raise DslError(f"'{key}'={v:g} ngoài khoảng [{lo:g}, {hi:g}]")
    return v


def _int(node: dict, key: str, lo: int, hi: int, default: int) -> int:
    v = node.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or float(v) != int(v):
        raise DslError(f"'{key}' phải là số nguyên")
    v = int(v)
    if not (lo <= v <= hi):
        raise DslError(f"'{key}'={v} ngoài khoảng [{lo}, {hi}]")
    return v


def _vec(node: dict, key: str, n: int, lo: float = -MAX_COORD, hi: float = MAX_COORD, default=None) -> np.ndarray:
    if key not in node:
        if default is None:
            raise DslError(f"thiếu '{key}'")
        return np.asarray(default, float)
    v = node[key]
    if not isinstance(v, list) or len(v) != n:
        raise DslError(f"'{key}' phải là mảng {n} số")
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)) or not (lo <= x <= hi):
            raise DslError(f"'{key}' chứa giá trị không hợp lệ")
        out.append(float(x))
    return np.asarray(out)


def _points(v: Any, dim: int, key: str = "points", min_n: int = 2) -> np.ndarray:
    if not isinstance(v, list) or not (min_n <= len(v) <= MAX_POINTS):
        raise DslError(f"'{key}' phải có {min_n}–{MAX_POINTS} điểm")
    arr = []
    for p in v:
        if not isinstance(p, list) or len(p) != dim:
            raise DslError(f"mỗi điểm trong '{key}' phải có {dim} tọa độ")
        for x in p:
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)) or abs(x) > MAX_COORD:
                raise DslError(f"tọa độ trong '{key}' không hợp lệ")
        arr.append([float(x) for x in p])
    return np.asarray(arr)


def _allowed(node: dict, keys: set[str]) -> None:
    extra = set(node) - keys - {"op", "comment"}
    if extra:
        raise DslError(f"trường không được phép trong '{node.get('op', 'profile')}': {sorted(extra)}")


PROFILE_KEYS = {"shape", "points", "fillet", "chamfer", "spline", "radius", "width", "height", "corner_radius",
                "exponent", "code", "chord", "segments"}


def compile_profile(prof: Any) -> np.ndarray:
    """Profile 2D kín → mảng (N,2)."""
    if not isinstance(prof, dict):
        raise DslError("profile phải là object")
    _allowed(prof, PROFILE_KEYS)
    shape = prof.get("shape", "polygon")
    if shape == "circle":
        return P.circle(_num(prof, "radius", 0.01, MAX_COORD), _int(prof, "segments", 8, 256, 64))
    if shape == "rect":
        w, h = _num(prof, "width", 0.01, MAX_COORD), _num(prof, "height", 0.01, MAX_COORD)
        return P.rounded_rect(w, h, _num(prof, "corner_radius", 0, MAX_COORD, 0.0), 8) if prof.get("corner_radius") else \
            np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]])
    if shape == "superellipse":
        return P.superellipse(_num(prof, "width", 0.01, MAX_COORD), _num(prof, "height", 0.01, MAX_COORD),
                              _num(prof, "exponent", 1.0, 10.0, 2.5), _int(prof, "segments", 12, 256, 64))
    if shape == "naca":
        code = str(prof.get("code", "2412"))
        if not (len(code) == 4 and code.isdigit()):
            raise DslError("mã NACA phải gồm 4 chữ số")
        return P.naca4(code, _num(prof, "chord", 0.1, MAX_COORD), 48)
    if shape != "polygon":
        raise DslError(f"kiểu profile '{shape}' không hỗ trợ")
    pts = _points(prof.get("points"), 2, "points", 3)
    if prof.get("spline"):
        pts = P.spline_through(pts, max(24, len(pts) * 8), closed=True)
    if "fillet" in prof:
        f = prof["fillet"]
        radii = [f] * len(pts) if isinstance(f, (int, float)) and not isinstance(f, bool) else f
        if not isinstance(radii, list) or len(radii) != len(pts):
            raise DslError("'fillet' phải là số hoặc mảng cùng số đỉnh")
        radii = [float(r) for r in radii]
        if any(not math.isfinite(r) or r < 0 or r > MAX_COORD for r in radii):
            raise DslError("bán kính fillet không hợp lệ")
        pts = P.fillet_polygon(pts, radii, 8)
    elif "chamfer" in prof:
        pts = P.chamfer_polygon(pts, _num(prof, "chamfer", 0, MAX_COORD))
    if abs(P.signed_area(pts)) < 1e-6:
        raise DslError("profile có diện tích 0")
    return pts


def compile_node(node: Any, depth: int = 0, budget: _Budget | None = None) -> K.Solid:
    budget = budget or _Budget()
    if budget.check:
        budget.check()
    if depth > MAX_DEPTH:
        raise DslError(f"cây DSL quá sâu (> {MAX_DEPTH})")
    budget.nodes += 1
    if budget.nodes > MAX_NODES:
        raise DslError(f"quá nhiều nút DSL (> {MAX_NODES})")
    if not isinstance(node, dict) or "op" not in node:
        raise DslError("mỗi nút DSL phải là object có 'op'")
    op = node["op"]
    sub = lambda n: compile_node(n, depth + 1, budget)  # noqa: E731
    try:
        if op == "box":
            _allowed(node, {"size", "fillet", "chamfer"})
            s = _vec(node, "size", 3, 0.01, MAX_COORD)
            if node.get("fillet"):
                return K.rounded_box(*s, _num(node, "fillet", 0, MAX_COORD))
            if node.get("chamfer"):
                return K.chamfer_box(*s, _num(node, "chamfer", 0, MAX_COORD))
            return K.box(*s)
        if op == "cylinder":
            _allowed(node, {"radius", "height", "radius_top", "segments", "fillet", "center"})
            r, h = _num(node, "radius", 0.01, MAX_COORD), _num(node, "height", 0.01, MAX_COORD)
            rt = _num(node, "radius_top", 0.0, MAX_COORD, r)
            fil = _num(node, "fillet", 0, MAX_COORD, 0.0)
            if fil > 0:
                prof = P.fillet_polygon([(0, 0), (r, 0), (rt, h), (0, h)], [0, fil, fil, 0], 8)
                s = K.revolve(prof)
            else:
                s = K.cylinder(r, h, rt, int(node["segments"]) if node.get("segments") else None)
            return s.translate(0, 0, -h / 2) if node.get("center") else s
        if op == "cone":
            _allowed(node, {"radius", "height", "radius_top", "segments"})
            return K.cone(_num(node, "radius", 0.01, MAX_COORD), _num(node, "height", 0.01, MAX_COORD),
                          _num(node, "radius_top", 0, MAX_COORD, 0.0))
        if op == "sphere":
            _allowed(node, {"radius", "segments"})
            return K.sphere(_num(node, "radius", 0.01, MAX_COORD))
        if op == "capsule":
            _allowed(node, {"radius", "length"})
            return K.capsule(_num(node, "radius", 0.01, MAX_COORD), _num(node, "length", 0.02, MAX_COORD))
        if op == "ellipsoid":
            _allowed(node, {"radii"})
            r = _vec(node, "radii", 3, 0.01, MAX_COORD)
            return K.ellipsoid(*r)
        if op == "tube":
            _allowed(node, {"path", "radius", "scales", "rounded_ends", "smooth_path"})
            path = _points(node.get("path"), 3, "path", 2)
            if node.get("smooth_path", True) and len(path) >= 3:
                path = P.spline_through(path, max(24, len(path) * 10))
            scales = None
            if "scales" in node:
                sc = node["scales"]
                if not isinstance(sc, list) or len(sc) < 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not
                                                                  (0.01 <= x <= 100) for x in sc):
                    raise DslError("'scales' phải là mảng số trong [0.01, 100]")
                scales = np.interp(np.linspace(0, 1, len(path)), np.linspace(0, 1, len(sc)), sc)
            return K.tube(path, _num(node, "radius", 0.01, MAX_COORD), 24, scales, bool(node.get("rounded_ends", True)))
        if op == "hull":
            _allowed(node, {"children"})
            ch = node.get("children")
            if not isinstance(ch, list) or not (2 <= len(ch) <= 32):
                raise DslError("hull cần 2–32 'children'")
            return K.hull([sub(c) for c in ch])
        if op == "linear_array":
            _allowed(node, {"count", "step", "child"})
            n = _int(node, "count", 1, 64, 2)
            step = _vec(node, "step", 3)
            s = sub(node.get("child"))
            return K.Solid.union_all([s.moved(step * i) for i in range(n)])
        if op == "torus":
            _allowed(node, {"major", "minor"})
            major, minor = _num(node, "major", 0.01, MAX_COORD), _num(node, "minor", 0.005, MAX_COORD)
            if minor >= major:
                raise DslError("torus: minor phải nhỏ hơn major")
            return K.torus(major, minor)
        if op == "extrude":
            _allowed(node, {"profile", "height", "twist", "scale_top", "holes"})
            outer = compile_profile(node.get("profile"))
            holes = [compile_profile(h) for h in node.get("holes", [])] if isinstance(node.get("holes", []), list) else []
            st = _vec(node, "scale_top", 2, 0.0, 10.0, default=[1.0, 1.0])
            return K.extrude([outer] + holes, _num(node, "height", 0.01, MAX_COORD), _num(node, "twist", -3600, 3600, 0.0),
                             tuple(st), divisions=16 if node.get("twist") else 0)
        if op == "revolve":
            _allowed(node, {"profile", "degrees"})
            prof = compile_profile(node.get("profile"))
            if prof[:, 0].min() < -1e-6:
                raise DslError("revolve: profile phải nằm ở phía x ≥ 0 (x = bán kính)")
            return K.revolve(prof, degrees=_num(node, "degrees", 1, 360, 360.0))
        if op == "sweep":
            _allowed(node, {"profile", "path", "scales", "twist", "smooth_path"})
            prof = compile_profile(node.get("profile"))
            path = _points(node.get("path"), 3, "path", 2)
            if node.get("smooth_path", True) and len(path) >= 3:
                path = P.spline_through(path, max(24, len(path) * 10))
            scales = None
            if "scales" in node:
                sc = node["scales"]
                if not isinstance(sc, list) or len(sc) < 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not
                                                                  (0.01 <= x <= 100) for x in sc):
                    raise DslError("'scales' phải là mảng số trong [0.01, 100]")
                scales = np.interp(np.linspace(0, 1, len(path)), np.linspace(0, 1, len(sc)), sc)
            return K.sweep(prof, path, scales, _num(node, "twist", -3600, 3600, 0.0))
        if op == "loft":
            _allowed(node, {"sections", "positions", "offsets"})
            secs = node.get("sections")
            pos = node.get("positions")
            if not isinstance(secs, list) or not isinstance(pos, list) or len(secs) != len(pos) or not (2 <= len(secs) <= 60):
                raise DslError("loft cần 2–60 'sections' và 'positions' (độ cao Z) cùng độ dài")
            offs = node.get("offsets") or [[0.0, 0.0]] * len(secs)
            if not isinstance(offs, list) or len(offs) != len(secs):
                raise DslError("'offsets' phải cùng số phần tử với 'sections'")
            count = 64
            out = []
            for s_, z_, o_ in zip(secs, pos, offs):
                if isinstance(z_, bool) or not isinstance(z_, (int, float)) or abs(z_) > MAX_COORD:
                    raise DslError("positions không hợp lệ")
                o = _points([o_], 2, "offsets", 1)[0]
                prof = P.resample_closed(compile_profile(s_), count)
                out.append(np.column_stack([prof[:, 0] + o[0], prof[:, 1] + o[1], np.full(count, float(z_))]))
            return K.loft(out)
        if op in ("union", "intersect"):
            _allowed(node, {"children"})
            ch = node.get("children")
            if not isinstance(ch, list) or not (1 <= len(ch) <= 64):
                raise DslError(f"{op} cần 1–64 'children'")
            solids = [sub(c) for c in ch]
            if op == "union":
                return K.Solid.union_all(solids)
            out = solids[0]
            for s in solids[1:]:
                out = out & s
            return out
        if op == "subtract":
            _allowed(node, {"base", "cut"})
            cut = node.get("cut")
            cut = cut if isinstance(cut, list) else [cut]
            if not (1 <= len(cut) <= 64):
                raise DslError("subtract cần 1–64 khối cắt")
            return sub(node.get("base")).subtract_all([sub(c) for c in cut])
        if op == "translate":
            _allowed(node, {"offset", "child"})
            return sub(node.get("child")).moved(_vec(node, "offset", 3))
        if op == "rotate":
            _allowed(node, {"angles", "child", "center"})
            a = _vec(node, "angles", 3, -3600, 3600)
            c = _vec(node, "center", 3, default=[0, 0, 0])
            return sub(node.get("child")).translate(*(-c)).rotate(*a).translate(*c)
        if op == "mirror":
            _allowed(node, {"normal", "child", "keep_original"})
            nrm = _vec(node, "normal", 3, -1, 1)
            if np.linalg.norm(nrm) < 1e-9:
                raise DslError("mirror: pháp tuyến bằng 0")
            s = sub(node.get("child"))
            m = s.mirror(nrm)
            return s + m if node.get("keep_original", True) else m
        if op == "scale":
            _allowed(node, {"factors", "child"})
            fct = _vec(node, "factors", 3, 0.001, 1000)
            return sub(node.get("child")).scale(*fct)
        if op == "array":
            _allowed(node, {"count", "axis", "child", "start_angle"})
            n = _int(node, "count", 1, 64, 2)
            axis = _vec(node, "axis", 3, -1, 1, default=[0, 0, 1])
            s = sub(node.get("child"))
            return K.Solid.union_all(K.radial_array(s, n, axis, _num(node, "start_angle", -360, 360, 0.0)))
        if op == "hole":
            _allowed(node, {"target", "diameter", "depth", "position", "axis"})
            d, h = _num(node, "diameter", 0.05, MAX_COORD), _num(node, "depth", 0.05, MAX_COORD)
            pos = _vec(node, "position", 3)
            axis = _vec(node, "axis", 3, -1, 1, default=[0, 0, -1])
            if np.linalg.norm(axis) < 1e-9:
                raise DslError("hole: trục bằng 0")
            cutter = K.cylinder(d / 2, h + 0.02).translate(0, 0, -0.01).align_z(axis, pos)
            return sub(node.get("target")) - cutter
        if op == "thread":
            _allowed(node, {"major_diameter", "pitch", "length"})
            d = _num(node, "major_diameter", 1.0, 200)
            p = _num(node, "pitch", 0.2, 10)
            if p > d / 2:
                raise DslError("thread: bước ren quá lớn so với đường kính")
            return K.threaded_rod(d, p, _num(node, "length", 0.5, 2000))
        if op == "smooth":
            _allowed(node, {"child", "refine"})
            return sub(node.get("child")).smooth(_int(node, "refine", 1, 4, 2))
    except K.GeometryError as exc:
        raise DslError(f"{op}: {exc}") from exc
    raise DslError(f"phép '{op}' không nằm trong danh sách được phép")


def compile_dsl(node: Any) -> K.Solid:
    solid = compile_node(node)
    if solid.is_empty:
        raise DslError("kết quả DSL rỗng")
    lo, hi = solid.bounds()
    if not (np.isfinite(lo).all() and np.isfinite(hi).all()):
        raise DslError("kết quả DSL có tọa độ không hữu hạn")
    return solid


ALLOWED_OPS = ["box", "cylinder", "cone", "sphere", "capsule", "ellipsoid", "torus", "extrude", "revolve", "sweep", "tube",
               "loft", "hull", "union", "intersect", "subtract", "translate", "rotate", "mirror", "scale", "array",
               "linear_array", "hole", "thread", "smooth"]

DSL_GUIDE = """CAD DSL (JSON, mm, trục X trước / Y trái / Z lên). Mỗi nút: {"op": ...}. Phép hợp lệ:
box{size:[x,y,z], fillet?, chamfer?} (tâm ở gốc) · cylinder{radius, height, radius_top?, fillet?, center?} (đáy z=0, trục Z)
· cone{radius, height, radius_top?} · sphere{radius} · ellipsoid{radii:[rx,ry,rz]} (tâm gốc) · capsule{radius, length} (dọc Z,
tâm gốc) · torus{major, minor} (nằm trong mặt XY) · extrude{profile, height, twist?, scale_top?:[sx,sy], holes?:[profile...]}
(profile trong mặt XY, đùn dọc +Z) · revolve{profile, degrees?} (profile: x = bán kính ≥ 0, y = chiều cao Z; xoay quanh Z)
· sweep{profile, path:[[x,y,z]...], scales?, twist?} (quét tiết diện dọc đường cong mượt) · tube{path:[[x,y,z]...], radius,
scales?, rounded_ends?} (ống tròn đặc dọc đường cong: quai, dây, tay vịn) · loft{sections:[profile...], positions:[z...],
offsets?:[[x,y]...]} (nối các tiết diện theo Z) · hull{children} (bao lồi — ghép cầu/ellipsoid thành khối hữu cơ mượt)
· union{children} · intersect{children} · subtract{base, cut:[...]} · translate{offset:[x,y,z], child}
· rotate{angles:[x,y,z] độ, child, center?} · mirror{normal, child, keep_original?} · scale{factors:[sx,sy,sz], child}
· array{count, axis?, child, start_angle?} (lặp quanh trục qua gốc) · linear_array{count, step:[dx,dy,dz], child}
· hole{target, diameter, depth, position, axis?} · thread{major_diameter, pitch, length} · smooth{child, refine 1-4}
Profile: {shape:"circle",radius} | {shape:"rect",width,height,corner_radius?} | {shape:"superellipse",width,height,exponent}
| {shape:"naca",code:"2412",chord} | {shape:"polygon",points:[[x,y]...], fillet?: số hoặc mảng, chamfer?, spline?}."""
