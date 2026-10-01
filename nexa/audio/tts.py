"""Phát âm tiếng Việt và hiệu ứng âm thanh.

Backend:
- edge  : edge-tts (mặc định en-US-AndrewMultilingualNeural — giọng nam đa ngữ, đọc được cả tiếng Việt;
          hoặc vi-VN-NamMinhNeural / vi-VN-HoaiMyNeural). CẦN INTERNET, dùng dịch vụ đọc văn bản của Microsoft Edge; có thể lỗi hoặc bị giới hạn bất cứ lúc nào.
- winrt : Windows.Media.SpeechSynthesis (giọng OneCore, OFFLINE). Chỉ dùng khi máy có giọng vi-VN
          (ví dụ "Microsoft An" — giọng nữ; NEXA hạ cao độ khi chọn giọng nam).
- sapi  : SAPI5 (OFFLINE). Chỉ dùng khi có giọng SAPI tiếng Việt (LCID 42A) — nhiều máy không có.
- none  : chỉ hiển thị chữ.
"auto" thử edge → winrt → sapi. Nếu không có backend nào, NEXA vẫn trả lời bằng chữ.

Tối ưu độ trễ:
- Câu trả lời được tách theo câu; câu kế tiếp được tổng hợp TRONG LÚC câu hiện tại đang phát.
- Câu ngắn hay dùng (lời chào, xác nhận…) được cache trong bộ nhớ.
- Luồng loa (24 kHz) được giữ mở giữa các lần nói để tránh độ trễ mở thiết bị (đặc biệt tai nghe Bluetooth).
Hiệu ứng giọng (tts.effect = jarvis | robot) áp dụng cục bộ sau khi tổng hợp.

Luồng phát báo on_start/on_end để pipeline mic tạm chặn đầu vào (chống tự nghe lời mình) và
on_level để quả cầu dao động theo âm thanh thật đang phát; on_bands (8 dải tần) để sóng âm quanh quả cầu
bám đúng phổ giọng; on_chunk báo câu đang phát (phụ đề HUD), chuỗi rỗng khi nói xong.
"""
from __future__ import annotations

import asyncio
import io
import queue
import re
import threading
import time
import wave
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from nexa.audio import sfx, voice_fx
from nexa.utils.logging import get_logger

log = get_logger("tts")

OUT_SR = 24000
N_BANDS = 8
_BAND_EDGES = np.geomspace(80.0, 8000.0, N_BANDS + 1)


def spectrum_bands(chunk: np.ndarray, sr: int = OUT_SR) -> list[float]:
    """Năng lượng 8 dải tần chia theo thang log 80 Hz – 8 kHz, chuẩn hóa về 0..1 (dùng cho quả cầu)."""
    if chunk.size < 32:
        return [0.0] * N_BANDS
    spec = np.abs(np.fft.rfft(chunk * np.hanning(chunk.size)))
    freqs = np.fft.rfftfreq(chunk.size, 1.0 / sr)
    out = []
    for lo, hi in zip(_BAND_EDGES[:-1], _BAND_EDGES[1:]):
        sel = spec[(freqs >= lo) & (freqs < hi)]
        mag = float(np.sqrt(np.mean(sel * sel))) if sel.size else 0.0
        # thang dB: -50 dB → 0, 0 dB → 1 (so với biên độ đầy thang của khối)
        db = 20 * np.log10(mag / (chunk.size / 4) + 1e-9)
        out.append(round(min(1.0, max(0.0, (db + 50) / 50)), 3))
    return out


@dataclass
class _Job:
    kind: str                 # speech | sfx
    chunks: list[str] = field(default_factory=list)
    samples: np.ndarray | None = None
    sr: int = OUT_SR
    done: threading.Event | None = None


