"""Tripo API v3 (openapi.tripo3d.ai/v3) — HTTP giả lập đúng schema tài liệu v3 (developers.tripo3d.ai, 2026-09-25).

Không gọi mạng thật, không tốn credit. Kiểm tra endpoint mới, tham số chất lượng, mã lỗi, kích thước thật (auto_size).
"""
from __future__ import annotations

import json

import httpx
import pytest

from nexa.three_d.asset_store import AssetStore
from nexa.three_d.generation.base import ProviderError, ProviderTask
from nexa.three_d.generation.tripo_provider import TripoProvider
from nexa.three_d.geometry import gltf
from nexa.three_d.geometry import kernel as K
from nexa.three_d.models import Bounds, Material
from nexa.three_d.pipeline import GenerationPipeline
from nexa.three_d.planner import Planner
from nexa.three_d.spec import normalize, validate_spec

KEY = "tsk_test_abcdefghijklmnop"


def _glb(tmp_path, size=(300.0, 200.0, 250.0)):
    p = tmp_path / "m.glb"
    gltf.write_glb(p, [("obj", [(K.box(*size).to_mesh(), "m")], {})], [Material(id="m", kind="plastic")])
    return p


def transport(glb: bytes, calls: list, fail: dict | None = None):
    state = {"polls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        ctype = req.headers.get("content-type", "")
        body = json.loads(req.content) if req.content and ctype.startswith("application/json") else None
        calls.append((req.method, req.url.host, req.url.path, body, req.headers.get("authorization", "")))
        if fail and req.method == "POST":
            return httpx.Response(fail["status"], json=fail["json"])
        if req.url.host == "openapi.tripo3d.ai":
            if req.method == "POST" and req.url.path == "/v3/files":
                assert ctype.startswith("multipart/form-data")
                return httpx.Response(200, json={"code": 0, "data": {"file_token": "file_abc"}})
            if req.method == "POST" and req.url.path.startswith("/v3/generation/"):
                return httpx.Response(200, json={"code": 0, "data": {"task_id": "task_1"}})
            if req.method == "POST" and req.url.path == "/v3/mesh/segment":
                return httpx.Response(200, json={"code": 0, "data": {"task_id": "task_seg"}})
            if req.url.path == "/v3/tasks/task_1":
                state["polls"] += 1
                if state["polls"] < 2:
                    return httpx.Response(200, json={"code": 0, "data": {"task_id": "task_1", "status": "running",
                                                                          "progress": 55}})
                return httpx.Response(200, json={"code": 0, "data": {
                    "task_id": "task_1", "type": "text_to_model", "status": "success", "progress": 100,
                    "output": {"model_url": "https://cdn.tripo3d.ai/output/model_pbr.glb",
                               "rendered_image_url": "https://cdn.tripo3d.ai/output/preview.png"},
                    "credits_consumed": 50.00, "created_at": "2026-09-25T12:00:00Z"}})
            if req.url.path == "/v3/tasks/task_bad":
                return httpx.Response(200, json={"code": 0, "data": {"task_id": "task_bad", "status": "failed",
                                                                      "progress": 0, "error_code": 2018,
                                                                      "error_message": "Model too complex"}})
            if req.url.path == "/v3/account/balance":
                return httpx.Response(200, json={"code": 0, "data": {"balance": 1234.5, "frozen": 0.0}})
        if req.url.host == "cdn.tripo3d.ai":
            assert "authorization" not in req.headers           # URL ký sẵn: không gửi API key
            return httpx.Response(200, content=glb, headers={"Content-Length": str(len(glb))})
        return httpx.Response(404, json={"code": 2001, "message": "not found"})
    return httpx.MockTransport(handler)


def provider(config, monkeypatch, calls, glb=b"", fail=None):
    monkeypatch.setenv("TRIPO_API_KEY", KEY)
    tr = transport(glb, calls, fail)
    return TripoProvider(config, http_factory=lambda **kw: httpx.Client(transport=tr, **kw))


def test_v3_is_default_and_text_to_model_uses_new_endpoint_and_quality(config, monkeypatch, tmp_path):
    calls: list = []
    prov = provider(config, monkeypatch, calls, _glb(tmp_path).read_bytes())
    assert prov.api == "v3" and prov.auto_size
    t = prov.create_from_text("a ceramic vase", negative_prompt="blurry")
    method, host, path, body, auth = calls[0]
    assert (method, host, path) == ("POST", "openapi.tripo3d.ai", "/v3/generation/text-to-model")
    assert auth == f"Bearer {KEY}" and "type" not in body                        # v3: không còn trường type
    assert body["model"] == "v3.1-20260211" and body["texture_quality"] == "detailed" and body["texture"] is True
    assert body["geometry_quality"] == "detailed" and body["pbr"] is True and body["auto_size"] is True
    assert body["negative_prompt"] == "blurry" and "face_limit" not in body       # để Tripo tự chọn topology
    while not t.done:
        t = prov.get_job_status(t)
    assert t.status == "success" and t.credits == 50.0 and t.outputs["model"].endswith("model_pbr.glb")
    assert "rendered_image" in t.outputs
    out = prov.download_result(t, tmp_path / "dl" / "c.glb", 10_000_000)
    assert out.read_bytes()[:4] == b"glTF"
    assert prov.balance() == 1234.5 and calls[-1][2] == "/v3/account/balance"


def test_v3_high_quality_image_multiview_and_segment(config, monkeypatch):
    calls: list = []
    prov = provider(config, monkeypatch, calls)
    prov.create_from_text("robot", quality="high")
    assert calls[-1][3]["texture_quality"] == "extreme"                          # 8K khi "chất lượng cao"
    prov.create_from_image(b"\x89PNG....", "image/png")
    assert calls[-2][2] == "/v3/files" and calls[-1][2] == "/v3/generation/image-to-model"
    assert calls[-1][3]["input"] == "file_abc"
    prov.create_from_multiview({"front": (b"a", "image/png"), "left": (b"b", "image/png")})
    assert calls[-1][2] == "/v3/generation/multiview-to-model"
    assert calls[-1][3]["inputs"] == [{"front": "file_abc"}, {"left": "file_abc"}]
    seg = prov.segment_model(ProviderTask("task_1", "text_to_model"))
    assert seg.task_id == "task_seg" and calls[-1][2] == "/v3/mesh/segment"
    assert calls[-1][3] == {"input": "task_1", "model": "v2.0-20260430", "segmentation_granularity": "balanced",
                            "split_by_connectivity": True}
    config.set("three_d.tripo_model_version", "v2.5-20250123")
    prov.create_from_text("x")
    assert "geometry_quality" not in calls[-1][3]                                 # tài liệu: không dùng với v2.5
    with pytest.raises(ProviderError):
        prov.refine_model(ProviderTask("task_1", "text_to_model"))                # chỉ có ở v2 (bản nháp v1.4)


@pytest.mark.parametrize("status,body,kind", [(401, {"code": 1000, "message": "Invalid API Key"}, "auth"),
                                              (403, {"code": 2010, "message": "Insufficient credits",
                                                     "suggestion": "Please top up your account"}, "quota"),
                                              (400, {"code": 2008, "message": "policy"}, "content_policy"),
                                              (400, {"code": 1004, "message": "bad param"}, "invalid"),
                                              (429, {"code": 2000, "message": "Rate limit"}, "rate_limit")])
def test_v3_error_codes(config, monkeypatch, status, body, kind):
    prov = provider(config, monkeypatch, [], fail={"status": status, "json": body})
    with pytest.raises(ProviderError) as e:
        prov.create_from_text("x")
    assert e.value.kind == kind
    if kind == "quota":
        assert "top up" in e.value.message and "credit" in e.value.message
    if kind == "rate_limit":
        assert e.value.retryable


def test_v3_failed_task_reports_error_and_no_cancel_endpoint(config, monkeypatch):
    prov = provider(config, monkeypatch, [])
    t = prov.get_job_status(ProviderTask("task_bad", "text_to_model"))
    assert t.status == "failed" and "Model too complex" in t.error and "2018" in t.error
    assert prov.cancel_job(t) is False


def test_v2_still_selectable(config, monkeypatch):
    calls: list = []
    prov = provider(config, monkeypatch, calls)
    config.set("three_d.tripo_api", "v2")
    assert prov.api == "v2" and not prov.auto_size
    with pytest.raises(ProviderError):
        prov.create_from_text("x")                        # transport giả chỉ biết v3 → 404, nhưng đã gọi đúng host v2
    assert calls[-1][1] == "api.tripo3d.ai" and calls[-1][2] == "/v2/openapi/task"


def test_real_size_kept_unless_user_says_size(config, tmp_path):
    """auto_size: GLB của Tripo theo mét → NEXA giữ cỡ thật; người dùng nói rõ kích thước thì co về đúng cỡ đó."""
    glb = _glb(tmp_path)                                                          # 300 × 200 × 250 mm
    p = GenerationPipeline(config, AssetStore(tmp_path / "c"), Planner(None), None)
    sp = normalize(validate_spec({"category": "generic", "params": {"description": "bình", "approx_size_mm": 120.0}}))
    size = lambda b: max(Bounds.union([pt.bounds for pt in b.parts]).size)        # noqa: E731
    assert abs(size(p._import_cloud(glb, tmp_path / "a", sp, real_size=True)) - 300) < 1
    assert abs(size(p._import_cloud(glb, tmp_path / "b", sp, real_size=False)) - 120) < 1   # không auto_size → ước lượng
    sp.explicit = {"approx_size_mm": 120.0}
    assert abs(size(p._import_cloud(glb, tmp_path / "c2", sp, real_size=True)) - 120) < 1   # người dùng nói rõ → thắng
    tiny = _glb(tmp_path / "t", size=(1.0, 1.0, 1.0)) if (tmp_path / "t").mkdir() is None else None
    assert abs(size(p._import_cloud(tiny, tmp_path / "d", sp.__class__(**{**sp.__dict__, "explicit": {}}),
                                    real_size=True)) - 120) < 1                  # cỡ vô lý (1 mm) → dùng ước lượng


def test_config_tripo_v3_defaults_and_enums(config):
    assert config.get("three_d.tripo_api") == "v3" and config.get("three_d.tripo_geometry_quality") == "detailed"
    config.update({"three_d": {"tripo_texture_quality": "super", "tripo_api": "v9"}})
    assert config.get("three_d.tripo_texture_quality") == "detailed" and config.get("three_d.tripo_api") == "v3"
