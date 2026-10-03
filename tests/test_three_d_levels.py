"""Mức 2 (Gemini thiết kế CAD DSL: sửa lỗi + xem ảnh tinh chỉnh) và mức 3 (Hugging Face Space / cloud) — không gọi mạng.

Gemini, gradio_client và provider cloud đều là bản giả lập; kiểm tra luồng điều phối, whitelist, an toàn khi hủy,
làm sạch lưới AI và chính sách chọn đường tạo.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from nexa.three_d.asset_store import AssetStore
from nexa.three_d.generation.base import ProviderError, ProviderTask
from nexa.three_d.generation.dsl_designer import EXAMPLES, DslDesigner
from nexa.three_d.generation.parametric import compile_dsl_parts
from nexa.three_d.geometry import dsl as D
from nexa.three_d.geometry import gltf
from nexa.three_d.geometry import kernel as K
from nexa.three_d.job_manager import JobManager
from nexa.three_d.models import JobState, Material
from nexa.three_d.pipeline import D_ERRORS, GenerationPipeline, ModelBuild
from nexa.three_d.planner import Planner
from nexa.three_d.quality import assess
from nexa.three_d.spec import normalize, validate_spec


def generic(prompt="cái cốc", **params):
    sp = normalize(validate_spec({"category": "generic", "params": {"description": prompt, **params}}))
    sp.prompt = prompt
    return sp


def wait(job, timeout=90):
    t = time.monotonic()
    while not job.terminal and time.monotonic() - t < timeout:
        time.sleep(0.02)
    return job


def box_glb(path: Path, n_boxes: int = 1) -> Path:
    # mesh AI thật là MỘT primitive; nhiều hộp rời được gộp vào cùng một lưới
    mesh = K.MeshData.concatenate([K.box(40, 40, 40).translate(i * 80, 0, 0).to_mesh() for i in range(n_boxes)])
    gltf.write_glb(path, [("obj", [(mesh, "m")], {})], [Material(id="m", kind="plastic")])
    return path


GOOD = {"parts": [
    {"id": "body", "name_vi": "Thân", "category": "body", "material": "ceramic",
     "shape": {"op": "cylinder", "radius": 40, "height": 90}},
    {"id": "lid", "name_vi": "Nắp", "category": "lid", "material": "plastic_black", "parent_id": "body", "color": "#aa3322",
     "explode_dir": [0, 0, 1], "shape": {"op": "translate", "offset": [0, 0, 88], "child": {"op": "cylinder", "radius": 42, "height": 12}}}]}
BROKEN = {"parts": [GOOD["parts"][0], {"id": "lid", "name_vi": "Nắp", "shape": {"op": "exec", "code": "import os"}}]}
REVIEW_BAD = {"category_match": True, "shape_score": 5, "appearance_score": 6, "summary": "chưa giống",
              "parts_visible": [{"part": "thân", "visible": True}, {"part": "quai", "visible": False}],
              "issues": [{"part": "quai", "severity": "major", "issue": "thiếu quai"}]}
REVIEW_GOOD = {"category_match": True, "shape_score": 9.5, "appearance_score": 9, "summary": "tốt",
               "parts_visible": [{"part": "thân", "visible": True}, {"part": "nắp", "visible": True}], "issues": []}


class FakeGemini:
    """Giả lập GeminiProvider: planner (ModelSpec), thiết kế DSL (schema=None), chấm ảnh, prompt cloud."""
    model = "fake-flash"

    def __init__(self, designs, reviews=None):
        self.designs = list(designs)
        self.reviews = list(reviews or [])
        self.calls: list[dict] = []
        self.last_model = "fake-flash"

    def status(self):
        return True, "ok"

    def generate_json(self, prompt, schema, token, system="", images=None, max_tokens=2048, temperature=0.2, **kw):
        kind = "dsl" if schema is None else ("review" if "shape_score" in json.dumps(schema) else
                                             "cloud_prompt" if "negative_prompt" in json.dumps(schema) else "plan")
        self.calls.append({"kind": kind, "images": bool(images), "kw": kw, "prompt": prompt})
        if kind == "plan":
            return {"category": "generic", "name": "Cái bình", "params": {"description": prompt[:100]}}
        if kind == "review":
            return self.reviews.pop(0) if self.reviews else REVIEW_GOOD
        if kind == "cloud_prompt":
            return {"prompt": "a ceramic vase", "approx_size_mm": 250}
        item = self.designs.pop(0) if self.designs else BROKEN
        if isinstance(item, BaseException):
            raise item
        return json.loads(json.dumps(item))


@pytest.fixture
def mkpipe(tmp_path, config):
    made = []

    def make(gem, provider_factory=lambda: None, **cfg):
        for k, v in cfg.items():
            config.set(f"three_d.{k}", v)
        store = AssetStore(tmp_path / f"cache{len(made)}")
        p = GenerationPipeline(config, store, Planner(gem), gem, provider_factory=provider_factory)
        jm = JobManager(p.run)
        made.append(jm)
        return p, jm, store
    yield make
    for jm in made:
        jm.shutdown()


# ------------------------------------------------------------------ DSL mở rộng
def test_new_dsl_ops_compile_and_validate():
    s = D.compile_dsl({"op": "hull", "children": [{"op": "sphere", "radius": 10},
                                                   {"op": "translate", "offset": [30, 0, 0], "child": {"op": "ellipsoid", "radii": [5, 8, 12]}}]})
    lo, hi = s.bounds()
    assert hi[0] > 30 and s.volume() > 4000
    t = D.compile_dsl({"op": "tube", "radius": 3, "path": [[0, 0, 0], [20, 0, 10], [40, 0, 0]]})
    assert t.volume() > 0
    arr = D.compile_dsl({"op": "linear_array", "count": 4, "step": [20, 0, 0], "child": {"op": "box", "size": [5, 5, 5]}})
    assert abs(arr.volume() - 4 * 125) < 1
    for bad in ({"op": "hull", "children": [{"op": "sphere", "radius": 1}]}, {"op": "ellipsoid", "radii": [1, 2]},
                {"op": "linear_array", "count": 999, "step": [1, 0, 0], "child": {"op": "sphere", "radius": 1}},
                {"op": "tube", "radius": 1, "path": [[0, 0, 0]]}, {"op": "exec", "code": "print(1)"}):
        with pytest.raises(D.DslError):
            D.compile_dsl(bad)
    assert {"hull", "ellipsoid", "tube", "linear_array"} <= set(D.ALLOWED_OPS)


@pytest.mark.parametrize("idx", range(len(EXAMPLES)))
def test_fewshot_examples_are_valid_and_connected(idx):
    ex = EXAMPLES[idx]
    res = compile_dsl_parts(generic(ex["request"]), ex["answer"]["parts"], tolerant=True)
    assert res.asm is not None and not res.errors
    rep = assess(generic(ex["request"]), ModelBuild.from_assembly(res.asm).part_data(), mode="dsl")
    assert not [f for f in rep.fixes if f["kind"] == "floating"]
    assert abs(res.asm.bounds.min[1]) < 1e-6                             # đặt trên mặt đất (asset: +Y lên)
    want = ex["answer"]["overall_size_mm"]
    got = sorted(res.asm.bounds.size)
    assert all(abs(g - w) / w < 0.15 for g, w in zip(got, sorted(want))), (got, want)


def test_tolerant_compile_isolates_bad_parts_and_applies_color():
    parts = GOOD["parts"] + [{"id": "evil", "name_vi": "X", "shape": {"op": "exec", "code": "__import__('os')"}},
                             {"id": "body", "name_vi": "Trùng id", "notes": "trường lạ bị bỏ", "shape": {"op": "sphere", "radius": 5}}]
    res = compile_dsl_parts(generic(), parts, tolerant=True)
    assert "evil" in res.errors and "không nằm trong danh sách" in res.errors["evil"]
    assert len(res.compiled) == 3 and len(set(res.compiled)) == 3       # id trùng được đổi tên, không hỏng assembly
    lid = next(bp for bp in res.asm.parts if bp.part.id == "lid")
    mid = lid.meshes[0][1]
    assert mid.startswith("plastic_black_aa3322") and res.asm.materials[mid].base_color[0] > res.asm.materials[mid].base_color[2]
    assert lid.part.parent_id == "body" and lid.part.explode_distance > 0
    with pytest.raises(D.DslError):
        compile_dsl_parts(generic(), parts, tolerant=False)


def test_explicit_size_scales_but_ai_guess_does_not():
    sp = generic(approx_size_mm=500.0)
    asm = compile_dsl_parts(sp, GOOD["parts"]).asm
    assert abs(max(asm.bounds.size) - 100) < 1                        # AI tự đoán cỡ → giữ kích thước thiết kế
    sp.explicit = {"approx_size_mm": 500.0}
    asm = compile_dsl_parts(sp, GOOD["parts"]).asm
    assert abs(max(asm.bounds.size) - 500) < 1                        # người dùng nói rõ → đúng cỡ


# ------------------------------------------------------------------ pipeline mức 2
def test_dsl_pipeline_repairs_then_refines_with_images(mkpipe):
    gem = FakeGemini([BROKEN, GOOD, GOOD], reviews=[REVIEW_BAD, REVIEW_GOOD])
    p, jm, store = mkpipe(gem, ai_review=True, dsl_refine_rounds=2, dsl_repair_rounds=2)
    job = wait(jm.submit("Tạo bình giữ nhiệt có nắp"))
    assert job.state == JobState.READY, (job.message, job.error)
    proj = store.load(job.project_id)
    b = proj.metadata["build"]
    assert proj.generation_mode == "dsl" and b["dsl_repairs"] == 1 and b["dsl_rounds"] == 2 and b["best_round"] == "r2"
    kinds = [c["kind"] for c in gem.calls]
    assert kinds.count("dsl") == 3 and kinds.count("review") == 2
    dsl_calls = [c for c in gem.calls if c["kind"] == "dsl"]
    assert "không biên dịch được" in dsl_calls[1]["prompt"].lower() and "exec" in dsl_calls[1]["prompt"]
    assert dsl_calls[2]["images"] and "thiếu quai" in dsl_calls[2]["prompt"]      # vòng xem ảnh nhận ảnh + góp ý
    assert all(c["kw"].get("timeout_s") for c in dsl_calls)                        # tác vụ dài, không theo 20 s hội thoại
    d = store.project_dir(proj.id)
    assert (d / "renders" / "front.png").is_file() and (d / "source" / "design.dsl.json").is_file()
    assert proj.status == "ready" and "best effort" in job.message


def test_dsl_failure_without_fallback_reports_clearly(mkpipe):
    gem = FakeGemini([BROKEN, BROKEN, BROKEN])
    p, jm, store = mkpipe(gem, ai_review=False, dsl_repair_rounds=2)
    bad_only = {"parts": [BROKEN["parts"][1]]}
    gem.designs = [bad_only, bad_only, bad_only]
    job = wait(jm.submit("Tạo cái bình"))
    assert job.state == JobState.FAILED and job.error_code == "dsl_failed" and "Không dựng được" in job.error


def test_dsl_failure_falls_back_to_free_cloud(mkpipe, tmp_path):
    glb = box_glb(tmp_path / "vase.glb")

    class FreeProv:
        name, free_tier, capabilities = "HF giả", True, {"text_to_model"}

        def available(self):
            return True, "ok"

        def create_from_text(self, prompt, **kw):
            return ProviderTask("hf1", "text_to_model")

        def get_job_status(self, t):
            t.status, t.progress = "success", 100
            return t

        def cancel_job(self, t):
            return True

        def download_result(self, t, dest, max_bytes, cancelled=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(glb.read_bytes())
            return dest
    bad_only = {"parts": [BROKEN["parts"][1]]}
    gem = FakeGemini([bad_only] * 3)
    p, jm, store = mkpipe(gem, provider_factory=lambda: FreeProv(), ai_review=False, dsl_repair_rounds=2,
                          refinement_rounds=0)
    job = wait(jm.submit("Tạo bình hoa gốm"))
    assert job.state == JobState.READY, job.error
    proj = store.load(job.project_id)
    assert proj.generation_mode == "cloud" and proj.provider == "HF giả"
    assert any("chuyển sang HF giả" in w for w in job.warnings)
    assert abs(max(proj.bounds.size) - 250) < 2                       # cỡ thật ước lượng từ Gemini (250 mm)


def test_route_policy_free_vs_paid(mkpipe):
    class Prov:
        def __init__(self, free):
            self.free_tier, self.name = free, "p"

        def available(self):
            return True, "ok"
    gem = FakeGemini([])
    p, _, _ = mkpipe(gem)
    sp = generic()
    p.provider_factory = lambda: Prov(True)
    assert p._route(sp, "auto")[0] == "dsl"                            # miễn phí + có Gemini → mức 2 trước
    assert p._route(sp, "cloud")[0] == "cloud"
    sp.quality = "high"
    assert p._route(sp, "auto")[0] == "cloud"                          # chất lượng cao → mức 3
    sp.quality = "standard"
    p.provider_factory = lambda: Prov(False)
    assert p._route(sp, "auto")[0] == "cloud"                          # có key trả phí → cloud
    uav = normalize(validate_spec({"category": "uav", "params": {}}))
    assert p._route(uav, "auto")[0] == "parametric"


def test_generic_score_is_honest_about_review():
    asm = compile_dsl_parts(generic(), GOOD["parts"]).asm
    pd = ModelBuild.from_assembly(asm).part_data()
    good = assess(generic(), pd, mode="dsl", ai_review={"ok": True, **REVIEW_GOOD})
    bad = assess(generic(), pd, mode="dsl", ai_review={"ok": True, **REVIEW_BAD})
    none = assess(generic(), pd, mode="dsl", ai_review=None)
    assert good.total > 90 > bad.total and bad.total < 80
    assert none.total < 75 and none.status == "best_effort"             # không có người chấm → không thể điểm cao
    assert not isinstance(RuntimeError(), D_ERRORS)
    from nexa.core.safety import Cancelled
    assert not issubclass(Cancelled, D_ERRORS)                          # hủy luôn lan ra ngoài vòng thiết kế


def test_designer_prompts_contain_whitelist_and_no_code():
    gem = FakeGemini([GOOD])
    d = DslDesigner(gem)
    out = d.design(generic("bình giữ nhiệt"), token=None)
    assert out["parts"][0]["id"] == "body"
    pr = gem.calls[0]["prompt"]
    assert "hull{children}" in pr and "Không viết mã" in pr and "TỰ KIỂM TRA" in pr


# ------------------------------------------------------------------ làm sạch lưới AI
def _dirty_mesh():
    m = K.box(10, 10, 10).to_mesh()
    v, f = m.vertices, m.faces
    n = len(v)
    extra_v = np.array([[100, 100, 100], [101, 100, 100], [100, 101, 100], [100, 100, 101]], float)
    tet = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]) + n
    degen = np.array([[0, 0, 1], [1, 2, 2]])
    colinear_v = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], float)
    col = np.array([[0, 1, 2]]) + n + 4
    V = np.vstack([v, extra_v, colinear_v])
    F = np.vstack([f, f[:1], tet, degen, col])
    uv = np.random.default_rng(1).random((len(V), 2))
    return K.MeshData(V, F.astype(np.int64), None, uv), len(f)


def test_clean_mesh_removes_junk_and_keeps_uvs():
    from nexa.three_d.postprocess.mesh import clean_mesh
    m, n_good = _dirty_mesh()
    out, st = clean_mesh(m)
    assert st["degenerate_removed"] == 3 and st["duplicate_removed"] == 1 and st["floaters_removed"] == 4
    assert out.triangle_count == n_good and out.uvs is not None and len(out.uvs) == len(out.vertices)
    assert out.normals is not None and np.isfinite(out.normals).all()


def test_split_components_and_import_clean(tmp_path):
    from nexa.three_d.postprocess.mesh import import_glb
    from nexa.three_d.validator import Limits
    src = box_glb(tmp_path / "two.glb", n_boxes=2)
    imp = import_glb(src, tmp_path / "proj", target_size_mm=200, limits=Limits(), max_triangles=100000, clean=True, split=True)
    assert len(imp.parts) == 2 and any("thành phần liên thông" in w for w in imp.warnings)


def test_structure_only_validation_for_raw_ai_mesh(tmp_path):
    from nexa.three_d.postprocess.mesh import import_glb
    from nexa.three_d.validator import AssetError, Limits, validate_glb_bytes
    m = K.box(10, 10, 10).to_mesh()
    junk = np.array([[i % len(m.vertices)] * 2 + [(i + 1) % len(m.vertices)] for i in range(200)])
    dirty = K.MeshData(m.vertices, np.vstack([m.faces, junk]).astype(np.int64), None, None).compute_normals()
    p = tmp_path / "dirty.glb"
    gltf.write_glb(p, [("d", [(dirty, "m")], {})], [Material(id="m")])
    data = p.read_bytes()
    assert not validate_glb_bytes(data, Limits(), "d").ok
    assert validate_glb_bytes(data, Limits(), "d", mesh_quality=False).ok
    with pytest.raises(AssetError):
        import_glb(p, tmp_path / "a", target_size_mm=None, limits=Limits(), max_triangles=10000)
    imp = import_glb(p, tmp_path / "b", target_size_mm=None, limits=Limits(), max_triangles=10000, clean=True)
    assert imp.parts[0].meshes[0][0].triangle_count == 12


# ------------------------------------------------------------------ Hugging Face Space provider (gradio giả)
class _Job:
    def __init__(self, result=None, exc=None, hang=False):
        self._r, self._e, self._hang, self.cancelled = result, exc, hang, False

    def done(self):
        return not self._hang or self.cancelled

    def status(self):
        return SimpleNamespace(code="PROCESSING", rank=0)

    def result(self):
        if self._e is not None:
            raise self._e
        return self._r

    def cancel(self):
        self.cancelled = True


TRELLIS_CONFIG = {"components": [{"id": 5, "props": {"label": "Single Image"}},
                                  {"id": 7, "props": {"label": "Multiple Images"}}],
                  "dependencies": [{"api_name": "single_mode", "inputs": [], "targets": [[5, "select"]]},
                                   {"api_name": "multi_mode", "inputs": [], "targets": [[7, "select"]]}]}


def _hf(config, tmp_path, behavior, gemini=None):
    from nexa.three_d.generation.hf_provider import HFSpaceProvider
    calls = []

    def factory(space, workdir):
        class C:
            config = TRELLIS_CONFIG
            def submit(self, api_name, **kw):
                calls.append((space, api_name, kw))
                if api_name == "/preprocess_image" and (space, api_name) not in behavior:
                    return _Job(result=kw["image"])
                b = behavior.get((space, api_name))
                return b() if callable(b) else _Job(result=b)
        return C()
    return HFSpaceProvider(config, gemini=gemini, client_factory=factory), calls


def _png(tmp_path):
    from PIL import Image
    p = tmp_path / "flux.webp"
    Image.new("RGB", (64, 64), (250, 250, 250)).save(p, "WEBP")
    return {"path": str(p)}


def _poll(prov, task, t=10):
    end = time.monotonic() + t
    while time.monotonic() < end:
        task = prov.get_job_status(task)
        if task.done:
            return task
        time.sleep(0.02)
    return task


def test_hf_text_to_3d_falls_through_quota_to_next_space(config, tmp_path):
    glb = box_glb(tmp_path / "white_mesh.glb")
    quota = RuntimeError("You have exceeded your ZeroGPU quota (120s requested vs. 30s left).")
    beh = {("black-forest-labs/FLUX.1-schnell", "/infer"): (_png(tmp_path), 7),
           ("trellis-community/TRELLIS", "/start_session"): None,
           ("trellis-community/TRELLIS", "/generate_and_extract_glb"): lambda: _Job(exc=quota),
           ("tencent/Hunyuan3D-2", "/shape_generation"): ({"value": str(glb), "__type__": "update"}, "<html>", {}, 1234)}
    prov, calls = _hf(config, tmp_path, beh)
    assert prov.available()[0] and prov.free_tier
    t = _poll(prov, prov.create_from_text("a ceramic vase"))
    assert t.status == "success", t.error
    assert [c[:2] for c in calls] == [("black-forest-labs/FLUX.1-schnell", "/infer"), ("trellis-community/TRELLIS", "/start_session"),
                                      ("trellis-community/TRELLIS", "/preprocess_image"), ("trellis-community/TRELLIS", "/single_mode"),
                                      ("trellis-community/TRELLIS", "/generate_and_extract_glb"), ("tencent/Hunyuan3D-2", "/shape_generation")]
    flux_kw = calls[0][2]
    assert "a ceramic vase" in flux_kw["prompt"] and flux_kw["num_inference_steps"] == 4 and "white background" in flux_kw["prompt"]
    assert calls[-1][2]["caption"] is None and calls[-1][2]["check_box_rembg"] is True
    dest = prov.download_result(t, tmp_path / "out" / "c.glb", 50_000_000)
    assert dest.read_bytes() == glb.read_bytes()
    with pytest.raises(ProviderError) as e:
        prov.download_result(t, tmp_path / "out" / "d.glb", 10)
    assert e.value.kind == "invalid"


def test_hf_all_spaces_out_of_quota_reports_quota(config, tmp_path):
    quota = RuntimeError("You have exceeded your ZeroGPU quota")
    beh = {("black-forest-labs/FLUX.1-schnell", "/infer"): (_png(tmp_path), 7)}
    for sp, ep in (("trellis-community/TRELLIS", "/generate_and_extract_glb"), ("tencent/Hunyuan3D-2", "/shape_generation"),
                   ("tencent/Hunyuan3D-2.1", "/shape_generation"), ("trellis-community/TRELLIS", "/start_session")):
        beh[(sp, ep)] = (lambda: _Job(exc=quota))
    prov, _ = _hf(config, tmp_path, beh)
    t = _poll(prov, prov.create_from_text("a lamp"))
    assert t.status == "failed" and t.raw_status == "quota" and "HF_TOKEN" in t.error


def test_hf_cancel_stops_job(config, tmp_path):
    hanging = _Job(hang=True)
    beh = {("black-forest-labs/FLUX.1-schnell", "/infer"): lambda: hanging}
    prov, _ = _hf(config, tmp_path, beh)
    t = prov.create_from_text("a chair")
    time.sleep(0.3)
    assert prov.cancel_job(t)
    t = _poll(prov, t)
    assert t.status == "cancelled" and hanging.cancelled


def test_hf_uses_gemini_image_when_available_and_remembers_quota(config, tmp_path):
    import nexa.three_d.generation.hf_provider as H
    H._gemini_image_blocked_until = 0.0
    glb = box_glb(tmp_path / "m.glb")

    class Gem:
        n = 0

        def status(self):
            return True, "ok"

        def generate_image(self, prompt, token, model, references=None):
            Gem.n += 1
            err = RuntimeError("quota")
            err.kind = "quota"
            raise err
    beh = {("black-forest-labs/FLUX.1-schnell", "/infer"): (_png(tmp_path), 7),
           ("trellis-community/TRELLIS", "/start_session"): None,
           ("trellis-community/TRELLIS", "/generate_and_extract_glb"): ({"video": "x"}, str(glb), str(glb))}
    prov, calls = _hf(config, tmp_path, beh, gemini=Gem())
    t = _poll(prov, prov.create_from_text("a mug"))
    assert t.status == "success" and Gem.n == 1 and calls[0][0] == "black-forest-labs/FLUX.1-schnell"
    t2 = _poll(prov, prov.create_from_text("a cup"))
    assert t2.status == "success" and Gem.n == 1                       # hạn mức ảnh Gemini = 0 → không thử lại ngay
    H._gemini_image_blocked_until = 0.0


def test_get_provider_auto_prefers_paid_key_then_hf(config, monkeypatch):
    from nexa.three_d.generation.base import get_provider
    monkeypatch.delenv("NEXA_3D_PROVIDER", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("MESHY_API_KEY", raising=False)
    assert config.get("three_d.provider") == "auto"
    assert get_provider(config).name == "Hugging Face Space"
    monkeypatch.setenv("TRIPO_API_KEY", "tsk_" + "a" * 40)
    assert get_provider(config).name.lower().startswith("tripo")
    config.set("three_d.provider", "none")
    assert get_provider(config) is None


# ------------------------------------------------------------------ Gemini: tác vụ dài
def test_gemini_long_task_uses_own_model_chain_and_timeout(config):
    from google.genai import errors
    from test_gemini import provider, text_resp
    from nexa.core.safety import SafetyManager
    e503 = errors.ServerError(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}})
    p, c = provider(config, [e503, text_resp('{"parts": [{"id": "a"}]}')])
    good_before = p._good_model
    out = p.generate_json("dựng", None, SafetyManager().new_token(), models=["m-strong", "m-backup"], timeout_s=120,
                          thinking="medium")
    assert out == {"parts": [{"id": "a"}]}
    reqs = c.models.requests
    assert [r["model"] for r in reqs] == ["m-strong", "m-backup"]
    cfg = reqs[0]["config"]
    assert cfg.response_json_schema is None and cfg.response_mime_type == "application/json"
    assert cfg.http_options.timeout >= 120_000 and cfg.thinking_config.thinking_level.name.lower() == "medium"
    assert p._good_model == good_before                                 # không đổi model "tốt" của hội thoại giọng nói


def test_gemini_truncated_json_is_reported(config):
    from google.genai import types
    from test_gemini import provider
    from nexa.ai.gemini_provider import AIError
    from nexa.core.safety import SafetyManager
    resp = types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=[types.Part(text='{"parts": [{"id": "a", "shape": {"op"')]),
        finish_reason=types.FinishReason.MAX_TOKENS)])
    p, _ = provider(config, [resp])
    with pytest.raises(AIError) as e:
        p.generate_json("x", None, SafetyManager().new_token(), models=["m"], timeout_s=30)
    assert "cắt giữa chừng" in e.value.message


def test_config_levels_defaults_and_clamping(config):
    assert config.get("three_d.dsl_refine_rounds") == 2 and config.get("three_d.hf_enabled") is True
    assert "gemini-3.8-flash" in config.get("three_d.dsl_models")
    config.update({"three_d": {"dsl_refine_rounds": 9, "provider": "bogus", "dsl_thinking": "max"}})
    assert config.get("three_d.dsl_refine_rounds") == 4 and config.get("three_d.provider") == "auto"
    assert config.get("three_d.dsl_thinking") == "medium"


def test_threads_do_not_leak_after_hf_job(config, tmp_path):
    glb = box_glb(tmp_path / "m.glb")
    beh = {("black-forest-labs/FLUX.1-schnell", "/infer"): (_png(tmp_path), 7),
           ("trellis-community/TRELLIS", "/start_session"): None,
           ("trellis-community/TRELLIS", "/generate_and_extract_glb"): ({"video": "x"}, str(glb), str(glb))}
    prov, _ = _hf(config, tmp_path, beh)
    before = {t.name for t in threading.enumerate()}
    t = _poll(prov, prov.create_from_text("a mug"))
    time.sleep(0.2)
    assert t.status == "success"
    assert not [n for n in {t.name for t in threading.enumerate()} - before if n.startswith("nexa-hf-")]
    assert tempfile.gettempdir()


def test_new_key_formats_are_redacted():
    from nexa.utils.logging import redact
    out = redact("gemini AQ." + "Ab8RN6x" * 6 + " hf " + "hf_" + "a1B2" * 8)
    assert "AQ.Ab8" not in out and "hf_a1B2" not in out and out.count("[ĐÃ ẨN]") == 2


def test_settings_qml_offers_new_providers():
    from nexa.utils.config import QML_DIR
    src = (QML_DIR / "Settings.qml").read_text(encoding="utf-8")
    assert '"auto", "tripo", "meshy", "hf_space", "none"' in src and "dsl_refine_rounds" in src and "hf_enabled" in src
