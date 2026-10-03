import threading
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from nexa.three_d.geometry import gltf, kernel as K
from nexa.three_d.models import Material
from nexa.three_d.product_media import MediaOptions, MediaCancelled, export_media
from nexa.three_d.render import RenderResult, render


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "model.glb"
    gltf.write_glb(path, [("body", [(K.box(30, 50, 20).to_mesh(), "blue")], {})],
                   [Material(id="blue", base_color=[0.03, 0.2, 0.7, 1])])
    return SimpleNamespace(load=lambda pid: SimpleNamespace(name="Sản phẩm", asset_path="model.glb"),
                           resolve=lambda pid, rel: path)


def test_png_and_no_overwrite(store, tmp_path):
    dest = tmp_path / "media"
    paths = [export_media(store, "test", dest, MediaOptions(size=256), threading.Event()) for _ in range(2)]
    assert paths[0] != paths[1]
    with Image.open(paths[0]) as image:
        assert image.size == (256, 256)
        assert image.mode == "RGB"
        assert np.asarray(image).std() > 10
    assert len(list(dest.iterdir())) == 2


@pytest.mark.parametrize("color", [[0, 0, 0, 1], [1, 1, 1, 1], [0.03, 0.2, 0.7, 1]])
def test_transparent_png_uses_geometry_and_preserves_object_pixels(store, tmp_path, color):
    mesh = K.box(30, 50, 20).to_mesh()
    material = Material(id="body", base_color=color)
    gltf.write_glb(store.resolve("test", "model.glb"), [("body", [(mesh, "body")], {})], [material])
    dest = tmp_path / "media"
    paths = [export_media(store, "test", dest, MediaOptions(size=256, background=bg, yaw=0, pitch=0),
                          threading.Event()) for bg in ("light", "transparent")]
    with Image.open(paths[0]) as image:
        opaque = np.array(image)
    with Image.open(paths[1]) as image:
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        assert image.size == (256, 256)
        rgba = np.array(image)
    lo, hi = mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)
    expected = render([(mesh, material)], size=256, background="light", bounds=(lo, hi),
                      fixed_extent=float(np.linalg.norm(hi - lo) / 2), ssaa=1, outline=False)
    alpha = rgba[:, :, 3]
    np.testing.assert_array_equal(alpha, expected.mask)
    assert set(np.unique(alpha)) == {0, 255}
    assert alpha[0, 0] == 0
    assert alpha[128, 128] == 255
    np.testing.assert_array_equal(rgba[:, :, :3][alpha > 0], opaque[alpha > 0])
    assert len(list(dest.iterdir())) == 2


def test_renderer_mask_downsamples_coverage_without_changing_rgb_contract():
    items = [(K.box(30, 50, 20).to_mesh(), Material(id="body"))]
    result = render(items, view="iso", size=64, ssaa=2)
    full = render(items, view="iso", size=128, ssaa=1)
    expected = full.mask.reshape(64, 2, 64, 2).mean(axis=(1, 3)).astype(np.uint8)
    np.testing.assert_array_equal(result.mask, expected)
    assert np.any((result.mask > 0) & (result.mask < 255))
    assert result.image.shape == (64, 64, 3)
    assert result.image.dtype == np.uint8
    assert RenderResult(result.image, 0.0, 0.0).mask is None
    empty = render([], size=64, ssaa=2)
    assert empty.mask.shape == (64, 64)
    assert not empty.mask.any()


def test_transparent_mp4_rejected_before_accessing_store_or_creating_output(tmp_path):
    dest = tmp_path / "media"
    with pytest.raises(ValueError, match="MP4"):
        export_media(None, "test", dest, MediaOptions(kind="mp4", background="transparent"), threading.Event())
    assert not dest.exists()


def test_dialog_switches_transparent_png_to_opaque_mp4(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_QUICK_CONTROLS_STYLE", "Basic")
    from pathlib import Path
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
    engine.rootContext().setContextProperty("nexa3d", {"media": {}, "viewerOpen": True, "loading": False})
    path = Path(__file__).resolve().parents[1] / "nexa/ui/qml/ProductMediaDialog.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    dialog = component.create()
    assert dialog is not None, [error.toString() for error in component.errors()]

    def evaluate(source):
        expression = QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, source)
        value, _ = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value

    assert evaluate("mediaBackground.count") == 3
    evaluate("mediaBackground.currentIndex = 2")
    evaluate("format.currentIndex = 1")
    app.processEvents()
    assert evaluate("mediaBackground.count") == 2
    assert evaluate("mediaBackground.currentIndex") == 0
    evaluate("format.currentIndex = 0")
    app.processEvents()
    assert evaluate("mediaBackground.count") == 3
    assert not warnings, warnings


def test_mp4_actual_frames_and_rotation(store, tmp_path):
    progress = []
    path = export_media(store, "test", tmp_path / "media", MediaOptions(kind="mp4", size=256, seconds=3),
                        threading.Event(), progress.append)
    cap = cv2.VideoCapture(str(path))
    frames = []
    try:
        assert cap.get(cv2.CAP_PROP_FPS) == 24
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        cap.release()
    assert len(frames) == 72
    assert frames[0].shape == (256, 256, 3)
    assert np.mean(np.abs(frames[0].astype(float) - frames[18])) > 3
    assert progress[-1] == 100


def test_cancel_removes_partial_output(store, tmp_path):
    event = threading.Event()
    dest = tmp_path / "media"
    with pytest.raises(MediaCancelled):
        export_media(store, "test", dest, MediaOptions(kind="mp4", size=256, seconds=3),
                     event, lambda _: event.set())
    assert not list(dest.iterdir())


def test_encoder_failure_removes_partial_output(store, tmp_path, monkeypatch):
    monkeypatch.setattr(cv2, "VideoWriter", lambda *a: SimpleNamespace(isOpened=lambda: False, release=lambda: None))
    dest = tmp_path / "media"
    with pytest.raises(RuntimeError, match="MP4"):
        export_media(store, "test", dest, MediaOptions(kind="mp4", size=256), threading.Event())
    assert not list(dest.iterdir())


def test_incomplete_mp4_is_not_published(store, tmp_path, monkeypatch):
    capture = cv2.VideoCapture

    def incomplete_capture(path):
        cap = capture(path)
        return SimpleNamespace(read=cap.read, get=lambda prop: 1, release=cap.release)

    monkeypatch.setattr(cv2, "VideoCapture", incomplete_capture)
    dest = tmp_path / "media"
    with pytest.raises(RuntimeError, match="Video"):
        export_media(store, "test", dest, MediaOptions(kind="mp4", size=256, seconds=3), threading.Event())
    assert not list(dest.iterdir())


@pytest.mark.parametrize("options", [MediaOptions(size=9999), MediaOptions(pitch=90), MediaOptions(yaw=float("nan")),
                                      MediaOptions(background="invalid"), MediaOptions(kind="gif")])
def test_invalid_options(options):
    with pytest.raises(ValueError):
        options.validate()
