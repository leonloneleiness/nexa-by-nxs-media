"""Giao diện chính mới: icon trạng thái, dock tròn, hội thoại gộp thẻ tác vụ, màu theo trạng thái, vòng CPU/RAM/GPU/AI."""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from nexa.utils.config import QML_DIR  # noqa: E402


class _NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeNvml:
    def __init__(self, value):
        self.value = value
        self.closed = False

    def sample(self):
        return self.value

    def close(self):
        self.closed = True


# ------------------------------------------------------------------ thông số máy
def test_sysstats_with_gpu_and_without():
    from nexa.ui.sysstats import SysStats
    s = SysStats(nvml=_FakeNvml((42.0, 25.0)))
    v = s.sample(1234.0)
    assert set(v) == {"cpu", "ram", "gpu", "vram", "ai_ms"}
    assert 0.0 <= v["cpu"] <= 100.0 and 0.0 < v["ram"] <= 100.0
    assert v["gpu"] == 42.0 and v["vram"] == 25.0 and v["ai_ms"] == 1234.0
    s.close()
    assert s._nvml.closed
    none = SysStats(nvml=_FakeNvml(None)).sample(None)
    assert none["gpu"] is None and none["vram"] is None and none["ai_ms"] == 0.0


def test_gemini_records_latency(config):
    from google.genai import types

    from nexa.ai.gemini_provider import GeminiProvider
    from nexa.core.safety import SafetyManager

    resp = types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=[types.Part(text="Dạ.")]))])

    class Models:
        def generate_content(self, model, contents, config):
            time.sleep(0.03)
            return resp

    config.store_api_key("AIzaSyTEST_" + "k" * 28, persist=False)
    p = GeminiProvider(config, client_factory=lambda k, t: _NS(models=Models()))
    assert p.last_latency_ms == 0.0
    p.converse("xin chào", [], lambda fc: None, SafetyManager().new_token())
    assert 25.0 <= p.last_latency_ms < 5000.0


def test_defaults(config):
    assert config.get("ui.stats_ring") is True
    assert config.get("ui.show_fps") is False


# ------------------------------------------------------------------ dòng thời gian hội thoại
@pytest.fixture(scope="module")
def app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _bridge(config, app, latency=0.0):
    from nexa.ui.bridge import UiBridge
    ctrl = _NS(config=config, gestures=_NS(running=False), provider=_NS(last_latency_ms=latency))
    return UiBridge(ctrl)


def _task(status, step="s1", msg=""):
    return {"task_id": "t1", "step_id": step, "tool": "open_app", "title": "Mở ứng dụng", "status": status,
            "message": msg, "source": "voice"}


def test_timeline_merges_messages_and_updates_task_card_in_place(config, app):
    ui = _bridge(config, app)
    ui._handle("user_message", {"text": "mở Notepad", "source": "voice"})
    ui._handle("task", _task("running", msg="Đang mở"))
    ui._handle("task", _task("done", msg="Đã mở Notepad"))
    ui._handle("task", _task("running", step="s2"))
    ui._handle("assistant_message", {"text": "Dạ, xong rồi ạ."})
    tl = ui.timeline
    assert [x["kind"] for x in tl] == ["msg", "task", "task", "msg"]
    assert tl[1]["status"] == "done" and tl[1]["text"] == "Đã mở Notepad"       # cập nhật đúng thẻ, không thêm thẻ mới
    assert tl[2]["status"] == "running" and tl[2]["key"] == "t1/s2/open_app"
    assert tl[0]["role"] == "user" and tl[3]["role"] == "assistant"
    assert len(ui.tasks) == 3 and len(ui.messages) == 2                          # danh sách cũ vẫn giữ cho HUD / tương thích
    ui._handle("clear_chat", {})
    assert ui.timeline == [] and ui.messages == []


def test_stats_sampling_follows_toggle(config, app):
    ui = _bridge(config, app, latency=850.0)
    ui._stats = __import__("nexa.ui.sysstats", fromlist=["SysStats"]).SysStats(nvml=_FakeNvml((3.0, 24.0)))
    ui._sample_stats()
    assert ui.sysStats["ai_ms"] == 850.0 and ui.sysStats["gpu"] == 3.0
    config.set("ui.stats_ring", False)
    ui._sample_stats()
    assert dict(ui.sysStats) == {}