def split_sentences(text: str, max_len: int = 220) -> list[str]:
    """Tách câu để phát dần; câu đầu ngắn giúp NEXA bắt đầu nói sớm."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…;:])\s+|\n+", text) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            cut = cut if cut > 40 else p.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out or [text.strip()]


def _decode_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as wf:
        sr, ch, width = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError("WAV không phải 16-bit")
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def trim_silence(audio: np.ndarray, sr: int, lead_s: float = 0.03, tail_s: float = 0.12,
                 threshold: float = 0.01) -> np.ndarray:
    """Cắt khoảng lặng đầu/cuối. Edge TTS để ~0,25 s lặng đầu và 0,8–1,3 s lặng cuối: mic phải chờ hết
    khoảng này mới nghe lại, nên cắt đi làm NEXA phản hồi nhanh hơn gần 1 giây mỗi câu."""
    if audio.size == 0:
        return audio
    idx = np.flatnonzero(np.abs(audio) > threshold)
    if idx.size == 0:
        return audio[:0]
    start = max(0, int(idx[0]) - int(lead_s * sr))
    end = min(audio.size, int(idx[-1]) + int(tail_s * sr))
    return audio[start:end]


def _to_out_rate(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == OUT_SR:
        return x.astype(np.float32, copy=False)
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(sr, OUT_SR)
    return resample_poly(x, OUT_SR // g, sr // g).astype(np.float32)


# Giọng Edge nam (dùng để hạ cao độ giọng Windows dự phòng cho khớp).
MALE_VOICES = ("NamMinh", "Andrew", "Brian", "Guy", "Christopher", "Eric", "Roger", "Steffan", "William", "Ryan")
EDGE_VOICES = ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural", "en-US-EmmaMultilingualNeural",
               "en-US-AvaMultilingualNeural", "vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"]


class EdgeBackend:
    name = "edge"
    online = True

    def __init__(self, voice: str, rate: int, pitch_hz: int = 0) -> None:
        self.voice = voice or EDGE_VOICES[0]
        self.rate = rate
        self.pitch_hz = pitch_hz

    def available(self) -> tuple[bool, str]:
        try:
            import importlib
            importlib.import_module("edge_tts")             # chỉ kiểm tra có cài (import thật, lỗi → ImportError)
            importlib.import_module("miniaudio")
            return True, f"{self.voice} (cần Internet)"
        except ImportError as exc:
            return False, f"Thiếu thư viện: {exc.name}"

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        import edge_tts
        import miniaudio

        async def run() -> bytes:
            comm = edge_tts.Communicate(text, self.voice, rate=f"{int(self.rate):+d}%",
                                        pitch=f"{int(self.pitch_hz):+d}Hz", connect_timeout=6, receive_timeout=15)
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        data = asyncio.run(asyncio.wait_for(run(), timeout=20))
        if not data:
            raise RuntimeError("Dịch vụ edge-tts không trả âm thanh")
        decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1, sample_rate=OUT_SR)
        return np.asarray(decoded.samples, dtype=np.float32), OUT_SR


class WinRTBackend:
    name = "winrt"
    online = False

    def __init__(self, voice_name: str, rate: int, pitch: float = 1.0) -> None:
        self.voice_name = voice_name
        self.rate = rate
        self.pitch = pitch

    def _voice(self):
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        voices = [v for v in SpeechSynthesizer.all_voices if (v.language or "").lower().startswith("vi")]
        if self.voice_name:
            named = [v for v in voices if v.display_name == self.voice_name]
            if named:
                return named[0]
        return voices[0] if voices else None

    def available(self) -> tuple[bool, str]:
        try:
            v = self._voice()
        except Exception as exc:
            return False, f"Không dùng được WinRT: {exc}"
        if v is None:
            return False, "Máy chưa có giọng đọc tiếng Việt (Settings > Time & language > Speech)"
        return True, f"{v.display_name} (offline)"

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        from winrt.windows.storage.streams import DataReader

        async def run() -> bytes:
            s = SpeechSynthesizer()
            v = self._voice()
            if v is None:
                raise RuntimeError("Không có giọng vi-VN")
            s.voice = v
            try:
                s.options.speaking_rate = max(0.5, min(3.0, 1.0 + self.rate / 100.0))
                s.options.audio_pitch = max(0.0, min(2.0, float(self.pitch)))
            except Exception:
                pass
            stream = await s.synthesize_text_to_stream_async(text)
            size = int(stream.size)
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            return bytes(buf)

        return _decode_wav_bytes(asyncio.run(run()))


class SapiBackend:
    name = "sapi"
    online = False

    def _voice(self, sp):
        for v in sp.GetVoices():
            try:
                lang = v.GetAttribute("Language") or ""
            except Exception:
                lang = ""
            if "42a" in lang.lower().split(";"):
                return v
        return None

    def available(self) -> tuple[bool, str]:
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            sp = win32com.client.Dispatch("SAPI.SpVoice")
            v = self._voice(sp)
        except Exception as exc:
            return False, f"Không dùng được SAPI: {exc}"
        if v is None:
            return False, "SAPI5 không có giọng tiếng Việt trên máy này"
        return True, v.GetDescription()

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        import tempfile
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        v = self._voice(sp)
        if v is None:
            raise RuntimeError("Không có giọng SAPI tiếng Việt")
        sp.Voice = v
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "nexa_tts.wav")
            stream.Open(path, 3)  # SSFMCreateForWrite
            sp.AudioOutputStream = stream
            sp.Speak(text)
            stream.Close()
            data = Path(path).read_bytes()
        return _decode_wav_bytes(data)


class TTSManager:
    CACHE_ITEMS = 128
    CACHE_MAX_CHARS = 140

    def __init__(self, config: Any, assets_dir: Path,
                 on_start: Callable[[], None] | None = None,
                 on_end: Callable[[], None] | None = None,
                 on_level: Callable[[float], None] | None = None,
                 on_status: Callable[[str], None] | None = None,
                 on_idle: Callable[[str], None] | None = None,
                 on_bands: Callable[[list[float]], None] | None = None,
                 on_chunk: Callable[[str], None] | None = None) -> None:
        self.config = config
        self.assets_dir = assets_dir
        self.on_idle = on_idle
        self.on_start = on_start
        self.on_end = on_end
        self.on_level = on_level
        self.on_status = on_status
        self.on_bands = on_bands
        self.on_chunk = on_chunk
        self._q: "queue.Queue[_Job | None]" = queue.Queue(maxsize=16)
        self._stop_flag = threading.Event()
        self._speaking = threading.Event()
        self._synth_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nexa-tts-synth")
        self._cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._out = None
        self._out_device: int | None | str = "unset"
        self._thread = threading.Thread(target=self._worker, name="nexa-tts", daemon=True)
        self._running = True
        self.active_backend = ""
        self.last_error = ""
        self._edge_fail_until = 0.0
        self._thread.start()

    # ----- backend -----
    def _male(self) -> bool:
        voice = self.config.get("tts.edge_voice") or ""
        return any(n in voice for n in MALE_VOICES)

    def _backend(self, name: str):
        rate = int(self.config.get("tts.rate") or 0)
        if name == "edge":
            return EdgeBackend(self.config.get("tts.edge_voice"), rate, int(self.config.get("tts.edge_pitch_hz") or 0))
        if name == "winrt":
            pitch = self.config.get("tts.winrt_pitch")
            if pitch is None:
                pitch = 0.6 if self._male() else 1.0
            return WinRTBackend(self.config.get("tts.winrt_voice") or "", rate, float(pitch))
        if name == "sapi":
            return SapiBackend()
        return None

    def chain(self) -> list[str]:
        chosen = (self.config.get("tts.backend") or "auto").lower()
        if chosen == "none":
            return []
        if chosen == "auto":
            return ["edge", "winrt", "sapi"]
        return [chosen]

    def describe_backends(self) -> list[dict[str, Any]]:
        out = []
        for name in ("edge", "winrt", "sapi"):
            try:
                ok, info = self._backend(name).available()
            except Exception as exc:
                ok, info = False, str(exc)
            out.append({"name": name, "available": ok, "info": info, "online": name == "edge"})
        return out

    def winrt_voices(self) -> list[str]:
        try:
            from winrt.windows.media.speechsynthesis import SpeechSynthesizer
            return [v.display_name for v in SpeechSynthesizer.all_voices if (v.language or "").lower().startswith("vi")]
        except Exception:
            return []

    # ----- API -----
    @property
    def speaking(self) -> bool:
        return self._speaking.is_set() or not self._q.empty()

    def speak(self, text: str, wait: bool = False, timeout: float = 30.0) -> None:
        text = (text or "").strip()
        if not text or not self.chain():
            return
        job = _Job("speech", chunks=split_sentences(text), done=threading.Event())
        try:
            self._q.put_nowait(job)
        except queue.Full:
            log.warning("Hàng đợi TTS đầy, bỏ câu: %s", text[:40])
            return
        if wait:
            job.done.wait(timeout)

    def prewarm(self, texts: list[str]) -> None:
        """Tổng hợp trước các câu hay dùng (lời chào…) vào cache, chạy nền."""
        def run() -> None:
            for t in texts:
                for chunk in split_sentences(t):
                    try:
                        self._synthesize(chunk)
                    except Exception:
                        return
        threading.Thread(target=run, name="nexa-tts-prewarm", daemon=True).start()

    def play_sfx(self, name: str, wait: bool = False) -> None:
        if not self.config.get("ui.sounds"):
            return
        samples, sr = sfx.load(name, self.assets_dir)
        job = _Job("sfx", samples=_to_out_rate(samples, sr), sr=OUT_SR, done=threading.Event())
        try:
            self._q.put_nowait(job)
        except queue.Full:
            return
        if wait:
            job.done.wait(5)

    def stop(self) -> None:
        """Dừng câu đang phát và xóa hàng đợi (dùng khi dừng khẩn cấp)."""
        self._stop_flag.set()
        while True:
            try:
                job = self._q.get_nowait()
            except queue.Empty:
                break
            if job and job.done:
                job.done.set()

    def shutdown(self) -> None:
        self._running = False
        self.stop()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        self._close_out()
        self._synth_pool.shutdown(wait=False, cancel_futures=True)

    # ----- tổng hợp -----
    def _cache_key(self, name: str, text: str) -> tuple:
        c = self.config
        return (name, c.get("tts.edge_voice"), c.get("tts.winrt_voice"), c.get("tts.rate"), c.get("tts.edge_pitch_hz"),
                c.get("tts.winrt_pitch"), c.get("tts.effect"), c.get("tts.effect_strength"), text)

    def _synthesize(self, text: str) -> np.ndarray | None:
        """Trả về âm thanh 24 kHz đã áp hiệu ứng, hoặc None nếu mọi backend lỗi."""
        errors = []
        for name in self.chain():
            if name == "edge" and time.monotonic() < self._edge_fail_until:
                continue
            key = self._cache_key(name, text)
            with self._cache_lock:
                hit = self._cache.get(key)
                if hit is not None:
                    self._cache.move_to_end(key)
                    return hit
            backend = self._backend(name)
            ok, info = backend.available()
            if not ok:
                errors.append(f"{name}: {info}")
                continue
            try:
                samples, sr = backend.synth(text)
                audio = _to_out_rate(samples, sr)
                audio = voice_fx.apply(self.config.get("tts.effect") or "none", audio, OUT_SR,
                                       float(self.config.get("tts.effect_strength") or 0.6))
                audio = trim_silence(audio, OUT_SR)
                if self.active_backend != name:
                    self.active_backend = name
                    if self.on_status:
                        self.on_status(f"Giọng nói: {info}")
                self.last_error = ""
                if len(text) <= self.CACHE_MAX_CHARS:
                    with self._cache_lock:
                        self._cache[key] = audio
                        while len(self._cache) > self.CACHE_ITEMS:
                            self._cache.popitem(last=False)
                return audio
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                log.warning("TTS %s lỗi: %s", name, exc)
                if name == "edge":
                    self._edge_fail_until = time.monotonic() + 60  # tạm bỏ qua dịch vụ online 1 phút
        self.last_error = "; ".join(errors) or "Không có backend TTS"
        self.active_backend = ""
        if self.on_status:
            self.on_status("Không phát được giọng nói — em trả lời bằng chữ. " + self.last_error[:160])
        return None

    # ----- phát -----
    def _output_device(self) -> int | None:
        from nexa.audio.pipeline import AudioPipeline
        return AudioPipeline.find_device(self.config.get("audio.output_device"), "output",
                                         self.config.get("audio.preferred_hostapi") or "MME")

    def _ensure_out(self):
        import sounddevice as sd
        device = self._output_device()
        if self._out is not None and device == self._out_device:
            return self._out
        self._close_out()
        self._out = sd.OutputStream(samplerate=OUT_SR, channels=1, dtype="float32", device=device,
                                    latency="low")
        self._out.start()
        self._out_device = device
        return self._out

    def _close_out(self) -> None:
        if self._out is not None:
            try:
                self._out.stop()
                self._out.close()
            except Exception:
                pass
        self._out = None
        self._out_device = "unset"

    def _play(self, data: np.ndarray) -> None:
        volume = float(self.config.get("tts.volume") or 1.0)
        data = np.clip(data * volume, -1, 1).astype(np.float32)
        block = int(OUT_SR * 0.03)
        for attempt in range(2):
            try:
                out = self._ensure_out()
                for i in range(0, data.size, block):
                    if self._stop_flag.is_set():
                        break
                    chunk = data[i:i + block]
                    out.write(chunk.reshape(-1, 1))
                    if self.on_level:
                        self.on_level(min(1.0, float(np.sqrt(np.mean(chunk * chunk) + 1e-12)) * 4.0))
                    if self.on_bands:
                        self.on_bands(spectrum_bands(chunk))
                break
            except Exception:
                log.warning("Luồng loa lỗi, mở lại (lần %d)", attempt + 1)
                self._close_out()
                if attempt == 1:
                    raise
        if self.on_level:
            self.on_level(0.0)
        if self.on_bands:
            self.on_bands([0.0] * N_BANDS)

    def _chunk(self, text: str) -> None:
        if self.on_chunk:
            try:
                self.on_chunk(text)
            except Exception:
                log.exception("on_chunk lỗi")

    def _play_speech(self, job: _Job) -> None:
        """Tổng hợp câu i+1 trong lúc phát câu i."""
        chunks = job.chunks
        future = self._synth_pool.submit(self._synthesize, chunks[0])
        started = False
        for i in range(len(chunks)):
            audio = future.result()
            if i + 1 < len(chunks):
                future = self._synth_pool.submit(self._synthesize, chunks[i + 1])
            if self._stop_flag.is_set():
                break
            if audio is None:
                continue
            if not started:
                started = True
                self._speaking.set()
                if self.on_start:
                    self.on_start()
            self._chunk(chunks[i])
            self._play(audio)
        if started:
            self._chunk("")
            self._speaking.clear()
            if self.on_end:
                self.on_end()

    def _worker(self) -> None:
        while self._running:
            job = self._q.get()
            if job is None:
                break
            self._stop_flag.clear()
            try:
                if job.kind == "speech":
                    self._play_speech(job)
                else:
                    self._speaking.set()
                    if self.on_start:
                        self.on_start()
                    try:
                        self._play(job.samples)
                    finally:
                        self._speaking.clear()
                        if self.on_end:
                            self.on_end()
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("Lỗi phát âm thanh")
                self._speaking.clear()
            finally:
                if job.done:
                    job.done.set()
                if self._q.empty() and self.on_idle:
                    try:
                        self.on_idle(job.kind)
                    except Exception:
                        log.exception("on_idle lỗi")
