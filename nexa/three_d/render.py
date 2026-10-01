"""Render phần mềm (không cần GPU) cho 6 góc nhìn kỹ thuật, ảnh thu nhỏ và kiểm tra mặt khuất.

Kiểu "deferred": (1) Pillow tô từng tam giác (mã C) vào ảnh ID 32-bit theo thứ tự xa → gần (thuật toán họa sĩ) để
có bộ đệm hiển thị — mỗi pixel biết tam giác gần nhất; (2) numpy nội suy barycentric pháp tuyến + độ sâu cho từng
pixel và tô bóng Blinn-Phong + phản xạ môi trường giả theo vật liệu PBR (bóng mượt, không lộ cạnh đa giác).
Chi phí ≈ số tam giác + số pixel, không phụ thuộc độ phức tạp chiều sâu. Khử răng cưa bằng siêu lấy mẫu 2×.
Hoàn toàn xác định nên dùng được cho kiểm thử và cho Gemini chấm ảnh.

Chỉ số phụ: tỷ lệ pixel thấy MẶT SAU của tam giác (pháp tuyến hình học quay ra xa camera). Lưới kín hướng đúng
→ ≈ 0. Lưới thủng/thiếu mặt khuất/lật pháp tuyến → cao (quality.py dùng làm kiểm tra "không thiếu mặt sau").
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from nexa.three_d.geometry.kernel import MeshData
from nexa.three_d.models import Material

# Góc nhìn trong hệ asset (+Y lên, +Z trước, +X trái vật thể): (vị trí camera, hướng lên)
VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "front": ((0, 0, 1), (0, 1, 0)),
    "back": ((0, 0, -1), (0, 1, 0)),
    "left": ((1, 0, 0), (0, 1, 0)),
    "right": ((-1, 0, 0), (0, 1, 0)),
    "top": ((0, 1, 0), (0, 0, 1)),        # phía trước vật thể hướng lên trên ảnh
    "bottom": ((0, -1, 0), (0, 0, 1)),
    "iso": ((0.62, 0.48, 0.62), (0, 1, 0)),
}
SIX_VIEWS = ("front", "back", "left", "right", "top", "bottom")
VIEW_LABELS = {"front": "TRUOC (front)", "back": "SAU (back)", "left": "TRAI (left)", "right": "PHAI (right)",
               "top": "TREN (top)", "bottom": "DUOI (bottom)", "iso": "3/4"}


@dataclass
class RenderResult:
    image: np.ndarray            # (H, W, 3) uint8
    coverage: float              # tỷ lệ pixel có vật thể
    backface_ratio: float        # tỷ lệ pixel (vùng liền khối) thấy mặt sau


def _basis(view):
    pos, up = VIEWS[view] if isinstance(view, str) else (view, (0, 1, 0))
    f = -np.asarray(pos, float)
    f /= np.linalg.norm(f)
    u = np.asarray(up, float)
    r = np.cross(f, u)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return f, u, r


_TEX_CACHE: dict[str, np.ndarray] = {}


def _texture(root: Any, rel: str) -> np.ndarray | None:
    """Ảnh texture (tuyến tính, float32 H×W×3) từ <dự án>/<rel>; None nếu không đọc được."""
    if root is None or not rel:
        return None
    from pathlib import Path
    path = (Path(root) / rel).resolve()
    key = str(path)
    if key not in _TEX_CACHE:
        try:
            from PIL import Image
            img = Image.open(path).convert("RGB")
            if max(img.size) > 1024:                     # đủ cho ảnh kiểm tra 384–512 px, nhẹ bộ nhớ
                img.thumbnail((1024, 1024))
            _TEX_CACHE[key] = (np.asarray(img, np.float32) / 255.0) ** 2.2
        except Exception:
            _TEX_CACHE[key] = None                       # type: ignore[assignment]
        if len(_TEX_CACHE) > 16:
            _TEX_CACHE.pop(next(iter(_TEX_CACHE)))
    return _TEX_CACHE.get(key)


def _sample(tex: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Lấy màu gần nhất; UV glTF: (0,0) góc trên-trái ảnh, lặp (repeat)."""
    h, w = tex.shape[:2]
    u = np.mod(uv[:, 0], 1.0)
    v = np.mod(uv[:, 1], 1.0)
    return tex[np.clip((v * h).astype(np.int64), 0, h - 1), np.clip((u * w).astype(np.int64), 0, w - 1)]


