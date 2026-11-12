"""Offline synthetic microbenchmarks; no devices, credentials or cloud calls.

Run from the repository: .venv\\Scripts\\python scripts/bench_optimization_audit.py
Results are function timings, NOT whole-application latency or C++ speedups.
"""
from pathlib import Path
import json
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from nexa.audio.clap_detector import ClapDetector
from nexa.audio.snap_detector import SnapDetector
from nexa.audio.pipeline import UtteranceSegmenter, VadConfig, resample
from nexa.three_d.geometry.kernel import MeshData, rotation_minimizing_frames
from nexa.three_d.models import Material
from nexa.three_d.render import render
from nexa.ui.three_d_bridge import pack_mesh, pack_edges


def main():
    results = []

    def bench(name, fn, repeats=9):
        fn()  # warm imports and allocators
        samples = []
        for _ in range(repeats):
            start = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - start) * 1000)
        row = dict(name=name, repeats=repeats, median_ms=float(np.median(samples)),
                   p95_ms=float(np.percentile(samples, 95)), max_ms=max(samples))
        results.append(row)
        print(json.dumps(row), flush=True)

    rng = np.random.default_rng(42)
    blocks = (rng.normal(size=(500, 320)) * 0.005).astype(np.float32)
    clap, snap = ClapDetector(), SnapDetector()
    vad = UtteranceSegmenter(VadConfig())
    tick = 0

    def audio():
        nonlocal tick
        for block in blocks:
            t = tick * 0.02
            clap.process(block, t)
            snap.process(block, t)
            vad.process(block, t)
            tick += 1

    bench('audio_detectors_plus_idle_vad_500_blocks_10s', audio, 5)
    x = rng.normal(size=960).astype(np.float32)
    bench('resample_48k_to_16k_20ms_block', lambda: resample(x, 48000), 101)
    for n in (100, 1000, 10000):
        t = np.linspace(0, 8 * np.pi, n)
        path = np.column_stack((np.cos(t), np.sin(t), t / 8))
        bench(f'rotation_minimizing_frames_{n}_points', lambda: rotation_minimizing_frames(path))

    def grid(n):
        u, v = np.meshgrid(np.linspace(-1, 1, n), np.linspace(-1, 1, n))
        verts = np.column_stack((u.ravel(), v.ravel(), (0.15 * np.sin(u * 4) * np.cos(v * 4)).ravel()))
        a = (np.arange(n - 1)[:, None] * n + np.arange(n - 1)).ravel()
        faces = np.vstack((np.column_stack((a, a + 1, a + n)), np.column_stack((a + 1, a + n + 1, a + n))))
        uv = np.column_stack(((u.ravel() + 1) / 2, (v.ravel() + 1) / 2))
        return MeshData(verts, faces, uvs=uv).compute_normals()

    for n in (100, 225):
        m = grid(n)
        count = m.triangle_count
        bench(f'compute_normals_{count}_triangles', m.compute_normals)
        bench(f'pack_mesh_uv_{count}_triangles', lambda: pack_mesh(m.vertices, m.faces, m.normals, m.uvs, np.zeros(3), 1.0))
        bench(f'pack_edges_{count}_triangles', lambda: pack_edges(m.vertices, m.faces, np.zeros(3), 1.0), 5)
    m = grid(100)
    mat = Material(id='audit', name='Audit')
    bench('render_19602_triangles_384px_ssaa1', lambda: render([(m, mat)], size=384, ssaa=1), 5)
    out = ROOT / 'docs' / 'optimization_microbench_2026-11-12.json'
    out.write_text(json.dumps(dict(python=sys.version, platform=platform.platform(),
                                  numpy=np.__version__, synthetic=True, results=results), indent=2), encoding='utf-8')
    print(str(out))


if __name__ == '__main__':
    main()
