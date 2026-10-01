"""Tên ứng dụng nói bằng giọng: các cách Whisper nghe nhầm phải về đúng ứng dụng, và không mở nhầm ứng dụng khác."""
from __future__ import annotations

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.desktop.app_aliases import KNOWN_APPS, fuzzy_pick, known_app_for, norm
from nexa.desktop.apps_and_files import AppEntry, AppLauncher
from nexa.utils.text import fold

START_MENU = ["Visual Studio Code", "Zalo", "Word", "Excel", "PowerPoint", "Discord", "Canva", "Google Chrome",
              "Docker Desktop", "Steam", "Git Bash", "Git CMD", "Git GUI", "Python 3.11 (64-bit)", "IDLE (Python 3.11)",
              "Virtual Pet", "NVIDIA App"]


class _Cfg:
    def get(self, key, default=None):
        return {"apps.custom": [], "apps.browser_path": ""}.get(key, default)


@pytest.fixture
def launcher(monkeypatch):
    lau = AppLauncher(_Cfg())
    lau._start_menu = [AppEntry(fold(n), n, [fold(n)], startfile=f"C:/fake/{n}.lnk", source="startmenu")
                       for n in START_MENU]
    monkeypatch.setattr(lau, "browser_exe", lambda: "C:/Browser/browser.exe")
    return lau


# Câu Whisper ghi ra thật trong log của anh Sơn + các biến thể hay gặp.
@pytest.mark.parametrize("heard,expect", [
    ("VS Code", "Visual Studio Code"), ("VS Của", "Visual Studio Code"), ("vscode", "Visual Studio Code"),
    ("video scop", "Visual Studio Code"), ("viết của", "Visual Studio Code"), ("Visual Code", "Visual Studio Code"),
    ("visual corp", "Visual Studio Code"), ("VSiko", "Visual Studio Code"),
    ("Visual Answer Studio Code", "Visual Studio Code"),
    ("chát dù bị tùy", "ChatGPT (web)"), ("chat GPT", "ChatGPT (web)"), ("clout", "Claude (web)"),
    ("zalô", "Zalo"), ("Zaloo", "Zalo"), ("đi con", "Discord"), ("power phone", "PowerPoint"),
    ("cơ rôn", "Google Chrome"), ("Docker", "Docker Desktop"), ("Canvas", "Canva"),
])
def test_misheard_names_resolve_to_right_app(launcher, heard, expect):
    app, _ = launcher.resolve(heard)
    assert app is not None and app.name == expect


def test_web_fallback_opens_in_browser(launcher):
    app, _ = launcher.resolve("ChatGPT")
    assert app.command == ["C:/Browser/browser.exe", "https://chatgpt.com"]


@pytest.mark.parametrize("heard", ["xyz abc", "con mèo", "đi chơi", "nhanh"])
def test_unrelated_words_do_not_open_random_app(launcher, heard):
    assert launcher.resolve(heard)[0] is None


def test_ambiguous_name_asks_instead_of_guessing(launcher):
    app, candidates = launcher.resolve("Git")
    assert app is None and {c.name for c in candidates} >= {"Git Bash", "Git CMD"}


def test_fuzzy_pick_requires_clear_winner():
    assert fuzzy_pick("zaloo", [(1, "zalo"), (2, "canva")]) == 1
    assert fuzzy_pick("git", [(1, "git cmd"), (2, "git gui")]) is None


def test_known_app_spoken_forms_are_folded_and_unique():
    seen = {}
    for app in KNOWN_APPS:
        for s in app.spoken:
            assert s == norm(s), s
            assert seen.setdefault(s, app.name) == app.name, f"'{s}' thuộc hai ứng dụng"


def test_short_names_never_fuzzy_match():
    assert known_app_for("vs") is None
    assert known_app_for("uot", fuzzy=False).name == "Word"


# ------------------------------------------------------------------ bộ phân tích lệnh
@pytest.mark.parametrize("heard,name", [
    ("Mở VS Của", "Visual Studio Code"), ("Mở video scop", "Visual Studio Code"),
    ("Mở viết của", "Visual Studio Code"), ("Nexa ơi mở VS Code giúp anh", "Visual Studio Code"),
    ("mở ứng dụng vi ét code nhé", "Visual Studio Code"), ("Mở clout", "Claude"), ("Mở PowerPorn", "PowerPoint"),
])
def test_router_rewrites_misheard_app(heard, name):
    route = IntentRouter().route(heard)
    assert route.calls == [("open_app", {"name": name})]