def _shade(nrm: np.ndarray, view_dir: np.ndarray, mat: Material, albedo: np.ndarray | None = None) -> np.ndarray:
    """albedo: màu nền theo từng điểm (đã tuyến tính, đã nhân baseColorFactor) khi vật liệu có texture."""
    base = np.asarray(mat.base_color[:3], float)
    if albedo is not None:
        base = albedo
    metal = float(np.clip(mat.metallic, 0, 1))
    rough = float(np.clip(mat.roughness, 0.03, 1))
    lights = [(np.array([0.45, 0.8, 0.55]), 1.15), (np.array([-0.7, 0.3, 0.4]), 0.45), (np.array([0.1, 0.4, -0.9]), 0.55)]
    vdir = -view_dir                                   # từ bề mặt về camera
    diffuse = np.full(len(nrm), 0.16)                  # môi trường bán cầu
    diffuse += 0.12 * np.clip(nrm[:, 1], -1, 1)
    spec = np.zeros(len(nrm))
    shin = float(np.clip(2.0 / max(1e-3, rough ** 4) - 2.0, 4, 900))
    for d, inten in lights:
        l = d / np.linalg.norm(d)
        ndl = np.clip(nrm @ l, 0, None)
        diffuse += inten * ndl
        h = l + vdir
        h /= np.linalg.norm(h)
        spec += inten * np.clip(nrm @ h, 0, None) ** shin * ndl * (shin + 8) / (8 * math.pi) * 0.25
    refl = 2 * (nrm @ vdir)[:, None] * nrm - vdir     # phản xạ môi trường giả: trời sáng, sàn tối
    env = np.clip(0.35 + 0.55 * refl[:, 1], 0.04, 1.0)
    # Broad studio softboxes remain visible on curved metal and coated paint.
    # Point-light highlights alone collapse to a few pixels on smooth products.
    softbox = np.zeros(len(nrm))
    for direction, strength in (((-0.6, 0.7, 0.4), 0.65), ((0.7, 0.5, -0.4), 0.45)):
        direction = np.asarray(direction, float)
        direction /= np.linalg.norm(direction)
        softbox += strength * np.clip(refl @ direction, 0, 1) ** (6 + 18 * (1 - rough))
    env += softbox
    env_strength = (1 - rough) ** 2
    base2 = base if base.ndim == 2 else base[None, :]
    spec_color = base2 * metal + 0.04 * (1 - metal)
    col = base2 * diffuse[:, None] * (1 - metal) + spec_color * (
        spec[:, None] + env[:, None] * (0.25 + 0.75 * env_strength) * (0.4 + 0.6 * metal))
    col += np.asarray(mat.emissive, float)[None, :]
    col += float(mat.clearcoat) * softbox[:, None] * 0.12
    col = col / (1 + col * 0.35)                       # tonemap
    return np.clip(col, 0, 1) ** (1 / 2.2)             # gamma sRGB


