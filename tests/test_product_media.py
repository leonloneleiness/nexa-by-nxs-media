import threading
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from nexa.three_d.geometry import gltf, kernel as K
from nexa.three_d.models import Material
from nexa.three_d.product_media import MediaOptions, MediaCancelled, export_media


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
        assert np.asarray(image).std() > 10
    assert len(list(dest.iterdir())) == 2


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


@pytest.mark.parametrize("options", [MediaOptions(size=9999), MediaOptions(pitch=90), MediaOptions(yaw=float("nan"))])
def test_invalid_options(options):
    with pytest.raises(ValueError):
        options.validate()
