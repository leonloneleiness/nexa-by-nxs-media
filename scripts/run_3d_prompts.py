"""Chạy một danh sách câu lệnh tạo mô hình 3D qua ThreeDService thật (Gemini/cloud theo .env) và lưu ảnh chấm + kết quả.

  .venv\\Scripts\\python scripts\\run_3d_prompts.py <thư mục ra> <prompts.json | "câu 1" "câu 2"...> [--set=khóa=giá_trị ...]

Dùng để đánh giá mức 2 (CAD DSL do Gemini mô tả) và mức 3 (cloud / Hugging Face Space) trên vật thể ngoài nhóm hỗ trợ.
Không mở giao diện, không dùng camera/mic. Mỗi câu tốn vài lệnh gọi Gemini (và credit cloud nếu dùng cloud).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _value(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--set=")]
    if len(args) < 2:
        print(__doc__)
        return 1
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    src = Path(args[1])
    prompts = json.loads(src.read_text(encoding="utf-8")) if src.suffix == ".json" and src.exists() else args[1:]

    from nexa.ai.gemini_provider import GeminiProvider
    from nexa.three_d.asset_store import AssetStore
    from nexa.three_d.service import ThreeDService
    from nexa.utils.config import Config

    tmp = Path(tempfile.mkdtemp(prefix="nexa3d_run_"))
    cfg = Config(settings_path=tmp / "s.yaml", gestures_path=tmp / "g.yaml", load_env=True)
    for kv in [a[6:] for a in sys.argv[1:] if a.startswith("--set=")]:
        k, v = kv.split("=", 1)
        cfg.set(k, _value(v))
    svc = ThreeDService(cfg, gemini=GeminiProvider(cfg), store=AssetStore(tmp / "cache"))
    results = []
    for i, prompt in enumerate(prompts):
        t0 = time.monotonic()
        job = svc.submit(prompt, open_when_ready=False)
        while not job.terminal:
            time.sleep(0.2)
        r = {"i": i, "prompt": prompt, "state": job.state.value, "message": job.message, "error": job.error[:400],
             "error_code": job.error_code, "seconds": round(time.monotonic() - t0, 1), "score": job.quality_score,
             "questions": job.questions, "warnings": job.warnings[-6:]}
        if job.project_id:
            pr = svc.store.load(job.project_id)
            q = pr.quality_report
            ai = q.get("ai_review") or {}
            r.update(route=pr.generation_mode, provider=pr.provider, parts=len(pr.parts), triangles=sum(p.triangles for p in pr.parts),
                     scores=q.get("scores"), status=q.get("status"),
                     failed_gates=[k for k, g in (q.get("gates") or {}).items() if not g.get("ok")],
                     review=ai.get("summary", "")[:400], issues=[x.get("issue") for x in ai.get("issues", [])][:5],
                     metadata={k: pr.metadata.get("build", {}).get(k) for k in ("dsl_rounds", "dsl_repairs", "dsl_model",
                                                                               "repaired_parts", "dropped_parts",
                                                                               "best_round")})
            pdir = svc.store.project_dir(job.project_id)
            for f in sorted((pdir / "renders").glob("sheet*.jpg")):
                shutil.copy2(f, out / f"{i:02d}_{f.name}")
            if (pdir / "thumbnail.png").exists():
                shutil.copy2(pdir / "thumbnail.png", out / f"{i:02d}_thumb.png")
        print(json.dumps(r, ensure_ascii=False), flush=True)
        results.append(r)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r["state"] == "ready")
    print(f"XONG: {ok}/{len(results)} ready")
    svc.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
