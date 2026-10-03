"""Pipeline tạo mô hình (chạy trong JobManager, không bao giờ trên luồng giao diện/executor).

  planning → (cache) → chọn đường:
    parametric: dựng template/CAD → texturing (texture thủ tục) → segmenting (đã có assembly) → validating
    dsl:        Gemini mô tả CAD DSL (vật thể ngoài nhóm) → như parametric (best effort)
    cloud:      (ảnh tham chiếu nhiều góc) → N ứng viên text/multiview-to-3D → tải + kiểm tra + render + chấm từng
                ứng viên → chọn tốt nhất → (segmentation) → (làm lại có góp ý, giới hạn vòng/chi phí)
  → rendering 6 góc → reviewing (Gemini chấm ảnh) → quality gate → optimizing (LOD) → lưu manifest + cache.

Mô hình không đạt: lưu với status "rejected" (xem được khi anh yêu cầu, có cảnh báo) và job báo "chưa đạt tiêu chuẩn".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from nexa.ai.gemini_provider import AIError
from nexa.three_d import render as R
from nexa.three_d.asset_store import AssetStore
from nexa.three_d.checklist import canonical_checklist
from nexa.three_d.generation.assembly import BuiltAssembly
from nexa.three_d.generation.base import ProviderError, ProviderTask, ThreeDProvider
from nexa.three_d.geometry import gltf
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.dsl import DslError
from nexa.three_d.geometry.kernel import MeshData, Solid
from nexa.three_d.job_manager import Job, JobContext, JobFailed, NeedsInput
from nexa.three_d.manifest import validate_manifest
from nexa.three_d.models import (GENERATOR_VERSION, Bounds, ExplosionStep, JobState, Material, Model3DProject, Part3D)
from nexa.three_d.planner import Planner
from nexa.three_d.quality import PartData, QualityReport, assess
from nexa.three_d.review import review_renders
from nexa.three_d.spec import CATEGORY_VI, ModelSpec
from nexa.three_d.validator import Limits, ValidationReport, validate_glb_bytes
from nexa.utils.logging import get_logger

log = get_logger("3d.pipeline")
# lỗi "mềm" của vòng thiết kế DSL (Gemini lỗi/quá tải, JSON hỏng) — Cancelled KHÔNG nằm trong đây (phải lan ra ngoài)
D_ERRORS: tuple[type[BaseException], ...] = (DslError, AIError)

SAFETY_WARNING = ("Mô hình chỉ để hình dung/thiết kế ý tưởng, CHƯA được kiểm chứng về độ bền, trọng tâm, khí động học, "
                  "tải trọng, vật liệu và an toàn vận hành — không dùng trực tiếp để chế tạo.")
LOD_THRESHOLD = 40_000
DEFAULT_SIZE_MM = {"uav": 300.0, "rover": 700.0, "humanoid": 1650.0, "quadruped": 700.0, "helicopter": 12500.0,
                   "boat": 6500.0, "generic": 300.0,
                   # mẫu kỹ thuật mở rộng (cỡ tổng thể điển hình khi nhập lưới cloud)
                   "bearing": 47.0, "stepper_motor": 75.0, "gearbox": 360.0, "cylinder": 250.0, "ball_valve": 280.0,
                   "pipe_fitting": 250.0, "belt_drive": 180.0, "chain_drive": 620.0, "shaft_coupling": 120.0,
                   "ball_screw": 500.0, "linear_guide": 400.0, "spring": 80.0,
                   "robot_arm": 1000.0, "robot_vacuum": 350.0, "agv": 900.0,
                   "fixed_wing": 11000.0, "car": 4700.0, "motorbike": 2000.0, "excavator": 9500.0, "forklift": 3800.0, "crane": 17000.0,
                   "train": 43000.0, "cubesat": 340.0, "launch_vehicle": 70000.0,
                   "wind_turbine": 125000.0, "solar_array": 7000.0, "generator_set": 2400.0, "centrifugal_pump": 1200.0, "storage_tank": 5000.0,
                   "bridge": 67000.0, "steel_truss": 12700.0, "lattice_tower": 34000.0}


@dataclass
class ModelBuild:
    parts: list[Part3D]
    meshes: dict[str, list[tuple[MeshData, str]]]
    materials: dict[str, Material]
    explosion_plan: list[ExplosionStep]
    solids: dict[str, Solid | None] = field(default_factory=dict)
    no_clash: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    has_assembly: bool = True
    provider_task: ProviderTask | None = None

    @classmethod
    def from_assembly(cls, asm: BuiltAssembly) -> "ModelBuild":
        return cls(parts=[bp.part for bp in asm.parts], meshes={bp.part.id: list(bp.meshes) for bp in asm.parts},
                   materials=dict(asm.materials), explosion_plan=list(asm.explosion_plan),
                   solids={bp.part.id: bp.solid for bp in asm.parts},
                   no_clash={bp.part.id: list(bp.no_clash_with) for bp in asm.parts},
                   metadata=dict(asm.metadata), warnings=list(asm.warnings),
                   has_assembly=len(asm.parts) > 1 and any(bp.part.explode_distance > 0 for bp in asm.parts))

    def part_data(self) -> list[PartData]:
        out = []
        for p in self.parts:
            ms = [(m, self.materials.get(mid) or self.materials.get("mat_default") or
                   Material(id="x", kind="plastic")) for m, mid in self.meshes[p.id]]
            out.append(PartData(p, ms, self.solids.get(p.id), self.no_clash.get(p.id, [])))
        return out

    def render_items(self, exploded: float = 0.0) -> list[tuple[MeshData, Material]]:
        by_id = {p.id: p for p in self.parts}

        def offset(pid: str, depth: int = 0) -> np.ndarray:
            p = by_id[pid]
            o = np.asarray(p.explode_vector) * p.explode_distance * exploded
            return o + (offset(p.parent_id, depth + 1) if p.parent_id in by_id and depth < 32 else 0)
        items = []
        for p in self.parts:
            o = offset(p.id) if exploded else None
            for m, mid in self.meshes[p.id]:
                mm = m
                if o is not None and np.any(o):
                    mm = m.copy()
                    mm.vertices = mm.vertices + o
                items.append((mm, self.materials.get(mid) or Material(id="x")))
        return items


class GenerationPipeline:
    def __init__(self, config: Any, store: AssetStore, planner: Planner, gemini: Any = None,
                 provider_factory: Callable[[], ThreeDProvider | None] | None = None) -> None:
        self.config = config
        self.store = store
        self.planner = planner
        self.gemini = gemini
        self.provider_factory = provider_factory or (lambda: None)

    def cfg(self, key: str, default: Any) -> Any:
        v = self.config.get(f"three_d.{key}") if self.config is not None else None
        return default if v is None else v

    # ================================================================ điều phối
    def run(self, job: Job, ctx: JobContext) -> str:
        ctx.stage(JobState.PLANNING, 0.02, "Đang phân tích yêu cầu")
        overrides = {"mode": job.mode if job.mode != "auto" else None, "quality": job.quality if job.quality != "standard" else None}
        if job.options.get("reference_images"):
            from nexa.three_d.reference_images import load_views
            try:
                views = load_views(job.options["reference_images"])
            except ValueError as exc:
                raise JobFailed(str(exc), "invalid_reference") from exc
            spec = ModelSpec(category="generic", name="Mô hình theo ảnh", prompt=job.prompt,
                             params={"description": job.prompt}, reference_images=views)
        else:
            local_only = job.mode == "parametric" or (job.mode == "auto" and self.cfg("default_mode", "auto") == "parametric")
            planner = Planner(use_gemini=False) if local_only else self.planner
            if local_only:
                overrides["mode"] = "parametric"
            plan = planner.plan(job.prompt, token=ctx.token, overrides=overrides)
            ctx.check()
            for w in plan.warnings:
                ctx.warn(w)
            if plan.questions:
                suffix = " bằng CAD tham số" if local_only else " bằng cloud" if job.mode == "cloud" else ""
                suffix += " chất lượng cao" if job.quality == "high" else ""
                raise NeedsInput(plan.questions, resume=job.prompt.rstrip(" .") + suffix + ", {}")
            spec = plan.spec
        assert spec is not None
        if job.quality == "high":
            spec.quality = "high"
        mode = job.mode if job.mode != "auto" else (spec.mode if spec.mode != "auto" else str(self.cfg("default_mode", "auto")))
        if spec.reference_images:
            if not self.planner.gemini_ready():
                raise JobFailed("Cần cấu hình Gemini API để tạo mô hình từ ảnh tham chiếu.", "missing_key")
            provider = None if mode == "reference_cad" else self.provider_factory()
            if provider is not None and provider.available()[0] and "image_to_model" in provider.capabilities:
                route = "cloud"
            else:
                route, provider = "dsl", None
                ctx.warn("Dựng CAD từ ảnh gốc, không tách nền. Hình học được ước lượng; hoa, chữ và vật liệu có thể chưa giống ảnh."
                         if mode == "reference_cad" else
                         "Chưa có dịch vụ ảnh → 3D sẵn sàng; dùng CAD ước lượng. Chi tiết cong/phức tạp có thể không tái tạo đủ.")
        else:
            route, provider = self._route(spec, mode)
        how = {"parametric": "CAD tham số cục bộ", "dsl": "CAD DSL (best effort)",
               "cloud": "dịch vụ " + (provider.name if provider else "cloud")}[route]
        ctx.progress(0.06, f"{CATEGORY_VI.get(spec.category, 'Mô hình').capitalize()}: dựng bằng {how}")
        key = spec.cache_key(f"{GENERATOR_VERSION}:{route}:{provider.name if provider else 'local'}")
        if spec.reference_images:
            import hashlib
            digest = hashlib.sha256()
            for view, (data, _) in spec.reference_images.items():
                digest.update(view.encode())
                digest.update(data)
            key += ":" + digest.hexdigest()[:24]
        if not spec.reference_images and not job.options.get("no_cache") and route != "cloud":
            cached = self.store.find_cached(key)
            if cached is not None:
                job.cached = True
                job.quality_score, job.quality_status = cached.quality_score, cached.quality_report.get("status", "")
                job.message = f"Mô hình {cached.name} có sẵn trong cache"
                return cached.id
        project_id = Model3DProject.new_id()
        pdir = self.store.new_project_dir(project_id)
        t0 = time.monotonic()
        try:
            if spec.reference_images:
                refdir = pdir / "source" / "reference_images"
                refdir.mkdir(parents=True, exist_ok=True)
                for view, (data, mime) in spec.reference_images.items():
                    extension = "png" if mime == "image/png" else "jpg"
                    (refdir / f"{view}.{extension}").write_bytes(data)
            if route == "cloud":
                try:
                    build, report, renders = self._run_cloud(job, ctx, spec, provider, pdir)
                except JobFailed as exc:
                    if spec.reference_images:
                        raise  # Không âm thầm đổi sang CAD đơn giản khi dựng theo ảnh thất bại.
                    # NEXA tự chọn cloud (auto) cho vật thể tự do mà dịch vụ hết credit/sai key/quá tải → vẫn tạo bằng mức 2
                    soft = ("quota", "auth", "rate_limit") + (
                        ("failed", "timeout", "server", "provider_failed") if getattr(provider, "free_tier", False) else ())
                    free = bool(getattr(provider, "free_tier", False))
                    if not ((mode == "auto" or free) and not spec.supported and exc.code in soft
                            and self.planner.gemini_ready()):
                        raise
                    ctx.warn(f"{provider.name if provider else 'Cloud'}: {exc.message[:120]} — chuyển sang mức 2 "
                             "(Gemini thiết kế CAD DSL).")
                    route, provider = "dsl", None
                    build, report, renders = self._run_dsl(job, ctx, spec, pdir)
            elif route == "dsl":
                if spec.reference_images:
                    build, report, renders = self._run_dsl(job, ctx, spec, pdir)
                    build.metadata["reference_views"] = list(spec.reference_images)
                else:
                    build, report, renders = self._run_dsl_with_fallback(job, ctx, spec, pdir, mode)
                if build.metadata.pop("route_override", None) == "cloud":
                    route, provider = "cloud", build.metadata.pop("provider_obj", None)
            else:
                build = self._build_local(ctx, spec, route)
                report, renders = self._evaluate(ctx, spec, build, pdir, mode=route)
            if spec.reference_images:
                build.metadata["reference_views"] = list(spec.reference_images)
            project = self._finalize(job, ctx, spec, build, report, renders, pdir, project_id, route, provider, key, t0)
        except BaseException:
            self.store.discard(project_id)
            raise
        job.project_id = project.id
        job.quality_score = project.quality_score
        job.quality_status = report.status
        if report.status == "failed":
            reasons = [g["detail"] for g in report.gates.values() if not g["ok"]]
            raise JobFailed(f"Mô hình chưa đạt tiêu chuẩn ({project.quality_score:.0f}/100): " + "; ".join(reasons[:3]),
                            "quality_gate")
        job.message = (f"Mô hình {project.name} đã sẵn sàng ({project.quality_score:.0f}/100)" if report.status == "passed"
                       else f"Mô hình {project.name} (best effort, {project.quality_score:.0f}/100) đã sẵn sàng")
        return project.id

    def _route(self, spec: ModelSpec, mode: str) -> tuple[str, ThreeDProvider | None]:
        """parametric (nhóm hỗ trợ) · cloud (Tripo/Meshy có key, hoặc HF Space khi chọn cloud/chất lượng cao) · dsl (mức 2).

        Provider miễn phí (Hugging Face Space, free_tier) chậm và giới hạn GPU: ở chế độ auto chỉ dùng khi yêu cầu
        chất lượng cao hoặc khi chưa có Gemini; còn lại dùng mức 2 và HF là phương án dự phòng (xem run())."""
        provider = None
        if mode == "parametric":
            if spec.supported:
                return "parametric", None
            raise JobFailed("Vật thể này chưa có mẫu CAD tham số cục bộ. Chọn Tự động hoặc Cloud nếu muốn dùng dịch vụ AI.",
                            "unsupported")
        if mode == "cloud" or (mode == "auto" and not spec.supported):
            provider = self.provider_factory()
            ok, reason = provider.available() if provider is not None else (False, "Chưa cấu hình dịch vụ 3D cloud (NEXA_3D_PROVIDER).")
            gem = self.planner.gemini_ready()
            if ok and (mode == "cloud" or not getattr(provider, "free_tier", False) or spec.quality == "high" or not gem
                       or bool(getattr(provider, "preferred", False))):
                return "cloud", provider
            if mode == "cloud":
                raise JobFailed(reason + " Chế độ CAD tham số cục bộ vẫn dùng được cho các nhóm hỗ trợ.", "missing_key")
            if gem:
                return "dsl", None
            raise JobFailed(f"Vật thể này ngoài nhóm hỗ trợ của CAD cục bộ. {reason} Gemini cũng chưa sẵn sàng để mô tả "
                            "bằng CAD DSL, nên em chưa tạo được — em không giả vờ đã tạo.", "unsupported")
        if spec.supported:
            return "parametric", None
        if self.planner.gemini_ready():
            return "dsl", None
        raise JobFailed("Vật thể ngoài nhóm hỗ trợ và chưa có Gemini để mô tả CAD DSL.", "unsupported")

    def _long(self, timeout_s: float) -> dict:
        """Tham số "tác vụ dài" cho GeminiProvider thật (provider giả lập trong test có thể không nhận)."""
        import inspect
        try:
            params = inspect.signature(self.gemini.generate_json).parameters
        except (TypeError, ValueError, AttributeError):
            return {}
        return {"timeout_s": timeout_s} if "timeout_s" in params or any(
            p.kind == p.VAR_KEYWORD for p in params.values()) else {}

    def _cloud_fallback(self) -> ThreeDProvider | None:
        try:
            fb = self.provider_factory()
        except Exception:
            return None
        return fb if fb is not None and fb.available()[0] else None

    # ================================================================ dựng cục bộ
    def _build_local(self, ctx: JobContext, spec: ModelSpec, route: str) -> ModelBuild:
        from nexa.three_d.generation.parametric import build_from_dsl, build_parametric
        ctx.stage(JobState.GENERATING_GEOMETRY, 0.1, "Đang dựng hình học CAD")
        if route == "dsl":
            parts = self.planner.plan_dsl(spec, ctx.token)
            ctx.check()
            asm = build_from_dsl(spec, parts)
        else:
            asm = build_parametric(spec)
        ctx.check()
        build = ModelBuild.from_assembly(asm)
        build.metadata.setdefault("assembly_confidence", 1.0 if route == "parametric" else 0.6)
        return build

    # ================================================================ mức 2: CAD DSL do Gemini thiết kế
    def _dsl_compile(self, ctx: JobContext, spec: ModelSpec, designer: Any, data: dict, stats: dict) -> tuple[dict, Any]:
        """Biên dịch; bộ phận lỗi → Gemini sửa (tối đa dsl_repair_rounds lần). Trả (data, DslBuild có asm)."""
        from nexa.three_d.generation.parametric import compile_dsl_parts
        res = compile_dsl_parts(spec, data["parts"], tolerant=True, check=ctx.check)
        rounds = int(self.cfg("dsl_repair_rounds", 2))
        while res.errors and stats["repairs"] < rounds:
            ctx.check()
            stats["repairs"] += 1
            stats["repaired_parts"] += len(res.errors)
            ctx.progress(ctx.job.progress, f"Gemini đang sửa {len(res.errors)} bộ phận biên dịch lỗi")
            data = designer.repair(spec, data, res.errors, ctx.token)
            res = compile_dsl_parts(spec, data["parts"], tolerant=True, check=ctx.check)
        if res.asm is None:
            detail = "; ".join(f"{k}: {v}" for k, v in list(res.errors.items())[:3])
            raise JobFailed(f"Không dựng được bộ phận nào từ mô tả CAD của Gemini ({detail[:240]}).", "dsl_failed")
        if res.errors:
            stats["dropped_parts"] += len(res.errors)
            ctx.warn(f"Bỏ {len(res.errors)} bộ phận vẫn lỗi sau khi sửa: {', '.join(list(res.errors)[:5])}")
        return data, res

    @staticmethod
    def _dsl_facts(build: ModelBuild, report: QualityReport) -> str:
        """Số đo thật (khung X trước / Y trái / Z lên, mm) gửi kèm ảnh cho vòng tinh chỉnh."""
        def ros(b: Bounds) -> tuple[list[float], list[float]]:
            return [b.min[2], b.min[0], b.min[1]], [b.max[2], b.max[0], b.max[1]]
        allb = Bounds.union([p.bounds for p in build.parts])
        lines = ["Kích thước tổng thể X×Y×Z: " + " × ".join(f"{s:.0f}" for s in (allb.size[2], allb.size[0], allb.size[1])) + " mm"]
        for p in build.parts[:30]:
            lo, hi = ros(p.bounds)
            lines.append(f"- {p.id} ({p.name_vi}): x {lo[0]:.0f}..{hi[0]:.0f}, y {lo[1]:.0f}..{hi[1]:.0f}, z {lo[2]:.0f}..{hi[2]:.0f}")
        for fx in report.fixes[:6]:
            if fx.get("kind") in ("floating", "clash", "category_mismatch"):
                lines.append(f"LỖI {fx['kind']}: {fx.get('parts') or fx.get('pairs') or fx.get('detail')}")
        if report.geometry_errors:
            lines.append("LỖI hình học: " + "; ".join(report.geometry_errors[:3]))
        return "\n".join(lines)

    def _dsl_good_enough(self, report: QualityReport) -> bool:
        if "reference_similarity" in report.gates and not report.gates["reference_similarity"]["ok"]:
            return False
        ai = report.ai_review if isinstance(report.ai_review, dict) and report.ai_review.get("ok") else None
        if ai is None:
            return False
        serious = [i for i in ai.get("issues", []) if i.get("severity") in ("major", "critical")]
        return report.total >= float(self.cfg("quality_threshold", 90)) and not serious and ai.get("category_match", True) \
            and not any(fx.get("kind") == "floating" for fx in report.fixes)

    def _run_dsl(self, job: Job, ctx: JobContext, spec: ModelSpec, pdir: Path) -> tuple[ModelBuild, QualityReport, dict]:
        import json as _json
        from nexa.three_d.generation.dsl_designer import DslDesigner
        designer = DslDesigner(self.gemini, self.config)
        if not designer.ready():
            raise JobFailed("Cần Gemini để thiết kế vật thể ngoài nhóm hỗ trợ bằng CAD DSL.", "unsupported")
        ctx.stage(JobState.GENERATING_GEOMETRY, 0.1, "Gemini đang thiết kế hình khối (CAD DSL)")
        stats = {"repairs": 0, "repaired_parts": 0, "dropped_parts": 0, "rounds": 0}
        try:
            data = designer.design(spec, ctx.token)
        except (D_ERRORS) as exc:
            raise JobFailed(f"Gemini chưa thiết kế được mô hình: {getattr(exc, 'message', str(exc))[:200]}", "dsl_failed") from exc
        ctx.check()
        data, res = self._dsl_compile(ctx, spec, designer, data, stats)
        rounds = int(max(0, min(4, int(self.cfg("dsl_refine_rounds", 2)))))
        best: tuple[ModelBuild, QualityReport, dict, dict, str] | None = None
        for rnd in range(rounds + 1):
            ctx.check()
            build = ModelBuild.from_assembly(res.asm)
            build.metadata.setdefault("assembly_confidence", 0.6)
            tag = f"r{rnd + 1}"
            report, renders = self._evaluate(ctx, spec, build, pdir, mode="dsl", tag=tag)
            stats["rounds"] = rnd + 1
            ctx.warn(f"Phương án {rnd + 1}: {report.total:.0f}/100")
            if best is None or self._candidate_rank(spec, report) > self._candidate_rank(spec, best[1]):
                best = (build, report, renders, data, tag)
            if rnd == rounds or self._dsl_good_enough(report):
                break
            issues = [f"[{i.get('severity')}] {i.get('part', '')}: {i['issue']}" for i in
                      ((report.ai_review or {}).get("issues") or []) if isinstance(i, dict) and i.get("issue")]
            issues += [f"thiếu: {m}" for m in report.missing_parts]
            ctx.stage(JobState.REFINING, min(0.85, ctx.job.progress + 0.02),
                      f"Gemini đang xem ảnh và sửa mô hình (vòng {rnd + 1}/{rounds})")
            sheet = (pdir / "renders" / f"sheet_{tag}.jpg").read_bytes()
            try:
                new = designer.refine(spec, data, sheet, self._dsl_facts(build, report), issues, ctx.token)
                data, res = self._dsl_compile(ctx, spec, designer, new, stats)
            except (D_ERRORS + (JobFailed,)) as exc:
                ctx.warn(f"Vòng tinh chỉnh {rnd + 1} không dùng được ({getattr(exc, 'message', str(exc))[:100]}) — "
                         "giữ phương án tốt nhất.")
                break
        assert best is not None
        build, report, renders, data, tag = best
        self._promote_renders(pdir, tag)
        (pdir / "source").mkdir(exist_ok=True)
        (pdir / "source" / "design.dsl.json").write_text(_json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        build.metadata.update({"dsl_rounds": stats["rounds"], "dsl_repairs": stats["repairs"],
                               "repaired_parts": stats["repaired_parts"], "dropped_parts": stats["dropped_parts"],
                               "dsl_model": designer.last_model, "best_round": tag,
                               "design_notes": str(data.get("design_notes", ""))[:400]})
        return build, report, renders

    def _run_dsl_with_fallback(self, job: Job, ctx: JobContext, spec: ModelSpec, pdir: Path,
                               mode: str) -> tuple[ModelBuild, QualityReport, dict]:
        """Mức 2; nếu thất bại hoặc điểm quá thấp và có dịch vụ cloud (kể cả HF Space miễn phí) → thử mức 3, giữ bản tốt hơn."""
        low = float(self.cfg("dsl_fallback_below", 55))
        try:
            result = self._run_dsl(job, ctx, spec, pdir)
        except JobFailed as exc:
            fb = self._cloud_fallback() if mode == "auto" and exc.code in ("dsl_failed",) else None
            if fb is None:
                raise
            ctx.warn(f"Mức 2 không dựng được ({exc.message[:80]}) — chuyển sang {fb.name}.")
            return self._cloud_as_fallback(job, ctx, spec, fb, pdir)
        if mode == "auto" and result[1].total < low:
            fb = self._cloud_fallback()
            if fb is not None:
                ctx.warn(f"Mức 2 chỉ đạt {result[1].total:.0f}/100 — thử thêm {fb.name}.")
                try:
                    cloud = self._cloud_as_fallback(job, ctx, spec, fb, pdir)
                except JobFailed as exc:
                    ctx.warn(f"{fb.name} không tạo được ({exc.message[:100]}) — giữ bản CAD DSL.")
                    self._promote_renders(pdir, result[0].metadata.get("best_round", ""))
                    return result
                if cloud[1].total > result[1].total:
                    return cloud
                ctx.warn(f"Bản {fb.name} ({cloud[1].total:.0f}/100) không tốt hơn — giữ bản CAD DSL.")
                self._write_glbs(result[0], pdir)
                self._promote_renders(pdir, result[0].metadata.get("best_round", ""))
        return result

    def _cloud_as_fallback(self, job: Job, ctx: JobContext, spec: ModelSpec, provider: ThreeDProvider,
                           pdir: Path) -> tuple[ModelBuild, QualityReport, dict]:
        build, report, renders = self._run_cloud(job, ctx, spec, provider, pdir)
        build.metadata["route_override"] = "cloud"
        build.metadata["provider_obj"] = provider
        return build, report, renders

    @staticmethod
    def _promote_renders(pdir: Path, tag: str) -> None:
        """Ảnh của phương án được chọn → tên chuẩn renders/<góc>.png (manifest trỏ tới tên này)."""
        import shutil
        rdir = pdir / "renders"
        for f in list(rdir.glob(f"*_{tag}.*")):
            shutil.copy2(f, rdir / f.name.replace(f"_{tag}", ""))

    # ================================================================ cloud
    def _cloud_prompt(self, spec: ModelSpec, ctx: JobContext, feedback: str = "") -> tuple[str, str]:
        base = spec.prompt
        if self.planner.gemini_ready():
            try:
                data = self.gemini.generate_json(
                    f"Viết prompt tiếng Anh cho dịch vụ text-to-3D (Tripo/Meshy) để tạo: «{spec.prompt[:500]}». "
                    "Mô tả rõ hình khối, các bộ phận chính, vật liệu, màu, phong cách sản phẩm thật, chi tiết cao, bề mặt "
                    "mượt. Tối đa 900 ký tự. Một vật thể duy nhất, không nền, không chữ. approx_size_mm = kích thước lớn nhất "
                    "của vật thật (mm)." + (f" Sửa các lỗi của lần trước: {feedback[:400]}" if feedback else ""),
                    {"type": "object", "properties": {"prompt": {"type": "string"}, "negative_prompt": {"type": "string"},
                                                      "approx_size_mm": {"type": "number"}},
                     "required": ["prompt"]}, ctx.token, system="Chỉ trả JSON.", max_tokens=800, **self._long(60))
                if isinstance(data, dict) and data.get("prompt"):
                    try:
                        est = float(data.get("approx_size_mm") or 0)
                    except (TypeError, ValueError):
                        est = 0.0
                    if 1.0 <= est <= 50000.0 and not spec.params.get("approx_size_mm"):
                        spec.params["approx_size_mm"] = est          # cỡ thật ước lượng → co giãn mesh cloud đúng mm
                    return str(data["prompt"])[:1000], str(data.get("negative_prompt", ""))[:250]
            except Exception as exc:
                from nexa.core.safety import Cancelled
                if isinstance(exc, Cancelled):
                    raise
                ctx.warn(f"Không tạo được prompt tiếng Anh bằng Gemini ({str(exc)[:60]}), dùng nguyên câu tiếng Việt.")
        return (base + (f". Fix: {feedback}" if feedback else ""))[:1000], "low quality, broken geometry, blurry texture"

    def _reference_images(self, spec: ModelSpec, ctx: JobContext, provider: ThreeDProvider) -> dict | None:
        if spec.reference_images:
            return spec.reference_images
        use = self.cfg("reference_images", "auto")
        if use is False or use == "off" or "multiview_to_model" not in provider.capabilities:
            return None
        if use == "auto" and spec.quality != "high":
            return None
        if self.gemini is None or not hasattr(self.gemini, "generate_image") or not self.planner.gemini_ready():
            return None
        ctx.stage(JobState.GENERATING_REFERENCE, 0.12, "Đang tạo ảnh tham chiếu nhiều góc")
        model = str(self.cfg("reference_image_model", "gemini-3.1-flash-image"))
        views: dict[str, tuple[bytes, str]] = {}
        base = (f"Product design reference, plain light gray studio background, orthographic, full object visible, "
                f"no text: {spec.prompt[:400]}")
        try:
            front = self.gemini.generate_image(base + ". View: FRONT.", ctx.token, model)
            views["front"] = front
            for i, v in enumerate(("left", "back", "right")):
                ctx.progress(0.13 + 0.02 * i, f"Ảnh tham chiếu góc {v}")
                views[v] = self.gemini.generate_image(base + f". Same exact object as the reference image. View: {v.upper()}.",
                                                      ctx.token, model, references=[front])
        except Exception as exc:
            from nexa.core.safety import Cancelled
            if isinstance(exc, Cancelled):
                raise
            ctx.warn(f"Không tạo được ảnh tham chiếu ({getattr(exc, 'message', str(exc))[:80]}) — dùng text-to-3D.")
            return None
        return views

    def _poll(self, provider: ThreeDProvider, task: ProviderTask, ctx: JobContext, p0: float, p1: float, label: str) -> ProviderTask:
        interval = float(self.cfg("poll_interval_s", 3.0))
        while True:
            if ctx.cancelled:
                provider.cancel_job(task)
                ctx.check()
            task = provider.get_job_status(task)
            extra = f" — {task.raw_status}" if task.raw_status and not task.done else ""
            ctx.progress(p0 + (p1 - p0) * min(1.0, task.progress / 100.0), f"{label} ({task.progress:.0f}%){extra}")
            if task.done:
                if task.status != "success":
                    kind = "reference_mask" if task.raw_status == "reference_mask" else "failed"
                    raise ProviderError(kind, task.error if kind == "reference_mask" else f"{provider.name}: {task.error or task.raw_status}")
                return task
            if ctx.token.wait(interval):
                provider.cancel_job(task)
                ctx.check()

    def _cloud_candidate(self, ctx: JobContext, spec: ModelSpec, provider: ThreeDProvider, pdir: Path, idx: int,
                         prompt: str, negative: str, views: dict | None, p0: float, p1: float) -> tuple[ModelBuild, ProviderTask]:
        ctx.stage(JobState.GENERATING_GEOMETRY, p0, f"Đang tạo ứng viên {idx + 1} bằng {provider.name}")
        retries = int(self.cfg("provider_retries", 1))
        for attempt in range(retries + 1):
            try:
                if views:
                    supported = getattr(provider, "reference_views", None)
                    chosen = {v: image for v, image in views.items() if supported is None or v in supported}
                    if not chosen:
                        raise ProviderError("unsupported", f"{provider.name}: cần ảnh trước, sau, trái hoặc phải để dựng hình.")
                    if len(chosen) != len(views):
                        omitted = ", ".join(v for v in views if v not in chosen)
                        ctx.warn(f"{provider.name} không dựng từ góc {omitted}; các ảnh này chỉ dùng để đối chiếu kết quả.")
                    if len(chosen) > 1 and "multiview_to_model" in provider.capabilities:
                        if getattr(provider, "multiview_requires_front", False) and "front" not in chosen:
                            raise ProviderError("invalid", "Cần thêm ảnh Trước để dựng đa góc bằng dịch vụ này.")
                        task = provider.create_from_multiview(chosen, quality=spec.quality)
                    elif len(chosen) == 1:
                        task = provider.create_from_image(*next(iter(chosen.values())), quality=spec.quality)
                    else:
                        raise ProviderError("unsupported", f"{provider.name} không hỗ trợ nhiều ảnh cùng lúc.")
                else:
                    task = provider.create_from_text(prompt, negative_prompt=negative, quality=spec.quality)
                task = self._poll(provider, task, ctx, p0, p1, f"Ứng viên {idx + 1}")
                break
            except ProviderError as exc:
                if exc.retryable and attempt < retries:
                    ctx.warn(f"{provider.name} lỗi tạm thời ({exc.message[:60]}) — thử lại.")
                    continue
                raise
        ctx.check()
        for note in (provider.job_log(task) if hasattr(provider, "job_log") else [])[:4]:
            ctx.warn(note[:160])
        src = pdir / "source" / f"candidate_{idx + 1}.glb"
        provider.download_result(task, src, int(float(self.cfg("max_asset_mb", 200)) * 1024 * 1024), lambda: ctx.cancelled)
        build = self._import_cloud(src, pdir, spec, real_size=bool(getattr(provider, "auto_size", False)))
        # Mỗi lần import dùng src_0.png...; giữ texture riêng để ứng viên sau
        # không ghi đè màu/chi tiết của ứng viên được chọn trước đó.
        import shutil
        for material in build.materials.values():
            for slot, rel in list(material.textures.items()):
                saved = Path("textures") / f"candidate_{idx + 1}" / Path(rel).name
                (pdir / saved).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pdir / rel, pdir / saved)
                material.textures[slot] = saved.as_posix()
        build.provider_task = task
        return build, task

    def _import_cloud(self, src: Path, pdir: Path, spec: ModelSpec, real_size: bool = False) -> ModelBuild:
        """real_size: provider trả kích thước thật (Tripo v3 auto_size, mét) → giữ nguyên cỡ trừ khi người dùng nói rõ
        kích thước hoặc cỡ nhận được vô lý (< 5 mm / > 100 m)."""
        from nexa.three_d.postprocess.mesh import import_glb
        size = spec.params.get("approx_size_mm") or next((spec.params.get(k) for k in ("length_mm", "height_mm", "wheelbase_mm")
                                                         if spec.params.get(k)), None) or DEFAULT_SIZE_MM.get(spec.category, 300.0)
        told = bool(set(spec.explicit or {}) & {"approx_size_mm", "length_mm", "height_mm", "wheelbase_mm"})
        kw = dict(limits=Limits.from_config(self.config), max_triangles=int(self.cfg("max_triangles", 2_000_000)),
                  clean=True, split=not spec.supported and not spec.reference_images)
        imp = None
        if real_size and not told:
            imp = import_glb(src, pdir, target_size_mm=None, **kw)
            v = np.vstack([m.vertices for ip in imp.parts for m, _ in ip.meshes])
            got = float(np.ptp(v, axis=0).max())
            if not (5.0 <= got <= 100_000.0):
                imp = None                                   # cỡ vô lý → co giãn theo ước lượng như trước
        if imp is None:
            imp = import_glb(src, pdir, target_size_mm=float(size), **kw)
        parts: list[Part3D] = []
        meshes: dict[str, list] = {}
        allv = np.vstack([m.vertices for ip in imp.parts for m, _ in ip.meshes])
        center = (allv.min(axis=0) + allv.max(axis=0)) / 2
        radius = float(np.linalg.norm(allv.max(axis=0) - allv.min(axis=0))) / 2
        multi = len(imp.parts) > 1
        for i, ip in enumerate(imp.parts):
            pid = f"part_{i + 1}"
            v = np.vstack([m.vertices for m, _ in ip.meshes])
            b = Bounds.of_points(v)
            d = np.asarray(b.center) - center
            n = float(np.linalg.norm(d))
            direction = (d / n).tolist() if n > 1e-6 else [0.0, 1.0, 0.0]
            parts.append(Part3D(id=pid, name_vi=ip.name if multi else spec.name or "Mô hình", name_en=ip.name,
                                aliases=[ip.name.lower()] if multi else ["mô hình", "toàn bộ"], category="part",
                                pivot=b.center, bounds=b, material=ip.meshes[0][1], position_tag="",
                                explode_vector=direction, explode_distance=0.35 * radius if multi else 0.0,
                                explode_order=1, confidence=0.5 if multi else 1.0,
                                triangles=sum(m.triangle_count for m, _ in ip.meshes)))
            meshes[pid] = ip.meshes
        plan = [ExplosionStep(1, [p.id for p in parts if p.explode_distance > 0], "Hướng tách ước lượng từ vị trí bộ phận "
                              "(segmentation) — không phải logic lắp ráp đã biết")] if multi else []
        return ModelBuild(parts, meshes, imp.materials, plan, metadata={
            "cloud_scale": imp.scale, "source_triangles": imp.source_triangles, "explosion": "heuristic_radial" if multi else "none",
            "segmentation_confidence": 0.5 if multi else None, "assembly_confidence": 0.3 if multi else 0.0},
            warnings=imp.warnings, has_assembly=multi)

    def _run_cloud(self, job: Job, ctx: JobContext, spec: ModelSpec, provider: ThreeDProvider,
                   pdir: Path) -> tuple[ModelBuild, QualityReport, dict]:
        n = int(max(1, min(3, int(self.cfg("candidate_count", 2)) if spec.quality == "high" else 1)))
        rounds = int(max(0, min(2, int(self.cfg("refinement_rounds", 1)))))
        max_cost = float(self.cfg("max_cost_per_job", 0) or 0)
        views = self._reference_images(spec, ctx, provider)
        prompt, negative = ("", "") if spec.reference_images else self._cloud_prompt(spec, ctx)
        best: tuple[ModelBuild, QualityReport, dict] | None = None
        best_tag = ""
        spent = 0.0
        attempts = n + rounds
        feedback = ""
        for idx in range(attempts):
            if idx >= n:
                # đạt ngưỡng là đủ — vật thể tự do luôn "best effort" (không bao giờ "passed") nên xét theo điểm
                if best is not None and best[1].status != "failed" and (best[1].passed or (best[1].status == "best_effort" and best[1].total >=
                                                            float(self.cfg("quality_threshold", 90)))):
                    break
                ctx.stage(JobState.REFINING, 0.15 + 0.6 * idx / attempts, "Đang tạo lại phần chưa đạt theo góp ý")
                if not spec.reference_images:
                    prompt, negative = self._cloud_prompt(spec, ctx, feedback)
                    views = None
            if max_cost and spent >= max_cost:
                ctx.warn(f"Đã chạm giới hạn chi phí {max_cost:g} credit cho job này — dừng tạo thêm ứng viên.")
                break
            p0, p1 = 0.15 + 0.6 * idx / attempts, 0.15 + 0.6 * (idx + 0.7) / attempts
            try:
                build, task = self._cloud_candidate(ctx, spec, provider, pdir, idx, prompt, negative, views, p0, p1)
            except ProviderError as exc:
                if exc.kind in ("reference_mask", "missing_key", "auth", "quota", "content_policy") or best is None and idx == attempts - 1:
                    raise JobFailed(exc.message, exc.kind) from exc
                ctx.warn(f"Ứng viên {idx + 1} lỗi: {exc.message[:100]}")
                continue
            spent += task.credits or 0.0
            report, renders = self._evaluate(ctx, spec, build, pdir, mode="cloud", tag=f"c{idx + 1}")
            ctx.warn(f"Ứng viên {idx + 1}: {report.total:.0f}/100")
            if best is None or self._candidate_rank(spec, report) > self._candidate_rank(spec, best[1]):
                best = (build, report, renders)
                best_tag = f"c{idx + 1}"
            feedback = "; ".join(i["issue"] for i in (report.ai_review or {}).get("issues", [])[:5]) or \
                "; ".join(report.missing_parts[:3])
        if best is None:
            raise JobFailed(f"{provider.name} không tạo được ứng viên nào.", "provider_failed")
        build, report, renders = best
        if not spec.reference_images and bool(self.cfg("cloud_segmentation", True)) and "segment_model" in provider.capabilities and \
                build.provider_task is not None and not build.has_assembly and                 (spec.supported or bool(self.cfg("cloud_segment_free_objects", False))):
            ctx.stage(JobState.SEGMENTING, 0.8, "Đang tách bộ phận (mesh segmentation)")
            try:
                seg = provider.segment_model(build.provider_task)
                seg = self._poll(provider, seg, ctx, 0.8, 0.86, "Tách bộ phận")
                src = pdir / "source" / "segmented.glb"
                provider.download_result(seg, src, int(float(self.cfg("max_asset_mb", 200)) * 1024 * 1024), lambda: ctx.cancelled)
                seg_build = self._import_cloud(src, pdir, spec, real_size=bool(getattr(provider, "auto_size", False)))
                if seg_build.has_assembly:
                    build = seg_build
                    report, renders = self._evaluate(ctx, spec, build, pdir, mode="cloud", tag="seg")
                    best_tag = "seg"
            except ProviderError as exc:
                ctx.warn(f"Tách bộ phận thất bại: {exc.message[:100]} — giữ mô hình một khối.")
        if best_tag:
            self._promote_renders(pdir, best_tag)
        build.metadata["cloud_candidates"] = n
        build.metadata["cloud_credits"] = spent
        return build, report, renders

    # ================================================================ đánh giá
    def _evaluate(self, ctx: JobContext, spec: ModelSpec, build: ModelBuild, pdir: Path, mode: str,
                  tag: str = "") -> tuple[QualityReport, dict]:
        if spec.reference_images:
            # Photo reconstruction is a visual asset, not a mechanical assembly.
            build.has_assembly = False
            build.explosion_plan = []
            build.metadata["assembly_confidence"] = 0.0
            build.metadata["explosion"] = "none"
            for part in build.parts:
                part.explode_distance = 0.0
        fixed = mode == "parametric"          # dsl/cloud có nhiều vòng: giữ tiến độ hiện tại, không lùi
        ctx.stage(JobState.TEXTURING, 0.4 if fixed else ctx.job.progress, "Đang tạo vật liệu PBR")
        needed = set()
        for m in build.materials.values():
            for rel in m.textures.values():
                if "carbon" in rel:
                    needed.add("carbon")
                if "thread" in rel:
                    needed.add("thread")
                if Path(rel).stem in M.MICRO_TEXTURES:
                    needed.add(Path(rel).stem)
        if needed:
            M.write_textures(pdir, needed)
        if mode == "parametric":
            ctx.stage(JobState.SEGMENTING, 0.45, "Cấu trúc lắp ráp có sẵn từ CAD tham số")
        ctx.stage(JobState.VALIDATING, 0.5 if fixed else ctx.job.progress, "Đang kiểm tra hình học")
        size = self._write_glbs(build, pdir)
        data = (pdir / "model.glb").read_bytes()
        val = validate_glb_bytes(data, Limits.from_config(self.config), "model.glb")
        val.stats["glb_bytes"] = size
        ctx.stage(JobState.RENDERING, 0.6 if fixed else ctx.job.progress, "Đang render 6 góc")
        items = build.render_items()
        renders = R.render_six(items, int(self.cfg("review_render_size", 384)), texture_root=pdir)
        sheet = R.contact_sheet(renders)
        rdir = pdir / "renders"
        rdir.mkdir(exist_ok=True)
        sheet_jpg = R.jpeg_bytes(sheet)
        (rdir / f"sheet{('_' + tag) if tag else ''}.jpg").write_bytes(sheet_jpg)
        for v, rr in renders.items():
            (rdir / f"{v}{('_' + tag) if tag else ''}.png").write_bytes(R.png_bytes(rr.image))
        ai = None
        local_only = ctx.job.mode == "parametric" or spec.mode == "parametric"
        if spec.reference_images or (not local_only and bool(self.cfg("ai_review", True))):
            ctx.stage(JobState.REVIEWING, 0.75 if fixed else ctx.job.progress, "Gemini đang chấm ảnh 6 góc")
            ai = review_renders(sheet_jpg, spec, canonical_checklist(spec), self.gemini, ctx.token,
                                [p.name_vi for p in build.parts])
            if not ai.get("ok"):
                ctx.warn(f"Chưa có đánh giá ảnh bằng AI: {ai.get('reason', '')[:80]}")
        project_stub = Model3DProject(id="stub", name=spec.name, parts=build.parts, explosion_plan=build.explosion_plan,
                                      materials=list(build.materials.values()), has_assembly=build.has_assembly)
        man = validate_manifest(project_stub, pdir, require_explosion=build.has_assembly)
        report = assess(spec, build.part_data(), mode=mode, metadata=build.metadata, renders=renders, validation=val,
                        manifest_report=man, ai_review=ai, threshold=float(self.cfg("quality_threshold", 90)),
                        max_triangles=int(self.cfg("max_triangles", 2_000_000)), require_assembly=build.has_assembly)
        report.measurements["glb_bytes"] = size
        return report, renders

    @staticmethod
    def _candidate_rank(spec: ModelSpec, report: QualityReport) -> tuple:
        if not spec.reference_images:
            return (report.total,)
        ai = report.ai_review or {}
        return (report.status != "failed", bool(ai.get("ok")),
                float(ai.get("shape_score", 0)), float(ai.get("appearance_score", 0)), report.total)

    def _write_glbs(self, build: ModelBuild, pdir: Path) -> int:
        mats = list(build.materials.values())
        nodes = []
        for p in build.parts:
            rel = f"parts/{p.id}.glb"
            p.asset = rel
            extras = {"nexa_part": p.id, "name_vi": p.name_vi, "category": p.category, "parent_id": p.parent_id}
            used = {mid for _, mid in build.meshes[p.id]}
            gltf.write_glb(pdir / rel, [(p.id, build.meshes[p.id], extras)], [m for m in mats if m.id in used], pdir)
            nodes.append((p.id, build.meshes[p.id], extras))
        return gltf.write_glb(pdir / "model.glb", nodes, mats, pdir, extras={"generator": GENERATOR_VERSION})

    # ================================================================ hoàn tất
    def _finalize(self, job: Job, ctx: JobContext, spec: ModelSpec, build: ModelBuild, report: QualityReport,
                  renders: dict, pdir: Path, project_id: str, route: str, provider: ThreeDProvider | None, key: str,
                  t0: float) -> Model3DProject:
        ctx.stage(JobState.OPTIMIZING, 0.9, "Đang tối ưu LOD")
        # _evaluate ghi GLB của lần thử cuối. Xuất lại phương án THỰC SỰ được chọn
        # để mô hình mở trong viewer khớp bản render và điểm đánh giá.
        self._write_glbs(build, pdir)
        lods = {}
        for p in build.parts:
            if p.triangles > LOD_THRESHOLD:
                from nexa.three_d.postprocess.mesh import decimate
                lod_meshes = [(decimate(m, max(2000, m.triangle_count // 3)), mid) for m, mid in build.meshes[p.id]]
                rel = f"parts/{p.id}.lod1.glb"
                used = {mid for _, mid in lod_meshes}
                gltf.write_glb(pdir / rel, [(p.id, lod_meshes, {"lod": 1})],
                               [m for m in build.materials.values() if m.id in used], pdir)
                lods[p.id] = rel
        items = build.render_items()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(2, thread_name_prefix="nexa-thumb") as pool:   # ảnh thu nhỏ + ảnh tách song song
            f_thumb = pool.submit(R.render, items, "iso", 512, background="light", outline=False, texture_root=pdir)
            f_ex = None
            if build.has_assembly and any(p.explode_distance > 0 for p in build.parts):
                f_ex = pool.submit(R.render, build.render_items(exploded=1.0), "iso", 384, background="light", outline=False, texture_root=pdir)
            (pdir / "thumbnail.png").write_bytes(R.png_bytes(f_thumb.result().image))
            if f_ex is not None:
                (pdir / "renders" / "exploded.png").write_bytes(R.png_bytes(f_ex.result().image))
        warnings = list(dict.fromkeys(list(spec.warnings) + build.warnings + list(job.warnings)))
        if spec.safety_critical:
            warnings.append(SAFETY_WARNING)
        if not spec.supported:
            warnings.append("Vật thể ngoài nhóm hỗ trợ: kết quả best effort, mục tiêu 90% không áp dụng.")
        if not build.has_assembly and not spec.reference_images:
            warnings.append("Mô hình chưa có cấu trúc assembly để tháo lắp — xem/chọn bộ phận được nhưng chưa có chế độ tách rời.")
        elif build.metadata.get("explosion") == "heuristic_radial":
            warnings.append("Hướng tách ước lượng từ segmentation, chưa theo logic lắp ráp thật.")
        meta = dict(report.metadata)
        meta.update({"route": route, "timings": dict(job.stage_times), "lods": lods, "spec_source": spec.source,
                     "defaults_used": list(spec.defaults_used), "explicit": dict(spec.explicit),
                     "build": {k: v for k, v in build.metadata.items() if k not in ("prop_disks",)},
                     "generation_seconds": round(time.monotonic() - t0, 2)})
        status = "ready" if report.status in ("passed", "best_effort") else "rejected"
        project = Model3DProject(
            id=project_id, name=spec.name or CATEGORY_VI.get(spec.category, "Mô hình").capitalize(),
            source_prompt=spec.prompt, generation_mode=route, provider=provider.name if provider else "local",
            status=status, asset_path="model.glb", thumbnail_path="thumbnail.png",
            bounds=Bounds.union([p.bounds for p in build.parts]), quality_score=round(report.total, 2),
            validation_status="passed" if report.gates["geometry"]["ok"] and report.gates["asset"]["ok"] else "failed",
            warnings=warnings, parts=build.parts, explosion_plan=build.explosion_plan,
            materials=list(build.materials.values()), category=spec.category, supported_category=spec.supported,
            spec=spec.to_dict(), metadata=meta, quality_report=report.to_dict(),
            renders={v: f"renders/{v}.png" for v in renders} | ({"exploded": "renders/exploded.png"}
                                                                if (pdir / "renders" / "exploded.png").exists() else {}),
            has_assembly=build.has_assembly, cache_key=key if status == "ready" else "")
        ctx.check()                                     # hủy trong lúc hoàn tất → không lưu, không mở
        self.store.commit(project)
        return project


def summarize_report(report: dict) -> str:
    """Tóm tắt quality report bằng tiếng Việt (để đọc cho anh)."""
    if not report:
        return ""
    s = report.get("scores", {})
    return (f"Điểm {report.get('total', 0):.0f}/100 — hình dáng {s.get('shape', 0):.0f}/30, linh kiện "
            f"{s.get('completeness', 0):.0f}/25, kích thước {s.get('dimensions', 0):.0f}/20, lưới {s.get('mesh', 0):.0f}/15, "
            f"vật liệu {s.get('material', 0):.0f}/10.")


__all__ = ["GenerationPipeline", "ModelBuild", "summarize_report", "SAFETY_WARNING", "ValidationReport"]
