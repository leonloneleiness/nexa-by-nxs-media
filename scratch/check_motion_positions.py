"""Kiểm tra vị trí linh kiện khi chuyển động: mô phỏng motionXf của ModelViewer.qml bằng numpy trên đỉnh GLB thật.

Cặp linh kiện chạm nhau lúc nghỉ (hoặc cha–con) phải vẫn chạm khi chuyển động. Báo cặp bị tách > tol.
Dùng: python scratch/check_motion_positions.py [store|gen|all] [kind ...]
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from nexa.three_d.asset_store import AssetStore  # noqa: E402
from nexa.three_d.geometry.gltf import read_glb  # noqa: E402
from nexa.three_d.motion import infer_motions  # noqa: E402
from nexa.three_d.manifest import load_manifest  # noqa: E402


def qaxis(a, deg):
    a = np.asarray(a, float)
    n = np.linalg.norm(a)
    a = a / n if n > 1e-9 else np.array([0, 1.0, 0])
    h = math.radians(deg) / 2
    return np.array([math.cos(h), *(a * math.sin(h))])


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def qmat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def motion_xf(ms, tau, k=1.0):
    R, t = np.array([1.0, 0, 0, 0]), np.zeros(3)
    for m in ms:
        if m["t"] == "slide":
            d = (m["off"] + m["amp"] * math.sin(2 * math.pi * tau / m["per"] + m["ph"])) * k
            Rm, tm = np.array([1.0, 0, 0, 0]), np.asarray(m["a"]) * d
        else:
            ang = m["s"] * tau if m["t"] == "spin" else (m["off"] + m["amp"] * math.sin(2 * math.pi * tau / m["per"] + m["ph"])) * k
            Rm = qaxis(m["a"], ang)
            c = np.asarray(m["c"], float)
            tm = c - qmat(Rm) @ c
        t = qmat(Rm) @ t + tm
        R = qmul(Rm, R)
    return qmat(R), t


def part_points(pdir: Path, part, cap=4000) -> np.ndarray | None:
    f = pdir / part.asset if part.asset else None
    if not f or not f.is_file():
        return None
    doc = read_glb(f.read_bytes())
    pts = [pr.mesh.vertices for n in doc.nodes for pr in n.primitives]
    if not pts:
        return None
    v = np.concatenate(pts).astype(float)
    if len(v) > cap:
        v = v[np.random.default_rng(0).choice(len(v), cap, replace=False)]
    return v


def mind(a, b, tb=None):
    tb = tb or cKDTree(b)
    return float(tb.query(a, k=1)[0].min())


def check_project(pdir: Path, project, verbose=False) -> list[str]:
    from nexa.three_d.motion import _Builder, surface_centroid
    from nexa.three_d.viewer_controller import ViewerController
    geom = ViewerController.mesh_geom(project, str(pdir))
    cen = geom.centroid
    chains, mode = infer_motions(project.category, project.parts, geom)
    bld = _Builder(project.category, project.parts, geom)
    bld.build()
    own = bld.own
    pts = {p.id: part_points(pdir, p) for p in project.parts}
    pts = {k: v for k, v in pts.items() if v is not None}
    if not pts:
        return ["(không đọc được đỉnh)"]
    allv = np.concatenate(list(pts.values()))
    diag = float(np.linalg.norm(allv.max(0) - allv.min(0)))
    eps, tol = 0.004 * diag, float(os.environ.get("TOLF", "0.015")) * diag
    ids = list(pts)
    trees = {i: cKDTree(pts[i]) for i in ids}
    par = {p.id: p.parent_id for p in project.parts}
    moving = {i for i in ids if chains.get(i)}
    if mode == "turntable" or not moving:
        return [f"mode={mode}"]
    # cặp liên quan: ít nhất một bên chuyển động, và chạm lúc nghỉ hoặc cha–con
    lo = {i: pts[i].min(0) for i in ids}
    hi = {i: pts[i].max(0) for i in ids}
    pairs = []
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            if a not in moving and b not in moving:
                continue
            if chains.get(a) == chains.get(b):
                continue
            pc = par.get(a) == b or par.get(b) == a
            if not pc and (np.any(lo[a] > hi[b] + eps) or np.any(lo[b] > hi[a] + eps)):
                continue
            d0 = mind(pts[a], pts[b], trees[b])
            if d0 <= eps or (pc and d0 <= tol):
                pairs.append((a, b, d0, pc))
    issues = []
    taus = [0.37, 1.1, 1.9, 2.6, 3.3, 4.7]
    for a, b, d0, pc in pairs:
        worst, wt = 0.0, 0
        for tau in taus:
            Ra, ta = motion_xf(chains.get(a, []), tau)
            Rb, tb_ = motion_xf(chains.get(b, []), tau)
            A = pts[a] @ Ra.T + ta
            B = pts[b] @ Rb.T + tb_
            d = mind(A, B)
            if d > worst:
                worst, wt = d, tau
        rel = [m for m in chains.get(a, []) if m not in chains.get(b, [])] +               [m for m in chains.get(b, []) if m not in chains.get(a, [])]
        if worst - d0 > tol and not any(m["t"] == "slide" for m in rel):
            issues.append(f"TÁCH {a} <-> {b}{' (cha-con)' if pc else ''}: {d0:.1f} -> {worst:.1f} mm "
                          f"(tau {wt}, tol {tol:.1f})  chainA={[m['t'] for m in chains.get(a, [])]} "
                          f"chainB={[m['t'] for m in chains.get(b, [])]}")
    # trượt khớp: tâm vùng tiếp xúc con–cha lúc nghỉ phải đứng yên so với cha khi chuyển động
    for c_id in ids:
        pa = par.get(c_id)
        if pa not in pts or chains.get(c_id) == chains.get(pa):
            continue
        # chuyển động tương đối hợp lệ theo bản chất (lăn/quay trên ổ, trượt ray) → không phải khớp bản lề
        rel = [m for m in chains.get(c_id, []) if m not in chains.get(pa, [])] +               [m for m in chains.get(pa, []) if m not in chains.get(c_id, [])]
        if any(m["t"] in ("spin", "slide") or (m["t"] == "swing" and abs(m["amp"]) + abs(m["off"]) > 180) for m in rel):
            continue
        size_c = float(np.max(pts[c_id].max(0) - pts[c_id].min(0)))
        size_p = float(np.max(pts[pa].max(0) - pts[pa].min(0)))
        g = geom.contact(c_id, pa, min(size_c, size_p))  # tâm vùng tiếp xúc lấy mẫu đều theo diện tích
        if g is None:
            continue
        worst = 0.0
        for tau in taus:
            Rc, tc = motion_xf(chains.get(c_id, []), tau)
            Rp, tp = motion_xf(chains.get(pa, []), tau)
            gc = Rc @ g + tc
            # đưa về hệ của cha lúc nghỉ
            gl = Rp.T @ (gc - tp)
            worst = max(worst, float(np.linalg.norm(gl - g)))
        lim = max(0.03 * size_c, 0.002 * diag)
        if worst > lim:
            # bộ phận tròn xoay tại chỗ (khớp cầu/trụ quay quanh tâm của nó) vẫn chiếm đúng chỗ cũ → không lộ lệch
            rest = trees[c_id]
            inplace = 0.0
            for tau in taus:
                Rc, tc = motion_xf(chains.get(c_id, []), tau)
                Rp, tp = motion_xf(chains.get(pa, []), tau)
                loc = (pts[c_id] @ Rc.T + tc - tp) @ Rp
                inplace = max(inplace, float(np.percentile(rest.query(loc, k=1)[0], 95)))
            if inplace <= lim:
                continue
            issues.append(f"TRƯỢT KHỚP {c_id} trên {pa}: tâm tiếp xúc dời {worst:.1f} mm (tol {lim:.1f}) "
                          f"chain={[m['t'] for m in chains.get(c_id, [])]}")
    # tâm quay: bộ phận tự quay tròn (spin/swing lớn quanh trục đối xứng) phải giữ trọng tâm tại chỗ
    for pid, m in own.items():
        if m["t"] != "spin" or pid not in pts or bld.by[pid].cat in ("ball", "roller", "cage"):
            continue
        g = cen(pid)
        if g is None:
            continue
        worst = 0.0
        for tau in taus:
            R, t = motion_xf([m], tau)
            worst = max(worst, float(np.linalg.norm(R @ g + t - g)))
        if worst > 0.003 * diag:
            issues.append(f"LỆCH TÂM {pid}: trọng tâm chạy vòng {worst:.1f} mm (tol {0.003 * diag:.1f})")
    # bộ phận chuyển động mà không chạm ai lúc nghỉ -> không kiểm được, ghi chú
    if verbose:
        issues.append(f"  moving={len(moving)}/{len(ids)} pairs={len(pairs)} diag={diag:.0f}")
    return issues


def run_store(kinds):
    root = Path(os.path.expandvars(r"%LOCALAPPDATA%\NEXA\3d_cache"))
    store = AssetStore(root)
    bad = 0
    for pid in sorted(store._index["projects"]):
        try:
            project = load_manifest(store.project_dir(pid))  # không đụng last_used của kho thật
        except Exception as e:  # noqa: BLE001
            print(pid, "LOAD FAIL", e)
            continue
        if kinds and project.category not in kinds and pid not in kinds:
            continue
        iss = check_project(store.project_dir(pid), project, verbose=True)
        n = sum(1 for s in iss if s.startswith(("TÁCH", "LỆCH", "TRƯỢT")))
        bad += n
        print(f"[store] {pid} {project.category:14s} {project.name[:30]:30s} issues={n}")
        for s in iss:
            print("   ", s)
    return bad


def run_gen(kinds):
    from smoke_3d_viewer import PROMPTS

    from nexa.three_d.service import ThreeDService
    from nexa.utils.config import Config
    d = Path(tempfile.mkdtemp(prefix="nexa_motion_"))
    cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
    cfg.set("three_d.ai_review", False)
    store = AssetStore(d / "cache")
    svc = ThreeDService(cfg, notify=lambda k, v: None, store=store, provider_factory=lambda: None)
    bad = 0
    try:
        for kind, prompt in PROMPTS.items():
            if kinds and kind not in kinds:
                continue
            job = svc.submit(prompt, open_when_ready=False)
            t0 = time.time()
            while not job.terminal and time.time() - t0 < 180:
                time.sleep(0.05)
            if not job.project_id:
                print(f"[gen] {kind}: KHÔNG TẠO ĐƯỢC ({getattr(job, 'error', '')})")
                continue
            project = store.load(job.project_id)
            iss = check_project(store.project_dir(job.project_id), project, verbose=True)
            n = sum(1 for s in iss if s.startswith(("TÁCH", "LỆCH", "TRƯỢT")))
            bad += n
            print(f"[gen] {kind:14s} {project.category:16s} issues={n}")
            for s in iss:
                print("   ", s)
    finally:
        svc.shutdown()
    return bad


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    kinds = set(sys.argv[2:])
    total = 0
    if mode in ("store", "all"):
        total += run_store(kinds)
    if mode in ("gen", "all"):
        total += run_gen(kinds)
    print("TOTAL ISSUES", total)
