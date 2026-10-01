"""Chức năng tự động hóa v1.6: tài liệu Office mới, file VS Code, bỏ quảng cáo YouTube, Zalo, quản trị máy."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.core.events import ToolResult
from nexa.desktop import admin, office, youtube_ads, zalo


# ------------------------------------------------------------------ câu lệnh tiếng Việt
@pytest.mark.parametrize("heard,calls", [
    ("tạo file word mới", [("new_document", {"kind": "word"})]),
    ("mở word mới", [("new_document", {"kind": "word"})]),
    ("tạo file excel mới tên báo cáo", [("new_document", {"kind": "excel", "name": "báo cáo"})]),
    ("mở powerpoint mới", [("new_document", {"kind": "powerpoint"})]),
    ("tạo bài thuyết trình mới", [("new_document", {"kind": "powerpoint"})]),
    ("tạo file mới trong VS Code", [("vscode_new_file", {})]),
    ("tạo file main.py trong vs code", [("vscode_new_file", {"name": "main.py"})]),
    ("trong VS Code tạo file mới", [("vscode_new_file", {})]),
    ("bỏ qua quảng cáo", [("skip_youtube_ad", {})]),
    ("tắt quảng cáo của video này", [("skip_youtube_ad", {})]),
    ("bật tự động bỏ qua quảng cáo", [("auto_skip_ads", {"enabled": True})]),
    ("tắt tự động bỏ qua quảng cáo", [("auto_skip_ads", {"enabled": False})]),
    ("kiểm tra tin nhắn zalo", [("check_zalo", {})]),
    ("có ai nhắn tin cho tôi không", [("check_zalo", {})]),
    ("xem zalo có tin nhắn mới không", [("check_zalo", {})]),
    ("chạy với quyền quản trị", [("request_admin", {})]),
    ("xin quyền admin", [("request_admin", {})]),
    ("mở powershell với quyền quản trị", [("admin_shell", {"kind": "powershell"})]),
    ("mở task manager", [("open_admin_tool", {"name": "task manager"})]),
    ("mở quản lý thiết bị", [("open_admin_tool", {"name": "quan ly thiet bi"})]),
    ("ứng dụng nào đang ngốn RAM", [("top_processes", {"by": "ram"})]),
    ("buộc tắt Zalo", [("end_process", {"name": "Zalo", "force": True})]),
    ("tắt Chrome đang treo", [("end_process", {"name": "Chrome"})]),
    ("xem dung lượng ổ đĩa", [("disk_usage", {})]),
    ("kiểm tra mạng", [("network_info", {})]),
    ("máy có mạng không", [("network_info", {})]),
])
def test_routing(heard, calls):
    assert IntentRouter().route(heard).calls == calls


@pytest.mark.parametrize("heard,calls", [
    ("mở Word", [("open_app", {"name": "Word"})]),                 # không có "mới" → mở ứng dụng
    ("mở Excel", [("open_app", {"name": "Excel"})]),
    ("xem thông tin hệ thống", [("get_system_info", {})]),
    ("mở VS Code", [("open_app", {"name": "Visual Studio Code"})]),
    ("đóng Zalo", [("close_named", {"name": "Zalo", "kind": "any"})]),
    ("tắt tiếng", [("mute", {"on": True})]),
])
def test_existing_commands_not_hijacked(heard, calls):
    assert IntentRouter().route(heard).calls == calls


# ------------------------------------------------------------------ Zalo: chỉ tên, không nội dung
def _box(text, left, top, height=21):
    return zalo.TextBox(text, left, top, height)


def test_zalo_parses_names_and_badges():
    """Bố cục thật đo trên máy anh Sơn: tên cỡ chữ 21, trích tin cỡ 20, số chưa đọc ở cột ảnh (x≈108)."""
    boxes = [
        _box("Nhóm Dự án", 140, 215), _box("14:03", 355, 217, 17), _box("Anh: ok em nhé", 140, 241, 20),
        _box("5", 111, 240, 16),
        _box("Chị Lan", 140, 293), _box("13:58", 355, 295, 17), _box("Gửi anh file nhé", 140, 319, 20),
        _box("37", 108, 318, 16),
        _box("Không đọc", 140, 371), _box("Tin nhắn cũ", 140, 397, 20),        # không có badge → bỏ qua
    ]
    out = zalo.parse_unread(boxes)
    assert [(u.name, u.count) for u in out] == [("Nhóm Dự án", "5"), ("Chị Lan", "37")]


def test_zalo_joins_name_split_into_pieces():
    boxes = [_box("Nguyễn", 140, 215), _box("Xuân Sơn", 200, 215), _box("xin chào", 140, 241, 20),
             _box("2", 110, 240, 16)]
    assert [(u.name, u.count) for u in zalo.parse_unread(boxes)] == [("Nguyễn Xuân Sơn", "2")]


def test_zalo_no_badges_means_no_unread():
    assert zalo.parse_unread([_box("Ai đó", 140, 215), _box("tin nhắn", 140, 241, 20)]) == []
    assert zalo.parse_unread([]) == []


@pytest.mark.parametrize("names,expected", [
    (["An"], "Có tin nhắn mới từ An."),
    (["An", "Bình"], "Có tin nhắn mới từ An và Bình."),
    (["A", "B", "C"], "Có tin nhắn mới từ A, B và C."),
    ([str(i) for i in range(9)], "Có tin nhắn mới từ 0, 1, 2, 3, 4, 5 và 3 cuộc trò chuyện khác."),
])
def test_zalo_sentence(names, expected):
    assert zalo.unread_sentence(names) == expected


def test_zalo_not_running_is_reported(monkeypatch):
    monkeypatch.setattr(zalo, "_main_windows", lambda: [])
    r = zalo.check_unread()
    assert not r.ok and r.error_code == "not_running"


# ------------------------------------------------------------------ Office / VS Code
class FakeDoc:
    def __init__(self):
        self.saved = None

    def SaveAs2(self, path):
        self.saved = path

    SaveAs = SaveAs2

    @property
    def Slides(self):
        return SimpleNamespace(Add=lambda i, layout: None)

    def Windows(self, i):
        return SimpleNamespace(Activate=lambda: None)


class FakeApp:
    def __init__(self):
        self.doc = FakeDoc()
        self.Visible = False
        self.Documents = SimpleNamespace(Add=lambda: self.doc)
        self.Workbooks = SimpleNamespace(Add=lambda: self.doc)
        self.Presentations = SimpleNamespace(Add=lambda: self.doc)

    def Activate(self):
        pass


@pytest.mark.parametrize("kind,label", [("word", "Word"), ("excel", "Excel"), ("powerpoint", "PowerPoint")])
def test_new_office_document(kind, label, tmp_path):
    app = FakeApp()
    r = office.new_office_document(kind, None, tmp_path, dispatch=lambda progid: app)
    assert r.ok and r.verified and label in r.message and app.Visible and app.doc.saved is None


def test_new_document_with_name_never_overwrites(tmp_path):
    app = FakeApp()
    (tmp_path / "báo cáo.docx").write_text("cu", encoding="utf-8")
    r = office.new_office_document("word", "báo cáo", tmp_path, dispatch=lambda progid: app)
    assert r.ok and Path(app.doc.saved).name == "báo cáo (2).docx"
    assert (tmp_path / "báo cáo.docx").read_text(encoding="utf-8") == "cu"


def test_office_failure_is_reported_not_crashed(tmp_path):
    def boom(progid):
        raise OSError("Office chưa cài")
    r = office.new_office_document("word", None, tmp_path, dispatch=boom)
    assert not r.ok and r.error_code == "com_failed"


def test_unique_path_counts_up(tmp_path):
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "a (2).txt").write_text("")
    assert office.unique_path(tmp_path, "a", ".txt").name == "a (3).txt"


# ------------------------------------------------------------------ quảng cáo YouTube
def _ads_ctx(monkeypatch, skip_after: int | None, has_ad=True, ads=1):
    """skip_after: sau bao nhiêu lượt quét thì nút 'Bỏ qua' hiện ra (None = không bao giờ); ads: số quảng cáo."""
    state = {"n": 0, "clicked": [], "left": ads if has_ad else 0}

    def st(hwnd):
        state["n"] += 1
        if state["left"] <= 0:
            return youtube_ads.PlayerState(ad=False)
        skip = object() if skip_after is not None and state["n"] > skip_after else None
        return youtube_ads.PlayerState(ad=True, skip=skip)

    def press(elem, click=False):
        state["clicked"].append("click" if click else "invoke")
        state["left"] -= 1
        state["n"] = 0
        return True
    monkeypatch.setattr(youtube_ads, "youtube_windows", lambda wm: [5])
    return state, st, press


def _skip(monkeypatch, timeout=5, **kw):
    state, st, press = _ads_ctx(monkeypatch, **kw)
    return state, youtube_ads.skip_ad(wm=None, timeout=timeout, sleep=lambda s: None, state=st, press_fn=press)


def test_skip_ad_clicks_when_button_appears(monkeypatch):
    state, r = _skip(monkeypatch, skip_after=1)
    assert r.ok and r.verified and state["clicked"] == ["invoke"]


def test_skip_two_ads_in_a_row(monkeypatch):
    state, r = _skip(monkeypatch, skip_after=0, ads=2)
    assert r.ok and r.verified and state["clicked"] == ["invoke", "invoke"]


def test_skip_falls_back_to_real_click_when_invoke_ignored(monkeypatch):
    clicks = []
    st = lambda hwnd: youtube_ads.PlayerState(ad=True, skip=object()) if "click" not in clicks else         youtube_ads.PlayerState(ad=False)
    monkeypatch.setattr(youtube_ads, "youtube_windows", lambda wm: [5])
    r = youtube_ads.skip_ad(wm=None, timeout=5, sleep=lambda s: None, state=st,
                            press_fn=lambda e, click=False: clicks.append("click" if click else "invoke") or True)
    assert r.ok and clicks == ["invoke", "invoke", "click"]


def test_no_ad_reports_no_op_immediately(monkeypatch):
    state, r = _skip(monkeypatch, skip_after=None, has_ad=False)
    assert r.ok and r.data.get("no_op") and state["n"] == 1


def test_unskippable_ad_reports_honestly(monkeypatch):
    _, r = _skip(monkeypatch, timeout=0.2, skip_after=None, has_ad=True)
    assert not r.ok and r.error_code == "not_skippable"


def test_no_youtube_window(monkeypatch):
    monkeypatch.setattr(youtube_ads, "youtube_windows", lambda wm: [])
    monkeypatch.setattr(youtube_ads, "_bring_youtube_tab", lambda wm: [])
    r = youtube_ads.skip_ad(wm=None, timeout=1, sleep=lambda s: None)
    assert not r.ok and r.error_code == "no_youtube"


# Cấu trúc trình phát đo trên YouTube thật (2026-09-24, giao diện tiếng Việt): (là Button, tên, lớp HTML, ẩn).
PLAYER_ITEMS = [(True, "Hình mờ của kênh", "branding-img-container ytp-button", False),
                (False, "♪ quảng cáo trong lời bài hát ♪", "", False),          # phụ đề: không có lớp
                (True, "Tạm dừng (k)", "ytp-play-button ytp-button", False),
                (True, "Cài đặt", "ytp-button ytp-settings-button", False)]


@pytest.mark.parametrize("player_class,extra,ad,skip", [
    ("html5-video-player ytp-transparent", [], False, None),
    ("html5-video-player ad-showing ad-interrupting", [], True, None),
    ("html5-video-player ad-showing", [(True, "Bỏ qua", "ytp-skip-ad-button", False)], True, 4),
    ("html5-video-player ad-showing", [(True, "Skip", "ytp-ad-skip-button-modern ytp-button", False)], True, 4),
    ("html5-video-player", [(False, "Được tài trợ", "ytp-ad-badge__text", False)], True, None),
    ("html5-video-player ad-showing", [(True, "Bỏ qua", "ytp-skip-ad-button", True)], True, None),   # nút đang ẩn
])
def test_classify_player(player_class, extra, ad, skip):
    assert youtube_ads.classify(player_class, PLAYER_ITEMS + extra) == (ad, skip)


@pytest.mark.parametrize("name,is_skip", [
    ("Bỏ qua quảng cáo", True), ("Skip Ad", True), ("Bỏ qua", True), ("Skip Ads", True),
    ("Bỏ qua quảng cáo sau 5 giây", False), ("Đăng ký", False), ("Bỏ thích", False),
])
def test_skip_button_names(name, is_skip):
    from nexa.utils.text import fold
    assert bool(youtube_ads.SKIP_RE.match(fold(name))) is is_skip


# ------------------------------------------------------------------ quản trị
def test_essential_processes_are_protected():
    for name in ("csrss", "lsass", "winlogon", "services.exe"):
        r = admin.end_process(name)
        assert not r.ok and r.error_code == "protected"


def test_end_process_not_found():
    assert admin.end_process("khong-co-tien-trinh-nay")[1] if False else \
        admin.end_process("khong-co-tien-trinh-nay").error_code == "not_found"


def test_admin_tools_table_matches_router():
    import re
    from nexa.ai.intent_router import ADMIN_TOOL_RE
    for key in admin.ADMIN_TOOLS:
        assert re.fullmatch(ADMIN_TOOL_RE, key), key


def test_readonly_admin_info_runs():
    assert admin.disk_usage().ok
    assert admin.network_info().ok
    assert admin.top_processes(2, sample_s=0.05).ok
    assert isinstance(admin.is_admin(), bool)


def test_end_process_closes_windows_politely(monkeypatch):
    import psutil
    proc = SimpleNamespace(pid=999, info={"name": "notepad.exe"})
    monkeypatch.setattr(admin, "find_processes", lambda name: [proc])
    monkeypatch.setattr(psutil, "wait_procs", lambda procs, timeout: (procs, []))
    closed = []
    wm = SimpleNamespace(list_windows=lambda limit=100: [{"hwnd": 3}],
                         identity=lambda h: SimpleNamespace(pid=999),
                         close=lambda h: closed.append(h) or ToolResult.success("đóng", verified=True))
    r = admin.end_process("notepad", force=False, wm=wm)
    assert r.ok and closed == [3]
