"""Tripo/Meshy hết credit (hoặc sai key) khi NEXA tự chọn cloud → vẫn tạo mô hình bằng mức 2, báo rõ lý do."""
from __future__ import annotations

from nexa.three_d.generation.base import ProviderError
from nexa.three_d.models import JobState
import pytest
from test_three_d_levels import GOOD, FakeGemini, wait

from nexa.three_d.asset_store import AssetStore
from nexa.three_d.job_manager import JobManager
from nexa.three_d.pipeline import GenerationPipeline
from nexa.three_d.planner import Planner


@pytest.fixture
def mkpipe(tmp_path, config):
    made = []

    def make(gem, provider_factory=lambda: None, **cfg):
        for k, v in cfg.items():
            config.set(f"three_d.{k}", v)
        store = AssetStore(tmp_path / f"cache{len(made)}")
        jm = JobManager(GenerationPipeline(config, store, Planner(gem), gem, provider_factory=provider_factory).run)
        made.append(jm)
        return None, jm, store
    yield make
    for jm in made:
        jm.shutdown()


class NoCreditProv:
    name, capabilities = "tripo", {"text_to_model"}

    def available(self):
        return True, "Tripo 3D API v3"

    def create_from_text(self, prompt, **kw):
        raise ProviderError("quota", "Tài khoản Tripo không đủ credit. (Insufficient credits; Please top up)")


def test_auto_paid_cloud_without_credit_falls_back_to_level2(mkpipe):
    gem = FakeGemini([GOOD])
    p, jm, store = mkpipe(gem, provider_factory=lambda: NoCreditProv(), ai_review=False, dsl_refine_rounds=0)
    job = wait(jm.submit("Tạo bình giữ nhiệt có nắp"))
    assert job.state == JobState.READY, job.error
    proj = store.load(job.project_id)
    assert proj.generation_mode == "dsl" and proj.provider == "local"
    assert any("không đủ credit" in w and "mức 2" in w for w in job.warnings)


def test_explicit_cloud_without_credit_reports_error(mkpipe):
    gem = FakeGemini([GOOD])
    p, jm, _ = mkpipe(gem, provider_factory=lambda: NoCreditProv(), ai_review=False)
    job = wait(jm.submit("Tạo bình giữ nhiệt bằng cloud"))
    assert job.state == JobState.FAILED and job.error_code == "quota" and "credit" in job.error


class FreeProv:
    name, free_tier, capabilities = "Hugging Face Space", True, {"text_to_model"}

    def __init__(self, preferred, fail=False):
        self.preferred, self.fail = preferred, fail

    def available(self):
        return True, "ok"

    def create_from_text(self, prompt, **kw):
        raise ProviderError("failed", "Không Space image-to-3D nào tạo được mô hình: đang ngủ")


def test_hf_with_token_is_main_route_and_level2_is_backup(mkpipe):
    from nexa.three_d.spec import normalize, validate_spec
    gem = FakeGemini([GOOD])
    p, jm, store = mkpipe(gem, provider_factory=lambda: FreeProv(preferred=True), ai_review=False, dsl_refine_rounds=0,
                          refinement_rounds=0)
    pipe = jm.runner.__self__                                                     # GenerationPipeline.run
    sp = normalize(validate_spec({"category": "generic", "params": {}}))
    assert pipe._route(sp, "auto")[0] == "cloud"                                  # có token → mức 3 trước
    job = wait(jm.submit("Tạo bình hoa gốm"))
    assert job.state == JobState.READY, job.error                                 # HF lỗi → mức 2 vẫn tạo được
    assert store.load(job.project_id).generation_mode == "dsl"
    assert any("Hugging Face" in w and "mức 2" in w for w in job.warnings)


def test_hf_without_token_keeps_level2_first(mkpipe):
    gem = FakeGemini([GOOD])
    p, jm, store = mkpipe(gem, provider_factory=lambda: FreeProv(preferred=False), ai_review=False, dsl_refine_rounds=0)
    job = wait(jm.submit("Tạo bình hoa gốm"))
    assert job.state == JobState.READY and store.load(job.project_id).generation_mode == "dsl"
    assert not any("Hugging Face" in w for w in job.warnings)                     # không thử HF khi chưa có token


def test_hf_reuses_one_client_per_space_within_a_job(config, tmp_path):
    """TRELLIS cần phiên gradio liên tục: /start_session và /generate_and_extract_glb phải cùng một client."""
    import time
    from test_three_d_levels import _Job, _png, box_glb, TRELLIS_CONFIG
    from nexa.three_d.generation.hf_provider import HFSpaceProvider
    glb = box_glb(tmp_path / "m.glb")
    made = []

    def factory(space, workdir):
        class C:
            config = TRELLIS_CONFIG
            def submit(self, api_name, **kw):
                self.calls.append(api_name)
                if api_name == "/preprocess_image":
                    return _Job(result=kw["image"])
                if space.startswith("black-forest"):
                    return _Job(result=(_png(tmp_path), 7))
                return _Job(result=None if api_name == "/start_session" else ({"video": "x"}, str(glb), str(glb)))
        c = C()
        c.calls = []
        made.append((space, c))
        return c
    prov = HFSpaceProvider(config, client_factory=factory)
    t = prov.create_from_text("a vase")
    end = time.monotonic() + 10
    while not t.done and time.monotonic() < end:
        t = prov.get_job_status(t)
        time.sleep(0.02)
    assert t.status == "success", t.error
    trellis = [c for s, c in made if s == "trellis-community/TRELLIS"]
    assert len(trellis) == 1 and trellis[0].calls == ["/start_session", "/preprocess_image", "/single_mode", "/generate_and_extract_glb"]


