"""Mô hình 3D — lõi: ModelSpec, planner, kernel hình học, bu-lông ren helix, DSL whitelist, GLB, validator, manifest."""
from __future__ import annotations

import json
import math
import struct

import numpy as np
import pytest

from nexa.three_d.geometry import dsl as D
from nexa.three_d.geometry import gltf
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.manifest import load_manifest, save_manifest, validate_manifest
from nexa.three_d.models import Bounds, ExplosionStep, Material, Model3DProject, Part3D
from nexa.three_d.planner import LocalPlanner, Planner, detect_category
from nexa.three_d.spec import SpecError, normalize, validate_spec
from nexa.three_d.validator import AssetError, Limits, safe_relpath, validate_glb_bytes


def spec(cat, **params):
    return normalize(validate_spec({"category": cat, "params": params}))


# ------------------------------------------------------------------ ModelSpec
def test_spec_valid_and_iso_defaults():
    s = spec("bolt", diameter_mm=8, length_mm=30)
    assert s.params["pitch_mm"] == 1.25 and s.params["head"] == "hex" and s.params["thread"] == "technical"
    assert any("ISO" in d for d in s.defaults_used)


@pytest.mark.parametrize("data", [
    {"category": "bolt", "params": {"diameter_mm": 8, "length_mm": 30}, "evil": 1},              # trường lạ top-level
    {"category": "bolt", "params": {"diameter_mm": 8, "length_mm": 30, "code": "import os"}},    # trường lạ trong params
    {"category": "rocket", "params": {}},                                                          # loại lạ
    {"category": "bolt", "params": {"diameter_mm": 8}},                                            # thiếu bắt buộc
    {"category": "bolt", "params": {"diameter_mm": "8", "length_mm": 30}},                         # sai kiểu
])
def test_spec_rejects_bad_input(data):
    with pytest.raises(SpecError):
        validate_spec(data)


@pytest.mark.parametrize("params", [{"diameter_mm": 0.5, "length_mm": 30}, {"diameter_mm": 8, "length_mm": 9000},
                                    {"diameter_mm": 8, "length_mm": 30, "pitch_mm": 5.0},
                                    {"diameter_mm": 8, "length_mm": 2}])
def test_spec_size_limits(params):
    with pytest.raises(SpecError):
        validate_spec({"category": "bolt", "params": params})


def test_uav_arm_count_must_be_supported():
    with pytest.raises(SpecError):
        validate_spec({"category": "uav", "params": {"arm_count": 5}})


# ------------------------------------------------------------------ planner
@pytest.mark.parametrize("text,cat", [
    ("Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm.", "bolt"), ("Tạo một UAV mini bốn cánh", "uav"),
    ("Tạo xe tự hành sáu bánh có LiDAR và camera.", "rover"), ("Tạo robot hình người.", "humanoid"),
    ("Tạo robot hình chó, mỗi chân có ba khớp.", "quadruped"), ("Tạo trực thăng cứu hộ", "helicopter"),
    ("tạo đai ốc M10", "nut"), ("tạo bu lông M8 có đai ốc", "bolt"), ("tạo cái cốc", "generic")])
def test_detect_category(text, cat):
    assert detect_category(text) == cat


def test_planner_bolt_exact_numbers():
    r = Planner(None).plan("Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm.")
    assert r.spec.params["diameter_mm"] == 8 and r.spec.params["length_mm"] == 30 and r.spec.params["pitch_mm"] == 1.25
    assert r.spec.explicit == {"diameter_mm": 8.0, "length_mm": 30.0, "pitch_mm": 1.25}


def test_planner_asks_missing_required():
    r = Planner(None).plan("tạo bu lông M8")
    assert r.spec is None and "dài bao nhiêu" in r.questions[0]


def test_planner_sample_prompts():
    pl = Planner(None)
    uav = pl.plan("Tạo một UAV mini bốn cánh, thân carbon màu đen, camera phía trước.").spec
    assert uav.params["arm_count"] == 4 and uav.params["camera"] == "front" and uav.style["finish"] == "carbon"
    assert pl.plan("Tạo robot hình chó, mỗi chân có ba khớp.").spec.params["joints_per_leg"] == 3
    assert pl.plan("Tạo xe tự hành sáu bánh có LiDAR").spec.params["wheel_count"] == 6
    assert pl.plan("Tạo trực thăng dân sự có tời cứu hộ").spec.params["role"] == "civil"


