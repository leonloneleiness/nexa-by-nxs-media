"""Chống tái phát: lỗi v1.4.0 xóa nhầm `log` trong controller làm mất đánh thức bằng vỗ tay."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import nexa.core.controller as controller_mod
from nexa.core.controller import Controller
from nexa.core.events import AppState

ROOT = Path(__file__).resolve().parents[1]


def _fake_controller(state=AppState.STANDBY, guard=False, guard_asleep=False, display_off=False):
    woke = []
    fake = SimpleNamespace(
        notify=lambda *a, **k: None,
        audio=SimpleNamespace(clap=SimpleNamespace(stats=lambda: {})),
        clap_test=False,
        sm=SimpleNamespace(state=state),
        wake=lambda source, **k: woke.append(source),
        config=SimpleNamespace(get=lambda k, d=None: {"power.away_after_s": 300}.get(k, d)),
        sleep_guard=SimpleNamespace(enabled=guard, display_off=display_off),
        _guard_asleep=guard_asleep,
        _wake_from_away=lambda: woke.append("away"),
    )
    return fake, woke


def test_clap_wakes_nexa(monkeypatch):
    monkeypatch.setattr(controller_mod, "_ms_since_last_input", lambda: None)
    fake, woke = _fake_controller()
    Controller._on_clap(fake, SimpleNamespace(kind="wake", count=1, peak_db=-23.5))
    assert woke == ["clap"]


def test_clap_right_after_typing_is_ignored_without_crash(monkeypatch):
    monkeypatch.setattr(controller_mod, "_ms_since_last_input", lambda: 50)
    fake, woke = _fake_controller()
    Controller._on_clap(fake, SimpleNamespace(kind="wake", count=1, peak_db=-23.5))
    assert woke == []


@pytest.mark.parametrize("idle_ms,guard,asleep,expected", [
    (10_000, True, False, "clap"),        # đang dùng máy: chỉ "Dạ, em nghe."
    (600_000, True, False, "away"),       # vắng 10 phút: bật màn hình, mở NEXA, chào đầy đủ
    (10_000, True, True, "away"),         # vừa "cho máy ngủ" (màn hình đã tắt)
    (600_000, False, False, "clap"),      # tắt ngủ canh gác: như cũ
])
def test_clap_after_away_uses_guard_wake(monkeypatch, idle_ms, guard, asleep, expected):
    monkeypatch.setattr(controller_mod, "_ms_since_last_input", lambda: idle_ms)
    fake, woke = _fake_controller(guard=guard, guard_asleep=asleep)
    Controller._on_clap(fake, SimpleNamespace(kind="wake", count=1, peak_db=-23.5))
    assert woke == [expected]


@pytest.mark.parametrize("state,guard,display_off,expected", [
    (AppState.LISTENING, True, True, ["away"]),   # màn hình tự tắt khi NEXA chưa về chờ: vỗ tay vẫn bật lại
    (AppState.STANDBY, True, True, ["away"]),     # màn hình tắt theo hẹn giờ/nút nguồn dù anh mới thao tác
    (AppState.LISTENING, True, False, []),        # màn hình sáng, NEXA đang nghe: như cũ
    (AppState.LISTENING, False, True, []),        # tắt ngủ canh gác: như cũ
])
def test_clap_turns_screen_back_on(monkeypatch, state, guard, display_off, expected):
    monkeypatch.setattr(controller_mod, "_ms_since_last_input", lambda: 10_000)
    fake, woke = _fake_controller(state=state, guard=guard, display_off=display_off)
    Controller._on_clap(fake, SimpleNamespace(kind="wake", count=1, peak_db=-23.5))
    assert woke == expected


def test_no_undefined_names_in_source():
    """Quét tĩnh toàn bộ mã nguồn: mọi tên dùng tới đều phải được định nghĩa/import."""
    pyflakes_api = pytest.importorskip("pyflakes.api")
    from pyflakes import messages
    from pyflakes.reporter import Reporter
    import io

    bad: list[str] = []

    class Collect(Reporter):
        def __init__(self):
            super().__init__(io.StringIO(), io.StringIO())

        def flake(self, message):
            if isinstance(message, (messages.UndefinedName, messages.UndefinedLocal,
                                    messages.UndefinedExport)):
                bad.append(str(message))

    rep = Collect()
    for path in (ROOT / "nexa").rglob("*.py"):
        pyflakes_api.checkPath(str(path), rep)
    assert bad == []


# ------------------------------------------------------------------ vặn nhỏ nhạc khi nghe lệnh
class _Vol:
    def __init__(self, v):
        self.v = v

    def GetMasterVolume(self):
        return self.v

    def SetMasterVolume(self, v, _ctx):
        self.v = v


def _ducker(sessions):
    from nexa.desktop.system import MediaDucker
    d = MediaDucker(level=0.2)
    d._sessions = lambda: iter([(k, SimpleNamespace(State=st, SimpleAudioVolume=vol, Process=None, ProcessId=1))
                                for k, st, vol in sessions])
    return d


def test_ducker_lowers_only_active_sessions_and_restores():
    music, idle = _Vol(0.8), _Vol(0.5)
    d = _ducker([("edge", 1, music), ("idle", 0, idle)])
    d._do_duck()
    assert music.v == pytest.approx(0.16) and idle.v == 0.5
    d._do_duck()                                            # gọi lặp không vặn nhỏ thêm
    assert music.v == pytest.approx(0.16)
    d._do_restore()
    assert music.v == pytest.approx(0.8) and not d.ducked
    d.stop()


def test_ducker_keeps_user_change_made_while_ducked():
    music = _Vol(0.8)
    d = _ducker([("edge", 1, music)])
    d._do_duck()
    music.v = 0.6                                           # anh tự chỉnh trong lúc NEXA nghe
    d._do_restore()
    assert music.v == 0.6
    d.stop()


def test_media_session_keeps_ducking_while_listening_then_sleeps():
    """v1.7.1: trước đây sau "mở nhạc" NEXA thôi vặn nhỏ → nhạc to lọt mic, câu kéo đủ 12 s, nghe sai.
    Nay vẫn vặn nhỏ khi nghe; hết một lượt chờ không ai nói thì về chế độ chờ (trả âm lượng)."""
    calls, standby = [], []
    fake = SimpleNamespace(ducker=SimpleNamespace(duck=lambda: calls.append("duck"),
                                                  restore=lambda: calls.append("restore")),
                           _duck_session=True, _media_playing=True, _awake=True, _last_activity=0.0,
                           _ai_busy=SimpleNamespace(is_set=lambda: False),
                           _basic_busy=SimpleNamespace(is_set=lambda: False),
                           safety=SimpleNamespace(pending=None), config=SimpleNamespace(get=lambda k, d=None: 60),
                           go_standby=lambda reason="": standby.append(reason),
                           audio=SimpleNamespace(listen=lambda: calls.append("listen")))
    Controller._duck(fake)
    assert calls == ["duck"]                                # vẫn vặn nhỏ dù vừa mở nhạc
    import time as _t
    fake._last_activity = _t.monotonic()                    # vừa nói xong, chưa tới 60 s
    Controller._on_listen_timeout(fake)
    assert standby and "nhạc" in standby[0] and "listen" not in calls
    fake._media_playing = False
    standby.clear()
    Controller._on_listen_timeout(fake)
    assert not standby and calls[-1] == "listen"            # không phát nhạc: nghe tiếp như cũ


# ------------------------------------------------------------------ câu nghe không rõ
@pytest.mark.parametrize("text,logprob,unclear", [
    ("Màu yếu đùa ý", -1.2, True),                 # vô nghĩa + Whisper không chắc → hỏi lại
    ("Màu yếu đùa ý", -0.4, False),                # Whisper chắc chắn → để Gemini hiểu
    ("Mở VS Code", -1.2, False),                   # khớp lệnh cơ bản → chạy luôn
    ("dừng lại", -1.5, False),
])
def test_unclear_speech_asks_again_instead_of_guessing(text, logprob, unclear):
    from nexa.ai.intent_router import IntentRouter
    fake = SimpleNamespace(config=SimpleNamespace(get=lambda k, d=None: None), router=IntentRouter(),
                           safety=SimpleNamespace(pending=None))
    res = SimpleNamespace(text=text, avg_logprob=logprob)
    assert Controller._unclear(fake, res) is unclear
