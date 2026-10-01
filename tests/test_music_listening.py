"""Nghe lệnh khi đang phát nhạc YouTube (log 2026-09-24: câu kéo đủ 12,5 s, "Đổi video Mở Antigravity" dính nhau)."""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest

from nexa.audio.pipeline import UtteranceSegmenter, VadConfig
from nexa.core.controller import Controller

SR, BLOCK = 16000, 320


def _music(n, level_db, rng):
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) for f in (220, 277, 330, 440, 660, 880, 1320))
    x = x * (0.6 + 0.4 * (np.sin(2 * np.pi * 2.0 * t) > 0)) + 0.3 * rng.standard_normal(n)
    return x / np.sqrt(np.mean(x ** 2)) * 10 ** (level_db / 20)


def _speech(n, level_db, rng):
    from scipy.signal import butter, lfilter
    b, a = butter(4, [300 / 8000, 3000 / 8000], btype="band")
    t = np.arange(n) / SR
    x = lfilter(b, a, rng.standard_normal(n)) * np.clip(np.sin(2 * np.pi * 4 * t), 0.15, 1)   # âm tiết ~4 Hz
    return x / np.sqrt(np.mean(x ** 2)) * 10 ** (level_db / 20)


def _segment(music_db=None, music_from=0.0, speech_s=1.5, tail_soft_db=0.0, seed=0):
    """Giọng nói từ 2,0 s; trả (lúc bắt đầu ghi, lúc chốt câu, lúc giọng hết)."""
    rng = np.random.default_rng(seed)
    n = int((2.0 + speech_s + 14) * SR)
    x = 1e-4 * rng.standard_normal(n)
    if music_db is not None:
        m0 = int(music_from * SR)
        x[m0:] += _music(n - m0, music_db, rng)
    s = _speech(int(speech_s * SR), -20, rng)
    s[-int(0.5 * SR):] *= 10 ** (-tail_soft_db / 20)
    x[2 * SR:2 * SR + s.size] += s
    seg = UtteranceSegmenter(VadConfig(end_silence_ms=600, max_utterance_s=12.0, listen_timeout_s=30))
    seg.start(0.0)
    start = None
    for i in range(0, n - BLOCK, BLOCK):
        ev = seg.process(x[i:i + BLOCK].astype(np.float32), i / SR)
        if ev and ev[0] == "speech_start":
            start = i / SR
        if ev and ev[0] == "utterance":
            return start, i / SR, 2.0 + speech_s
    return start, None, 2.0 + speech_s


@pytest.mark.parametrize("music_db", [-26, -40])
def test_music_starting_while_listening_does_not_stretch_utterance_to_max(music_db):
    # Video vừa mở bắt đầu phát sau lúc NEXA học nền ồn: trước đây câu kéo đủ 12 s (chốt lúc 13,24 s).
    _, end, speech_end = _segment(music_db, music_from=1.0)
    assert end is not None and end < speech_end + 1.2


@pytest.mark.parametrize("speech_s,tail_soft_db,music_db", [
    (1.5, 0, None), (4.0, 0, None), (6.0, 0, None), (3.0, 10, None), (3.0, 10, -44), (4.0, 0, -40)])
def test_normal_speech_is_not_cut_early(speech_s, tail_soft_db, music_db):
    start, end, speech_end = _segment(music_db, speech_s=speech_s, tail_soft_db=tail_soft_db)
    assert start is not None and start < 2.5
    assert end is not None and speech_end <= end < speech_end + 1.2


def test_ducked_music_still_lets_speech_through():
    # Nhạc to đều (-30 dB) che mất giọng; vặn nhỏ còn 20% (-14 dB → -44 dB) thì nghe được.
    assert _segment(-30)[0] is None
    start, end, speech_end = _segment(-44)
    assert start is not None and end is not None and end < speech_end + 1.2


# ------------------------------------------------------------------ vặn nhỏ cả video BẮT ĐẦU phát sau lúc nghe
class _Vol:
    def __init__(self, v):
        self.v = v

    def GetMasterVolume(self):
        return self.v

    def SetMasterVolume(self, v, _ctx):
        self.v = v


