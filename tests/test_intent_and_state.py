"""Kiểm thử lệnh tiếng Việt (bộ lệnh cơ bản), câu mơ hồ, lọc STT và máy trạng thái tổng thể."""
from __future__ import annotations

import numpy as np
import pytest

from nexa.ai.intent_router import IntentRouter, apply_stt_fixes, parse_vi_number
from nexa.core.events import AppState as S
from nexa.core.state_machine import StateMachine

APPS = {"notepad", "trình duyệt", "file explorer", "chrome"}
R = IntentRouter(app_exists=lambda n: n.lower() in APPS)


@pytest.mark.parametrize("text,calls", [
    ("Nexa, mở Notepad", [("open_app", {"name": "Notepad"})]),
    ("Gõ nội dung: Xin chào, tôi là Nguyễn Xuân Sơn", [("type_text", {"text": "Xin chào, tôi là Nguyễn Xuân Sơn"})]),
    ("Đặt âm lượng 30 phần trăm", [("set_volume", {"percent": 30})]),
    ("đặt âm lượng ba mươi phần trăm", [("set_volume", {"percent": 30})]),
    ("giảm âm lượng xuống 30 phần trăm", [("set_volume", {"percent": 30})]),
    ("giảm âm lượng 10 phần trăm", [("change_volume", {"delta": -10})]),
    ("Tìm trên web cách học Python", [("web_search", {"query": "cách học Python"})]),
    ("tìm trên web cách chụp màn hình", [("web_search", {"query": "cách chụp màn hình"})]),
    ("Chụp màn hình", [("take_screenshot", {"scope": "all"})]),
    ("Chúc màn hình", [("take_screenshot", {"scope": "all"})]),
    ("Nexa, bật điều khiển bằng tay", [("set_gesture_mode", {"enabled": True})]),
    ("tắt điều khiển bằng tay", [("set_gesture_mode", {"enabled": False})]),
    ("Mở trình duyệt, tìm hướng dẫn Python rồi giảm âm lượng xuống 30 phần trăm",
     [("open_app", {"name": "trình duyệt"}), ("web_search", {"query": "hướng dẫn Python"}), ("set_volume", {"percent": 30})]),
    ("mở notepad rồi gõ xin chào, tôi là sơn", [("open_app", {"name": "notepad"}), ("type_text", {"text": "xin chào, tôi là sơn"})]),
    ("tìm cách học python và java", [("web_search", {"query": "cách học python và java"})]),
    ("thu nhỏ cửa sổ", [("minimize_window", {})]),
    ("khôi phục cửa sổ", [("restore_last_minimized", {})]),
    ("chuyển sang màn hình 2", [("move_window_to_monitor_2", {})]),
    ("tạm dừng video", [("youtube_pause", {})]),
    ("phát tiếp video", [("youtube_resume", {})]),
    ("cuộn lên 5 nấc", [("scroll", {"direction": "up", "notches": 5})]),
    ("bấm phím control shift t", [("press_keys", {"keys": ["ctrl", "shift", "t"]})]),
    ("sao chép", [("press_keys", {"keys": ["ctrl", "c"]})]),
    ("mấy giờ rồi", [("get_time", {"part": "time"})]),
    ("xem thông tin hệ thống", [("get_system_info", {})]),
    ("mở youtube", [("open_url", {"url": "https://www.youtube.com"})]),
    ("tạo thư mục Báo cáo trong tài liệu", [("create_folder", {"name": "Báo cáo", "parent": "tài liệu"})]),
    ("tắt tiếng", [("mute", {"on": True})]),
])
def test_basic_commands(text, calls):
    r = R.route(text)
    assert r.kind == "basic", (text, r)
    assert r.calls == calls


@pytest.mark.parametrize("text,kind", [
    ("Dừng lại", "stop"), ("Nexa, nghỉ đi", "sleep"), ("hủy", "cancel"),
    ("Mở Notepad và viết một đoạn giới thiệu ngắn về NXS MEDIA", "ai"),
    ("hôm nay em thấy thế nào", "ai"), ("xin chào", "chat"), ("xóa hội thoại", "internal"),
])
def test_other_kinds(text, kind):
    assert R.route(text).kind == kind


def test_ambiguous_asks_for_missing_part_and_resumes():
    r = R.route("mở")
    assert r.kind == "clarify" and "ứng dụng nào" in r.reply
    r2 = R.route("notepad", resume=r.resume)
    assert r2.kind == "basic" and r2.calls == [("open_app", {"name": "notepad"})]
    r = R.route("âm lượng")
    assert r.kind == "clarify" and "bao nhiêu" in r.reply
    assert R.route("40", resume=r.resume).calls == [("set_volume", {"percent": 40})]
    assert R.route("gõ").kind == "clarify"


def test_confirmation_words_only_when_pending():
    assert R.route("đồng ý", pending_confirmation=True).kind == "confirm"
    assert R.route("không", pending_confirmation=True).kind == "deny"
    assert R.route("đồng ý", pending_confirmation=False).kind != "confirm"


def test_unknown_app_is_not_guessed():
    assert R.route("mở phần mềm lạ hoắc xyz").kind == "ai"


def test_vietnamese_numbers():
    assert parse_vi_number("ba muoi phan tram") == 30
    assert parse_vi_number("muoi lam") == 15
    assert parse_vi_number("mot tram") == 100
    assert parse_vi_number("hai muoi lam") == 25
    assert parse_vi_number("khong co so") is None


def test_stt_fixes():
    assert apply_stt_fixes("Đã tâm lượng 30") == "đặt âm lượng 30"


def test_stt_rejects_silence_and_hallucination(config):
    from nexa.audio.stt import SpeechRecognizer

    class Seg:
        def __init__(self, text, lp=-0.2, nsp=0.1):
            self.text, self.avg_logprob, self.no_speech_prob = text, lp, nsp

    class Model:
        def __init__(self, segs):
            self.segs = segs

        def transcribe(self, audio, **kw):
            assert kw["language"] == "vi" and kw["vad_filter"] is True
            return iter(self.segs), None

    stt = SpeechRecognizer(config, config.settings_path.parent)
    audio = (np.random.default_rng(0).normal(0, 0.1, 16000)).astype(np.float32)
    stt._model = Model([Seg(" Hãy subscribe cho kênh Ghiền Mì Gõ")])
    assert not stt.transcribe(audio).ok
    stt._model = Model([Seg(" mở notepad")])
    assert stt.transcribe(audio).text == "mở notepad"
    assert not stt.transcribe(np.zeros(16000, np.float32)).ok
    stt._model = Model([])
    assert not stt.transcribe(audio).ok


# ------------------------------------------------------------------ máy trạng thái
def test_normal_lifecycle():
    sm = StateMachine()
    seen = []
    sm.add_listener(lambda old, new, d: seen.append(new))
    for st in (S.STANDBY, S.WAKING, S.SPEAKING, S.LISTENING, S.THINKING, S.EXECUTING, S.CONFIRMING,
               S.EXECUTING, S.SPEAKING, S.LISTENING, S.STANDBY):
        assert sm.set(st)
    assert seen[-1] == S.STANDBY and not sm.awake


def test_invalid_transition_rejected():
    sm = StateMachine()
    assert sm.set(S.LISTENING) is False
    assert sm.state == S.INITIALIZING
    sm.set(S.STANDBY)
    assert sm.set(S.WAKING) and sm.awake