def _rasterize(x: np.ndarray, y: np.ndarray, depth: np.ndarray, faces: np.ndarray, H: int, W: int
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mảnh (fragment) của tập tam giác tại TÂM pixel: (chỉ số pixel, độ sâu, chỉ số tam giác cục bộ).

    Mỗi tam giác sinh pixel ứng viên trong hộp bao (gom nhóm theo kích thước hộp làm tròn lũy thừa 2), kiểm tra
    trong/ngoài bằng hàm cạnh và nội suy độ sâu — hoàn toàn vector hóa bằng numpy."""
    empty = (np.zeros(0, np.int64), np.zeros(0), np.zeros(0, np.int64))
    if len(faces) == 0:
        return empty
    X, Y, Z = x[faces], y[faces], depth[faces]
    x0 = np.floor(X.min(axis=1) - 0.5).astype(np.int64)
    y0 = np.floor(Y.min(axis=1) - 0.5).astype(np.int64)
    x1 = np.floor(X.max(axis=1) - 0.5).astype(np.int64) + 1
    y1 = np.floor(Y.max(axis=1) - 0.5).astype(np.int64) + 1
    area2 = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0])
    keep = (x1 >= 0) & (y1 >= 0) & (x0 < W) & (y0 < H) & (np.abs(area2) > 1e-9)
    wq = np.maximum(1, x1 - x0 + 1)                    # nhóm theo đúng kích thước hộp bao (ít ứng viên thừa)
    hq = np.maximum(1, y1 - y0 + 1)
    key = wq * 100000 + hq
    out_p, out_z, out_t = [], [], []
    for k in np.unique(key[keep]):
        t_all = np.nonzero(keep & (key == k))[0]
        bw, bh = int(k // 100000), int(k % 100000)
        n_cand = bw * bh
        oy, ox = np.divmod(np.arange(n_cand), bw)
        for chunk in np.array_split(t_all, max(1, len(t_all) * n_cand // 2_500_000 + 1)):
            if len(chunk) == 0:
                continue
            px = x0[chunk, None] + ox[None, :]
            py = y0[chunk, None] + oy[None, :]
            cx, cy = px + 0.5, py + 0.5
            ax, ay = X[chunk, 0:1], Y[chunk, 0:1]
            bx, by = X[chunk, 1:2], Y[chunk, 1:2]
            qx, qy = X[chunk, 2:3], Y[chunk, 2:3]
            a2 = area2[chunk, None]
            w0 = ((bx - cx) * (qy - cy) - (qx - cx) * (by - cy)) / a2
            w1 = ((qx - cx) * (ay - cy) - (ax - cx) * (qy - cy)) / a2
            w2 = 1.0 - w0 - w1
            ok = (w0 >= -1e-7) & (w1 >= -1e-7) & (w2 >= -1e-7) & (px >= 0) & (py >= 0) & (px < W) & (py < H)
            if not ok.any():
                continue
            zz = w0 * Z[chunk, 0:1] + w1 * Z[chunk, 1:2] + w2 * Z[chunk, 2:3]
            out_p.append((py * W + px)[ok])
            out_z.append(zz[ok])
            out_t.append(np.broadcast_to(chunk[:, None], ok.shape)[ok])
    if not out_p:
        return empty
    return np.concatenate(out_p), np.concatenate(out_z), np.concatenate(out_t)


def _nearest(pix: np.ndarray, z: np.ndarray, t: np.ndarray, H: int, W: int) -> tuple[np.ndarray, np.ndarray]:
    """Z-buffer: (ảnh ID tam giác gần nhất, −1 = trống; ảnh độ sâu)."""
    zbuf = np.full(H * W, np.inf)
    ids = np.full(H * W, -1, np.int64)
    if len(pix):
        np.minimum.at(zbuf, pix, z)
        win = z <= zbuf[pix]
        ids[pix[win]] = t[win]
    return ids.reshape(H, W), zbuf.reshape(H, W)


def _split_large(V, N, F, MID, center, r, u, px, max_edge_px: float, T=None):
    """Chia đôi (theo cạnh dài nhất) các tam giác có cạnh chiếu dài hơn max_edge_px để hộp bao nhỏ và gọn.
    T: UV theo đỉnh (có thể NaN) — trung điểm được nội suy theo cùng cạnh."""
    if max_edge_px <= 0 or len(F) == 0:
        return (V, N, F, MID) if T is None else (V, N, F, MID, T)
    Vv, Nv = np.asarray(V), np.asarray(N)
    Tv = None if T is None else np.asarray(T)
    Pv = np.column_stack([(Vv - center) @ r, (Vv - center) @ u]) * px
    for _ in range(16):
        e = np.stack([np.linalg.norm(Pv[F[:, 1]] - Pv[F[:, 0]], axis=1), np.linalg.norm(Pv[F[:, 2]] - Pv[F[:, 1]], axis=1),
                      np.linalg.norm(Pv[F[:, 0]] - Pv[F[:, 2]], axis=1)], axis=1)
        sel = e.max(axis=1) > max_edge_px
        if not sel.any():
            break
        which = np.argmax(e[sel], axis=1)
        f = F[sel]
        rolled = np.stack([np.take_along_axis(f, ((which + k) % 3)[:, None], 1)[:, 0] for k in range(3)], axis=1)
        a, b2, c = rolled[:, 0], rolled[:, 1], rolled[:, 2]
        mid_n = Nv[a] + Nv[b2]
        mid_n /= np.maximum(np.linalg.norm(mid_n, axis=1, keepdims=True), 1e-12)
        m_idx = len(Vv) + np.arange(len(a))
        Vv = np.vstack([Vv, (Vv[a] + Vv[b2]) / 2])
        Nv = np.vstack([Nv, mid_n])
        Pv = np.vstack([Pv, (Pv[a] + Pv[b2]) / 2])
        if Tv is not None:
            Tv = np.vstack([Tv, (Tv[a] + Tv[b2]) / 2])
        F = np.vstack([F[~sel], np.column_stack([a, m_idx, c]), np.column_stack([m_idx, b2, c])])
        MID = np.concatenate([MID[~sel], MID[sel], MID[sel]])
    return (Vv, Nv, F, MID) if Tv is None else (Vv, Nv, F, MID, Tv)


def render(meshes: Sequence[tuple[MeshData, Material]], view: str = "front", size: int = 512,
           background: str | bool = "dark", bounds: tuple[np.ndarray, np.ndarray] | None = None,
           outline: bool = True, ssaa: int = 2, margin: float = 0.44, max_edge_px: float = 14.0,
           detect_holes: bool = False, texture_root: Any = None, fixed_extent: float | None = None) -> RenderResult:
    """texture_root: thư mục dự án — vật liệu có textures['base_color'] + lưới có UV được tô theo ảnh texture."""
    f, u, r = _basis(view)
    items = [(m, mat) for m, mat in meshes if m is not None and m.triangle_count]
    S = int(size) * max(1, int(ssaa))
    H = W = S
    img = np.zeros((H, W, 3))
    if background:
        # "dark": nền tối kiểu NEXA (ảnh thu nhỏ); "light": nền xám studio để AI/người xem rõ vật tối màu
        top, bot = ((np.array([0.035, 0.05, 0.09]), np.array([0.012, 0.018, 0.035])) if background != "light" else
                    (np.array([0.94, 0.95, 0.96]), np.array([0.80, 0.82, 0.85])))
        g = np.linspace(0, 1, H)[:, None]
        img[:] = (top * (1 - g) + bot * g)[:, None, :] * np.ones((1, W, 1))
    if not items:
        return RenderResult(_downsample(img, ssaa), 0.0, 0.0)
    if bounds is None:
        allv = np.vstack([m.vertices for m, _ in items])
        lo, hi = allv.min(axis=0), allv.max(axis=0)
    else:
        lo, hi = bounds
    center = (lo + hi) / 2
    corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])]) - center
    ext = max(float(np.abs(corners @ r).max()), float(np.abs(corners @ u).max()), 1e-6)
    if fixed_extent is not None:
        ext = max(float(fixed_extent), 1e-6)
    px = (W * margin) / ext
    texs = [(_texture(texture_root, (mat.textures or {}).get("base_color", "")) if m.uvs is not None else None)
            for m, mat in items]
    use_uv = any(t is not None for t in texs)
    verts, norms, faces, mids, uvs, off = [], [], [], [], [], 0
    for mi, (m, _mat) in enumerate(items):
        verts.append(m.vertices)
        norms.append(m.normals if m.normals is not None else MeshData(m.vertices, m.faces).compute_normals().normals)
        faces.append(m.faces + off)
        mids.append(np.full(len(m.faces), mi))
        if use_uv:
            uvs.append(m.uvs if (m.uvs is not None and len(m.uvs) == len(m.vertices)) else np.full((len(m.vertices), 2), np.nan))
        off += len(m.vertices)
    V, N, F, MID = np.vstack(verts), np.vstack(norms), np.vstack(faces), np.concatenate(mids)
    if use_uv:
        V, N, F, MID, TUV = _split_large(V, N, F, MID, center, r, u, px, max_edge_px, T=np.vstack(uvs))
    else:
        V, N, F, MID = _split_large(V, N, F, MID, center, r, u, px, max_edge_px)
        TUV = None
    rel = V - center
    x = rel @ r * px + W / 2
    y = H / 2 - rel @ u * px
    depth = rel @ f
    transp = np.array([items[i][1].transparent for i in range(len(items))])[MID]
    G = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])   # pháp tuyến hình học
    backface = (G @ f) > 0

    def surface(ids: np.ndarray):
        """Nội suy barycentric tại tâm pixel: (mặt nạ, tam giác, pháp tuyến)."""
        mask = ids >= 0
        t = ids[mask]
        py, pxl = np.nonzero(mask)
        qx, qy = pxl + 0.5, py + 0.5
        fa = F[t]
        x0, y0, x1, y1, x2, y2 = x[fa[:, 0]], y[fa[:, 0]], x[fa[:, 1]], y[fa[:, 1]], x[fa[:, 2]], y[fa[:, 2]]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1.0)
        w0 = np.clip(np.where(ok, ((y1 - y2) * (qx - x2) + (x2 - x1) * (qy - y2)) / den, 1 / 3), 0, 1)
        w1 = np.clip(np.where(ok, ((y2 - y0) * (qx - x2) + (x0 - x2) * (qy - y2)) / den, 1 / 3), 0, 1)
        w2 = np.clip(1 - w0 - w1, 0, 1)
        ws = w0 + w1 + w2
        w0, w1, w2 = w0 / ws, w1 / ws, w2 / ws
        n = N[fa[:, 0]] * w0[:, None] + N[fa[:, 1]] * w1[:, None] + N[fa[:, 2]] * w2[:, None]
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        n[(n @ f) > 0] *= -1
        uv = None
        if TUV is not None:
            uv = TUV[fa[:, 0]] * w0[:, None] + TUV[fa[:, 1]] * w1[:, None] + TUV[fa[:, 2]] * w2[:, None]
        return mask, t, n, uv

    def shade_group(n_sel: np.ndarray, uv_sel: np.ndarray | None, k: int) -> np.ndarray:
        mat = items[k][1]
        tex = texs[k] if texs else None
        albedo = None
        if tex is not None and uv_sel is not None and np.isfinite(uv_sel).all():
            albedo = _sample(tex, uv_sel) * np.asarray(mat.base_color[:3], float)[None, :]
        return _shade(n_sel, f, mat, albedo)

    zbuf = np.full((H, W), np.inf)
    filled = np.zeros((H, W), bool)
    back_ratio = 0.0
    op_idx = np.nonzero(~transp)[0]
    if len(op_idx):
        # Kiểm tra lỗ cần rasterize cả mặt sau (tốn gấp đôi) — chỉ bật cho ảnh kiểm tra 6 góc.
        sel_idx = op_idx if detect_holes else op_idx[~backface[op_idx]]
        pix, zz, tl = _rasterize(x, y, depth, F[sel_idx], H, W)
        t = sel_idx[tl]
        # Chỉ mặt trước tham gia z-buffer: lưới kín không bao giờ lộ mặt sau. Chỗ chỉ có mặt sau (lưới thủng, thiếu
        # mặt khuất, lật pháp tuyến) hiện ra dưới dạng "lỗ": bóng của mọi tam giác lớn hơn bóng của mặt trước.
        front = ~backface[t]
        ids, zbuf = _nearest(pix[front], zz[front], t[front], H, W)
        mask, tv, n, uvp = surface(ids)
        col = np.zeros((len(tv), 3))
        mt = MID[tv]
        for k in np.unique(mt):
            sel = mt == k
            col[sel] = shade_group(n[sel], None if uvp is None else uvp[sel], int(k))
        img[mask] = col
        filled = mask
        if detect_holes:
            allcov = np.zeros(H * W, bool)
            allcov[pix] = True
            holes = allcov.reshape(H, W) & ~mask
            core = holes & np.roll(holes, 1, 0) & np.roll(holes, -1, 0) & np.roll(holes, 1, 1) & np.roll(holes, -1, 1)
            back_ratio = float(core.sum()) / max(1, int(allcov.sum()))
    tr_idx = np.nonzero(transp)[0]
    if len(tr_idx):
        pix, zz, tl = _rasterize(x, y, depth, F[tr_idx], H, W)
        ids_t, z_t = _nearest(pix, zz, tr_idx[tl], H, W)
        mask, tv, n, uvp = surface(ids_t)
        in_front = z_t[mask] < zbuf[mask]
        mt = MID[tv]
        sub = img[mask]
        for k in np.unique(mt):
            sel = (mt == k) & in_front
            if not sel.any():
                continue
            mat = items[int(k)][1]
            a = float(mat.base_color[3])
            sub[sel] = sub[sel] * (1 - a) + shade_group(n[sel], None if uvp is None else uvp[sel], int(k)) * a
        img[mask] = sub
        filled = filled | mask
    if outline:
        z = np.where(np.isfinite(zbuf), zbuf, np.nan)
        span = float(np.nanmax(z) - np.nanmin(z)) if np.any(np.isfinite(zbuf)) else 1.0
        thr = max(span * 0.03, 1e-6)
        edge = np.zeros((H, W), bool)
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            z2 = np.roll(np.roll(z, dy, 0), dx, 1)
            f2 = np.roll(np.roll(filled, dy, 0), dx, 1)
            with np.errstate(invalid="ignore"):
                edge |= (filled != f2) | (np.abs(z - z2) > thr)
        img[edge & filled] *= 0.55
    return RenderResult(_downsample(img, ssaa), float(filled.mean()), back_ratio)


def _downsample(img: np.ndarray, k: int) -> np.ndarray:
    k = max(1, int(k))
    if k > 1:
        h, w = img.shape[0] // k, img.shape[1] // k
        img = img[:h * k, :w * k].reshape(h, k, w, k, 3).mean(axis=(1, 3))
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def render_six(meshes, size: int = 384, background: str = "light", ssaa: int = 1, **kw) -> dict[str, RenderResult]:
    """Sáu góc nhìn kỹ thuật cùng tỷ lệ (để so sánh kích thước), có kiểm tra lỗ/thiếu mặt."""
    allv = np.vstack([m.vertices for m, _ in meshes if m.triangle_count])
    b = (allv.min(axis=0), allv.max(axis=0))
    kw.setdefault("detect_holes", True)
    # 6 góc độc lập → chạy song song (numpy nhả GIL): ~2,5× nhanh hơn, kết quả giống hệt từng điểm ảnh
    import os
    from concurrent.futures import ThreadPoolExecutor
    workers = max(1, min(6, (os.cpu_count() or 2) // 2))
    with ThreadPoolExecutor(workers, thread_name_prefix="nexa-render") as ex:
        results = ex.map(lambda v: render(meshes, v, size, bounds=b, background=background, ssaa=ssaa, **kw), SIX_VIEWS)
        return dict(zip(SIX_VIEWS, results))


def contact_sheet(results: dict[str, RenderResult], cols: int = 3, label: bool = True) -> np.ndarray:
    from PIL import Image, ImageDraw
    names = [v for v in SIX_VIEWS if v in results] + [v for v in results if v not in SIX_VIEWS]
    size = results[names[0]].image.shape[0]
    rows = int(math.ceil(len(names) / cols))
    sheet = Image.new("RGB", (cols * size, rows * size), (6, 10, 20))
    draw = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        x0, y0 = (i % cols) * size, (i // cols) * size
        sheet.paste(Image.fromarray(results[n].image), (x0, y0))
        if label:
            draw.rectangle([x0 + 4, y0 + 4, x0 + 150, y0 + 22], fill=(0, 0, 0))
            draw.text((x0 + 8, y0 + 7), VIEW_LABELS.get(n, n), fill=(120, 230, 250))
    return np.asarray(sheet)


def png_bytes(img: np.ndarray) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def jpeg_bytes(img: np.ndarray, quality: int = 88) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=quality)
    return buf.getvalue()
