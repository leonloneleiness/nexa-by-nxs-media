"""Tìm/hỏi NGAY TRONG trang được nêu tên thay vì Google ("tìm kiếm trong ChatGPT về Nguyễn Xuân Sơn")."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.site_search import BY_KEY, SITES, find_site, search_url
from nexa.ai.tool_registry import h_site_search
from nexa.core.events import ToolResult


@pytest.mark.parametrize("heard,site,query", [
    ("tìm kiếm trong chat gpt về nguyễn xuân sơn", "chatgpt", "nguyễn xuân sơn"),          # yêu cầu của anh Sơn
    ("Tìm kiếm trong ChatGPT về Nguyễn Xuân Sơn", "chatgpt", "Nguyễn Xuân Sơn"),
    ("mở ChatGPT rồi tìm nguyễn xuân sơn", "chatgpt", "nguyễn xuân sơn"),                   # trước đây: tìm Google
    ("hỏi ChatGPT về lịch sử Việt Nam", "chatgpt", "lịch sử Việt Nam"),
    ("hỏi Claude cách học tiếng Anh", "claude", "cách học tiếng Anh"),
    ("tìm nguyễn xuân sơn trên facebook", "facebook", "nguyễn xuân sơn"),
    ("tìm trên YouTube nhạc remix", "youtube", "nhạc remix"),
    ("tìm trên shopee tai nghe bluetooth", "shopee", "tai nghe bluetooth"),
    ("tra cứu trên wikipedia Hồ Chí Minh", "wikipedia", "Hồ Chí Minh"),
    ("tìm trên bản đồ quán cà phê gần đây", "maps", "quán cà phê gần đây"),
    ("Nexa ơi tìm trong TikTok về công thức nấu ăn giúp anh", "tiktok", "công thức nấu ăn"),
])
def test_search_inside_named_site(heard, site, query):
    assert IntentRouter().route(heard).calls == [("site_search", {"site": site, "query": query})]


@pytest.mark.parametrize("heard,calls", [
    ("tìm trên google thời tiết", [("web_search", {"query": "thời tiết"})]),
    ("tìm thời tiết trên google", [("web_search", {"query": "thời tiết"})]),
    ("tìm nhạc remix", [("web_search", {"query": "nhạc remix"})]),
    ("tìm file báo cáo", [("find_files", {"name": "báo cáo"})]),
    ("mở ChatGPT", [("open_url", {"url": "https://chatgpt.com"})]),
    ("đóng ChatGPT", [("close_named", {"name": "ChatGPT", "kind": "any"})]),
])
def test_other_commands_unchanged(heard, calls):
    assert IntentRouter().route(heard).calls == calls


def test_ask_only_for_assistants():
    assert IntentRouter().route("hỏi YouTube về nhạc").kind != "basic"


def test_urls_are_encoded_for_each_site():
    assert search_url(BY_KEY["chatgpt"], "Nguyễn Xuân Sơn") == \
        "https://chatgpt.com/?q=Nguy%E1%BB%85n%20Xu%C3%A2n%20S%C6%A1n"
    assert search_url(BY_KEY["youtube"], "nhạc remix").endswith("search_query=nh%E1%BA%A1c+remix")
    for s in SITES:
        url = search_url(s, "a b&c")
        assert url.startswith("https://") and "%26c" in url   # "&" trong câu tìm được mã hóa


def test_aliases_are_unique_and_resolve():
    seen = {}
    for s in SITES:
        for a in s.aliases:
            assert seen.setdefault(a, s.key) == s.key, a
    assert find_site("Chat GPT").key == "chatgpt" and find_site("chatgpt").key == "chatgpt"
    assert find_site("không có trang này") is None


def test_site_search_tool_opens_url_and_reports(monkeypatch):
    opened = []
    apps = SimpleNamespace(open_url=lambda url: opened.append(url) or ToolResult.success("Đã mở.", verified=True))
    ctx = SimpleNamespace(services=SimpleNamespace(apps=apps))
    r = h_site_search({"site": "youtube", "query": "nhạc remix"}, ctx)
    assert r.ok and opened[0].startswith("https://www.youtube.com/results?") and         r.message == "Đã tìm trên YouTube: nhạc remix."
    assert not h_site_search({"site": "xyz", "query": "a"}, ctx).ok
    assert not h_site_search({"site": "chatgpt", "query": " "}, ctx).ok


# ------------------------------------------------------------------ bảo đảm câu hỏi thật sự được gửi
class _Browser:
    """Giả lập Edge: trang ChatGPT có thể tự gửi (auto) hoặc bỏ mất câu hỏi (lỗi ảnh 23:19)."""

    def __init__(self, auto_send: bool, editor: bool = True, prefilled: str = ""):
        self.auto_send, self.editor, self.prefilled = auto_send, editor, prefilled
        self.address, self.title, self.typed, self.keys = "https://chatgpt.com/?q=x", "ChatGPT", [], []
        self.t0 = None

    def tick(self):
        import time
        self.t0 = self.t0 or time.monotonic()
        if self.auto_send and time.monotonic() - self.t0 > 0.3:
            self.address = "https://chatgpt.com/c/abc"


def _ask_ctx(monkeypatch, browser):
    from nexa.desktop import uia
    monkeypatch.setattr(uia, "page_title", lambda h: (browser.tick(), browser.title)[1])
    monkeypatch.setattr(uia, "address_bar", lambda h: browser.address)
    monkeypatch.setattr(uia, "focused_page_editor",
                        lambda h, name: (object(), browser.prefilled) if browser.editor else None)

    def type_text(text, hwnd, cancelled=None):
        browser.typed.append(text)
        return ToolResult.success("gõ", verified=True)

    def hotkey(keys, hwnd=None):
        browser.keys.append(keys)
        if keys == ["enter"]:
            browser.address = "https://chatgpt.com/c/new"
        return ToolResult.success("phím", verified=True)
    wm = SimpleNamespace(list_windows=lambda limit=60: [{"hwnd": 7, "title": "ChatGPT - Microsoft Edge",
                                                          "process": "msedge.exe"}])
    apps = SimpleNamespace(open_url=lambda url: ToolResult.success("Đã mở.", verified=True))
    return SimpleNamespace(services=SimpleNamespace(apps=apps, wm=wm,
                                                    input=SimpleNamespace(type_text=type_text, hotkey=hotkey)),
                           token=SimpleNamespace(cancelled=False))


def test_question_auto_sent_by_page_needs_no_typing(monkeypatch):
    b = _Browser(auto_send=True)
    r = h_site_search({"site": "chatgpt", "query": "Nguyễn Xuân Sơn"}, _ask_ctx(monkeypatch, b))
    assert r.ok and r.verified and r.data["sent"] == "auto" and b.typed == [] and b.keys == []


def test_dropped_question_is_typed_into_chat_box_and_sent(monkeypatch):
    import nexa.ai.tool_registry as tr
    real = tr._ensure_question_sent
    monkeypatch.setattr(tr, "_ensure_question_sent", lambda c, s, q: real(c, s, q, timeout=6.0))
    b = _Browser(auto_send=False)
    r = tr.h_site_search({"site": "chatgpt", "query": "Nguyễn Xuân Sơn"}, _ask_ctx(monkeypatch, b))
    assert r.ok and r.verified and r.data["sent"] == "typed"
    assert b.typed == ["Nguyễn Xuân Sơn"] and b.keys == [["enter"]]


def test_prefilled_but_unsent_question_only_presses_enter(monkeypatch):
    b = _Browser(auto_send=False, prefilled="Nguyễn Xuân Sơn")
    r = h_site_search({"site": "chatgpt", "query": "Nguyễn Xuân Sơn"}, _ask_ctx(monkeypatch, b))
    assert r.data["sent"] == "enter" and b.typed == [] and b.keys == [["enter"]]


def test_never_types_when_cursor_not_in_chat_box(monkeypatch):
    import nexa.ai.tool_registry as tr
    real = tr._ensure_question_sent
    monkeypatch.setattr(tr, "_ensure_question_sent", lambda c, s, q: real(c, s, q, timeout=4.5))
    b = _Browser(auto_send=False, editor=False)
    r = tr.h_site_search({"site": "chatgpt", "query": "Nguyễn Xuân Sơn"}, _ask_ctx(monkeypatch, b))
    assert r.ok and not r.verified and r.data["sent"] == "unknown" and "bấm gửi" in r.message
    assert b.typed == [] and b.keys == []


def test_chatgpt_url_has_no_hints_param():
    assert "hints=" not in search_url(BY_KEY["chatgpt"], "x")
