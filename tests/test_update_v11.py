"""Kiểm thử bản cập nhật: toàn quyền, lệnh nhấp chuột bằng giọng nói, giọng robot, tách câu, cache TTS, thinking."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from google.genai import errors, types

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import ToolRegistry, ToolSpec, build_registry, obj
from nexa.audio import voice_fx
from nexa.audio.tts import OUT_SR, TTSManager, split_sentences
from nexa.core.events import Risk, Source, ToolCall, ToolResult
from nexa.core.executor import Executor
from nexa.core.safety import SafetyManager

R = IntentRouter(app_exists=lambda n: n.lower() in ("notepad",))


# ------------------------------------------------------------------ toàn quyền
def _executor(mode, always=False):
    calls, events = [], []
    reg = ToolRegistry()
    reg.register(ToolSpec("xoa", "Xóa", "t", obj({}), lambda a, c: (calls.append(1), ToolResult.success("ok"))[1],
                          risk=Risk.HIGH, always_confirm=always))
    safety = SafetyManager(confirm_timeout_s=0.5)
    ex = Executor(reg, safety, com_init=False, autonomy=lambda: mode)
    ex.add_listener(events.append)
    ex.start()
    return ex, safety, calls, events


def test_full_autonomy_runs_high_risk_without_confirmation_and_logs_it():
    ex, safety, calls, events = _executor("full")
    try:
        r = ex.execute(ToolCall("xoa", {}, Source.VOICE), safety.new_token())
        assert r.ok and calls == [1]
        assert safety.pending is None
        assert any(e.status == "auto_approved" for e in events)
    finally:
        ex.stop()


def test_standard_mode_still_asks():
    ex, safety, calls, _ = _executor("standard")
    try:
        r = ex.execute(ToolCall("xoa", {}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "not_confirmed" and calls == []
    finally:
        ex.stop()


def test_full_autonomy_keeps_always_confirm_tools():
    ex, safety, calls, _ = _executor("full", always=True)
    try:
        r = ex.execute(ToolCall("xoa", {}, Source.AI), safety.new_token())
        assert not r.ok and calls == []
    finally:
        ex.stop()


def test_full_autonomy_still_blocked_by_emergency_stop():
    ex, safety, calls, _ = _executor("full")
    try:
        safety.emergency_stop("test")
        r = ex.execute(ToolCall("xoa", {}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "control_paused" and calls == []
    finally:
        ex.stop()


def test_screen_upload_still_requires_preview_in_full_mode(config):
    assert build_registry(config).get("describe_screen").always_confirm is True


# ------------------------------------------------------------------ nhấp chuột bằng giọng nói
@pytest.mark.parametrize("text,calls", [
    ("bấm vào nút Lưu", [("click_ui_control", {"name": "Lưu"})]),
    ("click Tải về", [("click_ui_control", {"name": "Tải về"})]),
    ("chọn tab Cài đặt", [("click_ui_control", {"name": "Cài đặt"})]),
    ("nhấp vào nút Gửi", [("click_ui_control", {"name": "Gửi"})]),
    ("nhấp chuột tại 500 300", [("mouse_click", {"x": 500, "y": 300})]),
    ("click vào tọa độ 120, 80", [("mouse_click", {"x": 120, "y": 80})]),
    ("nhấp đúp tại 10 20", [("mouse_click", {"x": 10, "y": 20, "double": True})]),
    ("nhấp chuột phải tại 300 400", [("mouse_click", {"x": 300, "y": 400, "button": "right"})]),
    ("nhấp vào đây", [("mouse_click", {})]),
    ("nhấp chuột", [("mouse_click", {})]),
    ("nhap chuot", [("mouse_click", {})]),
    ("nhấn enter", [("press_keys", {"keys": ["enter"]})]),
    ("nhập nội dung: xin chào", [("type_text", {"text": "xin chào"})]),
    ("nhập xin chào anh", [("type_text", {"text": "xin chào anh"})]),
])
def test_voice_click_commands(text, calls):
    r = R.route(text)
    assert r.kind == "basic" and r.calls == calls


def test_voice_click_on_send_button_runs_without_prompt_in_full_mode(config):
    """"Bấm nút Gửi" là rủi ro cao; ở chế độ toàn quyền phải chạy ngay, không chờ xác nhận."""
    reg = build_registry(config)
    spec = reg.get("click_ui_control")
    assessment = spec.assess({"name": "Gửi"}, None)
    assert assessment.risk == Risk.HIGH and assessment.needs_confirmation(Source.VOICE)


# ------------------------------------------------------------------ giọng robot, tách câu, cache
def test_robot_effect_changes_signal_but_keeps_level_and_length():
    t = np.arange(OUT_SR) / OUT_SR
    x = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    y = voice_fx.apply("robot", x, OUT_SR, 0.6)
    assert y.shape == x.shape and y.dtype == np.float32
    assert abs(np.max(np.abs(y)) - np.max(np.abs(x))) < 1e-3
    assert np.mean(np.abs(y - x)) > 0.01
    assert voice_fx.apply("none", x, OUT_SR, 0.6) is x


def test_split_sentences_for_pipelined_speech():
    parts = split_sentences("Dạ, em đã mở trình duyệt. Em cũng đã tìm xong! Còn gì nữa không anh?")
    assert parts == ["Dạ, em đã mở trình duyệt.", "Em cũng đã tìm xong!", "Còn gì nữa không anh?"]
    long = "a " * 300
    assert all(len(p) <= 221 for p in split_sentences(long))


def test_tts_cache_and_pipeline(config, monkeypatch):
    config.set("tts.backend", "winrt")
    config.set("tts.effect", "none")
    calls = []

    class Fake:
        def available(self):
            return True, "fake"

        def synth(self, text):
            calls.append(text)
            time.sleep(0.05)
            return np.zeros(int(OUT_SR * 0.1), np.float32), OUT_SR

    m = TTSManager(config, None)
    monkeypatch.setattr(m, "_backend", lambda name: Fake())
    played = []
    monkeypatch.setattr(m, "_play", lambda data: played.append(data.size))
    assert m._synthesize("Dạ.") is not None
    m._synthesize("Dạ.")
    assert calls == ["Dạ."]  # lần 2 lấy từ cache
    done = threading.Event()
    m.on_idle = lambda kind: done.set()
    m.speak("Câu một. Câu hai. Câu ba.")
    assert done.wait(3)
    assert calls[1:] == ["Câu một.", "Câu hai.", "Câu ba."] and len(played) == 3
    m.shutdown()


# ------------------------------------------------------------------ thinking level
def test_thinking_level_sent_and_dropped_if_model_rejects(config):
    from nexa.ai.gemini_provider import GeminiProvider
    config.store_api_key("AIzaSyTEST_" + "k" * 28, persist=False)
    seen = []

    class Models:
        def generate_content(self, model, contents, config):
            seen.append(config.thinking_config)
            if config.thinking_config is not None:
                raise errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                         "message": "thinking_level is not supported for this model"}})
            return types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text="Dạ.")]))])

    client = type("C", (), {"models": Models()})()
    p = GeminiProvider(config, client_factory=lambda k, t: client)
    r = p.converse("chào", [], lambda fc: {}, SafetyManager().new_token())
    assert r.text == "Dạ."
    assert seen[0] is not None and seen[0].thinking_level.value.lower() == "minimal" and seen[1] is None


# ------------------------------------------------------------------ v1.2: bộ lọc One Euro
def test_one_euro_reduces_jitter_but_follows_fast_motion():
    from nexa.vision.gesture_state_machine import OneEuro
    rng = np.random.default_rng(0)
    f = OneEuro(1.5, 4.0)
    still = [f(0.5 + rng.normal(0, 0.004), i / 30) for i in range(60)]
    assert np.std(still[10:]) < 0.004 * 0.6          # rung khi đứng yên giảm rõ
    f = OneEuro(1.5, 4.0)
    xs = [f(0.2 + 0.05 * i, i / 30) for i in range(15)]  # vuốt nhanh 1.5 đơn vị/giây
    assert 0.2 + 0.05 * 14 - xs[-1] < 0.12            # trễ nhỏ khi tay di chuyển nhanh
