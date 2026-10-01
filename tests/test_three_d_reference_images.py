"""Reference images reach design, repair and review without network calls."""
import io

import pytest
from PIL import Image

from nexa.three_d.generation.dsl_designer import DslDesigner
from nexa.three_d.reference_images import VIEWS, load_views
from nexa.three_d.review import review_renders
from nexa.three_d.spec import ModelSpec
from test_three_d_levels import FakeGemini, GOOD, REVIEW_GOOD, REVIEW_BAD, box_glb, mkpipe, wait


def make_views(tmp_path):
    paths = {}
    for i, view in enumerate(VIEWS):
        path = tmp_path / f"{view}.png"
        Image.new("RGBA", (32, 24), (i * 30, 100, 150, 180)).save(path)
        paths[view] = str(path)
    return paths


def test_normalize_all_views_and_reject_invalid_inputs(tmp_path):
    paths = make_views(tmp_path)
    views = load_views(dict(reversed(list(paths.items()))))
    assert list(views) == list(VIEWS)
    for data, mime in views.values():
        assert mime == "image/jpeg"
        with Image.open(io.BytesIO(data)) as img:
            assert img.mode == "RGB" and img.size == (32, 24)
    bad = tmp_path / "fake.png"
    bad.write_text("not an image")
    for paths in ({}, {"unknown": str(bad)}, {"front": str(bad)}, {"front": str(tmp_path / "missing.png")}):
        with pytest.raises(ValueError):
            load_views(paths)


def test_images_and_labels_sent_in_design_repair_refine_and_review(tmp_path):
    class Capture(FakeGemini):
        def generate_json(self, prompt, schema, token, **kw):
            self.last_images = kw.get("images")
            self.last_prompt = prompt
            return super().generate_json(prompt, schema, token, **kw)

    gem = Capture([GOOD, GOOD, GOOD], [REVIEW_GOOD])
    spec = ModelSpec(category="generic", prompt="Vật thể trong ảnh", reference_images=load_views(make_views(tmp_path)))
    designer = DslDesigner(gem)
    designer.design(spec, None)
    assert gem.last_images == list(spec.reference_images.values())
    assert "ảnh 1: Trước" in gem.last_prompt and "ảnh 6: Phải" in gem.last_prompt
    designer.repair(spec, GOOD, {"body": "invalid"}, None)
    assert len(gem.last_images) == 6
    designer.refine(spec, GOOD, b"render", "", [], None)
    assert gem.last_images[0] == (b"render", "image/jpeg")
    assert len(gem.last_images) == 7 and "ảnh 2: Trước" in gem.last_prompt
    assert review_renders(b"render", spec, [], gem, None)["ok"]
    assert len(gem.last_images) == 7 and "ảnh 7: Phải" in gem.last_prompt


def test_reference_pipeline_uses_all_images_saves_sources_and_skips_text_cache(mkpipe, tmp_path, monkeypatch):
    gem = FakeGemini([GOOD, GOOD])
    pipe, jobs, store = mkpipe(gem, dsl_refine_rounds=0, dsl_fallback_below=101)
    def forbidden(*args, **kwargs):
        pytest.fail("Reference generation must not use text planning, cache or cloud fallback")
    monkeypatch.setattr(pipe.planner, "plan", forbidden)
    monkeypatch.setattr(store, "find_cached", forbidden)
    monkeypatch.setattr(pipe, "_cloud_fallback", forbidden)
    paths = make_views(tmp_path)
    job = wait(jobs.submit("Robot theo ảnh, cao 300 mm", reference_images=paths))
    assert job.project_id, job.error
    assert job.error_code != "dsl_failed", job.error
    assert not job.cached
    assert any(c["kind"] == "dsl" and c["images"] for c in gem.calls)
    for view in VIEWS:
        assert list(tmp_path.glob(f"cache*/**/source/reference_images/{view}.jpg"))


def test_invalid_reference_fails_before_ai(mkpipe, tmp_path):
    gem = FakeGemini([GOOD])
    _, jobs, _ = mkpipe(gem)
    job = wait(jobs.submit("mô hình", reference_images={"front": str(tmp_path / "missing.png")}))
    assert job.error_code == "invalid_reference"
    assert not gem.calls


def reference_review(**updates):
    return {**REVIEW_GOOD, "reference_views": [{"view": v, "shape_score": 9} for v in VIEWS], **updates}


