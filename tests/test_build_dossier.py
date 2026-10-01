import json

import pytest

from nexa.three_d.build_dossier import (ASSEMBLY_ID, build_dossier, export_dossier, load_records, save_record)
from nexa.three_d.build_profiles import coverage
from nexa.three_d.models import Model3DProject, Part3D
from nexa.three_d.spec import CATEGORIES


def project(category="rover"):
    return Model3DProject(id="test-project", name="Máy thử", category=category,
                          parts=[Part3D(id="motor", name_vi="Motor", category="motor")])


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_category_has_explicit_profile_and_no_fake_approval(category):
    assert coverage()[category]
    p = project(category)
    p.quality_score = 100
    p.status = "ready"
    d = build_dossier(p)
    assert not d["ready_to_build"]
    assert len(d["requirements"]) >= 3
    assert {r["id"] for r in d["rows"]} == {ASSEMBLY_ID, "motor"}
    assert not any(r["verified"] or r["record"].get("quantity") for r in d["rows"])


def test_whole_bearing_not_counted_as_internal_shopping_items():
    p = project("bearing")
    p.parts = [Part3D(id="balls", name_vi="Tám viên bi", category="ball", dimensions={"count": 8})]
    d = build_dossier(p)
    assert "nguyên cụm" in d["rows"][0]["suggestion"]
    assert "không tự cộng" in d["rows"][1]["suggestion"]
    assert not d["rows"][1]["record"].get("quantity")


def test_records_persist_and_geometry_change_stales_only_old_records(tmp_path):
    p = project()
    save_record(p, "motor", {"mode": "buy", "model_number": "ABC", "quantity": 4,
                              "url": "https://example.org/spec"}, tmp_path)
    records, stale = load_records(p, tmp_path)
    assert not stale and records["motor"]["quantity"] == 4
    assert not build_dossier(p, records)["ready_to_build"]
    p.parts[0].dimensions["shaft"] = 7
    assert load_records(p, tmp_path)[1]
    save_record(p, ASSEMBLY_ID, {"mode": "reference"}, tmp_path)
    d = build_dossier(p, load_records(p, tmp_path)[0])
    assert d["rows"][1]["stale"]
    assert not d["rows"][0]["stale"]


@pytest.mark.parametrize("record", [{"url": "file:///C:/secret"}, {"url": "javascript:alert(1)"},
                                   {"url": "https://user:pass@example.org"}, {"quantity": -2},
                                   {"quantity": 1.5}, {"mode": "verified"}])
def test_reject_bad_record(tmp_path, record):
    with pytest.raises(ValueError):
        save_record(project(), "motor", record, tmp_path)


def test_export_escaped_portable_and_unique(tmp_path):
    p = project()
    p.name = "<script>alert(1)</script>"
    d = build_dossier(p)
    a = export_dossier(d, tmp_path)
    b = export_dossier(d, tmp_path)
    assert a != b
    assert "<script>" not in a.read_text(encoding="utf-8")
    data = json.loads(a.with_name("dossier.json").read_text(encoding="utf-8"))
    assert data["project_id"] == p.id and not data["ready_to_build"]


def test_scaled_and_cloud_models_blocked():
    p = project()
    p.generation_mode = "cloud"
    p.metadata["fit_scale"] = 0.5
    d = build_dossier(p)
    assert any("co giãn" in b for b in d["blockers"])
    assert any("thiết kế kỹ thuật lại" in b for b in d["blockers"])


def test_old_manifest_works_without_migration():
    p = Model3DProject.from_dict({"id": "legacy", "name": "Cũ", "category": "bearing"})
    assert build_dossier(p)["rows"][0]["id"] == ASSEMBLY_ID