def test_ducker_catches_session_that_starts_playing_while_listening(monkeypatch):
    from nexa.desktop.system import MediaDucker
    monkeypatch.setattr(MediaDucker, "RESCAN_S", 0.02)
    music = _Vol(0.8)
    sessions = []
    d = MediaDucker(level=0.2)
    d._sessions = lambda: iter(list(sessions))
    d.duck()                                  # NEXA bắt đầu nghe: video còn đang tải, chưa có tiếng
    time.sleep(0.1)
    sessions.append(("edge", SimpleNamespace(State=1, SimpleAudioVolume=music, Process=None, ProcessId=1)))
    deadline = time.monotonic() + 2
    while music.v > 0.5 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert music.v == pytest.approx(0.16)     # video phát sau vẫn bị vặn nhỏ trong lúc nghe
    d.restore()
    deadline = time.monotonic() + 2
    while music.v < 0.5 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert music.v == pytest.approx(0.8)
    d.stop()


# ------------------------------------------------------------------ lời bài hát lọt mic không thành câu hỏi Gemini
def _fake(media=True):
    from nexa.ai.intent_router import IntentRouter
    return SimpleNamespace(_media_playing=media, router=IntentRouter(app_exists=lambda n: n.lower() == "antigravity"),
                           safety=SimpleNamespace(pending=None))


@pytest.mark.parametrize("text,noise", [
    ("Bỏ qua quảng cáo", False), ("tạm dừng video", False), ("Đổi video", False), ("Đóng YouTube", False),
    ("Mở Antigravity", False), ("Nexa, thời tiết hôm nay thế nào", False),
    ("anh yêu em nhiều lắm em ơi", True), ("Hãy đăng ký kênh để xem video mới", True),
])
def test_media_noise_filter(text, noise):
    assert Controller._media_noise(_fake(), SimpleNamespace(text=text)) is noise


def test_media_noise_filter_off_without_music():
    assert Controller._media_noise(_fake(media=False), SimpleNamespace(text="anh yêu em nhiều lắm")) is False


# ------------------------------------------------------------------ nhớ kết quả tìm YouTube
def test_youtube_search_is_cached(monkeypatch):
    from nexa.desktop.apps_and_files import AppLauncher
    calls = []
    monkeypatch.setattr(AppLauncher, "youtube_results",
                        staticmethod(lambda q, limit=10: calls.append(q) or [{"video_id": f"v{i}", "title": f"t{i}"}
                                                                           for i in range(8)]))
    a = AppLauncher(SimpleNamespace(get=lambda k, d=None: d))
    assert a._cached_youtube_results("nhạc TikTok Remix", 10) == a._cached_youtube_results("Nhạc TikTok remix", 10)
    assert calls == ["nhạc TikTok Remix"]      # lần 2 (khác hoa/thường) không tải lại
    a._cached_youtube_results("nhạc TikTok Remix", 20)
    assert len(calls) == 2                     # cần nhiều kết quả hơn lần trước: tải lại


def test_next_video_plays_following_result_of_last_search():
    from nexa.ai.tool_registry import h_play_youtube
    played = []
    apps = SimpleNamespace(play_youtube=lambda q, i: played.append((q, i)) or SimpleNamespace(ok=False))
    ctx = SimpleNamespace(services=SimpleNamespace(apps=apps, memory={}, media=None))
    h_play_youtube({"query": "nhạc TikTok Remix"}, ctx)
    h_play_youtube({"next": True}, ctx)
    h_play_youtube({"next": True}, ctx)
    assert played == [("nhạc TikTok Remix", 1), ("nhạc TikTok Remix", 2), ("nhạc TikTok Remix", 3)]


@pytest.mark.parametrize("text", ["Đổi video", "bài khác", "bài tiếp theo", "chuyển bài", "bỏ qua bài này"])
def test_next_video_phrases_are_basic_commands(text):
    from nexa.ai.intent_router import IntentRouter
    assert IntentRouter().route(text).calls == [("play_youtube", {"next": True})]
