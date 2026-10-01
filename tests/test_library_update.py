import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import psutil

from nexa.three_d.models import Model3DProject
from nexa.three_d.manifest import save_manifest

spec = importlib.util.spec_from_file_location("library_update", Path(__file__).resolve().parents[1] / "scripts/update_model_library.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


@pytest.fixture
def library(tmp_path, monkeypatch):
    source, stage = tmp_path / "live", tmp_path / "stage"
    items = []
    for pid in ("project-one", "project-two"):
        live, prepared = source / "projects" / pid, stage / "projects" / pid
        save_manifest(Model3DProject(id=pid, name="Original"), live)
        save_manifest(Model3DProject(id=pid, name="Updated"), prepared)
        (live / "model.glb").write_bytes(b"original")
        (prepared / "model.glb").write_bytes(b"updated")
        items.append({"id": pid, "original_hash": update.tree_hash(live), "staged_hash": update.tree_hash(prepared)})
    (source / "index.json").write_text(json.dumps({"projects": {r["id"]: {} for r in items}, "by_key": {"old": "project-one"}}))
    (stage / "update_report.json").write_text(json.dumps({"source": str(source), "errors": [], "projects": items}))
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])
    return source, stage


def test_publish_swaps_all_and_keeps_originals(library):
    source, stage = library
    update.publish(source, stage)
    record = json.loads((stage / "published.json").read_text())
    for pid in record["updated"]:
        assert (source / "projects" / pid / "model.glb").read_bytes() == b"updated"
        assert (Path(record["backup"]) / pid / "model.glb").read_bytes() == b"original"
    assert json.loads((source / "index.json").read_text())["by_key"] == {}


def test_input_changed_aborts_without_mutation(library):
    source, stage = library
    (source / "projects/project-two/model.glb").write_bytes(b"user edit")
    with pytest.raises(RuntimeError, match="Original changed"):
        update.publish(source, stage)
    assert (source / "projects/project-one/model.glb").read_bytes() == b"original"


def test_mid_swap_failure_restores_all_originals(library, monkeypatch):
    source, stage = library
    rename = Path.rename
    def fail_once(path, target):
        if path.name == "project-two.updating":
            raise OSError("simulated rename error")
        return rename(path, target)
    monkeypatch.setattr(Path, "rename", fail_once)
    with pytest.raises(OSError):
        update.publish(source, stage)
    for pid in ("project-one", "project-two"):
        assert (source / "projects" / pid / "model.glb").read_bytes() == b"original"
    assert json.loads((source / "index.json").read_text())["by_key"]["old"] == "project-one"


def test_running_app_aborts_before_mutation(library, monkeypatch):
    source, stage = library
    proc = SimpleNamespace(pid=1, info={"name": "NEXA.exe", "cmdline": [], "cwd": ""})
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [proc])
    with pytest.raises(RuntimeError, match="NEXA"):
        update.publish(source, stage)
    assert (source / "projects/project-one/model.glb").read_bytes() == b"original"


def test_library_ui_includes_models_older_than_twenty(tmp_path):
    from nexa.three_d.asset_store import AssetStore
    from nexa.ui.three_d_bridge import ThreeDBridge
    store = AssetStore(tmp_path)
    store._index["projects"] = {f"project-{i}": {"name": str(i), "created_at": i} for i in range(37)}
    bridge = SimpleNamespace(svc=SimpleNamespace(store=store))
    rows = ThreeDBridge._model_list(bridge)
    assert len(rows) == 37
    assert rows[-1]["id"] == "project-0"
