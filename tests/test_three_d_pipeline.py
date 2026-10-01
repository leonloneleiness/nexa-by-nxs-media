"""Mô hình 3D — template, quality gate, job manager, pipeline, asset store/cache, provider cloud (HTTP giả lập)."""
from __future__ import annotations

import json
import threading
import time

import httpx
import numpy as np
import pytest

from nexa.core.safety import Cancelled, CancelToken, SafetyManager
from nexa.three_d.asset_store import AssetStore, export_project
from nexa.three_d.generation.base import ProviderError, ProviderTask
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.job_manager import JobFailed, JobManager, NeedsInput
from nexa.three_d.models import JobState
from nexa.three_d.pipeline import GenerationPipeline
from nexa.three_d.planner import Planner
from nexa.three_d.quality import PartData, assess
from nexa.three_d.review import sanitize_review
from nexa.three_d.spec import normalize, validate_spec


def spec(cat, **params):
    return normalize(validate_spec({"category": cat, "params": params}))


def parts_of(asm):
    return [PartData(bp.part, [(m, asm.materials[mid]) for m, mid in bp.meshes], bp.solid, bp.no_clash_with) for bp in asm.parts]


def wait(job, timeout=60):
    t = time.monotonic()
    while not job.terminal and time.monotonic() - t < timeout:
        time.sleep(0.02)
    return job


# ------------------------------------------------------------------ template + assembly
@pytest.fixture(scope="module")
def uav():
    return build_parametric(spec("uav", arm_count=4))


def test_uav_has_required_parts_and_hierarchy(uav):
    cats = [bp.part.category for bp in uav.parts]
    for c, n in (("arm", 4), ("motor", 4), ("propeller", 4), ("camera", 1), ("frame", 1), ("battery", 1)):
        assert cats.count(c) == n
    prop = uav.part("propeller_front_left").part
    assert prop.parent_id == "motor_front_left" and uav.part("motor_front_left").part.parent_id == "arm_front_left"


def test_uav_primary_color_paints_frame_unless_material_said():
    """«thân màu trắng» (không nói vật liệu) → khung/tay đòn sơn trắng; nói «carbon» thì giữ carbon."""
    def arm_kinds(prompt):
        sp = spec("uav", arm_count=4)
        sp.prompt, sp.style = prompt, {"primary_color": "white"}
        asm = build_parametric(sp)
        return {asm.materials[mid].kind for m, mid in asm.part("arm_front_left").meshes} |             {asm.materials[mid].kind for m, mid in asm.part("frame").meshes}
    assert "carbon" not in arm_kinds("Tạo UAV sáu cánh thân màu trắng") and "paint" in arm_kinds("UAV màu trắng")
    assert "carbon" in arm_kinds("Tạo UAV khung carbon, vỏ màu trắng")


def test_uav_explosion_follows_assembly_logic(uav):
    arm = uav.part("arm_front_left").part
    # tay đòn tách xuyên tâm (ra ngoài, nằm ngang); motor + cánh quạt theo trục motor (+Y của asset = lên)
    c = np.asarray(arm.bounds.center)
    v = np.asarray(arm.explode_vector)
    assert abs(v[1]) < 1e-6 and np.dot(v[[0, 2]], c[[0, 2]]) > 0
    assert uav.part("motor_front_left").part.explode_vector == pytest.approx([0, 1, 0])
    assert uav.part("propeller_front_left").part.explode_vector == pytest.approx([0, 1, 0])
    batt = uav.part("battery").part.explode_vector
    assert batt[2] < -0.9                                       # pin rút ra phía sau (−Z asset)
    planned = {pid for s in uav.explosion_plan for pid in s.part_ids}
    assert planned == {bp.part.id for bp in uav.parts if bp.part.explode_distance > 0}


@pytest.mark.parametrize("cat,params", [("rover", {}), ("humanoid", {}), ("quadruped", {"joints_per_leg": 3}),
                                        ("helicopter", {}), ("gear", {"module_mm": 2, "teeth": 24}),
                                        ("flange", {"outer_d_mm": 120}), ("bracket", {})])
def test_templates_pass_quality_gate(cat, params):
    s = spec(cat, **params)
    asm = build_parametric(s)
    q = assess(s, parts_of(asm), mode="parametric", metadata=asm.metadata)
    assert q.passed, [c for c in q.checks if not c["ok"]]


