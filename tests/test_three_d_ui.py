"""Mô hình 3D — QML smoke load (offscreen), nạp GLB mẫu vào NexaMesh, RuntimeLoader, cấu hình và đóng gói.

Nền tảng offscreen dùng renderer phần mềm (không vẽ được 3D), nên ở đây chỉ kiểm tra QML nạp/khởi tạo được, không cảnh
báo và dữ liệu lưới đúng. Kiểm thử render thật (D3D11) nằm ở scripts/smoke_3d_viewer.py --window.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import Property, QObject, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine  # noqa: E402

from nexa.utils.config import QML_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture(scope="module")
def ctrl(app, tmp_path_factory):
    from nexa.three_d.asset_store import AssetStore
    from nexa.three_d.service import ThreeDService
    from nexa.utils.config import Config
    d = tmp_path_factory.mktemp("ui3d")
    cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
    cfg.set("three_d.ai_review", False)
    holder = {}

    class G:
        running = False

    class C:
        config = cfg
        gestures = G()
        three_d = ThreeDService(cfg, notify=lambda k, v: holder["b"].post(k, v) if "b" in holder else None,
                                store=AssetStore(d / "cache"), provider_factory=lambda: None)
    c = C()
    c.holder = holder
    job = c.three_d.submit("Tạo UAV mini bốn cánh camera phía trước", open_when_ready=False)
    while not job.terminal:
        time.sleep(0.05)
    c.project_id = job.project_id
    yield c
    c.three_d.shutdown()


class FakeNexa(QObject):
    changed = Signal()
    toast = Signal(str, bool)

    @Property(bool, notify=changed)
    def showFps(self):
        return True


def _load(app, qml: Path, context: dict) -> tuple[object, list[str]]:
    from nexa.ui.three_d_bridge import register_qml_types
    register_qml_types()
    engine = QQmlEngine()
    warns: list[str] = []
    engine.warnings.connect(lambda ws: warns.extend(w.toString() for w in ws))
    for k, v in context.items():
        engine.rootContext().setContextProperty(k, v)
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(qml)))
    obj = comp.create()
    errors = [e.toString() for e in comp.errors()]
    app.processEvents()
    return (engine, comp, obj), errors + warns


def _wait(app, cond, t=10.0):
    end = time.monotonic() + t
    while time.monotonic() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    return cond()


@pytest.mark.parametrize("name", ["ModelViewer.qml", "ModelPartPanel.qml", "ModelGenerationPanel.qml", "ProductMediaDialog.qml", "BuildDossierDialog.qml"])
def test_qml_3d_files_load_without_warnings(app, ctrl, name):
    from nexa.ui.three_d_bridge import ThreeDBridge
    bridge = ThreeDBridge(ctrl)
    ctrl.holder["b"] = bridge
    ctrl.three_d.viewer.open(ctrl.project_id)
    assert _wait(app, lambda: bool(bridge.model.get("parts")) and not bridge.loading)
    if name == "BuildDossierDialog.qml":
        bridge.refreshBuildDossier()
        assert bridge.buildDossier.get("rows")
    keep, problems = _load(app, QML_DIR / name, {"nexa3d": bridge, "nexa": FakeNexa()})
    assert keep[2] is not None and not problems, problems
    if name == "ModelGenerationPanel.qml":
        panel = keep[2]
        panel.setProperty("width", 640)
        panel.setProperty("height", 800)
        panel.setReference("front", QUrl.fromLocalFile(str(QML_DIR.parents[2] / "missing-test.png")).toString())
        assert panel.property("referenceCount") == 1
        panel.setReference("front", "")
        assert panel.property("referenceCount") == 0
    ctrl.three_d.viewer.close()


def test_reference_bridge_passes_labelled_local_files_and_honors_lock(app, ctrl, tmp_path, monkeypatch):
    from nexa.ui.three_d_bridge import ThreeDBridge
    bridge = ThreeDBridge(ctrl)
    calls = []
    monkeypatch.setattr(ctrl.three_d, "submit", lambda *a, **kw: calls.append((a, kw)))
    refs = {"front": QUrl.fromLocalFile(str(tmp_path / "ảnh trước.png")).toString()}
    bridge.generateFromReferences("", "high", refs)
    assert len(calls) == 1
    assert calls[0][1]["reference_images"] == {"front": str(tmp_path / "ảnh trước.png").replace("\\", "/")}
    assert calls[0][1]["quality"] == "high"
    bridge.generateFromReferences("x", "standard", {"front": "https://example.com/photo.png"})
    ctrl.three_d.locked = True
    try:
        bridge.generateFromReferences("x", "standard", refs)
        assert len(calls) == 1
    finally:
        ctrl.three_d.locked = False
    bridge.generateFromReferences("Giữ khoảng gãy", "high", refs, "cad")
    assert len(calls) == 2 and calls[-1][1]["mode"] == "reference_cad"
    assert calls[-1][0][0] == "Giữ khoảng gãy"


def test_active_job_tracks_running_work_before_queue_and_retains_completion(app, ctrl, monkeypatch):
    from nexa.ui.three_d_bridge import ThreeDBridge
    bridge = ThreeDBridge(ctrl)
    monkeypatch.setattr(bridge, "_model_list", lambda: [])
    bridge._handle("3d_job", {"id": "one", "state": "planning", "created": 1, "terminal": False})
    bridge._handle("3d_job", {"id": "two", "state": "queued", "created": 2, "terminal": False})
    assert bridge.activeJob["id"] == "one"
    bridge._handle("3d_job", {"id": "one", "state": "ready", "created": 1, "terminal": True})
    assert bridge.activeJob["id"] == "two"
    bridge._handle("3d_job", {"id": "two", "state": "failed", "created": 2, "terminal": True})
    assert bridge.activeJob["id"] == "two" and bridge.activeJob["terminal"]


def test_build_records_bridge_roundtrip_and_project_guard(app, ctrl, tmp_path, monkeypatch):
    from nexa.ui.three_d_bridge import ThreeDBridge
    from nexa.utils import config
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    bridge = ThreeDBridge(ctrl)
    ctrl.holder["b"] = bridge
    ctrl.three_d.viewer.open(ctrl.project_id)
    assert _wait(app, lambda: bool(bridge.model.get("parts")) and not bridge.loading)
    bridge.refreshBuildDossier()
    pid = bridge.buildDossier["rows"][1]["id"]
    assert not bridge.saveBuildRecord("wrong-project", pid, {"mode": "buy"})
    assert bridge.saveBuildRecord(ctrl.project_id, pid, {"mode": "buy", "model_number": "TEST-001", "quantity": 2})
    bridge.refreshBuildDossier()
    assert bridge.buildDossier["rows"][1]["record"]["model_number"] == "TEST-001"
    assert not bridge.buildDossier["ready_to_build"]
    ctrl.three_d.viewer.close()
    assert _wait(app, lambda: not bridge.viewerOpen)


def test_glb_sample_loads_into_nexamesh(app, ctrl):
    """GLB mẫu trong cache → bridge đóng gói lưới (đơn vị xem) → NexaMesh có dữ liệu và bounds đúng."""
    from nexa.ui.three_d_bridge import MeshGeometry, MeshStore, ThreeDBridge
    bridge = ThreeDBridge(ctrl)
    ctrl.holder["b"] = bridge
    ctrl.three_d.viewer.open(ctrl.project_id)
    assert _wait(app, lambda: bool(bridge.model.get("parts")) and not bridge.loading)
    assert bridge.loadError == ""
    parts = bridge.model["parts"]
    assert len(parts) == 26 and all(p["prims"] for p in parts)     # UAV 4 cánh: 25 bộ phận + GPS
    key = parts[0]["prims"][0]["key"]
    pm = MeshStore.get(key)
    assert pm is not None and pm.stride in (24, 56) and len(pm.indices) % 12 == 0
    geo = MeshGeometry()
    geo.source = key
    assert geo.stride() == pm.stride and geo.vertexData().size() == len(pm.vertices)
    allmax = max(max(abs(x) for x in MeshStore.get(pr["key"]).bmax) for p in parts for pr in p["prims"])
    assert 60 < allmax < 130                                            # mô hình chuẩn hóa về bán kính ~100
    mat = parts[0]["prims"][0]["material"]
    assert mat["color"].startswith("#") and 0 <= mat["roughness"] <= 1
    ctrl.three_d.viewer.close()
    assert _wait(app, lambda: not bridge.viewerOpen)


def test_runtime_loader_plugin_available(app, tmp_path):
    """QtQuick3D.AssetUtils (RuntimeLoader) có trong PySide6 — cần cho mở tệp GLB/glTF/OBJ trực tiếp và cho bản EXE."""
    from nexa.three_d.geometry import gltf
    from nexa.three_d.geometry import kernel as K
    from nexa.three_d.models import Material
    glb = tmp_path / "sample.glb"
    gltf.write_glb(glb, [("cube", [(K.box(10, 10, 10).to_mesh(), "m")], {})], [Material(id="m")])
    qml = tmp_path / "rl.qml"
    qml.write_text('import QtQuick\nimport QtQuick3D\nimport QtQuick3D.AssetUtils\nimport QtQuick3D.Helpers\n'
                   'Node { RuntimeLoader { id: rl; source: "%s" } property alias status: rl.status }\n'
                   % QUrl.fromLocalFile(str(glb)).toString(), encoding="utf-8")
    keep, problems = _load(app, qml, {})
    assert keep[2] is not None and not problems, problems


def test_studio_hdr_asset_present():
    f = ROOT / "assets" / "3d" / "studio.hdr"
    assert f.is_file() and f.read_bytes()[:10] == b"#?RADIANCE"


def test_main_qml_references_3d_components():
    main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert "ModelViewer.qml" in main and "ModelGenerationPanel" in main and "nexa3d" in main
    assert (QML_DIR / "ModelViewer.qml").stat().st_size < 30_000        # viewer ở file riêng, không nhồi vào Main.qml


def test_three_d_config_defaults(config):
    assert config.get("three_d.enabled") is True and config.get("three_d.quality_threshold") == 90
    assert config.get("three_d.gesture.fist_hold_ms") == 500 and config.get("three_d.gesture.acquire_ms") == 200
    config.update({"three_d": {"refinement_rounds": 7, "gesture": {"open_hold_ms": 5}}})
    assert config.get("three_d.refinement_rounds") == 2 and config.get("three_d.gesture.open_hold_ms") == 150
    assert config.config_warnings


def test_api_keys_never_in_settings_or_logs(config, tmp_path, monkeypatch):
    from nexa.utils.logging import redact
    monkeypatch.setenv("TRIPO_API_KEY", "tsk_secret_1234567890abcd")
    assert "tsk_secret" not in redact("gọi Tripo với key tsk_secret_1234567890abcd")
    assert "msy_" not in redact("Authorization: Bearer msy_abcdefghijklmnop123")
    config.save()
    assert "tsk_" not in config.settings_path.read_text(encoding="utf-8")


def test_pyinstaller_build_includes_3d():
    src = (ROOT / "scripts" / "build_exe.py").read_text(encoding="utf-8")
    for need in ("manifold3d", "fast_simplification", "PySide6.QtQuick3D", "AssetUtils", "Helpers", "THREE_D_MODULES"):
        assert need in src
    import importlib
    import PySide6
    qml = Path(PySide6.__file__).parent / "qml" / "QtQuick3D"
    assert (qml / "qmldir").exists() and (qml / "AssetUtils" / "qmldir").exists() and (qml / "Helpers" / "qmldir").exists()
    for mod in ("manifold3d", "fast_simplification"):
        importlib.import_module(mod)
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "manifold3d" in req and "fast-simplification" in req


def test_benchmark_has_enough_prompts_per_group():
    from nexa.three_d.benchmark import GROUPS, by_group, spec_matches
    from nexa.three_d.planner import Planner
    g = by_group()
    assert set(g) == set(GROUPS) and all(len(v) >= 50 for v in g.values())
    pl = Planner(None)
    for cases in g.values():
        for c in cases[:10]:
            assert spec_matches(c, pl.plan(c.prompt).spec)[0], c.prompt


def test_exploded_parts_stay_above_floor(app, ctrl):
    """Tách rời: bộ phận tháo đi xuống không được chui dưới sàn — viewer nâng mô hình (explodeLift) đúng bằng phần lún."""
    from nexa.ui.three_d_bridge import ThreeDBridge
    bridge = ThreeDBridge(ctrl)
    ctrl.holder["b"] = bridge
    ctrl.three_d.viewer.open(ctrl.project_id)
    assert _wait(app, lambda: bool(bridge.model.get("parts")) and not bridge.loading)
    keep, problems = _load(app, QML_DIR / "ModelViewer.qml", {"nexa3d": bridge, "nexa": FakeNexa()})
    root = keep[2]
    assert root is not None and not problems, problems
    parts = bridge.model["parts"]
    assert all("min_y" in p for p in parts)
    assert root.property("explodeLift") == 0
    ctrl.three_d.viewer.explode()
    assert _wait(app, lambda: root.property("explodeT") >= 0.999, 5.0)
    app.processEvents()
    bottom = bridge.model["bottom"]
    lowest = min(p["min_y"] + sum(c["v"][1] for c in p["explode"]) - bottom for p in parts)
    lift = root.property("explodeLift")
    assert lift == pytest.approx(max(0.0, -lowest), abs=1e-3)
    assert lowest < 0 and lift > 0            # UAV có bộ phận tháo xuống (pin/càng) → trước đây chui dưới sàn
    assert lowest + lift >= -1e-3
    ctrl.three_d.viewer.close()


def test_voice_close_hides_workspace(app, ctrl):
    """Lệnh giọng nói "đóng mô hình" → close_3d_viewer → viewer đóng và khung Mô hình 3D ẩn luôn."""
    from types import SimpleNamespace

    from nexa.three_d.tools import h_close
    from nexa.ui.three_d_bridge import ThreeDBridge
    bridge = ThreeDBridge(ctrl)
    ctrl.holder["b"] = bridge
    ctrl.three_d.viewer.open(ctrl.project_id)
    assert _wait(app, lambda: bridge.viewerOpen and bridge.workspace and not bridge.loading)
    res = h_close({}, SimpleNamespace(services=SimpleNamespace(three_d=ctrl.three_d)))
    assert res.ok
    assert _wait(app, lambda: not bridge.viewerOpen and not bridge.workspace)
