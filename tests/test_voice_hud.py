"""Giọng AndrewMultilingual + hiệu ứng jarvis, dải tần cho quả cầu, phụ đề theo câu, HUD góc màn hình (Arc Reactor)."""
from __future__ import annotations

import os
import threading
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from nexa.audio import voice_fx  # noqa: E402
from nexa.audio.tts import EDGE_VOICES, N_BANDS, OUT_SR, TTSManager, spectrum_bands  # noqa: E402
from nexa.ui.hud import corner_pos, pick_screen  # noqa: E402


def _tone(freq: float, seconds: float = 1.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(OUT_SR * seconds)) / OUT_SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# ------------------------------------------------------------------ giọng
def test_defaults_are_andrew_and_jarvis(config):
    assert config.get("tts.edge_voice") == "en-US-AndrewMultilingualNeural" == EDGE_VOICES[0]
    assert config.get("tts.effect") == "jarvis" and config.get("tts.edge_pitch_hz") == 0
    assert config.get("ui.theme") == "arc_reactor" and config.get("ui.hud.enabled") is True
    m = TTSManager(config, None)
    assert m._male()                 # Andrew là giọng nam → giọng Windows dự phòng cũng hạ cao độ
    m.shutdown()


def test_jarvis_is_subtle_keeps_level_length_and_is_finite():
    x = _tone(220)
    y = voice_fx.apply("jarvis", x, OUT_SR, 0.5)
    assert y.shape == x.shape and y.dtype == np.float32 and np.all(np.isfinite(y))
    assert abs(np.max(np.abs(y)) - np.max(np.abs(x))) < 1e-3
    assert np.mean(np.abs(y - x)) > 0.005
    # nhẹ hơn robot: giữ tương quan cao với giọng gốc
    rob = voice_fx.apply("robot", x, OUT_SR, 0.5)
    assert np.corrcoef(x, y)[0, 1] > np.corrcoef(x, rob)[0, 1]
    assert voice_fx.apply("jarvis", x, OUT_SR, 0.0) is x or np.allclose(voice_fx.apply("jarvis", x, OUT_SR, 0.0), x)
    assert voice_fx.apply("jarvis", np.zeros(0, np.float32), OUT_SR, 0.5).size == 0
    assert "jarvis" in voice_fx.EFFECTS


# ------------------------------------------------------------------ dải tần cho quả cầu
def test_spectrum_bands_follow_pitch():
    block = int(OUT_SR * 0.03)
    low = spectrum_bands(_tone(120)[:block])
    high = spectrum_bands(_tone(5000)[:block])
    assert len(low) == len(high) == N_BANDS
    assert int(np.argmax(low)) == 0 and int(np.argmax(high)) == N_BANDS - 1
    assert all(0.0 <= v <= 1.0 for v in low + high)
    assert spectrum_bands(np.zeros(block, np.float32)) == [0.0] * N_BANDS
    assert spectrum_bands(np.zeros(4, np.float32)) == [0.0] * N_BANDS


def test_play_emits_bands_then_zero(config, monkeypatch):
    m = TTSManager(config, None)

    class Out:
        def write(self, chunk):
            pass
    monkeypatch.setattr(m, "_ensure_out", lambda: Out())
    seen = []
    m.on_bands = seen.append
    m._play(_tone(440, 0.2))
    assert len(seen) >= 6 and max(seen[0]) > 0.3 and seen[-1] == [0.0] * N_BANDS
    m.shutdown()


def test_subtitle_per_sentence_then_empty(config, monkeypatch):
    config.set("tts.backend", "winrt")
    config.set("tts.effect", "none")

    class Fake:
        def available(self):
            return True, "fake"

        def synth(self, text):
            return np.full(int(OUT_SR * 0.05), 0.1, np.float32), OUT_SR

    m = TTSManager(config, None)
    monkeypatch.setattr(m, "_backend", lambda name: Fake())
    events = []
    monkeypatch.setattr(m, "_play", lambda data: events.append(("play",)))
    m.on_chunk = lambda t: events.append(("sub", t))
    done = threading.Event()
    m.on_idle = lambda kind: done.set()
    m.speak("Câu một. Câu hai.")
    assert done.wait(3)
    assert events == [("sub", "Câu một."), ("play",), ("sub", "Câu hai."), ("play",), ("sub", "")]
    m.shutdown()