def test_rover_wheels_move_sideways_and_touch_ground():
    asm = build_parametric(spec("rover", wheel_count=6, length_mm=800))
    wheels = [bp.part for bp in asm.parts if bp.part.category == "wheel"]
    assert len(wheels) == 6 and all(abs(w.explode_vector[0]) > 0.99 for w in wheels)
    assert all(abs(w.bounds.min[1] - asm.bounds.min[1]) < 1.0 for w in wheels)
    assert abs(asm.bounds.size[2] - 800) < 0.5                   # co giãn đúng chiều dài yêu cầu


def test_quadruped_joint_count():
    for j in (2, 3):
        asm = build_parametric(spec("quadruped", joints_per_leg=j))
        assert sum(bp.part.category == "joint" for bp in asm.parts) == 4 * j


def test_helicopter_rotor_axis_explode():
    asm = build_parametric(spec("helicopter", main_blades=4))
    hub = asm.part("main_rotor_hub").part
    assert hub.explode_vector == pytest.approx([0, 1, 0])        # rotor tách theo trục rotor
    tail = asm.part("tail_rotor_hub").part
    assert abs(tail.explode_vector[0]) > 0.99                    # rotor đuôi theo trục ngang


# ------------------------------------------------------------------ quality gate
def test_quality_missing_part_fails(uav):
    s = spec("uav", arm_count=4)
    ps = [p for p in parts_of(uav) if p.part.id != "propeller_front_left"]
    q = assess(s, ps, mode="parametric", metadata=uav.metadata)
    assert not q.passed and not q.gates["required_parts"]["ok"] and "cánh quạt" in q.missing_parts[0]


def test_quality_wrong_dimension_fails():
    s = spec("bolt", diameter_mm=8, length_mm=30)
    asm = build_parametric(spec("bolt", diameter_mm=8, length_mm=40))       # dựng sai chiều dài
    q = assess(s, parts_of(asm), mode="parametric", metadata=asm.metadata)
    assert not q.passed and any("chiều dài" in e for e in q.dimension_errors)


def test_quality_clash_detected():
    import copy
    s = spec("uav", arm_count=4)
    asm = build_parametric(s)
    ps = parts_of(asm)
    prop = next(p for p in ps if p.part.id == "propeller_front_left")
    frame = next(p for p in ps if p.part.id == "frame")
    prop.solid = frame.solid.translate(1, 0, 0)                            # đặt cánh quạt xuyên vào khung
    q = assess(s, ps, mode="parametric", metadata=copy.deepcopy(asm.metadata))
    assert not q.gates["geometry"]["ok"] and any("va chạm" in e for e in q.geometry_errors)


def test_quality_nan_geometry_fails(uav):
    s = spec("uav", arm_count=4)
    ps = parts_of(uav)
    m = ps[0].meshes[0][0].copy()
    m.vertices[0, 0] = np.nan
    ps[0] = PartData(ps[0].part, [(m, ps[0].meshes[0][1])], ps[0].solid)
    assert not assess(s, ps, mode="parametric", metadata=uav.metadata).gates["geometry"]["ok"]


def test_ai_score_is_never_sole_evidence(uav):
    s = spec("uav", arm_count=4)
    ps = parts_of(uav)
    perfect_ai = {"ok": True, "shape_score": 10, "appearance_score": 10, "category_match": True, "issues": []}
    bad = [p for p in ps if p.part.category != "propeller"]
    assert not assess(s, bad, mode="parametric", metadata=uav.metadata, ai_review=perfect_ai).passed
    zero_ai = dict(perfect_ai, shape_score=0, appearance_score=0)
    q = assess(s, ps, mode="parametric", metadata=uav.metadata, ai_review=zero_ai)
    assert q.scores["shape"] == pytest.approx(21.0) and not q.passed       # AI 0 điểm kéo tổng dưới ngưỡng


def test_cloud_without_ai_review_cannot_pass():
    s = spec("generic", description="cốc")
    from nexa.three_d.geometry import kernel as K
    from nexa.three_d.models import Material, Part3D
    m = K.cylinder(40, 100).to_mesh()
    p = Part3D(id="part_1", name_vi="Cốc", aliases=["cốc"], material="x")
    q = assess(s, [PartData(p, [(m, Material(id="x"))])], mode="cloud", require_assembly=False)
    assert q.total < 90 and not q.passed


def test_review_sanitized():
    r = sanitize_review({"shape_score": 99, "appearance_score": -5, "category_match": "yes", "issues": [{"issue": "x" * 500}]})
    assert r["shape_score"] == 10 and r["appearance_score"] == 0 and len(r["issues"][0]["issue"]) == 200


