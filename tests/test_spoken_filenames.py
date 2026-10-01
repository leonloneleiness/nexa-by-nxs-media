"""Tên tệp đọc bằng giọng nói (log thật 24–27/09): Whisper nghe "main.py" thành "main.by"/"main.3"/"men chấm bay",
"README.md" thành "read.md", và "trong VS Code" từng bị hiểu là thư mục tên "VS Code"."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.desktop.apps_and_files import FileService
from nexa.desktop.spoken_names import parse_spoken_name, score_name


class _Cfg:
    def get(self, key, default=None):
        return {"files.search_limit": 50}.get(key, default)


@pytest.mark.parametrize("heard,display", [
    ("main.by", "main.py"), ("main.3", "main.py"), ("men chấm bay", "men.py"), ("main py", "main.py"),
    ("read.md", "read.md"), ("rít mi chấm em đê", "rit mi.md"), ("Public HTML", "public.html"),
    ("public.html", "public.html"), ("men.v", "men"), ("báo cáo", "bao cao"), ("báo cáo pdf", "bao cao.pdf"),
    ("config chấm giây sơn", "config.json"), ("bài ba", "bai ba"),       # "ba" đứng riêng không bị coi là đuôi
])
def test_parse_spoken_name(heard, display):
    assert parse_spoken_name(heard).display == display


@pytest.mark.parametrize("heard,right,wrong", [
    ("main.by", "main.py", "main.js"), ("main.3", "main.py", "menu.py"), ("men chấm bay", "main.py", "comment.py"),
    ("read.md", "README.md", "readme.txt"), ("rít mi chấm em đê", "README.md", "main.py"),
    ("pắp lích chấm html", "public.html", "main.py"),
])
def test_score_prefers_the_file_meant(heard, right, wrong):
    q = parse_spoken_name(heard)
    assert score_name(q, right, False) > score_name(q, wrong, False)
    assert score_name(q, right, False) >= 0.73


def test_unrelated_names_do_not_match():
    q = parse_spoken_name("main.py")
    assert score_name(q, "Bao cao thang 9.docx", False) == 0
    assert score_name(parse_spoken_name("xyz"), "main.py", False) == 0


@pytest.mark.parametrize("heard,args", [
    ("Mở file public.html trong VS Code", {"name": "public.html", "kind": "file", "app": "vscode"}),
    ("Mở file read.md trong VS Code", {"name": "read.md", "kind": "file", "app": "vscode"}),
    ("file main.by trong VS Code cho tôi", {"name": "main.by", "kind": "file", "app": "vscode"}),
    ("Đọc giúp tôi tuệp main.3 trong VS Code", {"name": "main.3", "kind": "file", "app": "vscode"}),
    ("mở main.py trong VS Code", {"name": "main.py", "kind": "file", "app": "vscode"}),
    ("Mở thư mục Public HTML trong VS Code", {"name": "Public HTML", "kind": "folder", "app": "vscode"}),
])
def test_router_open_in_vscode(heard, args):
    assert IntentRouter().route(heard).calls == [("open_named", args)]


def test_router_new_file_in_vscode_still_creates():
    assert IntentRouter().route("tạo file main.py trong vs code").calls == [("vscode_new_file", {"name": "main.py"})]
    assert IntentRouter().route("mở file mới trong VS Code").calls == [("vscode_new_file", {})]


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Cây thư mục giống máy anh: dự án NEXA đang mở trong VS Code + tệp trùng tên ở chỗ khác."""
    nexa = tmp_path / "NEXA"
    (nexa / "assets" / "fonts").mkdir(parents=True)
    (nexa / "main.py").write_text("x")
    (nexa / "menu.js").write_text("x")
    (nexa / "README.md").write_text("x")
    (nexa / "assets" / "fonts" / "README.md").write_text("x")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "main.py").write_text("x")
    (tmp_path / "public.html").write_text("x")
    opened: list[tuple[str, str]] = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(("default", p)), raising=False)
    import nexa.desktop.office as office
    monkeypatch.setattr(office, "find_vscode", lambda: "code.exe")
    monkeypatch.setattr(office, "vscode_workspaces", lambda: [nexa])
    monkeypatch.setattr(office, "open_in_vscode",
                        lambda p, exe=None: (opened.append(("vscode", p)),
                                             __import__("nexa.core.events", fromlist=["ToolResult"]).ToolResult(
                                                 ok=True, verified=False, message=f"Đã mở {Path(p).name} trong VS Code.",
                                                 data={"path": p}))[1])
    fs = FileService(_Cfg())
    monkeypatch.setattr(FileService, "roots", property(lambda self: [tmp_path]))
    monkeypatch.setattr(fs, "check", lambda p: Path(p))
    return fs, nexa, opened


@pytest.mark.parametrize("heard", ["main.by", "main.3", "men chấm bay", "men.v"])
def test_misheard_main_py_opens_project_file_in_vscode(project, heard):
    fs, nexa, opened = project
    r = fs.open_by_name(heard, "file", app="vscode")
    assert r.ok, r.message
    assert opened[-1] == ("vscode", str(nexa / "main.py"))


def test_read_md_opens_project_readme(project):
    fs, nexa, opened = project
    r = fs.open_by_name("read.md", "file", app="vscode")
    assert r.ok and opened[-1] == ("vscode", str(nexa / "README.md"))


def test_script_is_opened_in_editor_not_executed(project):
    fs, nexa, opened = project
    r = fs.open_by_name("main.py", "file")                   # không nói VS Code: vẫn không được CHẠY main.py
    assert r.ok and opened[-1][0] == "vscode"


def test_folder_word_with_file_extension_opens_the_file(project, tmp_path):
    fs, _, opened = project
    r = fs.open_by_name("Public HTML", "folder", app="vscode")
    assert r.ok and opened[-1] == ("vscode", str(tmp_path / "public.html"))


def test_ambiguous_readme_lists_numbered_and_accepts_answer(project, monkeypatch):
    fs, nexa, opened = project
    import nexa.desktop.office as office
    monkeypatch.setattr(office, "vscode_workspaces", lambda: [])
    r = fs.open_by_name("README.md", "file")
    assert not r.ok and r.error_code == "ambiguous" and "1." in r.message
    r2 = fs.open_by_name("số hai", "file")
    assert r2.ok and opened[-1][1] in r.data["candidates"]
    r = fs.open_by_name("README.md", "file")
    r3 = fs.open_by_name("cái", "file", where="fonts")        # "mở tệp cái trong fonts"
    assert r3.ok and opened[-1][1] == str(nexa / "assets" / "fonts" / "README.md")


def test_not_found_suggests_similar_name_then_accepts_number(project, tmp_path):
    fs, _, opened = project
    (tmp_path / "popup.html").write_text("x")
    (tmp_path / "public.html").unlink()
    r = fs.open_by_name("public.html", "file", app="vscode")
    assert not r.ok and r.error_code == "ambiguous" and "popup.html" in r.message
    assert r.data["resume"] == "mở tệp {} trong VS Code"
    r = fs.open_by_name("số một", "file", app="vscode")
    assert r.ok and opened[-1] == ("vscode", str(tmp_path / "popup.html"))


def test_readme_beats_other_markdown_with_similar_sound():
    q = parse_spoken_name("read.md")
    assert score_name(q, "README.md", False) > score_name(q, "three_d.md", False)