class FakeGemini:
    def __init__(self, data):
        self.data = data

    def status(self):
        return True, "ok"

    def generate_json(self, prompt, schema, token, **kw):
        return self.data


def test_explicit_user_numbers_override_gemini():
    from nexa.core.safety import CancelToken
    g = FakeGemini({"category": "bolt", "name": "Bu lông", "params": {"diameter_mm": 10, "length_mm": 45}})
    r = Planner(g).plan("Tạo bu-lông M8 dài 30 mm", token=CancelToken(None, 0))
    assert r.spec.params["diameter_mm"] == 8 and r.spec.params["length_mm"] == 30
    assert any("dùng số người dùng" in w for w in r.warnings)


def test_invalid_gemini_spec_falls_back_to_local():
    from nexa.core.safety import CancelToken
    g = FakeGemini({"category": "uav", "params": {"arm_count": 4, "exec": "rm -rf"}})
    r = Planner(g).plan("Tạo UAV bốn cánh", token=CancelToken(None, 0))
    assert r.spec is not None and r.spec.source == "local" and any("không hợp lệ" in w for w in r.warnings)


# ------------------------------------------------------------------ kernel
def test_primitives_are_watertight():
    for s in (K.rounded_box(40, 30, 20, 4), K.cylinder(5, 10), K.capsule(5, 30), K.torus(10, 2),
              K.revolve(P.fillet_polygon([(0, 0), (20, 0), (20, 5), (0, 5)], 1.0)),
              K.sweep(P.circle(2, 12), P.spline_through([(0, 0, 0), (20, 0, 10), (40, 10, 0)], 20))):
        assert s.status_ok and not s.is_empty and s.volume() > 0


def test_loft_with_apex_and_bounds():
    secs = [K.section_on_plane(P.superellipse(20 * k + 1e-9, 10 * k, 3, 32), (x, 0, 0), (1, 0, 0), (0, 1, 0))
            for x, k in ((0, 1), (30, 1), (60, 0))]
    s = K.loft(secs)
    lo, hi = s.bounds()
    assert s.status_ok and np.allclose(lo[0], 0) and np.allclose(hi[0], 60)


def test_fillet_polygon_radius_and_involute_gear():
    sq = P.fillet_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], 2.0, 8)
    assert abs(P.signed_area(sq) - (100 - (4 - math.pi) * 4)) < 0.2
    g = P.involute_gear(2, 20)
    r = np.linalg.norm(g, axis=1)
    assert abs(r.max() - 22) < 1e-6 and abs(r.min() - 17.5) < 1e-6


def test_rotation_minimizing_frames_orthonormal():
    path = P.spline_through([(0, 0, 0), (10, 5, 0), (20, 0, 5), (30, 5, 10)], 30)
    T, N, B = K.rotation_minimizing_frames(path)
    assert np.allclose(np.einsum("ij,ij->i", T, N), 0, atol=1e-6) and np.allclose(np.linalg.norm(B, axis=1), 1)


# ------------------------------------------------------------------ bu-lông M8×30
@pytest.fixture(scope="module")
def bolt_m8():
    from nexa.three_d.generation.parametric import build_parametric
    return build_parametric(spec("bolt", diameter_mm=8, length_mm=30, pitch_mm=1.25))


def test_bolt_m8x30_dimensions_and_thread(bolt_m8):
    from nexa.three_d.quality import PartData, measure_bolt
    bp = bolt_m8.part("bolt")
    m = measure_bolt(PartData(bp.part, [(me, Material(id="x")) for me, _ in bp.meshes]), spec("bolt", diameter_mm=8,
                                                                                            length_mm=30, pitch_mm=1.25))
    assert abs(m["major_diameter"] - 8.0) < 0.02
    assert abs(m["length"] - 30.0) < 0.05
    assert abs(m["pitch"] - 1.25) < 0.01                      # bước ren đo trên lưới
    assert abs(m["helix_phase_offset"] - 0.5) < 0.05          # helix thật (không phải rãnh tròn song song)
    assert abs(m["across_flats"] - 13.0) < 0.05               # ISO 4017 M8: s = 13
    assert bolt_m8.metadata["thread_mode"] == "technical"