# ------------------------------------------------------------------ job manager
def test_job_lifecycle_ready():
    seen = []

    def runner(job, ctx):
        ctx.stage(JobState.PLANNING, 0.1)
        ctx.stage(JobState.GENERATING_GEOMETRY, 0.5)
        return "p1"
    jm = JobManager(runner)
    jm.add_listener(lambda s: seen.append(s["state"]))
    job = wait(jm.submit("x"))
    assert job.state == JobState.READY and job.project_id == "p1"
    assert seen[0] == "queued" and "planning" in seen and seen[-1] == "ready"
    jm.shutdown()


def test_cancel_running_job_and_late_result_ignored():
    release = threading.Event()
    finished = []

    def runner(job, ctx):
        ctx.stage(JobState.GENERATING_GEOMETRY, 0.2)
        release.wait(5)                  # "provider" trả kết quả muộn, không kiểm tra hủy
        return "late-project"
    jm = JobManager(runner)
    jm.add_finish_listener(lambda j: finished.append(j.state))
    job = jm.submit("x")
    time.sleep(0.2)
    assert jm.cancel(job.id)
    release.set()
    time.sleep(0.3)
    assert job.state == JobState.CANCELLED and job.project_id is None and finished == [JobState.CANCELLED]
    jm.shutdown()


def test_cancel_queued_job():
    block = threading.Event()
    jm = JobManager(lambda j, c: (block.wait(3), "a")[1])
    first, second = jm.submit("1"), jm.submit("2")
    assert jm.cancel(second.id) and second.state == JobState.CANCELLED
    block.set()
    wait(first)
    assert first.state == JobState.READY and second.state == JobState.CANCELLED
    jm.shutdown()


def test_job_timeout():
    def runner(job, ctx):
        while True:
            ctx.check()
            time.sleep(0.05)
    jm = JobManager(runner, timeout_s=0.5)
    job = wait(jm.submit("x"), 5)
    assert job.state == JobState.FAILED and job.error_code == "timeout"
    jm.shutdown()


def test_emergency_stop_epoch_cancels_job():
    safety = SafetyManager()

    def runner(job, ctx):
        while True:
            ctx.check()
            time.sleep(0.02)
    jm = JobManager(runner, token_factory=lambda: safety.new_token("3d"))
    job = jm.submit("x")
    time.sleep(0.1)
    safety.emergency_stop("test")
    wait(job, 3)
    assert job.state == JobState.CANCELLED
    jm.shutdown()


def test_job_failure_and_needs_input_states():
    jm = JobManager(lambda j, c: (_ for _ in ()).throw(JobFailed("Tripo lỗi", "provider")))
    j = wait(jm.submit("x"))
    assert j.state == JobState.FAILED and j.error == "Tripo lỗi"
    jm2 = JobManager(lambda j, c: (_ for _ in ()).throw(NeedsInput(["Dài bao nhiêu?"], "x {}")))
    j2 = wait(jm2.submit("x"))
    assert j2.state == JobState.NEEDS_INPUT and j2.questions == ["Dài bao nhiêu?"] and j2.resume == "x {}"
    jm.shutdown(), jm2.shutdown()


# ------------------------------------------------------------------ pipeline + store
@pytest.fixture
def pipe(tmp_path, config):
    config.set("three_d.ai_review", False)
    store = AssetStore(tmp_path / "cache")
    p = GenerationPipeline(config, store, Planner(None), None, provider_factory=lambda: None)
    jm = JobManager(p.run)
    yield p, jm, store
    jm.shutdown()


def test_pipeline_bolt_end_to_end(pipe):
    p, jm, store = pipe
    job = wait(jm.submit("Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm."))
    assert job.state == JobState.READY, job.message
    proj = store.load(job.project_id)
    d = store.project_dir(proj.id)
    assert proj.status == "ready" and proj.quality_score >= 90 and proj.metadata["technical_thread"] is True
    assert (d / "model.glb").is_file() and (d / "thumbnail.png").is_file() and all((d / f"renders/{v}.png").is_file()
                                                                                 for v in ("front", "back", "left", "right", "top", "bottom"))
    assert proj.metadata["manufacturing_unverified"] is True and proj.metadata["dimensionally_specified"] is True
    # cache: cùng yêu cầu → dùng lại, không dựng lại
    again = wait(jm.submit("Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm."))
    assert again.cached and again.project_id == proj.id


def test_pipeline_uav_has_safety_warning(pipe):
    p, jm, store = pipe
    job = wait(jm.submit("Tạo một UAV mini bốn cánh, thân carbon màu đen, camera phía trước."))
    assert job.state == JobState.READY
    proj = store.load(job.project_id)
    assert any("CHƯA được kiểm chứng" in w for w in proj.warnings) and proj.has_assembly


