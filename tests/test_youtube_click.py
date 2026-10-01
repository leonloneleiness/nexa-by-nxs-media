"""Kiểm thử v1.3: mở video YouTube theo từ khóa, chặn nhấp tọa độ đoán mò, ngữ cảnh lệnh cơ bản cho Gemini."""
from __future__ import annotations

import json
import time

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import Services, build_registry
from nexa.core.events import Source, ToolCall
from nexa.core.executor import Executor
from nexa.core.safety import SafetyManager
from nexa.desktop.apps_and_files import AppLauncher

R = IntentRouter(app_exists=lambda n: n.lower() in ("notepad", "trình duyệt"))


@pytest.mark.parametrize("text,call", [
    ("Nhất mở video đầu tiên trong chương trình nghị", ("play_youtube", {"query": "", "index": 1})),
    ("mở video thứ hai", ("play_youtube", {"query": "", "index": 2})),
    ("phát nhạc tích tắc", ("play_youtube", {"query": "nhạc Tíc Tắc", "index": 1})),
    ("bật bài hát Nơi này có anh trên YouTube", ("play_youtube", {"query": "bài hát Nơi này có anh", "index": 1})),
    ("mở video hướng dẫn nấu phở", ("play_youtube", {"query": "hướng dẫn nấu phở", "index": 1})),
])
def test_youtube_voice_commands(text, call):
    r = R.route(text)
    assert r.kind == "basic" and r.calls == [call]


def test_search_then_first_video_is_two_steps():
    r = R.route("tìm nhạc tích tốc rồi mở video đầu tiên")
    assert r.calls == [("web_search", {"query": "nhạc Tíc Tắc"}), ("play_youtube", {"query": "", "index": 1})]


def _fake_html(videos):
    data = {"contents": {"items": [{"videoRenderer": {"videoId": vid, "title": {"runs": [{"text": title}]}}}
                                   for vid, title in videos]}}
    return ("<html><script>var ytInitialData = " + json.dumps(data) + ";</script></html>").encode()


class _Resp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body


class _WM:
    def __init__(self, titles):
        self.titles = titles

    def list_windows(self, limit=100):
        return [{"hwnd": i + 1, "title": t, "process": "msedge.exe"} for i, t in enumerate(self.titles)]


def test_play_youtube_opens_nth_video_and_verifies_window(config, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=8: _Resp(_fake_html(
        [("aaa11111111", "Tíc Tắc - B-Ray"), ("bbb22222222", "Tíc Tắc Remix")])))
    opened = []
    app = AppLauncher(config, _WM(["Tíc Tắc Remix - YouTube - Microsoft Edge"]))
    monkeypatch.setattr(app, "open_url", lambda url: (opened.append(url), type("R", (), {"ok": True})())[1])
    r = app.play_youtube("nhạc tích tắc", index=2)
    assert opened == ["https://www.youtube.com/watch?v=bbb22222222"]
    assert r.ok and r.verified and "Tíc Tắc Remix" in r.message


def test_play_youtube_unverified_is_reported_honestly(config, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=8: _Resp(_fake_html([("aaa11111111", "Bài A")])))
    app = AppLauncher(config, _WM(["Cửa sổ khác"]))
    monkeypatch.setattr(app, "open_url", lambda url: type("R", (), {"ok": True})())
    monkeypatch.setattr(time, "monotonic", iter([0.0] + [100.0] * 50).__next__)
    r = app.play_youtube("bài a")
    assert r.ok and not r.verified and "chưa thấy" in r.message


def test_empty_query_uses_last_search(config):
    got = []

    class Apps:
        def play_youtube(self, q, i):
            got.append((q, i))
            from nexa.core.events import ToolResult
            return ToolResult.success("ok")

        def web_search(self, q):
            from nexa.core.events import ToolResult
            return ToolResult.success("ok")

    safety = SafetyManager()
    ex = Executor(build_registry(config), safety, Services(config=config, apps=Apps()), com_init=False)
    ex.start()
    try:
        assert not ex.execute(ToolCall("play_youtube", {}, Source.VOICE), safety.new_token()).ok  # chưa tìm gì
        ex.execute(ToolCall("web_search", {"query": "nhạc Tíc Tắc"}, Source.VOICE), safety.new_token())
        assert ex.execute(ToolCall("play_youtube", {}, Source.VOICE), safety.new_token()).ok
        assert got == [("nhạc Tíc Tắc", 1)]
    finally:
        ex.stop()


def test_ai_blind_coordinate_click_is_blocked_but_voice_is_allowed(config):
    clicks = []

    class Inp:
        def click(self, button, x, y, double=False):
            clicks.append((x, y))
            from nexa.core.events import ToolResult
            return ToolResult.success("ok", x=x, y=y)

    config.set("safety.autonomy", "full")
    safety = SafetyManager()
    services = Services(config=config, input=Inp())
    ex = Executor(build_registry(config), safety, services, com_init=False, autonomy=lambda: "full")
    ex.start()
    try:
        r = ex.execute(ToolCall("mouse_click", {"x": 250, "y": 280}, Source.AI), safety.new_token())
        assert not r.ok and r.error_code == "unverified_coordinates" and clicks == []
        services.memory["ui_rects"] = [((200, 250, 400, 300), time.monotonic())]   # vừa đọc bằng list_ui_controls
        assert ex.execute(ToolCall("mouse_click", {"x": 250, "y": 280}, Source.AI, call_id="c2"), safety.new_token()).ok
        assert ex.execute(ToolCall("mouse_click", {"x": 900, "y": 900}, Source.VOICE), safety.new_token()).ok
        assert clicks == [(250, 280), (900, 900)]
    finally:
        ex.stop()


def test_gemini_notes_carry_basic_command_context(config):
    from nexa.ai.gemini_provider import GeminiProvider
    p = GeminiProvider(config, client_factory=lambda k, t: None)
    for i in range(7):
        p.add_note(f"ghi chú {i}")
    assert p._notes == [f"ghi chú {i}" for i in range(2, 7)]