def test_iso_thread_profile():
    phase = np.linspace(0, 1.25, 400)
    r = K.iso_basic_radius(phase, 1.25, 4.0)
    assert abs(r.max() - 4.0) < 1e-9 and abs(r.min() - (4.0 - 0.541266 * 1.25)) < 1e-9


def test_illustrative_thread_is_not_marked_technical():
    from nexa.three_d.generation.parametric import build_parametric
    a = build_parametric(spec("bolt", diameter_mm=6, length_mm=40, thread="illustrative"))
    assert a.metadata["thread_mode"] == "illustrative"
    assert any(mid.endswith("_thread") for _, mid in a.part("bolt").meshes)


def test_bolt_bounding_box(bolt_m8):
    size = bolt_m8.bounds.size                                     # asset: X rộng, Y cao (trục bu-lông), Z dài
    assert abs(size[1] - (30 + 0.6 + 5.3)) < 0.2 and abs(size[0] - 13 / math.cos(math.radians(30))) < 0.3


# ------------------------------------------------------------------ DSL
def test_dsl_compiles_whitelisted_ops():
    node = {"op": "subtract", "base": {"op": "revolve", "profile": {"points": [[0, 0], [30, 0], [28, 80], [0, 80]], "fillet": 2}},
            "cut": [{"op": "translate", "offset": [0, 0, 5], "child": {"op": "cylinder", "radius": 25, "height": 90}}]}
    s = D.compile_dsl(node)
    assert s.status_ok and s.volume() > 0


@pytest.mark.parametrize("node", [
    {"op": "exec", "code": "import os"}, {"op": "box", "size": [1, 1, 1], "python": "x"},
    {"op": "box", "size": [1, 1, 1e9]}, {"op": "box", "size": [1, 1, float("nan")]}, "box",
    {"op": "union", "children": [{"op": "__import__"}]}, {"op": "cylinder", "radius": -1, "height": 2},
])
def test_dsl_rejects(node):
    with pytest.raises(D.DslError):
        D.compile_dsl(node)


def test_dsl_depth_and_node_limits():
    deep = {"op": "box", "size": [1, 1, 1]}
    for _ in range(D.MAX_DEPTH + 2):
        deep = {"op": "translate", "offset": [0, 0, 0], "child": deep}
    with pytest.raises(D.DslError):
        D.compile_dsl(deep)


# ------------------------------------------------------------------ GLB + validator
def _cube_mesh():
    return K.box(10, 10, 10).to_mesh()


def test_glb_roundtrip(tmp_path):
    mat = Material(id="m", base_color=[1, 0, 0, 1])
    size = gltf.write_glb(tmp_path / "a.glb", [("p1", [(_cube_mesh(), "m")], {"x": 1})], [mat])
    data = (tmp_path / "a.glb").read_bytes()
    assert data[:4] == b"glTF" and len(data) == size
    doc = gltf.read_glb(data)
    assert doc.nodes[0].name == "p1" and doc.nodes[0].extras == {"x": 1}
    v = doc.nodes[0].primitives[0].mesh.vertices
    assert np.allclose(v.min(axis=0), -5, atol=1e-4) and np.allclose(v.max(axis=0), 5, atol=1e-4)   # mm ⇄ m
    assert validate_glb_bytes(data).ok


def _glb_with_json(js: dict, bin_: bytes = b"") -> bytes:
    j = json.dumps(js).encode()
    j += b" " * ((4 - len(j) % 4) % 4)
    b = bin_ + b"\0" * ((4 - len(bin_) % 4) % 4)
    total = 12 + 8 + len(j) + (8 + len(b) if b else 0)
    out = struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(j), 0x4E4F534A) + j
    if b:
        out += struct.pack("<II", len(b), 0x004E4942) + b
    return out