def test_router_keeps_youtube_video_commands():
    r = IntentRouter()
    assert r.route("Mở video Sơn Tùng").calls == [("play_youtube", {"query": "Sơn Tùng", "index": 1})]
    assert r.route("Mở video đầu tiên chên YouTube").calls == [("play_youtube", {"query": "", "index": 1})]


@pytest.mark.parametrize("heard,kind,calls", [
    ("Xin chào, cho tôi hỏi ngày hôm nay là ngày bao nhiêu?", "basic", [("get_time", {"part": "date"})]),   # câu thật 22:19
    ("Chào em, mở VS Code giúp anh", "basic", [("open_app", {"name": "Visual Studio Code"})]),
    ("Alo, mấy giờ rồi", "basic", [("get_time", {"part": "time"})]),
    ("Chào em", "chat", []),
    ("xin chào", "chat", []),
])
def test_greeting_prefix_does_not_hide_simple_command(heard, kind, calls):
    route = IntentRouter().route(heard)
    assert route.kind == kind and route.calls == calls


# ------------------------------------------------------------------ từ tiếng Anh / viết tắt
@pytest.mark.parametrize("heard,expected", [
    ("mở phôn đơ dự án", "mở folder dự án"), ("Mở phai nghiên cứu", "Mở file nghiên cứu"),
    ("mở iu túp", "mở YouTube"), ("bật oai phai", "bật Wi-Fi"), ("tìm trên gu gồ", "tìm trên Google"),
    ("cóp pi đoạn này", "copy đoạn này"), ("mở pi đi ép hợp đồng", "mở PDF hợp đồng"),
    ("áo bị phai màu", "áo bị phai màu"), ("rẽ phải", "rẽ phải"),          # tiếng Việt thường không bị đổi
])
def test_english_terms_normalized(heard, expected):
    from nexa.ai.english_terms import normalize_english
    assert normalize_english(heard) == expected


@pytest.mark.parametrize("heard,calls", [
    ("Mà yêu đôi", [("open_url", {"url": "https://www.youtube.com"})]),                  # câu thật 22:24
    ("mở iu túp", [("open_url", {"url": "https://www.youtube.com"})]),
    ("Má gu gồ", [("open_url", {"url": "https://www.google.com"})]),
    ("Mở phai nghiên cứu khoa học trong máy tôi", [("open_named", {"name": "nghiên cứu khoa học", "kind": "file"})]),
    ("mở file báo cáo trong Downloads",
     [("open_named", {"name": "báo cáo", "kind": "file", "folder": "Downloads"})]),
    ("mở folder dự án", [("open_named", {"name": "dự án", "kind": "folder"})]),
    ("tạo phôn đơ dự án", [("create_folder", {"name": "dự án"})]),
    ("tìm file báo cáo", [("find_files", {"name": "báo cáo"})]),
    ("cóp pi", [("press_keys", {"keys": ["ctrl", "c"]})]),
    ("Hôm nay là ngày bao nhiêu?", [("get_time", {"part": "date"})]),
])
def test_router_understands_english_words(heard, calls):
    assert IntentRouter().route(heard).calls == calls


def test_ordinary_sentence_starting_with_ma_is_untouched():
    assert IntentRouter().route("mà trời đẹp quá").kind == "ai"


def test_open_by_name_opens_best_match_and_asks_when_ambiguous(tmp_path, monkeypatch):
    import os
    from nexa.desktop.apps_and_files import FileService
    (tmp_path / "Bao cao thang 9.docx").write_text("x")
    (tmp_path / "du an").mkdir()
    (tmp_path / "du an 2").mkdir()
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p), raising=False)
    fs = FileService(_Cfg())
    monkeypatch.setattr(FileService, "roots", property(lambda self: [tmp_path]))
    monkeypatch.setattr(fs, "check", lambda p: __import__("pathlib").Path(p))
    r = fs.open_by_name("báo cáo", "file")
    assert r.ok and opened and opened[-1].endswith("Bao cao thang 9.docx")
    r = fs.open_by_name("du an", "folder")                    # trùng tên hoàn toàn: mở luôn "du an"
    assert r.ok and opened[-1].endswith("du an")
    r = fs.open_by_name("xyz", "file")
    assert not r.ok and r.error_code == "not_found"