@pytest.mark.parametrize("problem", ["wrong_shape", "missing_view", "major_error", "no_review"])
def test_reference_quality_rejects_visually_wrong_or_unverified_model(problem):
    from nexa.three_d.generation.parametric import compile_dsl_parts
    from nexa.three_d.pipeline import ModelBuild
    from nexa.three_d.quality import assess
    spec = ModelSpec(category="generic", reference_images={v: (b"photo", "image/jpeg") for v in VIEWS})
    parts = ModelBuild.from_assembly(compile_dsl_parts(spec, GOOD["parts"]).asm).part_data()
    ai = {"ok": True, **reference_review()}
    if problem == "wrong_shape":
        ai["shape_score"] = 5
    elif problem == "missing_view":
        ai["reference_views"] = ai["reference_views"][:-1]
    elif problem == "major_error":
        ai["issues"] = [{"severity": "major", "issue": "Sai đường bao"}]
    else:
        ai = None
    report = assess(spec, parts, mode="dsl", ai_review=ai)
    assert report.status == "failed"
    assert not report.gates["reference_similarity"]["ok"]
    good = assess(spec, parts, mode="dsl", ai_review={"ok": True, **reference_review()})
    assert good.status == "best_effort" and good.gates["reference_similarity"]["ok"]


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("best_first", [False, True])
def test_cloud_uses_original_images_in_every_attempt_and_forces_review(mkpipe, tmp_path, single, best_first):
    from nexa.three_d.generation.base import ProviderTask
    from nexa.three_d.models import JobState
    glb = box_glb(tmp_path / "cloud.glb")
    other_glb = box_glb(tmp_path / "other.glb", n_boxes=2)
    class ImageProvider:
        name = "image-test"
        capabilities = {"image_to_model", "multiview_to_model"}
        calls = []
        def available(self):
            return True, "ok"
        def create_from_text(self, *a, **kw):
            pytest.fail("Must never convert references to a text-only request")
        def create_from_image(self, data, mime, **kw):
            self.calls.append({"front": (data, mime)})
            return ProviderTask(str(len(self.calls)), "image_to_model")
        def create_from_multiview(self, views, **kw):
            self.calls.append(dict(views))
            return ProviderTask(str(len(self.calls)), "multiview_to_model")
        def get_job_status(self, task):
            task.status, task.progress = "success", 100
            return task
        def download_result(self, task, dest, *a):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((glb if len(self.calls) == 1 else other_glb).read_bytes())
            return dest
    provider = ImageProvider()
    reviews = [reference_review(**REVIEW_BAD), reference_review()]
    gem = FakeGemini([], list(reversed(reviews)) if best_first else reviews)
    pipe, jobs, store = mkpipe(gem, provider_factory=lambda: provider, ai_review=False,
                             candidate_count=2, refinement_rounds=0 if best_first else 1)
    paths = make_views(tmp_path)
    if single:
        paths = {"front": paths["front"]}
    job = wait(jobs.submit("Theo ảnh", quality="high" if best_first else "standard", reference_images=paths))
    assert job.state == JobState.READY, job.error
    assert len(provider.calls) == 2
    assert provider.calls[0] == provider.calls[1] == load_views(paths)
    assert [c["kind"] for c in gem.calls] == ["review", "review"]
    project = store.load(job.project_id)
    assert project.generation_mode == "cloud"
    assert project.quality_report["gates"]["reference_similarity"]["ok"]
    import numpy as np
    from nexa.three_d.geometry import gltf
    saved = gltf.read_glb((store.project_dir(project.id) / "model.glb").read_bytes())
    points = np.vstack([p.mesh.vertices for n in saved.nodes for p in n.primitives])
    assert np.allclose(points.max(axis=0) - points.min(axis=0), project.bounds.size, atol=0.01)


def test_cloud_failure_does_not_silently_fall_back_to_dsl(mkpipe, tmp_path):
    from nexa.three_d.generation.base import ProviderError
    class BrokenProvider:
        name = "broken"
        free_tier = True
        capabilities = {"image_to_model"}
        def available(self):
            return True, "ok"
        def create_from_image(self, *a, **kw):
            raise ProviderError("quota", "Hết hạn mức")
    gem = FakeGemini([GOOD])
    _, jobs, _ = mkpipe(gem, provider_factory=lambda: BrokenProvider())
    paths = make_views(tmp_path)
    job = wait(jobs.submit("Theo ảnh", reference_images={"front": paths["front"]}))
    assert job.error_code == "quota"
    assert not gem.calls


def test_candidates_keep_independent_textures(mkpipe, tmp_path):
    from types import SimpleNamespace
    from nexa.three_d.generation.base import ProviderTask
    from nexa.three_d.models import JobState
    from test_three_d_cloud_fallback import _textured_glb
    blue_dir, red_dir = tmp_path / "blue", tmp_path / "red"
    blue_dir.mkdir()
    red_dir.mkdir()
    blue = _textured_glb(blue_dir, color=(10, 20, 240))
    red = _textured_glb(red_dir, color=(240, 20, 10))
    class Provider:
        name = "test"
        capabilities = {"image_to_model"}
        counter = 0
        def create_from_image(self, *a, **kw):
            self.counter += 1
            return ProviderTask(str(self.counter), "image_to_model", status="success", progress=100)
        def get_job_status(self, task):
            return task
        def download_result(self, task, dest, *a):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((blue if self.counter == 1 else red).read_bytes())
    pipe, _, _ = mkpipe(FakeGemini([]))
    ctx = SimpleNamespace(stage=lambda *a: None, check=lambda: None, warn=lambda *a: None,
                          progress=lambda *a: None, cancelled=False)
    spec = ModelSpec(category="generic", reference_images={"front": (b"img", "image/jpeg")})
    provider = Provider()
    folder = tmp_path / "project"
    builds = [pipe._cloud_candidate(ctx, spec, provider, folder, i, "", "", spec.reference_images, 0, 1)[0] for i in range(2)]
    paths = [folder / b.materials["mat_0"].textures["base_color"] for b in builds]
    assert paths[0] != paths[1]
    assert Image.open(paths[0]).getpixel((0, 0)) == (10, 20, 240)
    assert Image.open(paths[1]).getpixel((0, 0)) == (240, 20, 10)


def test_hf_does_not_drop_additional_views(config, tmp_path):
    from test_three_d_levels import _hf, _poll
    config.set("three_d.hf_3d_spaces", ["tencent/Hunyuan3D-2"])
    provider, calls = _hf(config, tmp_path, {})
    task = provider.create_from_multiview(load_views(make_views(tmp_path)))
    task = _poll(provider, task)
    assert task.status == "failed"
    assert "không nhận đủ ảnh đa góc" in task.error
    assert not calls