def test_pipeline_needs_input(pipe):
    _, jm, _ = pipe
    j = wait(jm.submit("tạo bu lông M8"))
    assert j.state == JobState.NEEDS_INPUT and j.questions


def test_pipeline_cloud_without_key_fails_clearly(pipe, monkeypatch):
    p, jm, _ = pipe
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    from nexa.three_d.generation.tripo_provider import TripoProvider
    p.provider_factory = lambda: TripoProvider(p.config)
    j = wait(jm.submit("Tạo UAV bốn cánh bằng cloud", mode="cloud"))
    assert j.state == JobState.FAILED and j.error_code == "missing_key" and "TRIPO_API_KEY" in j.error
    j2 = wait(jm.submit("Tạo mô hình 3D cái cốc"))
    assert j2.state == JobState.FAILED and "không giả vờ" in j2.error


def test_store_eviction_and_export(tmp_path, pipe):
    p, jm, store = pipe
    job = wait(jm.submit("Tạo đai ốc M8"))
    out = tmp_path / "exp"
    for fmt in ("glb", "stl", "obj", "3mf"):
        f = export_project(store, job.project_id, fmt, out)
        assert f.is_file() and f.stat().st_size > 100
    assert export_project(store, job.project_id, "glb", out).name.endswith("(2).glb")      # không ghi đè
    job2 = wait(jm.submit("Tạo vòng đệm M8"))
    store.cache_size_mb = 0.0001
    removed = store.evict()
    assert job.project_id in removed and job2.project_id not in removed


def test_asset_size_limit_rejected(tmp_path, config):
    from nexa.three_d.postprocess.mesh import import_glb
    from nexa.three_d.validator import AssetError, Limits
    f = tmp_path / "big.glb"
    f.write_bytes(b"glTF" + b"\0" * (2 * 1024 * 1024))
    with pytest.raises(AssetError):
        import_glb(f, tmp_path, target_size_mm=100, limits=Limits(max_asset_mb=1), max_triangles=1000)


# ------------------------------------------------------------------ provider cloud (HTTP giả lập)
def _glb_bytes():
    import io
    import tempfile
    from pathlib import Path

    from nexa.three_d.geometry import gltf
    from nexa.three_d.geometry import kernel as K
    from nexa.three_d.models import Material
    d = Path(tempfile.mkdtemp())
    gltf.write_glb(d / "m.glb", [("mug", [(K.cylinder(0.04 * 1000, 0.1 * 1000).to_mesh(), "m")], {})], [Material(id="m")])
    del io
    return (d / "m.glb").read_bytes()