# ------------------------------------------------------------------ QML
def test_theme_state_colors_distinct(app):
    from PySide6.QtQml import QJSEngine
    from PySide6.QtGui import QColor

    js = (QML_DIR / "Theme.js").read_text(encoding="utf-8")
    assert ".pragma library" in js
    engine = QJSEngine()
    result = engine.evaluate(js.replace(".pragma library", ""))
    assert not result.isError(), result.toString()
    colors = [engine.evaluate(f'stateColor("{st}")').toString() for st in
              ("STANDBY", "LISTENING", "THINKING", "SPEAKING", "CONFIRMING", "ERROR")]
    assert all(QColor(c).isValid() for c in colors)
    assert len(set(colors)) == len(colors)
    assert engine.evaluate('stateColor("UNKNOWN") === accent').toBool()
    assert engine.evaluate('loadColor(0.9) === danger && loadColor(0.7) === amber').toBool()


def _load(app, name):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    engine = QQmlEngine()
    warns: list[str] = []
    engine.warnings.connect(lambda ws: warns.extend(w.toString() for w in ws))
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / name)))
    obj = comp.create()
    app.processEvents()
    return (engine, comp, obj), [e.toString() for e in comp.errors()] + warns


def test_stats_ring_qml_loads(app):
    keep, problems = _load(app, "StatsRing.qml")
    ring = keep[2]
    assert ring is not None and not problems, problems
    ring.setProperty("width", 500)
    ring.setProperty("height", 500)
    ring.setProperty("stats", {"cpu": 50.0, "ram": 90.0, "gpu": None, "vram": None, "ai_ms": 1500.0})
    app.processEvents()
    assert ring.property("hasData")
    assert abs(ring.property("radius") - 500 * 0.445) < 1e-6


def test_generation_progress_reports_real_job_and_freezes_elapsed(app):
    keep, problems = _load(app, "GenerationProgress.qml")
    card = keep[2]
    assert card is not None and not problems, problems
    assert card.property("statusText") == "Chưa có tác vụ"
    card.setProperty("job", {"state": "running", "progress": 0.42, "started": 100})
    card.setProperty("now", 165)
    assert card.property("percent") == 42 and card.property("seconds") == 65
    assert card.property("running")
    card.setProperty("job", {"state": "done", "progress": 1, "started": 100, "finished": 180})
    card.setProperty("now", 900)
    assert card.property("percent") == 100 and card.property("seconds") == 80
    assert card.property("statusText") == "ĐÃ XONG" and not card.property("running")
    card.setProperty("job", {"state": "failed", "progress": 1, "error_code": "quality_gate", "project_id": "draft"})
    assert card.property("percent") == 99
    assert card.property("statusText") == "CẦN HOÀN THIỆN"


