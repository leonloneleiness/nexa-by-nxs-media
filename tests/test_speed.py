"""Phản hồi nhanh: đọc bản ngắn của câu trả lời và cắt khoảng lặng của giọng tổng hợp."""
from __future__ import annotations

import numpy as np
import pytest

from nexa.audio.tts import trim_silence
from nexa.core.controller import brief_speech


@pytest.mark.parametrize("message,spoken", [
    ("Đã mở video đầu tiên: Tóc Tiên - Ngày Mai (Official MV) ft. Hoàng Touliver.", "Đã mở video đầu tiên."),
    ("Đã tạm dừng: Video hay.", "Đã tạm dừng."),
    ("Đã mở Visual Studio Code.", "Đã mở Visual Studio Code."),
    ("Em đã gửi lệnh mở video đầu tiên (Bài hát) nhưng chưa thấy trình duyệt hiện video.",
     "Em đã gửi lệnh mở video đầu tiên nhưng chưa thấy trình duyệt hiện video."),
    ("Đã đặt âm lượng 30%", "Đã đặt âm lượng 30%."),
])
def test_brief_speech(message, spoken):
    assert brief_speech(message) == spoken


def test_trim_silence_keeps_speech_and_small_margins():
    sr = 24000
    speech = np.sin(np.linspace(0, 200, sr // 2)).astype(np.float32) * 0.5
    audio = np.concatenate([np.zeros(sr // 4), speech, np.zeros(sr)]).astype(np.float32)
    out = trim_silence(audio, sr)
    assert 0.5 <= out.size / sr <= 0.5 + 0.03 + 0.12 + 0.01
    assert trim_silence(np.zeros(sr, np.float32), sr).size == 0


# ------------------------------------------------------------------ chọn GPU / CPU cho nhận dạng
class _FakeWhisper:
    loads: list = []
    fail_on_cuda = False

    def __init__(self, name, device, compute_type, cpu_threads, download_root):
        if device == "cuda" and _FakeWhisper.fail_on_cuda:
            raise RuntimeError("CUDA lỗi")
        _FakeWhisper.loads.append((name, device, compute_type))

    def transcribe(self, *a, **k):
        return iter([]), None


def _recognizer(monkeypatch, cuda_ok, model="auto", device="auto"):
    import sys
    import types
    from nexa.audio import stt
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=_FakeWhisper))
    monkeypatch.setattr(stt, "cuda_ready", lambda: (cuda_ok, "" if cuda_ok else "thiếu cublas64_12.dll"))
    _FakeWhisper.loads = []
    values = {"stt.model": model, "stt.device": device, "stt.compute_type": "auto", "stt.cpu_threads": 2}
    cfg = type("C", (), {"get": lambda self, k, d=None: values.get(k, d)})()
    from pathlib import Path
    import tempfile
    return stt.SpeechRecognizer(cfg, Path(tempfile.mkdtemp()))


def test_auto_uses_turbo_on_gpu(monkeypatch):
    r = _recognizer(monkeypatch, cuda_ok=True)
    assert r.load() and _FakeWhisper.loads[-1] == ("large-v3-turbo", "cuda", "float16")
    assert r.model_name == "large-v3-turbo · CUDA"


def test_auto_without_gpu_uses_small_on_cpu(monkeypatch):
    r = _recognizer(monkeypatch, cuda_ok=False)
    assert r.load() and _FakeWhisper.loads[-1] == ("small", "cpu", "int8")


def test_gpu_failure_falls_back_to_cpu_instead_of_breaking(monkeypatch):
    _FakeWhisper.fail_on_cuda = True
    try:
        r = _recognizer(monkeypatch, cuda_ok=True)
        assert r.load() and _FakeWhisper.loads[-1] == ("small", "cpu", "int8") and r.device == "cpu"
    finally:
        _FakeWhisper.fail_on_cuda = False


def test_explicit_cpu_setting_is_respected(monkeypatch):
    r = _recognizer(monkeypatch, cuda_ok=True, model="small", device="cpu")
    assert r.load() and _FakeWhisper.loads[-1] == ("small", "cpu", "int8")


# ------------------------------------------------------------------ câu trả lời dài không được đọc to hết
def test_system_answers_speak_only_the_headline():
    """Lỗi đo được 23:52: đọc to cả dãy IP mất 15,5 giây. Câu đầu (loa đọc) không được chứa IP/danh sách dài."""
    from nexa.desktop import admin

    net = admin.network_info()
    spoken = brief_speech(net.message)
    assert net.ok and "Địa chỉ IP" in net.message          # chi tiết vẫn hiện trên màn hình
    assert "192." not in spoken and len(spoken) <= 70    # loa không đọc dãy số IP

    disk = admin.disk_usage()
    assert disk.ok and len(brief_speech(disk.message)) <= 60

    for by in ("cpu", "ram"):
        r = admin.top_processes(3, sample_s=0.05, by=by)
        head = brief_speech(r.message)
        assert ("CPU" in head) is (by == "cpu") and ("RAM" in head) is (by == "ram")
        assert len(head) <= 90


def test_router_asks_the_right_metric():
    from nexa.ai.intent_router import IntentRouter
    r = IntentRouter()
    assert r.route("ứng dụng nào đang ngốn RAM").calls == [("top_processes", {"by": "ram"})]
    assert r.route("app nào ngốn CPU").calls == [("top_processes", {"by": "cpu"})]
    assert r.route("app nào ngốn máy").calls == [("top_processes", {"by": "both"})]
