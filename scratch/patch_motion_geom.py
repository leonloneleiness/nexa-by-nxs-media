from pathlib import Path

p = Path("nexa/three_d/motion.py")
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:80], s.count(a))
    s = s.replace(a, b)


rep("""Tâm quay của bộ phận quay tròn lấy từ trọng tâm bề mặt lưới (`centroid`) vì tâm hộp bao lệch khỏi trục với cánh quạt
3 lá, bánh có nan lẻ…; thiếu lưới thì theo trục của cha đồng trục (motor, moay-ơ).
""", """Tâm quay lấy từ hình học thật (`MeshGeom`) chứ không từ tâm hộp bao: bộ phận quay tròn quay quanh trọng tâm bề mặt
(tâm hộp bao lệch trục với cánh quạt 3 lá…); khớp bản lề quay quanh tâm vùng tiếp xúc với bộ phận cha (đế cột vai robot,
lỗ chốt tay gầu…). Template đặt `pivot` tường minh thì dùng pivot. Thiếu lưới → trục cha đồng trục / ước lượng hộp bao.
""")
rep("""import numpy as np
""", """import numpy as np
from scipy.spatial import cKDTree
""")
rep("""    __slots__ = ("id", "cat", "parent", "axis", "lo", "hi", "c", "size", "name")
""", """    __slots__ = ("id", "cat", "parent", "axis", "lo", "hi", "c", "size", "name", "pivot")
""")
rep("""        self.name = f"{p.id} {p.name_en or ''}".lower()
""", """        self.name = f"{p.id} {p.name_en or ''}".lower()
        # pivot tường minh của template (khác tâm hộp bao — mặc định của manifest) = tâm khớp thật
        pv = getattr(p, "pivot", None)
        pv = np.asarray(list(pv), dtype=float) if pv is not None else None
        span = float(np.max(self.size)) if self.size.size else 0.0
        ok = pv is not None and pv.shape == (3,) and bool(np.all(np.isfinite(pv)))
        self.pivot = pv if ok and float(np.linalg.norm(pv - self.c)) > 1e-3 * max(span, 1e-6) else None
""")
rep('''Centroid = Callable[[str], "np.ndarray | None"]
''', '''MeshLoader = Callable[[str], "tuple[np.ndarray, np.ndarray] | None"]


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
''')
rep("""    def __init__(self, category: str, parts: list[Any], centroid: Centroid | None = None) -> None:
        self.category = (category or "").lower()
        self.centroid = centroid""", """    def __init__(self, category: str, parts: list[Any], geom: MeshGeom | None = None) -> None:
        self.category = (category or "").lower()
        self.geom = geom""")
rep("""        a = axis / max(1e-9, float(np.linalg.norm(axis)))
        span = float(np.max(p.size))
        ref = None
        g = None
        if self.centroid is not None:
            try:
                g = self.centroid(p.id)
            except Exception:  # noqa: BLE001 — lưới hỏng thì dùng cách dự phòng
                g = None
        if g is not None""", """        a = axis / max(1e-9, float(np.linalg.norm(axis)))
        if p.pivot is not None:
            return p.pivot.copy()
        span = float(np.max(p.size))
        ref = None
        g = self.geom.centroid(p.id) if self.geom is not None else None
        if g is not None""")
rep("""        if ref is None:
            return p.c.copy()
        d = ref - p.c
        return p.c + d - np.dot(d, a) * a

    def hinge(self, p: _P, axis: np.ndarray) -> np.ndarray:
        \"\"\"Tâm bản lề của bộ phận quay quanh trục (khi template không đặt pivot): khớp → tâm chính nó; bộ phận có cha là
        khớp → tâm khớp cha; còn lại dời tâm ra mặt hướng về cha theo cạnh vuông góc dài nhất, cạnh còn lại kẹp tâm cha.\"\"\"
        par = self.parent(p)
""", """        return self._on_axis(p, ref, a)

    @staticmethod
    def _on_axis(p: _P, ref: np.ndarray | None, a: np.ndarray) -> np.ndarray:
        \"\"\"Điểm trên trục: phần vuông góc trục theo `ref`, phần dọc trục giữ tâm hộp bao.\"\"\"
        if ref is None:
            return p.c.copy()
        a = a / max(1e-9, float(np.linalg.norm(a)))
        d = np.asarray(ref, dtype=float) - p.c
        return p.c + d - np.dot(d, a) * a

    def hinge(self, p: _P, axis: np.ndarray) -> np.ndarray:
        \"\"\"Tâm bản lề của bộ phận quay quanh trục: pivot tường minh của template; không có thì tâm vùng tiếp xúc với cha
        (đo trên lưới); thiếu lưới thì ước lượng hộp bao — khớp → tâm chính nó; cha là khớp → tâm khớp cha; còn lại dời
        tâm ra mặt hướng về cha theo cạnh vuông góc dài nhất, cạnh còn lại kẹp tâm cha.\"\"\"
        if p.pivot is not None:
            return p.pivot.copy()
        par = self.parent(p)
        if par is not None and self.geom is not None:
            g = self.geom.contact(p.id, par.id, float(min(np.max(p.size), np.max(par.size))))
            if g is not None:
                return self._on_axis(p, g, axis)
""")
rep("""def infer_motions(category: str, parts: list[Any], centroid: Centroid | None = None) -> tuple[dict[str, list[dict]], str]:
    \"\"\"Trả về ({part_id: chuỗi chuyển động}, chế độ "parts" | "turntable" | "none"). `centroid(part_id)` → trọng tâm bề
    mặt lưới (toạ độ asset, mm) hoặc None; chỉ gọi cho bộ phận quay tròn.\"\"\"
    if not parts:
        return {}, "none"
    chains = _Builder(category, parts, centroid).build()""", """def infer_motions(category: str, parts: list[Any], geom: MeshGeom | None = None) -> tuple[dict[str, list[dict]], str]:
    \"\"\"Trả về ({part_id: chuỗi chuyển động}, chế độ "parts" | "turntable" | "none"). `geom` cho lưới thật để đặt tâm
    quay/bản lề đúng; None → chỉ ước lượng từ hộp bao.\"\"\"
    if not parts:
        return {}, "none"
    chains = _Builder(category, parts, geom).build()""")
p.write_text(s, encoding="utf-8")
print("ok")