def tripo_transport(glb: bytes, calls: list, fail: dict | None = None):
    state = {"polls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path, req.headers.get("authorization", "")))
        if fail and req.url.path.endswith("/task") and req.method == "POST":
            return httpx.Response(fail["status"], json=fail["json"])
        if req.url.path.endswith("/task") and req.method == "POST":
            body = json.loads(req.content)
            assert body["type"] == "text_to_model" and body["prompt"] and body["pbr"] is True
            return httpx.Response(200, json={"code": 0, "data": {"task_id": "t-1"}})
        if "/task/t-1" in req.url.path:
            state["polls"] += 1
            if state["polls"] < 2:
                return httpx.Response(200, json={"code": 0, "data": {"task_id": "t-1", "status": "running", "progress": 40}})
            return httpx.Response(200, json={"code": 0, "data": {"task_id": "t-1", "status": "success", "progress": 100,
                                                                   "consumed_credit": 30,
                                                                   "output": {"pbr_model": "https://cdn.test/m.glb"}}})
        if req.url.host == "cdn.test":
            assert "authorization" not in req.headers           # URL ký sẵn: không gửi API key
            return httpx.Response(200, content=glb, headers={"Content-Length": str(len(glb))})
        return httpx.Response(404, json={"code": 2001, "message": "not found"})
    return httpx.MockTransport(handler)


def test_tripo_text_to_model_flow(tmp_path, config, monkeypatch):
    from nexa.three_d.generation.tripo_provider import TripoProvider
    monkeypatch.setenv("TRIPO_API_KEY", "tsk_test_abcdefghijklmnop")
    config.set("three_d.tripo_api", "v2")                 # API v2 (tùy chọn cũ); v3 kiểm trong test_three_d_levels
    calls: list = []
    tr = tripo_transport(_glb_bytes(), calls)
    prov = TripoProvider(config, http_factory=lambda **kw: httpx.Client(transport=tr, **kw))
    assert prov.available()[0]
    task = prov.create_from_text("a coffee mug")
    assert task.task_id == "t-1" and calls[0][2] == "Bearer tsk_test_abcdefghijklmnop"
    while not task.done:
        task = prov.get_job_status(task)
    assert task.status == "success" and task.credits == 30
    out = prov.download_result(task, tmp_path / "r.glb", 10_000_000)
    assert out.read_bytes()[:4] == b"glTF"


@pytest.mark.parametrize("status,body,kind", [(401, {"code": 1002, "message": "auth"}, "auth"),
                                              (403, {"code": 2010, "message": "no credit"}, "quota"),
                                              (400, {"code": 2008, "message": "policy"}, "content_policy")])
def test_tripo_error_mapping(config, monkeypatch, status, body, kind):
    from nexa.three_d.generation.tripo_provider import TripoProvider
    monkeypatch.setenv("TRIPO_API_KEY", "tsk_test_abcdefghijklmnop")
    config.set("three_d.tripo_api", "v2")
    tr = tripo_transport(b"", [], fail={"status": status, "json": body})
    prov = TripoProvider(config, http_factory=lambda **kw: httpx.Client(transport=tr, **kw))
    with pytest.raises(ProviderError) as e:
        prov.create_from_text("x")
    assert e.value.kind == kind


def test_provider_download_limits(tmp_path, config, monkeypatch):
    from nexa.three_d.generation.http import HttpClient
    tr = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 5000))
    c = HttpClient("https://api.test", "k" * 20, factory=lambda **kw: httpx.Client(transport=tr, **kw))
    with pytest.raises(ProviderError):
        c.download("https://cdn.test/a", tmp_path / "a", max_bytes=1000)
    with pytest.raises(ProviderError):
        c.download("http://insecure.test/a", tmp_path / "b", max_bytes=10_000)
    assert not (tmp_path / "a").exists()


def test_meshy_preview_refine_and_cancel(config, monkeypatch):
    from nexa.three_d.generation.meshy_provider import MeshyProvider
    monkeypatch.setenv("MESHY_API_KEY", "msy_test_abcdefghijklmnop")
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path))
        if req.method == "POST":
            body = json.loads(req.content)
            return httpx.Response(200, json={"result": "m-1" if body.get("mode") == "preview" else "m-2"})
        if req.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"status": "SUCCEEDED", "progress": 100, "model_urls": {"glb": "https://x/m.glb"}})
    prov = MeshyProvider(config, http_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(handler), **kw))
    t = prov.create_from_text("robot")
    t = prov.get_job_status(t)
    assert t.status == "success" and t.outputs["glb"].startswith("https://")
    r = prov.refine_model(t)
    assert r.task_id == "m-2" and prov.cancel_job(r)
    assert ("POST", "/openapi/v2/text-to-3d") in seen and ("DELETE", "/openapi/v2/text-to-3d/m-2") in seen


def test_cloud_pipeline_with_fake_provider(pipe, tmp_path):
    p, jm, store = pipe
    glb = _glb_bytes()

    class FakeProv:
        name = "fake"
        capabilities = {"text_to_model"}
        created = 0

        def available(self):
            return True, "ok"

        def create_from_text(self, prompt, **kw):
            FakeProv.created += 1
            return ProviderTask("f1", "text_to_model")

        def get_job_status(self, t):
            t.status, t.progress = "success", 100
            return t

        def cancel_job(self, t):
            return False

        def download_result(self, t, dest, max_bytes, cancelled=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(glb)
            return dest
    p.provider_factory = lambda: FakeProv()
    j = wait(jm.submit("Tạo mô hình 3D cái cốc cà phê cao 10 cm"))
    assert j.project_id, j.message
    proj = store.load(j.project_id)
    assert proj.generation_mode == "cloud" and not proj.has_assembly
    assert any("chưa có cấu trúc assembly" in w for w in proj.warnings)
    assert abs(max(proj.bounds.size) - 100) < 1.0                  # chuẩn hóa: kích thước lớn nhất = mô tả (10 cm)
    assert FakeProv.created == 2                                   # 1 ứng viên + 1 vòng làm lại (không có AI review nên chưa đạt)


def test_token_wait_cancel():
    t = CancelToken(None, 0)
    threading.Timer(0.05, t.cancel).start()
    assert t.wait(2)
    with pytest.raises(Cancelled):
        t.raise_if_cancelled()
