"""Benchmark chất lượng mô hình 3D trên bộ câu nexa/three_d/benchmark.py (≥ 60 câu mỗi nhóm hỗ trợ).

    .venv\\Scripts\\python scripts\\bench_3d_quality.py [--per-group N] [--workers 4] [--gemini] [--out results\\x.json]

Mỗi câu chạy TOÀN BỘ pipeline như trong NEXA (planner → CAD tham số → GLB → kiểm tra → render 6 góc → quality gate).
Báo cáo theo nhóm:
- gate_pass_rate = số mô hình vượt quality gate / tổng số yêu cầu (định nghĩa của dự án)
- spec_accuracy  = số spec khớp ground truth (loại + thông số) / tổng
- điểm trung bình, thời gian tạo p50/p95, danh sách lỗi.
Mặc định KHÔNG gọi Gemini (planner cục bộ, không chấm ảnh AI) để không tốn API; --gemini bật planner + chấm ảnh Gemini.
Kết quả chưa có đánh giá của người: không dùng để khẳng định "90% giống vật thể thật".
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _run_chunk(args: tuple[list[dict], bool, str]) -> list[dict]:
    cases, use_gemini, tmpdir = args
    sys.path.insert(0, str(ROOT))
    from nexa.three_d.asset_store import AssetStore
    from nexa.three_d.benchmark import BenchCase, spec_matches
    from nexa.three_d.job_manager import JobManager
    from nexa.three_d.pipeline import GenerationPipeline
    from nexa.three_d.planner import Planner
    from nexa.utils.config import Config
    tmp = Path(tmpdir)
    cfg = Config(settings_path=tmp / "s.yaml", gestures_path=tmp / "g.yaml", load_env=use_gemini)
    cfg.set("three_d.ai_review", bool(use_gemini))
    gemini = None
    if use_gemini:
        from nexa.ai.gemini_provider import GeminiProvider
        gemini = GeminiProvider(cfg)
    store = AssetStore(tmp / "cache", cache_size_mb=200000)
    planner = Planner(gemini, use_gemini=use_gemini)
    pipe = GenerationPipeline(cfg, store, planner, gemini, provider_factory=lambda: None)
    jm = JobManager(pipe.run, timeout_s=600)
    out = []
    for raw in cases:
        case = BenchCase(**raw)
        t0 = time.monotonic()
        plan = planner.plan(case.prompt)
        ok_spec, spec_problems = spec_matches(case, plan.spec)
        job = jm.submit(case.prompt)
        while not job.terminal:
            time.sleep(0.05)
        dt = time.monotonic() - t0
        rec = {"id": case.id, "group": case.group, "prompt": case.prompt, "spec_ok": ok_spec, "spec_problems": spec_problems,
               "state": job.state.value, "error_code": job.error_code, "message": job.message[:200],
               "seconds": round(dt, 2), "cached": job.cached, "score": job.quality_score, "status": job.quality_status}
        if job.project_id:
            try:
                p = store.load(job.project_id)
                q = p.quality_report
                rec.update({"gates": {k: v["ok"] for k, v in q.get("gates", {}).items()}, "scores": q.get("scores"),
                            "failed_checks": [c["name"] for c in q.get("checks", []) if not c["ok"]],
                            "triangles": p.triangle_count, "parts": len(p.parts)})
            except Exception as exc:
                rec["load_error"] = str(exc)
        rec["gate_pass"] = job.state.value == "ready" and job.quality_status == "passed"
        out.append(rec)
    jm.shutdown()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-group", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--gemini", action="store_true")
    ap.add_argument("--groups", default="", help="chỉ chạy các nhóm này (phân cách bằng dấu phẩy)")
    ap.add_argument("--out", default=str(ROOT / "results" / f"3d_benchmark_{time.strftime('%Y%m%d_%H%M')}.json"))
    a = ap.parse_args()
    from dataclasses import asdict

    from nexa.three_d.benchmark import GROUPS, by_group
    groups = by_group()
    todo = []
    only = [g.strip() for g in a.groups.split(",") if g.strip()]
    for g in GROUPS:
        if only and g not in only:
            continue
        cs = groups[g][: a.per_group] if a.per_group else groups[g]
        todo += [asdict(c) for c in cs]
    n = max(1, a.workers)
    chunks = [todo[i::n] for i in range(n)]
    t0 = time.monotonic()
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=n) as ex:
        for part in ex.map(_run_chunk, [(c, a.gemini, tempfile.mkdtemp(prefix="nexa3d_bench_")) for c in chunks if c]):
            results += part
    summary = {}
    for g in GROUPS:
        rs = [r for r in results if r["group"] == g]
        if not rs:
            continue
        secs = sorted(r["seconds"] for r in rs if not r["cached"]) or [0.0]
        scores = [r["score"] for r in rs if r.get("score") is not None]
        summary[g] = {
            "cases": len(rs), "gate_pass": sum(r["gate_pass"] for r in rs),
            "gate_pass_rate": round(sum(r["gate_pass"] for r in rs) / len(rs), 4),
            "spec_accuracy": round(sum(r["spec_ok"] for r in rs) / len(rs), 4),
            "mean_score": round(statistics.mean(scores), 2) if scores else None,
            "p50_s": round(statistics.median(secs), 2), "p95_s": round(secs[min(len(secs) - 1, int(0.95 * len(secs)))], 2),
            "failures": [{"id": r["id"], "prompt": r["prompt"], "state": r["state"], "code": r["error_code"],
                          "checks": r.get("failed_checks", [])[:4], "spec": r["spec_problems"]} for r in rs if not r["gate_pass"]][:10],
        }
    total = len(results)
    report = {"date": time.strftime("%Y-%m-%d %H:%M"), "gemini": a.gemini, "ai_review": a.gemini, "human_review": False,
              "total": total, "gate_pass_rate": round(sum(r["gate_pass"] for r in results) / max(1, total), 4),
              "spec_accuracy": round(sum(r["spec_ok"] for r in results) / max(1, total), 4),
              "wall_seconds": round(time.monotonic() - t0, 1), "groups": summary, "results": results}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"} | {"groups": {g: {k: v for k, v in s.items() if k != "failures"}
                                                                                      for g, s in summary.items()}},
                     ensure_ascii=False, indent=1))
    print("Chi tiết:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