def _textured_glb(tmp_path, color=(20, 60, 200), metallic_missing=True):
    """GLB kiểu TRELLIS: baseColorTexture + UV, KHÔNG có metallicFactor (chuẩn glTF → mặc định 1,0)."""
    import io
    import json
    import struct

    import numpy as np
    from PIL import Image
    from nexa.three_d.geometry import kernel as K
    m = K.box(40, 40, 40).to_mesh()
    uv = np.random.default_rng(0).random((len(m.vertices), 2)).astype(np.float32)
    pos = (m.vertices / 1000.0).astype(np.float32)
    idx = m.faces.astype(np.uint32).ravel()
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, "PNG")
    png = buf.getvalue()
    blobs = [pos.tobytes(), uv.tobytes(), idx.tobytes(), png]
    views, off = [], 0
    for b in blobs:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(b)})
        off += (len(b) + 3) // 4 * 4
    binary = b"".join(b + b"\0" * ((4 - len(b) % 4) % 4) for b in blobs)
    pbr = {"baseColorTexture": {"index": 0}, "baseColorFactor": [1, 1, 1, 1], "roughnessFactor": 1.0}
    if not metallic_missing:
        pbr["metallicFactor"] = 1.0
    js = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
          "materials": [{"pbrMetallicRoughness": pbr}], "textures": [{"source": 0}],
          "images": [{"bufferView": 3, "mimeType": "image/png"}], "bufferViews": views, "buffers": [{"byteLength": len(binary)}],
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
                         "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
                        {"bufferView": 1, "componentType": 5126, "count": len(uv), "type": "VEC2"},
                        {"bufferView": 2, "componentType": 5125, "count": len(idx), "type": "SCALAR"}]}
    jb = json.dumps(js).encode()
    jb += b" " * ((4 - len(jb) % 4) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(jb) + 8 + len(binary))
    out += struct.pack("<II", len(jb), 0x4E4F534A) + jb + struct.pack("<II", len(binary), 0x004E4942) + binary
    p = tmp_path / "tex.glb"
    p.write_bytes(out)
    return p


def test_ai_mesh_texture_is_rendered_and_not_metal(tmp_path):
    """Ảnh cho Gemini chấm phải có màu texture thật; vật liệu AI thiếu metallicFactor được coi là phi kim."""
    from nexa.three_d import render as R
    from nexa.three_d.postprocess.mesh import import_glb
    from nexa.three_d.validator import Limits
    src = _textured_glb(tmp_path)
    imp = import_glb(src, tmp_path / "p", target_size_mm=100, limits=Limits(), max_triangles=100000, clean=True)
    mat = imp.materials["mat_0"]
    assert mat.metallic == 0.0 and mat.textures.get("base_color")
    items = [(m, imp.materials[mid]) for ip in imp.parts for m, mid in ip.meshes]
    with_tex = R.render(items, "front", 96, background=False, ssaa=1, outline=False, texture_root=tmp_path / "p")
    plain = R.render(items, "front", 96, background=False, ssaa=1, outline=False)
    px_t = with_tex.image[with_tex.image.sum(axis=2) > 0].mean(axis=0)
    px_p = plain.image[plain.image.sum(axis=2) > 0].mean(axis=0)
    assert px_t[2] > px_t[0] * 1.5                                                # xanh lam của texture hiện ra
    assert abs(float(px_p[2]) - float(px_p[0])) < 20                              # không texture → xám/trắng
    kept = import_glb(_textured_glb(tmp_path / "k" if (tmp_path / "k").mkdir() is None else tmp_path, metallic_missing=False),
                      tmp_path / "q", target_size_mm=100, limits=Limits(), max_triangles=100000, clean=True)
    assert kept.materials["mat_0"].metallic == 1.0                                # có ghi rõ thì giữ nguyên


def test_free_object_stops_after_candidate_reaches_threshold(mkpipe, tmp_path):
    """Ứng viên đầu đã ≥ ngưỡng → không tạo thêm (trước đây vật thể tự do luôn tạo thêm vì không bao giờ 'passed')."""
    from test_three_d_levels import REVIEW_GOOD, box_glb
    from nexa.three_d.generation.base import ProviderTask
    glb = box_glb(tmp_path / "m.glb")

    class Prov:
        name, free_tier, preferred, capabilities = "Hugging Face Space", True, True, {"text_to_model"}
        created = 0

        def available(self):
            return True, "ok"

        def create_from_text(self, prompt, **kw):
            Prov.created += 1
            return ProviderTask(f"t{Prov.created}", "text_to_model")

        def get_job_status(self, t):
            t.status, t.progress = "success", 100
            return t

        def cancel_job(self, t):
            return False

        def download_result(self, t, dest, max_bytes, cancelled=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(glb.read_bytes())
            return dest
    gem = FakeGemini([], reviews=[REVIEW_GOOD, REVIEW_GOOD])
    _, jm, store = mkpipe(gem, provider_factory=lambda: Prov(), ai_review=True, refinement_rounds=1)
    job = wait(jm.submit("Tạo hộp quà"))
    assert job.state == JobState.READY, job.error
    assert store.load(job.project_id).quality_score >= 90 and Prov.created == 1
