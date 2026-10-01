"""Conversation routing and listening lifecycle without microphone or network."""
import threading
import time
from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.audio.pipeline import AudioPipeline
from nexa.core.controller import Controller


@pytest.mark.parametrize("text", ["Nexa, tôi muốn tâm sự với em", "bật chế độ tâm sự", "trò chuyện liên tục"])
def test_enter_conversation(text):
    assert IntentRouter().route(text).action == "companion_on"


@pytest.mark.parametrize("text", ["ừ", "không", "thôi", "mở lòng rất khó", "mở Notepad",
                                  "hôm qua anh bảo bạn nghỉ đi vì quá mệt"])
def test_story_never_becomes_desktop_command(text):
    route = IntentRouter().route(text, companion=True)
    assert route.kind == "ai"
    assert not route.calls


def test_exit_and_controls_still_work():
    router = IntentRouter()
    assert router.route("thoát chế độ tâm sự", companion=True).action == "companion_off"
    assert router.route("Nexa nghỉ đi", companion=True).kind == "sleep"
    assert router.route("dừng lại", companion=True).kind == "stop"
    assert router.route("xóa hội thoại", companion=True).action == "clear_history"
    assert router.route("đồng ý", pending_confirmation=True, companion=True).kind == "confirm"
    assert router.route("mở Notepad").kind == "basic"


def test_conversation_audio_profile_restores_original(config):
    audio = AudioPipeline(config)
    original = audio.segmenter.cfg
    audio.set_conversation_mode(True)
    assert audio.segmenter.cfg.end_silence_ms >= 1400
    assert audio.segmenter.cfg.max_utterance_s >= 60
    audio.set_conversation_mode(False)
    assert audio.segmenter.cfg == original


def test_conversation_waits_through_silence_and_music_then_sleeps():
    calls = []
    fake = SimpleNamespace(
        _companion=True, _awake=True, _media_playing=True,
        _last_activity=time.monotonic() - 90,
        _ai_busy=threading.Event(), _basic_busy=threading.Event(),
        safety=SimpleNamespace(pending=None),
        config=SimpleNamespace(get=lambda key: 300),
        audio=SimpleNamespace(listen=lambda: calls.append("listen")),
        go_standby=lambda reason: calls.append("sleep"))
    Controller._on_listen_timeout(fake)
    assert calls == ["listen"]
    fake._last_activity = time.monotonic() - 301
    Controller._on_listen_timeout(fake)
    assert calls == ["listen", "sleep"]


def test_reply_rearms_listening_and_resets_silence_clock():
    calls = []
    fake = SimpleNamespace(_then_standby=False, _awake=True, _last_activity=0,
                           _listen=lambda: calls.append("listen"))
    Controller._after_reply(fake)
    assert calls == ["listen"]
    assert time.monotonic() - fake._last_activity < 1
