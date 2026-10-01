"""Đóng ứng dụng/tab theo tên (lỗi 23:04: "Đóng ChatGPT" bị gửi sang Gemini rồi thất bại)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import h_close_named
from nexa.core.events import ToolResult
from nexa.desktop import uia


class FakeWM:
    def __init__(self, windows):
        self.windows = windows
        self.closed = []

    def list_windows(self, limit=100):
        return [w for w in self.windows if w["hwnd"] not in self.closed]

    def close(self, hwnd):
        self.closed.append(hwnd)
        return ToolResult.success("Đã đóng.", verified=True)


EDGE = {"hwnd": 1, "title": "ChatGPT - Cá nhân - Microsoft Edge", "process": "msedge.exe"}
CODE = {"hwnd": 2, "title": "main.py - NEXA - Visual Studio Code", "process": "Code.exe"}
ZALO = {"hwnd": 3, "title": "Zalo", "process": "Zalo.exe"}


def _ctx(monkeypatch, windows, tabs):
    """tabs: {hwnd: [tiêu đề tab]}; close_tab giả xóa tab khỏi danh sách."""
    state = {h: list(v) for h, v in tabs.items()}
    monkeypatch.setattr(uia, "browser_tabs", lambda hwnd: [SimpleNamespace(title=t) for t in state.get(hwnd, [])])
    monkeypatch.setattr(uia, "tab_title", lambda el: el.title)

    def fake_close(hwnd, tab, hotkey=None, sleep=None):
        state[hwnd].remove(tab.title)
        return True
    monkeypatch.setattr(uia, "close_tab", fake_close)
    wm = FakeWM(windows)
    ctx = SimpleNamespace(services=SimpleNamespace(wm=wm, input=SimpleNamespace(hotkey=lambda k, h: None)),
                          token=SimpleNamespace(cancelled=False))
    return ctx, wm, state


def test_close_chatgpt_closes_only_that_tab_not_the_browser(monkeypatch):
    ctx, wm, state = _ctx(monkeypatch, [EDGE, CODE],
                          {1: ["API keys | Google AI Studio", "(1) YouTube", "ChatGPT"]})
    r = h_close_named({"name": "ChatGPT"}, ctx)
    assert r.ok and r.verified and "ChatGPT" in r.message
    assert state[1] == ["API keys | Google AI Studio", "(1) YouTube"] and wm.closed == []


def test_close_app_window_by_known_name(monkeypatch):
    ctx, wm, _ = _ctx(monkeypatch, [EDGE, CODE, ZALO], {1: ["ChatGPT"]})
    assert h_close_named({"name": "VS Code"}, ctx).ok and wm.closed == [2]       # "VS Code" → Visual Studio Code
    assert h_close_named({"name": "Zalo"}, ctx).ok and wm.closed == [2, 3]


def test_browser_window_not_closed_just_because_active_tab_matches(monkeypatch):
    ctx, wm, _ = _ctx(monkeypatch, [EDGE], {1: []})
    r = h_close_named({"name": "ChatGPT", "kind": "app"}, ctx)
    assert not r.ok and wm.closed == []


def test_nothing_matching_reports_clearly(monkeypatch):
    ctx, wm, _ = _ctx(monkeypatch, [EDGE, CODE], {1: ["ChatGPT"]})
    r = h_close_named({"name": "Photoshop"}, ctx)
    assert not r.ok and r.error_code == "not_found" and wm.closed == []


def test_tab_only_request_does_not_close_apps(monkeypatch):
    ctx, wm, _ = _ctx(monkeypatch, [EDGE, ZALO], {1: ["ChatGPT"]})
    r = h_close_named({"name": "Zalo", "kind": "tab"}, ctx)
    assert not r.ok and wm.closed == []


@pytest.mark.parametrize("heard,calls", [
    ("Đóng ChatGPT", [("close_named", {"name": "ChatGPT", "kind": "any"})]),            # câu thật 23:04
    ("đóng tab YouTube", [("close_named", {"name": "YouTube", "kind": "tab"})]),
    ("tắt ứng dụng Zalo", [("close_named", {"name": "Zalo", "kind": "app"})]),
    ("thoát VS Code", [("close_named", {"name": "VS Code", "kind": "any"})]),
    ("đóng tab", [("press_keys", {"keys": ["ctrl", "w"]})]),
    ("đóng tab này", [("press_keys", {"keys": ["ctrl", "w"]})]),
    ("đóng cửa sổ", [("close_window", {})]),
    ("tắt tiếng", [("mute", {"on": True})]),
])
def test_close_routing(heard, calls):
    assert IntentRouter().route(heard).calls == calls


@pytest.mark.parametrize("heard", ["tắt máy", "tắt wifi", "tắt nhạc", "tắt camera"])
def test_turn_off_things_are_not_closed_as_apps(heard):
    assert all(name != "close_named" for name, _ in IntentRouter().route(heard).calls)


def test_tab_title_strips_edge_memory_suffix():
    el = SimpleNamespace(element_info=SimpleNamespace(name="ChatGPT - Mức sử dụng bộ nhớ - 281 MB"))
    assert uia.tab_title(el) == "ChatGPT"