def test_validator_rejects_bad_magic_and_length():
    assert not validate_glb_bytes(b"NOTGLB" + b"\0" * 30).ok
    good = _glb_with_json({"asset": {"version": "2.0"}})
    assert not validate_glb_bytes(good[:-4]).ok


def test_validator_rejects_external_uri():
    js = {"asset": {"version": "2.0"}, "buffers": [{"uri": "http://evil/x.bin", "byteLength": 10}],
          "images": [{"uri": "../../secret.png"}]}
    rep = validate_glb_bytes(_glb_with_json(js))
    assert not rep.ok and any("URI" in e for e in rep.errors)


def test_validator_rejects_nan(tmp_path):
    m = _cube_mesh()
    m.vertices[0, 0] = np.nan
    gltf.write_glb(tmp_path / "n.glb", [("p", [(m, "x")], {})], [Material(id="x")])
    rep = validate_glb_bytes((tmp_path / "n.glb").read_bytes())
    assert not rep.ok and any("NaN" in e for e in rep.errors)


def test_validator_size_and_triangle_limits(tmp_path):
    gltf.write_glb(tmp_path / "s.glb", [("p", [(K.sphere(10, 64).to_mesh(), "x")], {})], [Material(id="x")])
    data = (tmp_path / "s.glb").read_bytes()
    assert not validate_glb_bytes(data, Limits(max_asset_mb=len(data) / 2 / 1024 / 1024)).ok
    assert not validate_glb_bytes(data, Limits(max_triangles=100)).ok


@pytest.mark.parametrize("rel", ["../x.glb", "..\\..\\x", "C:\\Windows\\x", "/etc/passwd", "\\\\server\\s", "file:///c:/x",
                                 "http://a/b", "parts/../../x", ""])
def test_path_traversal_rejected(tmp_path, rel):
    with pytest.raises(AssetError):
        safe_relpath(tmp_path, rel)


def test_safe_relpath_ok(tmp_path):
    assert safe_relpath(tmp_path, "parts/a.glb") == (tmp_path / "parts" / "a.glb").resolve()


# ------------------------------------------------------------------ manifest
def _project(parts, plan=None):
    return Model3DProject(id="20260101-000000-abcdef", name="t", parts=parts, materials=[Material(id="m")],
                          explosion_plan=plan or [], has_assembly=len(parts) > 1)


def _part(pid, parent=None, dist=10.0):
    return Part3D(id=pid, name_vi=pid, aliases=[pid], parent_id=parent, material="m", explode_distance=dist,
                  explode_vector=[0, 1, 0], explode_order=1, bounds=Bounds([0, 0, 0], [1, 1, 1]))


def test_manifest_valid_and_roundtrip(tmp_path):
    p = _project([_part("a", dist=0), _part("b", "a")], [ExplosionStep(1, ["b"])])
    assert validate_manifest(p, tmp_path).ok
    save_manifest(p, tmp_path)
    q = load_manifest(tmp_path)
    assert q.parts[1].parent_id == "a" and q.explosion_plan[0].part_ids == ["b"]


def test_manifest_hierarchy_cycle_and_duplicates():
    rep = validate_manifest(_project([_part("a", "b"), _part("b", "a")], [ExplosionStep(1, ["a", "b"])]))
    assert any("vòng lặp" in e for e in rep.errors)
    rep = validate_manifest(_project([_part("a", dist=0), _part("a", dist=0)]))
    assert any("trùng id" in e for e in rep.errors)


def test_manifest_explosion_plan_complete():
    rep = validate_manifest(_project([_part("a", dist=0), _part("b", "a")], []))
    assert any("thiếu" in e for e in rep.errors)


def test_manifest_bad_transform_and_path(tmp_path):
    p = _part("a", dist=0)
    p.transform.rotation = [0, 0, 0, 2]
    p.asset = "../../evil.glb"
    rep = validate_manifest(_project([p]), tmp_path)
    assert any("quaternion" in e for e in rep.errors) and any("'..'" in e for e in rep.errors)


def test_local_planner_never_calls_network():
    raw = LocalPlanner().parse("Tạo UAV sáu cánh khung 450 mm")
    assert raw["params"]["arm_count"] == 6 and raw["params"]["wheelbase_mm"] == 450