# ------------------------------------------------------------------ HUD: vị trí
def test_corner_pos_stays_inside_work_area():
    work = (1920, 0, 1920, 1040)                      # màn hình 2 bên phải, taskbar 40 px
    x, y = corner_pos(work, "bottom_right", 480, 560, 12)
    assert (x, y) == (1920 + 1920 - 480 - 12, 1040 - 560 - 12)
    assert corner_pos(work, "top_left", 480, 560, 12) == (1932, 12)
    assert corner_pos(work, "rubbish", 480, 560, 12) == (x, y)


def test_pick_screen():
    class S:
        def __init__(self, n):
            self.n = n

        def name(self):
            return self.n
    a, b = S("\\\\.\\DISPLAY1"), S("\\\\.\\DISPLAY2")
    assert pick_screen([a, b], "\\\\.\\DISPLAY2", a) is b
    assert pick_screen([a, b], "primary", a) is a
    assert pick_screen([a, b], "cursor", a, b) is b
    assert pick_screen([a, b], "\\\\.\\DISPLAY9", a) is a      # màn hình đã rút → màn hình chính


# ------------------------------------------------------------------ QML
@pytest.fixture(scope="module")
def app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _load(app, name: str):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from nexa.utils.config import QML_DIR
    engine = QQmlEngine()
    warns: list[str] = []
    engine.warnings.connect(lambda ws: warns.extend(w.toString() for w in ws))
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / name)))
    obj = comp.create()
    app.processEvents()
    return (engine, comp, obj), [e.toString() for e in comp.errors()] + warns, warns


def _spin(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def test_hud_qml_subtitle_cards_and_idle(app):
    keep, problems, warns = _load(app, "Hud.qml")
    hud = keep[2]
    assert hud is not None and not problems, problems
    idle = []
    hud.idle.connect(lambda: idle.append(1))
    hud.setProperty("cardSeconds", 1)
    hud.setProperty("subtitle", "Dạ, em đã mở trình duyệt.")
    hud.setProperty("bands", [0.2, 0.5, 0.9, 0.4, 0.3, 0.1, 0.0, 0.0])
    hud.setProperty("outLevel", 0.6)
    for i in range(4):
        hud.addCard(f"Lệnh {i}", "Xong", "done" if i % 2 else "failed")
    _spin(app, 0.1)
    assert hud.property("busy") and hud.property("shownText") == "Dạ, em đã mở trình duyệt."
    hud.setProperty("subtitle", "")
    for corner in ("top_left", "bottom_right"):
        hud.setProperty("corner", corner)
    _spin(app, 2.6)                                   # giữ phụ đề 1,4 s + thẻ 1 s + chờ idle
    assert not hud.property("busy") and idle, "HUD phải báo idle khi hết phụ đề và thẻ"
    assert not warns, warns


def test_orb_qml_loads_with_bands(app):
    keep, problems, _w = _load(app, "Orb.qml")
    orb = keep[2]
    assert orb is not None and not problems, problems
    orb.setProperty("appState", "SPEAKING")
    orb.setProperty("outBands", [1, 0, 0, 0, 0, 0, 0, 0.5])
    orb.setProperty("bands", [1, 0, 0, 0, 0, 0, 0, 0.5])
    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject
    r = QMetaObject.invokeMethod(orb, "bandAt", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", 0.0))
    assert abs(float(r) - 1.0) < 1e-6
    assert abs(float(orb.property("bass")) - 1 / 3) < 1e-6