def test_main_qml_layout(config, app):
    """Main.qml nạp với UiBridge thật: không cảnh báo, có dock / nút dừng / vòng thông số, không còn khung Tác vụ."""
    from PySide6.QtCore import Property, QObject, QPointF, Signal, Slot
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem

    def fake(vals, slots=()):
        sig = Signal()
        attrs = {"changed": sig, "toast": Signal(str, bool), "panelChanged": Signal()}
        for k, (t, v) in vals.items():
            attrs[k] = Property(t, (lambda v: lambda self: v)(v), notify=sig)
        for s in slots:
            attrs[s] = Slot()(lambda self: None)
        return type("Fake", (QObject,), attrs)()

    ui = _bridge(config, app, latency=1200.0)
    ui._stats = __import__("nexa.ui.sysstats", fromlist=["SysStats"]).SysStats(nvml=_FakeNvml((3.0, 24.0)))
    ui._sample_stats()
    ui._handle("task", _task("running"))
    f3 = fake({"viewerOpen": (bool, False), "workspace": (bool, False), "activeJob": ("QVariantMap", {}),
               "providerStatus": ("QVariantMap", {})})
    fe = fake({"open": (bool, False), "catalog": ("QVariantList", []), "state": ("QVariantMap", {})}, ("selectLesson", "setParameter", "runSimulation", "close"))
    fc = fake({"panelOpen": (bool, False), "busy": (bool, False), "job": ("QVariantMap", {})}, ("openPanel", "closePanel"))
    eng = QQmlApplicationEngine()
    warns: list[str] = []
    eng.warnings.connect(lambda ws: warns.extend(w.toString() for w in ws))
    ctx = eng.rootContext()
    ctx.setContextProperty("nexa", ui)
    ctx.setContextProperty("nexa3d", f3)
    ctx.setContextProperty("nexaEdu", fe)
    ctx.setContextProperty("nexaCode", fc)
    eng.load(str(QML_DIR / "Main.qml"))
    try:
        win = eng.rootObjects()[0]
        end = time.monotonic() + 0.6
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        for name in ("dock", "stopButton", "statsRing", "statePill", "chat", "statusIcons"):
            assert win.findChild(QQuickItem, name) is not None, name
        dock = win.findChild(QQuickItem, "dock")
        assert dock.height() < 90                                   # một hàng, không xuống dòng
        assert win.findChild(QQuickItem, "statsRing").isVisible()
        assert win.findChild(QQuickItem, "chat").property("count") == 1
        # Lịch sử hội thoại luôn nổi dưới quả cầu; cột phải dành cho API/thư viện.
        assert win.findChild(QQuickItem, "subtitles") is not None
        drawer = win.findChild(QQuickItem, "historyDrawer")
        assert not win.property("logDocked") and drawer.isVisible()
        slot = win.findChild(QQuickItem, "floatingHistorySlot")
        assert drawer.parentItem() == slot and drawer.width() <= slot.width()
        assert win.findChild(QQuickItem, "runtimeRail").isVisible()
        assert win.findChild(QQuickItem, "nxsMediaIdentity").isVisible()

        def pump():
            end = time.monotonic() + 0.6
            while time.monotonic() < end:
                app.processEvents()
                time.sleep(0.02)
        # Màn hẹp vẫn hiện hội thoại dưới quả cầu; SYS thu thành dải ở đỉnh.
        win.setProperty("width", 900)
        pump()
        assert not win.property("logDocked") and not win.property("historyOpen") and drawer.isVisible()
        assert not win.findChild(QQuickItem, "statsRing").isVisible()
        assert win.findChild(QQuickItem, "statsStrip").isVisible()
        assert win.findChild(QQuickItem, "dock").height() < 90
        win.setProperty("historyOpen", True)
        pump()
        assert drawer.isVisible() and drawer.width() <= slot.width()

        # The command field and emergency stop must remain on screen at the minimum size.
        win.setProperty("historyOpen", False)
        win.setProperty("width", 600)
        win.setProperty("height", 640)
        pump()
        for name in ("commandInput", "dock", "stopButton", "historyDrawer", "identityHeader"):
            item = win.findChild(QQuickItem, name)
            origin = item.mapToScene(QPointF(0, 0))
            assert item.isVisible() and item.width() > 0 and item.height() > 0
            assert origin.x() >= 0 and origin.y() >= 0, name
            assert origin.x() + item.width() <= win.width() + 1, name
            assert origin.y() + item.height() <= win.height() + 1, name
        ui.commandNavigation.emit("open", "history")
        pump()
        assert win.property("historyOpen") and win.property("historyMode") == 2
        ui.commandNavigation.emit("close", "history")
        pump()
        assert not win.property("historyOpen") and win.property("historyMode") == 1
        assert not warns, warns
    finally:
        for o in eng.rootObjects():
            o.deleteLater()
        app.processEvents()
    main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert "nexa.timeline" in main and "nexa.tasks" not in main and "Ctrl+Alt+Esc" in main
    # chip việc 3D/Code nằm trong RowLayout: phải có implicitWidth, nếu không bị xếp chồng lên icon trạng thái
    assert "implicitWidth: chipRow.implicitWidth" in main
    # bong bóng tin ngắn phải đủ rộng cho dòng "Anh Sơn (giọng nói) · giờ"
    assert "Math.max(msg.implicitWidth, meta.implicitWidth)" in main
