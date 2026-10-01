"""Suy ra chuyển động cơ bản cho từng bộ phận (quay/dao động/trượt) từ loại mô hình, loại bộ phận, trục khớp và hộp bao.

Chạy lúc mở viewer nên áp dụng cho cả mô hình cũ trong kho, mô hình CAD DSL và cloud. Toạ độ asset (+Y lên, +Z trước,
+X trái, mm), góc bằng độ. Mỗi bộ phận nhận một CHUỖI chuyển động: của chính nó trước, rồi của tổ tiên (đã lọc theo
`carry`), để QML ghép thành một phép biến đổi mỗi khung hình:
  spin  {a, c, s, carry}                 — quay liên tục s °/s quanh trục a qua tâm c
  swing {a, c, amp, off, per, ph, carry} — góc = off + amp·sin(2π·τ/per + ph)
  slide {a, amp, off, per, ph}           — dời = (off + amp·sin(2π·τ/per + ph))·a
carry "all": mọi con cháu đi theo; "rot": chỉ con cháu đồng quay (bánh răng, puly, cánh…) đi theo.
Tâm quay lấy từ hình học thật (`MeshGeom`) chứ không từ tâm hộp bao: bộ phận quay tròn quay quanh trọng tâm bề mặt
(tâm hộp bao lệch trục với cánh quạt 3 lá…); khớp bản lề quay quanh tâm vùng tiếp xúc với bộ phận cha (đế cột vai robot,
lỗ chốt tay gầu…). Template đặt `pivot` tường minh thì dùng pivot. Thiếu lưới → trục cha đồng trục / ước lượng hộp bao.
Không bộ phận nào chuyển động → cả mô hình xoay chậm như bàn xoay trưng bày.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Iterable

import numpy as np
from scipy.spatial import cKDTree

CO_ROT = {"gear", "pulley", "sprocket", "impeller", "rotor_blade", "blade", "spinner", "hub", "rotor_hub",
          "coupling_hub", "spider", "propeller", "shaft", "rotor", "fan_rotor", "rim", "tire", "tyre", "brake_disc",
          "spoke", "flywheel", "cam"}
# chi tiết ghép chặt: luôn đi theo bộ phận chúng bắt vào, kể cả khi bộ phận đó chỉ cho con đồng quay theo (carry "rot")
FASTENERS = {"screw", "set_screw", "bolt", "nut", "washer", "key", "pin", "fastener", "rivet", "circlip"}
ROT_ROOTS = {"shaft", "gear", "pulley", "sprocket", "impeller", "coupling_hub", "rotor", "fan_rotor", "hub",
             "rotor_hub", "flywheel"}
WHEELS = {"wheel", "wheelset"}
FAST_SPIN = {"propeller": 720.0, "rotor": 600.0, "fan_rotor": 600.0}
BASE_SPIN = 120.0
MODEL_SPIN = {"helicopter": 420.0, "wind_turbine": 30.0, "centrifugal_pump": 360.0, "stepper_motor": 90.0,
              "shaft_coupling": 90.0}


class _P:
    __slots__ = ("id", "cat", "parent", "axis", "lo", "hi", "c", "size", "name", "pivot")

    def __init__(self, p: Any) -> None:
        self.id = p.id
        self.cat = (p.category or "").lower()
        self.parent = p.parent_id or None
        self.axis = _unit(p.joint_axis) if p.joint_axis is not None else None
        self.lo = np.asarray(p.bounds.min, dtype=float)
        self.hi = np.asarray(p.bounds.max, dtype=float)
        self.c = (self.lo + self.hi) / 2
        self.size = self.hi - self.lo
        self.name = f"{p.id} {p.name_en or ''}".lower()
        # pivot tường minh của template (khác tâm hộp bao — mặc định của manifest) = tâm khớp thật
        pv = getattr(p, "pivot", None)
        pv = np.asarray(list(pv), dtype=float) if pv is not None else None
        span = float(np.max(self.size)) if self.size.size else 0.0
        ok = pv is not None and pv.shape == (3,) and bool(np.all(np.isfinite(pv)))
        self.pivot = pv if ok and float(np.linalg.norm(pv - self.c)) > 1e-3 * max(span, 1e-6) else None


def _unit(v: Iterable[float] | None) -> np.ndarray | None:
    if v is None:
        return None
    a = np.asarray(list(v), dtype=float)
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-9 else None


def _canon(a: np.ndarray) -> np.ndarray:
    """Đổi dấu để thành phần lớn nhất dương — trục ±X đều thành +X."""
    return -a if a[int(np.argmax(np.abs(a)))] < 0 else a


def _major(a: np.ndarray) -> int | None:
    i = int(np.argmax(np.abs(a)))
    return i if abs(a[i]) > 0.97 else None


def _sym_axis(size: np.ndarray, tol: float = 0.2) -> int | None:
    """Trục đối xứng tròn: trục mà hai kích thước vuông góc gần bằng nhau (trong tol). None nếu không tròn."""
    best, err = None, tol
    for i in range(3):
        j, k = [x for x in range(3) if x != i]
        m = max(size[j], size[k], 1e-9)
        e = abs(size[j] - size[k]) / m
        if e <= err:
            best, err = i, e
    return best


def _axis_vec(i: int) -> np.ndarray:
    v = np.zeros(3)
    v[i] = 1.0
    return v


def _radius(p: _P, axis: np.ndarray) -> float:
    i = _major(axis)
    if i is None:
        return float(np.max(p.size)) / 2
    return float(max(p.size[j] for j in range(3) if j != i)) / 2


def surface_centroid(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray | None:
    """Trọng tâm bề mặt (theo diện tích tam giác) — không phụ thuộc mật độ lưới, nằm trên trục đối xứng quay."""
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    if len(v) == 0:
        return None
    if len(f) == 0:
        return v.mean(axis=0)
    t = v[f]
    area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    total = float(area.sum())
    if total <= 1e-12:
        return v.mean(axis=0)
    return (t.mean(axis=1) * area[:, None]).sum(axis=0) / total


def _r(v: np.ndarray | Iterable[float]) -> list[float]:
    return [round(float(x), 4) for x in v]


def spin(a: np.ndarray, c: np.ndarray, s: float, carry: str = "rot") -> dict:
    return {"t": "spin", "a": _r(a), "c": _r(c), "s": round(float(s), 3), "carry": carry}


def swing(a: np.ndarray, c: np.ndarray, amp: float, per: float, ph: float = 0.0, off: float = 0.0,
          carry: str = "all") -> dict:
    return {"t": "swing", "a": _r(a), "c": _r(c), "amp": round(float(amp), 3), "off": round(float(off), 3),
            "per": round(float(per), 3), "ph": round(float(ph), 4), "carry": carry}


def slide(a: np.ndarray, amp: float, per: float, ph: float = 0.0, off: float = 0.0) -> dict:
    return {"t": "slide", "a": _r(a), "amp": round(float(amp), 3), "off": round(float(off), 3),
            "per": round(float(per), 3), "ph": round(float(ph), 4), "carry": "all"}


MeshLoader = Callable[[str], "tuple[np.ndarray, np.ndarray] | None"]


class MeshGeom:
    """Truy vấn hình học lưới từng bộ phận (toạ độ asset, mm), nạp lười qua `loader(part_id) → (đỉnh, mặt) | None`."""

    SAMPLES = 6000

    def __init__(self, loader: MeshLoader) -> None:
        self.loader = loader
        self._mesh: dict[str, tuple[np.ndarray, np.ndarray] | None] = {}
        self._samples: dict[str, tuple[np.ndarray, float] | None] = {}
        self._tree: dict[str, cKDTree] = {}

    def mesh(self, pid: str) -> tuple[np.ndarray, np.ndarray] | None:
        if pid not in self._mesh:
            try:
                m = self.loader(pid)
            except Exception:  # noqa: BLE001 — lưới hỏng/thiếu thì dùng ước lượng hộp bao
                m = None
            if m is not None:
                v = np.asarray(m[0], dtype=float).reshape(-1, 3)
                f = np.asarray(m[1], dtype=np.int64).reshape(-1, 3)
                ok = len(v) and len(f) and bool(np.all(np.isfinite(v))) and int(f.min()) >= 0 and int(f.max()) < len(v)
                m = (v, f) if ok else None
            self._mesh[pid] = m
        return self._mesh[pid]

    def centroid(self, pid: str) -> np.ndarray | None:
        m = self.mesh(pid)
        return surface_centroid(*m) if m is not None else None

    def samples(self, pid: str) -> tuple[np.ndarray, float] | None:
        """Điểm rải đều theo diện tích trên bề mặt (kèm đỉnh lưới) + khoảng cách trung bình giữa các điểm."""
        if pid not in self._samples:
            m = self.mesh(pid)
            out = None
            if m is not None:
                v, f = m
                t = v[f]
                area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) / 2
                total = float(area.sum())
                if total > 1e-12:
                    rng = np.random.default_rng(0)
                    idx = rng.choice(len(f), self.SAMPLES, p=area / total)
                    r1, r2 = rng.random(self.SAMPLES), rng.random(self.SAMPLES)
                    flip = r1 + r2 > 1
                    r1[flip], r2[flip] = 1 - r1[flip], 1 - r2[flip]
                    tt = t[idx]
                    pts = tt[:, 0] + (tt[:, 1] - tt[:, 0]) * r1[:, None] + (tt[:, 2] - tt[:, 0]) * r2[:, None]
                    out = (pts, math.sqrt(total / self.SAMPLES))
            self._samples[pid] = out
        return self._samples[pid]

    def contact(self, pid: str, other: str, size: float) -> np.ndarray | None:
        """Tâm vùng bề mặt của `pid` nằm sát `other` (trong ~2% kích thước bộ phận nhỏ hơn) — nằm trên trục khớp nối hai
        bộ phận (mặt đầu ống, đế cột, lỗ chốt…). None nếu không chạm."""
        a, b = self.samples(pid), self.samples(other)
        if a is None or b is None:
            return None
        if other not in self._tree:
            self._tree[other] = cKDTree(b[0])
        eps = max(0.02 * size, 0.75 * max(a[1], b[1]), 1e-6)
        d = self._tree[other].query(a[0], k=1, distance_upper_bound=eps)[0]
        near = a[0][np.isfinite(d)]
        return near.mean(axis=0) if len(near) >= 8 else None


class _Builder:
    def __init__(self, category: str, parts: list[Any], geom: MeshGeom | None = None) -> None:
        self.category = (category or "").lower()
        self.geom = geom
        self.ps = [_P(p) for p in parts]
        self.by = {p.id: p for p in self.ps}
        for p in self.ps:
            if p.parent and p.parent not in self.by:
                p.parent = None
        self.kids: dict[str, list[_P]] = {}
        for p in self.ps:
            if p.parent:
                self.kids.setdefault(p.parent, []).append(p)
        self.own: dict[str, dict] = {}

    # ----- tiện ích -----
    def parent(self, p: _P) -> _P | None:
        return self.by.get(p.parent) if p.parent else None

    def has(self, *words: str, p: _P) -> bool:
        return any(w in p.name for w in words)

    def hub(self, p: _P, axis: np.ndarray) -> np.ndarray:
        """Tâm quay (điểm trên trục) của bộ phận quay tròn quanh `axis`. Thành phần dọc trục giữ tâm hộp bao."""
        a = axis / max(1e-9, float(np.linalg.norm(axis)))
        if p.pivot is not None:
            return p.pivot.copy()
        span = float(np.max(p.size))
        ref = None
        g = self.geom.centroid(p.id) if self.geom is not None else None
        if g is not None and np.all(np.isfinite(g)) and np.all(g >= p.lo - 1e-6 * span - 1e-9)                 and np.all(g <= p.hi + 1e-6 * span + 1e-9):
            ref = np.asarray(g, dtype=float)
        else:
            par = self.parent(p)
            if par is not None and _major(a) is not None and _sym_axis(par.size, 0.15) == _major(a):
                d = par.c - p.c
                off = d - np.dot(d, a) * a
                if float(np.linalg.norm(off)) <= 0.35 * span:
                    ref = par.c
        return self._on_axis(p, ref, a)

    @staticmethod
    def _round(p: _P, a: np.ndarray) -> bool:
        """Tròn đều quanh trục bản lề (khớp trụ, mâm tròn): quay tại chỗ quanh tâm hộp bao."""
        i = _major(a)
        return i is not None and _sym_axis(p.size, 0.03) == i

    @staticmethod
    def _on_axis(p: _P, ref: np.ndarray | None, a: np.ndarray) -> np.ndarray:
        """Điểm trên trục: phần vuông góc trục theo `ref`, phần dọc trục giữ tâm hộp bao."""
        if ref is None:
            return p.c.copy()
        a = a / max(1e-9, float(np.linalg.norm(a)))
        d = np.asarray(ref, dtype=float) - p.c
        return p.c + d - np.dot(d, a) * a

    def hinge(self, p: _P, axis: np.ndarray) -> np.ndarray:
        """Tâm bản lề của bộ phận quay quanh trục: pivot tường minh của template; không có thì tâm vùng tiếp xúc với cha
        (đo trên lưới); thiếu lưới thì ước lượng hộp bao — khớp → tâm chính nó; cha là khớp → tâm khớp cha; còn lại dời
        tâm ra mặt hướng về cha theo cạnh vuông góc dài nhất, cạnh còn lại kẹp tâm cha."""
        if p.pivot is not None:
            return p.pivot.copy()
        if self._round(p, axis):
            return p.c.copy()
        par = self.parent(p)
        if par is not None and self.geom is not None:
            g = self.geom.contact(p.id, par.id, float(min(np.max(p.size), np.max(par.size))))
            if g is not None:
                return self._on_axis(p, g, axis)
        if p.cat == "joint" or par is None:
            return p.c.copy()
        if par.cat == "joint":
            return par.c.copy()
        i = _major(axis)
        if i is None:
            return p.c.copy()
        perp = [j for j in range(3) if j != i]
        big = max(perp, key=lambda j: p.size[j])
        other = perp[0] if perp[1] == big else perp[1]
        c = p.c.copy()
        c[big] = p.hi[big] if par.c[big] > p.c[big] else p.lo[big]
        c[other] = min(max(par.c[other], p.lo[other]), p.hi[other])
        return c

    def side(self, p: _P) -> float:
        """+1 trái (asset +X), -1 phải."""
        if "left" in p.name:
            return 1.0
        if "right" in p.name:
            return -1.0
        return 1.0 if p.c[0] >= 0 else -1.0

    def front(self, p: _P) -> bool:
        return "front" in p.name or ("rear" not in p.name and p.c[2] >= 0)

    # ----- quy tắc -----
    def build(self) -> dict[str, list[dict]]:
        cat = self.category
        rules = {"humanoid": self.humanoid, "quadruped": self.quadruped, "robot_arm": self.robot_arm,
                 "excavator": self.excavator, "forklift": self.forklift, "crane": self.crane,
                 "fixed_wing": self.fixed_wing, "ball_valve": self.ball_valve, "cylinder": self.cylinder,
                 "ball_screw": self.ball_screw, "linear_guide": self.linear_guide, "motorbike": self.motorbike,
                 "cubesat": self.cubesat, "agv": self.agv, "fdm_printer": self.fdm_printer, "cnc_router": self.cnc_router,
                 "server_rack": self.server_rack, "electrical_enclosure": self.electrical_enclosure}
        self.spinners()
        self.wheels()
        self.drivetrain()
        self.bearing()
        if cat in rules:
            rules[cat]()
        chains = self.chains()
        if not any(chains.values()):
            chains = self.turntable()
        return chains

    def spinners(self) -> None:
        uav = self.category == "uav"
        for p in self.ps:
            if p.cat in ("propeller",) or (p.cat in ("rotor", "fan_rotor", "lidar", "brush")):
                axis = p.axis
                if axis is None:
                    i = _sym_axis(p.size, 0.25 if p.cat in ("brush", "propeller") else 0.15)
                    if p.cat == "brush" and i is None:
                        continue
                    if i is None:
                        if p.cat == "propeller":
                            i = int(np.argmin(p.size))
                        else:
                            continue
                    if p.cat == "propeller" and p.size[i] > 0.6 * max(p.size):
                        i = int(np.argmin(p.size))
                    axis = _axis_vec(i)
                axis = _canon(axis)
                if p.cat == "lidar":
                    s = 240.0
                elif p.cat == "brush":
                    s = 360.0 if "side" in p.name else -300.0
                else:
                    s = FAST_SPIN.get(p.cat, 600.0)
                if uav and p.cat == "propeller":
                    diag = ("front_left" in p.id or "rear_right" in p.id)
                    s = s if diag else -s
                self.own[p.id] = spin(axis, self.hub(p, axis), s)
        for p in self.ps:
            if p.cat == "rotor_hub":
                axis = _canon(p.axis if p.axis is not None else _axis_vec(int(np.argmin(p.size))))
                tail = "tail" in p.name
                s = MODEL_SPIN.get(self.category, 420.0) * (2.6 if tail else 1.0)
                self.own[p.id] = spin(axis, self.hub(p, axis), s)

    def wheels(self) -> None:
        ws = []
        for p in self.ps:
            if p.cat not in WHEELS and not (p.cat == "tire" and self.parent(p) and self.parent(p).cat not in WHEELS):
                continue
            i = _major(p.axis) if p.axis is not None else None
            if i is None:
                i = _sym_axis(p.size, 0.2)
                if i is None:
                    continue
                j, k = [x for x in range(3) if x != i]
                if p.size[i] > 0.9 * min(p.size[j], p.size[k]) and p.cat != "wheelset":
                    continue
            ws.append((p, i))
        if not ws:
            return
        rmax = max(_radius(p, _axis_vec(i)) for p, i in ws)
        for p, i in ws:
            r = max(1e-6, _radius(p, _axis_vec(i)))
            axis = _axis_vec(i)
            # lăn tới trước (+Z): điểm trên cùng phải chạy về +Z → quay dương quanh +X
            if i == 0:
                s = 200.0 * rmax / r
            else:
                s = 160.0
            self.own[p.id] = spin(axis, self.hub(p, axis), s)

    def _groups(self) -> dict[str, list[_P]]:
        """Nhóm quay: gốc là bộ phận quay (trục, bánh răng…) mà cha không phải bộ phận đồng quay."""
        groups: dict[str, list[_P]] = {}
        for p in self.ps:
            if p.id in self.own:
                continue
            if p.cat not in ROT_ROOTS or (p.cat == "hub" and self.category != "wind_turbine"):
                continue
            if p.cat in ("shaft",) and p.axis is None and not any(k.cat in CO_ROT for k in self.kids.get(p.id, [])):
                continue
            par = self.parent(p)
            if par is not None and (par.cat in CO_ROT or par.id in self.own):
                continue
            members, stack = [p], list(self.kids.get(p.id, []))
            while stack:
                k = stack.pop()
                if k.cat in CO_ROT:
                    members.append(k)
                    stack.extend(self.kids.get(k.id, []))
            groups[p.id] = members
        return groups

    def _group_axis(self, root: _P, members: list[_P]) -> np.ndarray | None:
        for m in members:
            if m.axis is not None:
                return _canon(m.axis)
        i = _sym_axis(root.size, 0.15)
        return _axis_vec(i) if i is not None else None

    def drivetrain(self) -> None:
        groups = self._groups()
        if not groups:
            return
        axes = {g: self._group_axis(self.by[g], ms) for g, ms in groups.items()}
        groups = {g: ms for g, ms in groups.items() if axes[g] is not None}
        if not groups:
            return
        wheels_of = {g: [m for m in ms if m.cat in ("gear", "pulley", "sprocket")] for g, ms in groups.items()}
        edges: dict[str, list[tuple[str, float]]] = {g: [] for g in groups}
        gl = list(groups)
        belt = any(p.cat in ("belt", "chain") for p in self.ps)
        for i, g1 in enumerate(gl):
            for g2 in gl[i + 1:]:
                if abs(float(np.dot(axes[g1], axes[g2]))) < 0.97:
                    continue
                a = axes[g1]
                for w1 in wheels_of[g1]:
                    for w2 in wheels_of[g2]:
                        r1, r2 = _radius(w1, a), _radius(w2, a)
                        d = w2.c - w1.c
                        dp = float(np.linalg.norm(d - np.dot(d, a) * a))
                        if w1.cat == "gear" and w2.cat == "gear":
                            if abs(dp - (r1 + r2)) <= 0.2 * (r1 + r2):
                                edges[g1].append((g2, -r1 / r2))
                                edges[g2].append((g1, -r2 / r1))
                        elif belt and w1.cat == w2.cat and w1.cat in ("pulley", "sprocket"):
                            edges[g1].append((g2, r1 / r2))
                            edges[g2].append((g1, r2 / r1))
        speed: dict[str, float] = {}
        base = MODEL_SPIN.get(self.category, BASE_SPIN)

        def score(g: str) -> tuple:
            n = self.by[g].name + " " + " ".join(m.name for m in groups[g])
            drv = 0 if ("driver" in n or "_in" in g or "input" in n or "motor" in n) else 1
            rr = min([_radius(w, axes[g]) for w in wheels_of[g]] or [1e9])
            return (drv, rr)
        for start in sorted(gl, key=score):
            if start in speed:
                continue
            speed[start] = base
            q = [start]
            while q:
                g = q.pop(0)
                for h, k in edges[g]:
                    if h not in speed:
                        speed[h] = speed[g] * k
                        q.append(h)
        for g, ms in groups.items():
            root = self.by[g]
            self.own[g] = spin(axes[g], self.hub(root, axes[g]), speed[g])

    def bearing(self) -> None:
        rings = [p for p in self.ps if p.cat == "bearing_ring" and p.axis is not None]
        if not rings:
            return
        ring = rings[0]
        axis = _canon(ring.axis)
        s = MODEL_SPIN.get(self.category, BASE_SPIN)
        c = self.hub(ring, axis)
        self.own[ring.id] = spin(axis, c, s)
        for p in self.ps:
            if p.cat in ("ball", "roller", "cage"):
                self.own[p.id] = spin(axis, c, s * 0.4, carry="all")

    def humanoid(self) -> None:
        per = 1.6
        x = np.array([1.0, 0.0, 0.0])
        y = np.array([0.0, 1.0, 0.0])
        for p in self.ps:
            if p.cat != "joint":
                continue
            ph = 0.0 if self.side(p) > 0 else math.pi
            n = p.name
            if "hip" in n:
                self.own[p.id] = swing(x, p.c, -18, per, ph)
            elif "knee" in n:
                self.own[p.id] = swing(x, p.c, 12, per, ph + math.pi / 2, off=14)
            elif "ankle" in n:
                self.own[p.id] = swing(x, p.c, 6, per, ph)
            elif "shoulder" in n:
                self.own[p.id] = swing(x, p.c, 16, per, ph)
            elif "elbow" in n:
                self.own[p.id] = swing(x, p.c, 6, per, ph, off=-18)
            elif "neck" in n:
                self.own[p.id] = swing(y, p.c, 10, per * 2, 0)
            elif "abdomen" in n or "waist" in n:
                self.own[p.id] = swing(y, p.c, 5, per, 0)

    def quadruped(self) -> None:
        per = 0.8
        x = np.array([1.0, 0.0, 0.0])
        for p in self.ps:
            if p.cat != "joint" or "hip_ab" in p.id:
                continue
            left, front = self.side(p) > 0, self.front(p)
            ph = 0.0 if left == front else math.pi
            if "knee" in p.name:
                self.own[p.id] = swing(x, p.c, 12, per, ph + math.pi / 2)
            elif "hip" in p.name:
                self.own[p.id] = swing(x, p.c, 16, per, ph)

    def robot_arm(self) -> None:
        plan = {"shoulder": (40, 9.0, 0.0), "upper_arm": (18, 7.0, 1.0), "elbow": (22, 6.0, 2.0),
                "forearm": (22, 6.0, 2.0), "wrist_1": (25, 5.0, 0.5), "wrist_2": (30, 5.0, 3.0),
                "wrist_3": (90, 4.0, 1.5)}
        used_elbow = any(p.id == "forearm" and p.axis is not None for p in self.ps)
        for p in self.ps:
            if p.axis is None or p.id not in plan or (p.id == "elbow" and used_elbow):
                continue
            amp, per, ph = plan[p.id]
            a = _canon(p.axis)
            self.own[p.id] = swing(a, self.hinge(p, a), amp, per, ph)

    def excavator(self) -> None:
        plan = {"upper_structure": (25, 12.0, 0.0), "boom": (7, 6.0, 0.0), "stick": (12, 6.0, 1.2),
                "bucket": (22, 6.0, 2.4)}
        for p in self.ps:
            if p.id not in plan or p.axis is None:
                continue
            amp, per, ph = plan[p.id]
            a = _canon(p.axis)
            if p.id == "upper_structure":
                par = self.parent(p)
                c = p.c.copy()
                if par is not None:
                    c[0], c[2] = par.c[0], par.c[2]
            else:
                c = self.hinge(p, a)
            self.own[p.id] = swing(a, c, amp, per, ph)

    def forklift(self) -> None:
        up = np.array([0.0, 1.0, 0.0])
        for p in self.ps:
            if p.id == "mast_inner":
                amp = 0.18 * p.size[1]
                self.own[p.id] = slide(up, amp, 7.0, -math.pi / 2, off=amp)
            elif p.id == "carriage":
                amp = 0.12 * p.size[1]
                self.own[p.id] = slide(up, amp, 7.0, -math.pi / 2, off=amp)

    def crane(self) -> None:
        for p in self.ps:
            if p.id == "turntable" and p.axis is not None:
                a = _canon(p.axis)
                self.own[p.id] = swing(a, self.hinge(p, a), 30, 16.0)  # quanh vòng bi mâm xoay, không quanh tâm cabin
            elif p.id == "boom_base" and p.axis is not None:
                a = _canon(p.axis)
                self.own[p.id] = swing(a, self.hinge(p, a), 6, 10.0, 0.5)
            elif p.id.startswith("boom_section"):
                par = self.parent(p)
                if par is None:
                    continue
                d = _unit(p.c - par.c)
                if d is None:
                    continue
                amp = 0.08 * float(np.max(p.size))
                self.own[p.id] = slide(d, amp, 10.0, -math.pi / 2, off=amp)

    def fixed_wing(self) -> None:
        for p in self.ps:
            if p.cat != "control_surface" or p.axis is None:
                continue
            a = _canon(p.axis)
            c = self.hinge(p, a)
            if "aileron" in p.name:
                self.own[p.id] = swing(a, c, 14 * self.side(p), 3.0)
            elif "rudder" in p.name:
                self.own[p.id] = swing(a, c, 14, 4.0, 1.0)
            else:
                self.own[p.id] = swing(a, c, 12, 3.5, 0.5)

    def ball_valve(self) -> None:
        for p in self.ps:
            if p.id in ("stem", "ball") and p.axis is not None:
                self.own[p.id] = swing(_canon(p.axis), p.c, 45, 5.0, -math.pi / 2, off=45)

    def cylinder(self) -> None:
        rod = next((p for p in self.ps if p.cat == "rod" and p.axis is not None), None)
        if rod is None:
            return
        a = _canon(rod.axis)
        barrel = next((p for p in self.ps if p.cat in ("barrel", "tube")), self.parent(rod))
        ref = barrel.c if barrel is not None else np.zeros(3)
        d = a if float(np.dot(rod.c - ref, a)) >= 0 else -a
        i = _major(a)
        length = float(rod.size[i]) if i is not None else float(np.max(rod.size))
        amp = 0.15 * length
        self.own[rod.id] = slide(d, amp, 4.0, -math.pi / 2, off=amp)

    def ball_screw(self) -> None:
        shaft = next((p for p in self.ps if p.cat == "shaft" and p.axis is not None), None)
        nut = next((p for p in self.ps if "ball_nut" in p.id or ("ball nut" in p.name)), None)
        if shaft is None:
            return
        a = _canon(shaft.axis)
        per = 6.0
        self.own[shaft.id] = swing(a, shaft.c, 1440, per, carry="rot")
        if nut is not None:
            i = _major(a)
            travel = (float(shaft.size[i]) - float(nut.size[i])) if i is not None else float(np.max(shaft.size))
            amp = max(0.0, 0.3 * travel)
            self.own[nut.id] = slide(a, amp, per)

    def linear_guide(self) -> None:
        rail = max(self.ps, key=lambda p: float(np.max(p.size)))
        i = int(np.argmax(rail.size))
        a = _axis_vec(i)
        cars = [p for p in self.ps if p.cat == "carriage"]
        if not cars:
            return
        span = float(rail.hi[i] - rail.lo[i])
        lo = min(float(p.lo[i]) for p in cars)
        hi = max(float(p.hi[i]) for p in cars)
        room = min(lo - float(rail.lo[i]), float(rail.hi[i]) - hi)
        amp = max(0.0, min(room * 0.9, 0.3 * span))
        for p in cars:
            self.own[p.id] = slide(a, amp, 5.0)

    def motorbike(self) -> None:
        fork = next((p for p in self.ps if p.cat == "fork" and p.axis is not None), None)
        if fork is not None:
            a = _canon(fork.axis)
            self.own[fork.id] = swing(a, self.hinge(fork, a), 10, 5.0)  # quanh ống cổ lái

    def cubesat(self) -> None:
        for p in self.ps:
            if p.cat == "solar_panel" and p.axis is not None:
                a = _canon(p.axis)
                self.own[p.id] = swing(a, self.hinge(p, a), 12 * self.side(p), 6.0)

    def agv(self) -> None:
        for p in self.ps:
            if p.cat == "lift" and p.axis is not None:
                self.own[p.id] = swing(_canon(p.axis), p.c, 35, 10.0)

    # ----- máy chế tạo: trục tuyến tính trên ray -----
    def _reparent(self, moves: dict[str, str], still: Iterable[str] = ()) -> None:
        """Đai ốc đi theo giá của con trượt (không quay theo vít), dây đai bám khung; bộ phận gộp nhiều chiếc (2 vít Y,
        4 puly góc) đứng yên — quay quanh tâm hộp bao sẽ làm chúng quay quanh nhau."""
        for pid, par in moves.items():
            if pid in self.by and par in self.by:
                self.by[pid].parent = par
                self.own.pop(pid, None)
        for pid in still:
            self.own.pop(pid, None)

    def _axes(self, plan: list[tuple[tuple[str, ...], str, float, float, str]]) -> dict[str, tuple[np.ndarray, float, float]]:
        """plan: (id con trượt, id ray, chu kỳ s, pha, kiểu). "mid" dao động quanh giữa hành trình; "up"/"down" đi một
        chiều từ vị trí gốc (đầu phun / dao không bao giờ ăn xuống bàn). Hành trình giữ con trượt nằm hẳn trên ray."""
        out = {}
        for ids, rail_id, per, ph, mode in plan:
            cars = [self.by[i] for i in ids if i in self.by]
            rail = self.by.get(rail_id)
            if not cars or rail is None or cars[0].axis is None:
                continue
            i = _major(cars[0].axis)
            if i is None:
                continue
            a = _axis_vec(i)
            back = max(0.0, min(float(c.lo[i] - rail.lo[i]) for c in cars))
            fwd = max(0.0, min(float(rail.hi[i] - c.hi[i]) for c in cars))
            if mode == "mid":
                amp, off = 0.85 * (fwd + back) / 2, (fwd - back) / 2
            elif mode == "up":
                amp = 0.2 * fwd
                off, ph = amp, -math.pi / 2
            else:
                amp = 0.2 * back
                off, ph = -amp, math.pi / 2
            if amp <= 1e-6:
                continue
            for c in cars:
                self.own[c.id] = slide(a, amp, per, ph, off)
            out[ids[0]] = (a, per, ph)                                  # pha thực (vít me quay đồng bộ)
        return out

    def _screw(self, pid: str, per: float, ph: float, *also: str) -> None:
        """Vít me (và khớp nối) quay qua lại đồng bộ với con trượt nó kéo."""
        for q in (pid, *also):
            p = self.by.get(q)
            if p is None or p.axis is None:
                continue
            a = _canon(p.axis)
            self.own[q] = swing(a, self.hub(p, a), 1440, per, ph, carry="rot")

    def fdm_printer(self) -> None:
        corexy = "corner_plates" in self.by
        if corexy:
            self._reparent({"belt_a": "corner_plates", "belt_b": "corner_plates"}, still=("corner_idlers", "gantry_idlers"))
            self._axes([(("y_carriages",), "y_rails", 3.2, 0.0, "mid"), (("x_carriage",), "x_rail", 2.2, 0.7, "mid"),
                        (("z_carriage_l", "z_carriage_r"), "z_rail_l", 14.0, 0.0, "down")])
        else:
            self._reparent({"y_belt": "y_brackets", "x_belt": "x_beam"})
            self._axes([(("y_carriages",), "y_rail", 3.0, 0.0, "mid"), (("x_carriage",), "x_rail", 2.2, 0.7, "mid"),
                        (("z_carriage_l", "z_carriage_r"), "z_rail_l", 14.0, 0.0, "up")])

    def _doors(self, amp: float = 40.0, per: float = 12.0) -> None:
        """Cửa tủ hé mở ra ngoài quanh bản lề rồi đóng lại; chiều mở chọn sao cho tâm cửa rời xa tâm tủ."""
        lo = np.min([p.lo for p in self.ps], axis=0)
        hi = np.max([p.hi for p in self.ps], axis=0)
        mid = (lo + hi) / 2
        for p in self.ps:
            if p.cat != "door" or p.axis is None:
                continue
            a = _canon(p.axis)
            c = self.hinge(p, a)
            k = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])

            def gap(deg: float) -> float:
                t = math.radians(deg)
                rot = np.eye(3) + math.sin(t) * k + (1 - math.cos(t)) * (k @ k)   # Rodrigues, quy tắc bàn tay phải
                return float(np.linalg.norm(rot @ (p.c - c) + c - mid))
            s = 1.0 if gap(30.0) >= gap(-30.0) else -1.0
            self.own[p.id] = swing(a, c, s * amp, per, -math.pi / 2, off=s * amp)

    def server_rack(self) -> None:
        self._doors()

    def electrical_enclosure(self) -> None:
        self._doors()

    def cnc_router(self) -> None:
        self._reparent({"y_nuts": "y_nut_brackets", "x_nut": "x_nut_bracket", "z_nut": "z_nut_bracket"},
                       still=("y_screws", "y_lock_nuts", "y_couplings"))
        ax = self._axes([(("y_carriages",), "y_rails", 9.0, 0.0, "mid"), (("x_carriages",), "x_rails", 5.0, 1.1, "mid"),
                         (("z_carriages",), "z_rails", 3.0, 0.0, "down")])          # gốc Z ở đỉnh: dao ăn xuống ≤ 40 % hành trình
        for car, screw, cpl in (("x_carriages", "x_screw", "x_coupling"), ("z_carriages", "z_screw", "z_coupling")):
            if car in ax:
                _, per, ph = ax[car]
                self._screw(screw, per, ph, cpl)
        nut = self.by.get("collet_nut")
        if nut is not None and nut.axis is None and "spindle" in self.by and self.by["spindle"].axis is not None:
            a = _canon(self.by["spindle"].axis)
            self.own[nut.id] = spin(a, self.hub(nut, a), 900.0, carry="all")    # đai ốc kẹp + dao quay theo trục chính

    # ----- ghép chuỗi -----
    def chains(self) -> dict[str, list[dict]]:
        memo: dict[str, list[dict]] = {}

        def full(p: _P, depth: int = 0) -> list[dict]:
            if p.id in memo:
                return memo[p.id]
            inherited: list[dict] = []
            par = self.parent(p)
            if par is not None and depth < 40:
                for m in full(par, depth + 1):
                    if m["carry"] == "all" or p.cat in CO_ROT or p.cat in FASTENERS:
                        inherited.append(m)
            own = self.own.get(p.id)
            out = list(inherited)
            if own is not None:
                a = np.asarray(own["a"])
                dup = own["t"] == "spin" and any(m["t"] == "spin" and abs(float(np.dot(a, m["a"]))) > 0.97
                                                 for m in inherited)
                if not dup:
                    out = [own] + inherited
            memo[p.id] = out
            return out
        return {p.id: full(p) for p in self.ps}

    def turntable(self) -> dict[str, list[dict]]:
        if not self.ps:
            return {}
        lo = np.min([p.lo for p in self.ps], axis=0)
        hi = np.max([p.hi for p in self.ps], axis=0)
        m = spin(np.array([0.0, 1.0, 0.0]), (lo + hi) / 2, 30.0, carry="all")
        m["turntable"] = True
        return {p.id: [m] for p in self.ps}


def infer_motions(category: str, parts: list[Any], geom: MeshGeom | None = None) -> tuple[dict[str, list[dict]], str]:
    """Trả về ({part_id: chuỗi chuyển động}, chế độ "parts" | "turntable" | "none"). `geom` cho lưới thật để đặt tâm
    quay/bản lề đúng; None → chỉ ước lượng từ hộp bao."""
    if not parts:
        return {}, "none"
    chains = _Builder(category, parts, geom).build()
    turn = any(m.get("turntable") for ch in chains.values() for m in ch)
    return chains, ("turntable" if turn else "parts")
